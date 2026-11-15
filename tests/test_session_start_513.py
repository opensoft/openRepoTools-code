# SPDX-License-Identifier: Apache-2.0
"""T513'S START OF THE REGISTER SERVICE, HELD BY COMMITTED CASES (feature 007,
lane 1's SHOULD on T513, opensoft/openRepoTools#165 6882025131).

Lane 1's U5 review passed T513 with one SHOULD: its verify asserts only exit
0, no register call and a socket within 10 s, and no committed test checks
that nothing starts in index mode, with no configuration, on a 78 or on a
compact; that the hook's bytes are the same with and without the start; that
the start comes after the whole answer; or the skip rule and the time limit.
Lane 5 takes the SHOULD in this module of its own, so that lane 2's guard
module is not touched. Lane 2's T237zzb case at line R runs `[index]`, `[78]`
and `[compact]` on a full primary estate; the cases here are hermetic, and
add `[no-config]`, the bytes, the order, the skip rule and the timer.

WHAT THE CODE DOES (`lanes-edit.sh`). The `session-start` arm sets
`SECONDS=0`, runs `session_start_block`, then runs `reg_service_start` only
where `REG_MODE` is `primary` and `SECONDS` is under the skip line, and exits
0. `REG_MODE` is the block's one mode answer (`reg_session_read`): files with
no configuration, else one `lanes-index mode` under its own timer, `refused`
on a 78. A compact returns before that read, so `REG_MODE` stays empty.
`reg_service_start` runs `lanes-index serve --start` under its own timer, with
its stdout and stderr on /dev/null, and ignores its exit.

THE ESTATE. Each run copies `lanes-edit.sh`, `repos.tsv` and `lane-start` into
a directory of its own under `tmp_path`, with a stand-in `lanes-index` beside
the copy, where `lanes_index_bin` looks first, so nothing installed runs. The
stand-in records every call's words; answers `mode` as the case says; and on
`serve --start` writes a line to its stdout and its stderr and then succeeds,
fails or hangs. Its success makes `register.sock` in the run directory a real
start would use, `${XDG_STATE_HOME}/openRepoTools/run/`, so "no socket" is
measured against a start that would make one. It is a plain file and never a
bound socket, so the path's length under pytest's base directory does not
matter. `HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `TMPDIR`, the protocol
root and `LANES_FILE` are under `tmp_path` too, and `tmux` is a stand-in
first on `PATH` that names no window. With no register the block answers its
no-lane notice and its last line, `as of ... (no fetch)`.

THE TIMES ARE READ FROM THE CODE: the hook's 5 s from the installer's
`HOOK_TIMEOUT`, the skip line from the arm, and the `timeout -k <k> <n>` of
`mode` and of `serve --start`. Every timing assertion has a margin for CI.
`SECONDS` counts whole seconds of the wall clock, so it can read 1 after a
tenth of a second and 2 after just over one. The cases that expect a start
rely on the arm reaching its start line inside 1 s, the one bound that
always reads under the skip line; with these stand-ins it takes about 0.1 s.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None, reason="the session-start hook is a bash command")]

#: The `timeout` both timers are held by. Where it is not installed the code
#: runs the call unbounded, so the cases that hang a start skip there.
NEEDS_TIMEOUT = pytest.mark.skipif(
    shutil.which("timeout") is None,
    reason="the start's timer is `timeout`'s; without it the code runs the start unbounded")

#: What each timing assertion allows past the bound it reads from the code.
CI_MARGIN_S = 1.5

#: How far past the skip line the slow case's arm is made to run. The delays
#: are sleeps, which never end early, and `SECONDS` counts whole seconds of
#: the wall clock, so an arm that has run 2.3 s reads 2 or more.
PAST_THE_SKIP_LINE_S = 0.3

#: How long a hung start lives if nothing ends it: its own alarm, so a case
#: whose timer is gone fails on the time instead of leaving a process.
HANG_LIFE_S = 20

#: The session the payload names. No row carries it: there is no register.
SESSION_ID = "aaaa0513-0000-4000-8000-000000000513"

#: The block's last line on every branch but a compact's (`ssb_tail`).
TAIL = re.compile(rb"\nas of [^\n]+ \(no fetch\)\n\Z")

#: `reg_session_read`'s line on stderr on primary: the evidence that the
#: block's one mode answer was primary.
PRIMARY_LINE = "makes no register call, R39"

#: What the stand-in's start writes, which must never reach the hook's output.
START_STDOUT = "T513 stand-in: serve --start wrote this to its stdout"
START_STDERR = "T513 stand-in: serve --start wrote this to its stderr"

#: THE HUNG START, run by the stand-in with `exec`, so the timer signals it
#: under the stand-in's own pid. It notes its pid and its start time (from
#: `/proc`, for the cleanup), then each TERM. `hang` exits on the TERM;
#: `hang-deaf` ignores it, so only the timer's KILL ends it.
_HANG = r'''import os, signal, sys
notes, how = sys.argv[1], sys.argv[2]
def note(text):
    with open(notes, "a", encoding="utf-8") as fh:
        fh.write(text + "\n")
def on_term(signum, frame):
    note("TERM")
    if how == "hang":
        os._exit(143)
signal.signal(signal.SIGTERM, on_term)
signal.alarm(@LIFE@)
try:
    with open("/proc/self/stat", encoding="ascii") as fh:
        start = fh.read().rsplit(")", 1)[1].split()[19]
except OSError:
    start = "-"
note("hanging %d %s" % (os.getpid(), start))
while True:
    signal.pause()
'''

#: THE STAND-IN `lanes-index`. Every @NAME@ is filled with a quoted value.
#: @OUT@ is the hook's stdout file where the case captures one, else empty:
#: `mode` and `serve --start` each copy it as it stands when they are called.
_STAND_IN = r'''#!/bin/sh
printf '%s\n' "$*" >> @CALLS@
case "${1-}" in
  mode)
    [ -z @OUT@ ] || cat -- @OUT@ > @AT_MODE@
    [ -z @MODE_DELAY@ ] || sleep @MODE_DELAY@
    case @MODE@ in
      primary|index) printf '%s\n' @MODE@; exit 0 ;;
      78) printf 'lanes-index: REFUSED: mode=primary in this build (T513 stand-in)\n' >&2
          exit 78 ;;
    esac
    exit 64 ;;
  serve)
    [ "${2-}" = --start ] || exit 64
    [ -z @OUT@ ] || cat -- @OUT@ > @AT_START@
    printf '%s\n' @START_STDOUT@
    printf '%s\n' @START_STDERR@ >&2
    case @START@ in
      ok) mkdir -p -- @RUN@ && : > @RUN@/register.sock; exit 0 ;;
      fail) exit 1 ;;
      hang|hang-deaf) exec @PY@ -I -c @HANG@ @NOTES@ @START@ ;;
    esac
    exit 64 ;;
esac
exit 64
'''


@dataclass
class Budget:
    """The times this module reads from the code."""
    hook_s: int         # the installer's SessionStart `timeout`
    skip_s: int         # the arm's `[ "$SECONDS" -ge <n> ]`
    mode_s: int         # `mode`'s `timeout -k <k> <n>`: n
    start_s: int        # `serve --start`'s `timeout -k <k> <n>`: n
    start_kill_s: int   # ...and its k


def _read(path: Path, pattern: str, what: str) -> tuple:
    text = path.read_text(encoding="utf-8")
    found = re.search(pattern, text, re.M)
    assert found, f"{path.name} no longer carries {what}, which this module reads from it"
    return tuple(int(group) for group in found.groups())


@pytest.fixture(scope="module")
def budget() -> Budget:
    edit = REPO / "lanes-edit.sh"
    (hook,) = _read(REPO / "openRepoTools", r"^HOOK_TIMEOUT=([0-9]+)$",
                    "the SessionStart hook's HOOK_TIMEOUT")
    (skip,) = _read(edit, r'\[ "\$SECONDS" -ge ([0-9]+) \] \|\| reg_service_start',
                    "the session-start arm's skip line")
    _, mode = _read(edit, r'timeout -k ([0-9]+) ([0-9]+) "\$rmq_bin" mode',
                    "the mode question's timer")
    kill, start = _read(edit, r'timeout -k ([0-9]+) ([0-9]+) "\$rss_bin" serve --start',
                        "the start's timer")
    return Budget(hook_s=hook, skip_s=skip, mode_s=mode, start_s=start, start_kill_s=kill)


@dataclass
class Run:
    """One `session-start`, and what the stand-in saw."""
    code: int
    stdout: bytes
    stderr: str
    seconds: float
    calls: list
    notes: list
    socket: bool
    at_mode: bytes | None
    at_start: bytes | None


def _alive(pid: int, start: str) -> bool:
    """`pid` is running and is the process that noted `start` (no reuse)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except OSError:
        return False
    fields = stat.rsplit(")", 1)[1].split()
    return fields[0] != "Z" and fields[19] == start


