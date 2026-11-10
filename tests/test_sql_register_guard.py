# SPDX-License-Identifier: Apache-2.0
"""The name guard's own cases, `lanes-edit.sh guard` and answer 2's detached
bind, `guard-bind` (feature 007; L2-N3; opensoft/openRepoTools#165).

T214 writes AT-F6's phase-N cases (the test plan's "Answer 2's bind,
detached"): lane 4's cases 1 to 7, 12 to 17 and 22, the four rows (a) to (d),
the `bind-failed` record for each code, lane 4's rows 34 and 35, and lane 5's
two (A5). The bind's writes, cases 8 to 11 and 18 to 21, are T254's, with the
`[primary]` half of every test below that binds through `start-record` in
both modes (A1): the mode is each such id's last part, `[files]` here.

THE ORACLE is the test plan's AT-F6 and lane 5's bind-record contract, draft 7
(`bind-record-d7-a832486c.md`): the record's keys and modes (its sections 1 to
3), the bound (section 4), the guard's eleven cases (section 5) and
`pid_start_of` (section 6). Where a text is quoted below it is the contract's;
where the code's own spelling differs from the contract's (a capital letter,
a sentence's opening), the case matches the words both share.

THE ESTATE is T203c's (`test_sql_register_helpers.py`): a bare origin, the
lane's checkout under `$HOME/projects` with `lanes/LANES.md` pushed,
`$HOME/.agents/workspace.yaml`, the compact hook JSON, and `guard_session`'s
live session record and stand-in `tmux` (T203c; R-F10-27, R-F10-28), in files
mode. The window is lane `repoA-2`, whose row names the session; the session
is named `repoA-3`, a lane with a row of its own; so the guard's first prompt
makes the offer, and a `2` answers it. `LANES_LANE_START` names a stand-in
`lane-start` that logs its argv and environment and holds, fails or forks as
the case says; `LANES_EDIT` names a stand-in that logs each call and answers
`set-row-state` (or sleeps on it); `LANES_BIND_BODY` names a stand-in body
(R48). The hook runs under a runner that, like Claude Code 2.1.319, sends
`SIGTERM` to the hook's whole process group at its 5 s timeout and does not
wait on pipes a child inherits.

EVERY CASE BUT TWO IS RED TODAY by its own assertion: today's answer 2 runs
`lane-start` inside the hook, so no "BINDING" is printed and the runner stops
the hook at 5 s; today's guard has no bind modes, no `guard-bind` and no
`pid_start_of`. They fail until L5-A1 and L5-A2 (lane 5's T502 and T507); the
ones that run the real `lane-start` fail until lane 4's `start-record` (L4-B9)
as well. The two are `test_the_hook_string_and_guard_timeout_are_unchanged`,
an invariant that holds today, and `test_an_unreadable_bind_record_is_dropped_with_exit_2`,
whose oracle is today's text and today's drop.
"""

from __future__ import annotations

import calendar
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_helpers import (ARGV_LOG, GUARD_PANE, GUARD_WINDOW, contract_stub,
                                  guard_session, guard_strip_env)

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None
    or not Path("/proc/self/stat").exists(),
    reason="the lane tooling is bash over git, and the bind's liveness test reads /proc")]

GUARD = REPO / "lanes-edit.sh"
INSTALLER = REPO / "openRepoTools"
#: The window's lane and the lane the session is named for: the offer's
#: `from` and `to`.
FROM = GUARD_WINDOW
TO = "repoA-3"
#: This guard's host and container, as the record's `host` and `container`
#: name them (`LANES_WORKSTATION`, `LANES_CONTAINER`; contract section 3).
HOST = "Eagle"
CONTAINER = "g-box"
#: The hook's timeout, `GUARD_TIMEOUT` (plan.md, "Governed invariants").
HOOK_TIMEOUT = 5.0
DOT = chr(0xB7)
#: The five copies a record holds only on primary (contract section 3; T254).
COPIES = ("write_id", "generation", "not_after", "write_lane", "args_sha256")

#: The contract's texts (section 5), as the guard prints them on stderr.
OFFER = "WARNING: the lane and Claude session names disagree"
BINDING = f"BINDING: this window is now named {TO}"
IN_PROGRESS = "BINDING IN PROGRESS"
NOT_SENT = "Your prompt was NOT sent"
NO_OUTCOME = "IS NO LONGER RUNNING AND LEFT NO OUTCOME"
UNREADABLE = ("could not be read, so it has been dropped rather than answered on a guess. "
              "Send your prompt again and the question will be asked afresh.")
NO_LONGER_2 = "choice 2 is no longer offered"
KEPT = "offer is KEPT"
BY_BOUND = "stopped by its bound"
BY_SIGNAL = "stopped by a signal"
UNKNOWN = "what it wrote is not known"

REGISTER_HEADER = ["# LANES.md", "",
                   "| lane | session id | workstation / env / user | started (UTC) | objects "
                   "owned | handoff path | state |",
                   "|---|---|---|---|---|---|---|"]


# ---------------------------------------------------------------- the stand-ins

#: THE STAND-IN `lane-start` (the test plan's fixture: one that sleeps, exits a
#: given code, or forks a `( ... & )` child as `index_nudge` does). It logs one
#: JSON line at its start and one at its end to `<ctl>/lane-start.log`, with
#: its argv, its process's ids, the variables lane 4's table names, and where
#: its stdin points. The files in `<ctl>` steer it: `hold` (wait for
#: `release`, at most that many seconds), `sleep` (that many seconds),
#: `rc`, `ignore-term`, `tmux` (make one untargeted `tmux` call) and `fork`
#: (leave a child that ignores TERM, living that many seconds).
_STUB_LANE_START = r'''#!@PY@ -I
import json, os, signal, subprocess, sys, time
CTL = @CTL@
KEYS = ("LANES_NO_FETCH", "LANES_ACT", "LANES_EXPECT", "LANES_WRITE_ID",
        "LANES_WRITE_GENERATION", "LANE_START_HANDOFF_ANSWER", "LANES_GIT_TIMEOUT",
        "TMUX", "TMUX_PANE", "LANES_BIND_BODY", "LANES_BIND_FACTS")
def ctl(name, default=None):
    try:
        with open(os.path.join(CTL, name), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return default
def ids():
    with open("/proc/self/stat", encoding="utf-8") as handle:
        f = handle.read().rsplit(") ", 1)[1].split()
    return {"ppid": int(f[1]), "pgid": int(f[2]), "sid": int(f[3])}
def log(entry):
    with open(os.path.join(CTL, "lane-start.log"), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
entry = dict(event="start", argv=sys.argv[1:], pid=os.getpid(), t=time.time(),
             env={k: os.environ.get(k) for k in KEYS}, **ids())
try:
    entry["stdin"] = os.readlink("/proc/self/fd/0")
except OSError:
    entry["stdin"] = None
if ctl("ignore-term") is not None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if ctl("tmux") is not None:
    done = subprocess.run(["tmux", "display-message", "-p", "#{pane_id}"],
                          capture_output=True, text=True)
    entry["tmux"] = [done.returncode, done.stdout.strip()]
if ctl("fork") is not None:
    child = subprocess.Popen(
        [sys.executable, "-I", "-c",
         "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
         "time.sleep(%s)" % float(ctl("fork"))],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    entry["fork"] = child.pid
log(entry)
if ctl("sleep") is not None:
    time.sleep(float(ctl("sleep")))
elif ctl("hold") is not None:
    end = time.time() + float(ctl("hold") or 60)
    while time.time() < end and not os.path.exists(os.path.join(CTL, "release")):
        time.sleep(0.05)
code = int(ctl("rc", "0") or 0)
if code:
    sys.stderr.write("lane-start: the stand-in refuses with %d (T214's fixture)\n" % code)
log(dict(event="end", pid=os.getpid(), t=time.time(), rc=code))
sys.exit(code)
'''

