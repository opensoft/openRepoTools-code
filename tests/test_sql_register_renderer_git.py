# SPDX-License-Identifier: Apache-2.0
"""Feature 007's test 5 and AT-C8: the renderer's git half and its push
(L2-G1; L2-G5's C8; AT-5; AT-C8; T270; FR-044, FR-045, FR-046, FR-059)
(opensoft/openRepoTools#165).

T270 writes 25 tests: AT-5's 23 and AT-C8's one are here (TP:1016-1246,
TP:3173-3196, at the test plan `8702b70a`). Its 25th, test 1's part G,
`test_the_mirror_on_origin_equals_a_full_render_after_each_write`, is in
`test_sql_register_render.py`, which line W4b owns; it is not here. Twenty
more, at the end, test no AT case: they are the fault-path regressions of
this module's own clean-up (lane 3's Codex reviews of code PR 97 at
`6d479418`, SHOULDs 1, 3 and 4, at `18529e5a`, BLOCKING and SHOULDs 1, 3
and 4, and at `46cac748`, BLOCKING and SHOULDs 1 to 7; the coordinator's
#165 6934112467 and his three points, #165 6938182757).

THE ESTATE (AT-5, "Fixture"; AT-C8, "Fixture"). Each case's database is
`pg_imported` (T227b): test 7's register imported at seq 0, the switch at
`files`. Its origin is a bare copy of the session's `imported_register`
origin, at C, so a case that pushes pushes to its own. The estate goes to
`primary` by AT-LR006's route (TP:4610-4615), as T304's own test does: a
`cutover` entry at seq 1 through `commit_write`, as REGISTER-WRITER, which
creates `lanes/STORE` with D21's fields; the marker commit, C plus that
`lanes/STORE` (SQL's own `render_file` of it), with `Register-Seq: 1`,
pushed to origin's `main` by hand; then `record_marker`. That is the open
point 27 form, "AT-5's `files` case pushes the marker commit by hand and
needs only the renderer's side", taken for `primary` too, so no case here
waits for lane 3's T327 (the cutover's own push). `n`, the head after the
cutover, is 1. Lane checkouts are clones of that origin, each with its own
`$HOME`, `workspace.yaml` naming a view of it, and `LANES_REPO` at it (test
7's `Workspace` form). That view is W. A lane whose writes fork the
renderer also has its own register checkout `<c>`, `<W>-lanes/<lane>/`,
made by `lanes-edit.sh lane-checkout <lane> --create`, since on primary
each write goes through it whatever `LANES_REPO` says, and its fork
renders there (T270e; `RenderEstate.own_checkout`).

ENTRIES "WRITTEN THROUGH THE WRITE PATH" (TP:1055-1056) come two ways:
- by `commit_write` as REGISTER-WRITER, the write path's SQL half (T107),
  where the case then starts the renderer itself, as a fork starts it,
  `lanes-index render --checkout <c>` in a session of its own. Each of
  these cases tests the renderer, never the writer or the fork;
- by `lanes-edit.sh log NOTED` on `primary` through T203's flipped copy,
  whose fork starts the renderer (lane 4's T415 and T416, L4-B13), where
  the oracle is about writers and forks (the writer- and fork-side cases,
  at the end).

TEST 5'S `git` WRAPPER (TP:1059-1082; open point 8, TP:8792-8812) is first
on the `PATH` of every `lanes-index` and `lanes-edit.sh` run here. It logs
each call as a JSON line: its subcommand, argv, pid, the pid above it (the
renderer) with that process's start token, field 22 of its
`/proc/<pid>/stat`, the repository it runs in, the time, and the environment's
`GIT_SSH_COMMAND`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_NOSYSTEM`,
`SSH_AUTH_SOCK`, `LANES_NO_FETCH` and `GIT_INDEX_FILE`. Before anything
else each call writes its launch record, its pid and start token, to
`git-wrapper.started`, which `arm()` never resets. Its arms, each on
one subcommand, and on one repository where `where` names it: `hold` on a
FIFO (re-armed per call, `times` bounding it), where an abort release
(`_let_go`'s `abort`) ends the call with no git; `kill`, SIGKILL to the
renderer's process group, member by member through pidfds, each pinned by
the case's identity (`IDENTITY`, the nonce in the estate's environment),
after leaving `<GIT_INDEX_FILE>.lock` where `index_lock` asks, as git
inside `read-tree` leaves it; `fail`, exit 1;
`reject`, git's non-fast-forward refusal with exit 1, N times, then
disarmed; `stall`, a sleep before the real git. `render_only` limits an
arm to the calls of a `lanes-index render --checkout`, by the argv of the
process above the call (`/proc/<pid>/cmdline`, read in memory), which the
log keeps as `render`, true or false. `redirect` sends a
`fetch` or `push` of a GitHub URL to the bare origin in its place.
Section 3.2's `psql` shim is beside it, handing every call to the
engine's own `psql` by its path.

THE PATH: every directory of the caller's `PATH` is kept, in its place; one
that holds a `psql`, a `lanes-index` or a `pg_` name is swapped for a
private mirror without them (`_masked_path`, lane 2's mask policy, as LX's
T253e has it). The case's own `psql` is the shim, in the estate's `bin`.

THE WAITS. A case that starts the renderer itself waits for its exit. A
render forked by a write is waited for by open point 8's two waits, and no
other: a poll of `status` every 100 ms until its lag is 0, under 30 s,
each poll after the harness's own fetch of the W `status` reads; or,
where the lag must stay above 0, a wait for every renderer pid the wrapper
logged after the write to exit.

WHAT EACH FAILS UNTIL. Every case fails until lane 3's T320 to T323 (the
push, the lock and its handshake, the pass, its bounds); line R holds them
at `refs/l1/V-round4`. `test_six_lost_races_leave_the_last_write_for_the_
next_write_or_reconcile`, which T325's verify selects by `reconcile`, also
fails until T325, at its own assertion: until then `reconcile` on `primary`
is T117's read-only check. The cases whose writes fork the renderer, at the end,
also fail until lane 4's T415 and T416 (L4-B13). Every case is RE: without
PostgreSQL 16 it skips with T205's banner.

COPIED, NEVER SHARED (lane 2's rule for wave 12): `_masked_path` from line
LX's T253e (`tests/test_sql_register_landing_expired.py`); `_rows`, the
`Workspace` form of a lane checkout, and T203's flipped copy with
`lanes-edit.sh` beside it (`flipped_indexer`) from line W3a's
`tests/test_sql_register_import.py`; the cutover entry and the commit call
from line RB's `tests/test_sql_register_rollback.py`; `_open_when_held`
from the same; `_stats` from the import module.

READINGS, NOT FOUND IN A CONTRACT:
- AT-LR006'S ROUTE to `primary`, and the marker commit pushed by hand, as
  above.
- "WRITTEN THROUGH THE WRITE PATH" is read as the commit call alone where
  the oracle is the renderer's, so those cases start the renderer
  themselves. The six-lost-races case is one: the renderer that loses six
  races is started as a fork starts it, for its one write.
- `reconcile` "in the given checkout" (B14 tasks:1531) is read as
  `lanes-index reconcile` run in the lane's checkout, its workspace root,
  with the `mode=primary` configuration, and no `--checkout`.
- AT DEPTH 0 "no `--skip`" (TP:1198-1199) is read as no page after the
  first: the walk's one `log` call may say `--skip 0`, as line R's does.
- THE COMMIT'S MESSAGE: "each message equals its journal entry's" is read
  through T322's form: the entry's message, then `Register-Seq: <k>`, in its
  final trailer block where its last paragraph is one, or as a new last
  paragraph after one blank line.
"""

from __future__ import annotations

import atexit
import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_cleanup import (IDENTITY, LEADS_A_GROUP, LEAVES_A_MEMBER, LINUX_ONLY, SAY_ME,
                                  SLEEP, _GapFifo, _Pipe, _Settled, _Undying, _carried, _each,
                                  _end_pin, _ended, _fifo_reader, _keep, _misrecorded, _nonce,
                                  _owned, _pidfds, _pin, _pin_child, _raise_first, _reap_all,
                                  _release, _reported, _send_each, _settle_pinned, _stat, _table,
                                  _with_identity)
from sql_register_helpers import PSQL_SHIM, PSQL_SHIM_CONTROL, PSQL_SHIM_LOG, flipped_copy

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

LANES_EDIT = REPO / "lanes-edit.sh"
INDEXER = REPO / "lanes-index"

#: The register's schema, and the role the commit call runs as.
SCHEMA = "lanes_register"
WRITER_ROLE = "lanes_register_writer"

#: Test 7's operator lane, and the two lanes whose checkouts race: `repoW-1`
#: and `repoD-1` are LIVE rows of test 7's register. `OPERATOR` is T227b's
#: `TEST7_OPERATOR` in `tests/pgcluster.py`, written out here: a name imported
#: from there at module level fails this module's collection wherever T227 has
#: not landed, and no landing gate skips a collection error (lane 3, #165
#: 6877365776, point 2). Each case checks that the two agree
#: (`_operator_is_test7s`).
OPERATOR = "repoA-2"
L1, L2 = "repoW-1", "repoD-1"
WS = "Eagle"
AUTHOR = "T270 writer <t270@example.invalid>"
OPERATOR_AUTHOR = "T270 operator <t270-operator@example.invalid>"
NOT_AFTER = "2100-01-01T00:00:00Z"
ARGS_SHA256 = "a" * 64
STORE_UTC = "2026-11-11T10:00:00Z"
#: The file the commit-call entries append to.
APPENDED = "lanes/LANES.md"

#: A commit's `Register-Seq` trailer, `status`'s lag at `primary`, and its
#: divergence and failed-pass lines (lane 1's T117; line R).
REGISTER_SEQ = re.compile(r"^Register-Seq: ([0-9]+)$", re.M)
LAG = re.compile(r"^\s*lag:\s+([0-9]+) seq", re.M)
DIVERGED = re.compile(r"diverged at ([0-9a-f]{40})")
FAILED_PASS = re.compile(r"^\s*renderer:\s+its last failed pass", re.M)

#: Open point 8's ceiling and poll.
CEILING, POLL = 30.0, 0.1

#: The GitHub repository the deploy-key case names, by HTTPS and by SSH.
GITHUB_REPO = "opensoft/t270-mirror"
GITHUB_HTTPS = f"https://github.com/{GITHUB_REPO}.git"
GITHUB_SSH = f"ssh://git@github.com/{GITHUB_REPO}.git"

#: The environment no case inherits.
DROPPED = ("LANES_", "CLAUDE_", "WORKBENCHES_", "TMUX", "XDG_", "PG", "AGENT_PROTOCOL_ROOT",
           "PROJECTS_", "GIT_", "SSH_", "FAKE_PSQL", "RULE6_", "OPENREPOTOOLS_")

#: The subcommands that would rewrite history, which no render may run.
REWRITES = ("rebase", "pull", "cherry-pick", "am", "reset", "merge", "commit")


# ------------------------------------------------------------------ the PATH mask
#: `_masked_path`'s mirrors, by each directory's real path (None where the
#: directory holds no masked name), and the one temporary root they share.
#: Copied from line LX's T253e.
_PATH_MIRRORS: dict = {}
_PATH_MIRROR_ROOT: list = []


def _masked_path() -> str:
    """The caller's PATH with every directory kept in its place, and each one
    that holds a `psql`, a `lanes-index` or a name that starts `pg_` swapped
    for a private mirror of it: a directory of links, one to each of its
    entries by its absolute path, those names left out. An installed
    indexer, a real `psql` or one of the `pg_` client wrappers shipped beside
    it is never what a case runs, but the tools beside them are: on a GitHub
    runner `postgresql-16`'s client puts `psql` in `/usr/bin` with `git` and
    `bash` (and `/bin` is a link to it), so dropping the directory dropped
    `git` and `bash` too (lane 1's census, #165 6807454856). A directory that
    holds none of those names passes through unchanged. Each mirror is made
    once per process, under one `mkdtemp` that an `atexit` handler removes."""
    parts = []
    for part in os.environ.get("PATH", "").split(os.pathsep):
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