def _hung(notes: list) -> list:
    """(pid, start) of each hung start the notes record."""
    return [(int(words[1]), words[2]) for words in (line.split() for line in notes)
            if len(words) == 3 and words[0] == "hanging"]


@pytest.fixture
def session_start(tmp_path):
    """`run(name, ...)`: the real `session-start` from a copy under
    `tmp_path/<name>`, as `Run`. Its teardown KILLs any hung start a run
    left alive (none should be: the timer ends it), matched by pid and start
    time, so no process outlives the case."""
    roots = []

    def run(name, *, mode="primary", config=True, start="ok", source="startup",
            tmux_delay="", mode_delay="", stdout_file=False) -> Run:
        root = tmp_path / name
        here = root / "bin"
        here.mkdir(parents=True)
        roots.append(root)
        for item in ("lanes-edit.sh", "repos.tsv", "lane-start"):
            shutil.copy2(REPO / item, here / item)
        fake = root / "fake"
        fake.mkdir()
        tmux = fake / "tmux"
        tmux.write_text("#!/bin/sh\n" + (f"sleep {tmux_delay}\n" if tmux_delay else "")
                        + "exit 1\n", encoding="utf-8")
        tmux.chmod(0o755)
        home, state, tmp = root / "home", root / "state", root / "tmp"
        for directory in (home, state, tmp, root / "config"):
            directory.mkdir()
        if config:
            (root / "config" / "openRepoTools").mkdir()
            (root / "config" / "openRepoTools" / "lanes-index.conf").write_text(
                "", encoding="utf-8")
        out = root / "hook.stdout"
        values = dict(CALLS=root / "calls.log", NOTES=root / "notes.log",
                      OUT=out if stdout_file else "", AT_MODE=root / "at-mode",
                      AT_START=root / "at-start", MODE_DELAY=mode_delay, MODE=mode,
                      START=start, START_STDOUT=START_STDOUT, START_STDERR=START_STDERR,
                      RUN=state / "openRepoTools" / "run", PY=sys.executable,
                      HANG=_HANG.replace("@LIFE@", str(HANG_LIFE_S)))
        text = _STAND_IN
        for key, value in values.items():
            text = text.replace(f"@{key}@", shlex.quote(str(value)))
        (here / "lanes-index").write_text(text, encoding="utf-8")
        (here / "lanes-index").chmod(0o755)
        env = {"HOME": str(home), "TMPDIR": str(tmp),
               "PATH": os.pathsep.join([str(fake), os.environ.get("PATH", os.defpath)]),
               "XDG_CONFIG_HOME": str(root / "config"), "XDG_STATE_HOME": str(state),
               "AGENT_PROTOCOL_ROOT": str(home / ".agents"),
               "LANES_FILE": str(root / "lanes" / "LANES.md")}
        payload = json.dumps({"session_id": SESSION_ID, "source": source, "cwd": str(root),
                              "hook_event_name": "SessionStart"}, separators=(",", ":"))
        argv = ["bash", str(here / "lanes-edit.sh"), "session-start"]
        began = time.monotonic()
        if stdout_file:
            with open(out, "wb") as sink:
                proc = subprocess.run(argv, input=payload.encode(), stdout=sink,
                                      stderr=subprocess.PIPE, env=env, cwd=str(root),
                                      timeout=60, check=False)
            stdout = out.read_bytes()
        else:
            proc = subprocess.run(argv, input=payload.encode(), capture_output=True,
                                  env=env, cwd=str(root), timeout=60, check=False)
            stdout = proc.stdout
        seconds = time.monotonic() - began

        def lines(path):
            return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

        def snap(path):
            return path.read_bytes() if path.exists() else None

        return Run(code=proc.returncode, stdout=stdout,
                   stderr=proc.stderr.decode("utf-8", "replace"), seconds=seconds,
                   calls=lines(root / "calls.log"), notes=lines(root / "notes.log"),
                   socket=(state / "openRepoTools" / "run" / "register.sock").exists(),
                   at_mode=snap(root / "at-mode"), at_start=snap(root / "at-start"))

    yield run
    for root in roots:
        notes = root / "notes.log"
        if notes.exists():
            for pid, start in _hung(notes.read_text(encoding="utf-8").splitlines()):
                if _alive(pid, start):
                    os.kill(pid, signal.SIGKILL)


