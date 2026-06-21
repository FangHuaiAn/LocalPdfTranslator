from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from epub_helpers import write_minimal_epub


class EpubTests(unittest.TestCase):
    def test_epub_converter_uses_spine_order_and_basic_markdown(self):
        from local_pdf_translator.epub import convert_epub_to_markdown

        with tempfile.TemporaryDirectory() as tmp:
            epub_path = Path(tmp) / "sample.epub"
            write_minimal_epub(epub_path)

            markdown = convert_epub_to_markdown(epub_path)

        self.assertLess(markdown.index("# First Chapter"), markdown.index("## Second Chapter"))
        self.assertIn("Hello world.", markdown)
        self.assertIn("- First item", markdown)
        self.assertIn("- Second item", markdown)
        self.assertIn("Read the [notes](notes.xhtml).", markdown)

    def test_translate_command_creates_raw_markdown_for_epub(self):
        from local_pdf_translator.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epub_path = root / "sample.epub"
            output_root = root / "output"
            write_minimal_epub(epub_path)

            output = StringIO()
            with redirect_stdout(output):
                result = main(
                    [
                        "translate",
                        str(epub_path),
                        "--output-dir",
                        str(output_root),
                        "--job-id",
                        "sample-job",
                    ]
                )

            raw_markdown = output_root / "sample-job" / "document.en.raw.md"
            metadata = json.loads(
                (output_root / "sample-job" / "metadata.json").read_text()
            )
            raw_text = raw_markdown.read_text()

            self.assertEqual(result, 0)
            self.assertTrue(raw_markdown.exists())
            self.assertIn("# First Chapter", raw_text)
            self.assertEqual(metadata["source_path"], str(epub_path))
            self.assertEqual(metadata["source_format"], "epub")
            self.assertEqual(metadata["status"], "Converted")
