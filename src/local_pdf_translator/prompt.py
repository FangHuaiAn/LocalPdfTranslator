from __future__ import annotations

from .models import Chunk


PROMPT_VERSION = "prompt-v1"


def build_translation_messages(chunk: Chunk) -> list[dict[str, str]]:
    context = " > ".join(chunk.heading_path) if chunk.heading_path else "Document"
    return [
        {
            "role": "system",
            "content": (
                "You translate English Markdown into natural Traditional Chinese "
                "for Taiwan readers. Preserve Markdown structure, headings, lists, "
                "links, numbers, units, code spans, code blocks, and URLs. Do not "
                "summarize, omit, expand, explain, or add commentary. Output only "
                "the translated Markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Section path: {context}\n\n"
                "Translate this Markdown to Traditional Chinese:\n\n"
                f"{chunk.source_text}"
            ),
        },
    ]
