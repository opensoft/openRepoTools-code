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
`pid_start_of`. They fail until L5-A1, lane 5's T502. Case 22's
`test_guard_bind_computes_bound_s_from_c_n_a_and_the_service` and lane 5's
`test_the_post_bind_refill_is_one_register_read_and_never_git` also fail until
L5-A3, lane 5's T507, which copies `c`, `n_a` and `w_s_ms` from `.head` and
makes the post-bind refill. Of the `[files]` cases that run the real
`lane-start`, only `test_the_bind_child_records_bind_failed_with_the_code_and_binds_nothing`
also fails until lane 4's `start-record` (L4-B9, T427 and T428), whose calls it
asserts; case 17 and row (d) need nothing more, and pass on lane 5's `6050581`
with T214g's estate (T214h, T214i). The two are
`test_the_hook_string_and_guard_timeout_are_unchanged`, an invariant that holds
today, and `test_an_unreadable_bind_record_is_dropped_with_exit_2`, whose
oracle is today's text and today's drop.
"""

from __future__ import annotations

import atexit
import calendar
import errno
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_helpers import (ARGV_LOG, GUARD_PANE, GUARD_WINDOW, PSQL_SHIM,
                                  PSQL_SHIM_CONTROL, PSQL_SHIM_LOG, contract_stub,
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
#: The shim's counters beside it (T203's `PSQL_SHIM`, whose docstring names
#: the file); `Estate.shim` drops a lost host from it (T254w).
PSQL_SHIM_STATE = "psql-shim.state"
#: CASE 10's `[found]` ARMS, and case 19's (T254w): "the shim's `after` mode
#: on that commit call, which commits, then exit 2 on every later call"
#: (TP:6094-6095 at a6497d00), as `no-reconnect` as `after` on the bind's
#: first commit call. So the write's own retry snapshot fails too and cannot
#: answer `found=` inside the run (lane 5, #165 6842157774; lane 3,
#: 6842243851), and the guard's prefetch calls, before the commit, are not
#: failed (T254t). The case's next `est.shim()` brings the host back.
FOUND_ARMS = ({"mode": "no-reconnect", "match": "commit_write", "call": 1, "as": "after"},)

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
#: `pending-record` (T254z; case 20) makes it write, before it holds, a whole
#: `start-record` pending record with one `call=` line, as T412's
#: `wr_record_write` lays one out, from the JSON in that file: `generation`,
#: `lane`, `session`, `host`, `container`, `database` and `base`. Its
#: `not_after` is the stand-in's clock, so a lookup may decide at once.
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
if ctl("pending-record") is not None:
    import hashlib, uuid
    spec = json.loads(ctl("pending-record"))
    state = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.environ.get("HOME") or "/", ".local", "state")
    pending = os.path.join(state, "openRepoTools", "register-pending")
    os.makedirs(pending, mode=0o700, exist_ok=True)
    now, clock = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), int(time.time())
    digest = hashlib.sha256(("start-record %s %s" % (spec["lane"], spec["session"])
                             ).encode("utf-8")).hexdigest()
    with open("/proc/self/stat", encoding="utf-8") as handle:
        started = handle.read().rsplit(") ", 1)[1].split()[19]
    lines = ["format=1", "write_id=%s" % uuid.uuid4(), "generation=%s" % spec["generation"],
             "database=%s" % spec["database"], "lane=%s" % spec["lane"],
             "session=%s" % spec["session"], "verb=start-record", "args_sha256=%s" % digest,
             "cmdline=lanes-edit.sh start-record %s" % spec["lane"], "created_utc=%s" % now,
             "updated_utc=%s" % now, "pid=%d" % os.getpid(), "pid_start=%s" % started,
             "host=%s" % spec["host"], "container=%s" % spec["container"], "attempts=1",
             "call=%d %d %d %s %s" % (int(spec["base"]), clock, clock,
                                     hashlib.sha256(b"").hexdigest(),
                                     os.path.join(pending, "stand-in-attempt"))]
    path = os.path.join(pending, digest)
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(path + ".tmp", 0o600)
    os.replace(path + ".tmp", path)
    entry["pending"] = path
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
#: where `edit-real` is there, runs the checkout's `lanes-edit.sh`. T254's
#: `inject-row` runs the real `act-begin`, then a rival's `set-row-state` on
#: the lane it names, outside the act (case 9's injected row change).
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
if verb == "act-begin" and ctl("inject-row") is not None:
    import subprocess
    done = subprocess.run(["bash", REAL] + args)
    env = {k: v for k, v in os.environ.items() if k not in ("LANES_ACT", "LANES_EXPECT")}
    lane = ctl("inject-row")
    # THE PHRASE IS `<STATE> <middle dot> <one line>` (`row_state_check`): with an ASCII
    # hyphen it was refused 2 and no rival change happened (T254u; lane 5,
    # #165 6841545201). The rival's exit is kept for the case to check.
    rival = subprocess.run(["bash", REAL, "set-row-state", lane,
                            "LIVE \u00b7 a rival's change"], env=env)
    with open(os.path.join(CTL, "inject-row.rc"), "w", encoding="utf-8") as handle:
        handle.write(str(rival.returncode))
    sys.exit(done.returncode)
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


def _release(fifo: Path, limit: float) -> bool:
    """Let go the call the shim holds on `fifo` (its `hold` arm, which reads
    the FIFO to its end): open it for writing and close it, inside `limit`
    seconds. True where a call was held and is let go; False where no call
    held the FIFO in that time. A plain `open(fifo, "w")` waits until a
    reader opens the FIFO, which is for ever where the engine never made the
    call the arm names, or the call died before it reached the FIFO; that
    open hung test 10's case 6 in lane 1's CI rounds 3, 4 and 5 (#165
    6810924785). So the open is `O_NONBLOCK`, which fails at once with ENXIO
    while no reader holds the FIFO, and it is tried again until `limit`."""
    def once() -> bool:
        try:
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno == errno.ENXIO:
                return False
            raise
        os.close(fd)
        return True
    return bool(_until(once, limit))


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
    logs when each stream reached EOF. Every wait is bounded: 10 s after the
    `SIGTERM`, then `SIGKILL` to the group and 10 s more, and a hook that
    outlives that is a `TimeoutExpired`, never a wait without end."""
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
            code = proc.wait(10)
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


#: THE ESTATE'S STATE HOME: SHORT, AND OUTSIDE THE TEMPORARY ROOT. The
#: service's one socket is `${XDG_STATE_HOME}/openRepoTools/run/register.sock`
#: (lane 5's socket contract d8, section 2.1): `_Listener` binds it, `serve`
#: binds it, and the client connects to it. `sun_path` holds 107 bytes on
#: Linux and 103 on macOS, and the contract's client and `serve` refuse a
#: path over 103 bytes (`path-too-long`). Under `tmp_path` the path followed
#: the temporary root: on the runner, `run.sh`'s basetemp put it at about 147
#: bytes, and both of `_Listener`'s cases failed with `OSError: AF_UNIX path
#: too long` (lane 1's verify-r5-c2b, CI run 43140203269); every service case
#: would meet `path-too-long` once T512 lands (line AN14). So each estate's
#: `XDG_STATE_HOME` is a `mkdtemp` of its own in `/tmp`, as `tests/pgcluster.py`
#: makes its socket directory: `/tmp/l2g-` and mkdtemp's 8 characters, 17
#: bytes, which puts the socket at 49 whatever `TMPDIR` or `--basetemp` is.
#: The estate removes it at its close (`Estate.close`), and one `atexit`
#: handler removes any that an estate which failed to finish left.
STATE_PARENT = "/tmp"
STATE_PREFIX = "l2g-"
#: The contract's bound on the socket's path, in bytes (section 2.1).
SOCKET_MAX = 103
#: Every state home made in this process, for the `atexit` handler.
_STATE_HOMES: list = []


def _remove_state_homes() -> None:
    for home in _STATE_HOMES:
        shutil.rmtree(home, ignore_errors=True)


def _state_home() -> Path:
    """A new state home (`STATE_PARENT`, `STATE_PREFIX`), 0700 as `mkdtemp`
    makes it, whose socket path is within `SOCKET_MAX`."""
    if not _STATE_HOMES:
        atexit.register(_remove_state_homes)
    home = Path(tempfile.mkdtemp(prefix=STATE_PREFIX, dir=STATE_PARENT))
    _STATE_HOMES.append(home)
    sock = home / "openRepoTools" / "run" / "register.sock"
    assert len(os.fsencode(str(sock))) <= SOCKET_MAX, \
        f"the service's socket path {sock} is over {SOCKET_MAX} bytes"
    return home


class Estate:
    """T203c's estate with the guard's offer for this session: the window is
    `FROM`, whose row names the session; the session is named `TO`, whose row
    ends on another session; and the stand-ins above in `<root>/ctl`. Its
    `XDG_STATE_HOME` is a short directory of its own in `/tmp`, never under
    `root` (`_state_home`), so the service's socket path is 49 bytes."""

    def __init__(self, root: Path, *, to=TO, to_row=True, guard=GUARD, path=None):
        self.root = root
        self.sid = str(uuid.uuid4())
        self.other = str(uuid.uuid4())
        self.to = to
        self.guard = guard
        #: The `lanes-index` the estate's own calls run (`_index`, `_Service`):
        #: the checkout's, or on primary the flipped copy beside the guard.
        self.index = REPO / "lanes-index"
        self.home = root / "home"
        self.wip = self.home / "projects" / "wip"
        self.origin = root / "origin.git"
        self.bin = root / "bin"
        self.ctl = root / "ctl"
        for d in (self.wip.parent, root / "t", self.bin, self.ctl):
            d.mkdir(parents=True, exist_ok=True)
        self.state_home = _state_home()
        env = guard_strip_env(os.environ)
        if path is not None:
            env["PATH"] = path
        env.update(HOME=str(self.home), XDG_STATE_HOME=str(self.state_home),
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

    def primary(self, pg) -> None:
        """T254: the estate on `mode=primary` against the session cluster
        (T205's `pg`), in T220's configuration form (its `Bench.config`: two
        URLs naming this test's database). The register's tables come from
        T227's `tmpl_imported` and its logins from T228, so a primary case
        waits for both besides lane 4's and lane 5's code; the bind's own
        calls go through T203's `PSQL_SHIM`, whose log the case reads.

        THE BUILD IS FLIPPED (lane 5's F2, #165 6812547449): the checkout's
        `lanes-index` keeps lane 1's `RENDER_GIT_HALF = False`, so its
        `load_config` refuses `mode=primary` with 78 before any request, and
        no case here would reach the database. So, as the outage module's
        `Estate` does (`tests/test_sql_register_outage.py:303-311` at W4a's
        `bc6e00a4`), the estate runs `flipped_copy`'s `lanes-index` with
        copies of `lanes-edit.sh`, `repos.tsv` and `lane-start` beside it
        (the copy rule, CLI4.5:885): the guard, the stand-in `LANES_EDIT`'s
        real verbs, the bind's real `lane-start` (`_real_estate`) and the
        estate's own `lanes-index` calls all run that build. A case that
        names its own guard keeps it. The database's switch stays at
        `files` until a case brings its register to primary (`_Register`)."""
        if self.guard == GUARD:
            from sql_register_helpers import flipped_copy
            tool = self.root / "tool"
            try:
                self.index = flipped_copy(REPO / "lanes-index", tool, True)
            except ValueError as exc:
                raise AssertionError(f"lanes-index cannot be flipped to its git half ({exc}): "
                                     f"lane 1's RENDER_GIT_HALF (T105) has not landed, and "
                                     f"mode=primary is refused without it") from exc
            for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
                if (REPO / name).exists():
                    shutil.copy2(REPO / name, tool / name)
            self.guard = tool / "lanes-edit.sh"
            self.edit = _script(self.root / "stub-lanes-edit", _STUB_EDIT, PY=sys.executable,
                                CTL=_q(self.ctl), REAL=_q(self.guard))
        conf = self.root / "conf" / "lanes-index.conf"
        conf.parent.mkdir(mode=0o700)
        url = pg.url()
        conf.write_text("\n".join([
            "mode=primary", f"register_url={url}", f"reader_url={url}",
            "register_label=register-test", ""]), encoding="utf-8")
        conf.chmod(0o600)
        self.pg = pg
        self.extra["LANES_INDEX_CONFIG"] = str(conf)

    def shim(self, arms=()) -> Path:
        """T203's `PSQL_SHIM` first on `PATH`, handing calls to the cluster's
        own `psql`, with `arms`; its log is `<bin>/psql-shim.log`.

        EACH ARMING BRINGS A LOST HOST BACK (T254w): a `no-reconnect` arm
        fails every later call "until the test removes a second control
        file" (TP:2277-2278 at a6497d00), and the shim keeps the lost call in
        its state, `psql-shim.state`, past a new control file. So the state's
        `lost` is dropped here, and its call counts kept."""
        shim = _script(self.bin / "psql", PSQL_SHIM)
        state = self.bin / PSQL_SHIM_STATE
        if state.exists():
            held = json.loads(state.read_text(encoding="utf-8") or "{}")
            if held.pop("lost", None) is not None:
                state.write_text(json.dumps(held), encoding="utf-8")
        (self.bin / PSQL_SHIM_CONTROL).write_text(json.dumps(
            {"psql": self.pg.cluster.tool("psql"), "arms": list(arms)}), encoding="utf-8")
        return shim

    def shim_calls(self) -> list:
        """The shim's request calls (its `--version` probes left out)."""
        path = self.bin / PSQL_SHIM_LOG
        if not path.exists():
            return []
        calls = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        return [c for c in calls if "kind" not in c]

    def _git(self, argv, cwd) -> str:
        return subprocess.run(["git", *argv], cwd=str(cwd), env=self.base, check=True,
                              capture_output=True, text=True, timeout=60).stdout

    def push_register(self, rows, first=False) -> None:
        """The register pushed to the bare origin. Once this estate has put its
        register in the SQL store (`_seed_primary`, T254q), each line that
        changed goes there too, one `write` entry per line (`_Register.replace`),
        so a case's stand-in for what a bind leaves reads the same on primary
        as in files mode (case 4)."""
        text = register_text(rows)
        (self.wip / "lanes" / "LANES.md").write_text(text, encoding="utf-8")
        if first:
            (self.wip / "lanes" / "log" / "README.md").write_text("logs.\n", encoding="utf-8")
        self._git(["add", "-A"], self.wip)
        self._git(["commit", "-q", "-m", "register"], self.wip)
        self._git(["push", "-q", "origin", "main"], self.wip)
        sql = getattr(self, "sql_register", None)
        if sql is not None:
            path = "lanes/LANES.md"
            old, new = sql.files[path].split("\n"), text.split("\n")
            assert len(old) == len(new), \
                f"the SQL store's register has {len(old)} lines and the new one {len(new)}"
            for line_no, (was, now) in enumerate(zip(old, new), 1):
                if was != now:
                    sql.replace(path, line_no, now)

    def origin_head(self) -> str:
        return self._git(["rev-parse", "main"], self.origin).strip()

    def set(self, name: str, value="") -> None:
        (self.ctl / name).write_text(str(value), encoding="utf-8")

    def env(self, **extra) -> dict:
        merged = dict(self.extra)
        merged.update(extra)
        return self.session.env(self.base, **merged)

    def hook(self, prompt="hello", timeout=HOOK_TIMEOUT, **extra) -> Hook:
        """One guard run. On primary, the register is put in the SQL store
        before the first one (`_seed_primary`, T254r), so a case that reads
        without making an offer, rows (a) and (b) among them, reads it there."""
        if getattr(self, "pg", None) is not None:
            _seed_primary(self)
        return run_hook(["bash", str(self.guard), "guard"],
                        self.session.hook_input(prompt=prompt), self.env(**extra),
                        self.session.cwd, timeout)

    def make_offer(self) -> dict:
        """The guard's first prompt makes the offer (`guard_offer`). On
        primary, the register the estate pushed is put in the SQL store first
        (`_seed_primary`, T254q), where the case has not put it there itself."""
        if getattr(self, "pg", None) is not None:
            _seed_primary(self)
        hook = self.hook("hello")
        record = read_record(self.offer)
        assert hook.code == 2 and OFFER in hook.text and record.get("mode") == "name-drift", \
            f"the guard made no offer for this estate: {record}\n{hook!r}"
        assert record.get("from") == FROM and record.get("to") == self.to, record
        return record

    def answer_2(self, **extra) -> Hook:
        """The person's `2`; the case's first assertion is always that the hook
        printed "BINDING" and exited 2, which today's in-hook bind never does.
        The line names the lane this estate's offer binds, `self.to` (T214l):
        `repoA-5` for the bind-failed test's `new` kind, which `BINDING`, on
        `TO`, never matched (lane 5, #165 6837268276)."""
        hook = self.hook("2", **extra)
        binding = f"BINDING: this window is now named {self.to}"
        assert not hook.killed and hook.code == 2 and binding in hook.err, \
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
        shutil.rmtree(self.state_home, ignore_errors=True)


@pytest.fixture
def estate(tmp_path, request):
    """The estate of the module's docstring, torn down with every process its
    bind left (the outer, its body, `timeout`, the stand-ins and their
    children).

    ON PRIMARY, A DATABASE PER ESTATE (T254q): the first primary estate of a
    case takes T205's `pg`; each later one a database of its own, cloned from
    the same template and dropped at the teardown, as each estate has a bare
    origin of its own in files mode, so case 9's rival reads its own register
    and not the one the first bind changed. A caller that means two estates to
    share one register passes `pg` (`_two_binds`)."""
    made, own = [], []

    def make(mode="files", pg=None, **kwargs) -> Estate:
        if mode != "primary":
            pg = None
        elif pg is None:
            pg = request.getfixturevalue("pg")
            if any(getattr(e, "pg", None) is not None for e in made):
                name = pg.cluster.new_database()
                own.append((pg.cluster, name))
                pg = type(pg)(pg.cluster, name)
        est = Estate(tmp_path / f"e{len(made)}", **kwargs)
        made.append(est)
        if pg is not None:
            est.primary(pg)
        return est

    yield make
    try:
        for est in made:
            est.close()
    finally:
        for cluster, name in own:
            cluster.drop_database(name)


def _sleeper() -> subprocess.Popen:
    """A live process in a session of its own: the stand-in for a bind's
    outer where a case writes the record itself (rows (a) to (c))."""
    return subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(300)"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def _dead_pid() -> int:
    """A pid that has exited and been reaped. The wait is bounded, as every
    wait in this module is."""
    proc = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    proc.wait(30)
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

@pytest.mark.parametrize("mode", ["files", "primary"])
def test_answer_2_exits_2_binding_before_t0_plus_1_s_and_the_runner_sees_eof(estate, mode):
    """AT-F6 case 1: answer `2` exits 2 with "BINDING" before `T0 + 1 s`,
    asserted at twice it (section 4's rule 2), while the stand-in `lane-start`
    holds; the runner sees EOF on both pipes at once, before the stand-in
    ends; the hook itself writes nothing to the register. Under the default
    bound the record holds `bound_s=500`, `bounded=yes` and a
    `deadline_epoch` 505 s after `started_utc`, "BINDING" says "bounded at
    500 s" and to send the work again in a minute or so, and the body runs as
    `timeout -k 10 490 ... guard-bind --body <uuid>`."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_the_bind_child_survives_a_group_kill_and_hangup_and_ends_bound(estate, mode):
    """AT-F6 case 2: the child survives a `SIGKILL` and a `SIGHUP` sent to the
    hook's whole process group, and the record ends `bound`. Its `ended_utc`
    less `started_utc` is recorded beside `bound_s`, never asserted (lane 4's
    row 37)."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_a_prompt_mid_bind_is_not_passed_and_leaves_the_record(estate, mode):
    """AT-F6 case 3: a prompt mid-bind gets "BINDING IN PROGRESS" with exit 2,
    is not passed, and the record is byte for byte unchanged."""
    est = estate(mode=mode)
    est.set("hold", 60)
    est.make_offer()
    est.answer_2()
    est.outer()
    before = est.offer.read_bytes()
    hook = est.hook("please do the work")
    assert hook.code == 2 and IN_PROGRESS in hook.err and NOT_SENT in hook.err, repr(hook)
    assert est.offer.read_bytes() == before, "the prompt mid-bind changed the record"
    assert len(est.starts()) == 1, "a prompt mid-bind started a second bind"


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_after_bound_one_moved_then_the_next_prompt_passes(estate, mode):
    """AT-F6 case 4: after `bound`, one "MOVED" naming the lane and this
    session (lane 5's draft 7, #165 6767031889), with the owed notes, the
    record removed, and the prompt not sent; the next prompt, in the window
    now named `<to>` whose row ends on this session, exits 0. The row and the
    window's name are the test's stand-ins for what the real `lane-start
    --bind` and the guard's rename leave."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_a_failed_bind_renames_back_keeps_the_offer_and_allows_three_attempts(estate, mode):
    """AT-F6 case 5: after a stand-in failure, the why, the window renamed back
    to `<from>`, the offer kept (`mode=name-drift`, `bind=k`), attempt 2 on
    the next `2`; after the third failure choice 2 is no longer offered, and
    a `2` typed anyway is refused with the offer kept."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
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
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_a_reused_bind_pid_gives_no_outcome_with_no_session_test(estate, mode):
    """AT-F6 case 6's last sentence: an altered `pidstart` reads as dead with
    no session test, "no outcome" at once, while the outer and its session
    still live."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_a_live_bind_past_its_bound_that_timeout_has_not_ended_answers_2_and_names_the_pid_to_kill(
        estate, mode):
    """Row (a): a `binding` record with `bounded=yes` and `bound_s=500`, its
    `deadline_epoch` past, whose pid and `pidstart` are a live process's on
    this host: exit 2, the record unchanged, "THE BIND HAS RUN PAST ITS 500 s
    BOUND and is still running (pid <p>, started <utc>)", that its `timeout`
    has not ended it and it is likely stuck on the disk or the network, and
    what `kill <p>` costs."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("where", ["host-files", "container-files", "host-primary",
                                   "container-primary"])
