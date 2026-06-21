from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class MarkdownPipelineTests(unittest.TestCase):
    def test_chunk_markdown_packs_adjacent_blocks_until_budget(self):
        from local_pdf_translator.markdown_pipeline import chunk_markdown

        markdown = "\n\n".join(
            [
                "# Chapter",
                "Paragraph one has enough text.",
                "Paragraph two has enough text.",
                "Paragraph three has enough text.",
                "Paragraph four has enough text.",
            ]
        )

        chunks = chunk_markdown(markdown, document_id="doc", max_chars=90)

        self.assertEqual(len(chunks), 2)
        self.assertIn("# Chapter", chunks[0].source_text)
        self.assertIn("Paragraph one", chunks[0].source_text)
        self.assertIn("Paragraph two", chunks[0].source_text)
        self.assertIn("Paragraph three", chunks[1].source_text)
        self.assertIn("Paragraph four", chunks[1].source_text)

    def test_chunk_markdown_keeps_code_blocks_intact_even_when_large(self):
        from local_pdf_translator.markdown_pipeline import chunk_markdown

        code_block = "```python\n" + "\n".join(f"print({i})" for i in range(20)) + "\n```"
        markdown = "\n\n".join(["Intro paragraph.", code_block, "Closing paragraph."])

        chunks = chunk_markdown(markdown, document_id="doc", max_chars=80)

        code_chunks = [chunk for chunk in chunks if "```python" in chunk.source_text]
        self.assertEqual(len(code_chunks), 1)
        self.assertIn("print(19)", code_chunks[0].source_text)
        self.assertTrue(code_chunks[0].source_text.strip().endswith("```"))

    def test_chunk_markdown_packs_realistic_book_into_bounded_count(self):
        from local_pdf_translator.markdown_pipeline import chunk_markdown

        raw_path = Path("output/war-peace-war-zh/document.en.raw.md")
        if not raw_path.exists():
            self.skipTest("real EPUB smoke output is not present")

        chunks = chunk_markdown(
            raw_path.read_text(encoding="utf-8"),
            document_id="war-peace-war",
            max_chars=8000,
        )

        self.assertLess(len(chunks), 180)
        self.assertGreater(len(chunks), 80)
        self.assertTrue(all(chunk.source_text.strip() for chunk in chunks))
