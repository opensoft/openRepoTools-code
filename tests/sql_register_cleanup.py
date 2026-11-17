# SPDX-License-Identifier: Apache-2.0
"""THE CLEAN-UP ENGINE TWO OF 007'S TEST MODULES SHARE (T270): the helpers
that own a case's processes, and the stand-ins of the clean-up regressions,
which `tests/test_sql_register_renderer_git.py` (T270) and
`tests/test_sql_register_rollback.py` (T273) held identical by `ast`, kept
here once, and imported by both (SonarCloud's quality gate on code PR 97 at
`f776b435`, 3.6% duplication on new code against its 3%, comment
6939998291; lane 3's reading, 6940039571; lane 2's ruling in round CX-34).

It is no test module: it holds no test and no landing-gate table, and
pytest collects nothing from it. The two modules import it from `tests/`,
as they import `tests/sql_register_helpers.py` and as `tests/conftest.py`
imports `tests/sql_register_gate.py`.

A PROCESS'S IDENTITY HERE (lane 3's Codex reviews of code PR 97 at
`18529e5a`, BLOCKING, and at `46cac748`, BLOCKING; lane 2's decision 1 in
round CX-33): the case's own, proved through the kernel, never by a pid and
a start token alone, which a process that takes the pid within the same
clock tick shares. Each case launches its processes with a fresh nonce in
their environment, `IDENTITY` (`_nonce`), which every process they start
inherits. A clean-up pins a process (`_pin`): its pidfd opened; its
environment, `/proc/<pid>/environ`, read in memory alone, never kept or
shown, and required to hold that exact entry; then a signal 0 sent through
the pidfd, whose success proves that the process the pidfd names held the
pid from the open through the read, so the read was its own. An environment
that cannot be read, is empty or lacks the entry fails closed: that process
is never signalled, and where a record or the estate names it, that is
reported. The case's own child, pinned while it is unreaped, is
authoritative and needs no nonce (`_pin_child`). Every signal goes through a
pidfd (`signal.pidfd_send_signal`), never by a number, and a group is never
signalled by its id. Where this Python or kernel has no pidfd, a clean-up
fails closed (`_pidfds`). The start token, field 22 of `/proc/<pid>/stat`
(`starttime`, in clock ticks since boot), which each module's wrapper logs,
only matches a record to a live process.

EACH MODULE KEEPS ITS OWN: the renderer's clean-up (`_quiesce` and the
reads it makes) and the rollback's teardown (`_teardown` and its steps);
each module's `GIT_WRAPPER`, `_logged`, `_Stuck`, and its `_let_go` and
`_open_when_held`, whose docstrings name their own module's owners, with
`ABORT` beside its `_let_go`; and each module's own data constants and file
helpers.

Python 3.9 or later: the standard library, and pytest for `LINUX_ONLY`'s
mark.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest


# ------------------------------------------------------------------ owned processes
#: The environment variable that carries a case's nonce.
IDENTITY = "SQL_REGISTER_CASE_ID"


def _nonce() -> str:
    """A fresh nonce for one case's processes (`IDENTITY`)."""
    return uuid.uuid4().hex