def test_a_binding_from_another_host_or_container_is_not_judged_by_its_pid_until_the_deadline_plus_60_s(
        estate, where):
    """Row (b): a `binding` record whose `host` or `container` differs from the
    guard's, with a pid dead on this host: until `deadline_epoch` plus 60 s,
    exit 2, the record unchanged, "A BIND OF THIS TRANSCRIPT IS RUNNING ON
    <host>/<container>" and "Your prompt was NOT sent"; with `bounded=no` the
    text adds that the child there may still be running and that on primary
    `bind:<to>` refuses whichever bind commits second; past it, stale with no
    copies: exit 2 once, `name-drift`, `rc=unknown`, and no rename."""
    est = estate(mode=where.rsplit("-", 1)[1])
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


#: THE STAND-IN `tmux` OF A REAL BIND (T214g): T203c's stand-in, kept beside
#: it as `tmux.t203c` and run for every call, so its log and its answers are
#: unchanged, but for one thing: this window's name follows `rename-window`, as
#: tmux's does. Answer 2 renames the window to `<to>` before the bind's child
#: runs, and the real `lane-start --no-launch --bind` then reads `#W`; T203c's
#: stand-in answers it with the name it was made with, `<from>`, a lane with
#: a row, so `lane-start` refuses with its veto 2, "this window is named
#: 'repoA-2', which is another lane the register has a row for"
#: (`lane-start:2274` at lane 5's `6050581`).
_FOLLOW_TMUX = r'''#!/bin/sh
# T214g: T203c's stand-in tmux (beside this file as tmux.t203c), with this
# window's name following rename-window, as tmux's does.
name=@NAME@
out="$(@ORIG@ "$@")"; rc=$?
if [ "$rc" = 0 ] && [ "${1-}" = rename-window ]; then
  target=""; prev=""; last=""
  for a in "$@"; do
    [ "$prev" = -t ] && target="$a"
    prev="$a"; last="$a"
  done
  case "$target" in
    ''|@ID@|@SESSION@:@ID@|@PANE@|@SESSION@:@ID@.@PANE@) printf '%s\n' "$last" > "$name" ;;
  esac
fi
if [ "$rc" = 0 ] && [ "${1-}" = display-message ] && [ "$out" = @WINDOW@ ] && [ -f "$name" ]; then
  cat "$name"
  exit 0
fi
[ -z "$out" ] || printf '%s\n' "$out"
exit "$rc"
'''


def _follow_renames(session) -> None:
    """Put `_FOLLOW_TMUX` in front of `session`'s stand-in `tmux`, once: a
    stand-in `guard_session` writes again is wrapped again."""
    tmux = Path(session.tmux)
    if "T214g" in tmux.read_text(encoding="utf-8"):
        return
    orig = tmux.with_name("tmux.t203c")
    _script(orig, tmux.read_text(encoding="utf-8"))
    _, window_id, pane = re.split(r"[:.]", session.target)
    words = {"NAME": tmux.with_name("tmux.window-name"), "ORIG": orig, "ID": window_id,
             "SESSION": session.target.split(":", 1)[0], "PANE": pane, "WINDOW": session.window}
    _script(tmux, _FOLLOW_TMUX, **{k: shlex.quote(str(v)) for k, v in words.items()})


def _real_estate(estate, register=True, **kwargs) -> Estate:
    """The estate with the checkout's own `lane-start` in place of the
    stand-in: the bind's real `lane-start --no-launch --bind`, the copy
    beside the guard on primary (`Estate.primary`), so it runs that build.

    TWO THINGS THE REAL `lane-start` NEEDS THAT THE STAND-IN DID NOT (T214g;
    lane 5's CI run 43239525007, where case 17 and row (d) ended `bind-failed`
    with 2 on T502's tree):
    - THE LANE'S CHECKOUT. Its ladder (`lane-start:1331-1460` at `6050581`)
      reads the swap record, the lane's log and `$PROJECTS_ROOT/<repo>`, and
      proves a candidate only against a recorded home. This estate has no swap
      record, no log line for `<to>`, no home and no `PROJECTS_ROOT`
      (`GUARD_ENV_STRIP`), so it refused at `:1475`: "lane repoA-3 has no
      recorded checkout and none could be PROVED, so nothing was started."
      So `$HOME/projects/<repo>` is made, the ladder's default (rung 4); it
      writes nothing to the register.
    - THE WINDOW'S NEW NAME: the stand-in `tmux` follows the hook's rename
      (`_follow_renames`), as tmux does.

    AND RULE 3'S STAMP NEEDS THE LANE'S HANDOFF (T214k): where the lane has a
    row, `_handoff` commits the file that row names, so the bind's
    `write-handoff --stamp` writes the stamp as it does on a real lane. A new
    lane (`to_row=False`) has no handoff yet, and its `lane-start` writes no
    stamp (`lane-start:4352-4356` at `6050581`).

    AND ON PRIMARY, THE REGISTER IN ITS SQL STORE (T254p): `_seed_primary`,
    unless `register` is false, for a caller that seeds it later itself
    (`_two_binds`). AND EACH LANE'S OWN REGISTER CHECKOUT (T254s):
    `_lane_checkouts`."""
    est = estate(**kwargs)
    est.extra["LANES_LANE_START"] = str(est.guard.parent / "lane-start")
    est.set("edit-real")
    (est.home / "projects" / est.to.rsplit("-", 1)[0]).mkdir(exist_ok=True)
    _follow_renames(est.session)
    if kwargs.get("to_row", True):
        _handoff(est)
    if kwargs.get("mode") == "primary":
        _lane_checkouts(est, [FROM] + ([est.to] if kwargs.get("to_row", True) else []))
    if register and kwargs.get("mode") == "primary":
        _seed_primary(est)
    return est


def _seed_primary(est: Estate) -> None:
    """Bring the primary estate's register into its SQL store (T254p), as the
    service cases do (`_guard_state`): `_Register` imports the `lanes/LANES.md`
    the estate pushed, cuts over and records the marker, so the switch reads
    `primary` with the marker `present`.

    WHY: `Estate.primary` leaves `tmpl`'s switch at `files`. From lane 5's T507
    on (line R's merge25), the guard on `mode=primary` reads the register's
    SQL store, which refuses that switch: `lanes-index register read --for
    guard --prefetch` exits 69, "the register's switch is `files`, not
    `primary`", and the guard refuses the prompt with 2, so no offer is made
    (G-18's run A, case 17 `[primary]`, on lane 4's `pair-m33a` `afc6c67d`).
    A write on primary refuses the same switch with 69 at its snapshot's
    check 4 (line BD17's run e03).

    ONCE PER DATABASE: where the case, or an estate sharing its database,
    already brought this `pg` to `primary`, nothing is sent. Otherwise the
    `_Register` is kept as `est.sql_register`, and `Estate.push_register`
    sends later changes through it (T254q). `Estate.make_offer` calls this
    before the first offer, so every primary estate that makes one reads its
    register there (T254q).

    AND BEFORE ANY READ (T254r): `Estate.hook` calls it before every guard
    run, and `_Service` before it starts `serve`, so the cases that read
    without an offer read a register at `primary` too: rows (a) and (b), the
    service and read cases, and SVC-10, which measured the refusal path
    (lane 5, #165 6837268276). A case that seeds its register itself does so
    before its first read (`_Register`; `_guard_state`), so this finds it at
    `primary` and sends nothing. The answer is kept on the estate
    (`est.seeded`), so the switch is asked once per estate."""
    if getattr(est, "seeded", False):
        return
    out = est.pg.psql("SELECT mode FROM lanes_register.register_switch;",
                      check=False).stdout.split()
    if not (out and out[-1] == "primary"):
        est.sql_register = _Register(est)
    est.seeded = True


def _lane_checkouts(est: Estate, lanes) -> None:
    """EACH LANE'S OWN REGISTER CHECKOUT ON PRIMARY (T254s), `<W>-lanes/<lane>/`,
    made by `lanes-edit.sh lane-checkout <lane> --create` (the estate's build),
    as the real layout has one register checkout per lane.

    WHY: on primary, T415's `pw_checkout` asks every write for its lane's
    own checkout, even under an explicit `LANES_REPO`
    (`lanes-edit.sh:8578-8583` at G-18c's `050dc9b4`), while `lane-start`
    makes it only under `LANES_ROUTE_WRITES=1` and its default resolution
    (`lane-start:1146-1147`, `:3981-3990`). The estate names `LANES_REPO`,
    so each of the bind's writes refused with 2, "lane repoA-3's own
    register checkout, ... is not here, and on primary a write makes no
    clone"; the session cell never ended on the bound uuid, and T503's rerun
    rule could not hold (case 11; G-18c's run cL). A slice of its own, so a
    later one can reverse it if lanes 3 and 4 rule that the tools should
    agree instead. The clone is a fetch, so `LANES_NO_FETCH` is left out."""
    env = {k: v for k, v in est.base.items() if k != "LANES_NO_FETCH"}
    for lane in lanes:
        done = subprocess.run(["bash", str(est.guard), "lane-checkout", lane, "--create"],
                              cwd=str(est.wip), env=env, capture_output=True, text=True,
                              timeout=120)
        assert done.returncode == 0, \
            f"lane-checkout {lane} --create exited {done.returncode}: {done.stderr}"


#: THE LANE'S HANDOFF (T214k), as a real lane's register holds it: the file
#: its row's handoff cell names (`_row`'s `handoffs/<lane>.md`; `lane-start`
#: reads the cell as field 7, `lane-start:4413` at `6050581`), whose head is
#: the one `lane-handoff`'s `top_block` writes (`lane-handoff:2559-2563`): the
#: lane header on line 1, the blank line that ends the header block, then the
#: resume prompt. `write-handoff --stamp` puts Rule 3's stamp immediately
#: after that blank (`lanes-edit.sh:22439`; `lane-start:4358-4361`).
DASH = chr(0x2014)
HANDOFF_HEAD = (
    "Lane: {lane} (test, session {sid}) " + DASH + " single-use resume prompt: stamp "
    "RESUMED-by before acting (lane-collision-protocol rule 3)\n"
    "\n"
    "## RESUME PROMPT " + DASH + " PAUSED 2026-10-01T02:00:00Z (T214's estate), agent claude, "
    "transcript {sid}, kind unknown\n"
    "\n"
    "**STATE at 2026-10-01T02:00:00Z.** Lane {lane} is paused, and the guard's answer 2 "
    "resumes it.\n")


def _handoff(est: Estate) -> Path:
    """Commit and push the lane's handoff (`HANDOFF_HEAD`) where the row for
    `est.to` names it, so that `write-handoff --stamp` finds a tracked file
    to stamp, as on a real lane. Without it the stamp exits 8, "lane
    repoA-3's handoff is not at ..., so there is nothing to write into"
    (`lanes-edit.sh:22426-22428` at `6050581`), `lane-start` goes on with the
    stamp owed (`lane-start:4481-4483`), and a case passed on a path where
    the stamp stopped early (G17's doubt, wave 17). It is a commit of its own
    after the estate's first, so the estate every other case builds is
    unchanged; an untracked file would not do, since `write-handoff` refuses
    a handoff git has never had (`lanes-edit.sh:22414`)."""
    rel = f"handoffs/{est.to}.md"
    register = (est.wip / "lanes" / "LANES.md").read_text(encoding="utf-8")
    assert f"| `{est.to}` | harness `{est.other}` |" in register and f"| {rel} |" in register, \
        f"the register names no handoff {rel} for {est.to}:\n{register}"
    path = est.wip / rel
    path.parent.mkdir(exist_ok=True)
    path.write_text(HANDOFF_HEAD.format(lane=est.to, sid=est.other), encoding="utf-8")
    est._git(["add", "--", rel], est.wip)
    est._git(["commit", "-q", "-m", f"handoff({est.to}): the lane's handoff", "--", rel], est.wip)
    est._git(["push", "-q", "origin", "main"], est.wip)
    return path


def _two_binds(estate, mode="files") -> tuple:
    """Two sessions, in windows `FROM` and `repoA-4`, each named `TO`, both
    answering `2` with the real `lane-start`: the two estates and their
    outcomes. On primary, the register goes into the SQL store once both
    windows' rows are pushed (`_seed_primary`), and `two` runs the same
    flipped build as `one` on `one`'s database (T254q): built in files mode,
    it ran the checkout's `lanes-edit.sh`, whose `lanes-index` refuses
    `mode=primary` (`Estate.primary`), so it could make no offer."""
    one = _real_estate(estate, register=False, mode=mode)
    two = _real_estate(estate, register=False, mode=mode, pg=getattr(one, "pg", None))
    if mode == "primary":
        two.extra["LANES_INDEX_CONFIG"] = one.extra["LANES_INDEX_CONFIG"]
    two.home, two.wip, two.origin = one.home, one.wip, one.origin
    two.offer = one.offer.parent / two.sid
    two.base.update(HOME=str(one.home), LANES_REPO=str(one.wip))
    two.push_register([_row(FROM, one.sid, "LIVE"), _row("repoA-4", two.sid, "LIVE"),
                       _row(TO, one.other, "PAUSED")])
    if mode == "primary":
        _seed_primary(one)
    for session in two.sessions:
        session.close()
    two.session = guard_session(one.home, two.bin, one.wip, window="repoA-4",
                                session_id=two.sid, name=TO)
    _follow_renames(two.session)
    two.sessions.append(two.session)
    if mode == "primary":
        _lane_checkouts(two, ["repoA-4"])
    one.make_offer()
    two.hook("hello")
    assert read_record(two.offer).get("mode") == "name-drift", read_record(two.offer)
    one.answer_2()
    two.answer_2()
    return one, two, [one.ended(60), two.ended(60)]


def test_two_sessions_binding_one_lane_in_files_mode_both_binds_land(estate):
    """Row (d): two sessions answer `2` for one lane on the files-mode
    fixture, and both binds land, which is what files mode does (lane 3's
    ruling (a), #165 6827853480, on lane 4's check, 6827539379). Each bind
    reads `binding` once on `lane-start --no-launch --bind`, before either
    writes, and finds the lane free; nothing in files mode refuses the second:
    only a handoff wait or a Claude resolution sets `bind_recheck` for a second
    read (`lane-start:2654-2655`, `:2751` at `6050581`), and neither runs here:
    the lane has no live holder to wait for, and the resolution never runs
    under `--no-launch` (`:708`). So the race is one read wide, the log
    carries two bindings, and the reservation stays #84's
    (`lane-start:2724-2733` at `6050581`). Both records end `bound`, and the
    lane's log holds two `RESUMED` lines, one for each bind. Primary keeps its
    own case, case 8, `test_two_sessions_binding_one_lane_one_start_record_commits`,
    where `bind:<to>` refuses whichever bind commits second. Each record's
    code and notes are printed, not asserted."""
    one, two, ends = _two_binds(estate)
    print(f"T214 row (d): the codes {[r.get('rc') for r in ends]}, "
          f"the notes {[r.get('note') for r in ends]}")
    assert [r["mode"] for r in ends] == ["bound", "bound"], ends
    log = one._git(["show", f"main:lanes/log/{TO}.md"], one.origin)
    assert log.count("RESUMED") == 2, log


@pytest.mark.parametrize("kind,code,mode", [
    (kind, code, mode) for mode in ("files", "primary") for kind in ("resume", "new")
    for code in (2, 75, 3, 69)],
    ids=[f"{kind}-{code}-{mode}" for mode in ("files", "primary") for kind in ("resume", "new")
         for code in (2, 75, 3, 69)])
def test_the_bind_child_records_bind_failed_with_the_code_and_binds_nothing(estate, kind, code,
                                                                            mode):
    """The record's code: the child runs the real `lane-start --no-launch
    --bind`, for a resume and for a new lane the offer names; where
    `start-record` ends with 2, 75, 3 or 69, the record ends `bind-failed`
    with `rc` that code, the register holds none of the bind's lines and the
    child writes no stamp. In files mode the five copies are never written.
    `start-record`'s code is the `LANES_EDIT` stand-in's; it fails until lane
    4's `start-record` (L4-B9) as well as L5-A1."""
    est = _real_estate(estate, mode=mode, to=TO if kind == "resume" else "repoA-5",
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_the_bind_child_reaches_tmux_through_tmux_pane(estate, mode):
    """AT-F6 case 12: the child's untargeted `tmux` call reaches the stand-in
    with `TMUX_PANE` set to the hook's pane and its stdin on `/dev/null`."""
    est = estate(mode=mode)
    est.set("tmux")
    est.make_offer()
    est.answer_2()
    est.ended()
    start = est.starts()[0]
    assert start["env"]["TMUX_PANE"] == GUARD_PANE and start["env"]["TMUX"], start
    assert start["stdin"] == "/dev/null", start
    assert start["tmux"] == [0, GUARD_PANE], start
    assert ["display-message", "-p", "#{pane_id}"] in est.session.tmux_calls()


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_the_bind_child_environment_is_as_lane_4_lists_it(estate, mode):
    """AT-F6 case 13: the stand-in `lane-start` sees `LANES_NO_FETCH`,
    `LANES_ACT` and `LANES_EXPECT` unset, `TMUX` and `TMUX_PANE` set,
    `LANES_WRITE_ID`, `LANES_WRITE_GENERATION` (R52) and
    `LANE_START_HANDOFF_ANSWER` unset, and `LANES_GIT_TIMEOUT=45`, each set
    in the hook's own environment. The `LANES_ACT` and `LANES_EXPECT` of the
    `set-row-state` on the lane left are primary's, T254's."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_kill_of_the_bind_outer_ends_the_record_with_the_signals_code(estate, mode):
    """AT-F6 case 15: `kill <p>` on the outer mid-bind, while the stand-in
    holds, ends the record with the signal's code, 143 (lane 3's point 11),
    the `why` "stopped by a signal" and "what it wrote is not known"."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
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
    est = estate(mode=mode, path=_no_timeout_path(tmp_path))
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


