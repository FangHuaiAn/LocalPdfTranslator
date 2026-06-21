from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class ModelTests(unittest.TestCase):
    def test_job_round_trips_through_json_dict(self):
        from local_pdf_translator.models import Job, JobStatus

        job = Job.create(
            job_id="job-test",
            source_pdf=Path("/input/report.pdf"),
            output_dir=Path("/output/job-test"),
            model="llama3.1",
            translation_profile="Balanced",
            prompt_version="prompt-v1",
        )
        restored = Job.from_dict(job.to_dict())

        self.assertEqual(restored.job_id, "job-test")
        self.assertEqual(restored.source_pdf, Path("/input/report.pdf"))
        self.assertEqual(restored.output_dir, Path("/output/job-test"))
        self.assertEqual(restored.status, JobStatus.CREATED)
        self.assertEqual(restored.model, "llama3.1")
        self.assertEqual(restored.translation_profile, "Balanced")
        self.assertEqual(restored.prompt_version, "prompt-v1")

    def test_chunk_records_source_hash_and_heading_path(self):
        from local_pdf_translator.models import Chunk, ChunkStatus, ChunkType

        chunk = Chunk.create(
            document_id="doc-1",
            chunk_id="chunk-0001",
            order=1,
            chunk_type=ChunkType.PARAGRAPH,
            heading_path=["Executive Summary"],
            source_text="A paragraph.",
        )

        self.assertEqual(chunk.status, ChunkStatus.PENDING)
        self.assertEqual(chunk.heading_path, ["Executive Summary"])
        self.assertEqual(
            Chunk.from_dict(chunk.to_dict()).source_hash,
            chunk.source_hash,
        )

    def test_qa_result_and_glossary_entry_are_serializable(self):
        from local_pdf_translator.models import GlossaryEntry, QAResult

        qa = QAResult(
            check_name="markdown_links",
            passed=True,
            warnings=["no links found"],
            errors=[],
        )
        glossary_entry = GlossaryEntry(
            english="deterrence",
            zh_tw="嚇阻",
            term_type="policy",
            force=True,
            note="Use Taiwan terminology.",
        )

        self.assertEqual(QAResult.from_dict(qa.to_dict()).warnings, ["no links found"])
        self.assertEqual(
            GlossaryEntry.from_dict(glossary_entry.to_dict()).zh_tw,
            "嚇阻",
        )

    def test_job_created_at_uses_timezone_aware_datetime(self):
        from local_pdf_translator.models import Job

        job = Job.create(
            job_id="job-test",
            source_pdf=Path("/input/report.pdf"),
            output_dir=Path("/output/job-test"),
        )

        self.assertIsInstance(job.created_at, datetime)
        self.assertEqual(job.created_at.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
