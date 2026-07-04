import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "write_model_provenance.py"
SCRIPT_DIR = MODULE_PATH.parent


def load_write_model_provenance():
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        spec = importlib.util.spec_from_file_location("write_model_provenance_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class WriteModelProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.module = load_write_model_provenance()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name).resolve()
        self.original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)
        self.tmp.cleanup()

    def test_main_writes_model_provenance_file(self):
        os.environ["PAPER_REVIEW_CODEX_MODEL"] = "custom-model"
        artifact_root = self.tmp_path / "artifacts"
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["write_model_provenance.py", "--artifact-root", str(artifact_root)]):
            with redirect_stdout(output):
                status = self.module.main()

        self.assertEqual(status, 0)
        written = artifact_root / "model_provenance.json"
        self.assertEqual(output.getvalue().strip(), str(written))
        payload = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(payload["default_model"], "custom-model")
        self.assertEqual(payload["ai_interface"], "codex exec")
        self.assertIn("review.final", payload["thinking_levels"])