def _stat(pid: int) -> dict | None:
    """`/proc/<pid>/stat`, read once: the process's state, ppid, process
    group, session and start token (field 22, as text); None where no
    process has the pid."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_bytes()
    except OSError:
        return None
    fields = raw[raw.rindex(b")") + 2:].split()
    return {"state": fields[0].decode(), "ppid": int(fields[1]), "pgrp": int(fields[2]),
            "session": int(fields[3]), "start": fields[19].decode()}


def _carried(pid: int) -> str | None:
    """The nonce `pid`'s environment carries (`IDENTITY`), read from
    `/proc/<pid>/environ` in memory alone, never kept or shown; None where
    it carries none, or its environment cannot be read or is empty."""
    try:
        environ = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return None
    prefix = f"{IDENTITY}=".encode()
    for entry in environ.split(b"\0"):
        if entry.startswith(prefix):
            return entry[len(prefix):].decode("utf-8", "replace") or None
    return None


def _pidfds() -> None:
    """Fails closed (`RuntimeError`) where this Python has no pidfd: no
    clean-up here falls back to a signal by number. `os.pidfd_open` and
    `signal.pidfd_send_signal` are Python 3.9's, on Linux 5.3 and later;
    a kernel without them refuses the open, which `_pin` raises."""
    missing = [name for name, there in (("os.pidfd_open", hasattr(os, "pidfd_open")),
                                        ("signal.pidfd_send_signal",
                                         hasattr(signal, "pidfd_send_signal")))
               if not there]
    if missing:
        raise RuntimeError(f"{' and '.join(missing)} missing: a clean-up here signals a process "
                           f"only through a pidfd (Python 3.9 or later, Linux 5.3 or later), "
                           f"never by its number")


class _Pinned:
    """A PROCESS PINNED (`_pin`, `_pin_child`): its pid, its start token and
    its pidfd, held until `close()`. Every signal goes through the pidfd,
    which names this process alone, ended or not; its exit is read from it."""

    def __init__(self, pid: int, start: str, fd: int):
        self.pid, self.start, self.fd = pid, start, fd

    def gone(self, seconds: float = 0) -> bool:
        """Whether it has ended, within `seconds`: its pidfd reads as ready
        (`POLLIN`)."""
        import select
        poller = select.poll()
        poller.register(self.fd, select.POLLIN)
        return bool(poller.poll(int(seconds * 1000)))

    def alive(self) -> bool:
        """Whether it still holds its pid and runs: a signal 0 through its
        pidfd succeeds, as it does until the process is reaped, and the
        pidfd is not readable, as it is once the process has ended."""
        try:
            signal.pidfd_send_signal(self.fd, 0)
        except ProcessLookupError:
            return False
        return not self.gone()

    def send(self, sig: int) -> None:
        try:
            signal.pidfd_send_signal(self.fd, sig)
        except ProcessLookupError:
            pass  # it has ended; the pidfd names it alone, so no other process is signalled

    def close(self) -> None:
        os.close(self.fd)


def _opened(pid: int) -> int | None:
    """`os.pidfd_open(pid)`; None where no process has the pid. Any other
    failure raises (`RuntimeError`): there is no fallback to a number."""
    _pidfds()
    try:
        return os.pidfd_open(pid)
    except ProcessLookupError:
        return None
    except OSError as exc:
        raise RuntimeError(f"os.pidfd_open({pid}) failed ({exc}): a clean-up here signals a "
                           f"process only through a pidfd, never by its number") from exc


def _pin(pid: int, nonce: str | None) -> _Pinned | None:
    """`pid` PINNED BY THE CASE'S IDENTITY (lane 2's decision 1 in round
    CX-33): its pidfd opened; its stat and its environment read, the
    environment required to carry `nonce` (`_carried`); then a signal 0
    through the pidfd (`_Pinned.alive`), whose success proves the process
    the pidfd names held the pid from the open through both reads, so they
    were its own. None, the pidfd closed and nothing signalled, where it has
    ended, is a zombie, or its environment cannot be read, is empty, or does
    not carry `nonce`: it fails closed."""
    fd = _opened(pid)
    if fd is None:
        return None
    now = _stat(pid)
    pinned = _Pinned(pid, now["start"] if now else "", fd)
    if (not nonce or now is None or now["state"] in ("Z", "X") or _carried(pid) != nonce
            or not pinned.alive()):
        pinned.close()
        return None
    return pinned


def _pin_child(proc) -> _Pinned | None:
    """The case's own child `proc`, pinned while it is unreaped
    (`returncode` None): authoritative, with no nonce asked, since the
    kernel gives its pid again only once this process reaps it (lane 2's
    decision 1 in round CX-33). None where it has been reaped, or no process
    has its pid."""
    if proc is None or proc.returncode is not None:
        return None
    fd = _opened(proc.pid)
    if fd is None:
        return None
    now = _stat(proc.pid)
    return _Pinned(proc.pid, now["start"] if now else "", fd)


def _table() -> dict:
    """{pid: `_stat`} of every process this user owns, but pid 1, this
    process and its ancestors, which no clean-up here ever signals."""
    mine, pid = set(), os.getpid()
    while pid > 1 and pid not in mine:
        mine.add(pid)
        above = _stat(pid)
        pid = above["ppid"] if above else 0
    table, uid = {}, os.getuid()
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) in mine or int(name) == 1:
            continue
        try:
            if os.stat(f"/proc/{name}").st_uid != uid:
                continue
        except OSError:
            continue
        found = _stat(int(name))
        if found is not None:
            table[int(name)] = found
    return table


def _stopped(held: _Pinned) -> bool:
    """Whether `held` is seen stopped, or has ended: its stat, read while its
    pidfd shows it alive, in state `T` or `t`. A stopped process forks no
    child, so a read made once each one found is stopped misses none."""
    now = _stat(held.pid)
    if held.gone():
        return True
    return now is not None and now["start"] == held.start and now["state"] in ("T", "t")


def _owned(table: dict, nonces: set, pinned: dict) -> list:
    """Each process of `table` not pinned already whose environment carries
    one of `nonces`, pinned by it (`_pin`): the case's, found by its
    identity alone, with no leader, parent or record needed (lane 3's Codex
    review of code PR 97 at `46cac748`, SHOULD 1)."""
    found = []
    for pid, row in table.items():
        nonce = _carried(pid) if (pid, row["start"]) not in pinned else None
        if nonce in nonces:
            held = _pin(pid, nonce)
            if held is not None:
                found.append(held)
    return found


def _keep(pinned: dict, fresh: list, held) -> None:
    """`held`, where there is one, registered in `pinned` by its pid and
    start token, before any signal, and in `fresh`."""
    if held is not None:
        pinned[(held.pid, held.start)] = held
        fresh.append(held)


def _send_each(helds, sig: int, raised: list) -> None:
    """`sig` through each pidfd of `helds`, each in a `try` of its own: what
    one raises is kept in `raised`, and the rest are still signalled (lane
    3's Codex review of code PR 97 at `46cac748`, SHOULD 6)."""
    for held in helds:
        try:
            held.send(sig)
        except OSError as exc:  # kept; the rest are still signalled
            raised.append(exc)


def _release(helds, raised: list) -> None:
    """Each pidfd of `helds` let go, each in a `try` and `finally` of its
    own: its process killed (SIGKILL) where it is not yet gone, so none is
    left stopped, then the pidfd closed. What one raises is kept in
    `raised`, and the rest are still let go (SHOULD 6 at `46cac748`)."""
    for held in helds:
        try:
            if not held.gone():
                held.send(signal.SIGKILL)
        except OSError as exc:  # kept; the rest are still let go
            raised.append(exc)
        finally:
            held.close()


def _wait_all(test, helds, until: float, pause: float = 0.01) -> bool:
    """Whether `test(held)` holds for each of `helds` by the time `until`
    (`time.monotonic()`), polled every `pause` s."""
    while not all(test(held) for held in helds):
        if time.monotonic() >= until:
            return False
        time.sleep(pause)
    return True


def _raise_first(errors: list) -> None:
    """The first of `errors` raised as it is, each other one named in a
    `RuntimeError` set as its cause; nothing where there is none. No
    exception group, so Python 3.9 parses it."""
    if len(errors) > 1:
        raise errors[0] from RuntimeError("; ".join(f"{type(exc).__name__}: {exc}"
                                                    for exc in errors[1:]))
    if errors:
        raise errors[0]


# ------------------------------------------------------------------ stand-ins
#: The clean-up regressions of both modules run on Linux alone.
LINUX_ONLY = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="a FIFO opened O_RDWR, and /proc, are Linux's")


