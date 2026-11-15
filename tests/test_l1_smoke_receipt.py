# SPDX-License-Identifier: Apache-2.0
"""LANE 1'S CI RECEIPT OF P01'S SMOKE. THIS FILE NEVER LANDS ANYWHERE.

opensoft/openRepoTools#165, the coordinator's comment 6895004104, asks for
`python3 -I -B tests/pgcluster.py --smoke session stoppable` to run on CI at
P01's reviewed head 7f1141be, rather than binary detection alone: that smoke
starts a cluster, clones a database from the empty template and runs SELECT 1,
stops a cluster by SIGINT, starts it again and runs SELECT 1, and removes what
it made. No workflow at 7f1141be runs it, so this one test does, unchanged, in
a verify commit whose tree is P01's plus this file.

IT NEVER SKIPS. Under `Verify-Postgres: 1` the runner has PostgreSQL 16 and
`OPENREPOTOOLS_REQUIRE_PG=1`; where the engine is missing the smoke exits 1
and this test fails, with the exit code, stdout and stderr whole in its
message. Python 3.9 or later, standard library only.
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
    # The smoke's own lines go to the run's log, which a passing test's
    # captured output never reaches.
    with capsys.disabled():
        print(f"\n$ python3 -I -B tests/pgcluster.py --smoke session stoppable\n{said}", end="")
    assert proc.returncode == 0, said
    lines = proc.stdout.splitlines()
    for prefix in EXPECTED:
        assert any(line.startswith(prefix) for line in lines), f"no stdout line starts {prefix!r}\n{said}"