#: THE STAND-IN BODY, put in through `LANES_BIND_BODY` (R48; case 7's seam,
#: and case 22's "stub body that exits 0"). It logs its argv, its ids and its
#: parent's argv (`timeout`'s, where the outer bounds it) to `<ctl>/body.log`.
#: `body-ignore-term` makes it ignore TERM in its own process;
#: `body-grandchild` leaves a child that ignores TERM; `body-sleep` and
#: `body-rc` say how long it runs and how it ends.
_STUB_BODY = r'''#!@PY@ -I
import json, os, signal, subprocess, sys, time
CTL = @CTL@
def ctl(name, default=None):
    try:
        with open(os.path.join(CTL, name), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return default
def ids():
    with open("/proc/self/stat", encoding="utf-8") as handle:
        f = handle.read().rsplit(") ", 1)[1].split()
    return {"ppid": int(f[1]), "pgid": int(f[2]), "sid": int(f[3])}
def argv_of(pid):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            return [a.decode("utf-8", "replace") for a in handle.read().split(b"\0")[:-1]]
    except OSError:
        return []
if ctl("body-ignore-term") is not None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
entry = dict(event="body", argv=sys.argv[1:], pid=os.getpid(), t=time.time(),
             parent=argv_of(os.getppid()),
             env={k: os.environ.get(k) for k in ("LANES_BIND_BODY", "LANES_BIND_FACTS")},
             **ids())
if ctl("body-grandchild") is not None:
    child = subprocess.Popen(
        [sys.executable, "-I", "-c",
         "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    entry["grandchild"] = child.pid
with open(os.path.join(CTL, "body.log"), "a", encoding="utf-8") as handle:
    handle.write(json.dumps(entry, sort_keys=True) + "\n")
if ctl("body-sleep") is not None:
    time.sleep(float(ctl("body-sleep")))
sys.exit(int(ctl("body-rc", "0") or 0))
'''

#: THE STAND-IN `LANES_EDIT` (the fixture's "`LANES_EDIT` stub that logs and
#: counts each call"): it logs each call's argv and the bind's variables to
#: `<ctl>/lanes-edit.log`, then answers `set-row-state` with 0, or sleeps on it
#: (`edit-sleep`), and answers `start-record` with the code in
#: `start-record-rc` where that file is there; every other call, and every call
#: where `edit-real` is there, runs the checkout's `lanes-edit.sh`.
_STUB_EDIT = r'''#!@PY@ -I
import json, os, sys, time
CTL = @CTL@
REAL = @REAL@
def ctl(name, default=None):
    try:
        with open(os.path.join(CTL, name), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return default
args = sys.argv[1:]
with open(os.path.join(CTL, "lanes-edit.log"), "a", encoding="utf-8") as handle:
    handle.write(json.dumps(dict(argv=args, pid=os.getpid(), t=time.time(), env={
        k: os.environ.get(k) for k in ("LANES_ACT", "LANES_EXPECT", "LANES_WRITE_ID")}),
        sort_keys=True) + "\n")
verb = args[0] if args else ""
if verb == "start-record" and ctl("start-record-rc") is not None:
    sys.stderr.write("lanes-edit.sh start-record: the stand-in's code\n")
    sys.exit(int(ctl("start-record-rc")))
if verb == "set-row-state" and ctl("edit-real") is None:
    if ctl("edit-sleep") is not None:
        time.sleep(float(ctl("edit-sleep")))
    sys.exit(0)
os.execvp("bash", ["bash", REAL] + args)
'''


def _q(value) -> str:
    """`value` as a Python literal, for the stand-ins' `@...@` words."""
    return repr(str(value))


def _script(path: Path, text: str, **words) -> Path:
    for key, value in words.items():
        text = text.replace(f"@{key}@", value)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


# ---------------------------------------------------------------- processes

def _stat(pid) -> dict:
    """`/proc/<pid>/stat`'s state and ids, or {} where it is gone."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    f = text.rsplit(") ", 1)[1].split()
    return {"state": f[0], "ppid": int(f[1]), "pgid": int(f[2]), "sid": int(f[3]),
            "start": f[19]}


def _alive(pid) -> bool:
    return _stat(pid).get("state", "Z") not in ("Z", "X", "x", "Z")


def _members(field: str, value: int) -> list:
    """The live processes whose `sid` or `pgid` is `value` (zombies left out,
    as the guard's session test leaves them out)."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        st = _stat(entry.name)
        if st and st[field] == value and st["state"] not in ("Z", "X", "x"):
            found.append(int(entry.name))
    return found


def _argv(pid) -> list:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [a.decode("utf-8", "replace") for a in raw.split(b"\0")[:-1]]


def _kill(pid, sig=signal.SIGKILL) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _until(predicate, limit: float, step: float = 0.05):
    """`predicate()`'s first true value inside `limit` seconds, else None."""
    end = time.monotonic() + limit
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() >= end:
            return None
        time.sleep(step)


def _utc(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _epoch(utc: str) -> int:
    return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))


# ---------------------------------------------------------------- the runner

class Hook:
    """One run of the hook: its exit, its two streams, and the runner's times
    (monotonic, from `t0`, the runner's exec): the exit, each stream's EOF,
    and whether the runner's timer stopped it."""

    def __init__(self, code, out, err, t0, t_exit, eof, killed, pgid):
        self.code, self.out, self.err = code, out, err
        self.t0, self.t_exit, self.eof, self.killed, self.pgid = t0, t_exit, eof, killed, pgid

    @property
    def text(self) -> str:
        return self.out + self.err

    def __repr__(self) -> str:
        return (f"<hook exit {self.code} after {self.t_exit - self.t0:.2f} s"
                f"{' (stopped by the runner)' if self.killed else ''}:\n{self.text[-1500:]}>")


def run_hook(argv, stdin_text: str, env: dict, cwd, timeout: float = HOOK_TIMEOUT) -> Hook:
    """THE RUNNER: Claude Code 2.1.319's way with a `UserPromptSubmit` hook, as
    lane 4's hook probe found it (the test plan's AT-F6 fixture). It starts
    the hook as the leader of a process group of its own, feeds its JSON on
    stdin, and at `timeout` sends `SIGTERM` to that whole group; it never
    waits on a pipe a child inherited, only for the hook's own exit, and it
    logs when each stream reached EOF."""
    t0 = time.monotonic()
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=str(cwd), env=env,
                            start_new_session=True)
    chunks = {"out": [], "err": []}
    eof = {}

    def read(name, stream):
        fd = stream.fileno()
        while True:
            try:
                data = os.read(fd, 65536)
            except OSError:
                data = b""
            if not data:
                eof[name] = time.monotonic()
                return
            chunks[name].append(data)

    readers = [threading.Thread(target=read, args=(name, stream), daemon=True)
               for name, stream in (("out", proc.stdout), ("err", proc.stderr))]
    for reader in readers:
        reader.start()
    try:
        proc.stdin.write(stdin_text.encode("utf-8"))
        proc.stdin.close()
    except OSError:
        pass
    killed = False
    try:
        code = proc.wait(timeout)
    except subprocess.TimeoutExpired:
        killed = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            code = proc.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
    t_exit = time.monotonic()
    for reader in readers:
        reader.join(timeout=1.0)
    text = {k: b"".join(v).decode("utf-8", "replace") for k, v in chunks.items()}
    return Hook(code, text["out"], text["err"], t0, t_exit, eof, killed, proc.pid)


# ---------------------------------------------------------------- the record

def read_record(path: Path) -> dict:
    """The record's `key=value` lines, the first of each key winning as the
    guard reads it (`guard_bind_load`), and the `note=` lines in a list."""
    record = {"note": []}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "note":
            record["note"].append(value)
        else:
            record.setdefault(key, value)
    return record


