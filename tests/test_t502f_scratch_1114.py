# SPDX-License-Identifier: Apache-2.0
"""SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's follow-up
round (`l5/007-T502-followup-1925`), on lane 3's rulings on spec#47's points
20, 21 and 25, and on the two exit comments those rulings route to the round
(opensoft/openRepoTools#165 comment 6879754335; lane 3's rulings, never
Brett's). The contract is T501's `bind-record.md`, draft 11 at `a2e0e3e6`.
Lane 2 writes the permanent AT-F6 cases; this file lives only on the branch
`scratch/t502f-proof`.

Each case runs the tree's `lanes-edit.sh` on a record written directly, with a
stand-in body through `LANES_BIND_BODY` (R48), or runs the real body with a
stand-in `lane-start` (`LANES_LANE_START`). Where the outer's own
`pid_start_of $$` must exit 2, the case runs a TEST-ONLY COPY of
`lanes-edit.sh` whose `pid_start_of` answers 2 for the caller's own pid, as
lane 3's point 23 says: no seam goes into the shipped script.

A change inside the outer's window is made by a stand-in `awk` or `mktemp`
first on PATH: after the body has ended (it leaves a trigger file), the first
call changes the record once, and every call then runs the real tool.
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
BASE_PATH = "/usr/local/bin:/usr/bin:/bin"
NOT_OWN = "is no longer this bind's own"
PSO_HEAD = "pid_start_of() {   # <pid>\n"


def q(value) -> str:
    return shlex.quote(str(value))


class Box:
    """One sandbox: `$HOME`, `$CLAUDE_CONFIG_DIR` with `lanes/offers/`, a
    state home, and a directory of stand-ins first on PATH."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.cfg = tmp / "cfg"
        self.offers = self.cfg / "lanes" / "offers"
        self.offers.mkdir(parents=True)
        self.state = tmp / "state"
        self.state.mkdir()
        self.fakes = tmp / "fakes"
        self.fakes.mkdir()
        self.rec = self.offers / UUID
        self.out = Path(f"{self.rec}.bind.1.out")
        self.facts = Path(f"{self.rec}.bind.1.facts")
        self.trigger = tmp / "body-ended"
        self.stub = tmp / "stub-body"

    def record(self, **over) -> None:
        keys = {
            "mode": "binding", "from": "repoA-2", "to": "repoA-3", "session": "repoA-3",
            "uuid": UUID, "window": "@1", "pane": "%1", "utc": "2026-11-14T00:00:00Z",
            "bind": "1", "started_utc": "2026-11-14T00:00:00Z", "bound_s": "500",
            "bounded": "yes", "deadline_epoch": str(int(time.time()) + 505),
            "host": HOST, "container": CONTAINER, "out": str(self.out), "detach": "setsid",
        }
        keys.update(over)
        self.rec.write_text("".join(f"{k}={v}\n" for k, v in keys.items() if v is not None))
        os.chmod(self.rec, 0o600)

    @staticmethod
    def read(path: Path) -> dict:
        got: dict = {}
        for line in path.read_text().splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                got.setdefault(key, value)
        return got

    def body(self, *, sed: str = "", code: int = 0, facts: str = "") -> None:
        """The stand-in body: an optional `sed` over the record (temporary
        file and `mv`), its facts, the trigger, and its exit code."""
        change = ""
        if sed:
            change = (f"sed -e {q(sed)} {q(self.rec)} > {q(str(self.rec) + '.mut')} && "
                      f"mv -f {q(str(self.rec) + '.mut')} {q(self.rec)}\n")
        self.stub.write_text(
            "#!/bin/bash\n" + change
            + f'[ -z "${{LANES_BIND_FACTS:-}}" ] || printf %s {q(facts)} > "$LANES_BIND_FACTS"\n'
            + f": > {q(self.trigger)}\nexit {code}\n")
        self.stub.chmod(0o755)

    def fake(self, name: str, change: str = ":") -> None:
        """`name` first on PATH: after the trigger it logs each call, and the
        first one makes <change>; then it runs the real one."""
        real = shutil.which(name, path=BASE_PATH)
        assert real, name
        tool = self.fakes / name
        tool.write_text(
            "#!/bin/bash\n"
            f"if [ -e {q(self.trigger)} ]; then\n"
            f"  printf '%s\\n' \"$*\" >> {q(self.tmp / (name + '-calls'))}\n"
            f"  if mkdir {q(self.tmp / ('once-' + name))} 2>/dev/null; then\n"
            f"    {change}\n"
            "  fi\n"
            "fi\n"
            f"exec {q(real)} \"$@\"\n")
        tool.chmod(0o755)

    def to_name_drift(self) -> str:
        mut = str(self.rec) + ".mut"
        return (f"sed -e 's/^mode=binding$/mode=name-drift/' {q(self.rec)} > {q(mut)} && "
                f"mv -f {q(mut)} {q(self.rec)}")

    def calls(self, name: str) -> list:
        path = self.tmp / (name + "-calls")
        return path.read_text().splitlines() if path.exists() else []

    def temps(self) -> list:
        return sorted(p.name for p in self.offers.iterdir() if p.name.startswith(f".{UUID}."))

    def env(self, **extra) -> dict:
        env = {
            "HOME": str(self.home), "PATH": f"{self.fakes}:{BASE_PATH}", "TMPDIR": str(self.tmp),
            "CLAUDE_CONFIG_DIR": str(self.cfg), "XDG_STATE_HOME": str(self.state),
            "LANES_WORKSTATION": HOST, "LANES_CONTAINER": CONTAINER,
            "LANES_BIND_BOUND_S": "15", "LC_ALL": "C",
        }
        env.update(extra)
        return env

    def outer(self, script: Path = SCRIPT):
        """`guard-bind <uuid>`, its stdout and stderr in the attempt's `.out`,
        as the hook's fork gives them."""
        with open(self.out, "ab") as fh:
            proc = subprocess.run(["bash", str(script), "guard-bind", UUID],
                                  env=self.env(LANES_BIND_BODY=str(self.stub)),
                                  stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=60)
        return proc.returncode, self.out.read_text(errors="replace")

    def own_start_unread_copy(self) -> Path:
        """Lane 3's point 23: a test-only copy whose `pid_start_of` exits 2
        for the caller's own pid, so the outer writes `pid` alone."""
        text = SCRIPT.read_text()
        assert text.count(PSO_HEAD) == 1
        text = text.replace(PSO_HEAD, PSO_HEAD + '  [ "${1-}" != "$$" ] || return 2\n')
        copy = self.tmp / "lanes-edit-copy.sh"
        copy.write_text(text)
        copy.chmod(0o755)
        return copy


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# ---- POINT 20, (a): the outcome's test also matches `host` and `container`.

