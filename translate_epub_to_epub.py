import sys
import shutil
import time
import zipfile
import re
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree
from bs4 import BeautifulSoup
import markdown

# Add project src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from local_pdf_translator.models import SourceFormat
from local_pdf_translator.markdown_pipeline import chunk_markdown
from local_pdf_translator.epub import _read_manifest, _xhtml_to_markdown
from local_pdf_translator.ollama import OllamaClient

def translate_text_simple(client, text, model="gemma3:4b"):
    """Helper to translate short text like titles using Ollama."""
    if not text.strip():
        return text
    messages = [
        {
            "role": "system",
            "content": (
                "You translate short book/chapter titles or metadata from English into natural Traditional Chinese "
                "for Taiwan readers. Output only the translated title, no commentary, no quotes, no markdown formatting."
            )
        },
        {
            "role": "user",
            "content": f"Translate this title: {text}"
        }
    ]
    try:
        translated = client.chat(model=model, messages=messages)
        return translated.strip().strip('"').strip("'")
    except Exception as e:
        print(f"[Warning] Failed to translate metadata '{text}': {e}")
        return text

def find_cached_translation(source_text, cache_dir):
    """Find translated text in the cached chunks folder by matching SHA256 source hash."""
    if not cache_dir.exists():
        return None
    source_hash = sha256(source_text.encode("utf-8")).hexdigest()
    
    # Check if there is an en.md file in the cache directory with this hash or content
    for en_path in cache_dir.glob("*.en.md"):
        try:
            cached_en_text = en_path.read_text(encoding="utf-8")
            cached_hash = sha256(cached_en_text.encode("utf-8")).hexdigest()
            if cached_hash == source_hash or cached_en_text.strip() == source_text.strip():
                # Matching chunk found! Get corresponding zh-TW.md file
                zh_path = en_path.with_name(en_path.name.replace(".en.md", ".zh-TW.md"))
                if zh_path.exists():
                    return zh_path.read_text(encoding="utf-8")
        except Exception as e:
            continue
    return None