#: A reader of one byte from a FIFO, as a held call, a held push or a launcher
#: reads it.
READ_ONE = "import os, sys; os.read(os.open(sys.argv[1], os.O_RDONLY), 1)"


#: A process that stays until it is ended.
SLEEP = "import time; time.sleep(300)"


#: How a stand-in's process says who it is: its pid and its start token, from
#: its own `/proc/self/stat`, one line on its stdout, which it then lets go,
#: so the case pins exactly that process, by the case's identity, never one
#: that took its pid (`_reported`).
SAY_ME = ("import os, sys, time\n"
          "def say_me():\n"
          "    raw = open('/proc/self/stat', 'rb').read()\n"
          "    token = raw[raw.rindex(b')') + 2:].split()[19]\n"
          "    os.write(1, b'%d %s\\n' % (os.getpid(), token))\n"
          "    os.dup2(os.open(os.devnull, os.O_WRONLY), 1)\n")


#: A stand-in that leads a group with one member in it, a child that says who
#: it is (`SAY_ME`): a renderer's (T270), or a held push's, started in a
#: session of its own as T320's `_run_bounded` starts each git call, with
#: its git (T273). Both stay until they are ended.
LEADS_A_GROUP = SAY_ME + ("if os.fork() == 0:\n"
                          "    say_me()\n"
                          "    time.sleep(300)\n"
                          "    os._exit(0)\n"
                          "time.sleep(300)\n")