def test_t502f_p20_a_record_whose_host_changed_is_not_written_over(box):
    box.record()
    box.body(sed="s/^host=Eagle$/host=Other-host/")
    rc, said = box.outer()
    rec = box.read(box.rec)
    assert rc == 0, said
    assert rec.get("mode") == "binding" and rec.get("host") == "Other-host", (rec, said)
    assert "rc" not in rec and "ended_utc" not in rec, (rec, said)
    assert NOT_OWN in said, said


def test_t502f_p20_a_pid_alone_record_whose_container_changed_is_not_written_over(box):
    copy = box.own_start_unread_copy()
    box.record()
    box.body(sed="s/^container=g-box$/container=other-box/")
    rc, said = box.outer(copy)
    rec = box.read(box.rec)
    assert rc == 0, said
    assert rec.get("pid", "").isdigit() and "pidstart" not in rec, (rec, said)
    assert rec.get("mode") == "binding" and rec.get("container") == "other-box", (rec, said)
    assert "rc" not in rec, (rec, said)
    assert NOT_OWN in said, said


@pytest.mark.parametrize("alone", [False, True], ids=["pidstart", "pid-alone"])
def test_t502f_p20_control_its_own_host_and_container_in_another_case_end_bound(box, alone):
    script = box.own_start_unread_copy() if alone else SCRIPT
    box.record()
    box.body(sed="s/^host=Eagle$/host=EAGLE/;s/^container=g-box$/container=G-BOX/")
    rc, said = box.outer(script)
    rec = box.read(box.rec)
    assert rc == 0, said
    assert rec.get("mode") == "bound" and rec.get("rc") == "0", (rec, said)
    assert ("pidstart" in rec) is (not alone), rec


# ---- POINT 21: the window kept, and narrowed in code.