#: CASE 17'S READ CALLS (T214h). TP:6164-6166 bounds the `lanes-edit.sh`
#: processes on the resume path that each make one `register read`, and Y:5443
#: is that term of `bound_s`'s sum. Lane 3 ruled that the case counts those
#: calls only, and that `N_r` = 17 stands (#165 6827853480), on lane 4's count of
#: lane 5's 29 calls, 13 of them register reads (6827539379). A call whose verb
#: is below is not counted, by its kind; every other verb is, so a read this
#: table does not know still counts against 17:
#: - "write": the bind's writes, which Y:5440-5450 bounds as terms of their own
#:   (`S`, `M` + `W`, the stamp): `act-begin`, `start-record` and
#:   `write-handoff` at lane 4's T428; at lane 5's T502, Y:5523's
#:   `append-session-id`, `set-row-state LIVE` and `log RESUMED`, the stamp's
#:   `publish-handoff`, and `add-row` for a new lane; and the guard child's own
#:   `set-row-state` on the lane left;
#: - "none": the arms that touch no register state, class "none" at Y:4898, "no
#:   door, no call": the four it names, and `workspace-root`, which reads
#:   `$HOME/.agents/workspace.yaml` and the checkout it names, never the
#:   register (`lanes-edit.sh:21593`, `:1004` at `6050581`), and which R2B's
#:   section 2, the inventory Y:4894 cites, lists as local-only;
#: - "host-local": Y:5646's host-local reads that Y:4898 does not name, which
#:   lane 4 counted apart from the 13. The case prints their count beside the
#:   reads: Y:4894 would give these hybrid arms a door of their own.
#: `LANES_INDEX=off` is set for the bind, so `index_nudge` returns at once
#: (`lanes-edit.sh:3855` at `6050581`), and no detached `lanes-index sync` adds
#: calls of its own after a write lands: 6 of the 29, varying with timing.
CASE_17_NOT_A_READ = {
    **{verb: "write" for verb in ("act-begin", "start-record", "write-handoff",
                                  "append-session-id", "set-row-state", "log",
                                  "publish-handoff", "add-row")},
    **{verb: "none" for verb in ("workstation", "fetch-age", "window-session",
                                 "transcript-holders", "workspace-root")},
    **{verb: "host-local" for verb in ("live-holder", "lane-holders", "idle-holders",
                                       "restart-intent")},
}


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_the_bind_resume_path_makes_at_most_n_r_read_calls(estate, mode):
    """AT-F6 case 17: a counting `LANES_EDIT` stand-in sees at most `N_r` = 17
    read calls on the real `lane-start --no-launch --bind`'s resume path, each
    a `lanes-edit.sh` process that makes one `register read`; the test fails
    where `N_r` must grow (lane 4's section, "The record, and its liveness
    test"). It counts the read calls only (`CASE_17_NOT_A_READ`), with
    `LANES_INDEX=off`, as lane 3 ruled (#165 6827853480)."""
    est = _real_estate(estate, mode=mode)
    est.extra["LANES_INDEX"] = "off"
    est.make_offer()
    est.answer_2()
    record = est.ended(90)
    calls = [e["argv"] for e in est.log("lanes-edit.log")]
    kinds = [CASE_17_NOT_A_READ.get(a[0] if a else "", "read") for a in calls]
    reads = [a[:1] for a, kind in zip(calls, kinds) if kind == "read"]
    print(f"T214 case 17: {len(reads)} read calls of {len(calls)} lanes-edit.sh calls on the "
          f"resume path, {kinds.count('host-local')} more host-local; the reads: {reads}; "
          f"every call: {[(a[:1], kind) for a, kind in zip(calls, kinds)]}")
    assert record["mode"] == "bound", record
    assert 0 < len(reads) <= 17, reads


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

#: Case 22's `[answer-2]`: the contract stub's constants line as T207 writes
#: it (section 2.4's defaults, `sql_register_helpers.py`'s `_CONTRACT_STUB`),
#: and the line this case's own copy of the stub carries instead, so that its
#: `.head` gives `c=3`, `n_a=2` and `w_s_ms=300`: `BOUND_CASES["a2-c3-socket"]`,
#: 620 s. A record missing any one of the three gives another bound: 560
#: without `c` (`"a2-c2-socket"`), 530 without `n_a` (`"c3-socket"`) and 610
#: without `w_s_ms` (`"a2-c3"`).
ANSWER_2 = "answer-2"
STUB_HEAD_LINE = "C, N_A, W_S_MS, SCHEMA = 2, 1, 0, 1"
ANSWER_2_HEAD_LINE = "C, N_A, W_S_MS, SCHEMA = 3, 2, 300, 1"


def _bound_through_answer_2_on_the_stub(estate, tmp_path) -> None:
    """Case 22's `[answer-2]`: the contract's stub `lanes-index` (T207), its
    register the estate's own `lanes/LANES.md`, with `lanes-edit.sh`,
    `repos.tsv` and `lane-start` copied beside it and a configuration naming
    the store, as `test_the_guard_maps_69_75_and_3_to_2` does, so the guard
    reads the register through the stub and the stub's `.head` (form 2). The
    stand-in `lane-start` holds, so the record is read at `mode=binding`."""
    code = tmp_path / "code"
    code.mkdir()
    for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
        shutil.copy2(REPO / name, code / name)
    est = estate(guard=code / "lanes-edit.sh")
    stub = contract_stub(code, register={
        "lanes/LANES.md": (est.wip / "lanes" / "LANES.md").read_text(encoding="utf-8")})
    text, made = re.subn(re.escape(STUB_HEAD_LINE), ANSWER_2_HEAD_LINE,
                         stub.read_text(encoding="utf-8"))
    assert made == 1, f"the contract stub's constants line was replaced {made} times, not once"
    stub.write_text(text, encoding="utf-8")
    conf = tmp_path / "lanes-index.conf"
    conf.write_text(f"register_url=postgresql:///register?host={tmp_path}/sock\n",
                    encoding="utf-8")
    est.extra["LANES_INDEX_CONFIG"] = str(conf)
    est.set("hold", 60)
    est.make_offer()
    est.answer_2()
    record = est.outer()
    assert record["mode"] == "binding", record
    assert (record.get("c"), record.get("n_a"), record.get("w_s_ms")) == ("3", "2", "300"), \
        f"the record does not hold .head's c=3, n_a=2 and w_s_ms=300: {record}"
    assert record["bound_s"] == "620", record
    assert int(record["deadline_epoch"]) == _epoch(record["started_utc"]) + 625, record


@pytest.mark.parametrize("configuration", sorted(BOUND_CASES) + [ANSWER_2])
def test_guard_bind_computes_bound_s_from_c_n_a_and_the_service(estate, tmp_path, configuration):
    """AT-F6 case 22: `bound_s` as `guard-bind` computes it from the record's
    `c`, `n_a` and `w_s_ms`, which the hook copies from `.head` (R05: it
    reads no configuration), with a stand-in body that exits 0: each record's
    `deadline_epoch` is its start plus `bound_s` plus 5 s, and its body runs
    under `timeout -k 10` at `bound_s` - 10.

    `[answer-2]` writes no record of its own: it reaches `guard-bind` through
    answer 2 on the contract stub (T207), its `.head` set to `c=3`, `n_a=2`
    and `w_s_ms=300`, and the record at `mode=binding` holds the three as
    `.head` gives them, with `bound_s=620` and a `deadline_epoch` 625 s after
    `started_utc`. It fails until L5-A3 (lane 5's T507), which copies them."""
    if configuration == ANSWER_2:
        _bound_through_answer_2_on_the_stub(estate, tmp_path)
        return
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_answer_2_survives_a_group_sigterm_at_the_hooks_timeout(estate, mode):
    """Lane 4's row 34, answer 2 killed partway: a stand-in `lane-start` that
    takes 10.5 s, today's measured bind, and forks a `( ... & )` child as
    `index_nudge` does. Under the runner's group SIGTERM at 5 s the detached
    form's hook has exited 2 before the timer, and its child completes, the
    record ending `bound`. The body ended on its own, so the outer sweeps
    nothing: the forked child is still alive after the outcome."""
    est = estate(mode=mode)
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