def write_record(path: Path, lines) -> None:
    """A record written as every writer of it writes one: a temporary file in
    `offers/` at 0600, then a rename (contract section 1)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.parent / f".{path.name}.t214"
    tmp.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    tmp.chmod(0o600)
    os.replace(tmp, path)


# ---------------------------------------------------------------- the estate

def _row(lane: str, cell: str, state: str) -> str:
    return (f"| `{lane}` | harness `{cell}` | {HOST} / test / brett | 2026-10-01T00:00Z | none "
            f"| handoffs/{lane}.md | {state} {DOT} 2026-10-01T02:00:00Z {DOT} working |")


def register_text(rows) -> str:
    return "\n".join(REGISTER_HEADER + list(rows) + [""])


class Estate:
    """T203c's estate with the guard's offer for this session: the window is
    `FROM`, whose row names the session; the session is named `TO`, whose row
    ends on another session; and the stand-ins above in `<root>/ctl`."""

    def __init__(self, root: Path, *, to=TO, to_row=True, guard=GUARD, path=None):
        self.root = root
        self.sid = str(uuid.uuid4())
        self.other = str(uuid.uuid4())
        self.to = to
        self.guard = guard
        self.home = root / "home"
        self.wip = self.home / "projects" / "wip"
        self.origin = root / "origin.git"
        self.bin = root / "bin"
        self.ctl = root / "ctl"
        for d in (self.wip.parent, root / "t", self.bin, self.ctl):
            d.mkdir(parents=True, exist_ok=True)
        env = guard_strip_env(os.environ)
        if path is not None:
            env["PATH"] = path
        env.update(HOME=str(self.home), XDG_STATE_HOME=str(root / "state"),
                   XDG_CONFIG_HOME=str(root / "config"), TMPDIR=str(root / "t"),
                   LANES_WORKSTATION=HOST, LANES_CONTAINER=CONTAINER, LANES_NO_GITHUB="1",
                   LANES_NO_FETCH="1", LANES_REPO=str(self.wip), LANES_LANE=FROM,
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        self.base = env
        self._git(["init", "-q", "--bare", "-b", "main", str(self.origin)], cwd=root)
        self._git(["clone", "-q", str(self.origin), str(self.wip)], cwd=root)
        (self.wip / "lanes" / "log").mkdir(parents=True)
        rows = [_row(FROM, self.sid, "LIVE")]
        if to_row:
            rows.append(_row(to, self.other, "PAUSED"))
        self.push_register(rows, first=True)
        (self.home / ".agents").mkdir()
        (self.home / ".agents" / "workspace.yaml").write_text(
            f"repository: {self.origin}\npath: {self.wip}\n", encoding="utf-8")
        py = sys.executable
        self.lane_start = _script(self.root / "stub-lane-start", _STUB_LANE_START,
                                  PY=py, CTL=_q(self.ctl))
        self.body = _script(self.root / "stub-body", _STUB_BODY, PY=py, CTL=_q(self.ctl))
        self.edit = _script(self.root / "stub-lanes-edit", _STUB_EDIT, PY=py,
                            CTL=_q(self.ctl), REAL=_q(self.guard))
        self.offer = self.home / ".claude" / "lanes" / "offers" / self.sid
        self.extra = {"LANES_LANE_START": str(self.lane_start), "LANES_EDIT": str(self.edit)}
        self.session = guard_session(self.home, self.bin, self.wip, window=FROM,
                                     session_id=self.sid, name=to)
        self.sessions = [self.session]
        self.spare = []

    def _git(self, argv, cwd) -> str:
        return subprocess.run(["git", *argv], cwd=str(cwd), env=self.base, check=True,
                              capture_output=True, text=True).stdout

    def push_register(self, rows, first=False) -> None:
        (self.wip / "lanes" / "LANES.md").write_text(register_text(rows), encoding="utf-8")
        if first:
            (self.wip / "lanes" / "log" / "README.md").write_text("logs.\n", encoding="utf-8")
        self._git(["add", "-A"], self.wip)
        self._git(["commit", "-q", "-m", "register"], self.wip)
        self._git(["push", "-q", "origin", "main"], self.wip)

    def origin_head(self) -> str:
        return self._git(["rev-parse", "main"], self.origin).strip()

    def set(self, name: str, value="") -> None:
        (self.ctl / name).write_text(str(value), encoding="utf-8")

    def env(self, **extra) -> dict:
        merged = dict(self.extra)
        merged.update(extra)
        return self.session.env(self.base, **merged)

    def hook(self, prompt="hello", timeout=HOOK_TIMEOUT, **extra) -> Hook:
        return run_hook(["bash", str(self.guard), "guard"],
                        self.session.hook_input(prompt=prompt), self.env(**extra),
                        self.session.cwd, timeout)

    def make_offer(self) -> dict:
        """The guard's first prompt makes the offer (`guard_offer`)."""
        hook = self.hook("hello")
        record = read_record(self.offer)
        assert hook.code == 2 and OFFER in hook.text and record.get("mode") == "name-drift", \
            f"the guard made no offer for this estate: {record}\n{hook!r}"
        assert record.get("from") == FROM and record.get("to") == self.to, record
        return record

    def answer_2(self, **extra) -> Hook:
        """The person's `2`; the case's first assertion is always that the hook
        printed "BINDING" and exited 2, which today's in-hook bind never does."""
        hook = self.hook("2", **extra)
        assert not hook.killed and hook.code == 2 and BINDING in hook.err, \
            f"answer 2 did not exit 2 with BINDING: {hook!r}"
        return hook

    def record(self) -> dict:
        return read_record(self.offer)

    def outer(self, limit=10.0) -> dict:
        """The record once the outer has rewritten it with its `pid`."""
        record = _until(lambda: (lambda r: r if r.get("pid") else None)(self.record()), limit)
        assert record, f"no outer wrote its pid into the record: {self.record()}"
        return record

    def ended(self, limit=30.0) -> dict:
        """The record once the outer has written an outcome."""
        record = _until(lambda: (lambda r: r if r.get("mode") in ("bound", "bind-failed")
                                 else None)(self.record()), limit, 0.1)
        assert record, f"the bind wrote no outcome in {limit} s: {self.record()}"
        return record

    def log(self, name: str) -> list:
        path = self.ctl / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def starts(self) -> list:
        return [e for e in self.log("lane-start.log") if e["event"] == "start"]

    def release(self) -> None:
        self.set("release")

    def swap_window(self, window: str, name: str):
        """The window renamed to `window`: the stand-in answers `#W` with its
        name, so the session's live process is replaced by one in a window of
        that name (T203c's `guard_session`), with the same session id."""
        for session in self.sessions:
            session.close()
        self.session = guard_session(self.home, self.bin, self.wip, window=window,
                                     session_id=self.sid, name=name)
        self.sessions.append(self.session)
        return self.session

    def close(self) -> None:
        self.release()
        pids = set(self.spare)
        record = self.record()
        if record.get("pid", "").isdigit():
            pids.add(int(record["pid"]))
        for entry in self.log("lane-start.log") + self.log("body.log"):
            for key in ("pid", "fork", "grandchild"):
                if isinstance(entry.get(key), int):
                    pids.add(entry[key])
        for pid in list(pids):
            pids.update(_members("sid", pid))
            pids.update(_members("pgid", pid))
        for pid in pids:
            if pid != os.getpid():
                _kill(pid)
        for session in self.sessions:
            session.close()


@pytest.fixture
def estate(tmp_path, request):
    """The estate of the module's docstring, torn down with every process its
    bind left (the outer, its body, `timeout`, the stand-ins and their
    children)."""
    made = []

    def make(**kwargs) -> Estate:
        est = Estate(tmp_path / f"e{len(made)}", **kwargs)
        made.append(est)
        return est

    yield make
    for est in made:
        est.close()


def _sleeper() -> subprocess.Popen:
    """A live process in a session of its own: the stand-in for a bind's
    outer where a case writes the record itself (rows (a) to (c))."""
    return subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(300)"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def _dead_pid() -> int:
    """A pid that has exited and been reaped."""
    proc = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    proc.wait()
    return proc.pid


