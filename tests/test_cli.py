from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class CliTests(unittest.TestCase):
    def test_parser_exposes_core_commands(self):
        from local_pdf_translator.cli import build_parser

        parser = build_parser()
        help_text = parser.format_help()

        self.assertIn("translate", help_text)
        self.assertIn("resume", help_text)
        self.assertIn("inspect", help_text)
        self.assertIn("models", help_text)

    def test_main_without_command_prints_help(self):
        from local_pdf_translator.cli import main

        output = StringIO()
        with redirect_stdout(output):
            result = main([])

        self.assertEqual(result, 0)
        self.assertIn("translate", output.getvalue())


if __name__ == "__main__":
    unittest.main()
