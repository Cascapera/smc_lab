"""Run manage.py check with CI settings (used by .pre-commit-config.yaml)."""

from __future__ import annotations

import os
import subprocess
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trader_portal.settings.ci")
raise SystemExit(subprocess.call([sys.executable, "manage.py", "check"]))