#: A group's leader that leaves a member behind: it forks a child in its own
#: group, which says who it is (`SAY_ME`) and stays, and ends at once.
LEAVES_A_MEMBER = SAY_ME + ("if os.fork() == 0:\n"
                            "    say_me()\n"
                            "    time.sleep(300)\n"
                            "    os._exit(0)\n")


class _Pipe:
    """A child's pipe, which only records that it was closed."""

    def __init__(self):
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Undying:
    """A pin whose process is never seen gone: each signal and the close
    are recorded, and nothing is signalled."""

    pid, start = 4194304 + 9, "1"

    def __init__(self):
        self.calls: list = []

    def gone(self, seconds: float = 0) -> bool:
        return False

    def send(self, sig: int) -> None:
        self.calls.append(sig)

    def close(self) -> None:
        self.calls.append("close")


def _with_identity(nonce: str) -> dict:
    """This process's environment with the case's nonce (`IDENTITY`), for a
    stand-in the clean-up must own by it."""
    return dict(os.environ, **{IDENTITY: nonce})


def _fifo_reader(path, env: dict | None = None) -> subprocess.Popen:
    """A child that reads one byte from the FIFO at `path`, in the
    environment `env` where given."""
    return subprocess.Popen([sys.executable, "-I", "-c", READ_ONE, str(path)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True, env=env)


def _on_fifo(proc: subprocess.Popen, seconds: float = 5, fifo=None) -> bool:
    """Whether `proc` is seen on a FIFO within `seconds`: asleep in its
    `open()` (`wait_for_partner`) or its `read()`, or, where `fifo` is
    given, holding it open (a link in its `/proc/<pid>/fd` is the FIFO's
    path), so a wait channel the kernel does not show still finds it. False
    where it ends first, the time runs out, or its `/proc` cannot be read."""
    path = os.path.realpath(str(fifo)) if fifo is not None else None
    deadline = time.monotonic() + seconds
    while proc.poll() is None and time.monotonic() < deadline:
        try:
            wchan = Path(f"/proc/{proc.pid}/wchan").read_text(encoding="utf-8")
        except OSError:
            return False
        if any(word in wchan for word in ("partner", "pipe", "fifo")):
            return True
        if path is not None and path in _fd_links(proc.pid):
            return True
        time.sleep(0.01)
    return False


def _fd_links(pid: int) -> list:
    """What each of `pid`'s open fds links to, as `/proc/<pid>/fd` shows it;
    an fd closed while they are read is passed over."""
    links = []
    try:
        names = os.listdir(f"/proc/{pid}/fd")
    except OSError:
        return links
    for name in names:
        try:
            links.append(os.readlink(f"/proc/{pid}/fd/{name}"))
        except OSError:
            continue
    return links


def _ended(proc: subprocess.Popen, seconds: float = 5) -> bool:
    """Whether `proc` ends within `seconds`."""
    try:
        proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        return False
    return True


def _reap_one(proc, seconds: float = 30):
    """One child a case started, killed by its pid where it is still
    unreaped, its output read for at most `seconds`; its pipes closed in a
    `finally`, and, where it is still unreaped, one more wait of at most
    `seconds`, which raises where it times out. Returns its stderr."""
    try:
        if proc.poll() is None:
            proc.kill()
        return proc.communicate(timeout=seconds)[1]
    finally:
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                pipe.close()
        if proc.returncode is None:
            proc.wait(timeout=seconds)


def _reap_all(procs: list) -> list:
    """Each child a case started reaped (`_reap_one`), every one tried
    whatever an earlier one raised; the first error raised once the whole
    set is done, the others named as its cause (lane 3's Codex review of
    code PR 97 at `46cac748`, SHOULD 4). Returns what each wrote to its
    stderr, None where that could not be read."""
    said, errors = [], []
    for proc in procs:
        try:
            said.append(_reap_one(proc))
        except Exception as exc:  # every child is still tried; raised below
            said.append(None)
            errors.append(exc)
    _raise_first(errors)
    return said


def _each(*steps) -> None:
    """Each of `steps` called, each tried whatever the one before it raised;
    then the first error raised, the others named as its cause."""
    errors = []
    for step in steps:
        try:
            step()
        except Exception as exc:  # each step is tried; raised below
            errors.append(exc)
    _raise_first(errors)


class _GapFifo:
    """A FIFO's path whose `unlink()` first starts a reader on it and waits
    until that reader is on the FIFO: a reader that comes in the gap just
    before the unlink (the coordinator's `GapPath`, #165 6934112467)."""

    def __init__(self, path: Path, readers: list):
        self.path, self.readers, self.on = path, readers, False

    def __str__(self) -> str:
        return str(self.path)

    def unlink(self, missing_ok: bool = False) -> None:
        self.readers.append(_fifo_reader(self.path))
        self.on = _on_fifo(self.readers[-1], fifo=self.path)
        self.path.unlink(missing_ok=missing_ok)


def _reported(proc: subprocess.Popen, what: str, nonce: str, seconds: float = 30) -> _Pinned:
    """The process whose pid `proc`'s tree printed (`SAY_ME`), pinned by the
    case's identity (`_pin`): exactly that process, alive. Its line is read
    under `select` with an absolute deadline, `seconds` on: where none
    comes by then, `proc` is ended and reaped (`_reap_all`), and it raises
    with what `proc` said (lane 3's Codex review of code PR 97 at
    `46cac748`, SHOULD 2)."""
    import select
    if not select.select([proc.stdout], [], [], seconds)[0]:
        said = _reap_all([proc])
        raise AssertionError(f"{what}: nothing was printed within {seconds:g} s; its starter "
                             f"was ended ({proc.returncode}) and said {said}")
    words = proc.stdout.readline().split()
    assert len(words) == 2, f"{what}: no pid and start token were printed"
    held = _pin(int(words[0]), nonce)
    assert held is not None, f"{what}: pid {words[0]} was gone, or not the case's, when pinned"
    return held


def _end_pin(held, seconds: float = 5) -> None:
    """A process the case pinned, killed through its pidfd where it is still
    there, and seen gone within `seconds` (its pidfd readable); the pidfd
    closed in a `finally`; it raises (`RuntimeError`) unless the process is
    seen gone (lane 3's Codex review of code PR 97 at `46cac748`,
    SHOULD 3)."""
    try:
        if not held.gone():
            held.send(signal.SIGKILL)
        if not held.gone(seconds):
            raise RuntimeError(f"pid {held.pid} is still there {seconds:g} s after its SIGKILL "
                               f"through its pidfd")
    finally:
        held.close()
