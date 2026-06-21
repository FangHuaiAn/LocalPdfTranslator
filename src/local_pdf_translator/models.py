from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4


class JobStatus(str, Enum):
    CREATED = "Created"
    CLASSIFIED = "Classified"
    CONVERTED = "Converted"
    NORMALIZED = "Normalized"
    CHUNKED = "Chunked"
    TRANSLATING = "Translating"
    PAUSED = "Paused"
    FAILED = "Failed"
    COMPLETED_WITH_WARNINGS = "CompletedWithWarnings"
    COMPLETED = "Completed"


class ChunkType(str, Enum):
    HEADING = "Heading"
    PARAGRAPH = "Paragraph"
    LIST = "List"
    TABLE = "Table"
    BLOCKQUOTE = "Blockquote"
    CODE_BLOCK = "CodeBlock"
    FOOTNOTE = "Footnote"
    REFERENCE = "Reference"
    MIXED_SECTION = "MixedSection"


class ChunkStatus(str, Enum):
    PENDING = "Pending"
    TRANSLATING = "Translating"
    TRANSLATED = "Translated"
    FAILED = "Failed"
    SKIPPED = "Skipped"


class SourceFormat(str, Enum):
    PDF = "pdf"
    EPUB = "epub"


def source_format_from_path(path: Path) -> SourceFormat:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return SourceFormat.PDF
    if suffix == ".epub":
        return SourceFormat.EPUB
    raise ValueError(f"Unsupported source format: {suffix or '<none>'}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _datetime_to_json(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime_from_json(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _path_to_json(value: Path | None) -> str | None:
    return str(value) if value is not None else None


def _path_from_json(value: str | None) -> Path | None:
    return Path(value) if value else None


@dataclass(slots=True)
class QAResult:
    check_name: str
    passed: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QAResult":
        return cls(
            check_name=data["check_name"],
            passed=bool(data["passed"]),
            warnings=list(data.get("warnings", [])),
            errors=list(data.get("errors", [])),
        )


@dataclass(slots=True)
class GlossaryEntry:
    english: str
    zh_tw: str
    term_type: str = ""
    force: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "english": self.english,
            "zh_tw": self.zh_tw,
            "term_type": self.term_type,
            "force": self.force,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GlossaryEntry":
        return cls(
            english=data["english"],
            zh_tw=data["zh_tw"],
            term_type=data.get("term_type", ""),
            force=bool(data.get("force", False)),
            note=data.get("note", ""),
        )


@dataclass(slots=True)
class Document:
    document_id: str
    source_pdf: Path
    raw_markdown_path: Path | None = None
    normalized_markdown_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_pdf": _path_to_json(self.source_pdf),
            "raw_markdown_path": _path_to_json(self.raw_markdown_path),
            "normalized_markdown_path": _path_to_json(self.normalized_markdown_path),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        raw_markdown_path = _path_from_json(data.get("raw_markdown_path"))
        normalized_markdown_path = _path_from_json(data.get("normalized_markdown_path"))
        return cls(
            document_id=data["document_id"],
            source_pdf=Path(data["source_pdf"]),
            raw_markdown_path=raw_markdown_path,
            normalized_markdown_path=normalized_markdown_path,
        )


@dataclass(slots=True)
class Chunk:
    document_id: str
    chunk_id: str
    order: int
    chunk_type: ChunkType
    heading_path: list[str]
    source_text: str
    source_hash: str
    translation_text: str = ""
    status: ChunkStatus = ChunkStatus.PENDING
    model: str = ""
    prompt_version: str = ""
    translated_at: datetime | None = None
    retry_count: int = 0
    qa_results: list[QAResult] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        document_id: str,
        chunk_id: str,
        order: int,
        chunk_type: ChunkType,
        heading_path: list[str],
        source_text: str,
    ) -> "Chunk":
        return cls(
            document_id=document_id,
            chunk_id=chunk_id,
            order=order,
            chunk_type=chunk_type,
            heading_path=list(heading_path),
            source_text=source_text,
            source_hash=sha256(source_text.encode("utf-8")).hexdigest(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "order": self.order,
            "chunk_type": self.chunk_type.value,
            "heading_path": list(self.heading_path),
            "source_text": self.source_text,
            "source_hash": self.source_hash,
            "translation_text": self.translation_text,
            "status": self.status.value,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "translated_at": _datetime_to_json(self.translated_at),
            "retry_count": self.retry_count,
            "qa_results": [result.to_dict() for result in self.qa_results],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chunk":
        return cls(
            document_id=data["document_id"],
            chunk_id=data["chunk_id"],
            order=int(data["order"]),
            chunk_type=ChunkType(data["chunk_type"]),
            heading_path=list(data.get("heading_path", [])),
            source_text=data["source_text"],
            source_hash=data["source_hash"],
            translation_text=data.get("translation_text", ""),
            status=ChunkStatus(data.get("status", ChunkStatus.PENDING.value)),
            model=data.get("model", ""),
            prompt_version=data.get("prompt_version", ""),
            translated_at=_datetime_from_json(data.get("translated_at")),
            retry_count=int(data.get("retry_count", 0)),
            qa_results=[
                QAResult.from_dict(result) for result in data.get("qa_results", [])
            ],
        )


@dataclass(slots=True)
class Job:
    job_id: str
    source_pdf: Path
    output_dir: Path
    created_at: datetime
    source_format: SourceFormat = SourceFormat.PDF
    status: JobStatus = JobStatus.CREATED
    model: str = ""
    translation_profile: str = "Balanced"
    prompt_version: str = "prompt-v1"
    glossary_enabled: bool = False
    traditional_chinese_conversion_enabled: bool = False
    total_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        source_pdf: Path,
        output_dir: Path,
        job_id: str | None = None,
        model: str = "",
        translation_profile: str = "Balanced",
        prompt_version: str = "prompt-v1",
        source_format: SourceFormat | None = None,
    ) -> "Job":
        source_path = Path(source_pdf)
        return cls(
            job_id=job_id or f"job-{uuid4().hex[:12]}",
            source_pdf=source_path,
            output_dir=Path(output_dir),
            created_at=_utc_now(),
            source_format=source_format or source_format_from_path(source_path),
            model=model,
            translation_profile=translation_profile,
            prompt_version=prompt_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "source_path": _path_to_json(self.source_pdf),
            "source_pdf": _path_to_json(self.source_pdf),
            "output_dir": _path_to_json(self.output_dir),
            "created_at": _datetime_to_json(self.created_at),
            "source_format": self.source_format.value,
            "status": self.status.value,
            "model": self.model,
            "translation_profile": self.translation_profile,
            "prompt_version": self.prompt_version,
            "glossary_enabled": self.glossary_enabled,
            "traditional_chinese_conversion_enabled": (
                self.traditional_chinese_conversion_enabled
            ),
            "total_chunks": self.total_chunks,
            "completed_chunks": self.completed_chunks,
            "failed_chunks": self.failed_chunks,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        return cls(
            job_id=data["job_id"],
            source_pdf=Path(data.get("source_path", data["source_pdf"])),
            output_dir=Path(data["output_dir"]),
            created_at=_datetime_from_json(data["created_at"]) or _utc_now(),
            source_format=SourceFormat(data.get("source_format", SourceFormat.PDF.value)),
            status=JobStatus(data.get("status", JobStatus.CREATED.value)),
            model=data.get("model", ""),
            translation_profile=data.get("translation_profile", "Balanced"),
            prompt_version=data.get("prompt_version", "prompt-v1"),
            glossary_enabled=bool(data.get("glossary_enabled", False)),
            traditional_chinese_conversion_enabled=bool(
                data.get("traditional_chinese_conversion_enabled", False)
            ),
            total_chunks=int(data.get("total_chunks", 0)),
            completed_chunks=int(data.get("completed_chunks", 0)),
            failed_chunks=int(data.get("failed_chunks", 0)),
            warnings=list(data.get("warnings", [])),
        )
