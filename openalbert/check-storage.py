#!/usr/bin/env python3
"""Check real MinIO installation and cold restart using disposable storage."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parent
project = "homelab-storage-check-" + uuid.uuid4().hex[:12]
env = {key: value for key, value in os.environ.items() if key in {
    "PATH", "HOME", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
    "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
}}
env.update(POSTGRES_PASSWORD="test-only-password", S3_ACCESS_KEY="test-access",
           S3_SECRET_KEY="test-only-secret", TELEGRAM_BOT_TOKEN="test-only-token",
           TELEGRAM_ALLOWED_USER_IDS="123", LLM_API_KEY="test-only-key")


def run(*args, timeout=180):
    return subprocess.check_output(args, text=True, env=env, stderr=subprocess.STDOUT,
                                   timeout=timeout).strip()


base = ["docker", "compose", "--env-file", str(ROOT / ".env.example"),
        "--env-file", str(ROOT / "pi.env"), "-f", str(ROOT / "compose.yaml")]
normal = json.loads(run(*base, "config", "--format", "json"))["services"]
assert "minio-init" not in normal, "Normal startup must not include initialization"
services = json.loads(run(*base, "--profile", "*", "config", "--format", "json"))["services"]
dependency = services["openalbert"]["depends_on"]
assert "minio-init" not in dependency, "Albert must not require an init container"
assert dependency["minio"]["condition"] == "service_healthy"
minio, init = services["minio"], services["minio-init"]
minio.pop("ports", None)
minio["volumes"] = [{"type": "volume", "source": "storage", "target": "/data"}]
for service in (minio, init):
    service["logging"] = {"driver": "local"}
    service["pull_policy"] = "never"
# A probe uses Albert's actual MinIO dependency without requiring Telegram/LLM/DB.
probe = {
    "image": init["image"], "pull_policy": "never",
    "entrypoint": ["/bin/sh", "-ec"],
    "command": ["exec tail -f /dev/null"],
    "depends_on": {"minio": dependency["minio"]},
    "healthcheck": {"test": ["CMD", "wget", "-q", "-O", "/dev/null",
                                "http://minio:9000/minio/health/ready"],
                    "interval": "1s", "timeout": "3s", "retries": 30},
}
config = {"name": project, "services": {"minio": minio, "minio-init": init,
                                          "probe": probe}, "volumes": {"storage": {}}}
mc_alias = 'mc alias set local http://minio:9000 "$S3_ACCESS_KEY" "$S3_SECRET_KEY" >/dev/null; '

with tempfile.TemporaryDirectory(prefix=project) as directory:
    path = Path(directory)
    (path / "compose.yaml").write_text(json.dumps(config))
    (path / ".env").write_text("")
    (path / "pi.env").write_text("")
    shutil.copyfile(ROOT / "install-storage.sh", path / "install-storage.sh")
    compose = ["docker", "compose", "-f", str(path / "compose.yaml")]

    def mc(command):
        return run(*compose, "run", "--rm", "--no-deps", "--entrypoint", "/bin/sh",
                   "minio-init", "-ec", mc_alias + command)

    def require_object():
        assert "retained-storage-check" in mc('mc cat "local/$S3_BUCKET/check-marker"')
        assert not run(*compose, "--profile", "*", "ps", "--all", "--quiet", "minio-init"), \
            "Installation must leave no init container"

    try:
        run("/bin/sh", str(path / "install-storage.sh"))
        mc('printf retained-storage-check | mc pipe "local/$S3_BUCKET/check-marker"')
        run("/bin/sh", str(path / "install-storage.sh"))
        require_object()
        print("Explicit installation and repeated initialization preserve objects: OK", flush=True)
        run(*compose, "up", "-d", "--wait", "--wait-timeout", "90")
        require_object()
        # Match the backup controller's stop/start cycle; no init container exists.
        run(*compose, "stop", "probe", "minio")
        run(*compose, "start", "--wait", "--wait-timeout", "90", "probe", "minio")
        require_object()
        print("Normal startup and cold restart without an init container: OK", flush=True)
        run(*compose, "up", "-d", "--force-recreate", "--wait", "--wait-timeout", "90")
        require_object()
        print("Container recreation preserves the bucket and object: OK", flush=True)
    except BaseException as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(error.output)
        print(run(*compose, "logs", "--tail", "30"))
        raise
    finally:
        run(*compose, "--profile", "*", "down", "--volumes", "--remove-orphans")
        print("Disposable containers, network and storage removed", flush=True)
