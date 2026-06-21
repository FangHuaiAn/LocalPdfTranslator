from __future__ import annotations

import re

from .models import Chunk, ChunkType


def normalize_markdown(markdown: str) -> str:
    lines = [line.rstrip() for line in markdown.replace("\r\n", "\n").split("\n")]
    return _collapse_blank_lines("\n".join(lines)).strip() + "\n"


def chunk_markdown(
    markdown: str,
    *,
    document_id: str,
    max_chars: int = 3000,
) -> list[Chunk]:
    blocks = _split_blocks(markdown)
    grouped = _group_blocks(blocks, max_chars=max_chars)
    chunks: list[Chunk] = []
    heading_path: list[str] = []

    for index, block in enumerate(grouped, start=1):
        first_line = block.splitlines()[0] if block.splitlines() else ""
        heading = _parse_heading(first_line)
        if heading:
            level, title = heading
            heading_path = heading_path[: level - 1] + [title]

        chunks.append(
            Chunk.create(
                document_id=document_id,
                chunk_id=f"chunk-{index:04d}",
                order=index,
                chunk_type=_classify_block(block),
                heading_path=heading_path,
                source_text=block.strip() + "\n",
            )
        )

    return chunks


def _split_blocks(markdown: str) -> list[str]:
    normalized = normalize_markdown(markdown)
    return [block.strip() for block in re.split(r"\n{2,}", normalized) if block.strip()]


def _group_blocks(blocks: list[str], *, max_chars: int) -> list[str]:
    grouped: list[str] = []
    current: list[str] = []

    for block in blocks:
        candidate = "\n\n".join([*current, block]) if current else block
        if current and len(candidate) > max_chars:
            grouped.append("\n\n".join(current))
            current = [block]
            continue
        current.append(block)

    if current:
        grouped.append("\n\n".join(current))

    return grouped


def _classify_block(block: str) -> ChunkType:
    lines = block.splitlines()
    first = lines[0].strip() if lines else ""
    if _parse_heading(first):
        return ChunkType.MIXED_SECTION if len(lines) > 1 else ChunkType.HEADING
    if all(line.startswith(("- ", "* ", "+ ")) for line in lines if line.strip()):
        return ChunkType.LIST
    if all(line.startswith(">") for line in lines if line.strip()):
        return ChunkType.BLOCKQUOTE
    if first.startswith("```"):
        return ChunkType.CODE_BLOCK
    if "|" in first:
        return ChunkType.TABLE
    return ChunkType.PARAGRAPH


def _parse_heading(line: str) -> tuple[int, str] | None:
    match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
    if match is None:
        return None
    return len(match.group(1)), match.group(2).strip()


def _collapse_blank_lines(markdown: str) -> str:
    lines = markdown.splitlines()
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = blank
    return "\n".join(collapsed)
