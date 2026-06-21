from __future__ import annotations

import json
import shutil
from pathlib import Path

from .models import Job, source_format_from_path


def create_job_workspace(
    source_pdf: Path,
    output_root: Path,
    *,
    job_id: str | None = None,
    model: str = "",
    translation_profile: str = "Balanced",
    prompt_version: str = "prompt-v1",
    overwrite: bool = False,
) -> Job:
    source_pdf = Path(source_pdf)
    if not source_pdf.exists():
        raise FileNotFoundError(f"Source file does not exist: {source_pdf}")
    if not source_pdf.is_file():
        raise ValueError(f"Source path is not a file: {source_pdf}")
    source_format = source_format_from_path(source_pdf)

    output_root = Path(output_root)
    effective_job_id = job_id or source_pdf.stem
    output_dir = output_root / effective_job_id

    if output_dir.exists() and not overwrite:
        raise FileExistsError(f"Job output directory already exists: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=overwrite)
    chunks_dir = output_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)

    shutil.copy2(source_pdf, output_dir / f"document.original{source_pdf.suffix.lower()}")

    job = Job.create(
        job_id=effective_job_id,
        source_pdf=source_pdf,
        output_dir=output_dir,
        model=model,
        translation_profile=translation_profile,
        prompt_version=prompt_version,
        source_format=source_format,
    )
    _write_json(output_dir / "metadata.json", job.to_dict())
    _write_initial_report(output_dir / "report.md", job)

    return job


def save_job_metadata(job: Job) -> None:
    _write_json(job.output_dir / "metadata.json", job.to_dict())


def _write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_initial_report(path: Path, job: Job) -> None:
    content = "\n".join(
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
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
