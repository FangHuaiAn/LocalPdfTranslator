from __future__ import annotations

from pathlib import Path
import time

from .markdown_pipeline import chunk_markdown, normalize_markdown
from .models import ChunkStatus, Job, JobStatus
from .ollama import OllamaClient
from .prompt import build_translation_messages
from .workspace import save_job_metadata


def run_markdown_translation_pipeline(
    job: Job,
    *,
    ollama_host: str = "http://localhost:11434",
    chunk_max_chars: int = 3000,
    temperature: float = 0.1,
    top_p: float = 0.9,
    timeout: float = 120.0,
) -> Job:
    raw_path = job.output_dir / "document.en.raw.md"
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw Markdown does not exist: {raw_path}")

    normalized = normalize_markdown(raw_path.read_text(encoding="utf-8"))
    normalized_path = job.output_dir / "document.en.normalized.md"
    normalized_path.write_text(normalized, encoding="utf-8")

    chunks = chunk_markdown(
        normalized,
        document_id=job.job_id,
        max_chars=chunk_max_chars,
    )
    chunks_dir = job.output_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    client = OllamaClient(ollama_host, timeout=timeout)

    job.status = JobStatus.TRANSLATING
    job.total_chunks = len(chunks)
    job.completed_chunks = 0
    job.failed_chunks = 0
    save_job_metadata(job)

    total_chars_translated = 0
    total_translation_seconds = 0.0
    chunk_timings = []

    translated_paths: list[Path] = []
    for chunk in chunks:
        en_path = chunks_dir / f"{chunk.chunk_id}.en.md"
        zh_path = chunks_dir / f"{chunk.chunk_id}.zh-TW.md"
        en_path.write_text(chunk.source_text, encoding="utf-8")

        if zh_path.exists():
            chunk.translation_text = zh_path.read_text(encoding="utf-8").strip()
            chunk.status = ChunkStatus.TRANSLATED
        else:
            chunk.status = ChunkStatus.TRANSLATING
            start_time = time.time()
            translated = client.chat(
                model=job.model,
                messages=build_translation_messages(chunk),
                temperature=temperature,
                top_p=top_p,
            )
            duration = time.time() - start_time
            chunk.translation_text = translated.strip()
            chunk.status = ChunkStatus.TRANSLATED
            zh_path.write_text(chunk.translation_text + "\n", encoding="utf-8")
            
            char_count = len(chunk.source_text)
            total_chars_translated += char_count
            total_translation_seconds += duration
            chunk_timings.append((chunk.chunk_id, char_count, duration))
            print(f"[Timing] Translated {chunk.chunk_id} ({char_count} chars) in {duration:.2f}s (Speed: {(duration / char_count * 1000):.2f}s per 1k chars)")

        translated_paths.append(zh_path)
        job.completed_chunks += 1
        save_job_metadata(job)

    stitched = _stitch_translations(translated_paths)
    (job.output_dir / "document.zh-TW.md").write_text(stitched, encoding="utf-8")

    job.status = JobStatus.COMPLETED
    job.failed_chunks = 0
    save_job_metadata(job)
    
    avg_speed = (total_translation_seconds / total_chars_translated * 1000) if total_chars_translated > 0 else 0.0
    if total_chars_translated > 0:
        print(f"[Timing Summary] Translated {total_chars_translated} chars in {total_translation_seconds:.2f}s (Avg: {avg_speed:.2f}s per 1k chars)")
        
    _write_report(
        job,
        total_chars=total_chars_translated,
        total_time=total_translation_seconds,
        avg_speed=avg_speed,
        chunk_timings=chunk_timings
    )
    return job


def _stitch_translations(paths: list[Path]) -> str:
    parts = [path.read_text(encoding="utf-8").strip() for path in paths]
    return "\n\n".join(part for part in parts if part) + "\n"


def _write_report(
    job: Job,
    total_chars: int = 0,
    total_time: float = 0.0,
    avg_speed: float = 0.0,
    chunk_timings: list[tuple[str, int, float]] | None = None,
) -> None:
    lines = [
        f"# Processing Report: {job.job_id}",
        "",
        "## Status",
        "",
        f"- Current status: {job.status.value}",
        f"- Source file: `{job.source_pdf}`",
        f"- Source format: `{job.source_format.value}`",
        f"- Output directory: `{job.output_dir}`",
        f"- Model: `{job.model or 'not set'}`",
        f"- Translation profile: `{job.translation_profile}`",
        f"- Total chunks: {job.total_chunks}",
        f"- Completed chunks: {job.completed_chunks}",
        f"- Failed chunks: {job.failed_chunks}",
    ]
    
    if total_chars > 0:
        lines.extend([
            "",
            "## Performance Summary",
            "",
            f"- Total source characters translated: {total_chars}",
            f"- Total translation duration: {total_time:.2f} seconds",
            f"- Average processing speed: {avg_speed:.2f} seconds per 1,000 characters",
        ])
        
    if chunk_timings:
        lines.extend([
            "",
            "## Chunk Breakdown",
            "",
            "| Chunk ID | Character Count | Duration (s) | Processing Speed (s per 1k chars) |",
            "| --- | --- | --- | --- |",
        ])
        for chunk_id, char_count, duration in chunk_timings:
            speed = (duration / char_count * 1000) if char_count > 0 else 0.0
            lines.append(f"| {chunk_id} | {char_count} | {duration:.2f}s | {speed:.2f}s |")
            
    lines.append("")
    report = "\n".join(lines)
    (job.output_dir / "report.md").write_text(report, encoding="utf-8")
