import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aks_data.config import load_project_env


class AksConfigTests(unittest.TestCase):
    def test_fallback_loads_key_without_overriding_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("AKS_API_KEY=from-file\nAKS_API_BASE_URL=https://example.test/api\n", encoding="utf-8")
            with patch.dict(os.environ, {"AKS_API_KEY": "from-environment"}, clear=True):
                with patch.dict("sys.modules", {"dotenv": None}):
                    load_project_env(path)
                self.assertEqual(os.environ["AKS_API_KEY"], "from-environment")
                self.assertEqual(os.environ["AKS_API_BASE_URL"], "https://example.test/api")


if __name__ == "__main__":
    unittest.main()