def _binding(est: Estate, *, started: float, bound_s=500, bounded="yes", deadline=None,
             pid=None, pidstart=None, host=HOST, container=CONTAINER, extra=()) -> list:
    """A `mode=binding` record in the keys and order the hook and the outer
    write it (contract sections 1 and 3), for rows (a) and (b)."""
    if deadline is None:
        deadline = int(started) + bound_s + 5
    lines = ["mode=binding", f"from={FROM}", f"to={est.to}", f"session={est.to}",
             f"uuid={est.sid}", f"utc={_utc(started)}", "window=testsess:@1",
             f"pane={GUARD_PANE}", "bind=1", f"started_utc={_utc(started)}",
             f"bound_s={bound_s}", f"bounded={bounded}", f"deadline_epoch={deadline}",
             f"host={host}", f"container={container}", f"out={est.offer}.bind.1.out",
             "detach=setsid"]
    if pid is not None:
        lines.append(f"pid={pid}")
    if pidstart is not None:
        lines.append(f"pidstart={pidstart}")
    return lines + list(extra)


def _timeout_argv(outer: int, sid: str):
    """The `timeout` the outer bounds its body with, as `/proc` gives its
    argv: a member of the session the outer leads."""
    for pid in _members("sid", outer):
        argv = _argv(pid)
        if argv and os.path.basename(argv[0]) == "timeout" and sid in argv:
            return pid, argv
    return None


def _renames(est: Estate, since: int = 0) -> list:
    return [c for c in est.session.tmux_calls()[since:] if c and c[0] == "rename-window"]


# ============================================================ T214: AT-F6, phase N

@pytest.mark.parametrize("mode", ["files"])
def test_answer_2_exits_2_binding_before_t0_plus_1_s_and_the_runner_sees_eof(estate, mode):
    """AT-F6 case 1: answer `2` exits 2 with "BINDING" before `T0 + 1 s`,
    asserted at twice it (section 4's rule 2), while the stand-in `lane-start`
    holds; the runner sees EOF on both pipes at once, before the stand-in
    ends; the hook itself writes nothing to the register. Under the default
    bound the record holds `bound_s=500`, `bounded=yes` and a
    `deadline_epoch` 505 s after `started_utc`, "BINDING" says "bounded at
    500 s" and to send the work again in a minute or so, and the body runs as
    `timeout -k 10 490 ... guard-bind --body <uuid>`."""
    est = estate()
    est.set("hold", 60)
    est.make_offer()
    head = est.origin_head()
    hook = est.answer_2()
    took = hook.t_exit - hook.t0
    print(f"T214 case 1: the hook exited {took:.3f} s after T0 (bound 1 s, asserted at 2 s); "
          f"EOF {max(hook.eof.values()) - hook.t_exit:+.3f} s after the exit")
    assert took < 2.0, f"answer 2 exited {took:.2f} s after T0, past T0 + 2 s: {hook!r}"
    assert set(hook.eof) == {"out", "err"}, f"the runner saw no EOF on {hook.eof}: {hook!r}"
    assert max(hook.eof.values()) - hook.t_exit < 0.5, f"EOF came late: {hook.eof}"
    assert "bounded at 500 s" in hook.err and "send your work again in a minute or so" \
        in hook.err, hook.err
    assert est.origin_head() == head, "the hook's own process wrote to the register"
    record = est.outer()
    assert not [e for e in est.log("lane-start.log") if e["event"] == "end"], \
        "the stand-in lane-start ended before the runner's EOF was asserted"
    assert record["mode"] == "binding" and record["bound_s"] == "500" \
        and record["bounded"] == "yes", record
    assert int(record["deadline_epoch"]) == _epoch(record["started_utc"]) + 505, record
    assert re.search(rf"pid {record['pid']}\b", hook.err), hook.err
    found = _until(lambda: _timeout_argv(int(record["pid"]), est.sid), 5)
    assert found, f"no timeout in the outer's session: {_members('sid', int(record['pid']))}"
    argv = found[1]
    assert argv[1:4] == ["-k", "10", "490"] and argv[-3:] == ["guard-bind", "--body", est.sid], argv


@pytest.mark.parametrize("mode", ["files"])
def test_the_bind_child_survives_a_group_kill_and_hangup_and_ends_bound(estate, mode):
    """AT-F6 case 2: the child survives a `SIGKILL` and a `SIGHUP` sent to the
    hook's whole process group, and the record ends `bound`. Its `ended_utc`
    less `started_utc` is recorded beside `bound_s`, never asserted (lane 4's
    row 37)."""
    est = estate()
    est.set("hold", 60)
    est.make_offer()
    hook = est.answer_2()
    record = est.outer()
    for sig in (signal.SIGHUP, signal.SIGKILL):
        try:
            os.killpg(hook.pgid, sig)
        except ProcessLookupError:
            pass
    assert _alive(int(record["pid"])), "the bind's outer died with the hook's group"
    est.release()
    record = est.ended()
    assert record["mode"] == "bound" and record["rc"] == "0", record
    print(f"T214 case 2: ended_utc - started_utc = "
          f"{_epoch(record['ended_utc']) - _epoch(record['started_utc'])} s "
          f"beside bound_s = {record['bound_s']} s")


@pytest.mark.parametrize("mode", ["files"])
def test_a_prompt_mid_bind_is_not_passed_and_leaves_the_record(estate, mode):
    """AT-F6 case 3: a prompt mid-bind gets "BINDING IN PROGRESS" with exit 2,
    is not passed, and the record is byte for byte unchanged."""
    est = estate()
    est.set("hold", 60)
    est.make_offer()
    est.answer_2()
    est.outer()
    before = est.offer.read_bytes()
    hook = est.hook("please do the work")
    assert hook.code == 2 and IN_PROGRESS in hook.err and NOT_SENT in hook.err, repr(hook)
    assert est.offer.read_bytes() == before, "the prompt mid-bind changed the record"
    assert len(est.starts()) == 1, "a prompt mid-bind started a second bind"


@pytest.mark.parametrize("mode", ["files"])
def test_after_bound_one_moved_then_the_next_prompt_passes(estate, mode):
    """AT-F6 case 4: after `bound`, one "MOVED" naming the lane and this
    session (lane 5's draft 7, #165 6767031889), with the owed notes, the
    record removed, and the prompt not sent; the next prompt, in the window
    now named `<to>` whose row ends on this session, exits 0. The row and the
    window's name are the test's stand-ins for what the real `lane-start
    --bind` and the guard's rename leave."""
    est = estate()
    est.make_offer()
    est.answer_2()
    record = est.ended()
    assert record["mode"] == "bound", record
    hook = est.hook("the next prompt")
    moved = f"MOVED: this window is lane {TO}, bound to this session ({est.sid}) at "
    assert hook.code == 2 and moved + record["ended_utc"] in hook.err, repr(hook)
    for note in record["note"]:
        assert f"still owed: {note}" in hook.err, (note, hook.err)
    assert not est.offer.exists(), "MOVED left the record in place"
    assert "NOT sent" in hook.err, hook.err
    est.push_register([_row(FROM, est.other, "PAUSED"), _row(TO, est.sid, "LIVE")])
    est.swap_window(TO, TO)
    hook = est.hook("and the one after")
    assert hook.code == 0 and "MOVED" not in hook.text, repr(hook)


@pytest.mark.parametrize("mode", ["files"])
def test_a_failed_bind_renames_back_keeps_the_offer_and_allows_three_attempts(estate, mode):
    """AT-F6 case 5: after a stand-in failure, the why, the window renamed back
    to `<from>`, the offer kept (`mode=name-drift`, `bind=k`), attempt 2 on
    the next `2`; after the third failure choice 2 is no longer offered, and
    a `2` typed anyway is refused with the offer kept."""
    est = estate()
    est.set("rc", 1)
    est.make_offer()
    for attempt in (1, 2, 3):
        hook = est.answer_2()
        record = est.record()
        assert record["bind"] == str(attempt) and record["mode"] in (
            "binding", "bind-failed"), record
        record = est.ended()
        assert record["mode"] == "bind-failed" and record["rc"] == "1", record
        assert "the stand-in refuses with 1" in record["why"], record
        calls = len(est.session.tmux_calls())
        hook = est.hook("after the failure")
        assert hook.code == 2 and f"THE BIND TO LANE {TO} FAILED (exit 1)" in hook.err, repr(hook)
        assert [c for c in _renames(est, calls) if c[-1] == FROM], \
            f"the window was not renamed back to {FROM}: {est.session.tmux_calls()[calls:]}"
        record = est.record()
        assert record["mode"] == "name-drift" and record["bind"] == str(attempt), record
        assert record["from"] == FROM and record["to"] == TO, record
        if attempt < 3:
            assert KEPT in hook.err and NO_LONGER_2 not in hook.err, hook.err
        else:
            assert NO_LONGER_2 in hook.err, hook.err
    hook = est.hook("2")
    assert hook.code == 2 and NO_LONGER_2 in hook.err and BINDING not in hook.err, repr(hook)
    record = est.record()
    assert record["mode"] == "name-drift" and record["bind"] == "3", record
    assert len(est.starts()) == 3, est.starts()