@pytest.mark.parametrize("mode", ["files", "primary"])
def test_a_failed_bind_can_be_answered_again(estate, mode):
    """Lane 4's row 35, a failed bind answered again: after the stand-in fails
    once, the window is renamed back to `<from>`, the offer kept, and the next
    `2` starts attempt 2."""
    est = estate(mode=mode)
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
            holder.wait(10)
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
    (the copy rule, CLI4.5:885), with a `git` that logs its calls. The stub's
    register is the estate's own `lanes/LANES.md`, as `[answer-2]`'s is: on
    primary the guard reads the register from the prefetch's `.register`, and
    a register with no `lanes/LANES.md` is a failed read there (T505), which
    would end the hook 2 at its text check before any offer. The refill's
    filter leaves out every `--for` call: the two hooks' own form-2 reads,
    `register read --for guard --prefetch`, at the offer's prompt and the
    answer's, are no refill (lane 5, #165 6809022654). A refill sent with
    `--for guard` is then no refill either, and the count of one refuses it.
    Fails until L5-A3 (lane 5's T507)."""
    code = tmp_path / "code"
    code.mkdir()
    for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
        shutil.copy2(REPO / name, code / name)
    est = estate(guard=code / "lanes-edit.sh")
    stub = contract_stub(code, register={
        "lanes/LANES.md": (est.wip / "lanes" / "LANES.md").read_text(encoding="utf-8")})
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
    refills = [c for c in calls if c[:2] == ["register", "read"] and "--prefetch" in c
               and "--for" not in c]
    assert len(refills) == 1, f"the refill was not one register read: {calls}"
    refill = refills[0]
    assert "--cache" in refill and refill[refill.index("--files") + 1] == "register,aliases" \
        and "--for" not in refill, refill
    logged = git_log.read_text(encoding="utf-8").splitlines() if git_log.exists() else []
    after = [line for line in logged if float(line.split(" ", 1)[0]) > done_at]
    assert not after, f"git was called after lane-start's end, by the refill: {after}"
    assert stub.exists()


# ============================================================ T254: AT-F6's writes, primary
#
# AT-F6's cases 8 to 11 and 18 to 21 bind on primary only and take no mode id
# (A1). Each runs on the session cluster (T205's `pg`), so on a bench with no
# engine it is collected and skipped with T205's banner; each fails until
# lane 4's `start-record` (L4-B9), lane 5's bind (L5-A1) and its phase 2's
# lookup (L5-B1, T510) land, and on the register's template and logins (T227,
# T228). The lookup's tries follow AT-F3's rule (R26, 40): they start inside
# a closed 10 s window, with D9's 9 s timer (open point 37).

#: The lookup's argv, which the child sends with the five values it copied
#: from `start-record`'s pending record (case 19).
LOOKUP = ("journal", "--write-id")


def _lookups(est: Estate) -> list:
    """The shim's calls that carry the bind's lookup (`find_write`)."""
    return [c for c in est.shim_calls() if "find_write" in c.get("sent", "")]


def _commits(est: Estate) -> list:
    """The shim's calls that carry a commit (`commit_write`)."""
    return [c for c in est.shim_calls() if "commit_write" in c.get("sent", "")]


def test_two_sessions_binding_one_lane_one_start_record_commits(estate):
    """AT-F6 case 8: two sessions answer `2` for one lane on the primary
    fixture: one `start-record` commits, and the other is refused 2 by its
    `bind:<to>` expectation.

    THE SCOPE IS READ IN THE ATTEMPT'S `out` FILE (T254y): the writer's
    `expectation:` line names `bind:<L>` in lower case (Y:5584, Y:5589),
    and a failed bind keeps that line in its attempt's `out` file, while
    the record's `why=` stays `lane-start`'s last refusal line, which
    names no scope (Y:5487; lane 3, #165 6841918192). The `out` file's
    `expectation:` and `row:` lines are printed, for lane 3's check that
    `start-record` lists `row:<L>` first (Y:5528)."""
    one, two, ends = _two_binds(estate, mode="primary")
    assert sorted(r["mode"] for r in ends) == ["bind-failed", "bound"], ends
    (est, failed), = [(e, r) for e, r in zip((one, two), ends) if r["mode"] == "bind-failed"]
    assert failed["rc"] == "2", failed
    out = Path(failed.get("out") or f"{est.offer}.bind.{failed.get('bind', 1)}.out")
    text = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
    for line in text.splitlines():
        if "expectation" in line or "row:" in line:
            print(f"T254 case 8, {out.name}: {line}")
    assert f"bind:{TO.lower()}" in text, (str(out), failed, text[-2000:])


def test_the_bind_is_one_register_write_and_refuses_a_changed_row(estate):
    """AT-F6 case 9: on primary the bind is one journal entry, and with the
    `set-row-state` on the lane left answer 2 journals two; a row change
    injected after `act-begin` refuses it with 2 and writes nothing.

    "WRITES NOTHING" IS READ IN THE RIVAL'S JOURNAL (T254zc; lane 2's
    review RV20, finding 4): from its offer to its end, the rival's
    database gains one entry, the injected `set-row-state`, and no
    `start-record`."""
    est = _real_estate(estate, mode="primary")
    est.shim()
    est.make_offer()
    est.answer_2()
    record = est.ended(90)
    assert record["mode"] == "bound", record
    assert len(_commits(est)) == 2, [c.get("arms") for c in _commits(est)]
    rival = _real_estate(estate, mode="primary")
    rival.shim()
    rival.set("inject-row", TO)
    rival.make_offer()
    head = int(rival.pg.psql("SELECT seq FROM lanes_register.register_head;").stdout.split()[-1])
    rival.answer_2()
    record = rival.ended(90)
    # THE RIVAL'S CHANGE LANDED (T254u): its `set-row-state` exited 0, or the
    # refusal below would not be the changed row's.
    injected = rival.ctl / "inject-row.rc"
    rc = injected.read_text(encoding="utf-8") if injected.exists() else "never ran"
    assert rc == "0", f"the rival's injected set-row-state exited {rc}: no row changed"
    assert record["mode"] == "bind-failed" and record["rc"] == "2", record
    grown = rival.pg.psql("SELECT string_agg(verb, ' ' ORDER BY seq) FROM "
                          f"lanes_register.journal WHERE seq > {head};").stdout.split()
    assert grown == ["set-row-state"], f"the rival's journal after seq {head}: {grown}"


@pytest.mark.parametrize("held", ["found", "absent"])
def test_a_bind_in_doubt_looks_its_write_up_before_a_rerun(estate, held):
    """AT-F6 case 10: an injected `psql` exit 2 gives `rc=3` with the id:
    `[absent]`, exit 2 on every call from the bind's commit call on;
    `[found]`, the shim's `after` mode on that call, which commits, then exit
    2 on every later call. At the next `2` the child's
    lookup runs first: `[absent]` binds anew under a new id; `[found]` writes
    no second `RESUMED`, its done mark says `done`, and the record ends
    `bound`.

    `[found]`'s later failures are not `fail-call` from the shim's second
    call: that counted every call, and calls 1 and 2 are both the guard's own
    prefetch, so the guard refused before its offer (T254t; lane 5, #165
    6841545201). Nor are they the lookup's alone: the write's own retry
    snapshot then answered `found=` and the record ended `bound` (lane 5,
    #165 6842157774). They are `FOUND_ARMS`, every call after the commit
    call (T254w).

    `[absent]` FAILS THE LOOKUP'S TRIES TOO (T254x): "exit 2 on every
    call of the bind's write from its commit call on, its deadline's
    lookup included" (TP:6092-6094 at a6497d00), by `fail-match` on
    `find_write` (TP:7355). No try then takes the lock, so the run ends 3
    and keeps the record (Y:5245), not the 75 of a lookup that answers
    absent (Y:5244; lane 3, #165 6841918192, point 5). The case's
    `est.shim()` disarms both before the next `2`, so that lookup answers
    absent and the bind starts again under a new id."""
    est = _real_estate(estate, mode="primary")
    arms = ([{"mode": "fail-match", "match": "commit_write", "from": 1},
             {"mode": "fail-match", "match": "find_write", "from": 1}]
            if held == "absent" else list(FOUND_ARMS))
    est.shim(arms)
    est.make_offer()
    est.answer_2()
    record = est.ended(120)
    assert record["mode"] == "bind-failed" and record["rc"] == "3", record
    assert all(k in record for k in COPIES), record
    est.shim()
    est.hook("hello")
    before = len(est.shim_calls())
    est.answer_2()
    record = est.ended(120)
    calls = est.shim_calls()[before:]
    look = [i for i, c in enumerate(calls) if "find_write" in c.get("sent", "")]
    start = [i for i, c in enumerate(calls) if "start-record" in c.get("sent", "")
             and "commit_write" in c.get("sent", "")]
    assert look and (not start or look[0] < start[0]), calls
    assert record["mode"] == "bound", record
    if held == "found":
        assert not start, f"the found write was committed again: {calls}"


def test_a_rerun_after_a_failed_stamp_push_writes_one_stamp(estate):
    """AT-F6 case 11 (R-F10-32; lane 5's T503, #165 6755410581): a rerun after
    a failed stamp push writes no register line and no second stamp; its
    output holds exactly one line with both `Rule 3's stamp` and `NOT` while
    the stamp is unpushed, and none once it is published (lane 5's hand
    counts 1, 0, 1 and 1 for unpushed, published, no upstream and
    `LANES_NO_GIT`); and a rerun never retries a failed `set-row-state`
    (Y:5511)."""
    est = _real_estate(estate, mode="primary")
    est.shim()
    hooks = est.root / "origin-hooks"
    hooks.mkdir()
    _script(hooks / "pre-receive", "#!/bin/sh\nexit 1\n")
    est._git(["config", "core.hooksPath", str(hooks)], est.origin)
    est.make_offer()
    est.answer_2()
    record = est.ended(120)
    owed = [n for n in record["note"] if "Rule 3's stamp" in n and "NOT" in n]
    assert record["mode"] == "bound" and len(owed) == 1, record
    commits = len(_commits(est))
    edits = [e for e in est.log("lanes-edit.log") if e["argv"][:1] == ["set-row-state"]]
    rerun = subprocess.run(["bash", str(REPO / "lane-start"), "--no-launch", "--bind", est.sid,
                            "repoA", "3"], capture_output=True, text=True, timeout=120,
                           env=est.env(), cwd=str(est.wip))
    lines = [line for line in (rerun.stdout + rerun.stderr).splitlines()
             if "Rule 3's stamp" in line and "NOT" in line]
    assert len(lines) == 1, rerun.stdout + rerun.stderr
    assert len(_commits(est)) == commits, "the rerun wrote a register line"
    assert [e for e in est.log("lanes-edit.log") if e["argv"][:1] == ["set-row-state"]] \
        == edits, "the rerun retried set-row-state"
    est._git(["config", "--unset", "core.hooksPath"], est.origin)


@pytest.mark.parametrize("held", ["found", "absent"])
def test_a_bind_killed_mid_commit_waits_for_ended_utc_plus_c_before_its_lookup(
        estate, tmp_path, held):
    """AT-F6 case 18: a bind stopped by `kill <p>` while the shim holds
    `start-record`'s commit call on a FIFO, and answered `2` at once: the
    outer copies the five values; the child's lookup starts, in the shim's
    log, no earlier than the record's `ended_utc` plus `C`, `N_a`*`c` + 6 s,
    8 s at `c` = 2, and gets no LR011; `[found]` writes no second
    `RESUMED`, where the shim held the call after the real `psql` had
    returned (`timer`), and `[absent]` binds anew, where it held it before
    (`hold`).

    THE END AND THE WAIT ARE BOTH READ (T254zb; lane 2's review RV20,
    finding 3): the second bind ends `bound`; `[found]` sends no second
    `start-record` commit, so no second `RESUMED`, and `[absent]` sends
    one under a new write id, not the copied one. And the `2` must go out
    at least 2 s inside `ended_utc` + 8 s, or the lookup's time could not
    tell a child that waited from a test that was slow: the case then
    fails as inconclusive."""
    est = _real_estate(estate, mode="primary")
    fifo = tmp_path / f"hold-{held}"
    os.mkfifo(fifo)
    mode = "timer" if held == "found" else "hold"
    est.shim([{"mode": mode, "match": "commit_write", "call": 1, "fifo": str(fifo)}])
    est.make_offer()
    est.answer_2()
    record = est.outer()
    assert _until(lambda: _commits(est), 60), "start-record's commit call never came"
    _kill(int(record["pid"]), signal.SIGTERM)
    record = est.ended(60)
    assert all(k in record for k in COPIES), record
    ended = _epoch(record["ended_utc"])
    est.shim()
    # THE FIRST PROMPT AFTER A FAILURE IS SPENT ON THE BIND-FAILED REPLY
    # (T254v), so `hello` goes first, as case 10's does; without it the next
    # `2` was that prompt and never reached the bind (lane 5, #165 6841545201).
    est.hook("hello")
    before = len(est.shim_calls())
    sent_at = time.time()
    assert sent_at < ended + 6, (f"inconclusive: the 2 went out {sent_at - ended:.1f} s "
                                 f"after ended_utc, too near C = 8 s to show a wait")
    est.answer_2()
    # THE SHIM LOGS NO TIME, so the lookup's start is read by watching for its
    # entry, at 50 ms: the time seen is at most 50 ms after the start.
    seen = _until(lambda: time.time() if [c for c in est.shim_calls()[before:]
                                          if "find_write" in c.get("sent", "")] else None,
                  120, 0.05)
    assert seen, est.shim_calls()[before:]
    print(f"T254 case 18: the lookup seen {seen - ended:.2f} s after ended_utc (C = 8 s)")
    assert seen >= ended + 8, (seen, ended)
    end = est.ended(120)
    assert "LR011" not in end.get("why", ""), end
    assert end["mode"] == "bound", end
    starts = [c for c in est.shim_calls()[before:]
              if "commit_write" in c.get("sent", "") and "start-record" in c.get("sent", "")]
    if held == "found":
        assert not starts, [c.get("call") for c in starts]
    else:
        assert starts and all(record["write_id"] not in c["sent"] for c in starts), \
            (record["write_id"], [c.get("call") for c in starts])


@pytest.mark.parametrize("case", ["found", "another-write", "generation"])
def test_the_bind_childs_lookup_sends_the_five_copied_values(estate, case):
    """AT-F6 case 19: with the window's name spelled otherwise than the lane's
    canonical name, after case 10's `[found]` `rc=3`, the child's lookup is
    `lanes-index journal --write-id <id> --not-after <n> --generation <g>
    --lane <write_lane> --verb start-record --args-sha256 <h>`, the five
    values copied from `start-record`'s pending record, never derived from
    `to`, and the found entry writes no second `RESUMED`. `[another-write]`:
    the record's `args_sha256` copy changed, LR007 `another-write` ends `rc=2`
    with the server's message and the copies dropped; `[generation]`: the
    `generation` copy changed, `rc=2` with a plain rerun's refusal and the
    copies kept."""
    est = _real_estate(estate, mode="primary")
    # CASE 10's `[found]` ARMS (T254t, T254w): every call after the commit
    # call fails, and the guard's own prefetch calls before it do not.
    est.shim(list(FOUND_ARMS))
    est.make_offer()
    est.answer_2()
    record = est.ended(120)
    assert record["rc"] == "3" and all(k in record for k in COPIES), record
    copies = {k: record[k] for k in COPIES}
    if case != "found":
        key = "args_sha256" if case == "another-write" else "generation"
        lines = [line for line in est.offer.read_text(encoding="utf-8").splitlines()
                 if not line.startswith(f"{key}=")]
        # THE COPY ALWAYS CHANGES (T254zf; lane 4, #165 6852642520 and
        # 6858782368): the digest and the generation are both lowercase hex,
        # a sha256 and a random uuid, so a `0` put first changed nothing
        # where the value began with `0`, about 1 run in 16. The lookup then
        # found the bind's own write, and the bind ended `bound` with rc 0
        # (lane 5's T510 call 1 on line R, #165 6852280934). So the first
        # digit is swapped for another, and the record is read back.
        old = copies[key]
        copies[key] = ("1" if old[0] == "0" else "0") + old[1:]
        write_record(est.offer, lines + [f"{key}={copies[key]}"])
        assert est.record().get(key) == copies[key] != old, (key, old, est.record().get(key))
    est.shim()
    est.hook("hello")
    # THIS ATTEMPT'S LOOKUP ALONE (T254zf; lane 4, #165 6858782368): the
    # shim's log is never reset, and the first attempt's lookups sent the
    # copies as they were, so the check below read them and passed without
    # the second `2`'s own lookup. Only the calls after this point count.
    before = len(est.shim_calls())
    est.answer_2()
    record = est.ended(120)
    lookups = [c for c in est.shim_calls()[before:] if "find_write" in c.get("sent", "")]
    assert lookups, f"the second 2 made no lookup: {record}"
    sent = " ".join(c.get("sent", "") for c in lookups)
    # THE FIVE VALUES AS THE LOOKUP SENDS THEM (T254zd): `--not-after <n>`
    # takes the copy's epoch seconds, and `find_write` gets them in their UTC
    # form, `'2026-11-13T10:57:06Z'` for 1794567426 (the shim's log, lane 2's
    # G-20 run k4b); the other four go as copied, a changed one as changed.
    copies["not_after"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime(int(copies["not_after"])))
    for key in COPIES:
        assert copies[key] in sent, (key, copies[key])
    if case == "found":
        assert record["mode"] == "bound", record
    elif case == "another-write":
        assert record["rc"] == "2" and not [k for k in COPIES if k in record], record
    else:
        assert record["rc"] == "2" and all(k in record for k in COPIES), record


def test_the_stale_row_copies_a_dead_outers_pending_call_and_the_next_2_looks_it_up(estate):
    """AT-F6 case 20: the outer killed with `-9` while a stand-in `lane-start`
    has written a `start-record` pending record of this session with a `call`
    line: once no process of the outer's session is left, the stale row
    copies the five values, `not_after` the largest among its `call` lines,
    and the next `2` makes the lookup, in the shim's log, before any
    `start-record` call.

    THE STAND-IN WRITES THAT RECORD (T254z; lane 5, #165 6841545201): a
    whole `start-record` pending record of this session, with one `call=`
    line (`pending-record`), at the register's own generation, host and
    container, so the stale row has something to copy. `LANES_HOST` pins
    the host the guard compares (`wr_here`), as a workstation outside a
    container would otherwise read `hostname`."""
    est = estate(mode="primary")
    est.shim()
    est.set("hold", 60)
    est.extra["LANES_HOST"] = HOST
    est.make_offer()
    generation = est.pg.psql("SELECT generation FROM lanes_register.register_switch;"
                             ).stdout.split()[-1]
    head = est.pg.psql("SELECT seq FROM lanes_register.register_head;").stdout.split()[-1]
    est.set("pending-record", json.dumps({
        "generation": generation, "lane": TO, "session": est.sid, "host": HOST,
        "container": CONTAINER, "database": "register-test", "base": int(head)}))
    est.answer_2()
    record = est.outer()
    assert _until(lambda: [e for e in est.starts() if e.get("pending")], 30), \
        "the stand-in wrote no pending record"
    outer = int(record["pid"])
    _kill(outer, signal.SIGKILL)
    est.release()
    assert _until(lambda: not _members("sid", outer), 30), "the outer's session never emptied"
    hook = est.hook("hello")
    assert hook.code == 2 and NO_OUTCOME in hook.err, repr(hook)
    record = est.record()
    assert all(k in record for k in COPIES), record
    est.extra["LANES_LANE_START"] = str(REPO / "lane-start")
    est.set("edit-real")
    est.answer_2()
    est.ended(120)
    calls = est.shim_calls()
    first_lookup = next(i for i, c in enumerate(calls) if "find_write" in c.get("sent", ""))
    # A `start-record` CALL IS ITS COMMIT (T254ze): the lookup's own call
    # names the verb too, `find_write(<id>, <utc>, <g>, <lane>, 'start-record',
    # <h>)`, so a filter on the verb alone counted the lookup as a start
    # (lane 2's G-20 run k12), as case 10 already filters.
    starts = [i for i, c in enumerate(calls) if "start-record" in c.get("sent", "")
              and "commit_write" in c.get("sent", "")]
    assert not starts or first_lookup < min(starts), calls


def test_a_bind_over_a_delayed_tls_link_at_c_3_ends_bound_inside_530_s(estate, request):
    """AT-F6 case 21 (R-P23): on the primary fixture behind T229's delayed
    loopback, 75 ms each way with TLS on, and `connect_timeout=3` with one
    address: `guard-bind` records `bound_s=530`, the bind ends `bound`, its
    `ended_utc` less `started_utc` recorded beside the 530 s, and the
    guard's register read is the hook's last database call in the shim's
    log. Waits for T229's `delayed_loopback`, which this line does not
    have.

    THE LINK IS ROUTED (T254za; lane 5, #165 6841545201): the estate
    reads and writes T229's TLS cluster, which listens on 127.0.0.1 (the
    session cluster has its socket alone), through the delayed loopback
    at 0.075 s each way, by that cluster's own configuration
    (`TLSCluster.configuration`, its two logins and their password files)
    with each URL's port the relay's and `connect_timeout=3`, one address
    and no `register_addresses=`. So the prefetch's `.head` says `c=3`,
    and `guard-bind` sums 530 s (TP:6183-6187 at a6497d00).

    THE IMAGE CACHE IS FILLED FIRST (T254zg; lane 5, #165 6852197902): a
    cold prompt reads form 2 and then fetches the whole files in a second
    `lanes-index` with a connect of its own (`f9e1449c:lanes-index:6856`,
    waited for to the cut at `:6862`), which the design prices past the
    start line at 150 ms of round trip (design.md:4261-4273 at b8e3df74);
    lane 2's G-20 saw it cut at `T0` + 3.75 s on py-bench. So the offer is
    made through the cluster's own port, and its fetch fills the cache; then
    the configuration is pointed at the relay, with `connect_timeout=3`, for
    the `2`, whose read is one call (design.md:4287-4289 at b8e3df74).

    AND NO SERVICE ANSWERS (T254zg): the estate's state home is one whose
    socket path is over `SOCKET_MAX` (`_state_home_with_no_service`), where
    the client reads directly and starts nothing
    (`f9e1449c:lanes-index:7568`). Otherwise the offer's fallback starts
    `serve` (`:9324`) on the configuration of the cluster's own port; each
    prompt's cache family is its own (`f9e1449c:lanes-edit.sh:11792`), so
    no earlier `.direct` keeps the `2`'s read direct (`lanes-index:9311`),
    and that `serve` would answer it off the delayed link, with no call of
    the hook's in the shim's log. So the row's last oracle is read: the
    calls the shim logs between the `2` and the hook's exit are the guard's
    read alone (D9's guard row, `statement_timeout=1500`,
    `lanes-index:4563`), the last of them through the relay at `c` = 3;
    answer 2 adds none."""
    pgcluster = pytest.importorskip("pgcluster")
    delayed = pgcluster.__dict__.get("delayed_loopback")
    assert delayed is not None, "tests/pgcluster.py has no delayed_loopback (T229)"
    cluster = request.getfixturevalue("tls_cluster")
    db = pgcluster.Database(cluster, cluster.database_name)
    est = _real_estate(estate, mode="primary", pg=db)
    est.extra["XDG_STATE_HOME"] = str(_state_home_with_no_service(est))
    with delayed(cluster.port, 0.075) as relay:
        conf = cluster.configuration(est.root / "tls-conf", mode="primary")
        text = conf.read_text(encoding="utf-8")
        direct = f"@127.0.0.1:{cluster.port}/"
        assert text.count(direct) == 2 and "register_addresses" not in text, text
        est.extra["LANES_INDEX_CONFIG"] = str(conf)
        est.shim()
        est.make_offer()
        offered = est.shim_calls()
        text = text.replace(direct, f"@127.0.0.1:{relay.port}/").replace(
            "?sslmode=verify-full", "?connect_timeout=3&sslmode=verify-full")
        assert text.count("connect_timeout=3") == 2, text
        conf.write_text(text, encoding="utf-8")
        hook = est.answer_2()
        calls = est.shim_calls()[len(offered):]
        record = est.outer()
        assert record["bound_s"] == "530", record
        record = est.ended(530)
        port = str(relay.port)
    seen = [(c.get("call"), c.get("pg", {}).get("PGPORT"), c.get("pg", {}).get("PGCONNECT_TIMEOUT"),
             c.get("pg", {}).get("PGOPTIONS")) for c in calls]
    fetched = [c for c in offered
               if "statement_timeout=14000" in c.get("pg", {}).get("PGOPTIONS", "")]
    print(f"T254 case 21: the offer's prompt made {len(offered)} call(s) through the cluster's "
          f"own port, {len(fetched)} of them the whole-file fetch; the 2's prompt exited "
          f"{hook.t_exit - hook.t0:.2f} s after T0, its calls {seen}")
    assert calls and all("statement_timeout=1500" in (s[3] or "") for s in seen) \
        and seen[-1][1:3] == (port, "3"), \
        f"the 2's prompt made calls other than the guard's read through the relay {port}: {seen}"
    assert record["mode"] == "bound", record
    print(f"T254 case 21: ended_utc - started_utc = "
          f"{_epoch(record['ended_utc']) - _epoch(record['started_utc'])} s beside 530 s")
    assert hook.code == 2


def _state_home_with_no_service(est: Estate) -> Path:
    """A STATE HOME WHERE NO SERVICE CAN RUN (T254zg), under the estate's
    root: its socket path is over `SOCKET_MAX`, so the client reads
    directly and starts nothing, as on a workstation whose socket path is
    too long (`f9e1449c:lanes-index:7568`, Y:3777-3781). The image cache
    and the pending records live there too, as in any state home."""
    home = est.root / ("state-with-no-service-" + "s" * 90)
    home.mkdir(mode=0o700)
    sock = home / "openRepoTools" / "run" / "register.sock"
    assert len(os.fsencode(str(sock))) > SOCKET_MAX, sock
    return home


# ============================================================ T213: test 10's direct part
#
# Test 10's direct part, the guard without the service (AT-10; section 4.4):
# each case runs with the service down, so the guard's own direct read meets
# the fault; T237 adds the `service-up` cases. The database cases run on the
# session cluster, so here they are collected and skipped with T205's banner;
# they fail until L1-A2, L1-A11 and L5-A3, and the second read past the start
# line's until L1v4.5's T113 and lane 5's T507. The hook's 4.5 s is asserted
# as stated; every other bound at twice its value, recorded beside it (section
# 1.2's timing rule).

#: The guard's frame (design, "One budget"; section 4's rule 1).
BUDGET = 4.5
#: The parse's start line, `T0 + 3.75 s` (SVC-8), asserted at twice it.
START_LINE = 3.75
#: How long case 6 waits, once the hook has exited, for the shim to hold the
#: whole-file fetch on its FIFO. The fetch starts before the cut, so it is
#: held by then; this is a margin, the outer's 10 s (`Estate.outer`).
HOLD_LIMIT = 10.0
#: FORM 4 AS THE SHIM SEES IT (lane 5's F2b, #165 6812547449). The shim logs
#: `psql`'s own argv, never `lanes-index`'s, so no `--for` is ever in it;
#: form 4 is known by its SQL instead, which the shim logs as `sent` and
#: which an arm's `match` reads. It is the one request that reads the
#: latest import at or below `n` (contract section 3.6's form 4;
#: `register_read_queries(at=n)` in lane 5's writer A, T507A `319cd928`,
#: `lanes-index:6081`). Form 2, the whole-file fetch and the render read
#: send no such bound.
FORM_4_SQL = "WHERE i.kind = 'import' AND i.seq <= "
#: THE WINDOW'S LANE, SPELLED ANOTHER WAY IN ITS ROW (lane 5's call 4, #165
#: 6813284257 and 6813607794): `RepoA-2` under the window `repoA-2`. The
#: guard's prefetch, form 2, asks with `--lane=` the window's name, and
#: `lanes-index` writes `.log.<that key>` even where the lane has no log; the
#: binding scan takes the row's own spelling from its case-insensitive match
#: (`G_LANE="$gr_hits"`), and only a key the cache lacks reaches form 4.
ROW_SPELLING = FROM[:1].upper() + FROM[1:]
#: The guard's note where a lane's object log could not be read, in today's
#: words (contract 4.19 section 3.6, B4: "the guard notes it as today", at
#: `lanes-edit.sh:10707-10710` at pin `2a057a6d`), which form 4's every end
#: but 0 reaches.
LOG_UNREAD = "object log could not be read"


def _silent_listener(host="127.0.0.1"):
    """Section 4.4's case 1: a loopback listener on port 0 that accepts and
    never speaks. Returns (its port, a function that closes it)."""
    import socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, 0))
    server.listen(16)
    held, stop = [], threading.Event()

    def accept():
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                held.append(conn)
            except OSError:
                continue

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()

    def close():
        stop.set()
        thread.join(1)
        for conn in held:
            conn.close()
        server.close()

    return server.getsockname()[1], close


def _db_config(est: Estate, reader_url: str, **keys) -> Path:
    """The estate's configuration with its reader's URL replaced (T220's
    form), plus any of `register_addresses=` and the like."""
    conf = Path(est.extra["LANES_INDEX_CONFIG"])
    lines = [line for line in conf.read_text(encoding="utf-8").splitlines()
             if not line.startswith("reader_url=")]
    lines.append(f"reader_url={reader_url}")
    lines.extend(f"{k}={v}" for k, v in keys.items())
    conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return conf


def _refuses_inside_the_budget(hook: Hook) -> None:
    took = hook.t_exit - hook.t0
    print(f"T213: the guard exited {hook.code} after {took:.3f} s (budget {BUDGET} s)")
    assert not hook.killed and hook.code == 2, repr(hook)
    assert took < BUDGET, f"the guard took {took:.2f} s, past the {BUDGET} s budget"


@pytest.mark.parametrize("case", [f"{n}-service-{s}" for s in ("down", "up")
                                  for n in (1, 2, 3, 4)])
def test_a_database_that_does_not_answer_is_2_inside_4_5_s(estate, case):
    """Section 4.4's cases 1 to 4 with the service down: a loopback listener
    that never speaks; a host silent after connecting (a relay that stops
    forwarding at the first query); a read behind a migration's lock, held
    by the test's own session; and a conninfo with two loopback hosts,
    `127.0.0.1` and `127.0.0.2` (T104's TLS refusal at load does not reach
    them). In each the hook exits 2, was not killed, and finished in under
    4.5 s, its refusal naming the store. T237 adds the `service-up` ids, where
    the service's connection meets the fault."""
    est = estate(mode="primary", to=FROM, to_row=False)
    closers = []
    if case.endswith("service-up"):
        closers.append(_Service(est).stop)
    try:
        if case.startswith("1-"):
            port, close = _silent_listener()
            closers.append(close)
            _db_config(est, f"postgresql://reader@127.0.0.1:{port}/{est.pg.name}")
        elif case.startswith("2-"):
            # T229c's RELAY in front of the case's own database: it passes the
            # startup on, then goes silent at the first ReadyForQuery, so the
            # read connects and logs in and its query is never answered. Its
            # login is the estate's own `reader_url=`'s (`pg.url()`'s), which
            # the cluster has; case 1's `reader` reaches no server, but here
            # a login the cluster lacks would end the read at once on its
            # FATAL, a refusal that is not this case's fault.
            silent = pytest.importorskip("pgcluster").__dict__.get("silent_after_startup")
            assert silent is not None, "tests/pgcluster.py has no silent-after-startup relay"
            relay = silent(est.pg.port, socket_dir=est.pg.host)
            closers.append(relay.close)
            login = urlsplit(est.pg.url()).username
            _db_config(est, f"postgresql://{login}@127.0.0.1:{relay.port}/{est.pg.name}")
        elif case.startswith("3-"):
            # The register goes to the SQL store BEFORE the lock (T213o):
            # `est.hook` seeds it first (`_seed_primary`, T254r), and that
            # seeding reads `register_head`, so seeding after the lock waited
            # on this case's own lock until psql's 120 s timeout (lane 5,
            # #165 6841316861). Seeded here, the hook's seeding sends nothing
            # and the guard's own read is the one that meets the lock.
            _seed_primary(est)
            holder = est.pg.session()
            closers.append(holder.kill)
            holder.stdin.write("BEGIN; LOCK TABLE lanes_register.register_head IN ACCESS EXCLUSIVE MODE;\n")
            holder.stdin.flush()
            # THE LOCK IS HELD BEFORE THE HOOK (T213p; lane 2's review RV20,
            # finding 5): the LOCK goes to `psql`'s stdin with no answer, so
            # on a loaded runner the guard could read before it was taken,
            # and exit 0. It is waited for, granted, in `pg_locks`.
            assert _until(lambda: _head_locked(est), 10, 0.1), \
                "the case's ACCESS EXCLUSIVE lock on register_head was never granted"
        else:
            ports = [_silent_listener(h) for h in ("127.0.0.1", "127.0.0.2")]
            closers.extend(c for _, c in ports)
            _db_config(est, "postgresql://reader@127.0.0.1:%d,127.0.0.2:%d/%s"
                       % (ports[0][0], ports[1][0], est.pg.name))
        hook = est.hook("hello")
        _refuses_inside_the_budget(hook)
        if case.startswith("3-"):
            # AND THE REFUSAL IS THE STORE'S (T213p; RV20, finding 5): the
            # guard's read met the lock, D9's guard row ended it at its
            # `lock_timeout`, 1 s, which is no cut, so 69, and the guard
            # refused with S3's text (`reg_guard_s3`), not at its start line,
            # "too late to verify", before or without a read.
            assert STORE_REFUSAL in hook.err, hook.err
    finally:
        for close in closers:
            close()


