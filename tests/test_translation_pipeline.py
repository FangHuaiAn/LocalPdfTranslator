from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from epub_helpers import write_minimal_epub


class FakeOllamaTransport:
    responses = [
        "# 第一章\n\n你好，世界。",
        "- 第一項\n- 第二項\n\n## 第二章\n\n閱讀[註釋](notes.xhtml)。",
    ]
    requests: list[dict] = []

    @classmethod
    def reset(cls):
        cls.requests = []

    @classmethod
    def urlopen(cls, request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        cls.requests.append({"url": request.full_url, "body": body, "timeout": timeout})
        index = min(len(cls.requests) - 1, len(cls.responses) - 1)
        payload = {"message": {"content": cls.responses[index]}}
        return FakeResponse(payload)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TranslationPipelineTests(unittest.TestCase):
    def test_translate_command_runs_epub_through_shared_markdown_pipeline(self):
        from local_pdf_translator.cli import main

        FakeOllamaTransport.reset()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "urllib.request.urlopen",
            side_effect=FakeOllamaTransport.urlopen,
        ):
            root = Path(tmp)
            epub_path = root / "sample.epub"
            output_root = root / "output"
            write_minimal_epub(epub_path)

            stdout = StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "translate",
                        str(epub_path),
                        "--output-dir",
                        str(output_root),
                        "--job-id",
                        "sample-job",
                        "--model",
                        "mock-model",
                        "--ollama-host",
                        "http://ollama.test",
                        "--chunk-max-chars",
                        "80",
                    ]
                )

            job_dir = output_root / "sample-job"
            metadata = json.loads((job_dir / "metadata.json").read_text())
            zh_text = (job_dir / "document.zh-TW.md").read_text()

            self.assertEqual(result, 0)
            self.assertIn("# 第一章", zh_text)
            self.assertIn("閱讀[註釋](notes.xhtml)。", zh_text)
            self.assertTrue((job_dir / "document.en.normalized.md").exists())
            self.assertTrue((job_dir / "chunks" / "chunk-0001.en.md").exists())
            self.assertTrue((job_dir / "chunks" / "chunk-0001.zh-TW.md").exists())
            self.assertEqual(metadata["status"], "Completed")
            self.assertEqual(metadata["total_chunks"], 2)
            self.assertEqual(metadata["completed_chunks"], 2)
            self.assertEqual(metadata["failed_chunks"], 0)
            self.assertEqual(len(FakeOllamaTransport.requests), 2)
            self.assertEqual(
                FakeOllamaTransport.requests[0]["url"],
                "http://ollama.test/api/chat",
            )
            self.assertFalse(FakeOllamaTransport.requests[0]["body"]["stream"])
            self.assertEqual(
                FakeOllamaTransport.requests[0]["body"]["model"],
                "mock-model",
            )

    def test_markdown_pipeline_reuses_completed_chunk_translation(self):
        from local_pdf_translator.models import Job
        from local_pdf_translator.pipeline import run_markdown_translation_pipeline

        FakeOllamaTransport.reset()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "urllib.request.urlopen",
            side_effect=FakeOllamaTransport.urlopen,
        ):
            root = Path(tmp)
            source = root / "source.epub"
            source.write_bytes(b"fake")
            output_dir = root / "job"
            output_dir.mkdir()
            (output_dir / "chunks").mkdir()
            (output_dir / "document.en.raw.md").write_text("# Title\n\nHello world.\n")
            existing = output_dir / "chunks" / "chunk-0001.zh-TW.md"
            existing.write_text("# 標題\n\n你好，世界。")
            job = Job.create(
                source_pdf=source,
                output_dir=output_dir,
                job_id="job",
                model="mock-model",
            )

            run_markdown_translation_pipeline(
                job,
                ollama_host="http://ollama.test",
                chunk_max_chars=80,
            )

            self.assertEqual(len(FakeOllamaTransport.requests), 0)
            self.assertEqual(
                (output_dir / "document.zh-TW.md").read_text(),
                "# 標題\n\n你好，世界。\n",
            )
