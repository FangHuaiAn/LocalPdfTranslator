from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, Path
from xml.etree import ElementTree
from zipfile import ZipFile


@dataclass(slots=True)
class EpubManifest:
    package_path: PurePosixPath
    items: dict[str, str]
    spine: list[str]


def convert_epub_to_markdown(epub_path: Path) -> str:
    with ZipFile(epub_path) as archive:
        manifest = _read_manifest(archive)
        chapter_markdown: list[str] = []
        for item_id in manifest.spine:
            href = manifest.items.get(item_id)
            if href is None:
                continue
            chapter_path = manifest.package_path.parent / href
            chapter_xml = archive.read(chapter_path.as_posix()).decode("utf-8")
            chapter_markdown.append(_xhtml_to_markdown(chapter_xml))

    return _normalize_blank_lines("\n\n".join(chapter_markdown)).strip() + "\n"


def _read_manifest(archive: ZipFile) -> EpubManifest:
    container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
    rootfile = _first_by_local_name(container, "rootfile")
    if rootfile is None:
        raise ValueError("EPUB container does not declare a rootfile")

    package_path = PurePosixPath(rootfile.attrib["full-path"])
    package = ElementTree.fromstring(archive.read(package_path.as_posix()))

    items: dict[str, str] = {}
    spine: list[str] = []
    manifest = _first_by_local_name(package, "manifest")
    if manifest is not None:
        for item in _children_by_local_name(manifest, "item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            if item_id and href:
                items[item_id] = href

    spine_element = _first_by_local_name(package, "spine")
    if spine_element is not None:
        for itemref in _children_by_local_name(spine_element, "itemref"):
            idref = itemref.attrib.get("idref")
            if idref:
                spine.append(idref)

    return EpubManifest(package_path=package_path, items=items, spine=spine)


def _xhtml_to_markdown(xml_text: str) -> str:
    root = ElementTree.fromstring(xml_text)
    body = _first_by_local_name(root, "body")
    if body is None:
        body = root
    blocks: list[str] = []
    for child in list(body):
        block = _block_markdown(child)
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _block_markdown(element: ElementTree.Element) -> str:
    tag = _local_name(element.tag)
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag[1])
        return f"{'#' * level} {_inline_markdown(element).strip()}"
    if tag == "p":
        return _inline_markdown(element).strip()
    if tag in {"ul", "ol"}:
        ordered = tag == "ol"
        lines = []
        for index, child in enumerate(_children_by_local_name(element, "li"), start=1):
            marker = f"{index}. " if ordered else "- "
            lines.append(marker + _inline_markdown(child).strip())
        return "\n".join(lines)
    if tag == "blockquote":
        text = _inline_markdown(element).strip()
        return "\n".join(f"> {line}" for line in text.splitlines())
    return _inline_markdown(element).strip()


def _inline_markdown(element: ElementTree.Element) -> str:
    parts: list[str] = []
    if element.text:
        parts.append(element.text)

    for child in list(element):
        tag = _local_name(child.tag)
        if tag == "a":
            text = _inline_markdown(child).strip()
            href = child.attrib.get("href")
            parts.append(f"[{text}]({href})" if href else text)
        elif tag == "br":
            parts.append("\n")
        elif tag == "img":
            src = child.attrib.get("src", "")
            alt = child.attrib.get("alt", "")
            parts.append(f"![{alt}]({src})")
        elif tag == "code":
            parts.append(f"`{_inline_markdown(child).strip()}`")
        else:
            parts.append(_inline_markdown(child))

        if child.tail:
            parts.append(child.tail)

    return _collapse_inline_space("".join(parts))


def _first_by_local_name(
    element: ElementTree.Element,
    local_name: str,
) -> ElementTree.Element | None:
    for child in element.iter():
        if _local_name(child.tag) == local_name:
            return child
    return None


def _children_by_local_name(
    element: ElementTree.Element,
    local_name: str,
) -> list[ElementTree.Element]:
    return [child for child in list(element) if _local_name(child.tag) == local_name]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _collapse_inline_space(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _normalize_blank_lines(text: str) -> str:
    lines = text.splitlines()
    normalized: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                normalized.append("")
            blank = True
            continue
        normalized.append(line.rstrip())
        blank = False
    return "\n".join(normalized)
