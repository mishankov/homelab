#!/usr/bin/env python3
"""Plan and apply routine Pi updates using published, immutable ARM64 images.

The workstation owns registry credentials and the source checkout. A temporary
SSH worker owns the deployment/backup locks and private installation data.
Only sanitized JSON crosses its stdout. No third-party Python packages required.
"""

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


VERSION = 1
ROUTINE = {"openalbert", "backup", "stt", "log-gateway"}
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
TERMINAL = {"idle", "completed", "failed"}


class Refused(Exception):
    """A public, credential-free explanation of a failed prerequisite."""


def require(condition, message):
    if not condition:
        raise Refused(message)


def now():
    return dt.datetime.now(dt.timezone.utc)


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_json(path):
    return json.loads(Path(path).read_text())


def command(args, *, timeout=120, input=None, stdin=None, stdout=None):
    """Never propagate stderr/CalledProcessError: it may contain credentials."""
    try:
        result = subprocess.run(args, input=input, stdin=stdin, stdout=stdout or subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        failure = Refused("Command timed out: " + Path(args[0]).name)
        failure.diagnostics = (error.stdout or b"") + (error.stderr or b"")
        raise failure from None
    except OSError:
        raise Refused("Cannot execute: " + Path(args[0]).name) from None
    if result.returncode:
        failure = Refused("Command failed: " + Path(args[0]).name + " (exit %d)" % result.returncode)
        failure.diagnostics = (result.stdout or b"") + result.stderr
        raise failure
    return result.stdout or b""


def json_command(args, **kwargs):
    return json.loads(command(args, **kwargs))


def source_guard(source, before, after, component):
    """Conservative structural guard, not a proof of semantic compatibility."""
    require(SHA.fullmatch(before or "") and SHA.fullmatch(after or ""),
            "Missing source revision for " + component)
    for revision in {before, after}:
        result = subprocess.run(["git", "-C", str(source), "cat-file", "-e",
                                 revision + "^{commit}"], capture_output=True)
        if result.returncode:
            command(["git", "-C", str(source), "fetch", "origin", revision])
    command(["git", "-C", str(source), "merge-base", "--is-ancestor", before, after])
    paths = command(["git", "-C", str(source), "diff", "--name-only", before, after]).decode().splitlines()
    risky = []
    for path in paths:
        if path.endswith("_test.go"):
            continue
        if (path.startswith("deploy/") or path in {".env.example", ".env.release.example"}
                or re.search(r"(^|/)(migrations?|schema)(/|\.)", path)
                or path.endswith(".sql")
                or path.startswith("apps/backend/internal/storage/")
                or path.startswith("services/backup/") and component == "backup"
                or path.startswith("services/minio/")):
            risky.append(path)
    return risky


def registry_image(repo):
    inspected = json_command(["docker", "buildx", "imagetools", "inspect", repo + ":master",
                              "--format", "{{json .}}"])
    manifest = inspected["manifest"]
    arm = inspected.get("image", {}).get("linux/arm64")
    arm_manifest = next((m for m in manifest.get("manifests", [])
                         if m.get("platform", {}).get("os") == "linux"
                         and m.get("platform", {}).get("architecture") == "arm64"), None)
    require(arm and arm_manifest, "No linux/arm64 image: " + repo)
    labels = arm.get("config", {}).get("Labels", {})
    revision = labels.get("org.opencontainers.image.revision", "")
    require(SHA.fullmatch(revision), "No OCI source revision: " + repo)
    require(DIGEST.fullmatch(manifest["digest"]) and DIGEST.fullmatch(arm_manifest["digest"]),
            "Invalid registry digest")
    raw = json_command(["docker", "buildx", "imagetools", "inspect",
                        repo + "@" + arm_manifest["digest"], "--raw"])
    return {"repo": repo, "digest": manifest["digest"], "arm_digest": arm_manifest["digest"],
            "config_digest": raw["config"]["digest"], "revision": revision,
            "source": labels.get("org.opencontainers.image.source", ""),
            "download_bytes": sum(layer["size"] for layer in raw["layers"])}


def image_matches(actual, target):
    refs = {target["repo"] + "@" + target[k] for k in ("digest", "arm_digest")}
    return (actual["platform"] == "linux/arm64"
            and actual["id"] in {target["digest"], target["arm_digest"], target["config_digest"]}
            and actual["revision"] == target["revision"]
            and actual.get("source") == target["source"]
            and bool(refs.intersection(actual["digests"])))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_json(url, *, data=None, headers=None, method=None, timeout=30):
    req = urllib.request.Request(url, data=canonical(data) if data is not None else None,
                                 headers=headers or {}, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise Refused("HTTP check failed (status %d)" % error.code) from None
    except (OSError, ValueError):
        raise Refused("HTTP check failed (connection or response)") from None


def llm_probe(env):
    require(env.get("OPENAI_AUTH_MODE", "api_key") == "api_key", "Only API-key LLM mode is supported")
    require(env.get("LLM_API_KEY"), "LLM API key is missing")
    url = env["LLM_BASE_URL"].rstrip("/")
    headers = {"Authorization": "Bearer " + env["LLM_API_KEY"],
               "Content-Type": "application/json", "User-Agent": "OpenAlbert/0.1"}
    if urllib.parse.urlparse(url).hostname == "opencode.ai" and "/inference/go/" in url:
        headers["x-opencode-session"] = "openalbert-update-" + uuid.uuid4().hex
    result = http_json(url + "/chat/completions", headers=headers,
                       data={"model": env["LLM_MODEL"], "messages": [
                           {"role": "user", "content": "Reply with OK."}], "max_tokens": 16}, timeout=60)
    require(bool(result.get("choices")), "LLM response has no choices")
    return {"status": 200}


def error_signatures(raw):
    signatures = []
    for line in raw.decode(errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            if re.search(r"(?i)\b(panic:|fatal:)", line):
                signatures.append(fingerprint(line))
            continue
        if str(record.get("level", "")).upper() not in {"ERROR", "FATAL"}:
            continue
        detail = {k: record[k] for k in ("msg", "error_code", "error_type", "http_status", "Error", "error") if k in record}
        for key in ("msg", "Error", "error"):
            if isinstance(detail.get(key), str):
                text = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27,}", "#", detail[key])
                pattern = r"\d+(?:\.\d+)?" if key == "msg" else r"\d+(?:\.\d+)?\s*(?:ms|seconds|sec|с)\b"
                detail[key] = re.sub(pattern, "#", text)
        signatures.append(fingerprint(detail))
    return signatures


class Worker:
    def __init__(self):
        self.run_dir = None
        self.deployment_lock = None
        self.backup_lock = None
        self.record = {}
        self.baseline = None

    def compose(self, extra=(), *, env_files=None):
        args = ["docker", "compose", "--project-name", "openalbert",
                "--project-directory", self.directory]
        for path in env_files or self.env_files:
            args += ["--env-file", path]
        for path in self.config_files:
            args += ["-f", path]
        return args + list(extra)

    def containers(self):
        ids = command(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=openalbert"]).decode().split()
        require(ids, "No openalbert containers")
        result = {}
        for container in json_command(["docker", "inspect"] + ids):
            service = container["Config"]["Labels"]["com.docker.compose.service"]
            require(service not in result, "Multiple containers for service: " + service)
            result[service] = container
        return result

    def image(self, ref):
        image = json_command(["docker", "image", "inspect", ref])[0]
        labels = image.get("Config", {}).get("Labels") or {}
        return {"id": image["Id"], "revision": labels.get("org.opencontainers.image.revision"),
                "source": labels.get("org.opencontainers.image.source"),
                "platform": image["Os"] + "/" + image["Architecture"],
                "digests": image.get("RepoDigests", [])}

    def discover(self, args):
        require(os.geteuid() == 0, "SSH worker requires sudo -n")
        containers = self.containers()
        require("openalbert" in containers and "computer" in containers and "backup" in containers,
                "Expected existing Pi application, computer and backup controller")
        labels = containers["openalbert"]["Config"]["Labels"]
        self.directory = labels["com.docker.compose.project.working_dir"]
        self.config_files = labels["com.docker.compose.project.config_files"].split(",")
        self.env_files = labels.get("com.docker.compose.project.environment_file", "").split(",")
        require(self.env_files == [str(Path(self.directory) / name) for name in (".env", "pi.env")],
                "Expected explicit .env followed by pi.env")
        for path in self.config_files + self.env_files:
            require(Path(path).is_absolute() and Path(path).is_file(), "Missing explicit configuration file")
        self.config = json_command(self.compose(["config", "--format", "json"]))
        hashes = dict(line.split() for line in command(self.compose(["config", "--hash", "*"])).decode().splitlines())
        require(self.config.get("name") == "openalbert", "Unexpected project name")
        services = self.config["services"]
        require("computer-init" not in services, "Legacy computer init requires manual deployment")
        require(services["computer"].get("pull_policy") == "never", "Computer must remain local")
        require(not services["computer"].get("ports"), "Computer SSH must not be published")
        for service in services:
            require(service in containers, "Configured service has no existing container: " + service)
        for service, container in containers.items():
            state = container["State"]
            if service not in services:
                require(state["Status"] == "exited" and state["ExitCode"] == 0,
                        "Unexpected inactive/failed container: " + service)
                continue
            require(state["Running"] and state.get("Health", {}).get("Status", "healthy") == "healthy",
                    "Service is not ready: " + service)
            require(container["Config"]["Labels"].get("com.docker.compose.config-hash") == hashes[service],
                    "Runtime configuration drift: " + service)
            require(container["Config"]["Labels"].get("com.docker.compose.project.config_files")
                    == ",".join(self.config_files), "Different Compose overrides: " + service)
        ports = services["openalbert"].get("ports", [])
        require(any(port.get("host_ip") == "192.168.1.31" and str(port.get("published")) == "8080"
                    and port["target"] == 8080 for port in ports), "Inspector LAN binding changed")
        for service, definition in services.items():
            if service == "openalbert":
                continue
            require(all(port.get("host_ip") == "127.0.0.1" for port in definition.get("ports", [])),
                    "Non-loopback service port: " + service)
        require(any(str(port.get("published")) == "15432" for port in services["postgres"].get("ports", [])),
                "PostgreSQL port changed")
        self.paths = {}
        expected_mounts = {"knowledge": ("openalbert", "/data/knowledge"),
                           "backup-state": ("backup", "/installation/container_data/backup-state"),
                           "backup-config": ("backup", "/etc/openalbert-backup"),
                           "client": ("openalbert", "/data/computer"),
                           "server": ("computer", "/etc/openalbert-ssh")}
        for name, (service, target) in expected_mounts.items():
            mounts = [mount for mount in services[service].get("volumes", []) if mount["target"] == target]
            require(len(mounts) == 1 and mounts[0]["type"] == "bind", "Unexpected data mount: " + name)
            self.paths[name] = Path(mounts[0]["source"])
        require(self.paths["knowledge"] == Path(self.directory) / "container_data/knowledge",
                "Knowledge path requires manual backup planning")
        self.backup_config = read_json(self.paths["backup-config"] / "config.json")
        require(self.backup_config.get("exclude_computer") is True, "exclude_computer must remain true")
        require(self.backup_config.get("enabled") is True, "Scheduled backups must be enabled")
        snapshots = {}
        for service, container in containers.items():
            image = self.image(container["Image"])
            snapshots[service] = {"id": container["Id"], "started": container["State"]["StartedAt"],
                                  "image": image, "restarts": container["RestartCount"],
                                  "running": container["State"]["Running"]}
        self.baseline = {"directory": self.directory, "config_files": self.config_files,
                         "env_files": self.env_files, "config_hash": fingerprint(self.config),
                         "lock_path": str(self.paths["backup-state"] / "update.lock"),
                         "files": {path: file_hash(path) for path in self.config_files + self.env_files},
                         "backup_policy_hash": fingerprint(self.backup_config), "containers": snapshots,
                         "backup_files": {str(path): file_hash(path) for path in self.paths["backup-config"].rglob("*") if path.is_file()},
                         "images": {s: definition["image"] for s, definition in services.items()},
                         "warnings": [] if json_command(["docker", "info", "--format", "{{json .MemoryLimit}}"])
                         else ["Host does not enforce Docker memory limits"]}
        self.check_backup()
        require(shutil.which("ssh") and shutil.which("tar"), "Host needs ssh and tar")
        require(shutil.disk_usage(self.directory).free >= 2 * 1024**3, "Less than 2 GiB free")
        return self.baseline

    def check_backup(self, *, deadline=False):
        state = read_json(self.paths["backup-state"] / "status.json")
        require(state.get("phase") in TERMINAL, "Cold backup is active or its state is unknown")
        require(not (self.paths["backup-state"] / "request.json").exists(), "A backup request is queued")
        success = state.get("last_success") or {}
        require(success.get("created_at") and dt.timedelta(0) <= now() - timestamp(success["created_at"]) <= dt.timedelta(hours=36),
                "No verified S3 backup in the last 36 hours")
        if deadline:
            require(timestamp(state["next_run_at"]) - now() > dt.timedelta(minutes=10),
                    "Backup deadline is within ten minutes; retry after the scheduled backup")
        return state

    def lock(self, path):
        descriptor = open(path, "a+")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            descriptor.close()
            raise Refused("Deployment or backup lock is held") from None
        return descriptor

    def save(self, phase, **fields):
        self.record.update(fields, phase=phase, updated_at=now().isoformat())
        write_json(self.run_dir / "status.json", self.record)

    def begin(self, args):
        plan = args["plan"]
        require(plan["baseline"] == self.discover({}), "Installation changed since the plan; create a new plan")
        root = Path(args["backup_root"])
        require(root.is_absolute(), "Rollback directory must be absolute")
        require(not any(path.is_symlink() for path in [root] + list(root.parents)), "Symlink in backup path")
        root = root.resolve()
        require(not root.is_relative_to(Path(self.directory).resolve().parent),
                "Rollback directory must be outside the installation checkout")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(root.stat().st_mode & 0o077 == 0, "Backup root must have mode 0700")
        self.deployment_lock = self.lock(self.baseline["lock_path"])
        require(plan["baseline"] == self.discover({}), "Installation changed while acquiring lock")
        self.run_dir = root / (now().strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
        self.run_dir.mkdir(mode=0o700)
        self.plan = plan
        self.record = {"version": VERSION, "deployment_started": False, "paused": [],
                       "backup_dir": str(self.run_dir)}
        write_json(self.run_dir / "plan.json", plan)
        # Keep complete private originals on the Pi, never in the workstation report.
        for index, path in enumerate(self.config_files + self.env_files):
            dest = self.run_dir / ("config-%02d-" % index + Path(path).name)
            shutil.copyfile(path, dest)
            os.chmod(dest, 0o600)
        shutil.copytree(self.paths["backup-config"], self.run_dir / "backup-config")
        os.chmod(self.run_dir / "backup-config", 0o700)
        for path in (self.run_dir / "backup-config").rglob("*"):
            os.chmod(path, 0o700 if path.is_dir() else 0o600)
        rollback = {}
        for service in plan["changed"]:
            tag = "homelab-rollback/" + service + ":" + self.run_dir.name.lower()
            command(["docker", "tag", self.baseline["containers"][service]["image"]["id"], tag])
            rollback[service] = {"image": tag}
        write_json(self.run_dir / "rollback-images.json", {"services": rollback})
        self.save("prepared")
        download = sum(plan["targets"][s]["download_bytes"] for s in plan["changed"])
        require(shutil.disk_usage(self.directory).free >= download * 2 + 2 * 1024**3,
                "Insufficient space for image download and extraction")
        self.checks = {"llm_before": llm_probe(self.app_env()), "s3_backup_before": self.remote_copies(),
                       "computer_before": self.computer_probe()}
        self.logs_before = {s: error_signatures(self.logs(s, "10m")) for s in plan["changed"]}
        return {"backup_dir": str(self.run_dir)}

    def app_env(self):
        container = self.containers()["openalbert"]
        env = dict(value.split("=", 1) for value in container["Config"]["Env"])
        expected = self.config["services"]["openalbert"]["environment"]
        require(all(env.get(key) == str(value) for key, value in expected.items()), "Application environment drift")
        return env

    def remote_copies(self):
        copies = json_command(["docker", "exec", self.containers()["backup"]["Id"],
                               "albert-backup", "list"], timeout=100)
        success = self.check_backup()["last_success"]["id"]
        require(any(item["id"] == success for item in copies), "Last successful backup is missing from S3")
        return {"count": len(copies), "last_success_id": success}

    def logs(self, service, since):
        container = self.containers()[service]
        result = subprocess.run(["docker", "logs", "--since", since, container["Id"]],
                                capture_output=True, timeout=30)
        require(result.returncode == 0, "Cannot inspect logs: " + service)
        return result.stdout + result.stderr

    def inventory(self):
        files, after = {}, ""
        while True:
            page = http_json("http://192.168.1.31:8080/api/inspect/files?" + urllib.parse.urlencode({"after": after}))
            for item in page["files"]:
                files[item["key"]] = item["size"]
            next_after = page.get("next_after", "")
            require(not next_after or next_after != after, "S3 pagination stalled")
            after = next_after
            if not after:
                return files

    def sql(self, query):
        return command(["docker", "exec", self.containers()["postgres"]["Id"], "psql", "-U", "openalbert",
                        "-d", "openalbert", "-At", "-v", "ON_ERROR_STOP=1", "-c", query]).decode().strip()

    def computer_probe(self):
        env = self.app_env()
        require(env.get("COMPUTER_SSH_ADDRESS") == "computer:22" and env.get("COMPUTER_SSH_USER") == "albert"
                and env.get("COMPUTER_SSH_KEY_FILE") == "/data/computer/id_ed25519" and not env.get("COMPUTER_SSH_PASSWORD"),
                "Computer SSH configuration requires manual verification")
        key = self.paths["client"] / "id_ed25519"
        require(key.is_file(), "Computer client key is missing")
        networks = self.containers()["computer"]["NetworkSettings"]["Networks"]
        address = networks["openalbert_computer"]["IPAddress"]
        command(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new",
                 "-o", "UserKnownHostsFile=" + str(self.run_dir / "known_hosts"), "-i", str(key), "albert@" + address,
                 "python3 -c 'import sys; assert sys.version_info >= (3,9)' && sudo -n true && test \"$(id -u)\" = 10001"], timeout=30)
        return {"ssh_python_sudo": True}

    def counts(self):
        tables = self.sql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
        return {table: int(self.sql('SELECT count(*) FROM "' + table.replace('"', '""') + '"')) for table in tables}

    @staticmethod
    def tree(root):
        result = {}
        for path in sorted(root.rglob("*")):
            require(not path.is_symlink(), "Unexpected symlink in verification data")
            if path.is_file():
                result[str(path.relative_to(root))] = {"bytes": path.stat().st_size, "hash": file_hash(path)}
        return result

    def pause(self, service):
        self.record["paused"].append(service)
        self.save("copying")  # Persist intent before issuing stop, including interrupted stop calls.
        command(["docker", "stop", "--time", "45", self.baseline["containers"][service]["id"]], timeout=65)

    def backup(self, args):
        require(self.record.get("phase") == "prepared", "Unexpected backup phase")
        require(self.baseline == self.discover({}), "Installation changed during image download")
        for service in self.plan["changed"]:
            target = self.plan["targets"][service]
            require(image_matches(self.image(target["repo"] + "@" + target["digest"]), target),
                    "Downloaded image differs from plan: " + service)
        self.backup_lock = self.lock(self.paths["backup-state"] / "backup.lock")
        self.check_backup(deadline=True)
        self.before_files = self.inventory()
        size = int(self.sql("SELECT pg_database_size(current_database())"))
        needed = size + sum(p.stat().st_size for p in self.paths["knowledge"].rglob("*") if p.is_file()) + 2 * 1024**3
        require(shutil.disk_usage(self.run_dir).free >= needed, "Insufficient free space for verified data copy")
        self.pause("backup")
        self.pause("openalbert")
        self.before_counts = self.counts()
        self.before_trees = {name: self.tree(self.paths[name]) for name in ("knowledge", "client", "server")}
        write_json(self.run_dir / "data-before.json", {"counts": self.before_counts, "trees": self.before_trees,
                                                      "s3_objects": self.before_files})
        dump = self.run_dir / "openalbert.dump"
        with open(dump, "wb") as output:
            command(["docker", "exec", self.containers()["postgres"]["Id"], "pg_dump", "-U", "openalbert",
                     "-d", "openalbert", "-Fc"], stdout=output, timeout=1800)
        with open(dump, "rb") as source:
            listed = command(["docker", "exec", "-i", self.containers()["postgres"]["Id"], "pg_restore", "--list"], stdin=source, timeout=120)
        require(b"openalbert_" in listed, "Database dump has no application objects")
        (self.run_dir / "pg-restore-list.txt").write_bytes(listed)
        archive = self.run_dir / "knowledge.tar.gz"
        command(["tar", "--numeric-owner", "-czf", str(archive), "-C", self.directory, "container_data/knowledge"], timeout=300)
        with tarfile.open(archive) as source:
            verified = {}
            for member in source:
                require(member.name == "container_data/knowledge" or member.name.startswith("container_data/knowledge/"),
                        "Unexpected archive entry")
                require(member.isdir() or member.isfile(), "Unexpected archive link")
                if member.isfile():
                    stream = source.extractfile(member)
                    h = hashlib.sha256()
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(block)
                    verified[member.name.removeprefix("container_data/knowledge/")] = {"bytes": member.size, "hash": h.hexdigest()}
        require(verified == self.before_trees["knowledge"], "Knowledge archive verification failed")
        self.checks["backup"] = {"dump_bytes": dump.stat().st_size, "knowledge_files": len(verified),
                                  "dump_sha256": file_hash(dump), "knowledge_sha256": file_hash(archive)}
        write_json(self.run_dir / "backup-verified.json", self.checks["backup"])
        self.save("backup_verified")
        return self.checks["backup"]

    def release_backup(self):
        if self.backup_lock:
            self.backup_lock.close()
            self.backup_lock = None

    def up(self, services, wait):
        if not services:
            return
        command(self.compose(["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait",
                              "--wait-timeout", str(wait)] + services), timeout=wait + 60)

    def wait_ready(self, services, timeout):
        deadline = time.monotonic() + timeout
        while True:
            containers = self.containers()
            ready = all(containers[s]["State"]["Running"] and
                        containers[s]["State"].get("Health", {}).get("Status", "healthy") == "healthy" for s in services)
            if ready and "backup" in services:
                state = read_json(self.paths["backup-state"] / "status.json")
                ready = timestamp(state["heartbeat_at"]) >= timestamp(self.record["started_at"])
            if ready:
                return
            require(time.monotonic() < deadline, "Services did not become ready: " + ", ".join(services))
            time.sleep(0.5)

    def deploy(self, args):
        require(self.record.get("phase") == "backup_verified", "Verified backup is required")
        require(self.baseline["files"] == {path: file_hash(path) for path in self.baseline["files"]},
                "Configuration files changed before deployment")
        require(fingerprint(json_command(self.compose(["config", "--format", "json"]))) == self.baseline["config_hash"],
                "Effective configuration changed before deployment")
        require(self.baseline["backup_files"] == {str(path): file_hash(path) for path in self.paths["backup-config"].rglob("*") if path.is_file()}, "Backup settings changed before deployment")
        command(self.compose(["config", "-q"]))
        self.check_backup(deadline=True)
        self.save("tagging")
        # Old image aliases were retained before pulls. Resolve mutable master only once.
        for service in self.plan["changed"]:
            target = self.plan["targets"][service]
            command(["docker", "tag", target["repo"] + "@" + target["digest"], target["repo"] + ":master"])
        self.save("deploying", deployment_started=True, started_at=now().isoformat())
        wait = args.get("wait_timeout", 180)
        self.up([s for s in ("log-gateway", "stt", "openalbert") if s in self.plan["changed"]], wait)
        if "openalbert" not in self.plan["changed"]:
            command(["docker", "start", self.baseline["containers"]["openalbert"]["id"]])
            self.wait_ready(["openalbert"], wait)
        # The controller initializes under backup.lock itself; release before starting it.
        self.check_backup(deadline=True)
        self.release_backup()
        if "backup" in self.plan["changed"]:
            self.up(["backup"], wait)
        else:
            command(["docker", "start", self.baseline["containers"]["backup"]["id"]])
        self.wait_ready(["backup"], min(wait, 30))
        self.save("verifying")
        return {"deployed": self.plan["changed"]}

    def verify(self, args):
        require(self.record.get("phase") == "verifying", "No deployment awaiting verification")
        containers = self.containers()
        checks = self.checks
        for service, before in self.baseline["containers"].items():
            after = containers[service]
            if not before["running"]:
                require(not after["State"]["Running"] and after["State"]["ExitCode"] == 0, "Init service failed")
                continue
            require(after["State"]["Running"] and after["State"].get("Health", {}).get("Status", "healthy") == "healthy",
                    "Service unhealthy: " + service)
            require(after["RestartCount"] == (0 if service in self.plan["changed"] else before["restarts"]),
                    "Unexpected restart: " + service)
            if service in self.plan["changed"]:
                require(image_matches(self.image(after["Image"]), self.plan["targets"][service]),
                        "Running image mismatch: " + service)
            else:
                require(after["Id"] == before["id"], "Unexpected container replacement: " + service)
                if service not in self.record["paused"]:
                    require(after["State"]["StartedAt"] == before["started"], "Unexpected stop/start: " + service)
        for path in ("/healthz", "/inspect/"):
            try:
                with urllib.request.urlopen("http://192.168.1.31:8080" + path, timeout=20) as response:
                    require(response.status == 200, "Application HTTP check failed")
            except OSError:
                raise Refused("Application HTTP check failed") from None
        command(["docker", "exec", containers["temporal"]["Id"], "temporal", "operator", "cluster", "health", "--address", "temporal:7233"])
        if "stt" in self.config["services"]:
            command(["docker", "exec", containers["stt"]["Id"], "python3", "-c",
                     "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready',timeout=10)"])
        counts = self.counts()
        require(all(counts.get(table, -1) >= count for table, count in self.before_counts.items()), "Application row count decreased")
        for name, before in self.before_trees.items():
            require(self.tree(self.paths[name]) == before, "Verification files changed: " + name)
        inventory = self.inventory()
        require(all(inventory.get(key) == size for key, size in self.before_files.items()), "S3 object missing or resized")
        samples = list(self.before_files)[::max(1, len(self.before_files) // 10)][:10]
        for key in samples:
            size = self.before_files[key]
            req = urllib.request.Request("http://192.168.1.31:8080/api/inspect/file/content?" + urllib.parse.urlencode({"key": key}),
                                         headers={"Range": "bytes=0-0"} if size else {})
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    if size:
                        require(response.status == 206 and response.headers.get("Content-Range") == "bytes 0-0/" + str(size)
                                and len(response.read(2)) == 1, "S3 sample read failed")
                    else:
                        require(response.status == 200 and response.read(1) == b"", "Empty S3 object check failed")
            except OSError:
                raise Refused("S3 sample check failed") from None
        checks["computer_after"] = self.computer_probe()
        checks["llm_after"] = llm_probe(self.app_env())
        checks["s3_backup_after"] = self.remote_copies()
        state = self.check_backup()
        require(all(state.get(key) == self.backup_config.get(key) for key in ("time", "timezone", "keep_days")), "Backup schedule changed")
        require(read_json(self.paths["backup-config"] / "config.json") == self.backup_config, "Backup policy changed")
        require(timestamp(state["heartbeat_at"]) >= timestamp(self.record["started_at"]), "Backup controller did not initialize")
        require(self.baseline["backup_files"] == {str(path): file_hash(path) for path in self.paths["backup-config"].rglob("*") if path.is_file()}, "Backup credentials or configuration changed")
        require(self.baseline["files"] == {path: file_hash(path) for path in self.baseline["files"]}, "Installation configuration changed")
        log_results = {}
        for service in self.plan["changed"]:
            raw = self.logs(service, self.record["started_at"])
            (self.run_dir / (service + ".log")).write_bytes(raw)
            errors = error_signatures(raw)
            unexpected = set(errors) - set(self.logs_before[service])
            log_results[service] = {"error_lines": len(errors), "new_error_types": len(unexpected)}
            require(not unexpected, "New errors in service logs: " + service)
        checks.update(http=True, dependencies=True, data=True, computer_ssh_python_sudo=True,
                      backup_policy=True, s3={"objects": len(inventory), "samples": len(samples)}, logs=log_results)
        receipt = {"version": VERSION, "backup_dir": str(self.run_dir), "checked_at": now().isoformat(),
                   "revisions": {s: self.plan["targets"][s]["revision"] for s in self.plan["changed"]},
                   "images": {s: self.image(containers[s]["Image"]) for s in self.plan["changed"]},
                   "warnings": self.baseline["warnings"], "checks": checks}
        write_json(self.run_dir / "verification.json", receipt)
        self.save("completed")
        return receipt

    def restore_paused(self):
        self.release_backup()
        containers = self.containers()
        for service in ("openalbert", "backup"):
            if service not in self.record.get("paused", []):
                continue
            before = self.baseline["containers"][service]
            current = containers[service]
            require(current["Id"] == before["id"], "Original container is missing; manual recovery required")
            if not current["State"]["Running"]:
                command(["docker", "start", before["id"]])

    def cleanup(self, error=None):
        if self.run_dir and self.deployment_lock and self.record.get("phase") not in {"completed", "recovered_before_deployment", "aborted_before_deployment"}:
            if not self.record.get("deployment_started"):
                try:
                    self.restore_paused()
                    self.save("aborted_before_deployment", error=error or "Connection closed", originals_restarted=True)
                except Exception:
                    self.save("recovery_required", error="Original containers could not be restarted")
            else:
                self.release_backup()
                # Originals which were never replaced have not run any new migrations.
                for service in ("openalbert", "backup"):
                    try:
                        current = self.containers()[service]
                        old = self.baseline["containers"][service]
                        if current["Id"] == old["id"] and not current["State"]["Running"]:
                            command(["docker", "start", old["id"]])
                    except Exception:
                        pass
                self.save("failed_after_deployment", error=error or "Connection closed",
                          recovery="Inspect diagnostics and data compatibility before a manual image rollback; no automatic database restore")
                for service in self.plan["changed"]:
                    try:
                        (self.run_dir / (service + ".log")).write_bytes(self.logs(service, self.record["started_at"]))
                    except Exception:
                        pass
        self.release_backup()
        if self.deployment_lock:
            self.deployment_lock.close()
            self.deployment_lock = None

    def recover(self, args):
        path = Path(args["run_dir"])
        require(path.is_absolute() and path.is_dir(), "Invalid recovery directory")
        record = read_json(path / "status.json")
        require(not record.get("deployment_started"), "Deployment was attempted; automatic recovery is refused")
        plan = read_json(path / "plan.json")
        deployment_lock = self.lock(plan["baseline"]["lock_path"])
        backup_lock = None
        try:
            require(plan["baseline"]["files"] == {p: file_hash(p) for p in plan["baseline"]["files"]}, "Configuration changed; inspect before recovery")
            self.directory = plan["baseline"]["directory"]
            self.config_files, self.env_files = plan["baseline"]["config_files"], plan["baseline"]["env_files"]
            config = json_command(self.compose(["config", "--format", "json"]))
            require(fingerprint(config) == plan["baseline"]["config_hash"], "Effective configuration changed before recovery")
            state_path = Path(next(m["source"] for m in config["services"]["backup"]["volumes"]
                                   if m["target"] == "/installation/container_data/backup-state"))
            backup_lock = self.lock(state_path / "backup.lock")
            require(read_json(state_path / "status.json").get("phase") in TERMINAL, "Cold backup is active; recovery refused")
            current = self.containers()
            require(all(current[s]["Id"] == plan["baseline"]["containers"][s]["id"] for s in record.get("paused", [])),
                    "Original container is missing; manual recovery required")
        except BaseException:
            if backup_lock:
                backup_lock.close()
            deployment_lock.close()
            raise
        self.run_dir, self.record = path, record
        self.plan = plan
        self.directory = plan["baseline"]["directory"]
        self.config_files, self.env_files = plan["baseline"]["config_files"], plan["baseline"]["env_files"]
        self.baseline = plan["baseline"]
        self.deployment_lock = deployment_lock
        self.backup_lock = backup_lock
        self.restore_paused()
        self.save("recovered_before_deployment", originals_restarted=True, error=None)
        return {"backup_dir": str(path), "originals_restarted": True}


def worker_main():
    os.umask(0o077)
    worker = Worker()
    def interrupted(signum, frame):
        raise InterruptedError()
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    error = None
    try:
        for line in sys.stdin:
            request = json.loads(line)
            require(request["method"] in {"discover", "begin", "backup", "deploy", "verify", "recover"}, "Unknown worker method")
            result = getattr(worker, request["method"])(request.get("args", {}))
            print(json.dumps({"ok": True, "result": result}), flush=True)
    except BaseException as failure:
        error = str(failure) if isinstance(failure, Refused) else "Worker stopped: " + type(failure).__name__
        if worker.run_dir and getattr(failure, "diagnostics", None):
            try:
                (worker.run_dir / "command-error.log").write_bytes(failure.diagnostics)
            except OSError:
                pass
        print(json.dumps({"ok": False, "error": error, "backup_dir": str(worker.run_dir) if worker.run_dir else None}), flush=True)
    finally:
        worker.cleanup(error)


class Remote:
    def __init__(self, host):
        require(re.fullmatch(r"[A-Za-z0-9_.@-]+", host) and not host.startswith("-"), "Invalid SSH host")
        source = Path(__file__).read_text()
        cmd = "sudo -n python3 -u -c " + shlex.quote(source) + " --worker"
        self.process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, cmd],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def call(self, method, **args):
        try:
            self.process.stdin.write(json.dumps({"method": method, "args": args}) + "\n")
            self.process.stdin.flush()
            response = self.process.stdout.readline()
        except (OSError, BrokenPipeError):
            raise Refused("SSH worker disconnected; inspect its private run status before retrying") from None
        require(response, "SSH worker unavailable; check BatchMode SSH and sudo -n")
        result = json.loads(response)
        if not result["ok"]:
            message = result["error"]
            if result.get("backup_dir"):
                message += "; run: " + result["backup_dir"]
            raise Refused(message)
        return result["result"]

    def close(self):
        self.process.stdin.close()
        # The worker sees EOF and restores paused originals before a deployment.
        try:
            self.process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            print("Worker cleanup still running; inspect status before using recover", file=sys.stderr)


def make_plan(remote, host, source):
    baseline = remote.call("discover")
    targets, changed, blockers = {}, [], []
    for service, ref in baseline["images"].items():
        if service not in ROUTINE | {"minio"}:
            continue
        require(ref.endswith(":master"), "Expected master image tag: " + service)
        target = registry_image(ref[:-7])
        targets[service] = target
        old = baseline["containers"][service]["image"]
        if image_matches(old, target):
            continue
        changed.append(service)
        if service not in ROUTINE:
            blockers.append({"service": service, "reason": "Storage image changed; manual consistent backup and deployment required"})
            continue
        try:
            expected_source = command(["git", "-C", str(source), "remote", "get-url", "origin"]).decode().strip().removesuffix(".git").lower()
            require(target["source"].removesuffix(".git").lower() == expected_source
                    and (old["source"] or "").removesuffix(".git").lower() == expected_source,
                    "Image source does not match the reviewed checkout")
            risky = source_guard(source, old["revision"], target["revision"], service)
            if risky:
                blockers.append({"service": service, "reason": "Structural source changes require manual review/deployment", "paths": risky})
        except Refused as error:
            blockers.append({"service": service, "reason": str(error)})
    return {"version": VERSION, "host": host, "created_at": now().isoformat(), "baseline": baseline,
            "targets": targets, "changed": sorted(changed), "blockers": blockers}


def validate_plan(plan, host, source):
    require(plan.get("version") == VERSION and plan.get("host") == host, "Plan version or host mismatch")
    require(dt.timedelta(0) <= now() - timestamp(plan["created_at"]) < dt.timedelta(hours=2), "Plan expired; create a new plan")
    require(not plan["blockers"], "Plan has blockers; use the manual deployment skill")
    require(set(plan["changed"]) <= ROUTINE, "Plan includes a storage or computer update")
    expected_changed = {s for s, target in plan["targets"].items()
                        if not image_matches(plan["baseline"]["containers"][s]["image"], target)}
    require(set(plan["changed"]) == expected_changed, "Plan service selection is inconsistent")
    for service in plan["changed"]:
        target = plan["targets"][service]
        expected_source = command(["git", "-C", str(source), "remote", "get-url", "origin"]).decode().strip().removesuffix(".git").lower()
        require(target["source"].removesuffix(".git").lower() == expected_source, "Image source changed")
        require(all(DIGEST.fullmatch(target[field]) for field in ("digest", "arm_digest", "config_digest")), "Invalid image digest")
        require(target["repo"] + ":master" == plan["baseline"]["images"][service], "Image repository changed")
        require(not source_guard(source, plan["baseline"]["containers"][service]["image"]["revision"], target["revision"], service),
                "Structural changes require manual deployment")


def apply_plan(remote, plan, args):
    validate_plan(plan, args.host, args.source)
    if not plan["changed"]:
        require(remote.call("discover") == plan["baseline"], "Installation changed since the plan")
        print("All running images already match the plan.", flush=True)
        return
    result = remote.call("begin", plan=plan, backup_root=args.backup_root)
    print("Rollback directory on " + args.host + ": " + result["backup_dir"], flush=True)
    for service in plan["changed"]:
        target = plan["targets"][service]
        print("Pulling verified ARM64 image: " + service, flush=True)
        command(["docker", "--host", "ssh://" + args.host, "pull", "--platform", "linux/arm64",
                 target["repo"] + "@" + target["digest"]], timeout=1800)
    print("Creating and verifying database/knowledge copy; application will pause.", flush=True)
    remote.call("backup")
    print("Starting selected services.", flush=True)
    remote.call("deploy", wait_timeout=args.wait_timeout)
    print("Verifying application, LLM, data, computer and S3 backups.", flush=True)
    receipt = remote.call("verify")
    print(json.dumps(receipt, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="mishankov@pi")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent / "vendor/openalbert")
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan", help="Read-only deployment/registry inspection; no pulls, pauses or LLM calls")
    plan.add_argument("--output", type=Path, required=True)
    apply = sub.add_parser("apply", help="Apply an unexpired plan, including two small LLM requests")
    apply.add_argument("--plan", type=Path, required=True)
    apply.add_argument("--backup-root", default="/home/mishankov/openalbert-update-backups")
    apply.add_argument("--wait-timeout", type=int, default=180)
    recover = sub.add_parser("recover", help="Restart exact originals after an interrupted pre-deployment copy")
    recover.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    remote = None
    try:
        remote = Remote(args.host)
        if args.action == "plan":
            result = make_plan(remote, args.host, args.source)
            write_json(args.output, result)
            print(json.dumps({"plan": str(args.output), "changed": result["changed"], "blockers": result["blockers"],
                              "warnings": result["baseline"]["warnings"]}, indent=2))
            return 2 if result["blockers"] else 0
        if args.action == "apply":
            apply_plan(remote, read_json(args.plan), args)
        else:
            print(json.dumps(remote.call("recover", run_dir=args.run_dir), indent=2))
        return 0
    except (Refused, OSError, ValueError, KeyError) as error:
        message = str(error) if isinstance(error, Refused) else type(error).__name__
        print("Update stopped: " + message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; waiting for worker cleanup. Check status before retrying.", file=sys.stderr)
        return 130
    finally:
        if remote:
            remote.close()


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        worker_main()
    else:
        sys.exit(main())