# ------------------------------------------------------------------ small helpers
def _script(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _private(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def _said(proc) -> str:
    return (f"exit {proc.returncode}\n--- stdout ---\n{(proc.stdout or '')[-3000:]}"
            f"\n--- stderr ---\n{(proc.stderr or '')[-3000:]}")


def _jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stats(samples: list) -> dict:
    """Section 5.3's statistics: median and p95 by nearest rank, min-max, n.
    Copied from the import module."""
    ordered = sorted(samples)
    rank = lambda p: ordered[max(0, -(-p * len(ordered) // 100) - 1)]  # noqa: E731
    return {"median": rank(50), "p95": rank(95), "min": ordered[0], "max": ordered[-1],
            "n": len(ordered)}


def _open_when_held(fifo: Path, proc: subprocess.Popen, seconds: float = 120):
    """The FIFO's write end, opened once a reader holds a call on it; None
    where `proc` ends, or the time runs out, first. Closing it releases the
    call. Copied from line RB's rollback module."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            return os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            time.sleep(0.05)
    return None


#: What an abort release writes into its FIFO (`_let_go`), beside its mark.
ABORT = b"abort\n"


def _let_go(fifo: Path, fd: int | None = None, abort: bool = False) -> None:
    """A FIFO'S LAST RELEASE, in its owner's outer `finally` (and on the path
    that succeeds), with no moment at which a reader can open it and be left
    on it (lane 3's Codex review of code PR 97 at `6d479418`, SHOULD 1).
    Where the owner still holds its write end `fd`, the FIFO is unlinked
    first and `fd` closed after: a reader that holds it open reads EOF, and
    none can open it once it is unlinked. Where the owner holds none, the
    FIFO is opened once with `O_RDWR | O_NONBLOCK`, which on Linux neither
    blocks nor fails for want of a reader, unlinked while that end is held,
    and the end closed: a reader blocked in its `open()` is let go by that
    open and reads EOF at the close, and one that comes later finds no FIFO
    (ENOENT) and exits. A FIFO already gone is left so. T320's
    `_run_bounded` (line R) runs each git call in a session of its own, so a
    wrapper held on a FIFO is in no group a case signals (lane 2's RV7-30,
    N1). EOF is a held call's release into its git, so a release on the
    path that succeeds is EOF alone. An ABORT RELEASE (`abort`, each outer
    `finally`'s, after its quiescence, `_quiesce`) first writes `ABORT`
    into the FIFO and makes the mark `<fifo>.abort` beside it: a wrapper's
    held call, or a launcher, let go then reads one or the other and runs
    nothing (lane 3's Codex review of code PR 97 at `18529e5a`, SHOULD 1).
    The mark stays beside the FIFO's path, so an abort release is that
    path's last use in its case: each is in its owner's outer `finally`,
    and no case here makes a FIFO at that path again."""
    if fd is None:
        try:
            fd = os.open(str(fifo), os.O_RDWR | os.O_NONBLOCK)
        except FileNotFoundError:
            return
    try:
        if abort:
            try:
                os.write(fd, ABORT)
            except (BrokenPipeError, BlockingIOError):
                pass  # no reader is left to read it, or the FIFO already holds it
            Path(f"{fifo}.abort").touch()
    finally:
        try:
            fifo.unlink(missing_ok=True)
        finally:
            os.close(fd)


def _end_session(proc: subprocess.Popen, grace: float = 10) -> str:
    """A child that leads a session of its own (`popen_render`'s
    `start_new_session`) ended with its process group, and reaped, with no
    wait unbounded: SIGTERM to the group and a `communicate()` of at most
    `grace` s, then SIGKILL to the group and another. The group is signalled
    only while the child is unreaped, so its pid is still the group's id:
    the kernel issues neither the pid nor the group's id again before this
    process reaps the child, so no other process can have them (the one
    `os.killpg` left in the module, on this process's own child alone).
    Where both waits timed out, the child's pipes are closed, in a
    `finally`, and it is waited for once more, at most `grace` s; where that
    times out too it raises (`RuntimeError`), so it never returns with the
    child unreaped (lane 3's Codex review of code PR 97 at `6d479418`,
    SHOULD 4). Returns what the child said (`_said`). `_open_when_held`
    gives None with the child still running once its time runs out, where a
    `communicate()` with no timeout waited for ever (lane 3's Codex review
    of code PR 97 at `4e9821ab`, BLOCKING 2; lane 3's check v97 of it; lane
    2's RV7-30, N3). The hold FIFO is not this call's: its owner lets it go
    in its own outer `finally` (`_let_go`, `_end_hold`)."""
    said = None
    try:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if proc.returncode is None:
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    pass
            try:
                out, err = proc.communicate(timeout=grace)
            except subprocess.TimeoutExpired:
                continue
            said = _said(SimpleNamespace(returncode=proc.returncode, stdout=out, stderr=err))
            break
    finally:
        if said is None:
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
            if proc.returncode is None:
                try:
                    proc.wait(timeout=grace)
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(f"pid {proc.pid} is still unreaped {grace:g} s after its "
                                       f"pipes were closed, SIGTERM and SIGKILL having gone to "
                                       f"its process group") from exc
    return said or (f"exit {proc.returncode}: its output was still open {2 * grace:g} s after "
                    f"SIGTERM and SIGKILL to its process group")


def _end_hold(proc, fifo: Path, fd: int | None, est) -> None:
    """A HOLD SITE'S OUTER `finally`, from the FIFO's making to the end:
    first every process of the estate `est` stopped, killed and seen gone
    (`_quiesce`), `proc` among them as the case's own child, and every
    process carrying the case's identity, so a call it forked in a session
    of its own, logged or not, is ended and never let go into its git; then
    `proc`, the renderer held at its push, where there is one and it is
    still unreaped, reaped with its session ended (`_end_session`, which
    raises where it cannot reap it); then, whatever those raised, the hold
    FIFO let go with an abort and unlinked (`_let_go`), with the write end
    `fd` where the case still holds one (lane 2's RV7-30, S1; lane 3's Codex
    reviews of code PR 97 at `6d479418`, SHOULDs 1 and 4, at `18529e5a`,
    SHOULD 1, and at `46cac748`, BLOCKING)."""
    try:
        try:
            _quiesce(est, roots=[proc] if proc is not None else [])
        finally:
            if proc is not None and proc.returncode is None:
                _end_session(proc)
    finally:
        _let_go(fifo, fd, abort=True)


# ------------------------------------------------------------------ owned processes
#: A PROCESS'S IDENTITY HERE, and the helpers that pin, signal and release a
#: case's processes (`IDENTITY`, `_nonce`, `_stat`, `_carried`, `_pidfds`,
#: `_Pinned`, `_pin_child`, `_table`, `_stopped`, `_owned`, `_keep`,
#: `_send_each`, `_release`, `_wait_all` and `_raise_first`), are
#: `tests/sql_register_cleanup.py`'s, which this module and the rollback
#: module import (round CX-34): its docstring says how a process is owned.
#: So is the one loop of stop, kill, confirm and read again (`_Settled`,
#: `_settle_pinned`; round CX-35), which `_settle` and the wrapper run.
#: The clean-up below, `_quiesce` and the reads it makes, is this module's.


def _in_estate(pid: int, roots: set) -> bool:
    """Whether `pid`'s argv names a path at or under one of `roots`, or its
    cwd is there. The argv is read in memory alone, never kept or shown."""
    def under(path: str) -> bool:
        return any(path == root or path.startswith(root + os.sep) for root in roots)
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        argv = []
    if any(under(os.fsdecode(arg)) for arg in argv if arg):
        return True
    try:
        return under(os.readlink(f"/proc/{pid}/cwd"))
    except OSError:
        return False


def _logged(est, after: int | None) -> list:
    """(pid, start token, what) of each call's launch record
    (`git-wrapper.started`) and, where `after` is a mark, of each renderer
    the wrapper's log names after it."""
    found = [(rec.get("pid"), rec.get("start") or "", "a git call's launch record")
             for rec in _jsonl(est.bin / "git-wrapper.started")]
    if after is not None:
        found += [(call["renderer"], call.get("renderer_start") or "", "a logged renderer")
                  for call in est.render_calls(after)]
    return found


def _unowned(est, after: int | None, table: dict, nonces: set, books: SimpleNamespace) -> None:
    """WHAT A CLEAN-UP FINDS OF THE ESTATE'S BUT CANNOT OWN, each named once
    in `books.errors` and never signalled: a process logged with no start
    token; a live one, not a zombie, whose pid and start token a record
    names but whose environment does not carry the case's identity, as a
    process that took the pid within the same tick would be; and one whose
    argv or cwd is in `est.root` without it (`_strangers`). Each record is
    validated by itself, apart from the table of this user's processes, so
    a live one another user owns, or whose environment cannot be read, is
    named too (`_misrecorded`; lane 3's Codex review of code PR 97 at
    `f776b435`, SHOULD 8). Where the logs cannot be read (`_logged` raises:
    an I/O or JSON error), the first such error is kept in `books.log`, and
    the rest is still found and ended before it is raised (the
    coordinator's #165 6938182757, point 2)."""
    try:
        logged = _logged(est, after)
    except Exception as exc:  # kept, and raised once what is known is ended
        books.log = books.log or exc
        logged = []
    held = {key[0] for key in books.pinned}
    books.errors += [text for text in _misrecorded(logged, nonces, held,
                                                   ", which was never signalled")
                     if text not in books.errors]
    books.errors += [text for text in _strangers(est, table, nonces, held)
                     if text not in books.errors]


def _strangers(est, table: dict, nonces: set, held: set) -> list:
    """What `_unowned` names of a live process, not pinned and not a zombie,
    whose argv or cwd is in `est.root` (`_in_estate`) but whose environment
    does not carry the case's identity."""
    homes = {str(est.root), os.path.realpath(str(est.root))}
    return [f"pid {pid} is in the estate without the case's identity, and was never signalled"
            for pid, row in table.items()
            if pid not in held and row["state"] not in ("Z", "X")
            and _carried(pid) not in nonces and _in_estate(pid, homes)]


def _sweep(est, roots, after: int | None, books: SimpleNamespace) -> int:
    """ONE READ of `_quiesce`: each of `roots`, the case's own children not
    yet reaped, pinned as such (`_pin_child`); then each process whose
    environment carries the estate's nonce, or one a root carries, pinned
    by it (`_owned`); what cannot be owned noted (`_unowned`). Each one new
    is registered in `books.pinned` before any signal, then each is stopped
    (SIGSTOP), each in a `try` of its own. Returns how many are new."""
    table = _table()
    nonces = {getattr(est, "nonce", None)}
    fresh: list = []
    for proc in roots:
        if proc is not None and proc.returncode is None and proc.pid in table:
            nonces.add(_carried(proc.pid))
            if (proc.pid, table[proc.pid]["start"]) not in books.pinned:
                _keep(books.pinned, fresh, _pin_child(proc))
    nonces.discard(None)
    _owned(table, nonces, books.pinned, fresh)
    _unowned(est, after, table, nonces, books)
    books.refused += _send_each(fresh, signal.SIGSTOP, books.raised)
    return len(fresh)


def _settle(est, roots, after: int | None, grace: float, books: SimpleNamespace) -> None:
    """The rounds of `_quiesce`, the shared clean-up's one loop
    (`_settle_pinned`; lane 3's Codex review of code PR 97 at `5a120647`,
    SHOULD 2): read after read (`_sweep`), each made once every process
    pinned is seen stopped, until one finds nothing new; then each still
    there is killed and seen gone, and the estate read again, until a read
    made once every one is seen gone finds nothing new. The deadline,
    `grace` s on, is checked on every read, whatever was stopped, and is an
    error; a stop not seen is one too, and an earlier error never spares
    the read after the kill. Each error is kept in `books.raised`."""
    _settle_pinned(lambda: _sweep(est, roots, after, books), books, time.monotonic() + grace,
                   books.raised)


def _quiesce(est, roots=(), after: int | None = None, grace: float = 10) -> None:
    """THE ESTATE QUIESCENT: every process of `est` stopped, then killed,
    then seen gone, each through its pidfd, every wait bounded (lane 3's
    Codex reviews of code PR 97 at `18529e5a`, BLOCKING and SHOULD 1, and at
    `46cac748`, BLOCKING and SHOULDs 1 and 6). Found, round after round
    until a round finds none not pinned already:
    - `roots`, the case's own children not yet reaped (`_pin_child`);
    - every process whose environment carries the estate's nonce
      (`est.nonce`, `IDENTITY`), or the one a root carries: a write's
      detached fork, a git call before its first record, a member of a
      group whose leader is gone, each found by its identity alone
      (`_owned`).
    Each is registered before any signal, then stopped (SIGSTOP), so none
    forks or runs on while the rest are found, and the next read is made
    only once each one found is seen stopped (`_stopped`); then every one
    still there is killed (SIGKILL), and once each is gone the estate is
    read again, until a read made then finds nothing new, or the deadline,
    `grace` s on and checked on every read, is reported (`_settle`). Each
    signal is sent in a `try` of its own, and every pidfd is let go in its
    own `finally` (`_release`), so whatever is raised, none is left stopped
    or open. A process logged with no start token, one that a record names
    and that is there without the identity, and one in the estate without
    it, are never signalled, and are errors (`_unowned`); so is one still
    there at the end. Where the logs cannot be read, their first error is
    kept and the rest is still found and ended. Then the first error is
    raised as it is, the log's own first, the others named as its cause
    (`_raise_first`). Where the case passed, nothing is left, and nothing
    is signalled."""
    _pidfds()
    books = SimpleNamespace(pinned={}, errors=[], raised=[], log=None, refused=[])
    try:
        _settle(est, roots, after, grace, books)
    finally:
        _release(books.pinned.values(), books.raised)
    _raise_first(([books.log] if books.log is not None else []) + books.raised
                 + ([RuntimeError("; ".join(books.errors))] if books.errors else []))


def _lock_is_free(path: Path) -> bool:
    """A non-blocking `flock` on `path` succeeds (D14; [L4-4])."""
    import fcntl
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    finally:
        os.close(fd)


def _flipped(directory: Path) -> Path:
    """T203's flipped copy, `RENDER_GIT_HALF = True`, with `lanes-edit.sh`
    and `repos.tsv` beside it (the copy rule, CLI4.5 section 6), so a
    `mode=primary` configuration loads and a render runs. Copied from line
    W3a's `flipped_indexer`."""
    copy = flipped_copy(INDEXER, directory, True)
    for name in ("lanes-edit.sh", "repos.tsv"):
        if (REPO / name).exists():
            shutil.copy2(REPO / name, copy.parent / name)
    return copy


# ------------------------------------------------------------------ the wrapper
GIT_WRAPPER = r'''#!/usr/bin/env -S python3 -I
# TEST 5'S `git` WRAPPER (TP:1059-1082; open point 8, TP:8792-8812), first on
# the renderer's PATH, standard library only. Each call is one JSON line of
# git-wrapper.log beside it; git-wrapper.json beside it holds `git` (the real
# git, by its path), `arms` and `redirect`. Before anything else each call
# writes its launch record, its pid and start token, to git-wrapper.started.
import fcntl, json, os, select, signal, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.join(HERE, "git-wrapper.json")
LOG = os.path.join(HERE, "git-wrapper.log")
STATE = os.path.join(HERE, "git-wrapper.state")
STARTED = os.path.join(HERE, "git-wrapper.started")
IDENTITY = "SQL_REGISTER_CASE_ID"
WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
              "--config-env"}
ENV_KEYS = ("GIT_SSH_COMMAND", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "SSH_AUTH_SOCK",
            "LANES_NO_FETCH", "GIT_INDEX_FILE")
NETWORK = ("fetch", "push", "ls-remote", "pull")


def subcommand(args):
    i = 0
    while i < len(args):
        if args[i] in WITH_VALUE:
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i]
    return ""


def where(args):
    """The repository the call runs in: its cwd, moved by each `-C`."""
    found = os.getcwd()
    i = 0
    while i < len(args):
        if args[i] == "-C" and i + 1 < len(args):
            found = os.path.join(found, args[i + 1])
            i += 2
        elif args[i] in WITH_VALUE:
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            break
    return os.path.realpath(found)


def stat(pid):
    """The fields of /proc/<pid>/stat after the command's name, or None."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    return raw[raw.rindex(b")") + 2:].split()


def started(pid):
    """`pid`'s start token: field 22 of its /proc stat, its start in clock
    ticks since boot, which no process that uses the pid again shares; ""
    where it is gone."""
    fields = stat(pid)
    return fields[19].decode() if fields else ""


def is_render(pid):
    """Whether the process above the call is a `lanes-index render
    --checkout`, by its argv, read in memory; only that answer is kept."""
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            argv = [arg.decode("utf-8", "replace") for arg in handle.read().split(b"\0") if arg]
    except OSError:
        return False
    return " render --checkout " in " %s " % " ".join(argv)


def above():
    """(the pid above this call, its start token, whether it is a render),
    read so the token is that process's own: the pid above is read again
    after, and where it has changed the process has ended, its token then
    "gone"."""
    pid = os.getppid()
    start, render = started(pid), is_render(pid)
    if os.getppid() != pid or not start:
        return pid, "gone", False
    return pid, start, render


def launched():
    """THE LAUNCH RECORD, before anything else the call does: its pid and
    start token, one line of git-wrapper.started, which `arm()` never
    resets, so a clean-up owns the call from its launch."""
    me = os.getpid()
    with open(STARTED, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(json.dumps({"pid": me, "start": started(me)}) + "\n")
        handle.flush()


def carried(pid):
    """The nonce `pid`'s environment carries (IDENTITY), read from
    /proc/<pid>/environ in memory alone, never kept or shown; None where it
    carries none or cannot be read."""
    try:
        with open("/proc/%d/environ" % pid, "rb") as handle:
            environ = handle.read()
    except OSError:
        return None
    prefix = ("%s=" % IDENTITY).encode()
    for entry in environ.split(b"\0"):
        if entry.startswith(prefix):
            return entry[len(prefix):].decode("utf-8", "replace") or None
    return None


def alive(fd):
    """Whether the process `fd` names still holds its pid and runs: a signal
    0 through the pidfd succeeds, as it does until the process is reaped,
    and the pidfd is not readable, as it is once the process has ended."""
    try:
        signal.pidfd_send_signal(fd, 0)
    except ProcessLookupError:
        return False
    return not select.select([fd], [], [], 0)[0]


def pin(pid, nonce, pgrp=None):
    """A pidfd on `pid`, kept only where the process it names carries the
    case's nonce (`carried`), is no zombie, is in the group `pgrp` where
    given, and, by a signal 0 through the pidfd after those reads (`alive`),
    held the pid through them; else None, and it is never signalled. Any
    failure of the open but ESRCH is raised; the pidfd is closed first,
    whatever a read raises, unless it is handed over (lane 3's Codex review
    of code PR 97 at `f776b435`, SHOULD 3)."""
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return None
    kept = None
    try:
        fields = stat(pid)
        if (fields and fields[0] not in (b"Z", b"X") and (pgrp is None or int(fields[2]) == pgrp)
                and carried(pid) == nonce and alive(fd)):
            kept = fd
    finally:
        if kept is None:
            os.close(fd)
    return kept


def send(fd, sig):
    try:
        signal.pidfd_send_signal(fd, sig)
    except ProcessLookupError:
        pass  # it has ended; the pidfd names it alone, so no other process is signalled


def stopped(pid, fd):
    """Whether the process `fd` names is seen stopped (state T or t, read
    while its pidfd shows it alive), or has ended."""
    fields = stat(pid)
    if select.select([fd], [], [], 0)[0]:
        return True
    return bool(fields) and fields[0] in (b"T", b"t")


def wait_until(test, seconds):
    """Whether `test()` holds within `seconds`."""
    deadline = time.monotonic() + seconds
    while not test():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


def members(pid, nonce, targets, ended):
    """ONE READ of /proc for the group `pid` leads: each member that carries
    the case's nonce pinned (`pin`), recorded in `targets` before any
    signal, then stopped. It needs no live leader: a group's id is no other
    group's while any member of it lives. A pid in `targets` is passed over
    only while its pidfd shows it there: where it has gone, the process
    that has the pid now is pinned again by its own identity, and the old
    pidfd kept in `ended`, to be closed (SHOULD 1 at `f776b435`). Returns
    how many are new."""
    found = 0
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        old = targets.get(int(name))
        if old is not None and not select.select([old], [], [], 0)[0]:
            continue
        fields = stat(int(name))
        if not fields or int(fields[2]) != pid:
            continue
        fd = pin(int(name), nonce, pgrp=pid)
        if fd is not None:
            if old is not None:
                ended.append(old)
            targets[int(name)] = fd
            send(fd, signal.SIGSTOP)
            found += 1
    return found


def end_all(targets, errors, ended=()):
    """SIGKILL through each pidfd of `targets`, each in a try of its own;
    then each seen gone within one bound, 10 s on, and each pidfd closed,
    with each of `ended` (pidfds of processes already gone), each wait and
    each close in a try of its own, so a close that raises leaves no other
    open (SHOULD 3 at `f776b435`). Each error met here is appended to
    `errors`, after those met before, so none is lost (lane 3's Codex
    review of code PR 97 at `bb190f7b`, SHOULD 2)."""
    for fd in targets.values():
        try:
            send(fd, signal.SIGKILL)
        except OSError as exc:  # kept; the rest are still killed
            errors.append(exc)
    deadline = time.monotonic() + 10
    for pid, fd in targets.items():
        try:
            if not wait_until(lambda: select.select([fd], [], [], 0)[0],
                              max(0, deadline - time.monotonic())):
                errors.append(RuntimeError("pid %d is still there 10 s after its SIGKILL "
                                           "through its pidfd" % pid))
        except OSError as exc:  # kept; the rest are still seen gone and closed
            errors.append(exc)
    for fd in list(targets.values()) + list(ended):
        try:
            os.close(fd)
        except OSError as exc:  # kept; the rest are still closed
            errors.append(exc)


''' + inspect.getsource(_raise_first) + r'''


''' + inspect.getsource(_Settled) + r'''

def kill_above(pid):
    """SIGKILL to the process above, and to every other member of the group
    it leads, each through a pidfd pinned by the case's identity (`pin`),
    never by a number or a group's id (lane 3's Codex review of code PR 97
    at `46cac748`, BLOCKING and SHOULDs 1 and 6; the coordinator's points 1
    and 3, #165 6938182757): the process above is pinned and sent SIGSTOP;
    then /proc is read for the members of its group, each pinned, recorded
    and stopped; after a read that finds any new, the next read is made
    only once every target, the process above among them, is seen stopped,
    until a read finds none new; the leader need not live for its members
    to be found. The first read follows the leader's SIGSTOP with no wait,
    and where it finds no member the leader is killed with its stop
    unchecked: no error is kept for a stop of its that is never seen, and
    the read after the kill still runs (lane 2's pre-review RV7-35, N1).
    Whatever is raised on the way, every target is then
    killed, seen gone and its pidfd closed (`end_all`), and the first error
    is raised, each later one named in its cause (`_raise_first`, whose
    source this script carries; lane 3's Codex review of code PR 97 at
    `bb190f7b`, SHOULD 2). A process without the case's identity is never
    signalled.
    Where the process above is gone before it is pinned, its group's
    members are still found by the nonce and the group's id; a stop not
    seen, where one is awaited after a read that found any new, is an
    error; and the discovery and the end are the shared
    clean-up's one loop (`_Settled`, whose source this script carries; lane
    3's Codex review of code PR 97 at `5a120647`, SHOULD 2): read after
    read (`members`), then each target killed and seen gone, then /proc
    read again, until a read made once every target is seen gone finds
    none new, or the one deadline, 10 s on and checked on every read,
    whatever was stopped, is reported. An earlier error never spares the
    read after the kill, so a member forked by one whose stop was never
    seen is still found and ended; each error is kept, and the first is
    raised with every later one as its cause."""
    nonce = os.environ.get(IDENTITY)
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal") or not nonce:
        sys.stderr.write("the test's git wrapper kills only through a pidfd pinned by the case's "
                         "identity (%s; Python 3.9 or later, Linux 5.3 or later), and it has "
                         "none\n" % IDENTITY)
        sys.exit(70)
    targets, ended, errors = {}, [], []
    lead = pin(pid, nonce)
    there = stat(pid) if lead is None else None
    if lead is not None:
        targets[pid] = lead
    elif there and there[0] not in (b"Z", b"X"):
        sys.stderr.write("the process above is not the case's: nothing is signalled\n")
        return
    until = time.monotonic() + 10

    def live():
        return [p for p, fd in targets.items() if not select.select([fd], [], [], 0)[0]]

    def stop(by):
        if wait_until(lambda: all(stopped(p, fd) for p, fd in targets.items()),
                      max(0, by - time.monotonic())):
            return None
        return "pids %s were never seen stopped" % sorted(
            p for p, fd in targets.items() if not stopped(p, fd))

    def kill(left):
        raised = []
        for p in left:
            try:
                send(targets[p], signal.SIGKILL)
            except OSError as exc:  # kept; the rest are still killed
                raised.append(exc)
        wait_until(lambda: not live(), max(0, until - time.monotonic()) + 1)
        return raised

    try:
        if lead is not None:
            send(lead, signal.SIGSTOP)
    except OSError as exc:  # kept; its group is still read, and every target ended
        errors.append(exc)
    try:
        _Settled(lambda: members(pid, nonce, targets, ended), stop, kill, live, until,
                 errors).run()
    except BaseException as exc:  # kept; every target is still ended, then the first is raised
        errors.append(exc)
    end_all(targets, errors, ended)
    _raise_first(errors)


def log(record):
    with open(LOG, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(json.dumps(record) + "\n")
        handle.flush()


def take(index, times):
    """Whether arm `index` takes this call: a count per arm, under a lock;
    `times` below 0 takes every call."""
    with open(STATE, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        text = handle.read()
        counts = json.loads(text) if text.strip() else {}
        used = counts.get(str(index), 0)
        if times >= 0 and used >= times:
            return False
        counts[str(index)] = used + 1
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(counts))
        return True


def applies(arm, sub, args, here, render):
    if arm.get("sub") != sub:
        return False
    if arm.get("where") and os.path.realpath(arm["where"]) != here:
        return False
    if arm.get("has") and arm["has"] not in args:
        return False
    if arm.get("render_only") and not render:
        return False
    return True


def main():
    launched()
    args = sys.argv[1:]
    with open(CONTROL, encoding="utf-8") as handle:
        control = json.load(handle)
    sub = subcommand(args)
    here = where(args)
    parent, parent_start, render = above()
    record = {"sub": sub, "argv": args, "pid": os.getpid(), "renderer": parent,
              "renderer_start": parent_start, "render": render, "where": here,
              "env": {key: os.environ.get(key) for key in ENV_KEYS}, "t0": time.time()}
    for index, arm in enumerate(control.get("arms", [])):
        if (not applies(arm, sub, args, here, record["render"])
                or not take(index, arm.get("times", -1))):
            continue
        do = arm["do"]
        if do == "hold":
            log(dict(record, outcome="held"))
            with open(arm["fifo"], "rb") as fifo:
                said = fifo.read()
            if said or os.path.exists(arm["fifo"] + ".abort"):
                log(dict(record, outcome="aborted", rc=75))
                return 75  # an abort release: this call runs no git
        elif do == "stall":
            log(dict(record, outcome="stalled"))
            time.sleep(float(arm.get("seconds", 5)))
        elif do == "fail":
            log(dict(record, outcome="failed", rc=1))
            sys.stderr.write("fatal: the test's git wrapper fails this %s\n" % sub)
            return 1
        elif do == "reject":
            log(dict(record, outcome="rejected", rc=1))
            refspec = next((a for a in reversed(args) if ":" in a and not a.startswith("-")),
                           "HEAD")
            dest = args[args.index(refspec) - 1] if refspec in args else "origin"
            if "--porcelain" in args:
                sys.stdout.write("To %s\n!\t%s\t[rejected] (non-fast-forward)\nDone\n"
                                 % (dest, refspec))
            sys.stderr.write(" ! [rejected]        %s (non-fast-forward)\nerror: failed to "
                             "push some refs to '%s'\nhint: Updates were rejected because "
                             "the remote contains work that you do not have locally.\n"
                             % (refspec, dest))
            return 1
        elif do == "kill":
            index_file = os.environ.get("GIT_INDEX_FILE")
            if arm.get("index_lock") and index_file:
                open(index_file + ".lock", "a").close()
            log(dict(record, outcome="killed"))
            # The renderer's own group where it leads one (a detached fork, or
            # a case's render in a session of its own); else the renderer
            # alone, each through a pidfd pinned by the case's identity
            # (`kill_above`). Each git call runs in
            # a group of its own (`_run_bounded`), so this call, which stands
            # for git, then ends itself.
            kill_above(parent)
            signal.raise_signal(signal.SIGKILL)
            return 137
    command = [control["git"]]
    redirect = control.get("redirect") or {}
    if sub in NETWORK:
        for url, path in sorted(redirect.items()):
            command += ["-c", "url.%s.insteadOf=%s" % (path, url)]
        args = [redirect.get(arg, arg) for arg in args]
    ran = time.time()
    rc = subprocess.run(command + args).returncode
    log(dict(record, outcome="ran", rc=rc, ran=ran, t1=time.time()))
    return rc


if __name__ == "__main__":
    sys.exit(main())
'''

#: Test 4's start barrier (TP:886-888): the launcher blocks on the FIFO it is
#: given until the test opens and closes it, then becomes the command; let go
#: by an abort release (`_let_go`'s `abort`), it ends with 75 and runs none.
LAUNCH = r'''#!/usr/bin/env -S python3 -I
import os, sys
with open(sys.argv[1], "rb") as fifo:
    said = fifo.read()
if said or os.path.exists(sys.argv[1] + ".abort"):
    sys.exit(75)  # an abort release: the command never runs
os.execv(sys.argv[2], sys.argv[2:])
'''


def _rows(db, sql: str) -> list:
    """`sql`'s rows as JSON objects, read in the register's schema, by
    `jsonb_agg`, whose text is one line. Copied from the import module."""
    out = db.psql(f"SET search_path TO {SCHEMA};\n"
                  f"SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM ({sql}) t;\n").stdout
    return json.loads(out.strip().splitlines()[-1])


# ------------------------------------------------------------------ the estate
class RenderEstate:
    """TEST 5'S ESTATE: see the module's docstring. `stage` is `primary` (the
    default), `imported` (seq 0, the switch at `files`) or `empty` (no
    journal, on `pg`). At `primary`, `marker` is `pushed`, or `recorded` for
    a marker commit `record_marker` names that is not on origin's `main`."""

    def __init__(self, root: Path, db, cluster, *, stage: str = "primary",
                 marker: str = "pushed"):
        assert stage in ("primary", "imported", "empty"), stage
        source = cluster.imported_register
        if source is None:
            pytest.fail(f"no imported register on the session cluster: "
                        f"{cluster.imported_problem}", pytrace=False)
        self.root, self.db, self.stage = root, db, stage
        root.mkdir(parents=True, exist_ok=True)
        masked = _masked_path()
        self.real_git = shutil.which("git", path=masked)
        assert self.real_git, "no git on PATH"
        self.bin, self.fakebin = root / "bin", root / "fakebin"
        _script(self.bin / "git", GIT_WRAPPER)
        _script(self.bin / "psql", PSQL_SHIM)
        _script(self.bin / "launch", LAUNCH)
        _script(self.fakebin / "tmux", "#!/bin/sh\nexit 1\n")
        self.copy = _flipped(root / "flip")
        env = {k: v for k, v in os.environ.items() if not k.startswith(DROPPED)}
        #: The case's nonce, which every process it launches carries (`IDENTITY`).
        self.nonce = _nonce()
        env[IDENTITY] = self.nonce
        env.update(TMPDIR=str(root / "tmp"), LANES_WORKSTATION=WS, LANES_HOST="eagle",
                   LANES_OS="linux", LANES_CONTAINER="none", LANES_IN_CONTAINER="0",
                   LANES_NO_GITHUB="1", LANES_EDIT=str(self.copy.parent / "lanes-edit.sh"),
                   GIT_AUTHOR_NAME="T270 estate", GIT_AUTHOR_EMAIL="t270@example.invalid",
                   GIT_COMMITTER_NAME="T270 estate", GIT_COMMITTER_EMAIL="t270@example.invalid",
                   PATH=os.pathsep.join([str(self.bin), str(self.fakebin), masked]))
        (root / "tmp").mkdir(exist_ok=True)
        self.env = env
        #: The test's own git calls: the real git, no wrapper on PATH.
        self.plain_env = dict(env, PATH=os.pathsep.join([str(self.fakebin), masked]))
        self.arm()
        self.c = source.c
        self.origin = root / "origin.git"
        self.git(None, "clone", "-q", "--bare", str(source.origin), str(self.origin))
        assert self.origin_tip() == self.c, "the imported register's origin is not at C"
        self.label = self.switch()["database_label"]
        self.conf_dir = root / "conf"
        self.passfile = _private(self.conf_dir / "empty.pgpass", "")
        self.index_conf = self.config("index", "index")
        self.primary_conf = self.config("primary", "primary")
        self.checkouts: dict = {}
        head = self.head()
        if stage == "empty":
            assert head == -1, f"`pg`'s journal is not empty: head {head}"
        else:
            assert head == 0 and self.switch()["mode"] == "files", (
                f"`pg_imported` is not test 7's register at seq 0 at files: head {head}, "
                f"switch {self.switch()}")
        self.n = head
        self.marker = None
        if stage == "primary":
            self._to_primary(marker)

    # ------------------------------------------------------------ git
    def git(self, cwd, *args: str, env: dict | None = None, data: bytes | None = None) -> str:
        proc = subprocess.run([self.real_git, *args], cwd=str(cwd) if cwd else None,
                              env=env or self.plain_env, input=data, capture_output=True,
                              timeout=300, check=False)
        assert proc.returncode == 0, (f"git {' '.join(args[:4])}: "
                                      f"{proc.stderr.decode('utf-8', 'replace')[-800:]}")
        return proc.stdout.decode("utf-8", "replace")

    def origin_git(self, *args: str, env: dict | None = None, data: bytes | None = None,
                   origin: Path | None = None) -> str:
        """git in a bare origin itself, so no clone's refs move."""
        return self.git(None, f"--git-dir={origin or self.origin}", *args, env=env, data=data)

    def origin_tip(self, origin: Path | None = None) -> str:
        return self.origin_git("rev-parse", "refs/heads/main", origin=origin).strip()

    def commit_in_origin(self, parent: str, files: dict, message: str,
                         origin: Path | None = None) -> str:
        """A commit on `parent` with `files` ({path: bytes}) changed, made in
        the bare origin through an index of its own; no ref moves."""
        index = self.root / f"build-{uuid.uuid4().hex[:8]}.index"
        env = dict(self.plain_env, GIT_INDEX_FILE=str(index))
        self.origin_git("read-tree", parent, env=env, origin=origin)
        for path, data in files.items():
            blob = self.origin_git("hash-object", "-w", "--stdin", data=data, origin=origin).strip()
            self.origin_git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}",
                            env=env, origin=origin)
        tree = self.origin_git("write-tree", env=env, origin=origin).strip()
        return self.origin_git("commit-tree", tree, "-p", parent, data=message.encode("utf-8"),
                               origin=origin).strip()

    def push_by_hand(self, commit: str, origin: Path | None = None) -> None:
        """Origin's `main` moved to `commit`, a fast-forward, as a push makes it."""
        old = self.origin_tip(origin)
        self.origin_git("merge-base", "--is-ancestor", old, commit, origin=origin)
        self.origin_git("update-ref", "refs/heads/main", commit, old, origin=origin)

    def second_origin(self, name: str) -> Path:
        """A bare copy of origin as it stands."""
        path = self.root / f"{name}.git"
        self.git(None, "clone", "-q", "--bare", str(self.origin), str(path))
        return path

    def commits_after(self, old: str, origin: Path | None = None) -> list:
        """[(sha, its Register-Seq values, its raw message)] on origin's
        `main`'s first-parent line after `old`, oldest first."""
        out = self.origin_git("rev-list", "--reverse", "--first-parent",
                              f"{old}..refs/heads/main", origin=origin)
        found = []
        for sha in out.split():
            raw = self.origin_git("cat-file", "commit", sha, origin=origin)
            message = raw.split("\n\n", 1)[1] if "\n\n" in raw else ""
            found.append((sha, [int(s) for s in REGISTER_SEQ.findall(message)], message))
        return found

    def identity(self, sha: str, origin: Path | None = None) -> dict:
        out = self.origin_git("log", "-1", "--format=%an <%ae>%x00%at%x00%cn <%ce>%x00%ct", sha,
                              origin=origin).rstrip("\n").split("\0")
        return {"author": out[0], "author_epoch": int(out[1]), "committer": out[2],
                "committer_epoch": int(out[3])}

    def form_c(self, sha: str, origin: Path | None = None) -> str:
        """Form C on one commit, with the walk's pins (Y:2843-2847)."""
        out = self.origin_git("-c", "trailer.separators=:", "-c", "core.commentChar=#",
                              "log", "-n", "1",
                              "--format=%(trailers:key=Register-Seq,valueonly)", sha,
                              origin=origin)
        return next((line.strip() for line in out.split("\n") if line.strip()), "")

    # ------------------------------------------------------------ the database
    def rows(self, sql: str) -> list:
        return _rows(self.db, sql)

    def sql(self, script: str, role: str | None = None) -> subprocess.CompletedProcess:
        head = f"SET search_path TO {SCHEMA};\n" + (f"SET ROLE {role};\n" if role else "")
        return self.db.psql(head + script, check=False)

    def head(self) -> int:
        return self.rows("SELECT seq FROM register_head")[0]["seq"]

    def window(self) -> int:
        return self.rows("SELECT version FROM schema_version")[0]["version"]

    def switch(self) -> dict:
        return self.rows("SELECT * FROM register_switch")[0]

    def mirror(self) -> dict:
        return self.rows("SELECT * FROM mirror_state")[0]

    def journal(self, after: int = -1) -> list:
        return self.rows(f"SELECT seq, kind, message, author, "
                         f"extract(epoch FROM utc)::bigint AS epoch FROM journal "
                         f"WHERE seq > {after} ORDER BY seq")

    def render_sql(self, path: str) -> bytes:
        """SQL's own render of `path` at the head (lane 1's T107)."""
        quoted = path.replace("'", "''")
        rows = self.rows(f"SELECT encode(render_file('{quoted}'), 'hex') AS hex")
        return bytes.fromhex(rows[0]["hex"])

    def commit_entries(self, bodies: list) -> list:
        """THE COMMIT CALL, as a writer sends it (section 1.3's step 3): one
        SERIALIZABLE transaction around `commit_write` per entry, as
        REGISTER-WRITER, in one `psql`. Returns the entries' seqs."""
        head, window = self.head(), self.window()
        generation = self.switch()["generation"]
        script = []
        for n, body in enumerate(bodies):
            literal = json.dumps(body, ensure_ascii=True).replace("'", "''")
            script += ["BEGIN ISOLATION LEVEL SERIALIZABLE;",
                       f"SELECT commit_write({head + n}, '{uuid.uuid4()}'::uuid, {window}, "
                       f"'{generation}'::uuid, '{literal}'::jsonb);", "COMMIT;"]
        proc = self.sql("\n".join(script) + "\n", WRITER_ROLE)
        assert proc.returncode == 0, f"commit_write refused an entry: {proc.stderr[-1500:]}"
        seqs = [int(word) for word in proc.stdout.split()]
        assert seqs == list(range(head + 1, head + 1 + len(bodies))), (
            f"the commit calls answered {seqs}, not {head + 1} to {head + len(bodies)}")
        return seqs

    def write_sql(self, texts: list, *, lane: str = L1, messages: list | None = None) -> list:
        """One write entry per text, each appending it to `APPENDED`, through
        the commit call alone (no fork). Returns their seqs."""
        data = self.render_sql(APPENDED)
        assert data.endswith(b"\n"), f"SQL's {APPENDED} does not end with a newline"
        bodies = []
        for n, text in enumerate(texts):
            data += text.encode("utf-8") + b"\n"
            bodies.append({
                "journal": {"kind": "write", "verb": "log", "lane": lane, "workstation": WS,
                            "author": AUTHOR, "args_sha256": ARGS_SHA256,
                            "message": messages[n] if messages else f"t270: {text}"},
                "not_after": NOT_AFTER,
                "edits": [{"ord": 1, "op": "append", "path": APPENDED, "new_text": text}],
                "files": [{"path": APPENDED, "present": True, "sha256": _sha256(data),
                           "final_newline": True}]})
        return self.commit_entries(bodies)

    def _to_primary(self, marker: str) -> None:
        """AT-LR006'S ROUTE (TP:4610-4615): the cutover entry at seq 1, the
        marker commit pushed by hand (or only recorded), `record_marker`."""
        tree = self.origin_git("rev-parse", f"{self.c}:lanes").strip()
        lines = ("store=primary", f"database={self.label}", f"import={self.c}",
                 f"lanes-tree={tree}", f"utc={STORE_UTC}")
        data = ("\n".join(lines) + "\n").encode("utf-8")
        message = "t270: the cutover, by AT-LR006's route"
        edits = [{"ord": 1, "op": "create", "path": "lanes/STORE"}]
        edits += [{"ord": n, "op": "append", "path": "lanes/STORE", "new_text": line}
                  for n, line in enumerate(lines, start=2)]
        (cut,) = self.commit_entries([{
            "journal": {"kind": "cutover", "verb": "cutover", "lane": OPERATOR,
                        "workstation": WS, "author": OPERATOR_AUTHOR, "message": message},
            "not_after": NOT_AFTER, "edits": edits,
            "files": [{"path": "lanes/STORE", "present": True, "sha256": _sha256(data),
                       "final_newline": True}]}])
        assert cut == 1, f"the cutover entry took seq {cut}, not 1"
        assert self.render_sql("lanes/STORE") == data, "SQL renders lanes/STORE otherwise"
        self.marker = self.commit_in_origin(self.c, {"lanes/STORE": data},
                                            f"{message}\n\nRegister-Seq: {cut}\n")
        if marker == "pushed":
            self.push_by_hand(self.marker)
        proc = self.sql(f"SELECT record_marker({self.window()}, {cut}, '{self.marker}', "
                        f"'{WS}');", WRITER_ROLE)
        assert proc.returncode == 0 and proc.stdout.strip() == "present", (
            f"record_marker answered {proc.stdout.strip()!r}: {proc.stderr[-800:]}")
        switch = self.switch()
        assert (switch["mode"], switch["marker_state"]) == ("primary", "present"), switch
        self.n = cut

    # ------------------------------------------------------------ configuration
    def config(self, name: str, mode: str, extra=()) -> Path:
        """A 0600 `lanes-index.conf` outside every work tree: `mode`, the two
        URLs on the cluster's socket as its own user, an empty password file,
        the switch's label and the schema, and `extra` lines."""
        lines = [f"mode={mode}", f"register_url={self.db.url()}",
                 f"register_passfile={self.passfile}", f"reader_url={self.db.url()}",
                 f"reader_passfile={self.passfile}", f"register_label={self.label}",
                 f"register_schema={SCHEMA}", *extra]
        return _private(self.conf_dir / name / "lanes-index.conf", "\n".join(lines) + "\n")

    # ------------------------------------------------------------ lane checkouts
    def checkout(self, name: str, lane: str = L1, *, origin: Path | None = None,
                 repository: str | None = None, own: bool = False) -> SimpleNamespace:
        """A lane's register checkout, a clone of `origin`, in test 7's
        `Workspace` form: its own `$HOME`, W a view of the clone that
        `workspace.yaml` names (with `repository:` `repository`, origin's
        path by default), and `LANES_REPO` at the clone. With `own`, for a
        lane whose writes fork the renderer, also the lane's own register
        checkout `<c>` (`own_checkout`), as `.own`."""
        root = self.root / name
        home = root / "home"
        agents = home / ".agents"
        agents.mkdir(parents=True)
        clone = home / "projects" / "wip"
        self.git(None, "clone", "-q", str(origin or self.origin), str(clone))
        view = root / "ro" / "wip"
        view.mkdir(parents=True)
        (view / ".git").write_text(f"gitdir: {os.path.realpath(clone / '.git')}\n",
                                   encoding="utf-8")
        (view / "lanes").symlink_to(clone / "lanes")
        (agents / "workspace.yaml").write_text(
            f"repository: {repository or (origin or self.origin)}\npath: {view}\n",
            encoding="utf-8")
        for d in ("state", "config", "tmp"):
            (root / d).mkdir()
        env = dict(self.env, HOME=str(home), AGENT_PROTOCOL_ROOT=str(agents),
                   XDG_STATE_HOME=str(root / "state"), XDG_CONFIG_HOME=str(root / "config"),
                   TMPDIR=str(root / "tmp"), CLAUDE_CONFIG_DIR=str(home / ".claude"),
                   LANES_REPO=str(clone), LANES_LANE=lane)
        lane_checkout = SimpleNamespace(name=name, lane=lane, root=root, home=home, clone=clone,
                                        git_dir=clone / ".git", env=env, w=view, own=None)
        if own:
            lane_checkout.own = self.own_checkout(lane_checkout)
        self.checkouts[name] = lane_checkout
        return lane_checkout

    def own_checkout(self, lc) -> SimpleNamespace:
        """THE LANE'S OWN REGISTER CHECKOUT ON PRIMARY, `<c>`, `<W>-lanes/<lane>/`
        (T270e), made by `lanes-edit.sh lane-checkout <lane> --create` through the
        flipped copy, as line G's T254s makes it for each primary lane. The estate makes
        `<c>` itself, because `lane-start` makes it only under `LANES_ROUTE_WRITES=1`
        with neither `LANES_REPO` nor `LANES_FILE` set (lane 3, #165 6841265575;
        `dfc4ce4c:lane-start:1209-1210`).

        WHY: on primary, T415's `pw_checkout` takes each write's checkout from
        `lane_checkout_path`, `<W>-lanes/<lane>`, and `LANES_REPO` never enters it
        (lane 4, #165 6840794493: `a38af255:lanes-edit.sh:6273`, `:20738`, `:1673-1674`).
        Where it is not there, the write refuses 2 and nothing is sent. The write's fork
        then renders there, `render --checkout "$PW_C"` (`pw_render_fork`). So the
        render's calls, lock and marks are `<c>`'s. The clone is a fetch, so
        `LANES_NO_FETCH` is left out. Returns `<c>`'s `clone` and `git_dir`."""
        proc = subprocess.run(["bash", str(self.copy.parent / "lanes-edit.sh"), "lane-checkout",
                               lc.lane, "--create"], cwd=str(lc.clone),
                              env=self.lane_env(lc, None, {"LANES_NO_FETCH": None}),
                              capture_output=True, text=True, timeout=300,
                              stdin=subprocess.DEVNULL, check=False)
        assert proc.returncode == 0, f"lane-checkout {lc.lane} --create:\n{_said(proc)}"
        c = Path(proc.stdout.strip().splitlines()[-1])
        expected = Path(os.path.realpath(lc.w) + "-lanes") / lc.lane
        assert c == expected and c.is_dir(), (
            f"lane-checkout {lc.lane} --create made {c}, not {expected}:\n{_said(proc)}")
        git_dir = Path(self.git(c, "rev-parse", "--absolute-git-dir").strip())
        return SimpleNamespace(clone=c, git_dir=git_dir)

    def snapshot(self, lc) -> dict:
        """The checkout's HEAD, index digest and `status --porcelain`, the
        index read first and `status` run with no optional lock, so this
        read never rewrites the index it digests."""
        index = _sha256((lc.git_dir / "index").read_bytes())
        return {"head": self.git(lc.clone, "rev-parse", "HEAD").strip(), "index": index,
                "status": self.git(lc.clone, "--no-optional-locks", "status", "--porcelain")}

    # ------------------------------------------------------------ the wrapper and the shim
    def arm(self, arms=(), redirect: dict | None = None, shim_arms=()) -> None:
        """The wrapper's arms and the shim's, each log and count started
        afresh."""
        for name in ("git-wrapper.log", "git-wrapper.state", PSQL_SHIM_LOG, "psql-shim.ends"):
            (self.bin / name).write_text("", encoding="utf-8")
        (self.bin / "psql-shim.state").write_text("{}", encoding="utf-8")
        control = {"git": self.real_git, "arms": list(arms), "redirect": redirect or {}}
        (self.bin / "git-wrapper.json").write_text(json.dumps(control), encoding="utf-8")
        (self.bin / PSQL_SHIM_CONTROL).write_text(
            json.dumps({"psql": self.db.psql_bin, "arms": list(shim_arms)}), encoding="utf-8")

    def calls(self, sub: str | None = None, lc=None) -> list:
        """The wrapper's log, in order: each call that ran, or that an arm
        took, once (its `ran` line, else its arm's line)."""
        entries = _jsonl(self.bin / "git-wrapper.log")
        ran = {e["pid"] for e in entries if e.get("outcome") == "ran"}
        kept = [e for e in entries if e.get("outcome") == "ran" or e["pid"] not in ran]
        if sub is not None:
            kept = [e for e in kept if e["sub"] == sub]
        if lc is not None:
            kept = [e for e in kept if e["where"] == os.path.realpath(lc.clone)]
        return kept

    # ------------------------------------------------------------ the commands
    def lane_env(self, lc, conf: Path | None, env: dict | None) -> dict:
        child = dict(lc.env, LANES_INDEX_CONFIG=str(conf or self.primary_conf))
        for key, value in (env or {}).items():
            if value is None:
                child.pop(key, None)
            else:
                child[key] = value
        return child

    def render_argv(self, lc) -> list:
        return [sys.executable, str(self.copy), "render", "--checkout", str(lc.clone)]

    def render(self, lc, *, conf: Path | None = None, env: dict | None = None,
               timeout: float = 300) -> subprocess.CompletedProcess:
        """`lanes-index render --checkout <c>`, as a fork starts it: in a
        session of its own, through the flipped copy, with the `mode=primary`
        configuration. Waited for to its exit."""
        return subprocess.run(self.render_argv(lc), cwd=str(lc.clone),
                              env=self.lane_env(lc, conf, env), capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL, start_new_session=True,
                              check=False)

    def popen_render(self, lc, *, conf: Path | None = None, env: dict | None = None,
                     argv: list | None = None) -> subprocess.Popen:
        return subprocess.Popen(argv or self.render_argv(lc), cwd=str(lc.clone),
                                env=self.lane_env(lc, conf, env), text=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)

    def index(self, lc, *args: str, conf: Path | None = None, env: dict | None = None,
              timeout: float = 300) -> subprocess.CompletedProcess:
        """Another `lanes-index` command in the lane's checkout."""
        return subprocess.run([sys.executable, str(self.copy), *args], cwd=str(lc.clone),
                              env=self.lane_env(lc, conf or self.index_conf, env),
                              capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL, check=False)

    def status(self, lc) -> subprocess.CompletedProcess:
        """`lanes-index status` in the lane's checkout: its lag is `n` less
        the `m` origin's `main` carried as last fetched there."""
        return self.index(lc, "status")

    def lag(self, lc) -> int | None:
        found = LAG.search(self.status(lc).stdout)
        return int(found.group(1)) if found else None

    def race(self, checkouts: list, *, conf: Path | None = None) -> list:
        """Test 4's barrier (TP:886-888, TP:1083): one renderer per checkout,
        each launched blocking on a FIFO of its own, released together once
        all are waiting. Returns each one's (returncode, stdout, stderr).
        By then each launcher holds its FIFO open, so every FIFO is unlinked
        before the release and none can be opened after it. The `finally`
        owns every child and FIFO: first the estate is made quiescent
        (`_quiesce`, each launcher not yet reaped among its roots, so its
        render and every call it forked are stopped, killed and seen gone
        through their pidfds); then each child not yet reaped has its
        session ended and is reaped (`_end_session`), each step in a `try` of
        its own that keeps its error; only then is each FIFO let go with an
        abort and unlinked (`_let_go`) and each write end still open closed,
        so no launcher is released into a render the case has given up on,
        or left on an unlinked FIFO; then the first error kept is raised, or,
        where a child is still unreaped, that is (lane 3's Codex reviews of
        code PR 97 at `4e9821ab`, SHOULD 4, at `6d479418`, SHOULDs 1 and 4,
        and at `18529e5a`, BLOCKING and SHOULD 1; lane 2's RV7-30, N4). A
        launcher that never waited is ended and drained into that failure."""
        procs, fifos, fds = [], [], []
        try:
            for lc in checkouts:
                fifo = self.root / f"barrier-{lc.name}.fifo"
                os.mkfifo(str(fifo), 0o600)
                fifos.append(fifo)
                procs.append(self.popen_render(lc, conf=conf, argv=[
                    sys.executable, "-I", str(self.bin / "launch"), str(fifo),
                    *self.render_argv(lc)]))
            for fifo, proc in zip(fifos, procs):
                fd = _open_when_held(fifo, proc)
                assert fd is not None, f"a launcher never waited on {fifo}:\n{_end_session(proc)}"
                fds.append(fd)
            for fifo in fifos:
                fifo.unlink()
            while fds:
                os.close(fds.pop(0))
            ended = []
            for proc in procs:
                out, err = proc.communicate(timeout=300)
                ended.append(SimpleNamespace(returncode=proc.returncode, stdout=out, stderr=err))
            return ended
        finally:
            errors = []
            try:
                _quiesce(self, roots=[proc for proc in procs if proc.returncode is None])
            except Exception as exc:  # its error is kept; every child is still tried
                errors.append(exc)
            for proc in procs:
                if proc.returncode is None:
                    try:
                        _end_session(proc)
                    except Exception as exc:  # every child is tried; the first error is raised
                        errors.append(exc)
            for fifo in fifos:
                try:
                    _let_go(fifo, abort=True)
                except OSError as exc:
                    errors.append(exc)
            while fds:
                os.close(fds.pop(0))
            unreaped = [proc.pid for proc in procs if proc.returncode is None]
            if errors:
                raise errors[0]
            if unreaped:
                raise RuntimeError(f"launcher pids {unreaped} are still unreaped")

    # ------------------------------------------------------------ writes that fork
    def rearm(self, arms=()) -> None:
        """The wrapper's arms changed, its log and counts kept."""
        control = json.loads((self.bin / "git-wrapper.json").read_text(encoding="utf-8"))
        control["arms"] = list(arms)
        (self.bin / "git-wrapper.json").write_text(json.dumps(control), encoding="utf-8")

    def edit(self, lc, *args: str, env: dict | None = None,
             timeout: float = 300) -> subprocess.CompletedProcess:
        """`lanes-edit.sh <args>` in the lane's checkout, as its lane, through
        the flipped copy's `lanes-edit.sh`, with the `mode=primary`
        configuration: a write on `primary`, which forks the renderer (lane
        4's T415 and T416)."""
        return subprocess.run(["bash", str(self.copy.parent / "lanes-edit.sh"), *args],
                              cwd=str(lc.clone), env=self.lane_env(lc, None, env),
                              capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL, check=False)

    def write(self, lc, text: str, env: dict | None = None,
              timeout: float = 300) -> subprocess.CompletedProcess:
        """One `log NOTED lane:<L> <text>` from the lane's checkout."""
        return self.edit(lc, "log", "NOTED", f"lane:{lc.lane}", text, env=env, timeout=timeout)

    def entries(self) -> int:
        """The wrapper log's length, the mark a wait starts after."""
        return len(_jsonl(self.bin / "git-wrapper.log"))

    def render_calls(self, after: int = 0) -> list:
        """The calls a `lanes-index render --checkout` made, logged after the
        mark `after`, each once."""
        entries = _jsonl(self.bin / "git-wrapper.log")[after:]
        ran = {e["pid"] for e in entries if e.get("outcome") == "ran"}
        return [e for e in entries if e.get("render")
                and (e.get("outcome") == "ran" or e["pid"] not in ran)]

    def wait_lag_0(self, lc, what: str) -> None:
        """OPEN POINT 8'S FIRST WAIT: `status` every 100 ms until its lag is
        0, under 30 s, each poll after the harness's fetch of the W `status`
        reads (T270e; lane 3's ruling (a), #165 6833830078):
        `git -C <W> fetch -q origin main`, with plain git, never through the
        wrapper. `status` reads `m` on W's `origin/main` as last fetched and
        never fetches, no write on primary fetches (D12), and the
        render pushes from the lane's `<c>`. The fetch is the harness's own
        act, not a write's, as the drill's `wait_lag_0` has it (DR's
        T276f)."""
        deadline = time.monotonic() + CEILING
        while True:
            self.git(lc.w, "fetch", "-q", "origin", "main")
            if self.lag(lc) == 0:
                return
            if time.monotonic() > deadline:
                shown = self.status(lc)
                pytest.fail(f"{what}: the lag, each read after a fetch of W, is not 0 within "
                            f"{CEILING:g} s:\n{shown.stdout}"
                            f"{shown.stderr[-800:]}", pytrace=False)
            time.sleep(POLL)

    def wait_renders_exit(self, after: int, what: str) -> list:
        """OPEN POINT 8'S SECOND WAIT: under 30 s, a render's call logged
        after the mark `after` (every pass begins with a fetch), then the
        exit of every renderer logged after it, a re-fork's included, each
        sought as the pair of its pid and the start token logged, read from
        `/proc` (`_exited`): a pid whose token no longer matches counts as
        exited, and an older record of a pid never hides a later renderer
        that took it. The deadline holds on every path, a read that finds
        another renderer logged among them (lane 3's Codex review of code PR
        97 at `46cac748`, SHOULD 7). Returns the renderer pids."""
        deadline = time.monotonic() + CEILING
        while not self.render_calls(after):
            if time.monotonic() > deadline:
                pytest.fail(f"{what}: no render's call was logged within {CEILING:g} s",
                            pytrace=False)
            time.sleep(POLL)
        seen: set = set()
        while True:
            seen |= {(c["renderer"], c["renderer_start"]) for c in self.render_calls(after)}
            live = sorted({pid for pid, start in seen if not _exited(pid, start)})
            if not live and {(c["renderer"], c["renderer_start"])
                             for c in self.render_calls(after)} <= seen:
                return sorted({pid for pid, _start in seen})
            if time.monotonic() > deadline:
                pytest.fail(f"{what}: renderer pids {live} did not exit, or more were logged, "
                            f"within {CEILING:g} s", pytrace=False)
            time.sleep(POLL)

def _exited(pid: int, start: str) -> bool:
    """Whether `pid`, which started at `start` (its start token, field 22 of
    its `/proc/<pid>/stat`, as the wrapper logs it), is gone: no process has
    the pid, the one that has it started at another time, or it is a zombie.
    One read of `/proc`, with no command run and no signal sent, so it never
    blocks (lane 3's Codex review of code PR 97 at `18529e5a`, SHOULD 2)."""
    now = _stat(pid)
    return now is None or now["start"] != start or now["state"] in ("Z", "X")


def _until(predicate, seconds: float) -> bool:
    """`predicate()` polled every 100 ms until it holds, or `seconds` pass;
    its last answer."""
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() > deadline:
            return bool(predicate())
        time.sleep(POLL)
    return True


def _held_fd(fifo: Path, what: str, seconds: float = 120) -> int:
    """The FIFO's write end, once the wrapper or the shim holds a call on
    it; the case fails, naming `what`, where none does in time."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            return os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            time.sleep(0.05)
    pytest.fail(f"{what}: nothing was held on {fifo.name} within {seconds:g} s", pytrace=False)


def _held_pushes(est: RenderEstate) -> int:
    """The render pushes the wrapper has held so far, each counted by its
    own `held` line in the raw `git-wrapper.log`. Not `render_calls()`,
    which drops a pid's `held` line once its push has run."""
    return sum(1 for c in _jsonl(est.bin / "git-wrapper.log")
               if c.get("render") and c["sub"] == "push" and c.get("outcome") == "held")


def _kth_held_fd(est: RenderEstate, fifo: Path, k: int, what: str,
                 seconds: float = 120) -> int:
    """`_held_fd`, opened only once the raw log holds the `k`-th held
    render push. A pass starts only after the previous push's wrapper has
    exited, so the open lands on the `k`-th push, never on one just
    released whose wrapper has not yet seen EOF (lane 3's #38, #165
    6859801732)."""
    if not _until(lambda: _held_pushes(est) >= k, seconds):
        pytest.fail(f"{what}: the wrapper's log holds {_held_pushes(est)} held render pushes, "
                    f"not {k}, within {seconds:g} s", pytrace=False)
    return _held_fd(fifo, what, seconds)


def _end_renders(est: RenderEstate, after: int, grace: float = 10) -> None:
    """EVERY RENDERER LOGGED AFTER THE MARK `after` ENDED, and with it every
    other process of the estate, with no wait unbounded (`_quiesce`; lane
    3's Codex reviews of code PR 97 at `6d479418`, SHOULD 3, at `18529e5a`,
    BLOCKING and SHOULDs 1 and 2, and at `46cac748`, BLOCKING and SHOULD 1).
    A write's renderer is a detached fork (lane 4's T416), no child of this
    process, leading a group of its own: it is found, with every process it
    started, by the case's identity, the estate's nonce its environment
    inherits, and it is stopped, then killed, through its pidfd alone, never
    by its number or its group's. A renderer the wrapper logged whose pid
    and start token a live process has without that identity is never
    signalled. Raises where one is still there `grace` s on, one was logged
    with no start token, or one is there without the identity. Where the
    case passed, every renderer has exited (`wait_renders_exit`), and none
    is signalled."""
    _quiesce(est, after=after, grace=grace)


def _end_held_renders(est: RenderEstate, fifo: Path, fd: int | None, after: int) -> None:
    """A HOLD ON FORKED RENDERS, ENDED: the outer `finally` of a case that
    holds a write's render on `fifo`, from the FIFO's making to the end. The
    wrapper's hold is disarmed (`rearm`); every process of the estate, each
    renderer logged after the mark `after` among them, is stopped, killed
    and seen gone (`_end_renders`), so a held call is ended, never let go
    into its git; only then is the FIFO let go with an abort and unlinked
    (`_let_go`, with the write end `fd` where the case still holds one).
    Each step is tried whatever the one before it raised (lane 3's Codex
    reviews of code PR 97 at `6d479418`, SHOULDs 1 and 3, and at
    `18529e5a`, SHOULD 1)."""
    try:
        try:
            est.rearm()
        finally:
            _end_renders(est, after)
    finally:
        _let_go(fifo, fd, abort=True)


def _wrote(proc, what: str) -> None:
    assert proc.returncode == 0, (
        f"{what} on primary did not exit 0 (lane 4's T415 and T416, L4-B13):\n{_said(proc)}")


#: Test 7's seed's session of `L1`'s row (pgcluster's `_test7_seed`).
UUID_L1 = "eeeeeeee-0002-4000-8000-00000000e002"


def _operator_is_test7s() -> None:
    """THE OPERATOR'S ONE VALUE: `OPERATOR` equals T227b's `TEST7_OPERATOR`.
    The name is imported here, when a case runs, and never at module level,
    so the module collects where T227 has not landed. Every case here waits
    for T227 anyway, since its estate is built on `pg_imported` and
    `pg_cluster.imported_register`, both T227's. So on a tree without the
    name each case fails here, naming T227, and on a tree whose value
    differs each case fails here, before it asks for the engine."""
    try:
        from pgcluster import TEST7_OPERATOR
    except ImportError as exc:
        pytest.fail(f"tests/pgcluster.py has no TEST7_OPERATOR ({exc}): every case "
                    f"here waits for T227, whose T227b adds it with `pg_imported`",
                    pytrace=False)
    assert OPERATOR == TEST7_OPERATOR, (
        f"this module's OPERATOR {OPERATOR!r} is not pgcluster's TEST7_OPERATOR "
        f"{TEST7_OPERATOR!r} (T227b): change the copy here to match")


def _estate(request, tmp_path: Path, **kw) -> RenderEstate:
    """A `RenderEstate` on `pg_imported`, or `pg` where `stage` is `empty`,
    once `OPERATOR` is checked against T227b's (`_operator_is_test7s`)."""
    _operator_is_test7s()
    stage = kw.get("stage", "primary")
    db = request.getfixturevalue("pg" if stage == "empty" else "pg_imported")
    cluster = request.getfixturevalue("pg_cluster")
    return RenderEstate(tmp_path / "estate", db, cluster, **kw)


def _assert_rendered(est: RenderEstate, old: str, seqs: list, origin: Path | None = None) -> list:
    """THE RACE'S ORACLE (TP:1092-1099): origin's `main` gains exactly one
    commit per seq after `old`, carrying `seqs` in order with none repeated,
    each message the journal entry's with its `Register-Seq` (T322's form),
    and author, committer and both dates the journal's (D15). Returns the
    commits."""
    gained = est.commits_after(old, origin)
    assert [s for _sha, carried, _m in gained for s in carried] == seqs, (
        f"origin's main gained {[(sha[:12], carried) for sha, carried, _m in gained]}, not one "
        f"commit for each of {seqs} in order")
    assert len(gained) == len(seqs), f"origin's main gained {len(gained)} commits for {seqs}"
    journal = {row["seq"]: row for row in est.journal(min(seqs) - 1)}
    for sha, (k,), message in gained:
        entry = journal[k]
        assert message.rstrip("\n") == _with_trailer(entry["message"], k), (
            f"the commit for seq {k} carries {message!r}, not the journal's message "
            f"{entry['message']!r} with Register-Seq: {k} (T322's form)")
        ident = est.identity(sha, origin)
        assert ident == {"author": entry["author"], "author_epoch": entry["epoch"],
                         "committer": entry["author"], "committer_epoch": entry["epoch"]}, (
            f"the commit for seq {k} has {ident}, not the journal's author {entry['author']} "
            f"as author and committer, both at {entry['epoch']} (D15)")
    return [sha for sha, _c, _m in gained]


#: A line of a trailer block, `Token: value` (F29; B14 tasks:1504).
TRAILER_LINE = re.compile(r"[A-Za-z0-9-]+: .*")


def _with_trailer(message: str, k: int) -> str:
    """T322'S FORM (B14 tasks:1504), with no final LF: the entry's message,
    its blank last lines dropped, then `Register-Seq: <k>` as the last line
    of its final trailer block, where it has two paragraphs or more and every
    line of the last is `Token: value`; otherwise as a new last paragraph
    after one blank line."""
    lines = message.split("\n")
    while lines and not lines[-1].strip(" \t"):
        lines.pop()
    paragraphs, current = [], []
    for line in lines:
        if line.strip(" \t"):
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    paragraphs.append(current)
    block = len(paragraphs) >= 2 and all(TRAILER_LINE.fullmatch(line) for line in paragraphs[-1])
    return "\n".join(lines) + ("\n" if block else "\n\n") + f"Register-Seq: {k}"


def _no_rewrite(est: RenderEstate) -> None:
    """The wrapper's log shows no `rebase`, no `pull --rebase` and no other
    command that moves a HEAD (TP:1099; P314-318)."""
    bad = [c["argv"] for c in est.calls() if c["sub"] in REWRITES]
    assert not bad, f"a render ran a command that rewrites or moves a HEAD: {bad}"


def _push_tip(call: dict) -> str:
    """The commit a push call names, from its `<tip>:refs/heads/main`."""
    spec = next((a for a in reversed(call["argv"]) if a.endswith(":refs/heads/main")), "")
    return spec.split(":", 1)[0].lstrip("+")


# =================================================================== AT-5: the race
def test_two_renderers_racing_push_one_commit_per_seq_in_order(request, tmp_path):
    """AT-5's race (TP:1092-1099): `n+1` to `n+5` committed, then two
    renderers, in `L1`'s and `L2`'s checkouts of one bare origin, started
    through test 4's barrier. Origin's `main` gains exactly five commits,
    carrying `n+1` to `n+5` in order with none repeated, each message and
    identity the journal's; both renderers exit 0; and the wrapper's log
    shows no `rebase` and no `pull --rebase`. Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one, two = est.checkout("L1", L1), est.checkout("L2", L2)
    seqs = est.write_sql([f"race entry {i}" for i in range(1, 6)])
    assert seqs == list(range(est.n + 1, est.n + 6)), seqs
    old = est.origin_tip()
    est.arm()
    ended = est.race([one, two])
    for lc, proc in zip((one, two), ended):
        assert proc.returncode == 0, f"{lc.name}'s renderer:\n{_said(proc)}"
    _assert_rendered(est, old, seqs)
    _no_rewrite(est)


def _held_and_rendered(est: RenderEstate, one, two, seqs: list) -> tuple:
    """`two`'s renderer held at its first push, `one`'s run to its end, then
    `two` released: returns (the commit `two` had built for its push,
    origin's commits for `seqs`, `two`'s exit). `held` and the FIFO are
    owned from the FIFO's making to the end (`_end_hold`)."""
    fifo = est.root / f"hold-{two.name}.fifo"
    os.mkfifo(str(fifo), 0o600)
    held = fd = None
    try:
        old = est.origin_tip()
        est.arm([{"sub": "push", "do": "hold", "fifo": str(fifo), "where": str(two.clone),
                  "times": 1}])
        held = est.popen_render(two)
        fd = _open_when_held(fifo, held)
        if fd is None:
            pytest.fail(f"{two.name}'s renderer never reached its push:\n{_end_session(held)}",
                        pytrace=False)
        proc = est.render(one)
        assert proc.returncode == 0, f"{one.name}'s renderer:\n{_said(proc)}"
        end, fd = fd, None
        _let_go(fifo, end)  # `two` released: its FIFO unlinked, then the write end closed
        out, err = held.communicate(timeout=300)
    finally:
        _end_hold(held, fifo, fd, est)
    first = next(c for c in est.calls("push", two))
    commits = _assert_rendered(est, old, seqs)
    return _push_tip(first), commits, SimpleNamespace(returncode=held.returncode, stdout=out,
                                                      stderr=err)


def test_renderers_make_identical_commits_for_one_seq(request, tmp_path):
    """AT-5's identical commits (TP:1100-1102; P1363-1367): with `n+1`
    committed, `L2`'s renderer is held at its push while `L1`'s renders and
    pushes; the commit `L2` built for `n+1`, the one its push names, is the
    sha `L1` pushed, its author and committer the journal's identity, both
    dated by the entry's commit UTC (D15). Released, `L2` exits 0. Fails
    until T320 to T322."""
    est = _estate(request, tmp_path)
    one, two = est.checkout("L1", L1), est.checkout("L2", L2)
    seqs = est.write_sql(["one seq, two renderers"])
    built, commits, two_ended = _held_and_rendered(est, one, two, seqs)
    assert built == commits[0], (f"L2's renderer built {built} for seq {seqs[0]}, and L1's "
                                 f"pushed {commits[0]}: two renderers made different commits")
    assert two_ended.returncode == 0, f"L2's renderer after the release:\n{_said(two_ended)}"


# =================================================================== AT-5: the kill
def test_a_renderer_killed_by_sigkill_leaves_the_checkout_able_to_render_at_once(request,
                                                                                tmp_path):
    """[L4-4] (TP:1107-1109): the wrapper sends SIGKILL to the renderer's
    process group just before its push. Then a non-blocking `flock` on
    `lanes-render.lock` succeeds at once, no lock directory is left, and,
    with no hand removal, the next render pushes every missing seq in order.
    Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1)
    seqs = est.write_sql(["killed before its push, 1", "killed before its push, 2"])
    old = est.origin_tip()
    est.arm([{"sub": "push", "do": "kill", "where": str(one.clone), "times": 1}])
    killed = est.render(one)
    assert killed.returncode == -signal.SIGKILL, (
        f"the renderer was not killed at its push:\n{_said(killed)}")
    assert est.origin_tip() == old, "the killed renderer pushed"
    lock = one.git_dir / "lanes-render.lock"
    assert not lock.is_dir(), "a lock directory is left behind"
    assert not [p.name for p in one.git_dir.iterdir()
                if p.is_dir() and p.name.startswith("lanes-render")], "a lock directory is left"
    assert _lock_is_free(lock), "the SIGKILL did not release lanes-render.lock (D14; [L4-4])"
    est.arm()
    proc = est.render(one)
    assert proc.returncode == 0, f"the next render, with no hand removal:\n{_said(proc)}"
    _assert_rendered(est, old, seqs)


def test_a_renderer_killed_inside_read_tree_does_not_block_the_next_render(request, tmp_path):
    """AT-5 (TP:1065-1067, :1223-1224): the wrapper leaves
    `lanes-render.index.lock` behind, as git inside `read-tree` does, and
    sends SIGKILL to the renderer's process group. The lock is free at once,
    and the next render clears the stale `.lock` under the lock and pushes
    every missing seq in order. Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1)
    seqs = est.write_sql(["killed inside read-tree"])
    old = est.origin_tip()
    est.arm([{"sub": "read-tree", "do": "kill", "index_lock": True, "where": str(one.clone),
              "times": 1}])
    killed = est.render(one)
    assert killed.returncode == -signal.SIGKILL, (
        f"the renderer was not killed inside read-tree:\n{_said(killed)}")
    stale = one.git_dir / "lanes-render.index.lock"
    assert stale.exists(), (f"no {stale.name} was left: the build ran no read-tree under "
                            f"GIT_INDEX_FILE {one.git_dir / 'lanes-render.index'}")
    assert _lock_is_free(one.git_dir / "lanes-render.lock"), "the render lock is still held"
    est.arm()
    proc = est.render(one)
    assert proc.returncode == 0, f"the next render after the stale index lock:\n{_said(proc)}"
    _assert_rendered(est, old, seqs)
    assert not stale.exists(), f"{stale.name} is still there after the next render"


# =================================================================== AT-5: the lost race
def test_a_lost_push_race_never_rebases_a_render(request, tmp_path):
    """P314-318 (TP:1034, :1181): `L1`'s renderer is held at its first push
    while another clone pushes a handoff commit, so the push is rejected as a
    non-fast-forward. The renderer fetches, builds again on the new tip, and
    pushes: origin's `main` is the handoff commit and then one commit per
    seq, in order; the wrapper's log shows two pushes with a fetch between,
    and no `rebase`, `pull` or other command that moves a HEAD; and `L1`'s
    HEAD, index and status are as before. Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1)
    seqs = est.write_sql(["a lost race, 1", "a lost race, 2"])
    before = est.snapshot(one)
    fifo = est.root / "hold.fifo"
    os.mkfifo(str(fifo), 0o600)
    held = fd = None
    try:  # `held` and the FIFO owned to the end (`_end_hold`)
        est.arm([{"sub": "push", "do": "hold", "fifo": str(fifo), "where": str(one.clone),
                  "times": 1}])
        held = est.popen_render(one)
        fd = _open_when_held(fifo, held)
        if fd is None:
            pytest.fail(f"the renderer never reached its push:\n{_end_session(held)}",
                        pytrace=False)
        handoff = est.commit_in_origin(est.origin_tip(), {
            f"handoffs/{L2}.md": b"# a handoff pushed while the render was held\n"},
            "a handoff commit, pushed during the render's push")
        est.push_by_hand(handoff)
        end, fd = fd, None
        _let_go(fifo, end)  # the render released: its FIFO unlinked, then the write end closed
        out, err = held.communicate(timeout=300)
    finally:
        _end_hold(held, fifo, fd, est)
    assert held.returncode == 0, _said(SimpleNamespace(returncode=held.returncode, stdout=out,
                                                       stderr=err))
    _assert_rendered(est, handoff, seqs)
    pushes = est.calls("push", one)
    assert [p.get("rc") for p in pushes] == [1, 0], (
        f"not one rejected push then one that landed: {[(p['outcome'], p.get('rc')) for p in pushes]}")
    calls = est.calls(lc=one)
    first, second = (calls.index(p) for p in pushes)
    assert any(c["sub"] == "fetch" for c in calls[first + 1:second]), (
        "the renderer pushed again with no fetch after the rejection")
    _no_rewrite(est)
    assert est.snapshot(one) == before, "the render moved L1's HEAD, index or status"


# =================================================================== AT-5: the push (T320)
def test_the_render_push_alone_carries_the_deploy_key(request, tmp_path):
    """D23 (TP:1182-1193): with `render_key=` set, origin named by a GitHub
    HTTPS URL, a global `url.*.insteadOf` rewriting SSH URLs to HTTPS and
    `SSH_AUTH_SOCK` in the case's own environment, the wrapper records the
    push and makes it to the bare origin in its place. The push names
    `ssh://git@github.com/<owner>/<repo>.git` and `<tip>:refs/heads/main`,
    with `--no-verify` and no force; its environment alone carries
    `GIT_SSH_COMMAND` with `-i` the key file, `IdentitiesOnly=yes` and
    `BatchMode=yes`, `GIT_CONFIG_GLOBAL=/dev/null` and
    `GIT_CONFIG_NOSYSTEM=1`, and no `SSH_AUTH_SOCK`; the checkout's
    configuration is unchanged, with no `pushurl`; and the read-back fetches
    `origin`. Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, repository=GITHUB_HTTPS)
    est.git(one.clone, "remote", "set-url", "origin", GITHUB_HTTPS)
    (one.home / ".gitconfig").write_text(
        '[url "https://github.com/"]\n\tinsteadOf = ssh://git@github.com/\n', encoding="utf-8")
    key = _private(one.root / "keys" / "render_key", "not a key: the git wrapper makes the push\n")
    conf = est.config("deploy-key", "primary", [f"render_key={key}"])
    local_before = est.git(one.clone, "config", "--local", "--list")
    seqs = est.write_sql(["pushed with the deploy key"])
    old = est.origin_tip()
    est.arm(redirect={GITHUB_HTTPS: str(est.origin), GITHUB_SSH: str(est.origin)})
    proc = est.render(one, conf=conf, env={"SSH_AUTH_SOCK": str(one.root / "agent.sock")})
    assert proc.returncode == 0, f"the render with render_key=:\n{_said(proc)}"
    _assert_rendered(est, old, seqs)
    calls = est.calls(lc=one)
    pushes = [c for c in calls if c["sub"] == "push"]
    assert len(pushes) == 1, f"not one push: {[p['argv'] for p in pushes]}"
    push = pushes[0]
    argv = push["argv"]
    assert GITHUB_SSH in argv, f"the push does not name {GITHUB_SSH}: {argv}"
    assert any(a.endswith(":refs/heads/main") and not a.startswith("+") for a in argv), argv
    assert "--no-verify" in argv and not {"-f", "--force", "--force-with-lease"} & set(argv), argv
    ssh = push["env"]["GIT_SSH_COMMAND"] or ""
    words = shlex.split(ssh)
    assert "-i" in words and words[words.index("-i") + 1] == str(key), (
        f"GIT_SSH_COMMAND does not name the key file with -i: {ssh!r}")
    for option in ("IdentitiesOnly=yes", "BatchMode=yes"):
        assert option in ssh, f"GIT_SSH_COMMAND lacks {option}: {ssh!r}"
    assert (push["env"]["GIT_CONFIG_GLOBAL"], push["env"]["GIT_CONFIG_NOSYSTEM"]) == (
        os.devnull, "1"), push["env"]
    assert push["env"]["SSH_AUTH_SOCK"] is None, "the push inherited SSH_AUTH_SOCK"
    others = [c for c in calls if c is not push]
    assert not [c["argv"] for c in others if c["env"]["GIT_SSH_COMMAND"]], (
        "another git call than the push carried GIT_SSH_COMMAND")
    assert not [c["argv"] for c in others if str(key) in json.dumps(c["argv"])], (
        "another git call named the key file")
    local_after = est.git(one.clone, "config", "--local", "--list")
    assert local_after == local_before, f"the checkout's configuration changed:\n{local_after}"
    assert "pushurl" not in local_after.lower(), local_after
    after = calls[calls.index(push) + 1:]
    assert any(c["sub"] == "fetch" and "origin" in c["argv"] for c in after), (
        "the read-back fetched no `origin` after the push")


def test_a_non_github_origin_with_render_key_is_refused_with_2(request, tmp_path):
    """D23 (TP:1194; B14 tasks:1472): with `render_key=` set and the
    checkout's origin a plain path, no GitHub repository, `render --checkout`
    exits 2, names the origin as not a GitHub repository, makes no push, and
    origin's `main` does not move. Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1)
    key = _private(one.root / "keys" / "render_key", "not a key\n")
    conf = est.config("deploy-key", "primary", [f"render_key={key}"])
    est.write_sql(["refused: the origin is no GitHub repository"])
    old = est.origin_tip()
    est.arm()
    proc = est.render(one, conf=conf)
    assert proc.returncode == 2, f"a non-GitHub origin with render_key= is not refused 2:\n{_said(proc)}"
    assert "not a GitHub repository" in proc.stderr, _said(proc)
    assert est.calls("push") == [], f"a push was made: {[c['argv'] for c in est.calls('push')]}"
    assert est.origin_tip() == old, "origin's main moved"


def test_without_render_key_the_push_goes_to_origin(request, tmp_path):
    """Q21(b)(A) (TP:1195; B14 tasks:1473-1477): without `render_key=` the
    push names `origin` as it stands, `<tip>:refs/heads/main`, never forced,
    with no `GIT_SSH_COMMAND`; origin gains the seq; and the checkout's
    configuration is unchanged. Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1)
    local_before = est.git(one.clone, "config", "--local", "--list")
    seqs = est.write_sql(["pushed to origin as it stands"])
    old = est.origin_tip()
    est.arm()
    proc = est.render(one)
    assert proc.returncode == 0, f"the render without render_key=:\n{_said(proc)}"
    commits = _assert_rendered(est, old, seqs)
    pushes = est.calls("push", one)
    assert len(pushes) == 1, f"not one push: {[p['argv'] for p in pushes]}"
    argv = pushes[0]["argv"]
    assert argv[argv.index(next(a for a in argv if a.endswith(":refs/heads/main"))) - 1] == "origin", (
        f"the push does not name `origin`: {argv}")
    assert _push_tip(pushes[0]) == commits[-1], argv
    assert not {"-f", "--force", "--force-with-lease"} & set(argv) and not any(
        a.startswith("+") for a in argv), argv
    assert pushes[0]["env"]["GIT_SSH_COMMAND"] is None, pushes[0]["env"]
    assert est.git(one.clone, "config", "--local", "--list") == local_before


# =================================================================== AT-5: the pass and form C
def _deepen(est: RenderEstate, depth: int) -> str:
    """`depth` commits under `handoffs/` on origin's `main`, none in the
    render set, by one `git fast-import`. Returns the new tip."""
    old = est.origin_tip()
    stream = []
    for n in range(1, depth + 1):
        message = f"t270: handoff commit {n} of {depth}\n".encode()
        content = f"# handoff {n}\n".encode()
        stream.append(b"commit refs/heads/main\n")
        stream.append(f"mark :{n}\n".encode())
        stream.append(f"committer T270 estate <t270@example.invalid> {1762858800 + n} +0000\n"
                      .encode())
        stream.append(b"data %d\n" % len(message) + message)
        stream.append(f"from {old if n == 1 else ':' + str(n - 1)}\n".encode())
        stream.append(b"M 100644 inline handoffs/t270-depth.md\n")
        stream.append(b"data %d\n" % len(content) + content)
    est.origin_git("fast-import", "--quiet", data=b"".join(stream))
    tip = est.origin_tip()
    assert est.origin_git("rev-list", "--count", f"{old}..{tip}").strip() == str(depth)
    return tip


def _walks(est: RenderEstate, lc) -> list:
    """The wrapper's `log --first-parent` calls in the checkout: form C's
    walk, as (`-n`, `--skip`, whether it says `--grep`)."""
    found = []
    for call in est.calls("log", lc):
        argv = call["argv"]
        if "--first-parent" not in argv or any(a.startswith("--raw") for a in argv):
            continue
        n = argv[argv.index("-n") + 1] if "-n" in argv else None
        skip = argv[argv.index("--skip") + 1] if "--skip" in argv else None
        found.append((n, skip, any(a.startswith("--grep") for a in argv)))
    return found


@pytest.mark.parametrize("depth", ["depth-0", "depth-250"])
def test_the_renderer_finds_m_by_paging_form_c(request, tmp_path, depth):
    """Lane 4's section (TP:1040-1043, :1196-1203): at depth 0 the newest
    render commit is the tip, and the renderer finds it in one page, the
    wrapper's log showing each pass's walk as one page of `-n 200`, no page
    after the first and no `--grep`; T323's holder runs a second pass after
    a pass that made progress, F15, and that pass walks its first page
    again from the new tip. At depth 250 it is 250 first-parent commits below the
    tip: the renderer pages with `--skip` and finds it, the log showing
    `-n 200`, the `--skip 200` page and no `--grep`. Either way it renders
    the seq after it on top of the tip. Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1)
    tip = _deepen(est, 250) if depth == "depth-250" else est.origin_tip()
    seqs = est.write_sql([f"found at {depth}"])
    est.arm()
    proc = est.render(one)
    assert proc.returncode == 0, f"the render at {depth}:\n{_said(proc)}"
    _assert_rendered(est, tip, seqs)
    walks = _walks(est, one)
    assert walks and all(n == "200" for n, _skip, _grep in walks), (
        f"form C's walk is not in pages of 200: {walks}")
    assert not any(grep for _n, _skip, grep in walks), f"form C's walk used --grep: {walks}"
    if depth == "depth-0":
        assert all(skip in (None, "0") for _n, skip, _g in walks), (
            f"at depth 0 a pass's walk took more than its first page: {walks}")
    else:
        assert [skip or "0" for _n, skip, _g in walks[:2]] == ["0", "200"], (
            f"at depth 250 the walk did not page on with --skip 200: {walks}")


@pytest.mark.parametrize("why", ["none", "out-of-time"])
def test_with_no_register_seq_found_the_renderer_pushes_nothing_and_records_why(request,
                                                                               tmp_path, why):
    """Lane 4's section (TP:1040-1043, :1204-1206): `[none]`, origin's
    `main` is C, no commit of which carries a `Register-Seq` (the marker
    commit is recorded and not on origin); `[out-of-time]`, the wrapper
    stalls the walk's `log` past `LANES_GIT_TIMEOUT`, set to 2 s. The
    renderer pushes nothing and exits non-zero; `mirror_state.last_error`
    and its time are set through `record_mirror_state`, `diverged_sha` stays
    NULL; `status` shows the failed pass; and origin is unchanged. Fails
    until T320 to T322."""
    est = _estate(request, tmp_path, marker="pushed" if why == "out-of-time" else "recorded")
    one = est.checkout("L1", L1)
    est.write_sql([f"no Register-Seq found: {why}"])
    old = est.origin_tip()
    env = None
    if why == "out-of-time":
        est.arm([{"sub": "log", "do": "stall", "has": "--first-parent", "seconds": 6,
                  "where": str(one.clone)}])
        env = {"LANES_GIT_TIMEOUT": "2"}
    else:
        assert old == est.c and est.form_c(old) == "", "origin's main carries a Register-Seq"
        est.arm()
    proc = est.render(one, env=env, timeout=120)
    assert proc.returncode != 0, f"the renderer found no m and still ended 0:\n{_said(proc)}"
    assert est.calls("push") == [], f"it pushed: {[c['argv'] for c in est.calls('push')]}"
    assert est.origin_tip() == old, "origin's main moved"
    mirror = est.mirror()
    assert mirror["last_error"] and mirror["last_error_utc"], (
        f"no failed pass is recorded in mirror_state: {mirror}\n{_said(proc)}")
    assert mirror["diverged_sha"] is None, f"a divergence was recorded: {mirror}"
    shown = est.status(one)
    assert FAILED_PASS.search(shown.stdout), f"status does not show the failed pass:\n{_said(shown)}"


def test_a_pass_renders_at_most_64_seqs(request, tmp_path):
    """PC-3 (TP:1044-1045, :1207-1209): a backlog of 70 seqs reaches origin
    as `m+1` to `m+64` in one pass, one push, and the rest in the next; and
    the commits are those of any other batching: a second origin, rendered
    in batches of 10 and then 60, carries the same 70 shas. Fails until
    T320 to T323."""
    est = _estate(request, tmp_path)
    other_origin = est.second_origin("origin-batched")
    one = est.checkout("L1", L1)
    batched = est.checkout("L2", L2, origin=other_origin)
    old = est.origin_tip()
    m = est.n
    first = est.write_sql([f"backlog entry {i}" for i in range(1, 11)])
    est.arm()
    proc = est.render(batched)
    assert proc.returncode == 0, f"the batched render of 10:\n{_said(proc)}"
    rest = est.write_sql([f"backlog entry {i}" for i in range(11, 71)])
    seqs = first + rest
    assert seqs == list(range(m + 1, m + 71)), seqs
    est.arm()
    proc = est.render(one)
    assert proc.returncode == 0, f"the render of a backlog of 70:\n{_said(proc)}"
    commits = _assert_rendered(est, old, seqs)
    tips = [_push_tip(p) for p in est.calls("push", one)]
    assert tips == [commits[63], commits[69]], (
        f"the pushes named {tips}, not seq {m + 64}'s commit, then seq {m + 70}'s: a pass "
        f"renders at most 64 seqs")
    est.arm()
    proc = est.render(batched)
    assert proc.returncode == 0, f"the batched render of 60:\n{_said(proc)}"
    assert _assert_rendered(est, old, seqs, other_origin) == commits, (
        "batches of 10 and 60 made other commits than batches of 64 and 6")


@pytest.mark.parametrize("shape", ["subject-only", "trailer-block", "prose"])
def test_form_c_reads_the_trailer_from_each_message_shape(request, tmp_path, shape):
    """Lane 4's section (TP:1225-1226): a journal message of each shape, a
    subject alone, a body ending in a trailer block, and a body ending in
    prose. Two checkouts give one sha for it (`L2` held at its push while
    `L1` renders), and form C reads `<k>` from it. The trailer joins the
    final trailer block, or is a new last paragraph after one blank line
    (T322). Fails until T320 to T322."""
    message = {
        "subject-only": "t270: a subject alone",
        "trailer-block": (f"t270: a subject\n\nA body line.\n\nLane: {L1}\n"
                          f"Co-Authored-By: T270 <t270@example.invalid>"),
        "prose": ("t270: a subject\n\nA body that ends in prose, a paragraph with no "
                  "trailer in it."),
    }[shape]
    est = _estate(request, tmp_path)
    one, two = est.checkout("L1", L1), est.checkout("L2", L2)
    old = est.origin_tip()
    (k,) = est.write_sql([f"form C, {shape}"], messages=[message])
    fifo = est.root / "hold.fifo"
    os.mkfifo(str(fifo), 0o600)
    held = fd = None
    try:  # `held` and the FIFO owned to the end (`_end_hold`)
        est.arm([{"sub": "push", "do": "hold", "fifo": str(fifo), "where": str(two.clone),
                  "times": 1}])
        held = est.popen_render(two)
        fd = _open_when_held(fifo, held)
        if fd is None:
            pytest.fail(f"L2's renderer never reached its push:\n{_end_session(held)}",
                        pytrace=False)
        proc = est.render(one)
        assert proc.returncode == 0, f"L1's renderer:\n{_said(proc)}"
        end, fd = fd, None
        _let_go(fifo, end)  # L2's render released: its FIFO unlinked, then the write end closed
        held.communicate(timeout=300)
    finally:
        _end_hold(held, fifo, fd, est)
    assert held.returncode == 0, "L2's renderer after the release"
    gained = est.commits_after(old)
    assert [carried for _s, carried, _m in gained] == [[k]], gained
    sha, _carried, raw = gained[0]
    assert _push_tip(est.calls("push", two)[0]) == sha, "two checkouts gave two shas"
    assert est.form_c(sha) == str(k), f"form C reads {est.form_c(sha)!r} from {sha}, not {k}"
    joined = "\n" if shape == "trailer-block" else "\n\n"
    assert raw.rstrip("\n") == f"{message}{joined}Register-Seq: {k}", (
        f"the {shape} message is not the journal's with Register-Seq: {k} "
        f"{'in its trailer block' if shape == 'trailer-block' else 'as a new paragraph'}: {raw!r}")


@pytest.mark.parametrize("case", ["marker-first-head-minus-1", "marker-first-head-0", "forged"])
def test_a_register_seq_above_the_head_with_the_switch_at_files_is_no_divergence_and_renders_nothing(
        request, tmp_path, case):
    """R2's N6, at `files` (TP:1150-1167, :1227-1228): the switch reads
    `files`, and origin's `main` carries a commit whose last `Register-Seq`
    is above the head `h`: the marker commit `S` with `Register-Seq: 1`,
    pushed ahead of the import (`h` -1, on `pg`) or after it (`h` 0); or a
    forged commit under `handoffs/` carrying `Register-Seq: <h+10>`. A pass
    run by `render --checkout <c>`, as a fork runs it, records no
    divergence (`diverged_sha` NULL, no `diverged at` in `status`), pushes
    nothing, and exits 0. Fails until T320 to T322."""
    est = _estate(request, tmp_path, stage="empty" if case.endswith("minus-1") else "imported")
    h = est.head()
    if case == "forged":
        top = est.commit_in_origin(est.c, {f"handoffs/{L1}.md": b"# a forged commit\n"},
                                   f"a forged handoff commit\n\nRegister-Seq: {h + 10}\n")
    else:
        top = est.commit_in_origin(est.c, {"lanes/STORE": b"store=primary\n"},
                                   "t270: the marker commit, pushed first\n\nRegister-Seq: 1\n")
    est.push_by_hand(top)
    one = est.checkout("L1", L1)
    est.arm()
    proc = est.render(one)
    assert proc.returncode == 0, f"the pass at files:\n{_said(proc)}"
    assert est.calls("push") == [] and est.origin_tip() == top, "the pass at files pushed"
    assert est.mirror()["diverged_sha"] is None, f"a divergence was recorded: {est.mirror()}"
    shown = est.status(one)
    assert not DIVERGED.search(shown.stdout), f"status prints a divergence:\n{shown.stdout}"
    assert est.head() == h and est.switch()["mode"] == "files"


def test_a_render_commit_with_a_private_index_and_its_push_are_timed_and_recorded(request,
                                                                                  tmp_path):
    """M6, section 5.1 (TP:1229-1235): the render commit made through the
    private index, and its push to the local origin, each timed from the
    wrapper's log, which tells the commit (`commit-tree`) from the push, over
    five renders of one seq each; recorded with section 5.3's statistics and
    their n, never asserted. Correctness alongside: each `write-tree` ran
    under `GIT_INDEX_FILE` `lanes-render.index`, and origin gains each commit
    with its `Register-Seq`. Fails until T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1)
    commits, pushes = [], []
    for n in range(1, 6):
        old = est.origin_tip()
        seqs = est.write_sql([f"timed render {n}"])
        est.arm()
        proc = est.render(one)
        assert proc.returncode == 0, f"timed render {n}:\n{_said(proc)}"
        _assert_rendered(est, old, seqs)
        trees = est.calls("write-tree", one)
        assert trees and all((c["env"]["GIT_INDEX_FILE"] or "").endswith("lanes-render.index")
                             for c in trees), (
            f"a write-tree ran without the private index: {[c['env'] for c in trees]}")
        commits += [(c["t1"] - c["ran"]) * 1000 for c in est.calls("commit-tree", one)]
        pushes += [(c["t1"] - c["ran"]) * 1000 for c in est.calls("push", one)]
    assert commits and pushes
    for what, samples in (("render commit, private index", commits), ("its push", pushes)):
        stats = _stats(samples)
        row = (f"| M6 | fixture cluster, local bare origin | {what} | median "
               f"{stats['median']:.1f} ms, p95 {stats['p95']:.1f} ms, "
               f"{stats['min']:.1f}-{stats['max']:.1f} ms, n={stats['n']} |")
        print("\n" + row)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(row + "\n")


# =================================================================== AT-5: six lost races (T323, T325)
def test_six_lost_races_leave_the_last_write_for_the_next_write_or_reconcile(request,
                                                                             tmp_path):
    """Lane 4's known gap (TP:1044-1045, :1074-1080, :1216-1218): the wrapper
    rejects six pushes in a row as non-fast-forwards. The renderer makes six
    push attempts in all, a fetch before each new one, and ends non-zero;
    origin is unchanged and `status` shows a lag of 1. Then `reconcile`,
    run in the lane's checkout with the `mode=primary` configuration,
    renders it: origin carries the seq, and the lag is 0. Fails until T320
    to T323, and T325 (the re-render), at its own assertion."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1)
    seqs = est.write_sql(["the last write, six races lost"])
    old = est.origin_tip()
    est.arm([{"sub": "push", "do": "reject", "where": str(one.clone), "times": 6}])
    proc = est.render(one)
    assert proc.returncode != 0, f"the renderer that lost six races ended 0:\n{_said(proc)}"
    assert est.origin_tip() == old, "origin moved"
    calls = est.calls(lc=one)
    pushes = [i for i, c in enumerate(calls) if c["sub"] == "push"]
    assert len(pushes) == 6 and all(calls[i]["outcome"] == "rejected" for i in pushes), (
        f"not six rejected pushes: {[(c['sub'], c['outcome']) for c in calls]}")
    for before, after in zip(pushes, pushes[1:]):
        assert any(c["sub"] == "fetch" for c in calls[before + 1:after]), (
            "a push was retried with no fetch after its rejection")
    assert est.lag(one) == 1, f"status does not show a lag of 1:\n{est.status(one).stdout}"
    proc = est.index(one, "reconcile", conf=est.primary_conf)
    assert proc.returncode == 0, f"reconcile:\n{_said(proc)}"
    assert est.commits_after(old) and est.commits_after(old)[-1][1] == seqs, (
        f"reconcile did not render seq {seqs[0]} (T325: it re-renders what the mirror lacks, "
        f"through T322's pass): origin carries {est.commits_after(old)}\n{_said(proc)}")
    _assert_rendered(est, old, seqs)
    assert est.lag(one) == 0, f"the lag is not 0 after reconcile:\n{est.status(one).stdout}"


# =================================================================== writes that fork
#: THE WRITER- AND FORK-SIDE CASES: each write is `lanes-edit.sh log NOTED`
#: (or lane-start's stamp) on `primary` from a lane's checkout, through the
#: flipped copy, and its fork starts the renderer in the lane's own register
#: checkout `<c>` (`own=True`, T270e), whose calls, lock and marks each case
#: reads. Each fails until lane 4's T415 and T416 (L4-B13), with T320 to
#: T323. Every wait for a forked render is open point 8's.


def test_a_renderer_killed_between_commit_and_push_blocks_nothing(request, tmp_path):
    """AT-5's kill (TP:1103-1115; P319-346; concern 3, ADV-C6): `L1`'s write
    forks a render that the wrapper kills by SIGKILL just before its push.
    Read after the renderer's exit (open point 8's second wait): `L1`'s
    HEAD, index digest and `status --porcelain` are as before the render.
    Then, with no other command between, `L1`'s next write forks a render
    that pushes every missing seq in order, and `L1`'s next handoff commit,
    lane-handoff's commit block, exits 0 and is pushed. A second kill, then
    a write, then lane-start's stamp (`append-session-id`), which exits 0
    and is rendered. Fails until L4-B13 and T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    old = est.origin_tip()
    before = est.snapshot(one.own)
    est.arm([{"sub": "push", "do": "kill", "render_only": True, "where": str(one.own.clone),
              "times": 1}])
    mark = est.entries()
    _wrote(est.write(one, "a write whose render is killed before its push"), "log NOTED")
    est.wait_renders_exit(mark, "the killed render")
    assert [c for c in est.render_calls(mark) if c["outcome"] == "killed"], (
        "the wrapper killed no render at its push")
    assert est.snapshot(one.own) == before, "the killed render moved L1's HEAD, index or status"
    assert _lock_is_free(one.own.git_dir / "lanes-render.lock"), "the render lock is still held"
    # The next write, then lane-handoff's commit block, with nothing between.
    est.rearm()
    _wrote(est.write(one, "the next write after the kill"), "the next log NOTED")
    est.wait_lag_0(one, "the next write's render")
    _assert_rendered(est, old, list(range(est.n + 1, est.head() + 1)))
    handoff = f"handoffs/{L1}.md"
    (one.own.clone / "handoffs").mkdir(exist_ok=True)
    (one.own.clone / handoff).write_text("# a handoff, after the killed render\n",
                                         encoding="utf-8")
    env = dict(est.plain_env, HOME=str(one.home))
    for argv in (["add", "--", handoff],
                 ["commit", "-q", "-m", f"handoff({L1}@{WS}): PAUSED, t270", "-m",
                  f"Lane: {L1}", "--", handoff],
                 ["pull", "--rebase", "-q", "origin", "main"], ["push", "-q", "origin", "main"]):
        est.git(one.own.clone, *argv, env=env)
    assert handoff in est.origin_git("ls-tree", "-r", "--name-only", "refs/heads/main",
                                     "handoffs/").split(), "the handoff commit was not pushed"
    # The second case: a kill, a write, then lane-start's stamp. It arms the
    # kill afresh with `est.arm()`, which starts the wrapper's log and its
    # counts again: `rearm()` keeps each arm's count of uses, and the first
    # case's kill used arm 0's one (`times: 1`), so a re-armed kill never
    # fired and the second case passed with no kill (RV20, finding 2).
    est.arm([{"sub": "push", "do": "kill", "render_only": True, "where": str(one.own.clone),
              "times": 1}])
    mark = est.entries()
    _wrote(est.write(one, "a second write whose render is killed"), "log NOTED")
    est.wait_renders_exit(mark, "the second killed render")
    assert [c for c in est.render_calls(mark) if c["outcome"] == "killed"], (
        f"the wrapper killed no render at the second case's push: "
        f"{[(c['sub'], c['outcome']) for c in est.render_calls(mark)]}")
    est.rearm()
    _wrote(est.write(one, "the write after the second kill"), "log NOTED")
    stamp = est.edit(one, "append-session-id", L1, f"harness `{UUID_L1}`", " (t270)")
    _wrote(stamp, "lane-start's stamp, append-session-id")
    est.wait_lag_0(one, "the stamp's render")


def _held_burst(est: RenderEstate, one) -> SimpleNamespace:
    """AT-5's HELD RENDERER (TP:1116-1125): `L1`'s render held at its push
    (the hold re-armed for each push) while four more writes from `L1` each
    exit 0; then the hold is disarmed and released, and both of open point
    8's waits run. Returns what the case reads. The hold, the FIFO and every
    renderer are owned from the FIFO's making to the end: the `try` begins
    at once after `mkfifo`, with every fallible call inside it, and its
    `finally` disarms the hold, ends every process of the estate, then lets
    the FIFO go with an abort and unlinks it (`_end_held_renders`). The hold
    is released into its push only where the four forks were seen; where
    they were not, the held call is ended with the rest and never let go
    into its git. The four forks' result, saved while the hold stood, is
    asserted only after the clean-up (lane 3's Codex reviews of code PR 97
    at `6d479418`, SHOULD 3, and at `18529e5a`, SHOULDs 1 and 3)."""
    fifo = est.root / "held.fifo"
    os.mkfifo(str(fifo), 0o600)
    fd, mark = None, 0
    try:
        rerun = one.own.git_dir / "lanes-render.rerun"
        old = est.origin_tip()
        est.arm([{"sub": "push", "do": "hold", "render_only": True, "fifo": str(fifo),
                  "where": str(one.own.clone)}])
        mark = est.entries()
        _wrote(est.write(one, "the first write of a burst"), "log NOTED")
        fd = _held_fd(fifo, "the first write's render, at its push")
        holder = {c["renderer"] for c in est.render_calls(mark) if c["outcome"] == "held"}
        waited = []
        for n in range(2, 6):
            start = time.monotonic()
            _wrote(est.write(one, f"write {n} of a burst, while the render is held",
                             timeout=120), f"write {n}")
            waited.append(time.monotonic() - start)

        def forks() -> dict:
            return {c["renderer"]: c["renderer_start"] for c in est.render_calls(mark)
                    if c["renderer"] not in holder}
        # A detached fork may start after its write returns: wait, the hold
        # standing, until the four have run a git call and exited, or 30 s.
        # The hold is released only once that holds: four writes, four forks,
        # each a renderer other than the holder (TP:1116-1120; lane 3's Codex
        # review of code PR 97, SHOULD 5).
        settled = _until(lambda: len(forks()) >= 4
                         and all(_exited(p, s) for p, s in forks().items()), CEILING)
        held_forks = forks()
        forks_live = [pid for pid, start in held_forks.items() if not _exited(pid, start)]
        marked = rerun.exists()
        four = settled and len(held_forks) >= 4
        if four:  # where they were not seen, the case fails below, after the clean-up
            est.rearm()
            end, fd = fd, None
            _let_go(fifo, end)  # the hold released: its FIFO unlinked, then the write end closed
            est.wait_lag_0(one, "the burst's last write")
            est.wait_renders_exit(mark, "the burst's renders")
    finally:
        _end_held_renders(est, fifo, fd, mark)
    assert four, (
        f"with the render held, {len(held_forks)} renderers besides the holder ran "
        f"`render --checkout`, not at least four, one per write, all exited within "
        f"{CEILING:g} s: {sorted(held_forks)}, still live {forks_live}")
    assert _lock_is_free(one.own.git_dir / "lanes-render.lock"), "the render lock is still held"
    pushes = [c for c in est.render_calls(mark) if c["sub"] == "push" and c["outcome"] == "ran"]
    return SimpleNamespace(old=old, holder=holder, marked=marked, forks=forks(),
                           forks_live=forks_live, waited=waited, pushes=pushes,
                           rerun_left=rerun.exists())


def test_a_held_renderer_delays_no_writer_beyond_the_fork(request, tmp_path):
    """AT-5's held renderer (TP:1116-1120, :1240-1241): with `L1`'s render
    held at its push, four more writes from `L1` each exit 0 while it is
    held, so no fork waited; each fork that found the lock held left
    `lanes-render.rerun` in the checkout's git directory and had exited
    while the hold still stood (D14). Fails until L4-B13 and T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    seen = _held_burst(est, one)
    assert len(seen.holder) == 1, f"not one held render: {seen.holder}"
    assert seen.marked, "no fork that found the lock held left lanes-render.rerun"
    assert seen.forks, "no fork of the four writes ran `render --checkout`"
    assert not seen.forks_live, (
        f"forks {seen.forks_live} that found the lock held had not exited while it was held")


def test_a_burst_from_one_lane_gives_at_most_two_renders(request, tmp_path):
    """[L4-3], qualified (TP:1028-1030, :1121-1125, :1242): the held
    renderer's burst of five writes. Once the lag is 0 and every renderer
    has exited, at most two renders made commits, the wrapper's log
    counting their pushes, and origin carries the burst's last seq, each
    seq once, in order. Fails until L4-B13 and T320 to T323."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    seen = _held_burst(est, one)
    assert 1 <= len(seen.pushes) <= 2, (
        f"{len(seen.pushes)} pushes for a burst that arrived within one pass, not at most two: "
        f"{[_push_tip(p)[:12] for p in seen.pushes]}")
    _assert_rendered(est, seen.old, list(range(est.n + 1, est.head() + 1)))


def test_the_last_write_of_a_burst_is_rendered_with_no_later_write(request, tmp_path):
    """S2 (TP:1031): five writes from `L1` in a row, no hold, and no later
    write. Within open point 8's waits the lag reaches 0 and every renderer
    exits; origin carries every seq of the burst, its last included, in
    order. Fails until L4-B13 and T320 to T323."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    old = est.origin_tip()
    est.arm()
    for n in range(1, 6):
        _wrote(est.write(one, f"burst write {n}, with no later write"), f"write {n}")
    est.wait_lag_0(one, "the burst's last write")
    est.wait_renders_exit(0, "the burst's renders")
    _assert_rendered(est, old, list(range(est.n + 1, est.head() + 1)))


@pytest.mark.parametrize("fail", ["fetch", "push"])
def test_a_failed_render_shows_its_lag_and_the_next_render_catches_up(request, tmp_path, fail):
    """AT-5's failed render (TP:1134-1149): every render's `fetch` (or
    `push`) fails. After the write, open point 8's second wait: SQL holds
    the seq and `status` shows a lag of 1; `last_error` and its time are set
    by the failed pass, and `diverged_sha` stays NULL; in the push case each
    push follows a fetch, six pushes at most; and after the renderer's exit
    no pass follows it, no render's `fetch` or `push` until the next write.
    Released, the next write's render leaves both seqs on origin in order,
    and a lag of 0. Fails until L4-B13 and T320 to T323."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    old = est.origin_tip()
    est.arm([{"sub": fail, "do": "fail", "render_only": True, "where": str(one.own.clone)}])
    mark = est.entries()
    _wrote(est.write(one, f"a write whose render's {fail} fails"), "log NOTED")
    est.wait_renders_exit(mark, f"the render whose {fail} fails")
    k = est.head()
    assert k == est.n + 1 and est.origin_tip() == old, "the failed render pushed"
    assert est.lag(one) == 1, f"status does not show a lag of 1:\n{est.status(one).stdout}"
    mirror = est.mirror()
    assert mirror["last_error"] and mirror["last_error_utc"], (
        f"the failed pass recorded nothing: {mirror}")
    assert mirror["diverged_sha"] is None, f"a divergence was recorded: {mirror}"
    calls = est.render_calls(mark)
    if fail == "push":
        pushes = [i for i, c in enumerate(calls) if c["sub"] == "push"]
        assert 1 <= len(pushes) <= 6, f"{len(pushes)} pushes, not one to six"
        for i in pushes:
            assert any(c["sub"] == "fetch" for c in calls[:i]), "a push with no fetch before it"
    ended = est.entries()
    est.rearm()
    assert not [c for c in est.render_calls(ended) if c["sub"] in ("fetch", "push")], (
        "a pass followed the failed one (F15: a pass that pushed nothing ends the renderer)")
    _wrote(est.write(one, "the next write, after the release"), "the next log NOTED")
    est.wait_lag_0(one, "the next write's render")
    _assert_rendered(est, old, [k, k + 1])


def test_a_renderer_hands_over_once_after_16_passes(request, tmp_path):
    """PC-3's handover (TP:1046-1049, :1210-1215): a stream of 17 writes
    from `L1`, one per pass, each made while that pass is held at its push
    (the hold re-arms for each push). Each write waits for that pass's push
    in the wrapper's raw log, so no two writes share a pass. No renderer
    process makes more than 16 passes (a pass begins with its fetch), a
    second process follows once, and the last write reaches origin. Fails
    until L4-B13 and T320 to T323."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    old = est.origin_tip()
    fifo = est.root / "pass.fifo"
    os.mkfifo(str(fifo), 0o600)
    fd = None
    try:  # the hold, the FIFO and the renders owned to the end (`_end_held_renders`)
        est.arm([{"sub": "push", "do": "hold", "render_only": True, "fifo": str(fifo),
                  "where": str(one.own.clone)}])
        _wrote(est.write(one, "stream write 1"), "write 1")
        # Write n waits for pass n-1's push, the (n-1)-th held line in the raw
        # log (lane 3's #38, #165 6859801732). `_held_fd` alone could reopen the
        # FIFO onto the push just released, before its wrapper saw EOF: that
        # push stayed held through write n, and the next pass rendered two seqs.
        for n in range(2, 18):
            fd = _kth_held_fd(est, fifo, n - 1, f"pass {n - 1}'s push")
            _wrote(est.write(one, f"stream write {n}", timeout=120), f"write {n}")
            end, fd = fd, None
            os.close(end)  # pass n-1's push let go; the FIFO stays, for pass n's
        fd = _kth_held_fd(est, fifo, 17, "the last pass's push")
        est.rearm()
        end, fd = fd, None
        _let_go(fifo, end)  # the last push let go: the FIFO unlinked, then the write end closed
        est.wait_lag_0(one, "the stream's last write")
        est.wait_renders_exit(0, "the stream's renders")
    finally:
        _end_held_renders(est, fifo, fd, 0)
    # Each pass renders one write and pushes it once (nothing rejects here),
    # so a renderer's pushes count its passes that made progress.
    passes: dict = {}
    for call in est.render_calls(0):
        if call["sub"] == "push" and call["outcome"] == "ran":
            passes[call["renderer"]] = passes.get(call["renderer"], 0) + 1
    assert sum(passes.values()) == 17, (
        f"the 17 writes did not go out in 17 render pushes, one per pass: {passes}")
    assert passes and max(passes.values()) <= 16, f"a renderer made more than 16 passes: {passes}"
    assert len(passes) == 2, (
        f"{len(passes)} renderer processes pushed, not the first and one that follows it: "
        f"{passes}")
    _assert_rendered(est, old, list(range(est.n + 1, est.n + 18)))


def test_no_rerun_mark_is_left_and_the_last_write_is_rendered_after_a_burst(request, tmp_path):
    """D14's handshake (TP:1219-1221): after each of two bursts of 10 forks
    from `L1`, both halves of the `flock` handshake leave no
    `lanes-render.rerun`, and origin carries the last seq. Fails until
    L4-B13 and T320 to T323."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    old = est.origin_tip()
    est.arm()
    for burst in (1, 2):
        mark = est.entries()
        for n in range(1, 11):
            _wrote(est.write(one, f"burst {burst}, fork {n}"), f"burst {burst}, write {n}")
        est.wait_lag_0(one, f"burst {burst}")
        est.wait_renders_exit(mark, f"burst {burst}'s renders")
        assert not (one.own.git_dir / "lanes-render.rerun").exists(), (
            f"burst {burst} left lanes-render.rerun")
        assert est.commits_after(old)[-1][1] == [est.head()], (
            f"origin does not carry burst {burst}'s last seq {est.head()}")
    _assert_rendered(est, old, list(range(est.n + 1, est.head() + 1)))


def test_a_write_that_commits_as_the_render_lets_go_is_rendered_with_no_later_write(request,
                                                                                    tmp_path):
    """Commit I's "A write that commits as the render lets go" (TP:1084-1090,
    :1126-1133; S2's two halves of `SyncLock`'s handshake): `L1`'s first
    write forks a render, and the `psql` shim holds that render's second
    pass, one-shot, once the real `psql` has returned its read of the head,
    which holds no entry after `m`. A second write from `L1` commits and
    exits 0; its fork finds the lock held, leaves `lanes-render.rerun`, and
    exits. The case releases the shim and makes no later write: the second
    write's seq reaches origin, `status` shows a lag of 0, and no
    `lanes-render.rerun` is left. Fails until L4-B13 and T320 to T323."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    old = est.origin_tip()
    fifo = est.root / "lets-go.fifo"
    os.mkfifo(str(fifo), 0o600)
    fd, mark = None, 0
    try:  # the hold, the FIFO and the renders owned to the end (`_end_held_renders`)
        est.arm(shim_arms=[{"mode": "timer", "fifo": str(fifo),
                            "match": "FROM register_head h, register_switch s", "call": 2}])
        mark = est.entries()
        _wrote(est.write(one, "the first write; its render lets go"), "write 1")
        fd = _held_fd(fifo, "the render's second pass, after its read of the head")
        _wrote(est.write(one, "the write that commits as the render lets go", timeout=120),
               "write 2")
        assert _until(lambda: (one.own.git_dir / "lanes-render.rerun").exists(), CEILING), (
            "the second write's fork found the lock held and left no lanes-render.rerun")
        end, fd = fd, None
        _let_go(fifo, end)  # the render let go: its FIFO unlinked, then the write end closed
        est.wait_lag_0(one, "the write that commits as the render lets go")
        est.wait_renders_exit(mark, "the renders")
    finally:
        _end_held_renders(est, fifo, fd, mark)
    _assert_rendered(est, old, [est.n + 1, est.n + 2])
    assert not (one.own.git_dir / "lanes-render.rerun").exists(), "lanes-render.rerun is left"


# =================================================================== AT-C8
def test_a_render_forked_from_a_no_fetch_verb_still_renders(request, tmp_path):
    """AT-C8 (C172-184; TP:3173-3196): `log NOTED` run with
    `LANES_NO_FETCH=1` from `L1`'s checkout on a primary estate. Its render
    commit reaches origin and `status` reports a lag of 0 (open point 8's
    first wait); the wrapper's log shows the renderer's own fetch, made with
    the variable absent from its environment, and no render's call made
    with it set (D12). Fails until L4-B13 and T320 to T322."""
    est = _estate(request, tmp_path)
    one = est.checkout("L1", L1, own=True)
    old = est.origin_tip()
    est.arm()
    _wrote(est.write(one, "a write under LANES_NO_FETCH=1", env={"LANES_NO_FETCH": "1"}),
           "log NOTED under LANES_NO_FETCH=1")
    est.wait_lag_0(one, "the no-fetch write's render")
    est.wait_renders_exit(0, "the no-fetch write's render")
    _assert_rendered(est, old, [est.n + 1])
    renders = est.render_calls(0)
    fetches = [c for c in renders if c["sub"] == "fetch"]
    assert fetches and all(c["env"]["LANES_NO_FETCH"] is None for c in fetches), (
        f"the renderer made no fetch of its own with LANES_NO_FETCH absent: "
        f"{[(c['argv'], c['env']['LANES_NO_FETCH']) for c in fetches]}")
    assert not [c["argv"] for c in renders if c["env"]["LANES_NO_FETCH"] is not None], (
        "a render's git call inherited LANES_NO_FETCH")


# =================================================================== the clean-up's own faults
#: The fault-path regressions of this module's own clean-up (lane 3's Codex
#: reviews of code PR 97 at `6d479418`, SHOULDs 1, 3 and 4, at `18529e5a`,
#: BLOCKING and SHOULDs 1, 3 and 4, and at `46cac748`, BLOCKING and SHOULDs 1
#: to 7; the coordinator's reproductions, #165 6934112467, and his three
#: points, #165 6938182757). They need no engine and no task, so each has an
#: empty gate row and ordinary PR CI runs it (SHOULD 5 at `18529e5a`). Each
#: process they start is theirs: a child by its `Popen`, any other launched
#: with the case's nonce (`_with_identity`) and pinned by it (`_pin`). Each
#: case owns what it makes from its making: its variables first, then each
#: FIFO made with the `try` at once after it, whose `finally` ends every
#: process, lets each FIFO go with an abort, kills each pin and reaps each
#: child, each step tried whatever the one before it raised (`_each`;
#: SHOULD 5 at `46cac748`). No process of anyone else's is signalled:
#: `os.killpg` is stubbed where a stub child stands for a renderer, and the
#: clean-up under test signals only what it pinned by the case's identity.
#: The stand-ins and helpers these share with the rollback module's
#: (`LINUX_ONLY`, `SLEEP`, `SAY_ME`, `LEADS_A_GROUP`, `LEAVES_A_MEMBER`,
#: `_Pipe`, `_Undying`, `_with_identity`, `_fifo_reader`, `_ended`,
#: `_reap_all`, `_each`, `_GapFifo`, `_reported` and `_end_pin`) are
#: `tests/sql_register_cleanup.py`'s (round CX-34).


#: A renderer's stand-in that forks a git call into a session of its own and
#: stays. The call says who it is (`SAY_ME`), blocks on the FIFO `argv[1]` as
#: a held wrapper's call does and, let go by EOF with no abort mark, makes
#: the file `argv[2]`, as its git would run.
FORKS_A_CALL = SAY_ME + ("if os.fork() == 0:\n"
                         "    os.setsid()\n"
                         "    say_me()\n"
                         "    with open(sys.argv[1], 'rb') as fifo:\n"
                         "        said = fifo.read()\n"
                         "    if not said and not os.path.exists(sys.argv[1] + '.abort'):\n"
                         "        open(sys.argv[2], 'x').close()\n"
                         "    os._exit(0)\n"
                         "time.sleep(300)\n")

#: A write's detached fork's stand-in: a child in a session of its own that
#: says who it is (`SAY_ME`) and stays, its starter ending at once, so it is
#: no child of the case. Its argv names `argv[1]`.
DETACHES = SAY_ME + ("if os.fork() == 0:\n"
                     "    os.setsid()\n"
                     "    say_me()\n"
                     "    time.sleep(300)\n"
                     "    os._exit(0)\n")


#: THE WRAPPER'S KILL, MODELLED (lane 2's decisions 1, 2 and 7 in round
#: CX-33): `GIT_WRAPPER`'s functions, imported from the file `argv[1]` with no
#: `main()` run (its last line runs it only as a script), on the model named
#: `argv[2]`, with stand-ins for its `os`, `signal`, `select`, `time` and
#: `sys`, and for its readers of `/proc` (`stat`, `carried`): no process is
#: read or signalled. The renderer is pid 4000; 4001 and 4002 are members of
#: its group with the case's nonce; 4003 has the nonce in a group of its own;
#: 4004 is in the renderer's group without the nonce. It prints, as JSON, each
#: signal sent through a pidfd, by pid, each pidfd opened and closed, and
#: what `kill_above` raised. Round CX-34's models (lane 3's Codex review of
#: code PR 97 at `f776b435`, SHOULDs 1 and 3): `lead-gone`, the renderer gone
#: before it is pinned; `stop-never`, 4002's stop never seen; `close-error`,
#: the close of 4001's pidfd fails (EIO); `pin-raises`, the signal 0 of
#: 4002's pin is refused (EPERM). Round CX-35's model (lane 3's Codex review
#: of code PR 97 at `5a120647`, SHOULD 2): `stop-forks`, 4002's stop never
#: seen, and in that gap it forks 4005, a late member of the group, shown
#: only once 4002 has been sent SIGKILL, so only a read made after the kill
#: finds it (lane 2's pre-review RV7-35, S1).
KILL_HARNESS = r'''
import errno, importlib.util, io, json, sys
from types import SimpleNamespace

NONCE, MODEL, IDENTITY = "n0nce", sys.argv[2], sys.argv[3]
GROUP = {4000: 4000, 4001: 4000, 4002: 4000, 4003: 4003, 4004: 4000, 4005: 4000}
CARRY = {4000: NONCE, 4001: NONCE, 4002: NONCE, 4003: NONCE, 4005: NONCE}
if MODEL == "stranger-above":
    del CARRY[4000]  # the pid and start token above, but not the case's identity
sent, opened, opens, closed, now = [], {}, [], [], {"t": 0.0, "reads": {}}
gone, stops = ({4000} if MODEL == "lead-gone" else set()), set()


def listdir(path):
    if MODEL == "proc-error":
        raise OSError(errno.EIO, "a read of /proc failed")
    late = (MODEL == "late-stop" and now["reads"].get(4002, 0) >= 1) or (
        MODEL == "stop-forks" and [4002, "KILL"] in sent)
    return [str(pid) for pid in sorted(GROUP) if pid != 4005 or late] + ["self"]


def pidfd_open(pid):
    if MODEL == "member-emfile" and pid == 4002:
        raise OSError(errno.EMFILE, "Too many open files")
    if pid in gone or pid not in GROUP:
        raise ProcessLookupError(errno.ESRCH, "No such process")
    opened[100 + pid - 4000] = pid
    opens.append(pid)
    return 100 + pid - 4000


def pidfd_send_signal(fd, sig):
    pid = opened[fd]
    if sig != 0:
        sent.append([pid, sig])
    if pid in gone:
        raise ProcessLookupError(errno.ESRCH, "No such process")
    if MODEL == "pin-raises" and pid == 4002 and sig == 0:
        raise PermissionError(errno.EPERM, "Operation not permitted")
    if MODEL == "kill-refused" and pid == 4001 and sig == "KILL":
        raise PermissionError(errno.EPERM, "Operation not permitted")
    if sig == "STOP":
        stops.add(pid)
        if MODEL == "lead-ends" and pid == 4000:
            gone.add(4000)  # the leader ends once it is stopped, its members left
    elif sig == "KILL":
        gone.add(pid)


def stat(pid):
    if pid in gone or pid not in GROUP:
        return None
    reads = now["reads"][pid] = now["reads"].get(pid, 0) + (pid in stops)
    landed = pid in stops and not (MODEL == "late-stop" and pid == 4002 and reads < 2) and not (
        MODEL in ("stop-never", "stop-forks") and pid == 4002)
    return [b"T" if landed else b"S", b"1", str(GROUP[pid]).encode(), b"1"] + [b"0"] * 15 + [b"500"] + [b"0"] * 5


def select_(r, w, x, t):
    return [fd for fd in r if opened.get(fd) in gone], [], []


def sleep(seconds):
    now["t"] += seconds


def close(fd):
    closed.append(fd)
    if MODEL == "close-error" and opened[fd] == 4001:
        raise OSError(errno.EIO, "the close failed")


spec = importlib.util.spec_from_file_location("git_wrapper", sys.argv[1])
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
wrapper.os = SimpleNamespace(listdir=listdir, pidfd_open=pidfd_open, getpid=lambda: 9999,
                             close=close, environ={IDENTITY: NONCE})
wrapper.signal = SimpleNamespace(SIGSTOP="STOP", SIGKILL="KILL",
                                 pidfd_send_signal=pidfd_send_signal)
wrapper.select = SimpleNamespace(select=select_)
wrapper.time = SimpleNamespace(monotonic=lambda: now["t"], sleep=sleep)
wrapper.sys = SimpleNamespace(stderr=io.StringIO(), exit=sys.exit)
wrapper.stat = stat
wrapper.carried = CARRY.get
raised = cause = None
try:
    wrapper.kill_above(4000)
except Exception as exc:  # recorded for the case to assert
    raised = [type(exc).__name__, errno.errorcode.get(getattr(exc, "errno", None))]
    cause = None if exc.__cause__ is None else str(exc.__cause__)
print(json.dumps({"sent": sent, "opened": sorted(opens),
                  "closed": sorted(opened[fd] for fd in closed), "raised": raised,
                  "cause": cause, "said": wrapper.sys.stderr.getvalue()}))
'''


class _Stuck:
    """A child that never ends: each `communicate()` and `wait()` times
    out, and nothing ever sets its `returncode`. Its pid is never
    signalled: the cases that use it stub `os.killpg`."""

    pid = 4194304 + 7  # above Linux's pid_max ceiling, so no process has it

    def __init__(self):
        self.returncode = None
        self.stdout, self.stderr = _Pipe(), _Pipe()
        self.calls: list = []

    def communicate(self, input=None, timeout=None):
        self.calls.append("communicate")
        raise subprocess.TimeoutExpired("stuck", timeout)

    def wait(self, timeout=None):
        self.calls.append("wait")
        raise subprocess.TimeoutExpired("stuck", timeout)

    def poll(self):
        return None


def _kill_pinned(pins: list) -> None:
    """Each process a case pinned (`_reported`) ended and seen gone, its
    pidfd closed (`_end_pin`), every one tried whatever an earlier one
    raised; then the first error raised, the others named as its cause."""
    _each(*[lambda held=held: _end_pin(held) for held in pins])


def _kill_models(tmp_path: Path, *models: str) -> dict:
    """`KILL_HARNESS` run on each of `models` against this module's
    `GIT_WRAPPER`, each in a child Python of its own, bounded: {model: what
    it printed}."""
    wrapper = tmp_path / "git_wrapper.py"
    harness = tmp_path / "kill_harness.py"
    wrapper.write_text(GIT_WRAPPER, encoding="utf-8")
    harness.write_text(KILL_HARNESS, encoding="utf-8")
    found = {}
    for model in models:
        ran = subprocess.run([sys.executable, "-I", "-B", str(harness), str(wrapper), model,
                              IDENTITY],
                             capture_output=True, text=True, timeout=60, check=False)
        assert ran.returncode == 0, f"the harness failed on {model}:\n{_said(ran)}"
        found[model] = json.loads(ran.stdout)
    return found


def _killed(model: dict) -> set:
    """The pids a modelled kill sent SIGKILL to."""
    return {pid for pid, sig in model["sent"] if sig == "KILL"}


def test_end_session_raises_rather_than_return_with_its_child_unreaped(monkeypatch):
    """SHOULD 4 at `6d479418`: `_end_session`, on a child whose every
    `communicate()` and `wait()` times out, signals its group SIGTERM, then
    SIGKILL (stubbed), closes the child's pipes, waits once more, bounded,
    and then raises: it never returns with `returncode` None."""
    signals = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    stuck = _Stuck()
    with pytest.raises(RuntimeError, match="still unreaped"):
        _end_session(stuck, grace=0)
    assert signals == [(stuck.pid, signal.SIGTERM), (stuck.pid, signal.SIGKILL)], signals
    assert stuck.calls == ["communicate", "communicate", "wait"], stuck.calls
    assert stuck.stdout.closed and stuck.stderr.closed, "the child's pipes were left open"


def test_race_raises_its_clean_up_error_and_leaves_no_barrier_fifo(monkeypatch, tmp_path):
    """SHOULDs 4 and 1 at `6d479418`, `RenderEstate.race`: where a launcher
    never waits and cannot be reaped, the case fails with the clean-up's own
    error, not with the launcher left unreaped behind an assertion, and its
    barrier FIFO is gone. Stubbed: the launcher (`_Stuck`), `os.killpg`, and
    `_open_when_held`, which gives None at once."""
    signals = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(sys.modules[__name__], "_open_when_held", lambda fifo, proc: None)
    stuck = _Stuck()
    estate = SimpleNamespace(root=tmp_path, bin=tmp_path / "bin",
                             popen_render=lambda lc, conf=None, argv=None: stuck,
                             render_argv=lambda lc: ["render"])
    with pytest.raises(RuntimeError, match="still unreaped"):
        RenderEstate.race(estate, [SimpleNamespace(name="L1")])
    assert not (tmp_path / "barrier-L1.fifo").exists(), "race() left its barrier FIFO"
    assert signals and set(signals) <= {(stuck.pid, signal.SIGTERM),
                                        (stuck.pid, signal.SIGKILL)}, signals


@LINUX_ONLY
def test_a_fifo_let_go_leaves_no_reader_blocked(tmp_path):
    """SHOULD 1 at `6d479418`: `_let_go`, the owner's last release, leaves
    no reader blocked on its FIFO. With no write end held, a reader that
    comes in the gap just before the unlink is let go. With the write end
    held, as a hold site holds it, the reader already on the FIFO and one
    that comes in that gap both read EOF. Either way the FIFO is gone, and a
    reader that comes after finds none (ENOENT) and ends. Each gap reader
    must be seen on the FIFO before its unlink, so the race is exercised,
    before any exit is read: then the three readers before the release exit
    0, and only the one after it meets ENOENT (lane 3's Codex review of code
    PR 97 at `18529e5a`, SHOULD 4)."""
    fifo = tmp_path / "held.fifo"
    readers: list = []
    try:
        os.mkfifo(str(fifo), 0o600)
        first = _GapFifo(fifo, readers)
        _let_go(first)
        assert _ended(readers[0]), (
            "with no write end held, a reader that came in the gap before the unlink is left "
            "blocked on the unlinked FIFO")
        os.mkfifo(str(fifo), 0o600)
        readers.append(_fifo_reader(fifo))
        fd = _held_fd(fifo, "the reader already on the FIFO", 10)
        second = _GapFifo(fifo, readers)
        _let_go(second, fd)
        assert not fifo.exists(), "the FIFO is still there after its let-go"
        readers.append(_fifo_reader(fifo))
        left = [n for n, proc in enumerate(readers) if not _ended(proc)]
        assert not left, f"readers {left} of {len(readers)} are left blocked"
    finally:
        said = _reap_all(readers)
    assert first.on and second.on, (
        f"a gap reader was not seen on the FIFO before its unlink (first {first.on}, second "
        f"{second.on}), so the race went unexercised")
    assert [proc.returncode for proc in readers[:3]] == [0, 0, 0], (
        [proc.returncode for proc in readers], said)
    assert readers[3].returncode != 0 and "FileNotFoundError" in said[3], (
        f"a reader that came after the let-go found a FIFO: {said[3]}")


@LINUX_ONLY
def test_a_held_burst_ends_its_renders_before_its_assertion_fails(monkeypatch, tmp_path):
    """SHOULD 3 at `6d479418`: where the four forks are not seen while the
    hold stands, `_held_burst` fails only after its clean-up: the hold
    disarmed, the held call ended and never let go into its git, the FIFO
    unlinked, and the renderer the wrapper logged killed through its pidfd,
    pinned by the case's identity (SHOULDs 1 and 2 at `18529e5a`; BLOCKING
    at `46cac748`). Stubbed: the estate and its writes, and `CEILING`, 1 s;
    the held call is a FIFO reader of this case's, the renderer a child of
    this case's in a session of its own, each launched with the estate's
    nonce."""
    monkeypatch.setattr(sys.modules[__name__], "CEILING", 1.0)
    fifo = tmp_path / "held.fifo"
    held, renderers, arms, nonce = [], [], [], _nonce()
    try:
        renderers.append(subprocess.Popen(
            [sys.executable, "-I", "-c", SLEEP], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            env=_with_identity(nonce)))
        logged = [{"renderer": renderers[0].pid, "renderer_start": _stat(renderers[0].pid)["start"],
                   "sub": "push", "outcome": "held", "render": True}]

        def write(lc, text, env=None, timeout=300):
            if not held:  # the first write's render, held at its push
                held.append(_fifo_reader(fifo, _with_identity(nonce)))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        est = SimpleNamespace(root=tmp_path, bin=tmp_path / "bin", nonce=nonce,
                              origin_tip=lambda: "0" * 40, entries=lambda: 0, arm=arms.append,
                              rearm=lambda new=(): arms.append(list(new)), write=write,
                              render_calls=lambda after=0: logged)
        one = SimpleNamespace(own=SimpleNamespace(git_dir=tmp_path, clone=tmp_path))
        with pytest.raises(AssertionError, match="not at least four"):
            _held_burst(est, one)
        assert arms[-1] == [], f"the hold was not disarmed: {arms}"
        assert not fifo.exists(), "the hold FIFO is still there"
        assert held and _ended(held[0]), "the held call was not ended"
        assert _ended(renderers[0]), "the renderer was not ended"
    finally:
        _reap_all(held + renderers)
    assert renderers[0].returncode == -signal.SIGKILL, renderers[0].returncode


@LINUX_ONLY
def test_a_clean_up_signals_through_pidfds_alone_and_spares_a_wrong_start_token(monkeypatch,
                                                                                tmp_path):
    """BLOCKING at `18529e5a`: the render clean-up (`_end_renders`) signals
    only through pidfds, each pinned by the case's identity, never by a
    number or a group's id, and runs no command. A renderer that leads a
    session of its own, with a member in its group, both launched with the
    estate's nonce, is logged with its right start token; a stranger, alive
    and without the nonce, is logged with its token one tick off, as a
    process that took a logged pid would be. With `os.kill`, `os.killpg`,
    `os.getpgid`, `subprocess.run` and `subprocess.Popen` stubbed as
    recorders, the clean-up calls none of them; the renderer ends by
    SIGKILL, its member is gone, and the stranger is untouched."""
    estate = tmp_path / "estate"
    procs, pins, calls, nonce = [], [], [], _nonce()

    def recorder(name):
        def record(*args, **kwargs):
            calls.append(name)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return record

    try:
        leader = subprocess.Popen([sys.executable, "-I", "-c", LEADS_A_GROUP],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, start_new_session=True,
                                  env=_with_identity(nonce))
        procs.append(leader)
        stranger = subprocess.Popen([sys.executable, "-I", "-c", SLEEP], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(stranger)
        pins.append(_reported(leader, "the renderer's group member", nonce))
        token = int(_stat(stranger.pid)["start"])
        logged = [{"renderer": leader.pid, "renderer_start": _stat(leader.pid)["start"]},
                  {"renderer": stranger.pid, "renderer_start": str(token + 1)}]
        est = SimpleNamespace(root=estate, bin=estate / "bin", nonce=nonce,
                              render_calls=lambda after=0: logged)
        with monkeypatch.context() as stubs:
            for owner, name in ((os, "kill"), (os, "killpg"), (os, "getpgid"),
                                (subprocess, "run"), (subprocess, "Popen")):
                stubs.setattr(owner, name, recorder(f"{owner.__name__}.{name}"))
            _end_renders(est, 0, grace=2)
        assert not calls, f"the clean-up ran a command or signalled by a number: {calls}"
        assert _ended(leader) and leader.returncode == -signal.SIGKILL, (
            f"the logged renderer was not killed: {leader.returncode}")
        assert _until(pins[0].gone, 5), "the renderer's group member is still there"
        assert stranger.poll() is None, "the process logged with a wrong start token was signalled"
    finally:
        _each(lambda: _kill_pinned(pins), lambda: _reap_all(procs))


@LINUX_ONLY
def test_a_hold_clean_up_ends_a_call_forked_before_its_first_record(tmp_path):
    """SHOULD 1 at `18529e5a`: a hold site's clean-up (`_end_hold`) ends a
    call its renderer forked into a session of its own before the call made
    any record, so before the wrapper's log or its launch records name it:
    found by the case's identity, which it inherits from the renderer, and
    ended through its pidfd before the FIFO is let go, so it is never let go
    into its git. The renderer's stand-in leads a session of its own; the
    call blocks on the hold FIFO and, let go with no abort, makes the file
    `ran`, as its git would run. Its argv, its cwd and the FIFO are outside
    the estate's root, and nothing is logged, so only its identity finds
    it. The FIFO is owned from its making (SHOULD 5 at `46cac748`)."""
    estate, outside = tmp_path / "estate", tmp_path / "outside"
    estate.mkdir()
    outside.mkdir()
    fifo, ran = outside / "call.fifo", outside / "ran"
    renderer, pins, fd, nonce = None, [], None, _nonce()
    est = SimpleNamespace(root=estate, bin=estate / "bin", nonce=nonce)
    try:
        os.mkfifo(str(fifo), 0o600)
        renderer = subprocess.Popen([sys.executable, "-I", "-c", FORKS_A_CALL, str(fifo),
                                     str(ran)], cwd=str(outside), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    start_new_session=True, env=_with_identity(nonce))
        pins.append(_reported(renderer, "the call the renderer forked", nonce))
        fd = _open_when_held(fifo, renderer, 30)
        assert fd is not None, "the forked call never blocked on the hold FIFO"
        end, fd = fd, None
        _end_hold(renderer, fifo, end, est)
        assert _until(pins[0].gone, 5), "the call forked before its first record is still there"
        assert not ran.exists(), "the clean-up let the forked call go into its git"
    finally:
        _each(lambda: _quiesce(est, roots=[renderer], grace=5),
              lambda: _let_go(fifo, fd, abort=True), lambda: _kill_pinned(pins),
              lambda: _reap_all([renderer] if renderer is not None else []))


@LINUX_ONLY
def test_a_render_clean_up_ends_a_detached_render_no_log_names(tmp_path):
    """SHOULD 1 at `18529e5a`: a forked-render case's clean-up
    (`_end_held_renders`) ends a detached render that no line of the
    wrapper's log names, a write's fork that never reached its first git
    call: no child of this process, in a session of its own, found by the
    case's identity, which it inherits from the write that started it, and
    killed through its pidfd. The hold is disarmed, and the FIFO let go with
    an abort and gone. The FIFO is owned from its making (SHOULD 5 at
    `46cac748`)."""
    estate = tmp_path / "estate"
    estate.mkdir()
    fifo = estate / "held.fifo"
    arms, pins, starter, nonce = [], [], None, _nonce()
    est = SimpleNamespace(root=estate, bin=estate / "bin", nonce=nonce,
                          rearm=lambda new=(): arms.append(list(new)),
                          render_calls=lambda after=0: [])
    try:
        os.mkfifo(str(fifo), 0o600)
        starter = subprocess.Popen([sys.executable, "-I", "-c", DETACHES,
                                    str(estate / "flip" / "lanes-index")],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True,
                                   env=_with_identity(nonce))
        pins.append(_reported(starter, "the detached render", nonce))
        assert _ended(starter, 10), "the detached render's starter did not end"
        _end_held_renders(est, fifo, None, 0)
        assert _until(pins[0].gone, 5), "the detached render that no log names is still there"
        assert not fifo.exists(), "the hold FIFO is still there"
        assert arms == [[]], f"the hold was not disarmed once: {arms}"
    finally:
        _each(lambda: _quiesce(est, roots=[starter], grace=5),
              lambda: _let_go(fifo, abort=True), lambda: _kill_pinned(pins),
              lambda: _reap_all([starter] if starter is not None else []))


@LINUX_ONLY
def test_a_clean_up_raises_on_a_process_logged_with_no_start_token(tmp_path):
    """SHOULD 1 at `18529e5a`: a clean-up never skips a process it cannot
    identify. A git call's launch record (`git-wrapper.started`) and a
    renderer in the wrapper's log, each with an empty start token, make
    `_end_renders` raise (`RuntimeError`, "no start token") once the rest
    is done, where it read such a renderer as gone and returned. Their pids
    are above Linux's pid_max ceiling, so no process has them, and nothing
    is signalled."""
    estate = tmp_path / "estate"
    (estate / "bin").mkdir(parents=True)
    call, renderer = _Stuck.pid, _Stuck.pid + 1
    (estate / "bin" / "git-wrapper.started").write_text(
        json.dumps({"pid": call, "start": ""}) + "\n", encoding="utf-8")
    logged = [{"renderer": renderer, "renderer_start": "", "sub": "push", "outcome": "held",
               "render": True}]
    est = SimpleNamespace(root=estate, bin=estate / "bin", render_calls=lambda after=0: logged)
    with pytest.raises(RuntimeError, match="no start token") as raised:
        _end_renders(est, 0, grace=1)
    assert f"pid {call} " in str(raised.value) and f"pid {renderer} " in str(raised.value), (
        f"not both processes with no start token are named: {raised.value}")


@LINUX_ONLY
def test_an_abort_release_runs_neither_a_held_call_nor_a_launched_command(tmp_path):
    """SHOULD 1 at `18529e5a`: an abort release (`_let_go`'s `abort`) is not
    the success release. The real wrapper (`GIT_WRAPPER`), its call held at
    a push by its `hold` arm, and the real launcher (`LAUNCH`), each let go
    by an abort, run nothing: the wrapper's git and the launcher's command,
    each a script that makes a file, never run, and both end with 75. The
    wrapper wrote its launch record first: its pid, and the start token
    `/proc` gave it while its call was held. Both FIFOs are owned from their
    making, each let go with an abort in the `finally` (SHOULD 5 at
    `46cac748`)."""
    bin_ = tmp_path / "bin"
    made = {what: tmp_path / f"{what}.ran" for what in ("git", "command")}
    for what, path in made.items():
        _script(tmp_path / what, f"#!/bin/sh\n: > {shlex.quote(str(path))}\n")
    _script(bin_ / "git", GIT_WRAPPER)
    _script(bin_ / "launch", LAUNCH)
    held, barrier = tmp_path / "push.fifo", tmp_path / "barrier.fifo"
    (bin_ / "git-wrapper.json").write_text(json.dumps({
        "git": str(tmp_path / "git"), "redirect": {},
        "arms": [{"sub": "push", "do": "hold", "fifo": str(held)}]}), encoding="utf-8")
    procs, token, said = [], None, []
    try:
        for fifo in (held, barrier):
            os.mkfifo(str(fifo), 0o600)
        for argv in ([str(bin_ / "git"), "push", "origin", "HEAD:refs/heads/main"],
                     [str(bin_ / "launch"), str(barrier), str(tmp_path / "command")]):
            procs.append(subprocess.Popen([sys.executable, "-I", *argv], cwd=str(tmp_path),
                                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True))
        for proc, fifo in zip(procs, (held, barrier)):
            fd = _open_when_held(fifo, proc, 30)
            assert fd is not None, f"nothing was held on {fifo.name}"
            if proc is procs[0]:
                token = _stat(proc.pid)["start"]  # read while the call is held
            _let_go(fifo, fd, abort=True)
        for proc in procs:
            proc.wait(timeout=30)
    finally:
        _each(lambda: _let_go(held, abort=True), lambda: _let_go(barrier, abort=True),
              lambda: said.extend(_reap_all(procs)))
    ran = [what for what, path in made.items() if path.exists()]
    assert not ran, f"an abort release ran {ran}: {said}"
    assert [proc.returncode for proc in procs] == [75, 75], (
        [proc.returncode for proc in procs], said)
    records = _jsonl(bin_ / "git-wrapper.started")
    assert records == [{"pid": procs[0].pid, "start": token}], (
        f"the wrapper's launch record is not its pid {procs[0].pid} and start token {token}: "
        f"{records}")


@LINUX_ONLY
def test_a_held_burst_leaves_no_fifo_where_its_first_log_read_fails(tmp_path):
    """SHOULD 3 at `18529e5a`: `_held_burst` owns its FIFO from its making,
    every fallible call inside its `try`. Where the first read of the
    wrapper's log fails (`est.entries()`, stubbed to raise `OSError`), that
    error is what the case raises, the hold is disarmed and the FIFO is
    gone. Stubbed: the estate; no process is started."""
    arms = []

    def unreadable():
        raise OSError("the wrapper's log cannot be read")

    est = SimpleNamespace(root=tmp_path, bin=tmp_path / "bin", origin_tip=lambda: "0" * 40,
                          entries=unreadable, arm=arms.append,
                          rearm=lambda new=(): arms.append(list(new)),
                          render_calls=lambda after=0: [])
    one = SimpleNamespace(own=SimpleNamespace(git_dir=tmp_path, clone=tmp_path))
    with pytest.raises(OSError, match="cannot be read"):
        _held_burst(est, one)
    assert not (tmp_path / "held.fifo").exists(), (
        "_held_burst left its FIFO behind where its first read of the wrapper's log failed")
    assert arms and arms[-1] == [], f"the hold was not disarmed: {arms}"


@LINUX_ONLY
def test_a_clean_up_never_signals_a_logged_pid_and_start_token_without_the_case_s_identity(
        tmp_path):
    """BLOCKING at `46cac748` (lane 2's decision 1 in round CX-33): a process
    is never owned on its pid and start token alone, which a process that
    takes a logged pid within the same clock tick shares. A stranger without
    the case's nonce is logged as a renderer with its own pid and its own
    start token, exactly, as such a successor would match; a renderer
    launched with the nonce is logged beside it. `_end_renders` kills the
    renderer (-9) through its pidfd, never signals the stranger, which is
    still running and not stopped, and raises (`RuntimeError`) naming the
    stranger's pid as without the identity."""
    estate = tmp_path / "estate"
    procs, nonce = [], _nonce()
    try:
        renderer = subprocess.Popen([sys.executable, "-I", "-c", SLEEP],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True,
                                    env=_with_identity(nonce))
        procs.append(renderer)
        stranger = subprocess.Popen([sys.executable, "-I", "-c", SLEEP], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    start_new_session=True)
        procs.append(stranger)
        until = time.monotonic() + 5  # their environments are set only once their execs are done
        while (_carried(renderer.pid) != nonce
               or not Path(f"/proc/{stranger.pid}/environ").read_bytes()):
            assert time.monotonic() < until, "a child's environment was never set"
            time.sleep(0.005)
        logged = [{"renderer": proc.pid, "renderer_start": _stat(proc.pid)["start"]}
                  for proc in procs]
        est = SimpleNamespace(root=estate, bin=estate / "bin", nonce=nonce,
                              render_calls=lambda after=0: logged)
        with pytest.raises(RuntimeError, match="does not carry the case's identity") as raised:
            _end_renders(est, 0, grace=2)
        assert f"pid {stranger.pid} " in str(raised.value), raised.value
        assert _ended(renderer) and renderer.returncode == -signal.SIGKILL, renderer.returncode
        assert stranger.poll() is None and _stat(stranger.pid)["state"] not in ("T", "t"), (
            "the stranger with a logged pid and start token, but not the case's identity, was "
            "signalled")
    finally:
        _reap_all(procs)


@LINUX_ONLY
def test_a_clean_up_ends_each_member_of_a_group_whose_leader_is_gone(tmp_path):
    """SHOULD 1 at `46cac748` and the coordinator's point 1 (#165
    6938182757): discovery needs no live leader. A leader in a session of
    its own forks a member into its group and ends; the case reaps it, so
    no leader is left to pin, and nothing is logged. The member's argv and
    cwd are outside the estate. `_end_renders` still finds the member by
    the case's identity alone, and it is gone."""
    estate = tmp_path / "estate"
    leader, pins, nonce = None, [], _nonce()
    est = SimpleNamespace(root=estate, bin=estate / "bin", nonce=nonce,
                          render_calls=lambda after=0: [])
    try:
        leader = subprocess.Popen([sys.executable, "-I", "-c", LEAVES_A_MEMBER],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, start_new_session=True,
                                  env=_with_identity(nonce))
        pins.append(_reported(leader, "the member its leader left", nonce))
        assert _ended(leader, 10), "the leader did not end"
        _end_renders(est, 0, grace=2)
        assert _until(pins[0].gone, 5), "the member of a group whose leader is gone is still there"
    finally:
        _each(lambda: _quiesce(est, grace=5), lambda: _kill_pinned(pins),
              lambda: _reap_all([leader] if leader is not None else []))


@LINUX_ONLY
def test_a_clean_up_ends_what_it_knows_before_it_raises_an_unreadable_log(tmp_path):
    """The coordinator's point 2 (#165 6938182757): where the launch records
    cannot be read (`git-wrapper.started` is a directory, so `_logged`
    raises `IsADirectoryError`), `_quiesce` still finds and ends what it
    knows: its root, the case's child leading a session of its own, ends
    -9, and the root's group member, found by the case's identity, is gone.
    Then the log's own error is what it raises. Its `finally` first ends
    every process carrying the case's nonce (`_quiesce`, with no log to
    read), then each pin and the root (lane 3's Codex review of code PR 97
    at `f776b435`, SHOULD 5)."""
    estate = tmp_path / "estate"
    (estate / "bin" / "git-wrapper.started").mkdir(parents=True)
    root, pins, nonce = None, [], _nonce()
    est = SimpleNamespace(root=estate, bin=estate / "bin", nonce=nonce)
    owner = SimpleNamespace(root=estate, bin=tmp_path / "no-log", nonce=nonce)
    try:
        root = subprocess.Popen([sys.executable, "-I", "-c", LEADS_A_GROUP],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, start_new_session=True,
                                env=_with_identity(nonce))
        pins.append(_reported(root, "the root's group member", nonce))
        with pytest.raises(IsADirectoryError):
            _quiesce(est, roots=[root], grace=2)
        assert _ended(root) and root.returncode == -signal.SIGKILL, (
            f"the root was not ended before the log's error was raised: {root.returncode}")
        assert _until(pins[0].gone, 5), "the root's group member is still there"
    finally:
        _each(lambda: _quiesce(owner, roots=[root], grace=5), lambda: _kill_pinned(pins),
              lambda: _reap_all([root] if root is not None else []))


@LINUX_ONLY
def test_a_report_that_never_comes_ends_its_starter_and_raises(tmp_path):
    """SHOULD 2 at `46cac748`: `_reported` reads its stand-in's line under
    `select` with an absolute deadline. A stand-in that prints nothing and
    stays makes it raise within the bound, its starter ended and reaped,
    where a `readline()` with no bound waited for ever. The bound is 1 s,
    held to within a cushion of 1.5 s (lane 3's Codex review of code PR 97
    at `f776b435`, SHOULD 7)."""
    proc = subprocess.Popen([sys.executable, "-I", "-c", SLEEP], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    start = time.monotonic()
    try:
        with pytest.raises(AssertionError, match="nothing was printed"):
            _reported(proc, "the silent stand-in", _nonce(), seconds=1)
        assert 0.9 <= time.monotonic() - start < 2.5, "the bound of 1 s was not kept"
        assert proc.returncode == -signal.SIGKILL, f"its starter was not ended: {proc.returncode}"
    finally:
        _reap_all([proc])


def test_a_pinned_process_s_end_raises_unless_it_is_seen_gone():
    """SHOULD 3 at `46cac748`: `_kill_pinned` confirms each end. A pin whose
    process is never seen gone (`_Undying`) is sent SIGKILL, its pidfd is
    closed, and it raises (`RuntimeError`, "still there"), where it
    returned with the process alive. No process is signalled."""
    held = _Undying()
    with pytest.raises(RuntimeError, match="still there"):
        _kill_pinned([held])
    assert held.calls == [signal.SIGKILL, "close"], held.calls


@LINUX_ONLY
def test_reap_all_tries_every_child_and_raises_after_the_whole_set():
    """SHOULD 4 at `46cac748`: `_reap_all` tries every child. The first
    never ends (`_Stuck`, its `kill` recorded); the second is a real child
    that stays. The second is still killed and reaped (-9), the first's
    pipes are closed after its bounded waits, and only then is the first
    error raised (`subprocess.TimeoutExpired`)."""
    stuck = _Stuck()
    stuck.kill = lambda: stuck.calls.append("kill")
    child = subprocess.Popen([sys.executable, "-I", "-c", SLEEP], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            _reap_all([stuck, child])
        assert child.returncode == -signal.SIGKILL, f"the second child: {child.returncode}"
        assert stuck.calls == ["kill", "communicate", "wait"], stuck.calls
        assert stuck.stdout.closed and stuck.stderr.closed, "the first child's pipes are open"
    finally:
        if child.returncode is None:
            child.kill()
            child.wait(timeout=30)


@LINUX_ONLY
def test_a_clean_up_kills_and_closes_every_pin_whatever_a_signal_raised(monkeypatch, tmp_path):
    """SHOULD 6 at `46cac748`: each pin is registered before any signal, and
    each signal and pidfd has its own `try`. Two processes carry the case's
    nonce; the first SIGSTOP sent through a pidfd raises `PermissionError`
    (stubbed: every other call goes to the real `signal.pidfd_send_signal`).
    `_end_renders` still kills both (-9), leaves this process no more
    fds open than before, and then raises that error."""
    estate = tmp_path / "estate"
    procs, nonce, real = [], _nonce(), signal.pidfd_send_signal
    refused = []

    def first_stop_refused(fd, sig, *args):
        if sig == signal.SIGSTOP and not refused:
            refused.append(fd)
            raise PermissionError("the first SIGSTOP is refused")
        return real(fd, sig, *args)

    est = SimpleNamespace(root=estate, bin=estate / "bin", nonce=nonce,
                          render_calls=lambda after=0: [])
    try:
        for _ in range(2):
            procs.append(subprocess.Popen([sys.executable, "-I", "-c", SLEEP],
                                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, start_new_session=True,
                                          env=_with_identity(nonce)))
        until = time.monotonic() + 5  # their environments are set only once their execs are done
        while any(_carried(proc.pid) != nonce for proc in procs):
            assert time.monotonic() < until, "a child's environment never carried the nonce"
            time.sleep(0.005)
        fds = len(os.listdir("/proc/self/fd"))
        with monkeypatch.context() as stubs:
            stubs.setattr(signal, "pidfd_send_signal", first_stop_refused)
            with pytest.raises(PermissionError, match="refused"):
                _end_renders(est, 0, grace=2)
        assert refused, "no SIGSTOP was sent"
        assert [_ended(proc) and proc.returncode for proc in procs] == [-signal.SIGKILL] * 2, (
            [proc.returncode for proc in procs])
        assert len(os.listdir("/proc/self/fd")) <= fds, "a pidfd was left open"
    finally:
        _reap_all(procs)


def test_wait_renders_exit_waits_for_a_renderer_that_took_a_logged_pid_and_keeps_its_deadline(
        monkeypatch):
    """SHOULD 7 at `46cac748`: `wait_renders_exit` seeks each renderer as the
    pair of its pid and start token, and keeps its deadline on every path.
    First, a renderer still running (this process, whose pid and token
    `/proc` gives) is logged after an older record of its pid with another
    token: the older one never hides it, and the wait fails at its deadline.
    Then each read of the log names a renderer more, each already gone (a
    pid above pid_max): the wait still fails at its deadline, where it went
    on for ever. `CEILING` is 1 s, held to within a cushion of 1.5 s (lane
    3's Codex review of code PR 97 at `f776b435`, SHOULD 7); nothing is
    started or signalled."""
    monkeypatch.setattr(sys.modules[__name__], "CEILING", 1.0)
    me = os.getpid()
    live = [{"renderer": me, "renderer_start": str(int(_stat(me)["start"]) + 1)},
            {"renderer": me, "renderer_start": _stat(me)["start"]}]
    est = SimpleNamespace(render_calls=lambda after=0: live)
    with pytest.raises(pytest.fail.Exception, match=f"pids \\[{me}\\] did not exit"):
        RenderEstate.wait_renders_exit(est, 0, "the renderer that took a logged pid")
    reads = []

    def one_more(after=0):
        reads.append(len(reads))
        return [{"renderer": _Stuck.pid + n, "renderer_start": "1"} for n in range(len(reads))]

    start = time.monotonic()
    with pytest.raises(pytest.fail.Exception, match="within"):
        RenderEstate.wait_renders_exit(SimpleNamespace(render_calls=one_more), 0, "renders")
    assert 0.9 <= time.monotonic() - start < 2.5, "the deadline of 1 s was not kept"


@LINUX_ONLY
def test_a_wrapper_kill_signals_only_the_case_s_own_and_finds_each_member_without_its_leader(
        tmp_path):
    """BLOCKING and SHOULD 1 at `46cac748`, and the coordinator's point 1
    (#165 6938182757): `GIT_WRAPPER`'s `kill_above`, run on models
    (`KILL_HARNESS`), with no process read or signalled.
    - The process above has the pid and the start token, but not the case's
      identity: nothing is signalled at all.
    - The renderer ends once it is stopped, before its group is read: each
      member with the identity (4001, 4002) is still found, stopped and
      killed; 4003, in another group, and 4004, without the identity, are
      never signalled.
    - A member's stop lands late, and in that gap it forks 4005: each stop is
      seen before the next read, so 4005 is found and killed too.
    In each, every pidfd opened is closed."""
    said = _kill_models(tmp_path, "stranger-above", "lead-ends", "late-stop")
    for model, what in said.items():
        assert what["raised"] is None and what["closed"] == what["opened"], (model, what)
        assert not {pid for pid, _sig in what["sent"]} & {4003, 4004}, (model, what)
    assert said["stranger-above"]["sent"] == [], said["stranger-above"]
    assert _killed(said["lead-ends"]) == {4000, 4001, 4002}, said["lead-ends"]
    assert _killed(said["late-stop"]) == {4000, 4001, 4002, 4005}, said["late-stop"]


@LINUX_ONLY
def test_a_wrapper_kill_ends_every_target_whatever_its_discovery_or_a_kill_raised(tmp_path):
    """SHOULD 6 at `46cac748` and the coordinator's point 3 (#165
    6938182757): `GIT_WRAPPER`'s `kill_above`, run on models
    (`KILL_HARNESS`), with no process read or signalled. Where a member's
    pidfd cannot be opened (EMFILE), or a read of /proc fails (EIO), the
    renderer and each member already stopped are killed and their pidfds
    closed, and that error is raised. Where the SIGKILL through one pidfd
    is refused (EPERM), the others are still killed, every pidfd is
    closed, and that error is raised."""
    said = _kill_models(tmp_path, "member-emfile", "proc-error", "kill-refused")
    emfile, proc_error, refused = said["member-emfile"], said["proc-error"], said["kill-refused"]
    assert emfile["raised"] == ["OSError", "EMFILE"], emfile
    assert _killed(emfile) == {4000, 4001} and emfile["closed"] == [4000, 4001], emfile
    assert proc_error["raised"] == ["OSError", "EIO"], proc_error
    assert _killed(proc_error) == {4000} and proc_error["closed"] == [4000], proc_error
    assert refused["raised"] == ["PermissionError", "EPERM"], refused
    assert _killed(refused) == {4000, 4001, 4002}, refused
    assert refused["closed"] == refused["opened"], refused


#: A stand-in that prints a part of a line, with no newline, and stays.
PART_LINE = "import os, time; os.write(1, b'4194'); time.sleep(300)"


@LINUX_ONLY
def test_a_report_of_a_part_line_ends_its_starter_and_raises():
    """SHOULD 2 at `f776b435`: `_reported` reads its stand-in's line without
    blocking, in increments, under one deadline, to a newline or EOF. A
    stand-in prints a part of a line, with no newline, and stays; once that
    part can be read, `_reported` raises within its bound, 1 s, held to
    within a cushion of 1.5 s, with what came, its starter ended and reaped
    (-9), where a `readline()` after the first byte waited for ever."""
    import select
    proc = subprocess.Popen([sys.executable, "-I", "-c", PART_LINE], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([proc.stdout], [], [], 30)[0], "the stand-in printed nothing"
        start = time.monotonic()
        with pytest.raises(AssertionError, match="nothing was printed within 1 s but b'4194'"):
            _reported(proc, "the stand-in with a part of a line", _nonce(), seconds=1)
        assert 0.9 <= time.monotonic() - start < 2.5, "the bound of 1 s was not kept"
        assert proc.returncode == -signal.SIGKILL, f"its starter was not ended: {proc.returncode}"
    finally:
        _reap_all([proc])


@LINUX_ONLY
def test_a_clean_up_raises_where_a_stop_is_never_seen(monkeypatch, tmp_path):
    """SHOULD 1 at `f776b435`: a stop not seen is no stop. A process carrying
    the case's nonce is found, but each SIGSTOP sent through a pidfd is
    dropped (stubbed: every other signal goes to the real
    `signal.pidfd_send_signal`), so it is never seen stopped. `_end_renders`
    still kills it (-9), and raises (`RuntimeError`, "never seen stopped"),
    where it returned as if the estate were quiescent."""
    estate = tmp_path / "estate"
    procs, nonce, real, dropped = [], _nonce(), signal.pidfd_send_signal, []

    def stop_dropped(fd, sig, *args):
        if sig == signal.SIGSTOP:
            dropped.append(fd)
            return None
        return real(fd, sig, *args)

    est = SimpleNamespace(root=estate, bin=estate / "bin", nonce=nonce,
                          render_calls=lambda after=0: [])
    try:
        procs.append(subprocess.Popen([sys.executable, "-I", "-c", SLEEP],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, start_new_session=True,
                                      env=_with_identity(nonce)))
        until = time.monotonic() + 5  # its environment is set only once its exec is done
        while _carried(procs[0].pid) != nonce:
            assert time.monotonic() < until, "the child's environment never carried the nonce"
            time.sleep(0.005)
        with monkeypatch.context() as stubs:
            stubs.setattr(signal, "pidfd_send_signal", stop_dropped)
            with pytest.raises(RuntimeError, match="never seen stopped"):
                _end_renders(est, 0, grace=1)
        assert dropped, "no SIGSTOP was sent"
        assert _ended(procs[0]) and procs[0].returncode == -signal.SIGKILL, procs[0].returncode
    finally:
        _each(lambda: _quiesce(est, grace=5), lambda: _reap_all(procs))


@LINUX_ONLY
def test_a_clean_up_pins_again_a_pid_whose_pinned_process_is_gone():
    """SHOULD 1 at `f776b435`: a pid and start token pinned before never
    hide the process that has them now. The pin held under a live
    process's pid and start token is one whose pidfd reads as gone, as a
    process that ended, its pid then taken within the same tick, would
    leave it. `_owned` pins the live process again, by its own identity,
    and keeps the gone pin under a key of its own, to be let go."""
    nonce, proc, fresh, pinned, raised = _nonce(), None, [], {}, []
    try:
        proc = subprocess.Popen([sys.executable, "-I", "-c", SLEEP], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True, env=_with_identity(nonce))
        until = time.monotonic() + 5  # its environment is set only once its exec is done
        while _carried(proc.pid) != nonce:
            assert time.monotonic() < until, "the child's environment never carried the nonce"
            time.sleep(0.005)
        now = _stat(proc.pid)
        ended = SimpleNamespace(pid=proc.pid, start=now["start"], fd=-1,
                                gone=lambda seconds=0: True, close=lambda: None)
        pinned[(proc.pid, now["start"])] = ended
        _owned({proc.pid: now}, {nonce}, pinned, fresh)
        assert [held.pid for held in fresh] == [proc.pid], (
            "the live process with a gone pin's pid and start token was not pinned again")
        assert pinned[(proc.pid, now["start"])] is fresh[0] and ended in pinned.values(), pinned
    finally:
        _each(lambda: _release(pinned.values(), raised), lambda: _raise_first(raised),
              lambda: _reap_all([proc] if proc is not None else []))
    assert proc.returncode == -signal.SIGKILL, f"the pinned one was not ended: {proc.returncode}"


@LINUX_ONLY
def test_a_clean_up_names_a_logged_live_process_it_cannot_own(tmp_path):
    """SHOULD 8 at `f776b435`: each record is validated by itself, apart
    from the table of this user's processes a clean-up signals from. A
    renderer is logged with the pid and start token of pid 1, a live process
    this case cannot own: another user's, where the case does not run as
    root, else one without the case's identity. `_end_renders` raises
    naming it, where it passed it over; it is never signalled, as a
    clean-up signals only what it pinned from this user's processes, and
    never pid 1."""
    init = _stat(1)
    assert init is not None, "pid 1 cannot be read"
    logged = [{"renderer": 1, "renderer_start": init["start"]}]
    est = SimpleNamespace(root=tmp_path / "estate", bin=tmp_path / "estate" / "bin",
                          nonce=_nonce(), render_calls=lambda after=0: logged)
    with pytest.raises(RuntimeError, match="names pid 1 with the start token of a live process "
                                           "(that is another user's|whose environment cannot be "
                                           "read|that does not carry the case's identity)"):
        _end_renders(est, 0, grace=1)


@LINUX_ONLY
def test_a_pin_and_a_release_close_every_pidfd_whatever_a_read_or_a_close_raised(monkeypatch):
    """SHOULD 3 at `f776b435`: each pidfd has an owner from its opening.
    `_pin`, whose signal 0 is refused (`PermissionError`, stubbed), closes
    the pidfd it opened before it raises. `_release` lets each handle go
    whatever one raised: the case's process is killed (-9), seen gone and
    closed; a pin never seen gone (`_Undying`), whose close raises, is sent
    SIGKILL, is an error, and its close's error is kept. This process has no
    more fds open than before. Only the case's own child is signalled."""
    nonce, real, raised = _nonce(), signal.pidfd_send_signal, []
    child = subprocess.Popen([sys.executable, "-I", "-c", SLEEP], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, env=_with_identity(nonce))
    undying = _Undying()

    def zero_refused(fd, sig, *args):
        if sig == 0:
            raise PermissionError("the signal 0 is refused")
        return real(fd, sig, *args)

    def close_refused():
        undying.calls.append("close")
        raise OSError("the close failed")

    try:
        until = time.monotonic() + 5  # its environment is set only once its exec is done
        while _carried(child.pid) != nonce:
            assert time.monotonic() < until, "the child's environment never carried the nonce"
            time.sleep(0.005)
        fds = len(os.listdir("/proc/self/fd"))
        with monkeypatch.context() as stubs:
            stubs.setattr(signal, "pidfd_send_signal", zero_refused)
            with pytest.raises(PermissionError, match="refused"):
                _pin(child.pid, nonce)
        assert len(os.listdir("/proc/self/fd")) <= fds, "the pidfd `_pin` opened was left open"
        held = _pin(child.pid, nonce)
        assert held is not None, "the case's process could not be pinned"
        undying.close = close_refused
        _release([held, undying], raised, seconds=0.5)
        assert _ended(child) and child.returncode == -signal.SIGKILL, child.returncode
        assert undying.calls == [signal.SIGKILL, "close"], undying.calls
        assert [type(exc).__name__ for exc in raised] == ["RuntimeError", "OSError"], raised
        assert len(os.listdir("/proc/self/fd")) <= fds, "a pidfd was left open"
    finally:
        _reap_all([child])


@LINUX_ONLY
def test_a_wrapper_kill_ends_a_gone_leader_s_group_and_every_pidfd_whatever_a_stop_or_a_close_did(
        tmp_path):
    """SHOULDs 1 and 3 at `f776b435`: `GIT_WRAPPER`'s `kill_above`, run on
    models (`KILL_HARNESS`), with no process read or signalled.
    - The renderer is gone before it is pinned: its group's members with the
      identity (4001, 4002) are still found by it and the group's id, and
      killed; 4003 and 4004 are never signalled.
    - 4002's stop is never seen: every target is still killed, and it
      raises (`RuntimeError`) by the one deadline.
    - The close of 4001's pidfd fails (EIO): every other pidfd is still
      closed, and that error is raised.
    - The signal 0 of 4002's pin is refused (EPERM): its pidfd is closed,
      the targets found are killed, and that error is raised.
    In each, every pidfd opened is closed, or its close tried."""
    said = _kill_models(tmp_path, "lead-gone", "stop-never", "close-error", "pin-raises")
    for model, what in said.items():
        assert what["closed"] == what["opened"], (model, what)
        assert not {pid for pid, _sig in what["sent"]} & {4003, 4004}, (model, what)
    assert said["lead-gone"]["raised"] is None, said["lead-gone"]
    assert _killed(said["lead-gone"]) == {4001, 4002}, said["lead-gone"]
    assert said["stop-never"]["raised"] == ["RuntimeError", None], said["stop-never"]
    assert _killed(said["stop-never"]) == {4000, 4001, 4002}, said["stop-never"]
    assert said["close-error"]["raised"] == ["OSError", "EIO"], said["close-error"]
    assert _killed(said["close-error"]) == {4000, 4001, 4002}, said["close-error"]
    assert said["pin-raises"]["raised"] == ["PermissionError", "EPERM"], said["pin-raises"]
    assert _killed(said["pin-raises"]) == {4000, 4001}, said["pin-raises"]


@LINUX_ONLY
def test_a_wrapper_kill_reads_again_once_every_target_is_gone_whatever_a_stop_did(tmp_path):
    """SHOULD 2 at `5a120647`: the shared clean-up's one loop (`_Settled`),
    run by `GIT_WRAPPER`'s `kill_above` on a model (`KILL_HARNESS`), with
    no process read or signalled. 4002's stop is never seen, and in that
    gap it forks 4005, a late member of the group, which the model shows
    only once 4002 has been sent SIGKILL: no read before the kill can find
    it (lane 2's pre-review RV7-35, S1). Every target is still killed and
    seen gone, and /proc is read again after the kill, so 4005 is found by
    that read and killed too, and the stop's error is raised
    (`RuntimeError`), where that error spared the read after the kill and
    4005 was left. 4003 and 4004 are never signalled, and every pidfd
    opened is closed."""
    said = _kill_models(tmp_path, "stop-forks")["stop-forks"]
    assert said["raised"] == ["RuntimeError", None], said
    assert _killed(said) == {4000, 4001, 4002, 4005}, said
    assert said["closed"] == said["opened"], said
    assert not {pid for pid, _sig in said["sent"]} & {4003, 4004}, said


@LINUX_ONLY
def test_a_wrapper_kill_raises_its_first_error_with_every_later_one_as_its_cause(tmp_path):
    """SHOULD 2 at `bb190f7b`: `GIT_WRAPPER`'s `kill_above`, run on a model
    (`KILL_HARNESS`), with no process read or signalled. The SIGKILL
    through 4001's pidfd is refused (EPERM), so 4001 is never seen gone:
    the loop's deadline passes, and `end_all` meets the refusal again and
    4001 still there 10 s on. The first error, the refusal, is raised, and
    every later one is named in its cause (`_raise_first`), where
    `end_all` was given the first alone and the rest were lost. Every
    pidfd opened is closed, and 4003 and 4004 are never signalled."""
    said = _kill_models(tmp_path, "kill-refused")["kill-refused"]
    assert said["raised"] == ["PermissionError", "EPERM"], said
    assert "the clean-up's deadline passed" in (said["cause"] or ""), said
    assert "pid 4001 is still there 10 s after its SIGKILL" in (said["cause"] or ""), said
    assert said["closed"] == said["opened"], said
    assert not {pid for pid, _sig in said["sent"]} & {4003, 4004}, said

@LINUX_ONLY
def test_the_one_loop_reports_its_deadline_where_a_read_past_it_finds_none_new(monkeypatch):
    """SHOULD 1 at `bb190f7b`: the shared clean-up's one loop (`_Settled`)
    checks its absolute deadline right after each read, before it ends on
    one that found none new. On a modelled clock, with no process read or
    signalled: the first read finds one target, whose stop is seen; the
    next finds none new, so the target is killed, and the kill's
    confirmation ends past the deadline, 10 s on; the read after it finds
    none new. The loop reports the deadline (`RuntimeError`) and returns
    False, where that pass crossed the deadline and returned True."""
    clock, targets, reads, errors = [0.0], [], [], []

    def scan():
        reads.append(clock[0])
        if len(reads) == 1:
            targets.append(4100)
        return 1 if len(reads) == 1 else 0

    def kill(left):
        clock[0] = 11.0  # the confirmation ends past the deadline
        targets.clear()
        return []

    monkeypatch.setattr(sys.modules[_Settled.__module__], "time",
                        SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda seconds: None))
    settled = _Settled(scan, lambda by: None, kill, lambda: list(targets), 10.0, errors)
    assert settled.run() is False, errors
    assert reads == [0.0, 0.0, 11.0], reads
    assert [type(exc) for exc in errors] == [RuntimeError], errors
    assert "deadline passed" in str(errors[0]), errors
