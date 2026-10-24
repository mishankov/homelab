"""Exercise deployment boundaries without starting containers or using real keys."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40
UPSTREAM = b"""name: upstream-name
services:
  openalbert:
    image: ${OPENALBERT_IMAGE_PREFIX}/openalbert:${OPENALBERT_IMAGE_TAG}
    environment:
      LLM_MODEL: ${LLM_MODEL}
      LLM_API_KEY: ${LLM_API_KEY:?required}
    ports:
      - '127.0.0.1:8080:8080'
    volumes:
      - ./container_data/knowledge:/data/knowledge
  stt:
    image: ${OPENALBERT_IMAGE_PREFIX}/stt:${OPENALBERT_IMAGE_TAG}
    profiles: [local-stt]
"""


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="openalbert test ")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.scripts = self.directory / "checkout" / "openalbert"
        shutil.copytree(ROOT, self.scripts, ignore=shutil.ignore_patterns(
            ".upstream", "__pycache__", "tests"
        ))
        self.state = self.directory / "private installation"
        self.state.mkdir()
        (self.state / ".env").write_text(
            "LLM_API_KEY=test-private-key\nLLM_MODEL=old-model\n"
            "OPENALBERT_IMAGE_TAG=old-tag\n"
        )
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("COMPOSE_", "OPENALBERT_", "LLM_", "STT_"))
        }
        self.env["OPENALBERT_STATE_DIR"] = str(self.state)
        spec = importlib.util.spec_from_file_location("sync_under_test", self.scripts / "sync.py")
        self.sync = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sync)

    def select_revision(self):
        responses = [json.dumps({"sha": REVISION}).encode(), UPSTREAM, b"LLM_API_KEY=\n"]
        with patch.object(self.sync, "download", side_effect=responses), patch("builtins.print"):
            self.sync.sync("master")

    def run_script(self, name, *arguments):
        return subprocess.run(
            [str(self.scripts / name), *arguments], cwd=self.directory,
            env=self.env, text=True, capture_output=True
        )

    def test_failed_sync_keeps_selected_revision_and_private_settings(self):
        self.select_revision()
        private_before = (self.state / ".env").read_bytes()
        with patch.object(self.sync, "download", side_effect=[
            json.dumps({"sha": "b" * 40}).encode(), UPSTREAM, URLError("interrupted")
        ]), self.assertRaises(URLError):
            self.sync.sync("master")
        self.assertEqual((self.sync.CACHE / "current").read_text(), REVISION + "\n")
        self.assertFalse((self.sync.CACHE / ("b" * 40)).exists())
        self.assertEqual((self.state / ".env").read_bytes(), private_before)

    def test_compose_preserves_project_data_secrets_and_replaces_port(self):
        self.select_revision()
        result = self.run_script("compose.sh", "config", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["name"], "openalbert")
        service = config["services"]["openalbert"]
        self.assertTrue(service["image"].endswith(":sha-" + REVISION))
        self.assertEqual(service["environment"]["LLM_API_KEY"], "test-private-key")
        self.assertEqual(service["environment"]["LLM_MODEL"], "deepseek-v4.1-flash")
        self.assertEqual(service["volumes"][0]["source"], str(self.state / "container_data/knowledge"))
        self.assertEqual(len(service["ports"]), 1)
        self.assertEqual(service["ports"][0]["host_ip"], "192.168.1.31")
        self.assertEqual(str(service["ports"][0]["published"]), "8080")
        self.assertIn("stt", config["services"])

    def test_missing_private_environment_refuses_to_run(self):
        self.select_revision()
        (self.state / ".env").unlink()
        result = self.run_script("compose.sh", "ps")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing", result.stderr)

    def test_pull_failure_prevents_up_and_stop_includes_disabled_profiles(self):
        self.select_revision()
        binaries = self.directory / "bin"
        binaries.mkdir()
        docker = binaries / "docker"
        docker.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$@" >> "$CALL_LOG"\n'
            'for arg do [ "$arg" != pull ] || exit 42; done\n'
        )
        docker.chmod(0o755)
        calls = self.directory / "calls"
        self.env.update(PATH=str(binaries) + os.pathsep + self.env["PATH"], CALL_LOG=str(calls))
        result = self.run_script("up.sh")
        self.assertEqual(result.returncode, 42)
        self.assertNotIn("up", calls.read_text().splitlines())
        calls.unlink()
        result = self.run_script("stop.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls.read_text().splitlines()[-3:], ["--profile", "*", "stop"])


if __name__ == "__main__":
    unittest.main()
