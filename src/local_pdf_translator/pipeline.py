from __future__ import annotations

from pathlib import Path

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
            translated = client.chat(
                model=job.model,
                messages=build_translation_messages(chunk),
                temperature=temperature,
                top_p=top_p,
            )
            chunk.translation_text = translated.strip()
            chunk.status = ChunkStatus.TRANSLATED
            zh_path.write_text(chunk.translation_text + "\n", encoding="utf-8")

        translated_paths.append(zh_path)
        job.completed_chunks += 1
        save_job_metadata(job)

    stitched = _stitch_translations(translated_paths)
    (job.output_dir / "document.zh-TW.md").write_text(stitched, encoding="utf-8")

    job.status = JobStatus.COMPLETED
    job.failed_chunks = 0
    save_job_metadata(job)
    _write_report(job)
    return job


def _stitch_translations(paths: list[Path]) -> str:
    parts = [path.read_text(encoding="utf-8").strip() for path in paths]
    return "\n\n".join(part for part in parts if part) + "\n"


def _write_report(job: Job) -> None:
    report = "\n".join(
        [
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
            "",
        ]
    )
    (job.output_dir / "report.md").write_text(report, encoding="utf-8")