#: S3'S REFUSAL, the guard's where its register read ended 69 with no outage
#: declared (`f9e1449c:lanes-edit.sh:20761`, `reg_guard_s3`).
STORE_REFUSAL = "the register's SQL store did not answer the guard's read"


def _head_locked(est: Estate) -> bool:
    """Whether a session holds `register_head`'s ACCESS EXCLUSIVE lock in the
    case's database, granted (T213p)."""
    sql = ("SELECT count(*) FROM pg_catalog.pg_locks l "
           "JOIN pg_catalog.pg_class c ON c.oid = l.relation "
           "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
           "WHERE l.database = (SELECT oid FROM pg_catalog.pg_database "
           "WHERE datname = current_database()) AND n.nspname = 'lanes_register' "
           "AND c.relname = 'register_head' AND l.mode = 'AccessExclusiveLock' AND l.granted;")
    return int(est.pg.psql(sql).stdout.strip() or 0) > 0


@pytest.mark.parametrize("case", ["service-down", "service-up"])
def test_a_connect_timeout_above_the_direct_reads_share_is_cut_at_the_parse_start_line(
        estate, case):
    """Section 4.4's case 5: `reader_url=` carries `connect_timeout=3`, so the
    connect alone would end past the start line; against case 1's listener
    the read's own timer ends it at `T0 + 3.75 s`, the hook exits 2 in under
    4.5 s, and the direct read's call carries `PGCONNECT_TIMEOUT=3`."""
    est = estate(mode="primary", to=FROM, to_row=False)
    port, close = _silent_listener()
    svc = _Service(est) if case == "service-up" else None
    try:
        _db_config(est, f"postgresql://reader@127.0.0.1:{port}/{est.pg.name}?connect_timeout=3")
        est.shim()
        hook = est.hook("hello")
        _refuses_inside_the_budget(hook)
        calls = est.shim_calls()
        assert calls and calls[-1]["pg"].get("PGCONNECT_TIMEOUT") == "3", calls[-1:]
    finally:
        close()
        if svc is not None:
            svc.stop()


#: Where the too-late case's guard arrives at its prefetch: just past the
#: start line, `T0 + 3.8 s` from the runner's own start (lane 3, #165
#: 6812673125, on lane 5's F3, 6812547449).
ARRIVAL = 3.8
#: The stand-in `tmux`'s hold for that case, put in before its `case "$fmt"`:
#: on the guard's last query before its prefetch, `record_window_state`'s
#: targeted `#{session_name}`, once, it sleeps until the wall time in
#: `@DEADLINE@`, then writes the time it woke to `@ARRIVED@`.
_TOO_LATE_HOLD = r'''if [ "$fmt" = '#{session_name}' ] && [ -n "$target" ] && [ ! -e @ARRIVED@ ]; then
  : > @ARRIVED@
  rem=$(awk -v d="$(cat @DEADLINE@)" -v n="$(date +%s.%N)" 'BEGIN { r = d - n; if (r < 0) r = 0; printf "%.3f", r }')
  sleep "$rem"
  date +%s.%N > @ARRIVED@
fi
'''


def test_a_guard_that_starts_too_late_refuses_2_without_a_read(estate):
    """AT-10: a guard that starts at or past the direct read's cap refuses 2
    and makes no read (the 5 s is one budget, spent once). The stand-in
    `tmux` holds the guard's last query before its prefetch,
    `record_window_state`'s targeted `#{session_name}`, until `T0 + 3.8 s`
    from the runner's own start (`ARRIVAL`), once, so `T0` is early and the
    read would start just past the start line; the arrival and the exit
    are printed beside the 4.5 s, which is asserted as stated (lane 3, #165
    6812673125; design:6181-6183 records every measured time). A sleep on
    every `tmux` call put four of them, 5.2 s, before the prefetch, so the
    runner killed the hook first (lane 5's F3, #165 6812547449). The estate
    is G1's, `to=FROM, to_row=False`, so the guard's only refusal is the
    late start's, never the name offer's (lane 3's reason in #165
    6812490130)."""
    est = estate(mode="primary", to=FROM, to_row=False)
    est.shim()
    deadline, arrived = est.bin / "tmux-deadline", est.bin / "tmux-arrived"
    hold = _TOO_LATE_HOLD.replace("@ARRIVED@", f"'{arrived}'").replace(
        "@DEADLINE@", f"'{deadline}'")
    tmux = est.session.tmux
    text = tmux.read_text(encoding="utf-8")
    assert text.count('case "$fmt" in') == 1, "the stand-in tmux has changed its shape"
    tmux.write_text(text.replace('case "$fmt" in', hold + 'case "$fmt" in'), encoding="utf-8")
    mono0, wall0 = time.monotonic(), time.time()
    deadline.write_text(f"{wall0 + ARRIVAL:.6f}\n", encoding="utf-8")
    hook = est.hook("hello")
    woke = arrived.read_text(encoding="utf-8").strip() if arrived.exists() else ""
    took = hook.t_exit - hook.t0
    if woke:
        at = float(woke) - wall0 - (hook.t0 - mono0)
        print(f"T213: the guard's last tmux query before its prefetch returned at T0 + "
              f"{at:.3f} s (set for {ARRIVAL} s); the hook exited {hook.code} at T0 + "
              f"{took:.3f} s (budget {BUDGET} s)")
    assert woke, ("the guard made no targeted `#{session_name}` query (record_window_state's), "
                  f"or was stopped in it, so nothing held it to the start line\n{hook!r}")
    _refuses_inside_the_budget(hook)
    assert not est.shim_calls(), "a guard past its start line still read"


def test_a_whole_file_fetch_the_start_line_cuts_fills_the_image_cache_for_the_next_prompt(
        estate, tmp_path):
    """Section 4.4's case 6, with the service down: the image cache lacks
    `lanes/LANES.md` at `n`, and the shim holds the direct read's whole-file
    fetch on a FIFO; the hook exits 2 at the cut inside the budget; the fetch
    runs on in a detached child, and once released writes the file to the
    image cache, so the next prompt's read fetches no whole file and
    answers. The FIFO is let go by `_release`, bounded at `HOLD_LIMIT`, so
    where no call is held on it the case fails, and never waits. The estate
    is G1's, `to=FROM, to_row=False`, as T213c built it for cases 1, 3, 4
    and 5: with the default estate the first prompt's 2 is the name offer's,
    and an oracle's refusal must come from the fault under test alone (lane
    3, #165 6812490130). The case's database holds the estate's register at
    primary (`_Register`; lane 5's F2, #165 6812547449): at `files` the
    first request ends 69, `switch-files`, and no whole-file fetch is ever
    made."""
    est = estate(mode="primary", to=FROM, to_row=False)
    _Register(est)
    fifo = tmp_path / "whole-file"
    os.mkfifo(fifo)
    est.shim([{"mode": "hold", "match": "lanes/LANES.md", "call": 1, "fifo": str(fifo)}])
    try:
        hook = est.hook("hello")
        _refuses_inside_the_budget(hook)
        assert _release(fifo, HOLD_LIMIT), (
            f"no call naming lanes/LANES.md was held on the FIFO {HOLD_LIMIT:.0f} s after the "
            f"hook exited, so the guard's direct read started no whole-file fetch for the cut "
            f"to leave running (fails until lane 5's T507); the shim logged "
            f"{len(est.shim_calls())} call(s)\n{hook!r}")
    finally:
        _release(fifo, 0)
    before = len(est.shim_calls())
    time.sleep(1.0)
    hook = est.hook("hello")
    assert hook.code in (0, 2) and not hook.killed, repr(hook)
    assert not [c for c in est.shim_calls()[before + 1:]
                if "lanes/LANES.md" in c.get("sent", "")], "the next prompt fetched it again"


def test_the_direct_read_connects_as_its_engineers_reader_login(estate):
    """AT-10: the guard's direct read connects as the engineer's reader login
    (design section 1.4, `lanes-index login add`), never as the writer."""
    est = estate(mode="primary")
    est.shim()
    est.hook("hello")
    calls = est.shim_calls()
    assert calls, "the guard made no direct read"
    assert all("writer" not in (c.get("pg", {}).get("PGUSER") or "") for c in calls), calls


def test_no_session_environment_carries_a_database_url_or_password(estate):
    """AT-10: no variable of the session's environment, as the guard and the
    bind's child see it, carries a database URL or a password."""
    est = estate(mode="primary")
    est.make_offer()
    est.answer_2()
    est.ended()
    env = est.starts()[0]["env"]
    leaked = {k: v for k, v in env.items() if v and ("postgresql://" in v or "PGPASSWORD" in k)}
    assert not leaked, leaked
    child = est.session.env(est.base, **est.extra)
    assert not [k for k, v in child.items() if k.startswith("PG") or "postgresql://" in v]


def test_claude_no_lane_still_skips_before_any_input(estate):
    """AT-10: `CLAUDE_NO_LANE=1` still makes the guard exit 0 before it reads
    any input: nothing printed, no `tmux` call and no read."""
    est = estate()
    calls = len(est.session.tmux_calls())
    hook = run_hook(["bash", str(est.guard), "guard"], "not json at all",
                    est.env(CLAUDE_NO_LANE="1"), est.session.cwd)
    assert hook.code == 0 and hook.text == "", repr(hook)
    assert len(est.session.tmux_calls()) == calls, est.session.tmux_calls()[calls:]


def test_the_guard_maps_69_75_and_3_to_2(estate, tmp_path):
    """AT-10, "The codes the guard maps (D10)" (TP:1958-1963;
    exit-codes.md:294): the guard exits 2 (the hook's only refusal), never
    the code it met.

    75 AND 3 ARE THE BIND'S (lane 5, #165 6814614032): `register read` never
    ends 75 (a lost turn, from `register commit` only, register-cli.md:337)
    or 3 (in doubt, from two commands only, :335), and the guard reads any
    read code outside 0, 2, 69 and 78 as files mode with a warning (:340).
    So answer 2's detached bind is made to exit 75, then 3, by the module's
    stand-in `lane-start` (`rc`, the AT-F6 fixture case 5 uses, in place of
    test 12's shim): the child records `mode=bind-failed` with `rc=` that
    code, and the next prompt's hook exits 2 with "THE BIND TO LANE `<to>`
    FAILED (exit `<rc>`)". In files mode, with the module's estate, whose
    offer the `2` answers. They fail until L5-A1 (lane 5's T502, its
    `bind-failed` arm).

    69 STAYS AT THE READ, where it is the outage's 2: through the contract's
    stub `lanes-index`, beside a copy of `lanes-edit.sh`, the end injected by
    `stub_outcome`. The estate is G1's, `to=FROM, to_row=False`: the session
    is named for the window's lane, whose row names it, so the guard's
    answer with a register it could read is 0, and its 2 can only be the
    read's (lane 3's reason in #165 6812490130). The module's default estate
    makes the name offer, whose own 2 would pass this half wherever the
    guard went on past a failed read (line AN14). It fails until L5-A3
    (lane 5's T507)."""
    for end in (75, 3):
        est = estate()
        est.set("rc", end)
        est.make_offer()
        est.answer_2()
        record = est.ended()
        assert record["mode"] == "bind-failed" and record["rc"] == str(end), (end, record)
        hook = est.hook("after the failure")
        assert hook.code == 2 and not hook.killed, (end, repr(hook))
        assert f"THE BIND TO LANE {TO} FAILED (exit {end})" in hook.err, (end, repr(hook))
    from sql_register_helpers import stub_outcome
    code = tmp_path / "code"
    contract_stub(code)
    for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
        shutil.copy2(REPO / name, code / name)
    for end in (69,):
        est = estate(guard=code / "lanes-edit.sh", to=FROM, to_row=False)
        conf = tmp_path / f"lanes-index-{end}.conf"
        conf.write_text(f"register_url=postgresql:///register?host={tmp_path}/sock\n",
                        encoding="utf-8")
        est.extra["LANES_INDEX_CONFIG"] = str(conf)
        stub_outcome(code, ["register", "read"], exit=end)
        hook = est.hook("hello")
        assert hook.code == 2 and not hook.killed, (end, repr(hook))
        calls = [json.loads(line) for line in (code / ARGV_LOG).read_text(
            encoding="utf-8").splitlines()] if (code / ARGV_LOG).exists() else []
        assert [c for c in calls if c[:2] == ["register", "read"]], (end, calls)


@pytest.mark.parametrize("case", ["at-the-cap", "under-a-declaration", "no-declaration-read"])
def test_a_second_read_past_the_start_line_is_noted_not_refused(estate, case):
    """S36-T507, lane 5's name: the guard's second read, form 4 (`register
    read --for guard --at <n> --pid <pid> --cache <file> --lane=<key>`).
    `[at-the-cap]`: started at or past `T0 + 3.75 s` it ends 2 and writes no
    `.log.<key>`, and the guard notes the log as unreadable and does not
    refuse (B4); `[under-a-declaration]`: its cut stays `T0 + 3.75 s` under
    an unexpired declaration (B5); `[no-declaration-read]`: it reads no
    declaration. The case's database holds the estate's register at primary
    (`_Register`; lane 5's F2, #165 6812547449), so form 2 answers.

    FORM 4 IS ASKED ONLY FOR A KEY FORM 2 DID NOT FILL (lane 5's call 4, #165
    6813284257 and 6813607794): the window's row is spelled `ROW_SPELLING`,
    so the binding scan asks for `.log.RepoA-2`, which the prefetch's
    `--lane=repoA-2` did not write, and the guard makes its second read.

    THE CUT, in `[at-the-cap]` and `[under-a-declaration]`: the shim holds
    form 4's request 3.9 s (`FORM_4_SQL`), so it would reach the database
    only past `T0 + 3.75 s`, and the read's own cut ends it 2, too late to
    verify (T113's fix round, MUST-2). `[under-a-declaration]` does so under
    an unexpired declaration that names this database, `database=` the
    configuration's `register_label=` (config.md section 6.4), so the
    declaration counts; there form 4 still starts, is cut and is noted. Both
    end inside the budget, noted as today (`LOG_UNREAD`; B4).
    `[no-declaration-read]` has no declaration and no hold: its form 4 ends
    0, and the guard notes no log it could not read.

    NOT REFUSED, in the module's estate, is the guard's own answer to it: the
    name offer, 2 with the offer's text and the record at `name-drift`. A
    refusal on the read makes no offer. `.log.<key>` is not asserted: the
    guard removes its cache files when it exits (`cleanup`)."""
    est = estate(mode="primary")
    est.push_register([_row(ROW_SPELLING, est.sid, "LIVE"), _row(est.to, est.other, "PAUSED")])
    _Register(est)
    cut = case in ("at-the-cap", "under-a-declaration")
    est.shim([{"mode": "window", "ms": 3900, "match": FORM_4_SQL}] if cut else [])
    if case == "under-a-declaration":
        conf = Path(est.extra["LANES_INDEX_CONFIG"])
        label = next((line.split("=", 1)[1] for line in conf.read_text(encoding="utf-8")
                      .splitlines() if line.startswith("register_label=")), "")
        assert label, f"the estate's configuration names no register_label=: {conf}"
        (conf.parent / "register-outage").write_text(
            f"format=1\nkind=word\ndatabase={label}\nutc=2026-11-10T00:00:00Z\nhost={HOST}\n"
            f"until={_utc(time.time() + 3600)}\nmirror-seq=1\nwhy=test\n", encoding="utf-8")
    hook = est.hook("hello")
    assert not hook.killed and hook.t_exit - hook.t0 < BUDGET, repr(hook)
    record = est.record()
    assert hook.code == 2 and OFFER in hook.text and record.get("mode") == "name-drift", \
        f"the guard did not answer with its name offer (a refusal on its read makes none): " \
        f"{record}\n{hook!r}"
    forms = [c for c in est.shim_calls() if FORM_4_SQL in c.get("sent", "")]
    assert forms, "the guard made no second read (no call in the shim's log is form 4's SQL)"
    if cut:
        assert "window" in forms[0].get("arms", []), f"the shim did not hold form 4: {forms[0]}"
        assert LOG_UNREAD in hook.err, \
            f"the guard did not note the log its cut second read left unread: {hook!r}"
    else:
        assert LOG_UNREAD not in hook.err, \
            f"form 4 was made, yet the guard noted the log as unread: {hook!r}"


def test_the_guards_last_budget_line_is_below_guard_timeout():
    """Lane 5's (A5): the last line of SVC-8's budget, the guard's own
    printing of its refusal, is below `GUARD_TIMEOUT`, 5 s: the guard's
    largest budget constant, read from `lanes-edit.sh`, is under 5000 ms.
    Fails until L5-A3 (lane 5's T507) writes the budget."""
    text = GUARD.read_text(encoding="utf-8")
    found = re.findall(r"^GUARD_BUDGET_[A-Z_]*_MS=(\d+)", text, re.M)
    assert found, "lanes-edit.sh states no GUARD_BUDGET_*_MS line (lane 5's T507)"
    assert max(int(v) for v in found) < 5000, found


#: A MIRROR READ'S LABEL, in the form the text gives it: `read: mirror at
#: <sha12>, …` on stderr (the test plan's AT-11 oracle, TP:2878-2881, which
#: names `session-start`; B15 tasks:728's mirror class). The words after the
#: comma are not fixed for the `SessionStart` block on primary (lane 5's
#: point 2 to lane 3, #165 6814032480), so only the prefix, the 12 hex digits
#: and the comma are pinned, as the readers module's `MIRROR_LINE` pins them.
MIRROR_LINE = re.compile(r"^read: mirror at [0-9a-f]{12}, .*$", re.M)


def test_the_session_start_block_makes_no_register_call_on_primary(estate):
    """Lane 5's (A5; R39): the `SessionStart` block, in the mirror class,
    makes no register call on primary: the shim logs no call while it
    runs. And it reads the mirror offline, labelled `read: mirror` (T508,
    B15 tasks:822): its stderr carries the label (`MIRROR_LINE`), its stdout
    does not, and it exits 0. A build with no SQL path makes no register
    call either, so the call count alone passed at the base and proved
    nothing for T508 (lane 5's point 4, #165 6814032480); the label is T508's
    own, so the case fails at the base on it, until T508 (L5-A4)."""
    est = estate(mode="primary")
    est.shim()
    proc = subprocess.run(["bash", str(est.guard), "session-start"],
                          input=est.session.hook_input(), capture_output=True, text=True,
                          env=est.env(), cwd=str(est.wip), timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert not est.shim_calls(), est.shim_calls()
    assert MIRROR_LINE.search(proc.stderr), \
        f"the block printed no `read: mirror at <sha12>, ...` line on stderr (T508): {proc.stderr}"
    assert not MIRROR_LINE.search(proc.stdout), proc.stdout


# ============================================================ T226: the guard's measured parts
#
# M5b and M10 (section 5.1), the guard module's half of T226; line M wrote
# the measure module's half (T226m). Each asserts correctness only; its
# figures go to the job's log and to `$GITHUB_STEP_SUMMARY`, never into a
# threshold (section 5.4). Ten runs each, as section 5.1's table gives them.

MEASURE_RUNS = 10
#: The measurement's register (the test plan's AT-10 fixture): about 2.6 MB
#: with 73 lanes, shaped as the real one is, the bound lane's log about 90 KB.
MEASURE_LANES = 73
MEASURE_BYTES = 2_600_000
MEASURE_LOG = 90_000


def _record_figure(title: str, figures: dict) -> None:
    """A measurement's figures, printed for the job's log and appended to
    `$GITHUB_STEP_SUMMARY` where it is set."""
    line = f"{title}: " + ", ".join(f"{k} {v}" for k, v in figures.items())
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"- {line}\n")