#: (a): each state where the arm must start nothing, with the stand-in's
#: answer, whether a configuration exists, the source, and the calls the
#: block makes: `[index]`, the answer `index`; `[no-config]`, no
#: configuration, so no question at all; `[78]`, `mode` exits 78, EX_CONFIG;
#: `[compact]`, a primary workstation, but a compact returns before the
#: question.
NO_START = {
    "index": dict(mode="index", config=True, source="startup", calls=["mode"]),
    "no-config": dict(mode="primary", config=False, source="startup", calls=[]),
    "78": dict(mode="78", config=True, source="startup", calls=["mode"]),
    "compact": dict(mode="primary", config=True, source="compact", calls=[]),
}


@pytest.mark.parametrize("state", list(NO_START), ids=list(NO_START))
def test_session_start_513_starts_nothing_where_it_must_not(session_start, state):
    """(a) Off primary, and on a compact, the arm starts nothing: exit 0, no
    `serve --start` call, and no `register.sock` in the run directory, where
    the stand-in's start would make one. The stand-in's log is also exactly
    the block's own calls, so the block read the answer the case gives and
    asked nothing else; and every state but the compact ends on the block's
    last line, so the arm reached its start line."""
    case = NO_START[state]
    run = session_start(state, mode=case["mode"], config=case["config"],
                        source=case["source"])
    assert run.code == 0, (run.code, run.stderr)
    assert "serve --start" not in run.calls and not run.socket, \
        f"session-start [{state}] started the service: {run.calls}\n{run.stderr}"
    assert run.calls == case["calls"], run.calls
    assert PRIMARY_LINE not in run.stderr and "WARNING" not in run.stderr, run.stderr
    if state == "compact":
        assert run.stdout == b"", run.stdout
    else:
        assert TAIL.search(run.stdout), run.stdout
    if state == "78":
        assert "exit 78" in run.stderr, run.stderr


