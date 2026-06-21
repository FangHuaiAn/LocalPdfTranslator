from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .epub import convert_epub_to_markdown
from .models import JobStatus, SourceFormat
from .pdf import convert_pdf_to_markdown
from .pipeline import run_markdown_translation_pipeline
from .workspace import create_job_workspace, save_job_metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local-pdf-translator",
        description="Local PDF to Traditional Chinese Markdown translation pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    translate = subparsers.add_parser(
        "translate",
        help="Create a translation job for one English PDF or EPUB.",
    )
    translate.add_argument("source_path", type=Path, help="Path to the source PDF or EPUB.")
    translate.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory that will contain job output folders.",
    )
    translate.add_argument("--job-id", help="Optional stable job id.")
    translate.add_argument("--model", default="", help="Ollama model name.")
    translate.add_argument(
        "--ollama-host",
        default="http://localhost:11434",
        help="Ollama HTTP host.",
    )
    translate.add_argument(
        "--chunk-max-chars",
        type=int,
        default=3000,
        help="Maximum approximate characters per Markdown chunk.",
    )
    translate.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Ollama temperature option.",
    )
    translate.add_argument(
        "--top-p",
        type=float,
        default=0.9,
        help="Ollama top_p option.",
    )
    translate.add_argument(
        "--profile",
        default="Balanced",
        help="Translation profile name, such as Fast, Balanced, or Quality.",
    )
    translate.set_defaults(handler=_handle_translate)

    resume = subparsers.add_parser("resume", help="Resume an existing job.")
    resume.add_argument("job_dir", type=Path, help="Existing job output directory.")
    resume.set_defaults(handler=_handle_not_implemented)

    inspect = subparsers.add_parser("inspect", help="Inspect job status and warnings.")
    inspect.add_argument("job_dir", type=Path, help="Existing job output directory.")
    inspect.set_defaults(handler=_handle_not_implemented)

    models = subparsers.add_parser("models", help="List locally available Ollama models.")
    models.set_defaults(handler=_handle_not_implemented)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))


def _handle_translate(args: argparse.Namespace) -> int:
    job = create_job_workspace(
        source_pdf=args.source_path,
        output_root=args.output_dir,
        job_id=args.job_id,
        model=args.model,
        translation_profile=args.profile,
    )
    if job.source_format is SourceFormat.EPUB:
        raw_markdown = convert_epub_to_markdown(job.source_pdf)
        (job.output_dir / "document.en.raw.md").write_text(
            raw_markdown,
            encoding="utf-8",
        )
        job.status = JobStatus.CONVERTED
        save_job_metadata(job)
    elif job.source_format is SourceFormat.PDF:
        raw_markdown = convert_pdf_to_markdown(job.source_pdf)
        (job.output_dir / "document.en.raw.md").write_text(
            raw_markdown,
            encoding="utf-8",
        )
        job.status = JobStatus.CONVERTED
        save_job_metadata(job)
    if job.model:
        run_markdown_translation_pipeline(
            job,
            ollama_host=args.ollama_host,
            chunk_max_chars=args.chunk_max_chars,
            temperature=args.temperature,
            top_p=args.top_p,
        )
    print(job.output_dir)
    return 0


def _handle_not_implemented(args: argparse.Namespace) -> int:
    print(f"{args.command} is planned but not implemented yet.")
    return 2