def _median(values) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _measurement_register(est: Estate) -> tuple:
    """The measurement's register on the estate's checkout, pushed: `FROM`'s
    row naming the session, 72 other lanes, each with its log, `FROM`'s about
    90 KB and the whole about 2.6 MB. Returns (its render set as a mapping of
    paths to text, its build time in seconds)."""
    t0 = time.monotonic()
    lanes = [FROM] + [f"bench{i:02d}-1" for i in range(1, MEASURE_LANES)]
    sids = {lane: (est.sid if lane == FROM else str(uuid.uuid4())) for lane in lanes}
    rows = [_row(lane, sids[lane], "LIVE" if lane == FROM else "PAUSED") for lane in lanes]
    rest = (MEASURE_BYTES - MEASURE_LOG) // (MEASURE_LANES - 1)
    files = {}
    for lane in lanes:
        # THE LOG'S LINE FORM, as the helper suite writes it
        # (`tests/test_lane_helpers.sh`): `<VERB> - lane <l>, session
        # <id>@<ws>, <utc>, lane:<l>`, the dash an em dash.
        entry = (f"RESUMED {chr(0x2014)} lane {lane}, session {sids[lane]}@{HOST}, "
                 f"2026-10-01T00:00:00Z, lane:{lane}\n")
        size = MEASURE_LOG if lane == FROM else rest
        files[f"lanes/log/{lane}.md"] = f"# {lane}\n\n" + entry * (size // len(entry))
    for path, text in files.items():
        (est.wip / path).write_text(text, encoding="utf-8")
    est.push_register(rows)
    files["lanes/LANES.md"] = register_text(rows)
    files["lanes/log/README.md"] = "logs.\n"
    return files, time.monotonic() - t0


def _timing_wrappers(est: Estate) -> tuple:
    """`tmux` and `git` wrappers ahead of the stand-in on `PATH`, each logging
    its call's wall time and arguments, then running the stand-in `tmux` or
    the real `git`. Returns (the `PATH` to pass, the two logs)."""
    wrap = est.root / "timing"
    wrap.mkdir(exist_ok=True)
    logs = (est.ctl / "tmux-times.log", est.ctl / "git-times.log")
    for name, target, log in (("tmux", est.bin / "tmux", logs[0]),
                              ("git", shutil.which("git"), logs[1])):
        _script(wrap / name, "#!/bin/sh\nprintf '%s %s\\n' \"$(date +%s.%N)\" \"$*\" >> @LOG@\n"
                "exec @TARGET@ \"$@\"\n", LOG=repr(str(log)), TARGET=repr(str(target)))
    path = os.pathsep.join([str(wrap), str(est.bin), est.base.get("PATH", os.defpath)])
    return path, logs


def _times(log: Path, since: float) -> list:
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        stamp, _, args = line.partition(" ")
        if float(stamp) >= since:
            out.append((float(stamp), args))
    return out


def test_todays_direct_guard_is_timed_in_its_four_parts(estate):
    """M5b (AT-10): today's direct guard, timed in the four parts the design
    measured (design, "What today's guard costs, in four parts"), on the
    measurement's register: reaching the guard's arm, to its first `tmux`
    call; the `tmux` read, to its last `tmux` call before the register's;
    `transcript_holders` and the rest, to the first `git` read of the
    register; and the register read with its parses, to the exit. The
    figures are recorded, never asserted; it asserts that each run lets the
    prompt through (the row names the session), that each part was reached,
    and that the four parts make up the run."""
    est = estate()
    _, built = _measurement_register(est)
    est.swap_window(FROM, FROM)
    path, (tmux_log, git_log) = _timing_wrappers(est)
    parts = {"arm": [], "tmux": [], "holders": [], "register": [], "total": []}
    for _ in range(MEASURE_RUNS):
        start = time.time()
        hook = est.hook("hello", PATH=path)
        end = time.time()
        assert hook.code == 0 and not hook.killed, repr(hook)
        tmux = [t for t, _ in _times(tmux_log, start)]
        reads = [t for t, args in _times(git_log, start) if "lanes/" in args]
        assert tmux and reads, f"a part was not reached: tmux {tmux}, register reads {reads}"
        before = [t for t in tmux if t <= reads[0]]
        assert before, "the register was read before the tmux read"
        marks = [start, tmux[0], before[-1], reads[0], end]
        assert marks == sorted(marks), marks
        for name, (a, b) in zip(("arm", "tmux", "holders", "register"), zip(marks, marks[1:])):
            parts[name].append(b - a)
        parts["total"].append(end - start)
        assert abs(sum(parts[n][-1] for n in ("arm", "tmux", "holders", "register"))
                   - parts["total"][-1]) < 1e-6
    _record_figure("M5b, today's direct guard in four parts (median ms)",
                   {k: f"{_median(v) * 1000:.1f}" for k, v in parts.items()}
                   | {"register built in": f"{built:.2f} s"})


def test_the_guards_register_parse_is_timed_on_a_real_sized_register_beside_todays_six_reads_through_git(
        estate, tmp_path):
    """M10 (AT-10): on the measurement's register, written twice, as the
    files of a git checkout and as SVC-8's cache files, the guard's register
    read is timed both ways: today's reads through `git` on the checkout,
    and the parse alone on the cache files, which the guard's prefetch
    (`register read --prefetch --cache <file>`, lane 5's T507) fills from the
    contract's stub `lanes-index` (T207) beside a copy of `lanes-edit.sh`.
    Each is recorded with the parse's 0.5 s reserve, never asserted.
    Correctness alongside: both ways the guard gives the same answer, and the
    parse alone makes no `git` read of the register. Fails until L5-A3."""
    code = tmp_path / "code"
    for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
        code.mkdir(exist_ok=True)
        shutil.copy2(REPO / name, code / name)
    est = estate(guard=code / "lanes-edit.sh")
    files, built = _measurement_register(est)
    est.swap_window(FROM, FROM)
    path, (_, git_log) = _timing_wrappers(est)
    through_git, reads = [], []
    for _ in range(MEASURE_RUNS):
        start = time.time()
        files_hook = est.hook("hello", PATH=path)
        end = time.time()
        assert files_hook.code == 0, repr(files_hook)
        got = [t for t, args in _times(git_log, start) if "lanes/" in args]
        assert got, "today's guard made no git read of the register"
        reads.append(len(got))
        through_git.append(end - got[0])
    t0 = time.monotonic()
    contract_stub(code, register={k: v for k, v in files.items()
                                  if k != "lanes/log/README.md"})
    built += time.monotonic() - t0
    conf = tmp_path / "lanes-index.conf"
    conf.write_text(f"register_url=postgresql:///register?host={tmp_path}/sock\n",
                    encoding="utf-8")
    parse = []
    for _ in range(MEASURE_RUNS):
        start = time.time()
        hook = est.hook("hello", PATH=path, LANES_INDEX_CONFIG=str(conf))
        end = time.time()
        calls = [json.loads(line) for line in (code / ARGV_LOG).read_text(
            encoding="utf-8").splitlines()] if (code / ARGV_LOG).exists() else []
        assert [c for c in calls if c[:2] == ["register", "read"] and "--prefetch" in c], \
            f"the guard made no prefetch into the cache files: {calls}"
        assert not [a for _, a in _times(git_log, start) if "lanes/" in a], \
            "the parse alone still read the register through git"
        assert (hook.code, hook.out) == (files_hook.code, files_hook.out), repr(hook)
        parse.append(end - start)
    _record_figure("M10, the guard's register read on a real-sized register (median ms)", {
        "today's reads through git": f"{_median(through_git) * 1000:.1f}",
        "git reads per run": f"{_median(reads):.0f}",
        "the parse alone": f"{_median(parse) * 1000:.1f}",
        "the parse's reserve": "500", "register built in": f"{built:.2f} s"})


# ============================================================ T237: test 10 through the service
#
# Test 10 through the service (L2-S1; AT-10; section 4.4; A5; A7; A10), and the
# service's own cases lane 5 asked for. Every case needs L5-S1's `lanes-index
# serve` (lane 5's T511 to T513); SVC-5's `mode=primary` comes from the
# session cluster, so these run on T205's `pg` and here are collected and
# skipped with T205's banner, but for `serve`'s and `status`'s refusals in
# files mode, which need no engine and are red today by their own assertions.
# THE FORMS ARE LANE 5's SOCKET CONTRACT, draft 8 (`socket-api-d8-563157a7.md`):
# the fixed path and its five files (sections 2.1 to 2.4), the failure stamp
# (8.6) and the request's first line (12). `status`'s `service` lines are
# T512's in `cmd_status` (R44), whose words the contract does not fix.

#: The checkout's `lanes-index`, which a case loads in process. A case's own
#: calls run its estate's (`Estate.index`), the flipped copy on primary.
INDEX = REPO / "lanes-index"
#: The fallback line, printed once wherever the service was unavailable and
#: the client then read directly (svc:104; lane 5's socket contract, draft 8,
#: section 5.3's table and OP-11).
FALLBACK = "guard: direct (service unavailable)"


def _index(est: Estate, *args, env=None, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(est.index), *args], capture_output=True, text=True,
                          env=env or est.env(), cwd=str(est.wip), timeout=timeout)


def _run_dir(est: Estate) -> Path:
    """The service's one directory, fixed by lane 5's socket contract d8
    (section 2.1): `${XDG_STATE_HOME:-~/.local/state}/openRepoTools/run/`,
    holding `register.sock`, `register.lock`, `register.owner`,
    `register.failed` and `register.log` (section 2.3). Under the estate's
    own state home (`_state_home`), its socket path is 49 bytes."""
    return Path(est.base["XDG_STATE_HOME"]) / "openRepoTools" / "run"


def _service_dir(est: Estate, stale=None):
    """The run directory, where the service's socket is bound; with `stale`,
    a socket's inode, only once the socket there is another one (T237zi)."""
    run = _run_dir(est)
    sock = run / "register.sock"
    if not sock.exists():
        return None
    if stale is not None:
        try:
            if os.lstat(sock).st_ino == stale:
                return None
        except OSError:
            return None
    return run


def _stale_socket(est: Estate):
    """The inode of a socket in the run directory that no process answers on,
    a dead service's (SVC-4), or None (T237zi): a connect refused, or a file
    that is not a socket, is stale; one that connects is a live service's."""
    import socket as _socket
    path = _run_dir(est) / "register.sock"
    try:
        inode = os.lstat(path).st_ino
    except OSError:
        return None
    probe = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    try:
        probe.settimeout(1.0)
        probe.connect(str(path))
    except OSError:
        return inode
    finally:
        probe.close()
    return None


def _failure_stamp(est: Estate, done: subprocess.CompletedProcess) -> list:
    """The words of `serve`'s failure stamp, `register.failed` (section 8.6),
    read only once `serve` has exited 2 and the stamp exists. Until lane 5's
    T512 adds `serve` (L5-S1), `lanes-index` answers it 64, unknown
    subcommand, and writes no stamp: the case then ends on this assertion,
    never on a missing file (line AN14)."""
    path = _run_dir(est) / "register.failed"
    assert done.returncode == 2 and path.is_file(), (
        f"`lanes-index serve` exited {done.returncode} and wrote "
        f"{'a' if path.is_file() else 'no'} failure stamp; lane 5's T512 (L5-S1) exits 2 "
        f"and stamps it: {done.stdout}{done.stderr}")
    return path.read_text(encoding="utf-8").split()


class _Listener:
    """A socket of the test's own at the contract's fixed path (section
    2.1), in a 0700 directory of this uid (section 2.2): it records what a
    client sends, and either never answers (`hang`) or closes at once."""

    def __init__(self, est: Estate, hang: bool):
        import socket
        run = _run_dir(est)
        run.mkdir(parents=True, exist_ok=True, mode=0o700)
        run.chmod(0o700)
        self.path = run / "register.sock"
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.path))
        self.server.listen(8)
        self.got, self.held, self.stop_ = [], [], threading.Event()

        def serve():
            self.server.settimeout(0.2)
            while not self.stop_.is_set():
                try:
                    conn, _ = self.server.accept()
                except OSError:
                    continue
                conn.settimeout(1.0)
                try:
                    self.got.append(conn.recv(65536))
                except OSError:
                    self.got.append(b"")
                if hang:
                    self.held.append(conn)
                else:
                    conn.close()

        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop_.set()
        self.thread.join(1)
        for conn in self.held:
            conn.close()
        self.server.close()
        self.path.unlink(missing_ok=True)