@pytest.mark.parametrize("state", ["primary"], ids=["primary"])
def test_session_start_513_starts_the_service_once_on_primary(session_start, state):
    """(b) The control: on primary the stand-in records the one mode question
    and then exactly one `serve --start`, and its start makes the socket the
    cases above look for."""
    run = session_start(state)
    assert run.code == 0, (run.code, run.stderr)
    assert run.calls == ["mode", "serve --start"], run.calls
    assert run.socket, "the start the stand-in was given made no register.sock"
    assert PRIMARY_LINE in run.stderr, run.stderr
    assert TAIL.search(run.stdout), run.stdout


@NEEDS_TIMEOUT
def test_session_start_513_keeps_the_hooks_bytes_whatever_the_start_does(session_start):
    """(c) On primary the hook's stdout is the same bytes whether the start
    succeeds, fails, or hangs until its timer ends it, and so is its stderr:
    the start's own output goes to /dev/null and its exit is ignored. Each
    run made its one start, and the stand-in's start wrote to its stdout and
    its stderr each time, so a start whose output reached the hook differs."""
    runs = {how: session_start(f"bytes-{how}", start=how) for how in ("ok", "fail", "hang")}
    for how, run in runs.items():
        assert run.code == 0, (how, run.code, run.stderr)
        assert run.calls == ["mode", "serve --start"], (how, run.calls)
        assert START_STDOUT.encode() not in run.stdout and START_STDERR not in run.stderr, how
        assert START_STDOUT not in run.stderr and START_STDERR.encode() not in run.stdout, how
    assert runs["ok"].socket and not runs["fail"].socket and not runs["hang"].socket
    assert "TERM" in runs["hang"].notes, runs["hang"].notes
    assert TAIL.search(runs["ok"].stdout), runs["ok"].stdout
    assert runs["ok"].stdout == runs["fail"].stdout == runs["hang"].stdout, \
        {how: run.stdout for how, run in runs.items()}
    assert runs["ok"].stderr == runs["fail"].stderr == runs["hang"].stderr, \
        {how: run.stderr for how, run in runs.items()}


