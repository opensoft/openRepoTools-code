# SPDX-License-Identifier: Apache-2.0
"""SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's part 20
(`l5/007-T502-followup-1925`): choice 1's `mode=allow` record checks every write
before its `mv`, as part 16 made `guard_bind_rewrite` do (Codex finding 1 of
lane 3's code review of `12eddddf`, opensoft/openRepoTools#165 6882203066;
T501's check of draft 15 against parts 16 to 19, whose :114 was false for this
one writer). This file lives only on the branch `scratch/t502r3-proof`; the
bash form is `scratch/t502r5-proof-1114.sh`.

The answer 1 runs through a TEST-ONLY COPY of the tree's `lanes-edit.sh` (lane
3's point 23: no seam in the shipped script), with two hooks, each anchored on
one line every version has once:

* the `guard-bind` arm answers `guard-bind --t502r5-answer <uuid> <lane>
  <session name> <offer file>` by setting the guard's `G_ID`, `G_LANE` and
  `G_NAME` and calling `guard_answer <offer file> 1 %1`, the very function the
  hook's answer reaches, and printing its code;
* a `printf` function in front of `guard_answer` fails the
  `T502R5_FAIL_PRINTF_N`th call it makes with a record line's format (one with
  an `=`), so one write to the temporary file fails while the later ones
  succeed, as part 16's proof does for the rewrite.

HERMETIC, as the part 15 proof is: PATH is the box's stand-ins first and then
/usr/bin:/bin only, and `LANES_HOST` and `LANES_IN_CONTAINER=0` are pinned.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or not Path("/proc/self/stat").exists(),
    reason="the guard's helpers read /proc")]

SCRIPT = REPO / "lanes-edit.sh"
UUID = "aaaa1111-2222-3333-4444-555566667777"
HOST = "Eagle"
CONTAINER = "g-box"
BASE_PATH = "/usr/bin:/bin"   # nothing installed under /usr/local/bin is ever reached
REFUSED = "the explicit allow could not be recorded"

GB_ARM = "  guard-bind)\n"
GA_HEAD = "\nguard_answer() {"

HOOK_ARM = ('    if [ "${1-}" = --t502r5-answer ]; then G_ID="$2"; G_LANE="$3"; G_NAME="$4"; '
            'guard_answer "$5" 1 "%1"; echo "answer-rc=$?"; exit 0; fi\n')
HOOK_PRINTF = (
    'printf() {\n'
    '  if [ -n "${T502R5_FAIL_PRINTF_N:-}" ] && [ "${FUNCNAME[1]-}" = guard_answer ]; then\n'
    '    case "${1-}" in\n'
    '      *=*)\n'
    '        T502R5_N=$(( ${T502R5_N:-0} + 1 ))\n'
    '        [ "$T502R5_N" != "$T502R5_FAIL_PRINTF_N" ] || return 1 ;;\n'
    '    esac\n'
    '  fi\n'
    '  builtin printf "$@"\n'
    '}\n')


class Box:
    """One sandbox: `$HOME`, `$CLAUDE_CONFIG_DIR` with `lanes/offers/` holding the
    pending offer and the bind's output file beside it, a state home, a
    directory of stand-ins first on PATH, and the test-only copy."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.offers = tmp / "cfg" / "lanes" / "offers"
        self.offers.mkdir(parents=True)
        self.state = tmp / "state"
        self.state.mkdir()
        self.fakes = tmp / "fakes"
        self.fakes.mkdir()
        self.rec = self.offers / UUID
        self.bind_out = Path(f"{self.rec}.bind.1.out")
        text = SCRIPT.read_text()
        assert text.count(GB_ARM) == 1 and text.count(GA_HEAD) == 1
        text = text.replace(GB_ARM, GB_ARM + HOOK_ARM)
        text = text.replace(GA_HEAD, "\n" + HOOK_PRINTF + GA_HEAD[1:])
        self.script = tmp / "lanes-edit-r5.sh"
        self.script.write_text(text)
        self.script.chmod(0o755)
        # the pending offer the person answers: name-drift, the bind's output beside it
        self.was = "".join(f"{line}\n" for line in [
            "mode=name-drift", "from=repoA-2", "to=repoA-3", "session=repoA-3", f"uuid={UUID}",
            "utc=2026-11-14T00:00:00Z", "window=@1", "pane=%1"])
        self.rec.write_text(self.was)
        os.chmod(self.rec, 0o600)
        self.bind_out.write_text("an attempt before\n")

    def stand_in(self, name: str) -> None:
        """A `name` first on PATH that fails."""
        tool = self.fakes / name
        tool.write_text("#!/bin/bash\nexit 1\n")
        tool.chmod(0o755)

    def temps(self) -> list:
        return sorted(p.name for p in self.offers.iterdir() if p.name.startswith(f".{UUID}."))

    def env(self, **extra) -> dict:
        env = {
            "HOME": str(self.home), "PATH": f"{self.fakes}:{BASE_PATH}", "TMPDIR": str(self.tmp),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "cfg"), "XDG_STATE_HOME": str(self.state),
            "LANES_WORKSTATION": HOST, "LANES_CONTAINER": CONTAINER, "LANES_HOST": HOST,
            "LANES_IN_CONTAINER": "0", "LC_ALL": "C",
        }
        env.update(extra)
        return env

    def answer(self, **extra):
        """The answer 1, through `guard_answer`: its code and its stderr."""
        got = subprocess.run(
            ["bash", str(self.script), "guard-bind", "--t502r5-answer", UUID, "repoA-2",
             "repoA-3", str(self.rec)],
            env=self.env(**extra), stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=60)
        last = got.stdout.strip().splitlines()[-1] if got.stdout.strip() else ""
        assert last.startswith("answer-rc="), (got.stdout, got.stderr[-2000:])
        return int(last[len("answer-rc="):]), got.stderr

    def refused_and_unchanged(self, code: int, err: str) -> None:
        """The guard's refusal with its 2, the record as this answer found it, the
        temporary file gone, and the offer's `.bind.*` files kept."""
        assert code == 2, err
        assert REFUSED in err, err
        assert "ALLOWED:" not in err, err
        assert self.rec.read_text() == self.was
        assert self.temps() == []
        assert self.bind_out.exists()


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


