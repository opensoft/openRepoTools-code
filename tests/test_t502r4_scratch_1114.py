# SPDX-License-Identifier: Apache-2.0
"""SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's round 4, parts
16 to 19 (`l5/007-T502-followup-1925`): lane 3's Codex code review of
`12eddddf` (report lane5-code-12eddddf-88b50886.md, sha256 caa3641e;
opensoft/openRepoTools#165 6882203066; lane 3's routing, not Brett's).
Findings 1 and 4 are behaviour, 8 and 10 the NITs; finding 5 is part 14's,
proved in `tests/test_t502r3_scratch_1114.py`. This file lives only on the
branch `scratch/t502r3-proof`; the bash form is `scratch/t502r4-proof-1114.sh`.

Every case runs a TEST-ONLY COPY of the tree's `lanes-edit.sh` (lane 3's point
23: no seam in the shipped script), with three hooks, each anchored on one line
that every version has once:

* the `guard-bind` arm answers `guard-bind --t502r4-rewrite <args>` with
  `guard_bind_rewrite <args>` and its code, and `--t502r4-index-ok <n>` with
  `guard_bind_index_ok`;
* a `printf` function in front of `guard_bind_rewrite` fails the
  `T502R4_FAIL_PRINTF_N`th call made from `guard_bind_rewrite` (only from its
  `--own` call where `T502R4_ONLY_OWN=1`) and runs the builtin for every other,
  so one write fails while the later ones succeed, as in the review's probe;
* the line after the rewrite's `-e` test moves the record away where
  `T502R4_VANISH` says (`any`, or `own` for a `--own` call only): the record
  that goes between the test and the open.

HERMETIC, as the round 3 fix made the S3 cases: PATH is /usr/bin:/bin only,
and `LANES_HOST` and `LANES_IN_CONTAINER=0` are pinned.
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
NOT_OWN = "is no longer this bind's own"

GB_ARM = "  guard-bind)\n"
REWRITE_HEAD = "\nguard_bind_rewrite() {"
EXISTS_TEST = '      if [ -e "$gbw_f" ]; then\n'

HOOK_ARM = (
    '    if [ "${1-}" = --t502r4-rewrite ]; then shift; guard_bind_rewrite "$@"; '
    'echo "rewrite-rc=$?"; exit 0; fi\n'
    '    if [ "${1-}" = --t502r4-index-ok ]; then if guard_bind_index_ok "${2-}"; '
    'then echo ok; else echo refused; fi; exit 0; fi\n')
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


def q(value) -> str:
    return shlex.quote(str(value))


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
        self.out = Path(f"{self.rec}.bind.1.out")
        self.facts = Path(f"{self.rec}.bind.1.facts")
        self.stub = tmp / "stub-body"
        self.rec4 = tmp / "rec4"
        text = SCRIPT.read_text()
        assert text.count(GB_ARM) == 1 and text.count(REWRITE_HEAD) == 1
        assert text.count(EXISTS_TEST) == 1
        text = text.replace(GB_ARM, GB_ARM + HOOK_ARM)
        text = text.replace(REWRITE_HEAD, "\n" + HOOK_PRINTF + REWRITE_HEAD[1:])
        text = text.replace(EXISTS_TEST, EXISTS_TEST + HOOK_VANISH)
        self.script = tmp / "lanes-edit-r4.sh"
        self.script.write_text(text)
        self.script.chmod(0o755)

    # ---- the direct cases' record
    def rec4_lines(self, text: str = "mode=binding\nkeep1=a\nkeep2=b\nkeep3=c\n") -> str:
        self.rec4.write_text(text)
        return text

    def temps(self) -> list:
        return sorted(p.name for p in self.tmp.iterdir() if p.name.startswith(".rec4."))

    def env(self, **extra) -> dict:
        env = {
            "HOME": str(self.home), "PATH": BASE_PATH, "TMPDIR": str(self.tmp),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "cfg"), "XDG_STATE_HOME": str(self.state),
            "LANES_WORKSTATION": HOST, "LANES_CONTAINER": CONTAINER, "LANES_HOST": HOST,
            "LANES_IN_CONTAINER": "0", "LANES_BIND_BOUND_S": "15", "LC_ALL": "C",
        }
        env.update(extra)
        return env

    def rewrite(self, *args, **extra) -> int:
        """`guard_bind_rewrite <args>` through the copy's hook: its code."""
        got = subprocess.run(["bash", str(self.script), "guard-bind", "--t502r4-rewrite", *args],
                             env=self.env(**extra), stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=60)
        last = got.stdout.strip().splitlines()[-1] if got.stdout.strip() else ""
        assert last.startswith("rewrite-rc="), (got.stdout, got.stderr[-2000:])
        return int(last[len("rewrite-rc="):])

    # ---- the outer's cases' record and stand-in body
    def record(self) -> None:
        keys = {
            "mode": "binding", "from": "repoA-2", "to": "repoA-3", "session": "repoA-3",
            "uuid": UUID, "window": "@1", "pane": "%1", "utc": "2026-11-14T00:00:00Z",
            "bind": "1", "started_utc": "2026-11-14T00:00:00Z", "bound_s": "500",
            "bounded": "yes", "deadline_epoch": str(int(time.time()) + 505),
            "host": HOST, "container": CONTAINER, "out": str(self.out), "detach": "setsid",
        }
        self.rec.write_text("".join(f"{k}={v}\n" for k, v in keys.items()))
        os.chmod(self.rec, 0o600)
        self.stub.write_text(
            "#!/bin/bash\n"
            '[ -z "${LANES_BIND_FACTS:-}" ] || printf %s \'\' > "$LANES_BIND_FACTS"\n'
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


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# ---- FINDING 1: a write that fails is a 1, wherever it is, and the record is
# left alone. The review's probe: only the FIRST output printf fails.

@pytest.mark.parametrize("n", [1, 3], ids=["first", "a-copied-line"])
def test_t502r4_f1_a_failed_write_is_result_1_and_the_record_is_unchanged(box, n):
    was = box.rec4_lines()
    code = box.rewrite(str(box.rec4), "mode rc", "mode=bound", "rc=0", T502R4_FAIL_PRINTF_N=str(n))
    assert code == 1
    assert box.rec4.read_text() == was
    assert box.temps() == []


def test_t502r4_f1_control_the_last_write_failing_is_result_1(box):
    was = box.rec4_lines()
    code = box.rewrite(str(box.rec4), "mode rc", "mode=bound", "rc=0", T502R4_FAIL_PRINTF_N="5")
    assert code == 1
    assert box.rec4.read_text() == was
    assert box.temps() == []


def test_t502r4_f1_control_no_failure_written_as_ever(box):
    box.rec4_lines()
    assert box.rewrite(str(box.rec4), "mode rc", "mode=bound", "rc=0") == 0
    assert box.rec4.read_text() == "mode=bound\nkeep1=a\nkeep2=b\nkeep3=c\nrc=0\n"
    assert box.temps() == []


@pytest.mark.parametrize("have, want", [
    ("mode=binding\nkeep1=a\nkeep2=b\nkeep3=c", "mode=bound\nkeep1=a\nkeep2=b\nkeep3=c\nrc=0\n"),
    ("mode=binding\n\nkeep1=a\n", "mode=bound\n\nkeep1=a\nrc=0\n"),
    ("mode=binding\nnoequals\nkeep1=a\n", "mode=bound\nnoequals\nkeep1=a\nrc=0\n"),
], ids=["nofinalnl", "blank", "noequals"])
def test_t502r4_f1_control_an_odd_record_is_rewritten_as_ever(box, have, want):
    box.rec4_lines(have)
    assert box.rewrite(str(box.rec4), "mode rc", "mode=bound", "rc=0") == 0
    assert box.rec4.read_text() == want


# ---- FINDING 4: under `--own`, a record that goes between the `-e` and the
# open is a 2, nothing written and nothing made; where it is still there and
# cannot be read it is a 1; without `--own` it stays a 1.

def test_t502r4_f2_an_own_record_gone_at_the_open_is_result_2_and_nothing_is_made(box):
    was = box.rec4_lines()
    code = box.rewrite("--own", str(box.rec4), "mode rc", "mode=bound", "rc=0", T502R4_VANISH="own")
    assert code == 2
    assert not box.rec4.exists()
    assert Path(f"{box.rec4}.gone").read_text() == was
    assert box.temps() == []


def test_t502r4_f2_control_without_own_a_record_gone_at_the_open_stays_result_1(box):
    box.rec4_lines()
    code = box.rewrite(str(box.rec4), "mode rc", "mode=bound", "rc=0", T502R4_VANISH="any")
    assert code == 1
    assert not box.rec4.exists()
    assert box.temps() == []


def test_t502r4_f2_control_an_own_record_absent_from_the_start_is_result_2(box):
    assert box.rewrite("--own", str(box.rec4), "mode rc", "mode=bound", "rc=0") == 2
    assert not box.rec4.exists()
    assert box.temps() == []


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any file")
def test_t502r4_f2_control_an_own_record_there_but_unreadable_is_result_1(box):
    was = box.rec4_lines()
    box.rec4.chmod(0)
    try:
        code = box.rewrite("--own", str(box.rec4), "mode rc", "mode=bound", "rc=0")
    finally:
        box.rec4.chmod(0o600)
    assert code == 1
    assert box.rec4.read_text() == was
    assert box.temps() == []


# ---- THE SAME TWO, THROUGH THE REAL OUTER with a stand-in body.

def test_t502r4_f1_outer_a_failed_write_is_exit_1_with_the_record_still_binding(box):
    box.record()
    rc, said = box.outer(T502R4_FAIL_PRINTF_N="3", T502R4_ONLY_OWN="1")
    rec = box.read(box.rec)
    assert rc == 1, said
    assert rec.get("mode") == "binding" and "pid" in rec, (rec, said)
    assert "rc" not in rec and "ended_utc" not in rec, (rec, said)
    assert not box.facts.exists(), said
    assert "the outcome could not be written" in said, said


def test_t502r4_f2_outer_a_record_gone_at_the_open_is_exit_0(box):
    box.record()
    rc, said = box.outer(T502R4_VANISH="own")
    assert rc == 0, said
    assert not box.rec.exists(), box.rec.read_text()
    assert box.read(Path(f"{box.rec}.gone")).get("mode") == "binding"
    assert not box.facts.exists(), said
    assert box.offer_temps() == [], box.offer_temps()
    assert NOT_OWN in said, said


# ---- FINDING 8 (NIT): the three comments no longer promise a record "as it
# was" or a change "after this read" left alone.

def _flat(text: str) -> str:
    return " ".join(line.lstrip().lstrip("#").strip() for line in text.splitlines())


def test_t502r4_nit8_the_comments_say_the_rewrite_did_not_change_the_record():
    text = SCRIPT.read_text()
    start = text.index("# WITH `--own`, THE OUTER")
    header = _flat(text[start:text.index("\nguard_bind_rewrite() {", start)])
    start = text.index("  # THE WINDOW IS KEPT, AND NARROWED IN CODE")
    window = _flat(text[start:text.index("\n  gbo_wrc=2\n", start)])
    assert "and the record is as it was" not in header, header
    assert "as another writer may have left it" in header, header
    assert "can still be overwritten" in header, header
    assert "a record changed after this read is still left as it is" not in window, window
    assert "can still be overwritten" in window, window
    assert "nothing written by this rewrite" in window, window


# ---- FINDING 10 (NIT): the index predicate spells its digits out; and it is
# the same predicate (a control through the hook).

def test_t502r4_nit10_the_index_predicate_spells_its_digits_out():
    text = SCRIPT.read_text()
    start = text.index("guard_bind_index_ok() {")
    body = text[start:text.index("\n}\n", start)]
    assert "[!0123456789]" in body, body
    assert "[!0-9]" not in body, body


@pytest.mark.parametrize("value, want", [
    ("1", "ok"), ("10", "ok"), ("123", "ok"), ("0", "refused"), ("01", "refused"),
    ("1a", "refused"), ("", "refused"), ("-1", "refused")])
def test_t502r4_nit10_control_the_index_predicate_answers_as_ever(box, value, want):
    got = subprocess.run(["bash", str(box.script), "guard-bind", "--t502r4-index-ok", value],
                         env=box.env(), stdin=subprocess.DEVNULL, capture_output=True,
                         text=True, timeout=60)
    assert got.stdout.strip() == want, (got.stdout, got.stderr[-2000:])
