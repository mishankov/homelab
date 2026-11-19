"""Fault-injection checks with synthetic data; never connect to Docker or the Pi."""

import copy
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import update


SECRET = "synthetic-private-key-must-not-appear"
ORIGIN = "https://github.com/example/OpenAlbert"
OLD, NEW = "a" * 40, "b" * 40


def target(service, char="b", revision=NEW):
    return {"repo": "ghcr.io/example/openalbert/" + service, "digest": "sha256:" + update.hashlib.sha256((service + char).encode()).hexdigest(),
            "arm_digest": "sha256:" + "c" * 64, "config_digest": "sha256:" + "d" * 64,
            "revision": revision, "source": ORIGIN, "download_bytes": 100}


class Installation:
    """Real temporary files/archives/locks, simulated Docker and HTTP boundaries."""

    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.project = self.directory / "checkout/openalbert"
        self.project.mkdir(parents=True)
        self.root = self.directory / "rollback"
        self.root.mkdir(mode=0o700)
        self.calls = []
        self.failure = None
        self.files = {"object-one": 12, "object-two": 5}
        self.hashes = {}
        for name in (".env", "pi.env", "compose.yaml"):
            (self.project / name).write_text(SECRET if name == ".env" else "synthetic")
        for name in ("knowledge", "computer/client", "computer/server", "backup-state"):
            path = self.project / "container_data" / name
            path.mkdir(parents=True)
            if name != "backup-state":
                (path / "retained").write_text("retained-value")
        (self.project / "container_data/computer/client/id_ed25519").write_text(SECRET)
        config = self.project / "backup-config"
        config.mkdir()
        self.policy = {"exclude_computer": True, "enabled": True, "time": "02:30",
                       "timezone": "Europe/Moscow", "keep_days": 14}
        update.write_json(config / "config.json", self.policy)
        update.write_json(config / "s3.json", {"key": SECRET})
        self.state_path = self.project / "container_data/backup-state/status.json"
        self.state = {**self.policy, "phase": "completed", "heartbeat_at": update.now().isoformat(),
                      "next_run_at": (update.now() + dt.timedelta(hours=12)).isoformat(),
                      "last_success": {"id": "verified-copy", "created_at": update.now().isoformat()}}
        update.write_json(self.state_path, self.state)
        config_files = str(self.project / "compose.yaml")
        env_files = ",".join(str(self.project / n) for n in (".env", "pi.env"))
        self.config = {"name": "openalbert", "services": {}}
        self.containers = {}
        self.images = {}
        self.logs = {}
        names = ["openalbert", "backup", "stt", "log-gateway", "minio", "computer", "postgres", "temporal"]
        for service in names:
            definition = {"image": "ghcr.io/example/openalbert/" + service + ":master", "volumes": [], "environment": {}}
            if service == "openalbert":
                definition["ports"] = [{"host_ip": "192.168.1.31", "published": "8080", "target": 8080}]
                definition["environment"] = {"LLM_API_KEY": SECRET, "LLM_BASE_URL": "http://provider.invalid/v1", "LLM_MODEL": "test"}
                definition["environment"].update(COMPUTER_SSH_ADDRESS="computer:22", COMPUTER_SSH_USER="albert",
                                                  COMPUTER_SSH_KEY_FILE="/data/computer/id_ed25519")
            if service == "postgres":
                definition["ports"] = [{"host_ip": "127.0.0.1", "published": "15432", "target": 5432}]
            if service == "computer":
                definition.update(image="local-computer", pull_policy="never")
            self.config["services"][service] = definition
            self.hashes[service] = "hash-" + service
            image_id = "old-image-" + service
            old = target(service, "a", OLD)
            self.images[image_id] = self.image_record(image_id, old)
            labels = {"com.docker.compose.service": service, "com.docker.compose.project.working_dir": str(self.project),
                      "com.docker.compose.project.config_files": config_files,
                      "com.docker.compose.project.environment_file": env_files,
                      "com.docker.compose.config-hash": self.hashes[service]}
            self.containers[service] = {"Id": "old-" + service, "Image": image_id, "RestartCount": 0,
                                        "Config": {"Labels": labels, "Env": [k + "=" + v for k, v in definition["environment"].items()]},
                                        "State": {"Running": True, "Status": "running", "ExitCode": 0,
                                                  "StartedAt": "2026-01-01T00:00:00Z", "Health": {"Status": "healthy"}},
                                        "NetworkSettings": {"Networks": {"openalbert_computer": {"IPAddress": "172.20.0.2"}}}}
            self.logs[service] = b""
        mounts = {"openalbert": [("knowledge", "/data/knowledge"), ("computer/client", "/data/computer")],
                  "backup": [("backup-state", "/installation/container_data/backup-state")],
                  "computer": [("computer/server", "/etc/openalbert-ssh")]}
        for service, entries in mounts.items():
            for source, dest in entries:
                self.config["services"][service]["volumes"].append({"source": str(self.project / "container_data" / source), "target": dest, "type": "bind"})
        self.config["services"]["backup"]["volumes"].append({"source": str(config), "target": "/etc/openalbert-backup", "type": "bind"})

    @staticmethod
    def image_record(image_id, image):
        return {"Id": image["digest"], "Os": "linux", "Architecture": "arm64", "RepoDigests": [image["repo"] + "@" + image["digest"]],
                "Config": {"Labels": {"org.opencontainers.image.revision": image["revision"], "org.opencontainers.image.source": ORIGIN}}}

    def service_for(self, identifier):
        return next(s for s, c in self.containers.items() if c["Id"] == identifier)

    def execute(self, args, *, stdout=None, stdin=None, input=None, **kwargs):
        self.calls.append(list(args))
        if self.failure and self.failure(args):
            raise update.Refused("Synthetic failure")
        if args[:2] == ["docker", "ps"]:
            return "\n".join(c["Id"] for c in self.containers.values()).encode()
        if args[:2] == ["docker", "info"]:
            return b"true"
        if args[:2] == ["docker", "inspect"]:
            return update.canonical([c for c in self.containers.values() if c["Id"] in args[2:]])
        if args[:3] == ["docker", "image", "inspect"]:
            return update.canonical([self.images[args[3]] if args[3] in self.images else next(i for i in self.images.values() if i["Id"] == args[3])])
        if args[:2] == ["docker", "compose"]:
            if "config" in args:
                if "--hash" in args:
                    return "\n".join(s + " " + h for s, h in self.hashes.items()).encode()
                return update.canonical(self.config) if "--format" in args else b""
            # Services follow the explicit wait-timeout value.
            services = args[args.index("--wait-timeout") + 2:]
            for s in services:
                if s == "backup":
                    # Regression: the new scheduler must be able to acquire backup.lock.
                    lock = update.Worker().lock(self.project / "container_data/backup-state/backup.lock")
                    lock.close()
                container = self.containers[s]
                container.update(Id="new-" + s, Image=self.config["services"][s]["image"], RestartCount=0)
                container["State"].update(Running=True, Status="running", StartedAt=update.now().isoformat())
                if s == "backup":
                    self.state["heartbeat_at"] = update.now().isoformat()
                    update.write_json(self.state_path, self.state)
            return b""
        if args[:2] == ["docker", "tag"]:
            self.images[args[3]] = copy.deepcopy(self.images[args[2]] if args[2] in self.images else next(i for i in self.images.values() if i["Id"] == args[2]))
            return b""
        if args[:2] == ["docker", "stop"]:
            self.containers[self.service_for(args[-1])]["State"].update(Running=False, Status="exited")
            return b""
        if args[:2] == ["docker", "start"]:
            s = self.service_for(args[-1])
            self.containers[s]["State"].update(Running=True, Status="running", StartedAt=update.now().isoformat())
            if s == "backup":
                self.state["heartbeat_at"] = update.now().isoformat()
                update.write_json(self.state_path, self.state)
            return b""
        if args[:2] == ["docker", "exec"]:
            if "list" in args:
                return update.canonical([{"id": "verified-copy"}])
            if "pg_dump" in args:
                stdout.write(b"synthetic-pg-dump")
                return b""
            if "pg_restore" in args:
                assert stdin.read() == b"synthetic-pg-dump"
                return b"TABLE openalbert_messages\n"
            if "psql" in args:
                query = args[-1]
                return (b"100" if "pg_database_size" in query else b"openalbert_messages" if "pg_tables" in query else b"5")
            return b""
        if args[0] == "tar":
            with tarfile.open(args[3], "w:gz") as archive:
                archive.add(self.project / "container_data/knowledge", arcname="container_data/knowledge")
            return b""
        if args[0] == "ssh":
            return b""
        raise AssertionError("Unexpected synthetic command: " + str(args))

    def raw_process(self, args, **kwargs):
        assert args[:2] == ["docker", "logs"], args
        return subprocess.CompletedProcess(args, 0, self.logs[self.service_for(args[-1])], b"")

    def downloaded(self, plan):
        for service in plan["changed"]:
            image = plan["targets"][service]
            ref = image["repo"] + "@" + image["digest"]
            self.images[ref] = self.image_record("new-image-" + service, image)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.install = Installation(self.temp.name)
        for name, replacement in [("command", self.install.execute), ("subprocess.run", self.install.raw_process),
                                  ("os.geteuid", lambda: 0), ("llm_probe", lambda env: {"status": 200})]:
            patcher = patch.object(update, name, replacement) if "." not in name else patch("update." + name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.worker = update.Worker()
        self.worker.inventory = lambda: self.install.files.copy()
        self.addCleanup(self.worker.cleanup)
        baseline = self.worker.discover({})
        self.plan = {"version": update.VERSION, "host": "test", "created_at": update.now().isoformat(),
                     "baseline": copy.deepcopy(baseline), "targets": {s: target(s) for s in ("openalbert", "backup")},
                     "changed": ["openalbert", "backup"], "blockers": []}
        self.install.downloaded(self.plan)

    def begin(self):
        return self.worker.begin({"plan": self.plan, "backup_root": str(self.install.root)})

    def verified_backup(self):
        self.begin()
        self.worker.backup({})

    def test_discovery_is_read_only_and_private(self):
        self.assertNotIn(SECRET, json.dumps(self.plan))
        self.assertFalse(any("stop" in args or "tag" in args or "up" in args for args in self.install.calls))
        self.assertFalse(list(self.install.root.iterdir()))

    def test_backup_accepts_repo_digest_added_by_rollback_tag(self):
        self.begin()
        image_id = self.install.containers["openalbert"]["Image"]
        self.install.images[image_id]["RepoDigests"].insert(0, "homelab-rollback/openalbert@" + target("openalbert")["digest"])
        self.worker.backup({})
        self.assertEqual(self.worker.record["phase"], "backup_verified")

    def test_runtime_drift_blocks_before_mutation(self):
        self.install.containers["openalbert"]["Config"]["Labels"]["com.docker.compose.config-hash"] = "changed"
        with self.assertRaisesRegex(update.Refused, "configuration drift"):
            self.begin()

    def test_stale_plan_blocks_before_tagging(self):
        self.install.containers["computer"]["State"]["StartedAt"] = "changed"
        with self.assertRaisesRegex(update.Refused, "changed since"):
            self.begin()
        self.assertFalse(any("tag" in c for c in self.install.calls))

    def test_queued_or_active_backup_refuses(self):
        for phase in ["copying", "uploading", "unknown"]:
            self.install.state["phase"] = phase
            update.write_json(self.install.state_path, self.install.state)
            with self.assertRaisesRegex(update.Refused, "Cold backup"):
                self.worker.discover({})

    def test_backup_lock_conflict_never_pauses_app(self):
        self.begin()
        held = self.worker.lock(self.install.project / "container_data/backup-state/backup.lock")
        try:
            with self.assertRaisesRegex(update.Refused, "lock is held"):
                self.worker.backup({})
            self.assertTrue(self.install.containers["openalbert"]["State"]["Running"])
        finally:
            held.close()

    def test_invalid_llm_key_refuses_before_pause(self):
        with patch("update.llm_probe", side_effect=update.Refused("HTTP check failed (status 401)")):
            with self.assertRaisesRegex(update.Refused, "status 401"):
                self.begin()
        self.worker.cleanup("preflight failed")
        self.assertFalse(any(c[:2] == ["docker", "stop"] for c in self.install.calls))

    def test_imminent_scheduled_backup_blocks_pause(self):
        self.begin()
        self.install.state["next_run_at"] = (update.now() + dt.timedelta(minutes=5)).isoformat()
        update.write_json(self.install.state_path, self.install.state)
        with self.assertRaisesRegex(update.Refused, "within ten minutes"):
            self.worker.backup({})
        self.assertFalse(any(c[:2] == ["docker", "stop"] for c in self.install.calls))

    def test_corrupt_dump_restores_exact_old_containers(self):
        self.begin()
        self.install.failure = lambda args: "pg_restore" in args
        with self.assertRaises(update.Refused):
            self.worker.backup({})
        self.worker.cleanup("dump failed")
        status = update.read_json(self.worker.run_dir / "status.json")
        self.assertEqual(status["phase"], "aborted_before_deployment")
        starts = [c[-1] for c in self.install.calls if c[:2] == ["docker", "start"]]
        self.assertEqual(starts, ["old-openalbert", "old-backup"])
        self.assertFalse(any("up" in c for c in self.install.calls))

    def test_wrong_download_platform_blocks_before_pause(self):
        self.begin()
        image = self.plan["targets"]["openalbert"]
        self.install.images[image["repo"] + "@" + image["digest"]]["Architecture"] = "amd64"
        with self.assertRaisesRegex(update.Refused, "differs from plan"):
            self.worker.backup({})
        self.assertFalse(any(c[:2] == ["docker", "stop"] for c in self.install.calls))

    def test_full_update_preserves_computer_and_verifies_real_archive(self):
        self.verified_backup()
        self.assertTrue((self.worker.run_dir / "backup-verified.json").exists())
        self.assertFalse(any("computer" in str(p.relative_to(self.worker.run_dir)) for p in self.worker.run_dir.rglob("*")))
        self.assertEqual((self.worker.run_dir / "config-01-.env").stat().st_mode & 0o777, 0o600)
        before = copy.deepcopy(self.install.containers["computer"])
        self.worker.deploy({"wait_timeout": 1})
        def response(request, **kwargs):
            result = FakeResponse()
            if isinstance(request, update.urllib.request.Request):
                key = update.urllib.parse.parse_qs(update.urllib.parse.urlparse(request.full_url).query)["key"][0]
                result.status = 206
                result.headers = {"Content-Range": "bytes 0-0/" + str(self.install.files[key])}
            return result
        with patch("update.urllib.request.urlopen", response):
            receipt = self.worker.verify({})
        self.assertEqual(receipt["checks"]["llm_after"]["status"], 200)
        self.assertEqual(self.install.containers["computer"], before)
        self.assertEqual(update.read_json(self.worker.run_dir / "status.json")["phase"], "completed")
        self.assertNotIn(SECRET, json.dumps(receipt))
        ups = [c for c in self.install.calls if "up" in c]
        self.assertEqual(len(ups), 2)
        self.assertTrue(all("--no-deps" in c and "--no-build" in c and "never" in c for c in ups))

    def test_failed_up_never_retries_or_restores_database(self):
        self.verified_backup()
        self.install.failure = lambda args: "up" in args
        with self.assertRaises(update.Refused):
            self.worker.deploy({})
        self.worker.cleanup("up failed")
        status = update.read_json(self.worker.run_dir / "status.json")
        self.assertEqual(status["phase"], "failed_after_deployment")
        self.assertEqual(len([c for c in self.install.calls if "up" in c]), 1)
        self.assertFalse(any("--clean" in c or "--create" in c for c in self.install.calls))
        self.assertTrue(self.install.containers["backup"]["State"]["Running"])

    def test_recovery_after_new_up_is_refused(self):
        self.verified_backup()
        self.worker.deploy({})
        other = update.Worker()
        with self.assertRaisesRegex(update.Refused, "automatic recovery is refused"):
            other.recover({"run_dir": str(self.worker.run_dir)})

    def test_held_deployment_lock_cannot_trigger_recovery_cleanup(self):
        self.verified_backup()
        other = update.Worker()
        with self.assertRaisesRegex(update.Refused, "lock is held"):
            other.recover({"run_dir": str(self.worker.run_dir)})
        other.cleanup()
        self.assertFalse(self.install.containers["openalbert"]["State"]["Running"])

    def simulate_worker_loss(self):
        run_dir = self.worker.run_dir
        self.worker.release_backup()
        self.worker.deployment_lock.close()
        self.worker.deployment_lock = None
        self.worker.run_dir = None
        return run_dir

    def test_recovery_after_lost_worker_starts_exact_originals(self):
        self.verified_backup()
        path = self.simulate_worker_loss()
        recovery = update.Worker()
        try:
            receipt = recovery.recover({"run_dir": str(path)})
            self.assertTrue(receipt["originals_restarted"])
            self.assertTrue(self.install.containers["openalbert"]["State"]["Running"])
            self.assertEqual(update.read_json(path / "status.json")["phase"], "recovered_before_deployment")
        finally:
            recovery.cleanup()

    def test_recovery_with_config_drift_does_not_start_anything(self):
        self.verified_backup()
        path = self.simulate_worker_loss()
        (self.install.project / ".env").write_text("changed")
        recovery = update.Worker()
        with self.assertRaisesRegex(update.Refused, "Configuration changed"):
            recovery.recover({"run_dir": str(path)})
        recovery.cleanup()
        self.assertFalse(self.install.containers["openalbert"]["State"]["Running"])

    def test_tag_failure_before_up_resumes_originals_even_with_master_changed(self):
        self.verified_backup()
        self.install.failure = lambda args: args[:2] == ["docker", "tag"] and args[-1].endswith("backup:master")
        with self.assertRaises(update.Refused):
            self.worker.deploy({})
        self.worker.cleanup("tag failed")
        self.assertTrue(self.install.containers["openalbert"]["State"]["Running"])
        self.assertFalse(update.read_json(self.worker.run_dir / "status.json")["deployment_started"])
        self.assertFalse(any("up" in c for c in self.install.calls))

    def test_missing_s3_object_fails_final_receipt(self):
        self.verified_backup()
        self.worker.deploy({})
        self.install.files = {}  # Assert data verification fails before any successful receipt.
        with patch("update.urllib.request.urlopen", return_value=FakeResponse()):
            with self.assertRaisesRegex(update.Refused, "S3 object missing"):
                self.worker.verify({})
        self.assertFalse((self.worker.run_dir / "verification.json").exists())
        self.worker.cleanup("verification failed")
        self.assertEqual(update.read_json(self.worker.run_dir / "status.json")["phase"], "failed_after_deployment")

    def test_new_log_error_blocks_success(self):
        self.verified_backup()
        self.worker.deploy({})
        self.install.logs["openalbert"] = b'{"level":"ERROR","msg":"new startup failure","error_code":"db_broken"}'
        def response(request, **kwargs):
            result = FakeResponse()
            if isinstance(request, update.urllib.request.Request):
                key = update.urllib.parse.parse_qs(update.urllib.parse.urlparse(request.full_url).query)["key"][0]
                result.status = 206
                result.headers = {"Content-Range": "bytes 0-0/" + str(self.install.files[key])}
            return result
        with patch("update.urllib.request.urlopen", response):
            with self.assertRaisesRegex(update.Refused, "New errors in service logs"):
                self.worker.verify({})
        self.assertFalse((self.worker.run_dir / "verification.json").exists())

    def test_independent_component_update_restarts_unmodified_app_without_recreation(self):
        del self.plan["targets"]["openalbert"]
        self.plan["changed"] = ["backup"]
        self.verified_backup()
        self.worker.deploy({"wait_timeout": 1})
        self.assertEqual(self.install.containers["openalbert"]["Id"], "old-openalbert")
        self.assertTrue(self.install.containers["openalbert"]["State"]["Running"])


class FakeResponse:
    status = 200
    headers = {"Content-Length": "12"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return b"x"


class PolicyTests(unittest.TestCase):
    def test_expired_or_blocked_plan_is_refused(self):
        plan = {"version": update.VERSION, "host": "pi", "created_at": (update.now() - dt.timedelta(hours=3)).isoformat(),
                "blockers": [], "changed": []}
        with self.assertRaisesRegex(update.Refused, "Plan expired"):
            update.validate_plan(plan, "pi", Path("unused"))
        plan.update(created_at=update.now().isoformat(), blockers=[{"reason": "schema change"}])
        with self.assertRaisesRegex(update.Refused, "Plan has blockers"):
            update.validate_plan(plan, "pi", Path("unused"))

    def test_template_review_is_bound_to_plan_and_cannot_clear_schema_blockers(self):
        service = "openalbert"
        old = target(service, "a", OLD)
        old_image = {"id": old["digest"], "revision": OLD, "source": ORIGIN,
                     "platform": "linux/arm64", "digests": [old["repo"] + "@" + old["digest"]]}
        blocker = {"service": service, "reason": update.STRUCTURAL_BLOCKER, "paths": ["deploy/compose.yaml"]}
        plan = {"version": update.VERSION, "host": "pi", "created_at": update.now().isoformat(),
                "baseline": {"images": {service: old["repo"] + ":master"},
                             "containers": {service: {"image": old_image}}},
                "changed": [service], "targets": {service: target(service)}, "blockers": [blocker]}
        reviewed = update.fingerprint(plan)
        with patch("update.command", return_value=ORIGIN.encode()), \
                patch("update.source_guard", return_value=blocker["paths"]) as guard:
            update.validate_plan(plan, "pi", Path("unused"), reviewed_plan=reviewed, review_reason="Same runtime default")
            plan["created_at"] = update.now().isoformat()
            with self.assertRaisesRegex(update.Refused, "exact plan fingerprint"):
                update.validate_plan(plan, "pi", Path("unused"), reviewed_plan=reviewed, review_reason="Same runtime default")
            blocker["paths"] = guard.return_value = ["schema.sql"]
            with self.assertRaisesRegex(update.Refused, "require manual deployment"):
                update.validate_plan(plan, "pi", Path("unused"), reviewed_plan=update.fingerprint(plan),
                                     review_reason="Same runtime default")

    def test_missing_arm_manifest_refuses_registry_candidate(self):
        index = {"manifest": {"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}]},
                 "image": {"linux/amd64": {}}}
        with patch("update.json_command", return_value=index):
            with self.assertRaisesRegex(update.Refused, "No linux/arm64"):
                update.registry_image("example/image")

    def test_plan_detects_storage_change_and_independent_component_revisions(self):
        baseline = {"images": {}, "containers": {}}
        candidates = {}
        for service in ["openalbert", "stt", "minio"]:
            old = target(service, "a", OLD)
            baseline["images"][service] = old["repo"] + ":master"
            baseline["containers"][service] = {"image": {"id": old["digest"], "revision": OLD,
                                                         "source": ORIGIN, "platform": "linux/arm64",
                                                         "digests": [old["repo"] + "@" + old["digest"]]}}
            candidates[old["repo"]] = old
        remote = unittest.mock.Mock()
        remote.call.return_value = baseline
        candidates[target("openalbert")["repo"]] = target("openalbert")
        with patch("update.registry_image", side_effect=lambda repo: candidates[repo]), \
                patch("update.source_guard", return_value=[]), patch("update.command", return_value=ORIGIN.encode()):
            plan = update.make_plan(remote, "pi", Path("unused"))
            self.assertEqual(plan["changed"], ["openalbert"])
            self.assertEqual(plan["blockers"], [])
            candidates[target("minio")["repo"]] = target("minio")
            plan = update.make_plan(remote, "pi", Path("unused"))
            self.assertEqual(plan["blockers"][0]["service"], "minio")
        self.assertTrue(all(call.args[0] == "discover" for call in remote.call.call_args_list))

    def test_independent_component_revisions_and_digest(self):
        image = target("stt", revision=OLD)
        actual = {"platform": "linux/arm64", "revision": OLD, "source": ORIGIN,
                  "id": image["config_digest"],
                  "digests": [image["repo"] + "@" + image["arm_digest"]]}
        self.assertTrue(update.image_matches(actual, image))
        actual["revision"] = NEW
        self.assertFalse(update.image_matches(actual, image))

    def test_command_error_never_exposes_secret_stderr(self):
        with patch("update.subprocess.run", return_value=subprocess.CompletedProcess(["docker"], 1, b"", SECRET.encode())):
            with self.assertRaises(update.Refused) as raised:
                update.command(["docker", "inspect"])
        self.assertNotIn(SECRET, str(raised.exception))

    def test_llm_uses_provider_session_and_never_exposes_response(self):
        captured = []
        def open_request(request, timeout):
            captured.append(request)
            raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", {}, io.BytesIO(SECRET.encode()))
        opener = unittest.mock.Mock()
        opener.open.side_effect = open_request
        with patch("update.urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(update.Refused, "status 401") as raised:
                update.llm_probe({"LLM_BASE_URL": "https://opencode.ai/inference/go/openai/v1", "LLM_MODEL": "test", "LLM_API_KEY": SECRET})
        self.assertNotIn(SECRET, str(raised.exception))
        self.assertIn("X-opencode-session", captured[0].headers)
        self.assertEqual(captured[0].headers["User-agent"], "OpenAlbert/0.1")

    def test_new_error_codes_are_not_hidden_by_old_activity_errors(self):
        before = update.error_signatures(b'{"level":"ERROR","msg":"Activity error.","Error":"HTTP 401"}')
        after = update.error_signatures(b'{"level":"ERROR","msg":"Activity error.","Error":"database broken"}')
        self.assertTrue(set(after) - set(before))
        before = update.error_signatures(b'{"level":"ERROR","msg":"Activity error.","error_code":"http_401","Error":"HTTP 401"}')
        after = update.error_signatures(b'{"level":"ERROR","msg":"Activity error.","error_code":"http_403","Error":"HTTP 403"}')
        self.assertTrue(set(after) - set(before))

    def test_source_guard_with_real_git_history(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)
            def git(*args):
                return subprocess.check_output(["git", "-C", name, *args], stderr=subprocess.DEVNULL).decode().strip()
            git("init")
            git("config", "user.name", "Synthetic Test")
            git("config", "user.email", "test@example.invalid")
            (path / "app.go").write_text("initial")
            git("add", "."); git("commit", "-m", "initial")
            old = git("rev-parse", "HEAD")
            (path / "app.go").write_text("routine")
            git("add", "."); git("commit", "-m", "routine")
            routine = git("rev-parse", "HEAD")
            self.assertEqual(update.source_guard(path, old, routine, "openalbert"), [])
            (path / "schema.sql").write_text("ALTER TABLE app DROP COLUMN data;")
            git("add", "."); git("commit", "-m", "migration")
            self.assertEqual(update.source_guard(path, routine, git("rev-parse", "HEAD"), "openalbert"), ["schema.sql"])


if __name__ == "__main__":
    unittest.main()
