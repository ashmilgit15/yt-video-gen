import os
import tempfile
import unittest
from datetime import datetime, timezone

from config import settings
from storage import LocalStorageBackend
from youtube_upload import build_upload_body


class LocalStorageBackendTests(unittest.TestCase):
    def test_persist_video_moves_file_into_storage_root(self):
        original_storage_dir = settings.storage_local_dir

        with tempfile.TemporaryDirectory() as temp_storage_dir:
            source_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            try:
                source_file.write(b"video-bytes")
                source_file.close()

                object.__setattr__(settings, "storage_local_dir", temp_storage_dir)
                backend = LocalStorageBackend()
                stored_file = backend.persist_video(
                    source_file.name,
                    "video-123",
                    "short.mp4",
                )

                resolved_path = backend.resolve_local_path(stored_file.key)
                self.assertEqual(stored_file.provider, "local")
                self.assertTrue(os.path.exists(resolved_path))
                self.assertFalse(os.path.exists(source_file.name))
                self.assertEqual(backend.materialize(stored_file.key), resolved_path)
            finally:
                object.__setattr__(settings, "storage_local_dir", original_storage_dir)
                if os.path.exists(source_file.name):
                    os.remove(source_file.name)


class UploadBodyTests(unittest.TestCase):
    def test_build_upload_body_keeps_immediate_privacy(self):
        body = build_upload_body(
            {
                "title": "Immediate upload",
                "description": "Description",
                "tags": ["shorts"],
                "category_id": "22",
                "privacy_status": "unlisted",
                "publish_at": None,
            }
        )

        self.assertEqual(body["status"]["privacyStatus"], "unlisted")
        self.assertNotIn("publishAt", body["status"])

    def test_build_upload_body_formats_scheduled_publish(self):
        body = build_upload_body(
            {
                "title": "Scheduled upload",
                "description": "Description",
                "tags": ["shorts"],
                "category_id": "22",
                "privacy_status": "public",
                "publish_at": datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            }
        )

        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], "2026-04-01T14:30:00Z")


if __name__ == "__main__":
    unittest.main()
