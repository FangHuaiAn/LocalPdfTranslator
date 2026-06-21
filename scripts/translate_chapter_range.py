#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.local_pdf_translator.markdown_pipeline import chunk_markdown, normalize_markdown
from src.local_pdf_translator.prompt import PROMPT_VERSION, build_translation_messages


DURATION_FIELDS = {
    "total_duration": "ollama_total_seconds",
    "load_duration": "ollama_load_seconds",
    "prompt_eval_duration": "ollama_prompt_eval_seconds",
    "eval_duration": "ollama_eval_seconds",
}


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir
    chunks_dir = out_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    source_markdown = args.source_md.read_text(encoding="utf-8")
    raw_chapters = extract_chapter_range(
        source_markdown,
        start_chapter=args.start_chapter,
        end_chapter=args.end_chapter,
    )
    raw_chapters = promote_chapter_headings(raw_chapters)
    normalized = normalize_markdown(raw_chapters)
    chunks = chunk_markdown(
        normalized,
        document_id=args.document_id,
        max_chars=args.chunk_max_chars,
    )

    (out_dir / "document.en.raw.md").write_text(raw_chapters, encoding="utf-8")
    (out_dir / "document.en.normalized.md").write_text(normalized, encoding="utf-8")
    for chunk in chunks:
        (chunks_dir / f"{chunk.chunk_id}.en.md").write_text(
            chunk.source_text,
            encoding="utf-8",
        )

    records = load_records(out_dir / "chunk-timing.jsonl")
    write_metadata(
        out_dir,
        args=args,
        total_chunks=len(chunks),
        completed_chunks=count_completed(records),
        failed_chunks=count_failed(records),
        status="Prepared" if args.dry_run else "Translating",
    )
    if args.dry_run:
        write_report(out_dir, args=args, chunks=chunks, records=records)
        print(
            f"Prepared {len(chunks)} chunks in {out_dir} "
            f"from chapters {args.start_chapter}-{args.end_chapter}."
        )
        return 0

    started_all = time.perf_counter()
    for chunk in chunks:
        zh_path = chunks_dir / f"{chunk.chunk_id}.zh-TW.md"
        if zh_path.exists() and chunk.chunk_id in records:
            print(
                f"[skip] {chunk.chunk_id} already translated "
                f"({records[chunk.chunk_id].get('elapsed_seconds', 0):.1f}s)",
                flush=True,
            )
            continue

        chapter = chunk.heading_path[0] if chunk.heading_path else ""
        print(
            f"[start] {chunk.order}/{len(chunks)} {chunk.chunk_id} "
            f"{chapter} source_chars={len(chunk.source_text)}",
            flush=True,
        )
        started_at = utc_now()
        start = time.perf_counter()
        try:
            translated, response_body = chat_with_ollama(
                host=args.ollama_host,
                model=args.model,
                messages=build_translation_messages(chunk),
                temperature=args.temperature,
                top_p=args.top_p,
                timeout=args.timeout_seconds,
            )
            elapsed = time.perf_counter() - start
            finished_at = utc_now()
            zh_path.write_text(translated.strip() + "\n", encoding="utf-8")
            record = build_record(
                chunk=chunk,
                chapter=chapter,
                translated=translated,
                elapsed=elapsed,
                started_at=started_at,
                finished_at=finished_at,
                model=args.model,
                response_body=response_body,
                status="translated",
            )
            records[chunk.chunk_id] = record
            write_records(out_dir / "chunk-timing.jsonl", records)
            write_timing_csv(out_dir / "chunk-timing.csv", records)
            write_stitched_translation(out_dir, chunks)
            write_metadata(
                out_dir,
                args=args,
                total_chunks=len(chunks),
                completed_chunks=count_completed(records),
                failed_chunks=count_failed(records),
                status=(
                    "Completed"
                    if count_completed(records) == len(chunks)
                    else "Translating"
                ),
            )
            write_report(out_dir, args=args, chunks=chunks, records=records)
            print(
                f"[done] {chunk.chunk_id} elapsed={elapsed:.1f}s "
                f"cjk={record['output_cjk_chars']} "
                f"sec_per_1000_cjk={record['seconds_per_1000_cjk_chars']:.1f}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - this is a batch runner.
            elapsed = time.perf_counter() - start
            finished_at = utc_now()
            record = build_record(
                chunk=chunk,
                chapter=chapter,
                translated="",
                elapsed=elapsed,
                started_at=started_at,
                finished_at=finished_at,
                model=args.model,
                response_body={},
                status="failed",
            )
            record["error"] = str(exc)
            records[chunk.chunk_id] = record
            write_records(out_dir / "chunk-timing.jsonl", records)
            write_timing_csv(out_dir / "chunk-timing.csv", records)
            write_metadata(
                out_dir,
                args=args,
                total_chunks=len(chunks),
                completed_chunks=count_completed(records),
                failed_chunks=count_failed(records),
                status="Failed",
            )
            write_report(out_dir, args=args, chunks=chunks, records=records)
            print(f"[failed] {chunk.chunk_id} after {elapsed:.1f}s: {exc}", flush=True)
            return 1

    total_elapsed = time.perf_counter() - started_all
    write_report(out_dir, args=args, chunks=chunks, records=records)
    print(f"Finished chapters in {total_elapsed:.1f}s", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate a chapter range and record per-chunk timing.",
    )
    parser.add_argument(
        "--source-md",
        type=Path,
        default=Path("output/war-peace-war-zh/document.en.raw.md"),
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--document-id", default="war-peace-war-chapter-range")
    parser.add_argument("--start-chapter", type=int, required=True)
    parser.add_argument("--end-chapter", type=int, required=True)
    parser.add_argument("--chunk-max-chars", type=int, default=3000)
    parser.add_argument("--model", default="gemma4:e4b-it-q4_K_M")
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def extract_chapter_range(
    markdown: str,
    *,
    start_chapter: int,
    end_chapter: int,
) -> str:
    lines = markdown.splitlines()
    start_marker = f"Chapter {start_chapter}"
    next_marker = f"Chapter {end_chapter + 1}"
    try:
        start = next(index for index, line in enumerate(lines) if line == start_marker)
        end = next(
            index
            for index, line in enumerate(lines[start + 1 :], start + 1)
            if line == next_marker
        )
    except StopIteration as exc:
        raise ValueError(
            f"Could not find chapter range {start_chapter}-{end_chapter}"
        ) from exc
    return "\n".join(lines[start:end]).strip() + "\n"


def promote_chapter_headings(markdown: str) -> str:
    lines = markdown.splitlines()
    promoted: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if re.fullmatch(r"Chapter \d+", line):
            promoted.append(f"# {line}")
            index += 1
            if index < len(lines) and not lines[index].strip():
                index += 1
            if index < len(lines) and lines[index].strip():
                promoted.extend(["", f"## {lines[index].strip()}"])
                index += 1
            if index < len(lines) and not lines[index].strip():
                index += 1
            if index < len(lines) and lines[index].strip():
                promoted.extend(["", f"*{lines[index].strip()}*"])
                index += 1
            promoted.append("")
            if index < len(lines) and not lines[index].strip():
                index += 1
            continue
        promoted.append(line)
        index += 1
    return "\n".join(promoted).strip() + "\n"


def chat_with_ollama(
    *,
    host: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float,
    timeout: float,
) -> tuple[str, dict[str, object]]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    if "message" in body and "content" in body["message"]:
        return str(body["message"]["content"]).strip(), body
    if "response" in body:
        return str(body["response"]).strip(), body
    raise ValueError("Ollama response did not contain translated content")


def build_record(
    *,
    chunk,
    chapter: str,
    translated: str,
    elapsed: float,
    started_at: str,
    finished_at: str,
    model: str,
    response_body: dict[str, object],
    status: str,
) -> dict[str, object]:
    output_cjk_chars = count_cjk_chars(translated)
    seconds_per_1000 = (
        elapsed / (output_cjk_chars / 1000) if output_cjk_chars else 0.0
    )
    record: dict[str, object] = {
        "chunk_id": chunk.chunk_id,
        "order": chunk.order,
        "chapter": chapter,
        "heading_path": list(chunk.heading_path),
        "status": status,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "source_chars": len(chunk.source_text),
        "source_bytes": len(chunk.source_text.encode("utf-8")),
        "output_chars": len(translated),
        "output_bytes": len(translated.encode("utf-8")),
        "output_cjk_chars": output_cjk_chars,
        "elapsed_seconds": round(elapsed, 3),
        "seconds_per_1000_cjk_chars": round(seconds_per_1000, 3),
        "cjk_chars_per_second": round(output_cjk_chars / elapsed, 3)
        if elapsed
        else 0.0,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    for source_key, target_key in DURATION_FIELDS.items():
        duration = response_body.get(source_key)
        if isinstance(duration, int | float):
            record[target_key] = round(float(duration) / 1_000_000_000, 3)
    for count_key in ("prompt_eval_count", "eval_count"):
        count = response_body.get(count_key)
        if isinstance(count, int):
            record[count_key] = count
    return record


def count_cjk_chars(text: str) -> int:
    return sum(
        1
        for char in text
        if "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
    )


def load_records(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        records[str(record["chunk_id"])] = record
    return records


def write_records(path: Path, records: dict[str, dict[str, object]]) -> None:
    ordered = sorted(records.values(), key=lambda record: int(record["order"]))
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in ordered),
        encoding="utf-8",
    )


def write_timing_csv(path: Path, records: dict[str, dict[str, object]]) -> None:
    fieldnames = [
        "chunk_id",
        "order",
        "chapter",
        "status",
        "source_chars",
        "output_chars",
        "output_cjk_chars",
        "elapsed_seconds",
        "seconds_per_1000_cjk_chars",
        "cjk_chars_per_second",
        "ollama_total_seconds",
        "ollama_eval_seconds",
        "prompt_eval_count",
        "eval_count",
        "started_at",
        "finished_at",
    ]
    rows = sorted(records.values(), key=lambda record: int(record["order"]))
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_stitched_translation(out_dir: Path, chunks) -> None:
    translated: list[str] = []
    chunks_dir = out_dir / "chunks"
    for chunk in chunks:
        zh_path = chunks_dir / f"{chunk.chunk_id}.zh-TW.md"
        if not zh_path.exists():
            continue
        translated.append(zh_path.read_text(encoding="utf-8").strip())
    if translated:
        (out_dir / "document.zh-TW.md").write_text(
            "\n\n".join(translated).strip() + "\n",
            encoding="utf-8",
        )


def write_metadata(
    out_dir: Path,
    *,
    args: argparse.Namespace,
    total_chunks: int,
    completed_chunks: int,
    failed_chunks: int,
    status: str,
) -> None:
    metadata = {
        "status": status,
        "source_markdown": str(args.source_md),
        "start_chapter": args.start_chapter,
        "end_chapter": args.end_chapter,
        "model": args.model,
        "ollama_host": args.ollama_host,
        "chunk_max_chars": args.chunk_max_chars,
        "total_chunks": total_chunks,
        "completed_chunks": completed_chunks,
        "failed_chunks": failed_chunks,
        "updated_at": utc_now(),
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_report(
    out_dir: Path,
    *,
    args: argparse.Namespace,
    chunks,
    records: dict[str, dict[str, object]],
) -> None:
    completed = [
        record
        for record in sorted(records.values(), key=lambda item: int(item["order"]))
        if record.get("status") == "translated"
    ]
    failed = [
        record
        for record in sorted(records.values(), key=lambda item: int(item["order"]))
        if record.get("status") == "failed"
    ]
    lines = [
        f"# Chapter {args.start_chapter}-{args.end_chapter} Translation Timing",
        "",
        f"- Model: `{args.model}`",
        f"- Chunk max chars: `{args.chunk_max_chars}`",
        f"- Total chunks: {len(chunks)}",
        f"- Completed chunks: {len(completed)}",
        f"- Failed chunks: {len(failed)}",
    ]
    if completed:
        total_elapsed = sum(float(record["elapsed_seconds"]) for record in completed)
        total_cjk = sum(int(record["output_cjk_chars"]) for record in completed)
        rates = [
            float(record["seconds_per_1000_cjk_chars"])
            for record in completed
            if float(record["seconds_per_1000_cjk_chars"]) > 0
        ]
        lines.extend(
            [
                f"- Total elapsed seconds: {total_elapsed:.1f}",
                f"- Total output CJK chars: {total_cjk}",
                f"- Overall seconds / 1000 CJK chars: {total_elapsed / (total_cjk / 1000):.1f}",
                f"- Median seconds / 1000 CJK chars: {statistics.median(rates):.1f}",
            ]
        )
        fastest = min(completed, key=lambda item: float(item["seconds_per_1000_cjk_chars"]))
        slowest = max(completed, key=lambda item: float(item["seconds_per_1000_cjk_chars"]))
        lines.extend(
            [
                f"- Fastest chunk: {fastest['chunk_id']} ({float(fastest['seconds_per_1000_cjk_chars']):.1f} sec / 1000 CJK chars)",
                f"- Slowest chunk: {slowest['chunk_id']} ({float(slowest['seconds_per_1000_cjk_chars']):.1f} sec / 1000 CJK chars)",
                f"- Slowest / fastest ratio: {float(slowest['seconds_per_1000_cjk_chars']) / float(fastest['seconds_per_1000_cjk_chars']):.2f}x",
            ]
        )
        lines.extend(["", "## By Chapter", ""])
        lines.append(
            "| Chapter | Chunks | Output CJK chars | Elapsed seconds | Sec / 1000 CJK chars |"
        )
        lines.append("|---|---:|---:|---:|---:|")
        for chapter in sorted({str(record["chapter"]) for record in completed}):
            chapter_records = [
                record for record in completed if str(record["chapter"]) == chapter
            ]
            elapsed = sum(float(record["elapsed_seconds"]) for record in chapter_records)
            cjk_chars = sum(int(record["output_cjk_chars"]) for record in chapter_records)
            lines.append(
                f"| {chapter} | {len(chapter_records)} | {cjk_chars} | "
                f"{elapsed:.1f} | {elapsed / (cjk_chars / 1000):.1f} |"
            )
    if failed:
        lines.extend(["", "## Failed Chunks", ""])
        for record in failed:
            lines.append(
                f"- {record['chunk_id']}: {record.get('error', 'unknown error')}"
            )
    lines.extend(["", "## Per Chunk", ""])
    lines.append(
        "| Chunk | Chapter | Source chars | Output CJK chars | Seconds | Sec / 1000 CJK chars |"
    )
    lines.append("|---|---|---:|---:|---:|---:|")
    for chunk in chunks:
        record = records.get(chunk.chunk_id)
        if record is None:
            lines.append(f"| {chunk.chunk_id} | | {len(chunk.source_text)} | | | |")
            continue
        lines.append(
            f"| {record['chunk_id']} | {record.get('chapter', '')} | "
            f"{record['source_chars']} | {record['output_cjk_chars']} | "
            f"{float(record['elapsed_seconds']):.1f} | "
            f"{float(record['seconds_per_1000_cjk_chars']):.1f} |"
        )
    lines.append("")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def count_completed(records: dict[str, dict[str, object]]) -> int:
    return sum(1 for record in records.values() if record.get("status") == "translated")


def count_failed(records: dict[str, dict[str, object]]) -> int:
    return sum(1 for record in records.values() if record.get("status") == "failed")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