def test_session_start_513_starts_only_after_the_whole_answer(session_start):
    """(d) The start comes after the block's whole answer, proved with no
    sleep. The hook's stdout is a file the case opens, and the stand-in
    copies that file as it stands when each call reaches it. At `mode`, the
    block's read before its first line, the copy is empty, so a copy shows
    the answer only as far as it was written. At `serve --start` it is the
    hook's whole stdout, byte for byte, so nothing was written after the
    start."""
    run = session_start("order", stdout_file=True)
    assert run.code == 0, (run.code, run.stderr)
    assert run.calls == ["mode", "serve --start"], run.calls
    assert TAIL.search(run.stdout), run.stdout
    assert run.at_mode == b"", run.at_mode
    assert run.at_start == run.stdout, (run.at_start, run.stdout)


def test_session_start_513_skips_the_start_once_two_seconds_are_spent(session_start, budget):
    """(e) The skip rule: where the arm's `SECONDS` reads the skip line or
    more before the start, nothing starts, though the answer was primary.

    `mode` cannot carry the arm past the line alone: it runs under its own
    timer, and a `mode` that takes longer is stopped and read as files mode,
    which starts nothing for another reason. So the stand-in answers
    `primary` in half its timer, and `tmux`, which the arm asks for the
    window after `SECONDS=0`, takes the rest and a little more. The stderr
    line says the answer was primary, and the hook still exits 0 inside
    its own budget."""
    mode_delay = budget.mode_s / 2
    tmux_delay = budget.skip_s - mode_delay + PAST_THE_SKIP_LINE_S
    run = session_start("skip", tmux_delay=f"{tmux_delay:.2f}", mode_delay=f"{mode_delay:.2f}")
    assert run.code == 0, (run.code, run.stderr)
    assert run.calls == ["mode"], f"the start ran past the skip line: {run.calls}"
    assert not run.socket
    assert PRIMARY_LINE in run.stderr and "WARNING" not in run.stderr, run.stderr
    assert TAIL.search(run.stdout), run.stdout
    assert budget.skip_s <= run.seconds < budget.hook_s, run.seconds


@NEEDS_TIMEOUT
@pytest.mark.parametrize("how", ["hang", "hang-deaf"], ids=["stops-on-term", "ignores-term"])
def test_session_start_513_ends_a_hung_start_by_its_timer(session_start, budget, how):
    """(e) The timer: a start that hangs is ended by `timeout -k <k> <n>`, at
    n s by its TERM (`[stops-on-term]`) or at n + k s by its KILL where the
    TERM is ignored (`[ignores-term]`). The hook exits 0 well inside its own
    budget, the hung start noted the TERM, and it is not running after."""
    bound = budget.start_s + budget.start_kill_s + CI_MARGIN_S
    assert bound < budget.hook_s, (bound, budget)
    run = session_start(f"timer-{how}", start=how)
    assert run.code == 0, (run.code, run.stderr)
    assert run.calls == ["mode", "serve --start"], run.calls
    hung = _hung(run.notes)
    assert len(hung) == 1 and "TERM" in run.notes, run.notes
    assert budget.start_s <= run.seconds < bound, (run.seconds, bound)
    pid, start = hung[0]
    assert not _alive(pid, start), f"the hung start {pid} outlived the hook"
    assert TAIL.search(run.stdout), run.stdout
