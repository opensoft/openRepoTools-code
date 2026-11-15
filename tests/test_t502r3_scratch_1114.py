# SPDX-License-Identifier: Apache-2.0
"""SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's round 3, part
14 (`l5/007-T502-followup-1925`): S3 of lane 3's Codex delta review of
spec#47's draft 13 at `cd578400` (opensoft/openRepoTools#165 6880978929;
lane 3's routing, not Brett's). Lane 3's ruling: the pending record and the
copies go only where `guard_bind_settle` succeeds, and stay where it fails;
only the diagnostic at LR007 `another-write` was wrong. This file lives only on
the branch `scratch/t502r3-proof`; the bash form is
`scratch/t502r3-proof-1114.sh`.

Each case runs the tree's `lanes-edit.sh`, copied beside a stand-in
`lanes-index` whose lookup answers LR007 `another-write`, on a bind record that
names a write and a `start-record` pending record that holds it. The REAL outer
runs the REAL body. Where the settle must fail, a stand-in `rm` first on PATH
refuses the pending record and runs the real `rm` for every other call.

HERMETIC (CI run 43622597182 failed these cases with `lane-start: command not
found`, rc 127): PATH is /usr/bin:/bin only, so no installed `lane-start` or
`lanes-index` is reached; `LANES_HOST` and `LANES_IN_CONTAINER=0` are pinned,
so the host `guard_bind_copies` compares is the pending record's whatever the
runner's `/.dockerenv` and `hostname` say (a runner with no `/.dockerenv` read
its own `hostname -s`, found no copies, and went on to `lane-start`); and
`LANES_LANE_START` names a stand-in in the box that the cases require was never
called.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or not Path("/proc/self/stat").exists(),
    reason="the bind's liveness test reads /proc")]

SCRIPT = REPO / "lanes-edit.sh"
UUID = "aaaa1111-2222-3333-4444-555566667777"
HOST = "Eagle"
CONTAINER = "g-box"
BASE_PATH = "/usr/bin:/bin"   # nothing installed under /usr/local/bin is ever reached
WRITE_ID = "11111111-2222-3333-4444-555566667777"
GENERATION = "99999999-8888-7777-6666-555544443333"
DIGEST = "d" * 64
FILES = "e" * 64
REMOVED = "its pending record is removed"
KEPT = "could not be settled, so it and its copies are kept"


def q(value) -> str:
    return shlex.quote(str(value))


class Box:
    """One sandbox: `$HOME`, `$CLAUDE_CONFIG_DIR` with `lanes/offers/`, a state
    home with `register-pending/`, a `bin/` holding the script under test and
    its stand-in `lanes-index`, and a directory of stand-ins first on PATH."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.offers = tmp / "cfg" / "lanes" / "offers"
        self.offers.mkdir(parents=True)
        self.state = tmp / "state"
        self.pending_dir = self.state / "openRepoTools" / "register-pending"
        self.pending_dir.mkdir(parents=True)
        self.pending_dir.chmod(0o700)
        self.fakes = tmp / "fakes"
        self.fakes.mkdir()
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.rec = self.offers / UUID
        self.out = Path(f"{self.rec}.bind.1.out")
        self.pending = self.pending_dir / DIGEST
        self.script = self.bin / "lanes-edit.sh"
        shutil.copy2(SCRIPT, self.script)
        self.script.chmod(0o755)
        index = self.bin / "lanes-index"
        index.write_text(
            "#!/bin/bash\n"
            "printf 'ERROR:  LR007: another-write\\nDETAIL:  another-write\\n' >&2\nexit 2\n")
        index.chmod(0o755)
        self.lane_start_called = tmp / "lane-start-called"
        lane_start = self.bin / "lane-start"
        lane_start.write_text(f"#!/bin/bash\n: > {q(self.lane_start_called)}\nexit 99\n")
        lane_start.chmod(0o755)
        self._record()
        self._pending()

    def _record(self) -> None:
        keys = {
            "mode": "binding", "from": "repoA-2", "to": "repoA-3", "session": "repoA-3",
            "uuid": UUID, "window": "@1", "pane": "%1", "utc": "2026-11-14T00:00:00Z",
            "bind": "1", "started_utc": "2026-11-14T00:00:00Z", "bound_s": "500",
            "bounded": "yes", "deadline_epoch": str(int(time.time()) + 505),
            "host": HOST, "container": CONTAINER, "out": str(self.out), "detach": "setsid",
            "write_id": WRITE_ID, "generation": GENERATION, "not_after": "1794700000",
            "write_lane": "repoA-2", "args_sha256": DIGEST, "ended_utc": "2026-01-01T00:00:00Z",
        }
        self.rec.write_text("".join(f"{k}={v}\n" for k, v in keys.items()))
        os.chmod(self.rec, 0o600)

    def _pending(self) -> None:
        call = f"1 0 1794700000 {FILES} {self.state}/openRepoTools/register-writes/{DIGEST}/r/c"
        self.pending.write_text("".join(f"{line}\n" for line in [
            "format=1", f"write_id={WRITE_ID}", f"generation={GENERATION}", "lane=repoA-2",
            f"session={UUID}", "verb=start-record", f"args_sha256={DIGEST}",
            "cmdline=lanes-edit.sh start-record repoA-3", "created_utc=2026-11-14T00:00:00Z",
            "updated_utc=2026-11-14T00:00:01Z", "pid=999999", f"host={HOST}",
            f"container={CONTAINER}", "attempts=1", f"call={call}"]))
        os.chmod(self.pending, 0o600)

    def refuse_the_pending_record_to_rm(self) -> None:
        """Make `guard_bind_settle` fail: a stand-in `rm` that refuses the
        pending record and runs the real `rm` for every other call."""
        real = shutil.which("rm", path=BASE_PATH)
        assert real
        tool = self.fakes / "rm"
        tool.write_text(
            "#!/bin/bash\n"
            'for a in "$@"; do\n'
            f"  case \"$a\" in */register-pending/{DIGEST}) exit 1 ;; esac\n"
            "done\n"
            f"exec {q(real)} \"$@\"\n")
        tool.chmod(0o755)

    @staticmethod
    def read(path: Path) -> dict:
        got: dict = {}
        for line in path.read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                got.setdefault(key, value)
        return got

    def env(self) -> dict:
        return {
            "HOME": str(self.home), "PATH": f"{self.fakes}:{BASE_PATH}", "TMPDIR": str(self.tmp),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "cfg"), "XDG_STATE_HOME": str(self.state),
            "LANES_WORKSTATION": HOST, "LANES_CONTAINER": CONTAINER, "LANES_HOST": HOST,
            "LANES_IN_CONTAINER": "0", "LANES_LANE_START": str(self.bin / "lane-start"),
            "LANES_BIND_BOUND_S": "60", "LC_ALL": "C",
        }

    def outer(self):
        """The REAL outer, which runs the REAL body: `guard-bind <uuid>`, its
        stdout and stderr in the attempt's `.out`, as the hook's fork gives
        them."""
        with open(self.out, "ab") as fh:
            proc = subprocess.run(["bash", str(self.script), "guard-bind", UUID],
                                  env=self.env(), stdin=subprocess.DEVNULL, stdout=fh,
                                  stderr=subprocess.STDOUT, timeout=120)
        return proc.returncode, self.out.read_text(errors="replace")


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def test_t502r3_s3_a_failed_settle_does_not_say_the_pending_record_is_removed(box):
    """RED at `12eddddf`: after a settle that fails, the pending record is
    still there and its copies are in the outcome (lane 3's ruling), but the
    diagnostic said the record was removed."""
    box.refuse_the_pending_record_to_rm()
    rc, said = box.outer()
    rec = box.read(box.rec)
    why = rec.get("why", "")
    # THE BEHAVIOUR STANDS: the body's 2 is the outcome's rc, the outer's exit is 0,
    # the pending record is kept, and its copies are in the outcome.
    assert rc == 0, said
    assert not box.lane_start_called.exists(), said
    assert rec.get("mode") == "bind-failed" and rec.get("rc") == "2", (rec, said)
    assert box.pending.exists(), said
    assert rec.get("write_id") == WRITE_ID and rec.get("args_sha256") == DIGEST, (rec, said)
    # THE DIAGNOSTIC SAYS WHAT HAPPENED: it does not claim the removal, in the
    # outcome or in the attempt's output, and it says the record was not
    # settled and is kept.
    assert REMOVED not in why, why
    assert REMOVED not in said, said
    assert KEPT in why, why


def test_t502r3_s3_control_a_successful_settle_removes_the_record_and_says_so(box):
    """CONTROL, passing at both: after a settle that succeeds the pending
    record and the copies are gone, and the diagnostic says the record was
    removed."""
    rc, said = box.outer()
    rec = box.read(box.rec)
    why = rec.get("why", "")
    assert rc == 0, said
    assert not box.lane_start_called.exists(), said
    assert rec.get("mode") == "bind-failed" and rec.get("rc") == "2", (rec, said)
    assert not box.pending.exists(), said
    assert "write_id" not in rec and "args_sha256" not in rec, (rec, said)
    assert f"{REMOVED}, and the next `2` binds anew" in why, why
    assert "could not be settled" not in why, why