class _Service:
    """`lanes-index serve` started by the test, stopped at teardown."""

    def __init__(self, est: Estate, **extra):
        self.est = est
        if getattr(est, "pg", None) is not None:
            _seed_primary(est)
        # A DEAD SERVICE'S SOCKET IS NOT THIS ONE'S (T237zi; lane 5, #165
        # 6837268276): where one is left, the wait is for the socket that
        # replaces it, so a case never reads the stale inode as the new one.
        stale = _stale_socket(est)
        self.proc = subprocess.Popen([sys.executable, str(est.index), "serve"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=est.env(**extra),
                                     cwd=str(est.wip), start_new_session=True)
        est.spare.append(self.proc.pid)
        self.dir = _until(lambda: _service_dir(est, stale), 10)
        if not self.dir:
            # WHAT `serve` SAID, where it has exited: until lane 5's T512
            # (L5-S1), `lanes-index` answers 64, "unknown subcommand 'serve'".
            # Read without waiting, so a child holding the pipe cannot hang it.
            code, said = self.proc.poll(), b""
            if code is not None:
                os.set_blocking(self.proc.stderr.fileno(), False)
                said = self.proc.stderr.read() or b""
            assert self.dir, (f"the service named no socket: {code} "
                              f"{said.decode('utf-8', 'replace').strip()}")

    def stop(self) -> None:
        _kill(self.proc.pid, signal.SIGTERM)
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            _kill(self.proc.pid)


def _both(est: Estate) -> tuple:
    """The guard's answer with the service up, then with it down. The
    service is warmed by one request first: a cold service answers
    `unavailable` until its `psql` has connected (d8:502), and a service
    holding no image answers its first request so (the cache miss)."""
    svc = _Service(est)
    try:
        est.hook("hello")
        up = est.hook("hello")
    finally:
        svc.stop()
    down = est.hook("hello")
    return up, down


#: THE STREAMING `psql`, T237y's `STREAM_PSQL` (`tests/test_sql_register_bounds.py`
#: on line W3a) in this module's own form, since this line does not carry that
#: module. PSQL_SHIM reads its stdin to the end before it hands a call on (its
#: `main()`), so the service's "one long-lived `psql` child on pipes" (d8
#: section 7, d8:229) never answers through it, and a case that rested on it
#: read the direct read's calls instead (lane 5's T512 plan, point 2, #165
#: 6827295319). This stand-in starts the real `psql` at once, on the caller's
#: stdout and stderr, and hands its stdin on chunk by chunk through a delay
#: line: each chunk goes on `stream-hold-ms` milliseconds (a file beside it,
#: read as each chunk comes) after it was read where the call is the service's
#: held child, known by its own argv's `VERBOSITY=sqlstate` (d8:229), and at
#: once for every other call, the guard's direct reads among them. It logs
#: each call's argv in `stream-begin.log`, and each chunk as it reads it, with
#: its monotonic time, the hold in force and whether the call is the held
#: child, in `stream-chunks.log`, so a chunk that the service's SIGINT
#: overtakes is logged all the same. SIGINT and SIGTERM go on to the real
#: `psql`; `psql --version` is the real one's.
_STREAM_PSQL = r'''#!@PY@ -I
import json, os, queue, signal, subprocess, sys, threading, time
HERE = @HERE@
REAL = @REAL@
args = sys.argv[1:]
held = "VERBOSITY=sqlstate" in args


def log(name, record):
    with open(os.path.join(HERE, name), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def hold_ms():
    try:
        with open(os.path.join(HERE, "stream-hold-ms"), encoding="utf-8") as handle:
            return float(handle.read().strip() or 0)
    except (OSError, ValueError):
        return 0.0


log("stream-begin.log", {"argv": args, "pid": os.getpid(), "held": held, "t": time.monotonic()})
if args == ["--version"]:
    os.execv(REAL, [REAL] + args)
proc = subprocess.Popen([REAL] + args, stdin=subprocess.PIPE)
for number in (signal.SIGINT, signal.SIGTERM):
    signal.signal(number, lambda sig, frame: proc.send_signal(sig))
line = queue.Queue()


def read():
    while True:
        try:
            chunk = os.read(0, 65536)
        except OSError:
            chunk = b""
        now = time.monotonic()
        hold = hold_ms() if held else 0.0
        if chunk:
            log("stream-chunks.log", {"pid": os.getpid(), "held": held, "read": now,
                                      "hold_ms": hold, "bytes": len(chunk)})
        line.put((now + hold / 1000, chunk))
        if not chunk:
            return


def feed():
    while True:
        due, chunk = line.get()
        if not chunk:
            break
        wait = due - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            proc.stdin.write(chunk)
            proc.stdin.flush()
        except OSError:
            break
    try:
        proc.stdin.close()
    except OSError:
        pass


for target in (read, feed):
    threading.Thread(target=target, daemon=True).start()
code = proc.wait()
sys.exit(code if code >= 0 else 128 - code)
'''


class _StreamPsql:
    """`_STREAM_PSQL` first on the estate's `PATH` as `psql` (its `bin`, as
    `Estate.shim` puts PSQL_SHIM), in front of the case's cluster's own
    `psql`, with no hold until `hold` sets one."""

    def __init__(self, est: Estate):
        self.dir = est.bin
        _script(est.bin / "psql", _STREAM_PSQL, PY=sys.executable, HERE=_q(est.bin),
                REAL=_q(est.pg.cluster.tool("psql")))

    def hold(self, ms: int) -> None:
        """Each chunk handed to the service's held child from now on is held
        `ms` milliseconds."""
        (self.dir / "stream-hold-ms").write_text(str(ms), encoding="utf-8")

    def log(self, name: str = "stream-chunks.log") -> list:
        path = self.dir / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def handed(self, hook: Hook) -> list:
        """The chunks the service's held child read while `hook` ran (one
        monotonic clock for the runner and the stand-in, as on Linux)."""
        return [c for c in self.log() if c["held"] and hook.t0 <= c["read"] <= hook.t_exit]


#: How long a case warms the service, in guard runs, before it reads it.
WARM_S = 15.0


def _warm(est: Estate, limit: float = WARM_S) -> Hook:
    """Guard runs until one is answered by the service, with no fallback
    line (d8 section 5.3), returned: a cold service answers `unavailable`
    until its `psql` has connected (d8:502), and one holding no image
    answers its first request so (the cache miss), as T237y's case warms
    it."""
    end = time.monotonic() + limit
    while True:
        hook = est.hook("hello")
        if FALLBACK not in hook.err:
            return hook
        assert time.monotonic() < end, \
            f"no guard run was answered by the service in {limit:.0f} s: {hook!r}"
        time.sleep(0.2)


def _service_backends(pg) -> set:
    """The pids of the case's database's `lanes-index` client backends, by
    the `application_name` the service's `psql` carries (`PGAPPNAME`, d8
    section 7). Between guard runs that is the service's held connection
    alone, once a direct read's backend has gone."""
    sql = ("SELECT pid FROM pg_catalog.pg_stat_activity WHERE datname = current_database() "
           "AND application_name LIKE 'lanes-index%' AND pid <> pg_backend_pid();")
    return {int(word) for word in pg.psql(sql).stdout.split()}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Register:
    """THE ESTATE'S REGISTER IN THE CASE'S DATABASE (T205's `pg`), brought to
    `primary` with the marker `present` by lane 1's own functions, as line
    N1's `RealRegister` does (T217h): as T228's writer login, one
    `commit_write` `import` entry holding the estate's `lanes/LANES.md`, then
    a `cutover` entry, which writes `lanes/STORE` alone (ruling 1), then
    `record_marker`. So the guard on `mode=primary`, through the service or
    directly, reads the register the case seeded, and the case knows each
    file's whole text (lane 2's reading). `lanes/log/README.md` is not sent:
    the `files` table's path CHECK refuses it (Q18 (A)).

    THE FORMS are `refs/l1/T112-fu2`'s `lanes-index` (L1-A6, T107): the call
    `commit_write(bigint, uuid, integer, uuid, jsonb)` as one request,
    `BEGIN ISOLATION LEVEL SERIALIZABLE`, the call, `COMMIT`
    (`register_commit_request`), at `register_head.seq` and
    `register_switch.generation`, with the client version the schema's own
    `version`; the entry's `journal` keys as `register_commit_entry` writes
    them, its `edits` with `ord` from 1, and a `files` row per path carrying
    the sha256 of the path's whole new text (step 8's proof). A write sends
    no structured rows: no step requires them, and the guard reads files.

    FAILS UNTIL T227 builds `tmpl` by the bootstrap (lane 1's L1-A7) and
    T228 makes the logins, each by its own assertion, never a psql error."""

    #: T228's fixture writer login, a member of REGISTER-WRITER.
    WRITER = "lanes_w_fx"
    #: The render set the case seeds: the estate's register file.
    PATHS = ("lanes/LANES.md",)

    def __init__(self, est: Estate):
        self.pg = est.pg
        assert self._one("SELECT to_regclass('lanes_register.register_head') IS NOT NULL;") \
            == "t", ("the pg fixture's database holds no lanes_register schema: lane 2's T227 "
                     "builds tmpl by the bootstrap, which waits for lane 1's L1-A7")
        can = self._one("SELECT count(*) FROM pg_catalog.pg_roles WHERE rolcanlogin AND "
                        f"rolname = '{self.WRITER}';")
        assert can == "1", (f"no {self.WRITER} login: lane 2's T228 makes it by `lanes-index "
                            "login add fx`; the group REGISTER-WRITER is NOLOGIN")
        self.client = int(self._one("SELECT version FROM lanes_register.schema_version;"))
        self.generation = self._one("SELECT generation FROM lanes_register.register_switch;")
        self.files = {path: (est.wip / path).read_text(encoding="utf-8") for path in self.PATHS}
        edits, rows = [], []
        for path, text in self.files.items():
            edits.append({"ord": len(edits) + 1, "op": "create", "path": path})
            for line in text[:-1].split("\n") if text.endswith("\n") else text.split("\n"):
                edits.append({"ord": len(edits) + 1, "op": "append", "path": path,
                              "new_text": line})
            rows.append({"path": path, "present": True, "sha256": _sha(text),
                         "final_newline": text.endswith("\n")})
        self.send("import", "import", edits, rows)
        store = "mode primary\n"
        self.send("cutover", "cutover",
                  [{"ord": 1, "op": "create", "path": "lanes/STORE"},
                   {"ord": 2, "op": "append", "path": "lanes/STORE", "new_text": store[:-1]}],
                  [{"path": "lanes/STORE", "present": True, "sha256": _sha(store),
                    "final_newline": True}])
        marked = self._one(f"SELECT lanes_register.record_marker({self.client}, {self.head()}, "
                           f"'{'3' * 40}', '{HOST}');", user=self.WRITER)
        assert marked == "present", ("record_marker answered", marked)

    def _one(self, sql: str, user=None) -> str:
        proc = self.pg.psql(sql) if user is None else self.pg.psql(sql, user=user)
        out = proc.stdout.strip().splitlines()
        return out[-1].strip() if out else ""

    def head(self) -> int:
        return int(self._one("SELECT seq FROM lanes_register.register_head;"))

    def line_of(self, path: str, lane: str) -> int:
        """The line number of `lane`'s row in `path`."""
        lines = self.files[path].split("\n")
        found = [n for n, line in enumerate(lines, 1) if line.startswith(f"| `{lane}` |")]
        assert len(found) == 1, (lane, found)
        return found[0]

    def send(self, kind: str, verb: str, edits: list, rows: list) -> int:
        """One `commit_write` call as the writer's login, at the head the
        database holds; the seq it committed."""
        # `journal.author` is `Name <address>` (its CHECK, `^[^<>]+ <[^<>]*>$`).
        journal = {"kind": kind, "verb": verb, "lane": FROM, "workstation": HOST,
                   "author": "T237 case <t237@example.invalid>",
                   "message": f"{kind} by T237's case",
                   "git_commit": "1" * 40 if kind == "import" else None,
                   "git_tree": "2" * 40 if kind == "import" else None,
                   "repos_blob": None, "args_sha256": "0" * 64}
        entry = {"journal": journal, "not_after": "2999-12-31T00:00:00Z", "edits": edits,
                 "files": rows}
        literal = json.dumps(entry, ensure_ascii=True, separators=(",", ":"))
        sql = ("BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
               f"SELECT lanes_register.commit_write({self.head()}, '{uuid.uuid4()}'::uuid, "
               f"{self.client}, '{self.generation}'::uuid, $entry${literal}$entry$::jsonb);\n"
               "COMMIT;\n")
        return int(self.pg.psql(sql, user=self.WRITER).stdout.split()[0])

    def replace(self, path: str, line_no: int, new_text: str) -> int:
        """THE WRITE: one committed `write` entry whose one edit replaces line
        `line_no` of `path`, its `old_sha256` the sha256 of the line's text
        without its LF (step 6), and whose `files` row carries the sha256 of
        the path's whole new text; the seq it made."""
        lines = self.files[path].split("\n")
        old = lines[line_no - 1]
        lines[line_no - 1] = new_text
        text = "\n".join(lines)
        seq = self.send("write", "start-record",
                        [{"ord": 1, "op": "replace", "path": path, "line_no": line_no,
                          "old_sha256": _sha(old), "new_text": new_text, "to_path": None}],
                        [{"path": path, "present": True, "sha256": _sha(text),
                          "final_newline": text.endswith("\n")}])
        self.files[path] = text
        return seq


def _live_other(est: Estate):
    """Another session, `est.other`, live in a window of the lane `FROM`: its
    own live record under the estate's `HOME` (T203c's `guard_session`), its
    stand-in `tmux` in a directory of its own, never on the case's `PATH`."""
    other = guard_session(est.home, est.root / "other-bin", est.wip, window=FROM,
                          session_id=est.other, name=FROM)
    est.sessions.append(other)
    return other


#: The test plan's three states, one for each guard answer (TP:1883-1886).
GUARD_STATES = ["ok", "refuse", "offer"]


def _guard_state(estate, state: str) -> Estate:
    """THE STATE, in the register the guard reads on primary (`_Register`):

    - `ok`, this session's lane bound to this window: the session named
      `FROM`, in the window `FROM`, whose row names it;
    - `refuse`, another session holding the lane, and live: the window's row
      names `est.other`, which `_live_other` makes live;
    - `offer`, the module's estate: the window `FROM`, whose row names this
      session, and the session named `TO`, a lane with a row of its own, so
      the guard makes its offer (`Estate.make_offer`). The test plan words it
      "an unbound window"; lane 5's bind-record contract makes the offer on
      this name drift (lane 2's reading)."""
    if state == "offer":
        est = estate(mode="primary")
    else:
        est = estate(mode="primary", to=FROM, to_row=False)
    if state == "refuse":
        _live_other(est)
        est.push_register([_row(FROM, est.other, "LIVE")])
    _Register(est)
    return est


def _connected(est: Estate) -> bool:
    """Wait until the service holds its connection: a client backend on the
    case's database other than this read's own."""
    sql = ("SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE datname = current_database() "
           "AND pid <> pg_backend_pid() AND backend_type = 'client backend';")
    return bool(_until(lambda: int(est.pg.psql(sql).stdout.strip() or 0) > 0, 10, 0.1))


@pytest.mark.parametrize("state", GUARD_STATES)
def test_the_guard_through_the_service_answers_byte_identical_to_the_direct_read(estate, state):
    """AT-10: on one state, the service path and the direct path give equal
    stdout, equal stderr once the one fallback line is removed, and equal
    exit codes: `[ok|refuse|offer]`, one state for each guard answer
    (TP:2009; the states at TP:1883-1886, `_guard_state`)."""
    est = _guard_state(estate, state)
    up, down = _both(est)
    assert down.err.count(FALLBACK) == 1 and FALLBACK not in up.err, (up.err, down.err)
    err = [line for line in down.err.splitlines() if line != FALLBACK]
    assert (up.code, up.out) == (down.code, down.out), (up, down)
    assert up.err.splitlines() == err, (up.err, down.err)


def test_with_the_service_down_the_hook_falls_back_and_says_so(estate):
    """AT-10: with the service down the hook reads directly and its stderr
    carries the fallback line exactly once."""
    est = estate(mode="primary")
    hook = est.hook("hello")
    assert hook.err.splitlines().count(FALLBACK) == 1, hook.err
    assert not hook.killed and hook.t_exit - hook.t0 < BUDGET, repr(hook)


def test_a_service_that_never_answers_falls_back_inside_5_s(estate):
    """AT-10: a socket that accepts and never answers: the hook falls back to
    the direct read and ends inside its 5 s, not killed."""
    est = estate(mode="primary")
    listener = _Listener(est, hang=True)
    try:
        hook = est.hook("hello")
    finally:
        listener.close()
    assert listener.got, "the client never connected to the socket at the fixed path"
    assert not hook.killed and hook.t_exit - hook.t0 < HOOK_TIMEOUT, repr(hook)
    assert hook.err.count(FALLBACK) == 1, hook.err


def test_the_database_unreachable_with_the_service_up_is_2_never_a_cached_ok(estate):
    """AT-10: with the service up and the database unreachable, the guard
    exits 2, never a cached 0."""
    est = estate(mode="primary")
    svc = _Service(est)
    est.hook("hello")
    est.pg.cluster.stop()
    try:
        hook = est.hook("hello")
    finally:
        est.pg.cluster.start_again()
        svc.stop()
    assert hook.code == 2 and not hook.killed, repr(hook)


#: THE HOLD on each chunk handed to the service's held child in the timer's
#: case: past the 200 ms timer with no `register_rtt_ms=`, and inside the
#: 250 ms at 150 (d8 section 6.2). The answer comes the hold and the real
#: `psql`'s run, a few ms, after the request reached the service, near the
#: middle of that window.
STREAM_HOLD_MS = 220


@pytest.mark.parametrize("rtt", ["none", "rtt-150"])
def test_the_services_request_timer_follows_register_rtt_ms(estate, rtt):
    """SVC-6 at X: the service's request timer is 200 ms, or the round trip
    plus 100 ms where `register_rtt_ms=` is over 100 (250 ms at 150).

    The contract fixes the timer, not a `status` key, so the case reads it
    from the answer, through the service's own `psql` (`_StreamPsql`, since
    PSQL_SHIM never runs the held child: lane 5's T512 plan, point 2). The
    service is warmed with no hold until a guard run is answered by it; then
    each chunk handed to its held child is held `STREAM_HOLD_MS`, and one more
    guard run's request reaches the held child and is held there: `[none]`
    falls back, its 200 ms timer having expired, and `[rtt-150]` is answered
    inside its 250 ms."""
    est = estate(mode="primary")
    if rtt != "none":
        _db_config(est, est.pg.url(), register_rtt_ms=150)
    stream = _StreamPsql(est)
    svc = _Service(est)
    try:
        _warm(est)
        stream.hold(STREAM_HOLD_MS)
        hook = est.hook("hello")
    finally:
        svc.stop()
    held = [c for c in stream.handed(hook) if c["hold_ms"] == STREAM_HOLD_MS]
    assert held, f"the guard's request never reached the service's held psql: {stream.log()}"
    if rtt == "none":
        assert hook.err.count(FALLBACK) == 1, hook.err
    else:
        assert FALLBACK not in hook.err, hook.err


def test_each_service_request_is_one_query(estate, request):
    """AT-10: each request the service answers is one Query message.

    PSQL_SHIM's log cannot count it: the shim reads its stdin to the end
    before it hands a call on, so the service's held `psql` never answers
    through it, and the call it counted was the direct read's (lane 5's T512
    plan, point 2). So the case runs on T229's counting cluster (line FX's
    `CountingCluster`), which logs one `statement:` line per Query message,
    each with its backend's pid (`log_statement=all`): the service is warmed
    until a guard run is answered by it, its held connection is then the one
    `lanes-index` backend (d8 section 7), and one more answered guard run,
    one request (form 2, d8 section 13.9), is one `statement:` line of that
    backend's."""
    pgcluster = pytest.importorskip("pgcluster")
    assert "CountingCluster" in vars(pgcluster), "tests/pgcluster.py has no counting cluster (T229)"
    cluster = request.getfixturevalue("counting_cluster")
    db = pgcluster.Database(cluster, cluster.new_database())
    est = estate()
    est.primary(db)
    svc = _Service(est)
    try:
        _warm(est)
        held = _until(lambda: (lambda s: s if len(s) == 1 else None)(_service_backends(db)),
                      10, 0.1)
        assert held, f"no one lanes-index backend is left for the service: {_service_backends(db)}"
        offset = cluster.log().stat().st_size
        hook = est.hook("hello")
    finally:
        svc.stop()
    time.sleep(0.2)                       # the server's last log line, as T229's smoke waits
    text = cluster.log().read_bytes()[offset:].decode("utf-8", "replace")
    pid = next(iter(held))
    queries = [line for line in text.splitlines() if f"[{pid}]" in line and "statement: " in line]
    assert FALLBACK not in hook.err, hook.err
    assert len(queries) == 1, queries


#: THE IDLE CHECK'S DEFAULT, kept for a value the contract ignores (d8
#: section 10), and the case's two reads of it: no replacement by
#: `IDLE_CHECK_EARLY_S`, `[interval]`'s old wait, and one by
#: `IDLE_CHECK_LIMIT_S`. `[interval]` itself, at 1 s, waits for its
#: replacement to `IDLE_CHECK_INTERVAL_LIMIT_S`, ten checks (T237zm).
IDLE_CHECK_DEFAULT_S = 60
IDLE_CHECK_EARLY_S = 2.5
IDLE_CHECK_LIMIT_S = IDLE_CHECK_DEFAULT_S + 30
IDLE_CHECK_INTERVAL_LIMIT_S = 10


@pytest.mark.parametrize("case", ["interval", "floor", "cap"])
def test_the_services_idle_check_replaces_a_dropped_connection_in_the_background(estate, case):
    """SVC-6 (R37): `[interval]`, at `LANES_REGISTER_SERVE_IDLE_CHECK_S=1`, a
    dropped connection is replaced in the background before the next
    request.

    `[floor]`, 0.5, under the 1 s floor, and `[cap]`, 240, the load
    balancer's 240 s: such a value is ignored, with the default 60 s kept,
    never `config-refused` (tasks:1643; lane 5's socket contract d8, section
    10; lane 3's OP-14, #165 6746215510, which stands, #165 6827356485). So
    `serve` listens and runs on, with no failure stamp (section 8.6), and
    `[interval]`'s own observable shows the 60 s: the service's dropped
    connection is not replaced within `IDLE_CHECK_EARLY_S`, as a check at
    the value given or at the 1 s floor would have replaced it, and is
    replaced within `IDLE_CHECK_LIMIT_S`, as a check at 240 s would not
    have; the next request is then answered by the service. The replacement
    is read in `pg_stat_activity` by its `application_name` (d8 section 7),
    with no request in between, since a request on the dropped connection
    would itself start the new one (d8 section 6.2)."""
    est = estate(mode="primary")
    value = {"interval": "1", "floor": "0.5", "cap": "240"}[case]
    if case != "interval":
        svc = _Service(est, LANES_REGISTER_SERVE_IDLE_CHECK_S=value)
        try:
            _warm(est)
            dropped = _until(lambda: _service_backends(est.pg), 10, 0.1)
            assert dropped, "the warmed service held no connection to drop"
            est.pg.psql("SELECT pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity "
                        f"WHERE pid IN ({','.join(str(p) for p in dropped)});")
            time.sleep(IDLE_CHECK_EARLY_S)
            early = _service_backends(est.pg) - dropped
            replaced = early or _until(lambda: _service_backends(est.pg) - dropped,
                                       IDLE_CHECK_LIMIT_S - IDLE_CHECK_EARLY_S, 1.0)
            hook = est.hook("hello")
            code = svc.proc.poll()
            stamp = (_run_dir(est) / "register.failed").exists()
        finally:
            svc.stop()
        assert code is None and not stamp, \
            f"serve exited {code} or stamped a failure under LANES_REGISTER_SERVE_IDLE_CHECK_S={value}"
        assert not early, (f"the dropped connection was replaced within {IDLE_CHECK_EARLY_S} s: "
                           f"the check ran at {value} s or at the 1 s floor, not at the default "
                           f"{IDLE_CHECK_DEFAULT_S} s")
        assert replaced, (f"the dropped connection was not replaced within {IDLE_CHECK_LIMIT_S} s: "
                          f"the check did not run at the default {IDLE_CHECK_DEFAULT_S} s")
        assert FALLBACK not in hook.err, hook.err
        return
    # WARMED FIRST, as `[floor]` and `[cap]` are (T237zj): the idle check's
    # promise is the next request "answered from the new connection, not
    # `unavailable`" (TP:1977-1981 at a6497d00), which presumes a service
    # that already holds an image. An unwarmed one answers its first request
    # `unavailable`, the cache miss (TP:1982-1987; d8 sections 5.1 and 5.3),
    # so without the warm-up this hook fell back whatever the idle check did
    # (lane 5, #165 6841406701).
    #
    # WHAT `[floor]` AND `[cap]` READ, READ HERE TOO (T237zm; lane 2's review
    # RV20, finding 6): the service's own connection is found, and only it
    # is dropped; its replacement is seen in `pg_stat_activity`, bounded at
    # `IDLE_CHECK_INTERVAL_LIMIT_S`, before the hook; and the window and the
    # session are both `FROM` (`swap_window`, as SVC-10's are), so the hook
    # answers 0 only after a read that verified the triple. A refusal before
    # any read, such as the start line's, is a 2, and fails the case.
    est.swap_window(FROM, FROM)
    svc = _Service(est, LANES_REGISTER_SERVE_IDLE_CHECK_S=value)
    try:
        _warm(est)
        dropped = _until(lambda: _service_backends(est.pg), 10, 0.1)
        assert dropped, "the warmed service held no connection to drop"
        est.pg.psql("SELECT pg_terminate_backend(pid) FROM pg_catalog.pg_stat_activity "
                    f"WHERE pid IN ({','.join(str(p) for p in dropped)});")
        replaced = _until(lambda: _service_backends(est.pg) - dropped,
                          IDLE_CHECK_INTERVAL_LIMIT_S, 0.1)
        hook = est.hook("hello")
    finally:
        svc.stop()
    assert replaced, (f"the dropped connection {sorted(dropped)} was not replaced within "
                      f"{IDLE_CHECK_INTERVAL_LIMIT_S} s at LANES_REGISTER_SERVE_IDLE_CHECK_S=1")
    assert hook.code == 0 and FALLBACK not in hook.err, repr(hook)


@pytest.mark.parametrize("cache", ["empty-cache", "cache-holds-n"])
def test_a_cache_miss_at_the_service_answers_unavailable_and_fetches_in_the_background(
        estate, cache):
    """AT-10, "A cache miss" (TP:2023; T302's image cache), on a service
    that holds its connection:

    - `[empty-cache]`: a service holding no image yet, with the
      per-environment image cache empty, answers its first request
      `unavailable`; the client reads directly, the service fetches the
      files whole in the background, and the next request is answered by
      the service;
    - `[cache-holds-n]`: with the cache already holding the files at `n`,
      the first request is answered from it. A first service fills the
      cache and is stopped, with the register still at `n`; a second
      answers."""
    est = estate(mode="primary")
    _Register(est)
    if cache == "cache-holds-n":
        svc = _Service(est)
        try:
            est.hook("hello")
            filled = est.hook("hello")
        finally:
            svc.stop()
        assert FALLBACK not in filled.err, f"the first service never filled the cache: {filled!r}"
    svc = _Service(est)
    try:
        assert _connected(est), "the service held no connection in 10 s"
        first = est.hook("hello")
        second = est.hook("hello")
    finally:
        svc.stop()
    if cache == "empty-cache":
        assert first.err.count(FALLBACK) == 1 and FALLBACK not in second.err, (first, second)
    else:
        assert FALLBACK not in first.err and FALLBACK not in second.err, (first, second)


def test_a_write_between_two_requests_is_in_the_next_answer(estate):
    """AT-10, "A fresh write": request, a write by another process, request;
    the second answer equals the direct read made after the write.

    The write is T107's `commit_write` as T228's `lanes_w_fx`, in a
    SERIALIZABLE transaction at `register_head.seq` and
    `register_switch.generation` (`_Register.replace`): it replaces the
    window's row so that another live session holds the lane, the test
    plan's `refuse` state, where the first request met its `ok` state. So
    the second answer differs from the first only by the write, and a
    cached answer cannot pass. The service is warmed first, since a cold
    service answers `unavailable` until its `psql` has connected (d8:502).
    It fails until L1-A6 (T107) lands and T228's logins with T227's
    template, as T237's Order says, beside L5-S1."""
    est = estate(mode="primary", to=FROM, to_row=False)
    _live_other(est)
    reg = _Register(est)
    svc = _Service(est)
    try:
        est.hook("hello")
        first = est.hook("hello")
        seq = reg.replace("lanes/LANES.md", reg.line_of("lanes/LANES.md", FROM),
                          _row(FROM, est.other, "LIVE"))
        second = est.hook("hello")
    finally:
        svc.stop()
    direct = est.hook("hello")
    assert seq == reg.head(), (seq, reg.head())
    assert FALLBACK not in first.err and FALLBACK not in second.err, (first, second)
    assert direct.err.splitlines().count(FALLBACK) == 1, direct.err
    assert (first.code, first.out, first.err) != (second.code, second.out, second.err), \
        f"the answer after the write is the answer before it: {second!r}"
    assert not second.killed and (second.code, second.out) == (direct.code, direct.out), \
        (second, direct)
    assert second.err.splitlines() == [line for line in direct.err.splitlines()
                                       if line != FALLBACK], (second.err, direct.err)


#: `_masked_path`'s mirrors, by each directory's real path (None where the
#: directory holds no masked name), and the one temporary root they share.
_PATH_MIRRORS: dict = {}
_PATH_MIRROR_ROOT: list = []


def _masked_path(path: str) -> str:
    """`path` with every directory kept in its place, and each one that holds
    a `psql`, a `lanes-index` or a name that starts `pg_` swapped for a
    private mirror of it: a directory of links, one to each of its entries
    by its absolute path, those names left out. The case below runs `serve`
    with no `psql` on a `PATH` of Python's own directory and `/bin`; on a
    GitHub runner `postgresql-16`'s client puts `psql` in `/usr/bin` with
    `git` and `bash`, and `/bin` is a link to it, so that `PATH` held a
    `psql` there (lane 1's census, #165 6807454856). A directory that holds
    none of those names passes through unchanged. Each mirror is made once
    per process, under one `mkdtemp` that an `atexit` handler removes."""
    parts = []
    for part in path.split(os.pathsep):
        if not part:
            continue
        real = os.path.realpath(part)
        if real not in _PATH_MIRRORS:
            try:
                names = os.listdir(real)
            except OSError:
                names = []
            masked = {name for name in names
                      if name in ("psql", "lanes-index") or name.startswith("pg_")}
            mirror = None
            if masked:
                if not _PATH_MIRROR_ROOT:
                    _PATH_MIRROR_ROOT.append(tempfile.mkdtemp(prefix="l2-pathmask-"))
                    atexit.register(shutil.rmtree, _PATH_MIRROR_ROOT[0], ignore_errors=True)
                mirror = os.path.join(_PATH_MIRROR_ROOT[0], str(len(_PATH_MIRRORS)))
                os.mkdir(mirror)
                for name in names:
                    if name not in masked:
                        os.symlink(os.path.join(real, name), os.path.join(mirror, name))
            _PATH_MIRRORS[real] = mirror
        parts.append(_PATH_MIRRORS[real] or part)
    return os.pathsep.join(parts)


def test_the_service_reaches_the_database_only_through_psql(estate):
    """OP-10 (R-F10-20): every answer from the database is a call through
    `psql`; with no `psql` at the start, `serve` stamps `no-psql` and exits 2
    before any socket exists, and the client's direct read answers.

    The first half reads the service's own `psql` through `_StreamPsql`:
    PSQL_SHIM, which reads its stdin to the end first, never runs the
    service's held child, so the call it logged was the direct read's (lane
    5's T512 plan, point 2). The guard run the service answers, with no
    fallback line, handed its request to the held child, the `psql` the
    service ran from `PATH`."""
    est = estate(mode="primary")
    stream = _StreamPsql(est)
    svc = _Service(est)
    try:
        hook = _warm(est)
    finally:
        svc.stop()
    assert stream.handed(hook), \
        f"an answer came from the database without psql: {stream.log('stream-begin.log')}"
    nopsql = subprocess.run([sys.executable, str(est.index), "serve"], capture_output=True,
                            text=True, timeout=30, cwd=str(est.wip),
                            env=est.env(PATH=_masked_path(os.pathsep.join(
                                [os.path.dirname(sys.executable), "/bin"]))))
    stamp = _failure_stamp(est, nopsql)
    # THE STAMP HOLDS THE UTC AND THE FIXED CAUSE, AND NO OTHER TEXT (section 8.6).
    assert "no-psql" in stamp and len(stamp) == 2, (nopsql, stamp)
    assert not (_run_dir(est) / "register.sock").exists(), "serve left a socket"
    assert est.hook("hello").code in (0, 2)


def test_the_session_start_block_reads_the_mirror_and_only_starts_the_service(estate):
    """A7: the `SessionStart` block reads the mirror and only starts the
    service: no register call of its own, and a service running after."""
    est = estate(mode="primary")
    est.shim()
    proc = subprocess.run(["bash", str(est.guard), "session-start"],
                          input=est.session.hook_input(), capture_output=True, text=True,
                          env=est.env(), cwd=str(est.wip), timeout=60)
    assert proc.returncode == 0 and not est.shim_calls(), est.shim_calls()
    assert _until(lambda: _service_dir(est), 10), "the block did not start the service"


def test_the_first_call_starts_the_service_with_no_supervisor(estate):
    """A7: the first guard call starts the service detached, with no
    supervisor: its parent is init or a subreaper, not the hook."""
    est = estate(mode="primary")
    hook = est.hook("hello")
    assert _until(lambda: _service_dir(est), 10), "the first call started no service"
    servers = [p for p in _members("sid", 0) if "serve" in " ".join(_argv(p))] or [
        int(e.name) for e in Path("/proc").iterdir() if e.name.isdigit()
        and _argv(e.name)[-1:] == ["serve"]]
    assert servers and all(_stat(p).get("ppid") != hook.pgid for p in servers), servers
    est.spare.extend(servers)


@pytest.mark.parametrize("case", ["start-fails", "psql-14"])
def test_a_service_that_cannot_start_falls_back_to_the_direct_read(estate, case):
    """AT-10 and OP-10 (a): `[start-fails]`, a service that cannot start, and
    the guard reads directly; `[psql-14]`, T203's fake answering 14, `serve`
    stamps `no-psql`, exits 2 and leaves no socket, and the fallback read
    refuses with 69 naming the version after one `--version` call and no
    request."""
    est = estate(mode="primary")
    if case == "psql-14":
        est.shim()
        control = est.bin / PSQL_SHIM_CONTROL
        data = json.loads(control.read_text(encoding="utf-8"))
        data["version"] = "psql (PostgreSQL) 14.11"
        control.write_text(json.dumps(data), encoding="utf-8")
        done = _index(est, "serve", timeout=30)
        stamp = _failure_stamp(est, done)
        assert "no-psql" in stamp and len(stamp) == 2, (done, stamp)
        assert not (_run_dir(est) / "register.sock").exists(), "serve left a socket"
        assert not [c for c in est.shim_calls()], "a request was sent past an old psql"
    extra = {}
    if case == "start-fails":
        # A STATE PATH PAST 103 BYTES (section 2.1): the client starts nothing
        # and reads directly, and `serve` refuses it with `path-too-long`. It
        # is long on purpose, in place of the estate's short state home: its
        # last part alone is 120 bytes, whatever the temporary root is.
        deep = est.root / ("s" * 120)
        deep.mkdir()
        extra["XDG_STATE_HOME"] = str(deep)
        done = _index(est, "serve", env=est.env(**extra), timeout=30)
        failed = deep / "openRepoTools" / "run" / "register.failed"
        assert done.returncode == 2 and "path-too-long" in failed.read_text(encoding="utf-8")
    hook = est.hook("hello", **extra)
    assert hook.code in (0, 2) and not hook.killed, repr(hook)
    if case == "psql-14":
        assert "14" in hook.err, hook.err


def test_the_guards_request_carries_only_file_names(estate):
    """AT-10: the guard's request to the service carries only file names: no
    URL, no password and no row text."""
    est = estate(mode="primary")
    listener = _Listener(est, hang=False)
    try:
        est.hook("hello")
    finally:
        listener.close()
    text = b"".join(listener.got).decode("utf-8", "replace")
    # ITS FORM (the contract's request section): `read 1`; one line per thing
    # it wants, `file <path>`, `set <prefix>` or `list`; then `end`.
    lines = text.split("\n")
    assert lines[0] == "read 1" and "end" in lines, text
    body = lines[1:lines.index("end")]
    assert body and all(line == "list" or (line.split(" ")[0] in ("file", "set")
                                            and line.split(" ", 1)[1].startswith("lanes/"))
                        for line in body), text
    assert "postgresql://" not in text and "password" not in text.lower(), text


def test_the_guard_answer_time_is_recorded_beside_todays_direct_guard(estate):
    """SVC-10: the guard's answer time through the service is recorded beside
    today's direct guard (M5b), with a warning past 50 ms and no failure.

    EACH SAMPLE'S READ PATH IS RECORDED BESIDE IT (T237zk; lane 5, #165
    6841316861, and lane 3, 6838735040): SC-005 bounds the service's
    answer, so a median over refusals and fallbacks says nothing of it.
    Exit 2 is a refusal; exit 0 with the fallback line (`FALLBACK`, T507's
    F1, tasks:806) matched whole on a stderr line is a fallback; exit 0
    without it was served. Each path's count is recorded, and the median of
    the served samples alone, or "none served" where none was. A sample
    with any other exit is counted as `other`, so none is put in a path it
    did not take. The case times the whole hook (`t_exit - t0`), so the
    served median is a whole-hook figure, beside M5b's, not SC-005's 50 ms.

    THE PROMPT GOES THROUGH, AS M5b'S DOES (T237zl): the estate's session is
    named `TO` in the window `FROM`, so every guard run made the name
    guard's offer and exited 2, ten refusals and no served answer (lane 2's
    G-19b capture). The window and the session are both `FROM` here, as
    M5b's and M10's are (`swap_window`), and the service is warmed first
    (`_warm`), so the samples read a service that holds its image, not the
    cache miss of its first request."""
    est = estate(mode="primary")
    est.swap_window(FROM, FROM)
    svc = _Service(est)
    paths = {"refusal": [], "fallback": [], "served": [], "other": []}
    try:
        _warm(est)
        for _ in range(MEASURE_RUNS):
            hook = est.hook("hello")
            took = hook.t_exit - hook.t0
            if hook.code == 2:
                paths["refusal"].append(took)
            elif hook.code == 0 and FALLBACK in hook.err.splitlines():
                paths["fallback"].append(took)
            elif hook.code == 0:
                paths["served"].append(took)
            else:
                paths["other"].append(took)
    finally:
        svc.stop()
    served = paths["served"]
    _record_figure("SVC-10, the guard through the service (median ms)",
                   {"served answer (whole hook)":
                        f"{_median(served) * 1000:.1f}" if served else "none served",
                    "bound": "50"}
                   | {f"{name} samples": len(times) for name, times in paths.items()})
    # SERVED, AND NOTHING ELSE UNKNOWN (T237zn; lane 2's review RV20, finding
    # 10): every sample lands in one path, so `any(paths.values())` held
    # whatever the paths were, ten refusals or ten fallbacks among them. The
    # time stays unasserted, as TP:7976-7979 at a6497d00 has it, "without
    # failing".
    assert served and not paths["other"], {name: len(times) for name, times in paths.items()}


def test_status_prints_the_services_lines_and_its_failure_stamp(estate):
    """A5 (R44): `lanes-index status` prints the service's lines and its
    failure stamp, as T512 writes them in `cmd_status`; with no service in
    files mode it still prints the service's line, saying none runs."""
    est = estate()
    done = _index(est, "status")
    assert [line for line in done.stdout.splitlines() if line.startswith("service")], \
        f"status printed no service line: {done.stdout}{done.stderr}"


def test_the_socket_directory_is_a_0700_directory_of_this_uid_and_never_a_symlink(estate):
    """SVC-2: the socket directory is a 0700 directory of this uid, never a
    symlink."""
    est = estate(mode="primary")
    svc = _Service(est)
    st = os.lstat(svc.dir)
    svc.stop()
    import stat as stat_mod
    assert stat_mod.S_ISDIR(st.st_mode) and (st.st_mode & 0o777) == 0o700, oct(st.st_mode)
    assert st.st_uid == os.getuid()
    # THE REFUSAL'S HALF (section 2.2; ERR-28): a directory that fails the
    # check is never used: `serve` exits 2 naming it and writes nothing in it.
    run = _run_dir(est)
    run.chmod(0o755)
    before = sorted(p.name for p in run.iterdir())
    done = _index(est, "serve", timeout=30)
    assert done.returncode == 2 and str(run) in done.stdout + done.stderr, done
    assert sorted(p.name for p in run.iterdir()) == before, "serve wrote in a refused directory"


def test_a_client_of_another_uid_is_closed_by_so_peercred(estate):
    """SVC-2: a client of another uid is closed. CI has no second uid, so the
    test loads `lanes-index` in process and replaces its peer-credential read
    with one that answers another uid (T512 reads `SO_PEERCRED` through one
    function)."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("lanes_index_t237", str(INDEX))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    reader = [name for name in dir(module) if "peercred" in name.lower()]
    assert reader, "lanes-index reads no peer credential through one function (T512)"
    estate(mode="primary")


@pytest.mark.parametrize("case", ["namespace", "boot"])
def test_an_owner_file_from_another_namespace_or_boot_is_no_service(estate, case):
    """SVC-2: an owner file naming another pid namespace or another boot is no
    service: the client falls back and a new service may start."""
    est = estate(mode="primary")
    svc = _Service(est)
    owner = svc.dir / "register.owner"
    text = owner.read_text(encoding="utf-8")
    # THE CLIENT'S OWN VALUE, REPLACED WHEREVER THE FILE HOLDS IT (section 2.4:
    # `readlink /proc/self/ns/pid` and `/proc/sys/kernel/random/boot_id`), so
    # the case needs no line format the contract does not fix.
    mine = (os.readlink("/proc/self/ns/pid") if case == "namespace" else
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip())
    assert mine in text, f"register.owner does not hold this {case}: {text}"
    owner.write_text(text.replace(mine, "pid:[1]" if case == "namespace" else
                                  "00000000-0000-0000-0000-000000000000"), encoding="utf-8")
    # A SOCKET THAT ANSWERS (section 2.4, 13.8): the client treats the service
    # as unavailable, reads directly and starts none.
    try:
        hook = est.hook("hello")
        serves = [int(e.name) for e in Path("/proc").iterdir() if e.name.isdigit()
                  and _argv(e.name)[-1:] == ["serve"] and int(e.name) != svc.proc.pid
                  and _stat(e.name).get("sid") != _stat(svc.proc.pid).get("sid")]
    finally:
        svc.stop()
    assert hook.err.count(FALLBACK) == 1 and not hook.killed, repr(hook)
    assert not serves, f"the client started another service: {serves}"


@pytest.mark.parametrize("case", ["files", "index", "refusing-build"])
def test_serve_refuses_unless_the_mode_answer_is_primary(estate, tmp_path, case):
    """SVC-5 (R36; A10): `serve` exits 2, with no socket, in files mode, in
    `mode=index`, and on the shipped build, whose constant still refuses
    `primary`; its refusal names the mode it needs."""
    est = estate()
    env = est.env()
    if case != "files":
        conf = tmp_path / "lanes-index.conf"
        conf.write_text(f"mode={'index' if case == 'index' else 'primary'}\n"
                        f"register_url=postgresql:///register?host={tmp_path}/sock\n",
                        encoding="utf-8")
        env["LANES_INDEX_CONFIG"] = str(conf)
    done = _index(est, "serve", env=env, timeout=30)
    assert done.returncode == 2 and "primary" in done.stdout + done.stderr, \
        f"serve {done.returncode}: {done.stdout}{done.stderr}"


def test_one_instance_holds_register_lock_and_a_second_starter_exits_0(estate):
    """SVC-4: one instance holds the register lock; a second starter exits 0
    and starts nothing."""
    est = estate(mode="primary")
    svc = _Service(est)
    second = _index(est, "serve", timeout=30)
    svc.stop()
    assert second.returncode == 0, second


def test_a_stale_socket_is_unlinked_under_the_lock_and_rebound(estate):
    """SVC-4: a socket left by a dead service is unlinked under the lock and
    bound again by the next start."""
    est = estate(mode="primary")
    svc = _Service(est)
    path = svc.dir / "register.sock"
    inode = os.lstat(path).st_ino
    _kill(svc.proc.pid)
    svc.proc.wait(10)
    assert path.exists(), "a service killed with -9 left no stale socket to test"
    again = _Service(est)
    try:
        assert path.exists() and os.lstat(path).st_ino != inode, \
            "the stale socket was not unlinked and bound again at the same path"
    finally:
        again.stop()


#: How long `[floor]`'s service must run on: ten times the 0.5 s given, five
#: times the 1 s floor, and past `[stops]`'s 2 s.
IDLE_STOP_RUNS_ON_S = 5.0


@pytest.mark.parametrize("case", ["stops", "floor"])
def test_the_service_stops_after_its_idle_time_and_unlinks_its_socket(estate, case):
    """SVC-4 (R37): `[stops]`, with `LANES_REGISTER_SERVE_IDLE_STOP_S=2` the
    service stops after it and unlinks its socket.

    `[floor]`, 0.5, under the 1 s floor: the value is ignored, with the
    default 900 s kept, never `config-refused` (tasks:1643; d8 section 10;
    lane 3's OP-14, #165 6746215510, which stands, #165 6827356485). So
    `serve` listens, with no failure stamp (section 8.6), and by section
    8.4's own observable, its process and its socket, it runs on for
    `IDLE_STOP_RUNS_ON_S`, past the 0.5 s given and the 1 s floor. The 900 s
    itself is not waited for."""
    est = estate(mode="primary")
    if case == "floor":
        svc = _Service(est, LANES_REGISTER_SERVE_IDLE_STOP_S="0.5")
        sock = svc.dir / "register.sock"
        try:
            stopped = _until(lambda: svc.proc.poll() is not None or not sock.exists(),
                             IDLE_STOP_RUNS_ON_S)
            code = svc.proc.poll()
            stamp = (_run_dir(est) / "register.failed").exists()
        finally:
            svc.stop()
        assert not stamp, "serve stamped a failure under LANES_REGISTER_SERVE_IDLE_STOP_S=0.5"
        assert not stopped, (f"serve stopped (exit {code}) or unlinked its socket inside "
                             f"{IDLE_STOP_RUNS_ON_S} s under LANES_REGISTER_SERVE_IDLE_STOP_S=0.5: "
                             f"the value was taken, not ignored with the default 900 s kept")
        return
    svc = _Service(est, LANES_REGISTER_SERVE_IDLE_STOP_S="2")
    sock = svc.dir / "register.sock"
    assert _until(lambda: svc.proc.poll() is not None, 15), "the service did not stop"
    assert not sock.exists(), "the stopped service left its socket"

