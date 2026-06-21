from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from epub_helpers import write_minimal_epub


class WorkspaceTests(unittest.TestCase):
    def test_create_job_workspace_copies_pdf_and_writes_metadata(self):
        from local_pdf_translator.models import JobStatus
        from local_pdf_translator.workspace import create_job_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_pdf = root / "source.pdf"
            source_pdf.write_bytes(b"%PDF-1.7\nsample")

            job = create_job_workspace(
                source_pdf=source_pdf,
                output_root=root / "output",
                job_id="job-test",
                model="llama3.1",
                translation_profile="Balanced",
            )

            self.assertEqual(job.status, JobStatus.CREATED)
            self.assertTrue((job.output_dir / "document.original.pdf").exists())
            self.assertTrue((job.output_dir / "chunks").is_dir())
            self.assertTrue((job.output_dir / "metadata.json").exists())
            self.assertTrue((job.output_dir / "report.md").exists())

            metadata = json.loads((job.output_dir / "metadata.json").read_text())
            self.assertEqual(metadata["job_id"], "job-test")
            self.assertEqual(metadata["source_path"], str(source_pdf))
            self.assertEqual(metadata["status"], "Created")

    def test_create_job_workspace_refuses_existing_directory_by_default(self):
        from local_pdf_translator.workspace import create_job_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_pdf = root / "source.pdf"
            source_pdf.write_bytes(b"%PDF-1.7\nsample")
            output_root = root / "output"

            create_job_workspace(source_pdf, output_root, job_id="job-test")

            with self.assertRaises(FileExistsError):
                create_job_workspace(source_pdf, output_root, job_id="job-test")

    def test_create_job_workspace_accepts_epub(self):
        from local_pdf_translator.workspace import create_job_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_epub = root / "source.epub"
            write_minimal_epub(source_epub)

            job = create_job_workspace(
                source_pdf=source_epub,
                output_root=root / "output",
                job_id="epub-job",
            )

            self.assertEqual(job.source_format.value, "epub")
            self.assertTrue((job.output_dir / "document.original.epub").exists())

    def test_create_job_workspace_rejects_unsupported_source_type(self):
        from local_pdf_translator.workspace import create_job_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_txt = root / "source.txt"
            source_txt.write_text("not supported")

            with self.assertRaises(ValueError):
                create_job_workspace(
                    source_pdf=source_txt,
                    output_root=root / "output",
                    job_id="txt-job",
                )


if __name__ == "__main__":
    unittest.main()
