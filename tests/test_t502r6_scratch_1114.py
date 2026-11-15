# SPDX-License-Identifier: Apache-2.0
"""SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's part 21
(`l5/007-T502-followup-1925`): the outer's start rewrite runs only on a record
that still says `mode=binding`, and where it does not the outer runs nothing
and returns 2 (lane 5's ruling on lane 2's reader's window, opensoft/
openRepoTools#165 6885568373; lane 3's ruling on open point 26, #165
6885378657, as lane 5's brief gives it: `guard_offer`'s write is the record's
only creation, so a rewrite never makes one). This file lives only on the
branch `scratch/t502r3-proof`; the bash form is `scratch/t502r6-proof-1114.sh`.

Every case runs a TEST-ONLY COPY of the tree's `lanes-edit.sh` (lane 3's point
23: no seam in the shipped script), with the hooks of `test_t502r4_scratch_1114`
(a rewrite hook in the `guard-bind` arm, a `printf` function that fails the
Nth write, and a move of the record between the rewrite's `-e` test and its
open) and one more, in the outer, on the line after its `gbo_ep=`, which is
after its load and before its start rewrite's existence test. It stands where
a hold would: `T502R6_START=gone` moves the record away there, and
`T502R6_START=drift` replaces it with a `name-drift` offer, once and
synchronously; the outer then goes on to its start rewrite.

HERMETIC, as the part 15 proof is: PATH is /usr/bin:/bin only, and
`LANES_HOST` and `LANES_IN_CONTAINER=0` are pinned.
"""

from __future__ import annotations

import os
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
NOTE = "is gone or no longer says mode=binding"
START = "2026-11-14T00:00:00Z"

GB_ARM = "  guard-bind)\n"
REWRITE_HEAD = "\nguard_bind_rewrite() {"
EXISTS_TEST = '      if [ -e "$gbw_f" ]; then\n'
GBO_EP = '  gbo_ep="${gbo_now%% *}"\n'

HOOK_ARM = (
    '    if [ "${1-}" = --t502r4-rewrite ]; then shift; guard_bind_rewrite "$@"; '
    'echo "rewrite-rc=$?"; exit 0; fi\n')
HOOK_PRINTF = (
    'printf() {\n'
    '  if [ -n "${T502R4_FAIL_PRINTF_N:-}" ] && [ "${FUNCNAME[1]-}" = guard_bind_rewrite ] &&\n'
    '     { [ "${T502R4_ONLY_OWN:-}" != 1 ] || [ "${gbw_own-}" = 1 ]; }; then\n'
    '    T502R4_N=$(( ${T502R4_N:-0} + 1 ))\n'
    '    [ "$T502R4_N" != "$T502R4_FAIL_PRINTF_N" ] || return 1\n'
    '  fi\n'
    '  builtin printf "$@"\n'
    '}\n')
HOOK_VANISH = ('        case "${T502R4_VANISH:-}:${gbw_own-}" in '
               'any:*|own:1) mv -f -- "$gbw_f" "$gbw_f.gone" ;; esac\n')
HOOK_START = (
    '  case "${T502R6_START:-}" in\n'
    '    gone) mv -f -- "$gbo_f" "$gbo_f.gone" ;;\n'
    '    drift) printf "%s\\n" mode=name-drift from=repoA-2 to=repoA-3 session=repoA-3 '
    '"uuid=$gbo_u" window=@1 pane=%1 > "$gbo_f" ;;\n'
    '  esac\n')

OFFER = "".join(f"{line}\n" for line in [
    "mode=name-drift", "from=repoA-2", "to=repoA-3", "session=repoA-3", f"uuid={UUID}",
    "window=@1", "pane=%1"])