def test_t502f_p21_a_change_while_the_copies_are_gathered_is_seen_by_the_read(box):
    pending = box.state / "openRepoTools" / "register-pending"
    pending.mkdir(parents=True)
    (pending / ("a" * 64)).write_text(f"verb=start-record\nsession={UUID}\n")
    box.record()
    box.fake("awk", box.to_name_drift())
    box.fake("mktemp")
    box.body(code=3, facts="why=the stand-in body refused\n")
    rc, said = box.outer()
    rec = box.read(box.rec)
    assert (box.tmp / "once-awk").is_dir(), said
    assert rc == 0, said
    assert rec.get("mode") == "name-drift" and "rc" not in rec, (rec, said)
    # THE READ CAUGHT IT, AFTER THE COPIES: the outcome's rewrite never ran.
    assert box.calls("mktemp") == [], (box.calls("mktemp"), said)
    assert NOT_OWN in said, said


def test_t502f_p21_a_change_after_the_read_is_seen_by_the_rewrites_copy_loop(box):
    box.record()
    box.fake("mktemp", box.to_name_drift())
    box.body()
    rc, said = box.outer()
    rec = box.read(box.rec)
    assert (box.tmp / "once-mktemp").is_dir(), said
    assert rc == 0, said
    assert rec.get("mode") == "name-drift" and "rc" not in rec, (rec, said)
    assert box.temps() == [], box.temps()
    assert NOT_OWN in said, said


def test_t502f_p21_a_record_dropped_after_the_read_is_not_made_again(box):
    box.record()
    gone = Path(str(box.rec) + ".gone")
    box.fake("mktemp", f"mv -f {q(box.rec)} {q(gone)}")
    box.body()
    rc, said = box.outer()
    assert (box.tmp / "once-mktemp").is_dir(), said
    assert rc == 0, said
    assert not box.rec.exists(), box.rec.read_text()
    assert box.read(gone).get("mode") == "binding"
    assert box.temps() == [], box.temps()
    assert NOT_OWN in said, said


# ---- POINT 25: the body reads its own words back only from an `out` of the
# record's own form.

def _lane_start(box: Box, extra: str = "") -> Path:
    stub = box.tmp / "stub-lane-start"
    stub.write_text("#!/bin/bash\n" + extra
                    + "printf 'lane-start: REFUSED for the scratch case\\n' >&2\nexit 5\n")
    stub.chmod(0o755)
    return stub


def _body(box: Box, stub: Path):
    with open(box.out, "ab") as fh:
        proc = subprocess.run(["bash", str(SCRIPT), "guard-bind", "--body", UUID],
                              env=box.env(LANES_LANE_START=str(stub),
                                          LANES_BIND_FACTS=str(box.facts)),
                              stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                              timeout=60)
    return proc.returncode, box.out.read_text(errors="replace")


def test_t502f_p25_the_body_reads_no_words_back_from_an_out_not_of_its_form(box):
    foreign = box.tmp / "elsewhere.log"
    foreign.write_text("a line from before\n")
    box.record(out=str(foreign))
    stub = _lane_start(box, f"printf 'FOREIGN-WORDS-NOT-THIS-ATTEMPTS\\n' >> {q(foreign)}\n")
    rc, said = _body(box, stub)
    assert rc == 5, said
    why = box.read(box.facts).get("why", "")
    assert "FOREIGN" not in why, why
    assert "could not be read back" in why, why


def test_t502f_p25_control_the_body_reads_its_own_out(box):
    box.record()
    rc, said = _body(box, _lane_start(box))
    assert rc == 5, said
    assert box.read(box.facts).get("why") == "lane-start: REFUSED for the scratch case", said


# ---- THE TWO COMMENTS name the exit 1 given where the outcome cannot be written.

def _joined(text: str, start: str, size: int) -> str:
    i = text.index(start)
    return " ".join(line.lstrip("#").strip() for line in text[i:i + size].splitlines())


def test_t502f_comments_name_the_outcomes_exit_1():
    text = SCRIPT.read_text()
    table = _joined(text, "#      AND `guard-bind` (feature 007, T502)", 900)
    assert "could not write the outcome" in table, table
    exits = _joined(text, "# Exits: 0 once the outcome is written", 500)
    assert "the outcome could not be written" in exits, exits
