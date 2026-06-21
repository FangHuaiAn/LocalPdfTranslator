from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class PdfAdapterTests(unittest.TestCase):
    def test_pdf_converter_uses_markitdown_when_available(self):
        from local_pdf_translator.pdf import convert_pdf_to_markdown

        class FakeResult:
            text_content = "# PDF Title\n\nHello from PDF."

        class FakeMarkItDown:
            def convert(self, path):
                self.path = path
                return FakeResult()

        fake_module = types.SimpleNamespace(MarkItDown=FakeMarkItDown)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            sys.modules,
            {"markitdown": fake_module},
        ):
            pdf_path = Path(tmp) / "source.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\nsample")

            markdown = convert_pdf_to_markdown(pdf_path)

        self.assertEqual(markdown, "# PDF Title\n\nHello from PDF.\n")

    def test_pdf_converter_explains_missing_markitdown_dependency(self):
        from local_pdf_translator.pdf import convert_pdf_to_markdown

        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {"markitdown": None}):
            pdf_path = Path(tmp) / "source.pdf"
            pdf_path.write_bytes(b"%PDF-1.7\nsample")

            with self.assertRaises(RuntimeError) as context:
                convert_pdf_to_markdown(pdf_path)

        self.assertIn("markitdown", str(context.exception))

    def test_translate_command_creates_raw_markdown_for_pdf(self):
        from local_pdf_translator.cli import main

        with tempfile.TemporaryDirectory() as tmp, patch(
            "local_pdf_translator.cli.convert_pdf_to_markdown",
            return_value="# PDF Title\n\nHello from PDF.\n",
        ):
            root = Path(tmp)
            pdf_path = root / "sample.pdf"
            output_root = root / "output"
            pdf_path.write_bytes(b"%PDF-1.7\nsample")

            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "translate",
                        str(pdf_path),
                        "--output-dir",
                        str(output_root),
                        "--job-id",
                        "pdf-job",
                    ]
                )

            job_dir = output_root / "pdf-job"
            metadata = json.loads((job_dir / "metadata.json").read_text())

            self.assertEqual(result, 0)
            self.assertEqual(
                (job_dir / "document.en.raw.md").read_text(),
                "# PDF Title\n\nHello from PDF.\n",
            )
            self.assertEqual(metadata["source_format"], "pdf")
            self.assertEqual(metadata["status"], "Converted")
