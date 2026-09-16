import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.logging_config import configure_application_logging


class LoggingConfigTests(unittest.TestCase):
    def test_configure_application_logging_writes_file_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "backend.log"
            with patch("app.logging_config.settings") as mock_settings:
                mock_settings.log_file = str(log_file)
                mock_settings.log_to_console = False
                mock_settings.log_format = "json"
                mock_settings.log_level = "INFO"
                mock_settings.log_max_bytes = 1024 * 1024
                mock_settings.log_backup_count = 3
                configure_application_logging(force=True)
                logging.getLogger("test.logging_config").info("file-only-check")
                for handler in logging.getLogger().handlers:
                    handler.flush()
                self.assertTrue(log_file.exists())
                contents = log_file.read_text(encoding="utf-8")
                self.assertIn("file-only-check", contents)
                has_stream = any(
                    isinstance(handler, logging.StreamHandler)
                    and not isinstance(handler, logging.FileHandler)
                    for handler in logging.getLogger().handlers
                )
                self.assertFalse(has_stream)


if __name__ == "__main__":
    unittest.main()
