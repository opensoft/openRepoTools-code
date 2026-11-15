# SPDX-License-Identifier: Apache-2.0
"""Coordinator-only real fixture receipt; this file never lands in product source.

Use only on an isolated GitHub verify branch whose parent is the recorded
actual-main foundation epoch. The executable test body follows the original
P01 smoke driver: no mock, skip, workflow change or substitute engine detection.
The commit/run record binds the base and helper blobs separately. Never execute
the fixture's stale-cluster sweep on a user bench or shared PID/tmp namespace.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = [sys.executable, "-I", "-B", "tests/pgcluster.py", "--smoke", "session", "stoppable"]
EXPECTED = ("pgcluster: smoke session: ok:", "pgcluster: smoke stoppable: ok:")


def test_pgcluster_smoke_session_and_stoppable_exit_0_on_the_real_engine(capsys):
    proc = subprocess.run(SMOKE, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    said = (f"the smoke exited {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}--- stderr ---\n{proc.stderr}")
    with capsys.disabled():
        print(f"\n$ python3 -I -B tests/pgcluster.py --smoke session stoppable\n{said}", end="")
    assert proc.returncode == 0, said
    lines = proc.stdout.splitlines()
    for prefix in EXPECTED:
        assert any(line.startswith(prefix) for line in lines), f"no stdout line starts {prefix!r}\n{said}"