@pytest.mark.parametrize("mode", ["files"])
def test_a_dead_bind_outer_answers_in_progress_while_its_session_lives_then_no_outcome(
        estate, mode):
    """AT-F6 case 6: the outer killed with `-9` while the stand-in holds: its
    pid is dead, but the body, its `timeout` and the stand-in are still in the
    session it led, so a prompt, `2` among them, gets "BINDING IN PROGRESS",
    the record unchanged, and no second `guard-bind` starts. Once no process
    of that session is left, the next prompt gets "no outcome" once: exit 2,
    `name-drift`, `rc=unknown`, `ended_utc` the guard's time, the offer kept,
    and none of the five values copied (the stand-in made no pending record);
    the next `2` binds anew."""
    est = estate()
    est.set("hold", 60)
    est.make_offer()
    est.answer_2()
    record = est.outer()
    outer = int(record["pid"])
    assert _until(lambda: _timeout_argv(outer, est.sid), 5), "no body under timeout"
    _kill(outer, signal.SIGKILL)
    assert _until(lambda: not _alive(outer), 5), "the outer survived kill -9"
    assert _members("sid", outer), "nothing was left in the session the outer led"
    before = est.offer.read_bytes()
    for prompt in ("hello", "2"):
        hook = est.hook(prompt)
        assert hook.code == 2 and IN_PROGRESS in hook.err, (prompt, repr(hook))
        assert est.offer.read_bytes() == before, f"{prompt!r} changed the record"
    assert len(est.starts()) == 1 and len(list(est.offer.parent.glob(
        f"{est.sid}.bind.*.out"))) == 1, "a second guard-bind started"
    est.release()
    assert _until(lambda: not _members("sid", outer), 15), "the outer's session never emptied"
    t_before = int(time.time())
    hook = est.hook("hello")
    assert hook.code == 2 and NO_OUTCOME in hook.err, repr(hook)
    record = est.record()
    assert record["mode"] == "name-drift" and record["rc"] == "unknown", record
    assert t_before - 1 <= _epoch(record["ended_utc"]) <= int(time.time()) + 1, record
    assert record["from"] == FROM and record["to"] == TO, record
    assert not [k for k in COPIES if k in record], record
    est.set("rc", 0)
    hook = est.answer_2()
    assert est.record()["bind"] == "2", est.record()


@pytest.mark.parametrize("mode", ["files"])
def test_a_reused_bind_pid_gives_no_outcome_with_no_session_test(estate, mode):
    """AT-F6 case 6's last sentence: an altered `pidstart` reads as dead with
    no session test, "no outcome" at once, while the outer and its session
    still live."""
    est = estate()
    est.set("hold", 60)
    est.make_offer()
    est.answer_2()
    record = est.outer()
    outer = int(record["pid"])
    lines = [line for line in est.offer.read_text(encoding="utf-8").splitlines()
             if not line.startswith("pidstart=")]
    write_record(est.offer, lines + [f"pidstart={int(record['pidstart']) + 7}"])
    hook = est.hook("hello")
    assert hook.code == 2 and NO_OUTCOME in hook.err, repr(hook)
    assert f"pid, {outer}, now belongs to another process" in hook.err, hook.err
    record = est.record()
    assert record["mode"] == "name-drift" and record["rc"] == "unknown", record
    assert _alive(outer) and _members("sid", outer), "the outer or its session had ended"


@pytest.mark.parametrize("case", ["term", "ignores-term", "slow-set-row-state",
                                  "grandchild-ignores-term", "after-137", "after-trap"])
def test_a_bind_body_past_its_bound_ends_with_the_bounds_code_and_leaves_no_process(
        estate, case):
    """AT-F6 case 7, with lane 5's answers to open point 39 as lane 3 ruled them
    (R47, R48): under `LANES_BIND_BOUND_S=15` the body runs under `timeout -k
    10 5`. `[term]`: the stand-in `lane-start` holding past the bound ends
    `rc=124` at `timeout`'s TERM; `[ignores-term]`: a stand-in body that
    ignores TERM ends `rc=137` at its KILL; `[slow-set-row-state]`: the
    stand-in ends 0 at once and `set-row-state` sleeps past the bound, 124;
    `[grandchild-ignores-term]`: the body's child ignores TERM and outlives
    `timeout`'s 124, and the outer sweeps the group `timeout` led;
    `[after-137]`: the sweep after `[ignores-term]`'s 137 with such a
    grandchild; `[after-trap]`: a TERM to the outer fires its trap, which
    sweeps the same way. Each ends with its `why` and "what it wrote is not
    known", the outcome written inside `deadline_epoch`, and no process of the
    group `timeout` led left. The body binds through no `start-record` in
    either mode, so the case takes no mode id (A1)."""
    est = estate()
    extra = {"LANES_BIND_BOUND_S": "15"}
    if case == "term":
        est.set("hold", 60)
    elif case == "slow-set-row-state":
        est.set("edit-sleep", 60)
    else:
        extra["LANES_BIND_BODY"] = str(est.body)
        est.set("body-sleep", 60)
        if case in ("ignores-term", "after-137"):
            est.set("body-ignore-term")
        if case in ("grandchild-ignores-term", "after-137", "after-trap"):
            est.set("body-grandchild")
    est.make_offer()
    est.answer_2(**extra)
    record = est.outer()
    outer = int(record["pid"])
    assert record["bound_s"] == "15", record
    found = _until(lambda: _timeout_argv(outer, est.sid), 5)
    assert found and found[1][1:4] == ["-k", "10", "5"], found
    group = found[0]
    if case == "after-trap":
        time.sleep(1.0)
        _kill(outer, signal.SIGTERM)
    record = est.ended(limit=40)
    expect = {"term": "124", "ignores-term": "137", "slow-set-row-state": "124",
              "grandchild-ignores-term": "124", "after-137": "137", "after-trap": "143"}[case]
    why = BY_SIGNAL if case == "after-trap" else BY_BOUND
    assert record["mode"] == "bind-failed" and record["rc"] == expect, record
    assert why in record["why"] and UNKNOWN in record["why"], record
    assert _epoch(record["ended_utc"]) <= int(record["deadline_epoch"]), record
    assert not _members("pgid", group), f"the group timeout led ({group}) was left running"
    if case == "slow-set-row-state":
        assert [e for e in est.log("lanes-edit.log") if e["argv"][:1] == ["set-row-state"]], \
            "the bind's set-row-state never ran"