class Box:
    """One sandbox: `$HOME`, `$CLAUDE_CONFIG_DIR` with `lanes/offers/`, a state
    home, and the test-only copy of the script under test."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.offers = tmp / "cfg" / "lanes" / "offers"
        self.offers.mkdir(parents=True)
        self.state = tmp / "state"
        self.state.mkdir()
        self.rec = self.offers / UUID
        self.gone = Path(f"{self.rec}.gone")
        self.out = Path(f"{self.rec}.bind.1.out")
        self.facts = Path(f"{self.rec}.bind.1.facts")
        self.stub = tmp / "stub-body"
        self.trigger = tmp / "body-ran"
        self.rec4 = tmp / "rec4"
        text = SCRIPT.read_text()
        for anchor in (GB_ARM, REWRITE_HEAD, EXISTS_TEST, GBO_EP):
            assert text.count(anchor) == 1, anchor
        text = text.replace(GB_ARM, GB_ARM + HOOK_ARM)
        text = text.replace(REWRITE_HEAD, "\n" + HOOK_PRINTF + REWRITE_HEAD[1:])
        text = text.replace(EXISTS_TEST, EXISTS_TEST + HOOK_VANISH)
        text = text.replace(GBO_EP, GBO_EP + HOOK_START)
        self.script = tmp / "lanes-edit-r6.sh"
        self.script.write_text(text)
        self.script.chmod(0o755)

    # ---- the outer's cases: the record, the stand-in body, the outer
    def record(self) -> None:
        keys = {
            "mode": "binding", "from": "repoA-2", "to": "repoA-3", "session": "repoA-3",
            "uuid": UUID, "window": "@1", "pane": "%1", "utc": START,
            "bind": "1", "started_utc": START, "bound_s": "500",
            "bounded": "yes", "deadline_epoch": str(int(time.time()) + 505),
            "host": HOST, "container": CONTAINER, "out": str(self.out), "detach": "setsid",
        }
        self.rec.write_text("".join(f"{k}={v}\n" for k, v in keys.items()))
        os.chmod(self.rec, 0o600)
        self.stub.write_text(
            "#!/bin/bash\n"
            '[ -z "${LANES_BIND_FACTS:-}" ] || printf %s \'\' > "$LANES_BIND_FACTS"\n'
            f": > '{self.trigger}'\n"
            "exit 0\n")
        self.stub.chmod(0o755)

    @staticmethod
    def read(path: Path) -> dict:
        got: dict = {}
        for line in path.read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                got.setdefault(key, value)
        return got

    def env(self, **extra) -> dict:
        env = {
            "HOME": str(self.home), "PATH": BASE_PATH, "TMPDIR": str(self.tmp),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "cfg"), "XDG_STATE_HOME": str(self.state),
            "LANES_WORKSTATION": HOST, "LANES_CONTAINER": CONTAINER, "LANES_HOST": HOST,
            "LANES_IN_CONTAINER": "0", "LANES_BIND_BOUND_S": "15", "LC_ALL": "C",
        }
        env.update(extra)
        return env

    def outer(self, **extra):
        """The REAL outer with the stand-in body: `guard-bind <uuid>`, its stdout
        and stderr in the attempt's `.out`, as the hook's fork gives them."""
        with open(self.out, "ab") as fh:
            proc = subprocess.run(["bash", str(self.script), "guard-bind", UUID],
                                  env=self.env(LANES_BIND_BODY=str(self.stub), **extra),
                                  stdin=subprocess.DEVNULL, stdout=fh,
                                  stderr=subprocess.STDOUT, timeout=60)
        return proc.returncode, self.out.read_text(errors="replace")

    def offer_temps(self) -> list:
        return sorted(p.name for p in self.offers.iterdir() if p.name.startswith(f".{UUID}."))

    def nothing_else(self, said: str) -> None:
        """What is left where the outer's start finds its record gone or no
        longer binding: no temporary file, the body never run, no facts file,
        and in the attempt's `.out` the outer's one note and nothing else (it
        writes nothing there before its start rewrite)."""
        assert self.offer_temps() == [], self.offer_temps()
        assert not self.trigger.exists(), "the bind body ran"
        assert not self.facts.exists()
        assert said.count("\n") == 1, said
        assert NOTE in said, said
        assert "attempt 1 for transcript" not in said, said

    # ---- the rewrite's own flag, direct, through the hook
    def rec4_lines(self, *lines: str) -> str:
        text = "".join(f"{line}\n" for line in lines)
        self.rec4.write_text(text)
        return text

    def rec4_temps(self) -> list:
        return sorted(p.name for p in self.tmp.iterdir() if p.name.startswith(".rec4."))

    def rewrite(self, *args, **extra) -> int:
        got = subprocess.run(["bash", str(self.script), "guard-bind", "--t502r4-rewrite", *args],
                             env=self.env(**extra), stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=60)
        last = got.stdout.strip().splitlines()[-1] if got.stdout.strip() else ""
        assert last.startswith("rewrite-rc="), (got.stdout, got.stderr[-2000:])
        return int(last[len("rewrite-rc="):])


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# ---- THE OUTER'S START, through the real outer with a stand-in body.

def test_t502r6_gone_before_its_start_the_outer_exits_2_makes_no_record_and_runs_no_bind(box):
    box.record()
    was = box.rec.read_text()
    rc, said = box.outer(T502R6_START="gone")
    assert rc == 2, said
    assert not box.rec.exists(), box.rec.read_text() if box.rec.exists() else ""
    assert box.gone.read_text() == was
    box.nothing_else(said)


def test_t502r6_no_longer_binding_at_its_start_the_outer_exits_2_leaves_the_offer_and_runs_no_bind(box):
    box.record()
    rc, said = box.outer(T502R6_START="drift")
    assert rc == 2, said
    assert box.rec.read_text() == OFFER, box.rec.read_text()
    box.nothing_else(said)


def test_t502r6_gone_at_the_open_of_its_start_the_outer_exits_2_makes_no_record_and_runs_no_bind(box):
    box.record()
    was = box.rec.read_text()
    rc, said = box.outer(T502R4_VANISH="any")
    assert rc == 2, said
    assert not box.rec.exists()
    assert box.gone.read_text() == was
    box.nothing_else(said)


def test_t502r6_control_an_ordinary_start_writes_its_six_keys_and_the_bind_runs(box):
    box.record()
    rc, said = box.outer()
    rec = box.read(box.rec)
    assert rc == 0, said
    assert rec.get("mode") == "bound" and rec.get("rc") == "0", (rec, said)
    for key in ("started_utc", "bound_s", "bounded", "deadline_epoch", "pid", "pidstart"):
        assert key in rec, (key, rec)
    assert box.trigger.exists(), said
    assert "attempt 1 for transcript" in said, said


# ---- THE REWRITE'S OWN FLAG, DIRECT.

ARGS = ["pid pidstart", f"started_utc={START}", "pid=1234"]


def test_t502r6_flag_binding_on_a_binding_record_writes_and_returns_0(box):
    box.rec4_lines("mode=binding", "keep=a")
    assert box.rewrite("--binding", str(box.rec4), *ARGS) == 0
    assert box.rec4.read_text() == f"mode=binding\nkeep=a\nstarted_utc={START}\npid=1234\n"
    assert box.rec4_temps() == []


@pytest.mark.parametrize("lines", [["mode=name-drift", "keep=a"], ["keep=a", "other=b"]],
                         ids=["name-drift", "no-mode"])
def test_t502r6_flag_binding_on_a_record_that_is_not_binding_returns_2_unchanged(box, lines):
    was = box.rec4_lines(*lines)
    assert box.rewrite("--binding", str(box.rec4), *ARGS) == 2
    assert box.rec4.read_text() == was
    assert box.rec4_temps() == []


def test_t502r6_flag_binding_reads_the_first_mode_line_as_the_loader_does(box):
    was = box.rec4_lines("mode=name-drift", "mode=binding")
    assert box.rewrite("--binding", str(box.rec4), "pid pidstart", "pid=1234") == 2
    assert box.rec4.read_text() == was
    box.rec4_lines("mode=binding", "mode=name-drift")
    assert box.rewrite("--binding", str(box.rec4), "pid pidstart", "pid=1234") == 0


def test_t502r6_flag_binding_on_an_absent_record_returns_2_and_makes_nothing(box):
    assert box.rewrite("--binding", str(box.rec4), *ARGS) == 2
    assert not box.rec4.exists()
    assert box.rec4_temps() == []


def test_t502r6_flag_binding_record_gone_at_the_open_returns_2(box):
    box.rec4_lines("mode=binding", "keep=a")
    assert box.rewrite("--binding", str(box.rec4), *ARGS, T502R4_VANISH="any") == 2
    assert not box.rec4.exists()
    assert box.rec4_temps() == []


def test_t502r6_flag_binding_a_failed_write_returns_1_unchanged(box):
    was = box.rec4_lines("mode=binding", "keep=a")
    assert box.rewrite("--binding", str(box.rec4), *ARGS, T502R4_FAIL_PRINTF_N="2") == 1
    assert box.rec4.read_text() == was
    assert box.rec4_temps() == []


def test_t502r6_control_no_flag_rewrites_a_name_drift_record_as_ever(box):
    box.rec4_lines("mode=name-drift", "keep=a")
    assert box.rewrite(str(box.rec4), *ARGS) == 0
    assert box.rec4.read_text() == f"mode=name-drift\nkeep=a\nstarted_utc={START}\npid=1234\n"