def translate_epub_to_epub(epub_path, output_dir, model="gemma3:4b", ollama_host="http://localhost:11434"):
    epub_path = Path(epub_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    unpacked_dir = output_dir / "unpacked"
    if unpacked_dir.exists():
        shutil.rmtree(unpacked_dir)
    unpacked_dir.mkdir(parents=True)
    
    # 1. Unpack EPUB
    print(f"Unpacking {epub_path.name} to {unpacked_dir}...")
    with zipfile.ZipFile(epub_path, 'r') as zip_ref:
        zip_ref.extractall(unpacked_dir)
        
    client = OllamaClient(ollama_host)
    
    # Find cache directory from the previous translation run (if any)
    cache_dir = output_dir / "chunks"
    print(f"Using cache directory for translated chunks: {cache_dir}")
    
    # 2. Parse container.xml to locate OPF file
    container_xml_path = unpacked_dir / "META-INF" / "container.xml"
    if not container_xml_path.exists():
        raise FileNotFoundError("META-INF/container.xml not found")
        
    container_tree = ElementTree.parse(container_xml_path)
    rootfile = None
    for elem in container_tree.iter():
        if elem.tag.endswith("rootfile"):
            rootfile = elem
            break
    if rootfile is None:
        raise ValueError("EPUB container.xml does not declare a rootfile")
        
    opf_rel_path = rootfile.attrib["full-path"]
    opf_path = unpacked_dir / opf_rel_path
    print(f"Found OPF file: {opf_path.relative_to(unpacked_dir)}")
    
    # 3. Read OPF manifest and spine using epub.py helper
    # We open the archive again to run the helper, or simulate it.
    with zipfile.ZipFile(epub_path) as archive:
        manifest = _read_manifest(archive)
        
    # 4. Translate Metadata in OPF
    print("Translating book metadata in OPF...")
    opf_content = opf_path.read_text(encoding="utf-8")
    opf_soup = BeautifulSoup(opf_content, "xml")
    
    title_tag = opf_soup.find("title") or opf_soup.find("dc:title")
    if title_tag and title_tag.string:
        orig_title = title_tag.string
        zh_title = translate_text_simple(client, orig_title, model)
        print(f"Translated Title: '{orig_title}' -> '{zh_title}'")
        title_tag.string = zh_title
        
    desc_tag = opf_soup.find("description") or opf_soup.find("dc:description")
    if desc_tag and desc_tag.string:
        orig_desc = desc_tag.string
        zh_desc = translate_text_simple(client, orig_desc, model)
        desc_tag.string = zh_desc
        
    lang_tag = opf_soup.find("language") or opf_soup.find("dc:language")
    if lang_tag:
        lang_tag.string = "zh-TW"
        
    # Save modified OPF back
    opf_path.write_bytes(str(opf_soup).encode("utf-8"))
    
    # 5. Translate chapters in Spine
    total_chapters = len(manifest.spine)
    print(f"Translating {total_chapters} chapters listed in spine...")
    
    stats_translated_chars = 0
    stats_cached_chars = 0
    stats_total_seconds = 0.0
    
    for idx, item_id in enumerate(manifest.spine, start=1):
        href = manifest.items.get(item_id)
        if href is None:
            continue
        chapter_rel_path = manifest.package_path.parent / href
        chapter_path = unpacked_dir / chapter_rel_path
        
        if not chapter_path.exists():
            print(f"[Warning] Chapter file does not exist: {chapter_path}")
            continue
            
        print(f"[{idx}/{total_chapters}] Processing chapter {href}...")
        chapter_xml = chapter_path.read_text(encoding="utf-8")
        
        # Convert XHTML body to markdown
        chapter_md = _xhtml_to_markdown(chapter_xml)
        if not chapter_md.strip():
            print(f" -> Chapter is empty. Skipping.")
            continue
            
        # Chunk the markdown
        chunks = chunk_markdown(chapter_md, document_id="epub-rebuild", max_chars=2500)
        
        translated_chunks_md = []
        for chunk_idx, chunk in enumerate(chunks, start=1):
            source_text = chunk.source_text
            char_count = len(source_text)
            
            # Check cache
            cached_zh_text = find_cached_translation(source_text, cache_dir)
            if cached_zh_text is not None:
                translated_chunks_md.append(cached_zh_text.strip())
                stats_cached_chars += char_count
            else:
                # Cache miss: translate via Ollama
                print(f"    (Cache Miss) Chunk {chunk_idx}/{len(chunks)} ({char_count} chars). Translating...")
                start_time = time.time()
                translated = client.chat(
                    model=model,
                    messages=[
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
                            "content": f"Translate this Markdown to Traditional Chinese:\n\n{source_text}"
                        }
                    ],
                    temperature=0.1,
                    top_p=0.9
                )
                duration = time.time() - start_time
                translated_chunks_md.append(translated.strip())
                stats_translated_chars += char_count
                stats_total_seconds += duration
                
        # Merge translated chunks
        zh_chapter_md = "\n\n".join(translated_chunks_md)
        
        # Convert translated Markdown to HTML body contents
        zh_chapter_html_body = markdown.markdown(zh_chapter_md)
        
        # Inject back into original XML body
        soup = BeautifulSoup(chapter_xml, "xml")
        body_tag = soup.find("body")
        if body_tag:
            body_tag.clear()
            # Wrap the raw HTML in a parsed BeautifulSoup structure
            html_soup = BeautifulSoup(zh_chapter_html_body, "xml")
            for node in html_soup.contents:
                body_tag.append(node)
                
        # Save translated chapter file back
        chapter_path.write_bytes(str(soup).encode("utf-8"))
        
    # 6. Translate Table of Contents (NCX if exists)
    for ncx_path in unpacked_dir.rglob("*.ncx"):
        print(f"Translating NCX TOC: {ncx_path.relative_to(unpacked_dir)}...")
        ncx_content = ncx_path.read_text(encoding="utf-8")
        ncx_soup = BeautifulSoup(ncx_content, "xml")
        for text_tag in ncx_soup.find_all("text"):
            if text_tag.string:
                orig_text = text_tag.string
                zh_text = translate_text_simple(client, orig_text, model)
                text_tag.string = zh_text
        ncx_path.write_bytes(str(ncx_soup).encode("utf-8"))
        
    # 7. Pack EPUB (Ensure mimetype is first and uncompressed)
    final_epub_path = output_dir / f"{epub_path.stem}.zh-TW.epub"
    print(f"Packaging files into EPUB: {final_epub_path}...")
    
    with zipfile.ZipFile(final_epub_path, 'w', zipfile.ZIP_DEFLATED) as epub:
        # Write mimetype first, uncompressed
        mimetype_path = unpacked_dir / "mimetype"
        if mimetype_path.exists():
            epub.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)
            
        # Recursively write other files
        for file_path in unpacked_dir.rglob("*"):
            if file_path.is_file() and file_path.name != "mimetype":
                arcname = file_path.relative_to(unpacked_dir)
                epub.write(file_path, arcname)
                
    # Clean up unpacked folder
    shutil.rmtree(unpacked_dir)
    
    print("\n" + "=" * 50)
    print("EPUB-to-EPUB Translation Completed successfully!")
    print(f"Output File: {final_epub_path}")
    print(f"Translated characters (Cache Miss): {stats_translated_chars}")
    print(f"Cached characters (Cache Hit): {stats_cached_chars}")
    print(f"Translation duration: {stats_total_seconds:.2f} seconds")
    if stats_translated_chars > 0:
        avg_speed = (stats_total_seconds / stats_translated_chars) * 1000
        print(f"Average translation speed: {avg_speed:.2f} s per 1k characters")
    print("=" * 50)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        # Defaults to targets files
        epub_source = r"C:\Projects\LocalPdfTranslator\targets\War and Peace and War\War and Peace and War.epub"
        output_workspace = r"C:\Projects\LocalPdfTranslator\output\War and Peace and War"
    else:
        epub_source = sys.argv[1]
        output_workspace = sys.argv[2]
        
    translate_epub_to_epub(epub_source, output_workspace)
