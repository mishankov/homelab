"""Check the upstream include boundary without containers or real credentials."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = """services:
  openalbert:
    image: ${OPENALBERT_IMAGE_PREFIX}/openalbert:${OPENALBERT_IMAGE_TAG}
    environment:
      LLM_MODEL: ${LLM_MODEL}
      LLM_API_KEY: ${LLM_API_KEY:?required}
    ports: ['127.0.0.1:8080:8080']
    volumes: ['./container_data/knowledge:/data/knowledge']
  stt:
    image: ${OPENALBERT_IMAGE_PREFIX}/stt:${OPENALBERT_IMAGE_TAG}
    profiles: [local-stt]
"""


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="openalbert test ")
        self.addCleanup(self.temp.cleanup)
        self.checkout = Path(self.temp.name) / "checkout"
        shutil.copytree(ROOT, self.checkout / "openalbert", ignore=shutil.ignore_patterns(
            "__pycache__", "tests"
        ))
        self.state = Path(self.temp.name) / "private installation"
        self.state.mkdir()
        (self.state / "compose.yaml").write_text(UPSTREAM)
        (self.state / ".env").write_text(
            "LLM_API_KEY=test-private-key\nLLM_MODEL=old-model\n"
            "OPENALBERT_IMAGE_TAG=installed-revision\n"
        )
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("COMPOSE_", "OPENALBERT_", "LLM_", "STT_"))}
        self.env["OPENALBERT_STATE_DIR"] = str(self.state)

    def compose(self, *args):
        return subprocess.run(
            ["docker", "compose", "--env-file", "openalbert/pi.env",
             "-f", "openalbert/compose.yml", *args],
            cwd=self.checkout, env=self.env, text=True, capture_output=True
        )

    def test_include_preserves_deployment_and_applies_pi_settings(self):
        result = self.compose("config", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["name"], "openalbert")
        app = config["services"]["openalbert"]
        self.assertTrue(app["image"].endswith(":installed-revision"))
        self.assertEqual(app["environment"]["LLM_API_KEY"], "test-private-key")
        self.assertEqual(app["environment"]["LLM_MODEL"], "deepseek-v4.1-flash")
        self.assertEqual(app["volumes"][0]["source"], str(self.state / "container_data/knowledge"))
        self.assertEqual(len(app["ports"]), 1)
        self.assertEqual(app["ports"][0]["host_ip"], "192.168.1.31")
        self.assertEqual(str(app["ports"][0]["published"]), "8080")
        self.assertIn("stt", config["services"])

    def test_all_profiles_includes_stt_even_when_disabled(self):
        self.env["COMPOSE_PROFILES"] = ""
        disabled = self.compose("config", "--services")
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertNotIn("stt", disabled.stdout.splitlines())
        result = self.compose("--profile", "*", "config", "--services")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stt", result.stdout.splitlines())

    def test_missing_private_settings_rejected(self):
        (self.state / ".env").unlink()
        self.assertNotEqual(self.compose("config", "-q").returncode, 0)


if __name__ == "__main__":
    unittest.main()