@pytest.mark.parametrize("mode", ["files"])
def test_a_live_bind_past_its_bound_that_timeout_has_not_ended_answers_2_and_names_the_pid_to_kill(
        estate, mode):
    """Row (a): a `binding` record with `bounded=yes` and `bound_s=500`, its
    `deadline_epoch` past, whose pid and `pidstart` are a live process's on
    this host: exit 2, the record unchanged, "THE BIND HAS RUN PAST ITS 500 s
    BOUND and is still running (pid <p>, started <utc>)", that its `timeout`
    has not ended it and it is likely stuck on the disk or the network, and
    what `kill <p>` costs."""
    est = estate()
    holder = _sleeper()
    est.spare.append(holder.pid)
    started = time.time() - 600
    write_record(est.offer, _binding(est, started=started, deadline=int(started) + 505,
                                     pid=holder.pid, pidstart=_stat(holder.pid)["start"]))
    before = est.offer.read_bytes()
    hook = est.hook("hello")
    assert hook.code == 2, repr(hook)
    assert (f"THE BIND HAS RUN PAST ITS 500 s BOUND and is still running (pid {holder.pid}, "
            f"started {_utc(started)})") in hook.err, hook.err
    assert "timeout` has not ended it; it is likely stuck on the disk or the network" \
        in hook.err, hook.err
    assert f"`kill {holder.pid}`" in hook.err and NOT_SENT in hook.err, hook.err
    assert est.offer.read_bytes() == before, "the record changed"


@pytest.mark.parametrize("where", ["host-files", "container-files"])
def test_a_binding_from_another_host_or_container_is_not_judged_by_its_pid_until_the_deadline_plus_60_s(
        estate, where):
    """Row (b): a `binding` record whose `host` or `container` differs from the
    guard's, with a pid dead on this host: until `deadline_epoch` plus 60 s,
    exit 2, the record unchanged, "A BIND OF THIS TRANSCRIPT IS RUNNING ON
    <host>/<container>" and "Your prompt was NOT sent"; with `bounded=no` the
    text adds that the child there may still be running and that on primary
    `bind:<to>` refuses whichever bind commits second; past it, stale with no
    copies: exit 2 once, `name-drift`, `rc=unknown`, and no rename."""
    est = estate()
    host, container = (("Elsewhere", CONTAINER) if where.startswith("host")
                       else (HOST, "other-box"))
    dead = _dead_pid()
    now = time.time()
    for bounded in ("yes", "no"):
        write_record(est.offer, _binding(est, started=now - 30, bounded=bounded,
                                         deadline=int(now) + 100, pid=dead, pidstart="1",
                                         host=host, container=container))
        before = est.offer.read_bytes()
        hook = est.hook("hello")
        assert hook.code == 2, repr(hook)
        assert f"A BIND OF THIS TRANSCRIPT IS RUNNING ON {host}/{container}" in hook.err \
            and NOT_SENT in hook.err, hook.err
        assert est.offer.read_bytes() == before, "the record changed before deadline + 60 s"
        if bounded == "no":
            assert "may still be running" in hook.err and f"`bind:{TO}`" in hook.err, hook.err
    write_record(est.offer, _binding(est, started=now - 700, deadline=int(now) - 62, pid=dead,
                                     pidstart="1", host=host, container=container))
    calls = len(est.session.tmux_calls())
    hook = est.hook("hello")
    assert hook.code == 2 and NO_OUTCOME in hook.err, repr(hook)
    record = est.record()
    assert record["mode"] == "name-drift" and record["rc"] == "unknown", record
    assert not [k for k in COPIES if k in record], record
    assert not _renames(est, calls), f"case 10 renamed the window: {_renames(est, calls)}"


def test_an_unreadable_bind_record_is_dropped_with_exit_2(estate):
    """Row (c): an offer file the guard cannot read, a truncated `binding`
    record: exit 2 with today's text (contract section 5, case 11), the record
    dropped and its `<uuid>.bind.*` files left for the next removal, so the
    next prompt meets the ordinary table, which asks afresh."""
    est = estate()
    est.offer.parent.mkdir(parents=True, exist_ok=True)
    out = est.offer.parent / f"{est.sid}.bind.1.out"
    out.write_text("an earlier attempt's output\n", encoding="utf-8")
    write_record(est.offer, ["mode=binding", f"from={FROM}", "to="])
    hook = est.hook("hello")
    assert hook.code == 2 and UNREADABLE in hook.err, repr(hook)
    assert not est.offer.exists(), "the unreadable record was not dropped"
    assert out.exists(), "case 11 removed the attempt's files"
    hook = est.hook("hello")
    assert hook.code == 2 and OFFER in hook.err, repr(hook)


def _real_estate(estate, **kwargs) -> Estate:
    """The estate with the checkout's own `lane-start` in place of the
    stand-in: the bind's real `lane-start --no-launch --bind`."""
    est = estate(**kwargs)
    est.extra["LANES_LANE_START"] = str(REPO / "lane-start")
    est.set("edit-real")
    return est


def test_two_sessions_binding_one_lane_in_files_mode_the_second_is_refused_at_the_reread(
        estate):
    """Row (d): two sessions answer `2` for one lane on the files-mode
    fixture. The bind that reaches `lane-start`'s re-read of `binding` second
    is refused there, the other record ends `bound`, and there is one
    `RESUMED` line and one stamp for the lane. Lane 4's table gives no exit
    code for the re-read, so the code seen is recorded, not asserted."""
    one = _real_estate(estate)
    two = _real_estate(estate)
    two.home, two.wip, two.origin = one.home, one.wip, one.origin
    two.offer = one.offer.parent / two.sid
    two.base.update(HOME=str(one.home), LANES_REPO=str(one.wip))
    two.push_register([_row(FROM, one.sid, "LIVE"), _row("repoA-4", two.sid, "LIVE"),
                       _row(TO, one.other, "PAUSED")])
    for session in two.sessions:
        session.close()
    two.session = guard_session(one.home, two.bin, one.wip, window="repoA-4",
                                session_id=two.sid, name=TO)
    two.sessions.append(two.session)
    one.make_offer()
    two.hook("hello")
    assert read_record(two.offer).get("mode") == "name-drift", read_record(two.offer)
    one.answer_2()
    two.answer_2()
    ends = [one.ended(60), two.ended(60)]
    modes = sorted(r["mode"] for r in ends)
    print(f"T214 row (d): the second bind's code: {[r.get('rc') for r in ends]}")
    assert modes == ["bind-failed", "bound"], ends
    log = one._git(["show", f"main:lanes/log/{TO}.md"], one.origin)
    assert log.count("RESUMED") == 1, log


@pytest.mark.parametrize("kind,code,mode", [
    (kind, code, "files") for kind in ("resume", "new") for code in (2, 75, 3, 69)],
    ids=[f"{kind}-{code}-files" for kind in ("resume", "new") for code in (2, 75, 3, 69)])
def test_the_bind_child_records_bind_failed_with_the_code_and_binds_nothing(estate, kind, code,
                                                                            mode):
    """The record's code: the child runs the real `lane-start --no-launch
    --bind`, for a resume and for a new lane the offer names; where
    `start-record` ends with 2, 75, 3 or 69, the record ends `bind-failed`
    with `rc` that code, the register holds none of the bind's lines and the
    child writes no stamp. In files mode the five copies are never written.
    `start-record`'s code is the `LANES_EDIT` stand-in's; it fails until lane
    4's `start-record` (L4-B9) as well as L5-A1."""
    est = _real_estate(estate, to=TO if kind == "resume" else "repoA-5",
                       to_row=kind == "resume")
    est.set("start-record-rc", code)
    est.make_offer()
    head = est.origin_head()
    est.answer_2()
    record = est.ended(90)
    calls = [e["argv"] for e in est.log("lanes-edit.log")]
    assert ["start-record"] == [a[0] for a in calls if a[:1] == ["start-record"]][:1], \
        f"lane-start made no start-record call: {calls}"
    assert record["mode"] == "bind-failed" and record["rc"] == str(code), record
    assert est.origin_head() == head, "the failed bind wrote to the register or stamped"
    assert not [k for k in COPIES if k in record], record


@pytest.mark.parametrize("mode", ["files"])
def test_the_bind_child_reaches_tmux_through_tmux_pane(estate, mode):
    """AT-F6 case 12: the child's untargeted `tmux` call reaches the stand-in
    with `TMUX_PANE` set to the hook's pane and its stdin on `/dev/null`."""
    est = estate()
    est.set("tmux")
    est.make_offer()
    est.answer_2()
    est.ended()
    start = est.starts()[0]
    assert start["env"]["TMUX_PANE"] == GUARD_PANE and start["env"]["TMUX"], start
    assert start["stdin"] == "/dev/null", start
    assert start["tmux"] == [0, GUARD_PANE], start
    assert ["display-message", "-p", "#{pane_id}"] in est.session.tmux_calls()


