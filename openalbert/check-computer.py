#!/usr/bin/env python3
"""Build and check the computer using disposable containers and synthetic keys."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parent
project = "homelab-computer-check-" + uuid.uuid4().hex[:12]
image = "homelab-openalbert-computer:check-" + uuid.uuid4().hex[:12]
env = {key: value for key, value in os.environ.items() if key in {
    "PATH", "HOME", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
    "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
}}
env.update(POSTGRES_PASSWORD="test-only-password", S3_ACCESS_KEY="test-access",
           S3_SECRET_KEY="test-only-secret", TELEGRAM_BOT_TOKEN="test-only-token",
           TELEGRAM_ALLOWED_USER_IDS="123", LLM_API_KEY="test-only-key")


def run(*args, timeout=120):
    return subprocess.check_output(args, text=True, env=env, stderr=subprocess.STDOUT,
                                   timeout=timeout).strip()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


base = ["docker", "compose", "--project-name", project,
        "--env-file", str(ROOT / ".env.example"),
        "--env-file", str(ROOT / "pi.env"), "-f", str(ROOT / "compose.yaml")]
config = json.loads(run(*base, "config", "--format", "json"))
services = config["services"]
computer, app = services["computer"], services["openalbert"]
require(not computer.get("ports"), "Computer SSH must not be published")
require(set(computer["networks"]) == {"computer"}, "Unexpected computer network")
require(set(app["networks"]) == {"computer", "default"}, "Albert needs both networks")
require(app["environment"]["COMPUTER_SSH_ADDRESS"] == "computer:22", "Wrong SSH address")
require(app["environment"]["COMPUTER_SSH_KEY_FILE"] == "/data/computer/id_ed25519",
        "Wrong client key path")
require(not app["environment"]["COMPUTER_SSH_PASSWORD"], "Key auth must not use a password")
require("COMPUTER_SSH_KNOWN_HOSTS_FILE" not in app["environment"], "Legacy SSH setting")
require("backup" not in services, "Unverified backup profile must not start by default")
require("computer-init" not in services, "SSH preparation must remain a manual installation step")
require(app["ports"][0]["host_ip"] == "192.168.1.31", "Wrong inspector binding")
require(services["postgres"]["ports"][0]["published"] == "15432", "Wrong PostgreSQL port")
all_profiles = json.loads(run(*base, "--profile", "*", "config", "--format", "json"))
for component in ("openalbert", "backup", "stt", "log-gateway", "minio", "minio-init"):
    require(all_profiles["services"][component]["image"] ==
            "ghcr.io/mishankov/openalbert/" + component + ":master",
            "Published Albert images must use master")
print("Compose configuration and all profiles: OK", flush=True)

# Reuse the real service definitions, replacing only their data with named test
# volumes and their image/network names. Never mount real container_data or .env.
test_services = {"computer": computer}
for service in test_services.values():
    service["image"] = image
    for volume in service["volumes"]:
        name = Path(volume["source"]).name
        require(name in {"client", "server", "home", "workspace"}, "Unexpected data mount")
        volume.clear()
        target = {"server": "/etc/openalbert-ssh", "home": "/home/albert",
                  "workspace": "/workspace"}[name]
        volume.update(type="volume", source=name, target=target)
        if service is computer and name == "server":
            volume["read_only"] = True
test = {"services": test_services,
        "networks": {"computer": {"name": project + "_computer"}},
        "volumes": {name: {} for name in ("client", "server", "home", "workspace")}}


def ssh(command):
    return run("docker", "run", "--rm", "--network", project + "_computer",
               "--user", "10001:10001", "--mount",
               "type=volume,src=" + project + "_client,dst=/keys,readonly",
               "--entrypoint", "ssh", image, "-i", "/keys/id_ed25519",
               "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
               "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
               "albert@computer", command)


def key_hashes(compose):
    client = run("docker", "run", "--rm", "--network", "none", "--mount",
                 "type=volume,src=" + project + "_client,dst=/keys,readonly",
                 "--entrypoint", "sha256sum", image, "/keys/id_ed25519")
    server = run(*compose, "exec", "-T", "computer", "sha256sum",
                 "/etc/openalbert-ssh/ssh_host_ed25519_key", "/etc/openalbert-ssh/authorized_keys")
    return hashlib.sha256((client + server).encode()).hexdigest()


with tempfile.TemporaryDirectory(prefix=project) as directory:
    path = Path(directory) / "compose.json"
    path.write_text(json.dumps(test))
    compose = ["docker", "compose", "--project-name", project, "-f", str(path)]
    try:
        run(*compose, "build", "computer", timeout=600)
        # Run the real installer with synthetic data, without a Compose init service.
        mounts = []
        data_dir = "/repo/openalbert/container_data/computer"
        for name in ("client", "server", "home", "workspace"):
            run("docker", "volume", "create", "--label", "com.docker.compose.project=" + project,
                "--label", "com.docker.compose.volume=" + name, project + "_" + name)
            mounts += ["--mount", "type=volume,src=" + project + "_" + name + ",dst=" + data_dir + "/" + name]
        setup = ["docker", "run", "--rm", "--network", "none", "--user", "0:0", *mounts,
                 "--mount", "type=bind,src=" + str(ROOT / "installer") + ",dst=/repo/openalbert/installer,readonly",
                 "--mount", "type=bind,src=" + str(ROOT / "install.sh") + ",dst=/repo/openalbert/install.sh,readonly",
                 "--entrypoint", "/bin/sh", image]
        run(*setup, "/repo/openalbert/install.sh")
        stat_command = ("stat -c '%u:%g:%a' " + " ".join(data_dir + "/" + path for path in (
            "client", "client/id_ed25519", "server", "server/ssh_host_ed25519_key",
            "server/authorized_keys", "home", "workspace")))
        permissions = run(*setup, "-c", stat_command)
        require(permissions.splitlines() == ["10001:10001:700", "10001:10001:600", "0:0:755",
                                            "0:0:600", "0:0:644", "10001:10001:755", "10001:10001:755"],
                "Installer set unexpected ownership or permissions")
        run(*compose, "up", "-d", "--no-build", "--wait", "--wait-timeout", "90", "computer")
        ssh(". /etc/os-release && test \"$VERSION_ID\" = 26.10 && "
            "test \"$(id -u)\" = 10001 && sudo -n true && "
            "python3 -c 'import sys; assert sys.version_info >= (3, 9)'")
        ssh("printf retained-home > /home/albert/check-home; "
            "printf retained-workspace > /workspace/check-workspace; "
            "mkdir -p /home/albert/.openalbert/workspace; "
            "printf retained-runner > /home/albert/.openalbert/workspace/check-runner")
        run(*setup, "-c", "printf '\\n# Preserve existing authorized_keys entries\\n' "
                         ">> " + data_dir + "/server/authorized_keys")
        before = key_hashes(compose)
        print("Ubuntu 26.10, SSH, Python and passwordless sudo: OK", flush=True)
        run(*setup, "-c", "chmod 0644 " + data_dir + "/client/id_ed25519 " +
                         data_dir + "/server/ssh_host_ed25519_key; chown 0:0 " +
                         data_dir + "/client/id_ed25519")
        run(*setup, "/repo/openalbert/install.sh")
        require(run(*setup, "-c", stat_command) == permissions, "Installer did not repair key permissions")
        require(key_hashes(compose) == before, "Repeated installation changed SSH keys or authorized_keys")
        print("Repeated installation repairs permissions and preserves keys and authorized_keys: OK", flush=True)
        run(*compose, "up", "-d", "--no-build", "--no-deps", "--force-recreate",
            "--wait", "--wait-timeout", "90", "computer")
        require(ssh("cat /home/albert/check-home") == "retained-home", "Lost home file")
        require(ssh("cat /workspace/check-workspace") == "retained-workspace", "Lost workspace file")
        require(ssh("cat /home/albert/.openalbert/workspace/check-runner") == "retained-runner",
                "Lost runner workspace file")
        require(key_hashes(compose) == before, "Recreation changed SSH identity")
        print("Installed SSH keys and data persist after recreation: OK", flush=True)
    except BaseException as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(error.output)
        print(run(*compose, "logs", "--tail", "40"))
        raise
    finally:
        run(*compose, "down", "--volumes", "--remove-orphans")
        run("docker", "image", "rm", image)
        print("Disposable containers, network, volumes and image removed", flush=True)