@pytest.mark.parametrize("n", [1, 3], ids=["first", "a-middle-line"])
def test_t502r5_choice_1_a_failed_early_write_is_refused_and_the_record_is_unchanged(box, n):
    """RED at `a6ee7c0b`: the failed write is hidden by the later ones, the `mv`
    runs, and the record is moved into place without that line."""
    code, err = box.answer(T502R5_FAIL_PRINTF_N=str(n))
    box.refused_and_unchanged(code, err)


def test_t502r5_choice_1_control_the_last_write_failing_is_refused(box):
    code, err = box.answer(T502R5_FAIL_PRINTF_N="6")
    box.refused_and_unchanged(code, err)


@pytest.mark.parametrize("tool", ["mktemp", "mv"])
def test_t502r5_choice_1_control_a_failed_mktemp_or_mv_is_refused(box, tool):
    box.stand_in(tool)
    code, err = box.answer()
    box.refused_and_unchanged(code, err)


def test_t502r5_choice_1_control_an_answer_writes_all_six_lines_and_moves_them_into_place(box):
    code, err = box.answer()
    lines = box.rec.read_text().splitlines()
    assert code == 2, err
    assert "ALLOWED: this lane/session name mismatch is explicitly allowed" in err, err
    assert lines[:5] == ["mode=allow", "from=repoA-2", "to=repoA-3", "session=repoA-3",
                         f"uuid={UUID}"], lines
    assert len(lines) == 6 and lines[5].startswith("utc=") and lines[5].endswith("Z"), lines
    assert not box.bind_out.exists()
    assert box.temps() == []