@pytest.mark.parametrize("mode", ["files"])
def test_the_bind_child_environment_is_as_lane_4_lists_it(estate, mode):
    """AT-F6 case 13: the stand-in `lane-start` sees `LANES_NO_FETCH`,
    `LANES_ACT` and `LANES_EXPECT` unset, `TMUX` and `TMUX_PANE` set,
    `LANES_WRITE_ID`, `LANES_WRITE_GENERATION` (R52) and
    `LANE_START_HANDOFF_ANSWER` unset, and `LANES_GIT_TIMEOUT=45`, each set
    in the hook's own environment. The `LANES_ACT` and `LANES_EXPECT` of the
    `set-row-state` on the lane left are primary's, T254's."""
    est = estate()
    est.make_offer()
    est.answer_2(LANES_ACT="act-0@1:g", LANES_EXPECT="row:x", LANES_WRITE_ID="w-1",
                 LANES_WRITE_GENERATION="g-1", LANE_START_HANDOFF_ANSWER="y",
                 LANES_GIT_TIMEOUT="7", LANES_NO_FETCH="1")
    est.ended()
    env = est.starts()[0]["env"]
    for key in ("LANES_NO_FETCH", "LANES_ACT", "LANES_EXPECT", "LANES_WRITE_ID",
                "LANES_WRITE_GENERATION", "LANE_START_HANDOFF_ANSWER"):
        assert env[key] is None, (key, env)
    assert env["TMUX"] and env["TMUX_PANE"] == GUARD_PANE, env
    assert env["LANES_GIT_TIMEOUT"] == "45", env


def test_the_hook_string_and_guard_timeout_are_unchanged():
    """AT-F6 case 14: the hook string and `GUARD_TIMEOUT` are byte for byte
    unchanged (plan.md, "Governed invariants"; PC-16)."""
    lines = INSTALLER.read_bytes().splitlines()
    assert b"GUARD_COMMAND='~/projects/xFactory/lanes-edit.sh guard'" in lines
    assert b"GUARD_TIMEOUT=5" in lines


@pytest.mark.parametrize("mode", ["files"])
def test_kill_of_the_bind_outer_ends_the_record_with_the_signals_code(estate, mode):
    """AT-F6 case 15: `kill <p>` on the outer mid-bind, while the stand-in
    holds, ends the record with the signal's code, 143 (lane 3's point 11),
    the `why` "stopped by a signal" and "what it wrote is not known"."""
    est = estate()
    est.set("hold", 60)
    est.make_offer()
    est.answer_2()
    record = est.outer()
    assert _until(lambda: est.starts(), 5), "the stand-in never started"
    _kill(int(record["pid"]), signal.SIGTERM)
    record = est.ended()
    assert record["mode"] == "bind-failed" and record["rc"] == "143", record
    assert BY_SIGNAL in record["why"] and UNKNOWN in record["why"], record


def _no_timeout_path(root: Path) -> str:
    """A `PATH` that holds every tool this host has but `timeout`."""
    farm = root / "no-timeout"
    farm.mkdir()
    for d in ("/usr/local/bin", "/usr/bin", "/bin"):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name == "timeout" or (farm / name).exists():
                continue
            src = os.path.join(d, name)
            if os.path.isfile(src) and os.access(src, os.X_OK):
                (farm / name).symlink_to(src)
    return str(farm)


@pytest.mark.parametrize("mode", ["files"])
def test_a_bind_with_no_timeout_says_bounded_no_and_kill_stops_its_group_once(
        estate, tmp_path, mode):
    """AT-F6 case 16: with `timeout` hidden from `PATH` and
    `LANES_BIND_BOUND_S=15`, the record says `bounded=no` and the body leads a
    process group of its own, outside the outer's. A prompt after
    `deadline_epoch`, while the stand-in still holds, gets exit 2, the record
    unchanged, "THE BIND HAS RUN PAST ITS 15 s BOUND and is still running",
    that this host has no `timeout`, so nothing stops it, what `kill <p>`
    costs, and "Your prompt was NOT sent". Then `kill <p>` stops the body's
    group and the outer writes the outcome."""
    est = estate(path=_no_timeout_path(tmp_path))
    est.set("hold", 60)
    est.make_offer()
    hook = est.answer_2(LANES_BIND_BOUND_S="15")
    record = est.outer()
    outer = int(record["pid"])
    assert record["bounded"] == "no", record
    start = _until(lambda: est.starts(), 5)
    assert start and start[0]["pgid"] != outer and start[0]["sid"] == outer, start
    deadline = int(record["deadline_epoch"])
    assert deadline == _epoch(record["started_utc"]) + 20, record
    _until(lambda: time.time() > deadline + 1, 30, 0.2)
    before = est.offer.read_bytes()
    hook = est.hook("hello")
    assert hook.code == 2 and (f"THE BIND HAS RUN PAST ITS 15 s BOUND and is still running "
                               f"(pid {outer}, started {record['started_utc']})") in hook.err, \
        repr(hook)
    assert "no `timeout`, so nothing stops it" in hook.err and f"`kill {outer}`" in hook.err \
        and NOT_SENT in hook.err, hook.err
    assert est.offer.read_bytes() == before, "the record changed"
    _kill(outer, signal.SIGTERM)
    record = est.ended()
    assert record["mode"] == "bind-failed" and BY_SIGNAL in record["why"], record
    assert not _members("pgid", start[0]["pgid"]), "the body's group was left running"


@pytest.mark.parametrize("mode", ["files"])
def test_the_bind_resume_path_makes_at_most_n_r_read_calls(estate, mode):
    """AT-F6 case 17: a counting `LANES_EDIT` stand-in sees at most `N_r` = 17
    calls on the real `lane-start --no-launch --bind`'s resume path, each a
    `lanes-edit.sh` process that makes one register read; the test fails where
    `N_r` must grow (lane 4's section, "The record, and its liveness test")."""
    est = _real_estate(estate)
    est.make_offer()
    est.answer_2()
    record = est.ended(90)
    calls = [e["argv"] for e in est.log("lanes-edit.log")]
    print(f"T214 case 17: {len(calls)} lanes-edit.sh calls on the resume path: "
          f"{[a[:1] for a in calls]}")
    assert record["mode"] == "bound", record
    assert 0 < len(calls) <= 17, calls


def _record_with(est: Estate, keys) -> None:
    """A `binding` record as the hook leaves it before the outer's start, with
    T507's keys `c`, `n_a` and `w_s_ms` as the hook copies them from
    `.head` (contract section 3)."""
    lines = _binding(est, started=time.time(), bound_s=500)
    lines = [line for line in lines if not line.startswith(("pid=", "pidstart="))]
    write_record(est.offer, lines + [f"{k}={v}" for k, v in keys.items()])


#: Case 22's configurations: `c`, `n_a` and `w_s_ms` (300, or
#: `register_rtt_ms` + 200 where it is over 100, with the service's socket;
#: 0 without), and the `bound_s` each gives (Y:5459, Y:5462; contract
#: section 4).
BOUND_CASES = {
    "c2": ({"c": 2, "n_a": 1, "w_s_ms": 0}, 500),
    "c3": ({"c": 3, "n_a": 1, "w_s_ms": 0}, 530),
    "c2-socket": ({"c": 2, "n_a": 1, "w_s_ms": 300}, 500),
    "c3-socket": ({"c": 3, "n_a": 1, "w_s_ms": 300}, 530),
    "a2-c2": ({"c": 2, "n_a": 2, "w_s_ms": 0}, 550),
    "a2-c3": ({"c": 3, "n_a": 2, "w_s_ms": 0}, 610),
    "a2-c2-socket": ({"c": 2, "n_a": 2, "w_s_ms": 300}, 560),
    "a2-c3-socket": ({"c": 3, "n_a": 2, "w_s_ms": 300}, 620),
    "c2-rtt120": ({"c": 2, "n_a": 1, "w_s_ms": 320}, 500),
    "c3-rtt270": ({"c": 3, "n_a": 1, "w_s_ms": 470}, 530),
}


