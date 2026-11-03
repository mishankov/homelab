#!/usr/bin/env python3
"""Run Railway CLI for this instance without putting credentials in argv."""

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
settings_path = ROOT / ".private/settings.json"
if not settings_path.exists():
    sys.exit("Missing .private/settings.json; see README.md")
settings = json.loads(settings_path.read_text())
project = settings["project"]
environment = os.environ.copy()
for name in ("RAILWAY_TOKEN", "RAILWAY_SERVICE_ID", "RAILWAY_ENV"):
    environment.pop(name, None)
environment["RAILWAY_PROJECT_ID"] = project["id"]
environment["RAILWAY_ENVIRONMENT_ID"] = project["environmentId"]
token_file = Path(settings["files"]["RAILWAY_API_TOKEN"])
environment["RAILWAY_API_TOKEN"] = token_file.read_text().strip()
os.chdir(ROOT)
command = ["npx", "--yes", "@railway/cli@5.71.0", *sys.argv[1:]]
os.execvpe(command[0], command, environment)