@pytest.mark.parametrize("configuration", sorted(BOUND_CASES))
def test_guard_bind_computes_bound_s_from_c_n_a_and_the_service(estate, configuration):
    """AT-F6 case 22: `bound_s` as `guard-bind` computes it from the record's
    `c`, `n_a` and `w_s_ms`, which the hook copies from `.head` (R05: it
    reads no configuration), with a stand-in body that exits 0: each record's
    `deadline_epoch` is its start plus `bound_s` plus 5 s, and its body runs
    under `timeout -k 10` at `bound_s` - 10."""
    keys, bound = BOUND_CASES[configuration]
    est = estate()
    _record_with(est, keys)
    proc = subprocess.run(["bash", str(GUARD), "guard-bind", est.sid], capture_output=True,
                          text=True, env=est.env(LANES_BIND_BODY=str(est.body)),
                          cwd=str(est.wip), timeout=60)
    record = est.record()
    assert proc.returncode == 0 and record.get("mode") == "bound", \
        f"guard-bind {proc.returncode}: {record}\n{proc.stdout}{proc.stderr}"
    assert record["bound_s"] == str(bound), (configuration, record)
    assert int(record["deadline_epoch"]) == _epoch(record["started_utc"]) + bound + 5, record
    body = est.log("body.log")
    assert body and os.path.basename(body[0]["parent"][0]) == "timeout", body
    assert body[0]["parent"][1:4] == ["-k", "10", str(bound - 10)], body


@pytest.mark.parametrize("mode", ["files"])
def test_answer_2_survives_a_group_sigterm_at_the_hooks_timeout(estate, mode):
    """Lane 4's row 34, answer 2 killed partway: a stand-in `lane-start` that
    takes 10.5 s, today's measured bind, and forks a `( ... & )` child as
    `index_nudge` does. Under the runner's group SIGTERM at 5 s the detached
    form's hook has exited 2 before the timer, and its child completes, the
    record ending `bound`. The body ended on its own, so the outer sweeps
    nothing: the forked child is still alive after the outcome."""
    est = estate()
    est.set("sleep", 10.5)
    est.set("fork", 40)
    est.make_offer()
    hook = est.answer_2()
    assert hook.t_exit - hook.t0 < HOOK_TIMEOUT, repr(hook)
    _until(lambda: time.monotonic() - hook.t0 >= HOOK_TIMEOUT, 6)
    try:
        os.killpg(hook.pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    record = est.ended(30)
    assert record["mode"] == "bound" and record["rc"] == "0", record
    fork = est.starts()[0]["fork"]
    est.spare.append(fork)
    assert _alive(fork), "the body's own exit was followed by a sweep of its group"


@pytest.mark.parametrize("mode", ["files"])
def test_a_failed_bind_can_be_answered_again(estate, mode):
    """Lane 4's row 35, a failed bind answered again: after the stand-in fails
    once, the window is renamed back to `<from>`, the offer kept, and the next
    `2` starts attempt 2."""
    est = estate()
    est.set("rc", 1)
    est.make_offer()
    est.answer_2()
    est.ended()
    calls = len(est.session.tmux_calls())
    hook = est.hook("hello")
    assert hook.code == 2 and KEPT in hook.err, repr(hook)
    assert [c for c in _renames(est, calls) if c[-1] == FROM], est.session.tmux_calls()[calls:]
    assert est.record()["mode"] == "name-drift", est.record()
    est.set("rc", 0)
    est.answer_2()
    assert est.record()["bind"] == "2", est.record()
    assert _until(lambda: len(est.starts()) == 2, 10), f"attempt 2 never ran: {est.starts()}"


def _pid_start_of() -> str:
    """`pid_start_of` as `lanes-edit.sh` defines it: self-contained on purpose,
    so a test can take the function as it stands (its own comment)."""
    text = GUARD.read_text(encoding="utf-8")
    found = re.search(r"^pid_start_of\(\) \{.*?^\}\n", text, re.S | re.M)
    assert found, "lanes-edit.sh defines no pid_start_of (lane 5's T502, L5-A1)"
    return found.group(0)


@pytest.mark.parametrize("case", ["live", "dead", "reused", "unreadable"])
def test_pid_start_of_answers_live_dead_and_unreadable(tmp_path, case):
    """Lane 5's (A5; R49): `pid_start_of <pid>` exits 0 for a live pid,
    printing its start token, field 22 of `/proc/<pid>/stat`; 1 for one not
    live; and 2 where the start cannot be read or the argument is no
    well-formed pid, which every caller reads as live. `[reused]`: a live pid
    prints its own token, not the one a record holds for an earlier process
    of that number, so the caller reads it as not live."""
    function = _pid_start_of()
    script = tmp_path / "pso.sh"
    script.write_text(function + 'pid_start_of "$1"\n', encoding="utf-8")

    def ask(arg):
        done = subprocess.run(["bash", "--noprofile", "--norc", str(script), str(arg)],
                              capture_output=True, text=True, timeout=30,
                              env={"PATH": os.environ.get("PATH", os.defpath)})
        return done.returncode, done.stdout.strip()

    if case in ("live", "reused"):
        holder = _sleeper()
        try:
            code, token = ask(holder.pid)
            assert code == 0 and token == _stat(holder.pid)["start"], (code, token)
            if case == "reused":
                assert token != str(int(token) + 7)
        finally:
            holder.kill()
            holder.wait()
    elif case == "dead":
        assert ask(_dead_pid())[0] == 1
    else:
        for arg in ("", "0", "007", "12a", "12345678901"):
            assert ask(arg)[0] == 2, arg


def test_the_post_bind_refill_is_one_register_read_and_never_git(estate, tmp_path):
    """Lane 5's (A5; S36-C1): after `bound`, the refill is form 1, `register
    read --prefetch --cache <file> --files register,aliases`, with a reader's
    row, never `--for guard`, and no `git` call. On primary through the
    contract's stub `lanes-index` (T207), beside a copy of `lanes-edit.sh`
    (the copy rule, CLI4.5:885), with a `git` that logs its calls. Fails until
    L5-A2 (lane 5's T507)."""
    code = tmp_path / "code"
    stub = contract_stub(code)
    for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
        shutil.copy2(REPO / name, code / name)
    est = estate(guard=code / "lanes-edit.sh")
    real_git = shutil.which("git")
    git_log = est.ctl / "git.log"
    _script(est.bin / "git", "#!/bin/sh\nprintf '%s %s\\n' \"$(date +%s.%N)\" \"$*\" >> @LOG@\n"
            "exec @GIT@ \"$@\"\n", LOG=repr(str(git_log)), GIT=repr(real_git))
    conf = tmp_path / "lanes-index.conf"
    conf.write_text(f"register_url=postgresql:///register?host={tmp_path}/sock\n",
                    encoding="utf-8")
    est.extra["LANES_INDEX_CONFIG"] = str(conf)
    est.make_offer()
    est.answer_2()
    end = est.ended()
    assert end["mode"] == "bound", end
    done_at = [e["t"] for e in est.log("lane-start.log") if e["event"] == "end"][0]
    calls = [json.loads(line) for line in (code / ARGV_LOG).read_text(
        encoding="utf-8").splitlines()] if (code / ARGV_LOG).exists() else []
    refills = [c for c in calls if c[:2] == ["register", "read"] and "--prefetch" in c]
    assert len(refills) == 1, f"the refill was not one register read: {calls}"
    refill = refills[0]
    assert "--cache" in refill and refill[refill.index("--files") + 1] == "register,aliases" \
        and "--for" not in refill, refill
    logged = git_log.read_text(encoding="utf-8").splitlines() if git_log.exists() else []
    after = [line for line in logged if float(line.split(" ", 1)[0]) > done_at]
    assert not after, f"git was called after lane-start's end, by the refill: {after}"
    assert stub.exists()
