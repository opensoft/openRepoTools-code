# SPDX-License-Identifier: Apache-2.0
"""Feature 007's AT-LRMPG, a managed PostgreSQL: its phase-N cases (T224;
FR-009, FR-053, FR-054, FR-055, FR-059) and its phase-W cases (T258; FR-009,
FR-054, FR-059) (opensoft/openRepoTools#165).

The test plan's thirteen phase-N names, byte for byte (AT-LRMPG, "Tests."),
and lane 1's two new since v3f, `dump_restore_privileges` (L1-2, T109's option
(a)) and `rotate_dump_job` (L1-3, T110's `rotate --dump-job`): 15 tests. The
phase-W cases, the logins' writes and reads through the flipped copy, are
T258's five, in the last section, "phase W (T258)", which says how they run.

THE SERVER (X, `97147aa8`, kept at Y): the register runs on CNPG, so the
admin of every case stands for the database's owner as CNPG's `initdb` makes
it, `lanes_register_admin` (lane 1's T109 name), `LOGIN CREATEROLE CREATEDB`
and no `SUPERUSER`. The cluster's own superuser stands for the provider: it
makes that admin and nothing of the register. One admin service (R-P41, lane
3's ruling on open point 41): the admin creates the register's database
first, as his own act, through his own maintenance connection, so he owns
it; every `lanes-index` step then runs through ONE service in the test's own
`$HOME/.pg_service.conf`, which names that database. `lanes-index` never
picks a database.

THE FIXTURE (AT-LRMPG, "Fixture"). Each engine case runs on a
`stoppable_cluster` of its own, since roles are global to a cluster and no
test changes a role on the session cluster; with no engine it skips with
T205's banner. Its `pg_hba.conf` takes `scram-sha-256` on the socket for
every login but the superuser and the admin, and it logs as section 5.6's
counting cluster does (`log_connections`, `log_statement=all`, each line
prefixed with its backend's pid). `bootstrap` runs with `--no-passwords`
where no password is under test, and under a pty where a password line is;
every `lanes-index login` runs under a pty, since it refuses off a terminal.
Each password line the run prints goes into a 0600 file under the test's
`$HOME/passfiles` (`passfiles-new` after a restore), which a login's
`PGPASSFILE` names. A second server, for a restore, is a `pgcluster.Cluster`
the test starts itself and destroys at its teardown.

CHECK 11 runs on section 5.6's TLS cluster, T229's `tls_cluster`, which
`tests/pgcluster.py` gives since this line merged line FX at T229d: each id
skips with T205's banner where there is no engine. What this module reads
of that fixture, from F12b's T229 text and not from a contract, is
`TlsEnvironment`'s docstring.

THE NO-ENGINE CASE is `login`'s refusals: each is refused before any
connection, so the register's fake `psql` (T203) stands in for the server and
its log shows that nothing was made. Its control, a good name under the pty,
reaches the fake, so each refusal is the condition's and never a verb this
build lacks.

READ FROM LANE 1'S CODE, NOT A CONTRACT (T109, T110 and T119 at
`l1-007-R-merge5`, `1511fa7f`): each object line is `<what>: created` or
`<what>: unchanged`, with a detail in brackets after it; a password-file line
is `*:*:<database>:<login>:<password>`; `login`'s argv is `login add|rotate
<engineer>|--dump-job --admin-service <service>`; the floors as
`pg_roles.rolconfig` holds them; and `ready`'s line form, `check <n>: ok` or
`check <n>: FAIL: <reason>`, as T218b reads it.

NO PASSWORD IN A FAILURE (T224j, T224k; Codex's review of P09 at
`f4f0ebce`, BLOCKING 3): `login add`'s, `login rotate`'s and `bootstrap`'s
stdout carry password-file lines, so `_said` and `_passwords` hide each
line's password. This module is also PYTEST_DONT_REWRITE: pytest's
assertion rewriting would add each operand's value to a failure's message,
a `CompletedProcess` with that stdout or a dict of password-file lines
among them, so an assertion here reports its own message and nothing else.
"""

from __future__ import annotations

import atexit
import contextlib
import errno
import hashlib
import itertools
import json
import os
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_helpers import (LANES_INDEX, PSQL_SHIM, PSQL_SHIM_CONTROL, PSQL_SHIM_ENDS,
                                  PSQL_SHIM_LOG, REGISTER_FAKE_PSQL, RENDER_SET_PATH, flipped_copy,
                                  guard_strip_env)
from test_sql_register_bounds import _said_safely  # the one helper for a failure's output (T258l)
from test_sql_register_bounds import _whole  # a number from output, quoting none of it (T258n)
from test_sql_register_bounds import _reported  # pytest's own report of a failure (T258r)

pytestmark = [WINDOWS_SKIP]

#: THE LANDING GATE'S TABLE (T280; task sets version 12b's rule 11,
#: opensoft/openRepoTools#165 6877673742), TEMPORARY: T281 removes it in the
#: last set. `tests/sql_register_gate.py` reads it: in a code pull request's
#: full CI, each id of a function below is skipped until every task its row
#: names has landed, and the skip names them. The rows are T224's Order
#: (tasks:2156), T230's (tasks:2220, with its As built at :2219) and T258's
#: (tasks:2464), tasks.md at lane 3's commit 17 `204145ae`. No task is common
#: to all of its functions, so there is no "*" row. T224j's, T224n's, T224o's,
#: T224p's, T258e's, T258f's, T258g's and T258h's cases, which run on synthetic text
#: and stand-ins with no database, have no row: they run ungated.
SQL_REGISTER_GATE_TABLE = {
    # T224: until L1-A7 (T109), L1-A8 (T110), L1-A17 (T119, T120) and T229.
    # Lane 1's two cases' T109 and T110, and `[in-recovery]`'s T229, are in
    # that list. T230's three check-11 ids keep check 11's row, which holds
    # their T119 (L1-A17).
    "test_bootstrap_without_a_superuser_runs_twice_with_one_catalog":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_bootstrap_refuses_a_database_its_admin_does_not_own":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_login_add_makes_an_engineers_two_logins_with_their_floors_and_prints_their_lines_once":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_login_add_run_again_puts_back_a_lost_membership_and_changes_nothing_else":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_a_member_made_without_the_login_step_carries_no_floor_and_fails_ready_check_12":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_ready_check_12_passes_the_logins_the_step_made":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_login_rotate_keeps_an_open_session_and_refuses_the_old_password":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_login_refuses_a_bad_name_a_connection_string_and_a_pipe":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_an_open_session_gets_42501_between_the_revokes_steps_then_57p01":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_the_reader_login_dumps_both_schemas_and_still_cannot_write":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_a_restore_from_the_dump_equals_its_source_with_new_passwords":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_a_restore_from_the_providers_copy_keeps_the_roles_and_takes_new_passwords":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_ready_check_11_needs_tls_and_the_primary":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_dump_restore_privileges_hold_after_roles_only_the_restore_and_bootstrap":
        ("T109", "T110", "T119", "T120", "T229"),
    "test_rotate_dump_job_changes_only_the_dump_logins_password":
        ("T109", "T110", "T119", "T120", "T229"),
    # T230: `tls_at_load` until L1-A3 (T104); its `[for-guard]` also until
    # T113, which builds the `register read` it needs (tasks:2219), and its
    # `[journal-write-id]` until T114 (L1-A12), which builds the `journal` it
    # runs (lane 1, opensoft/openRepoTools#165 6899134636; T224i).
    "test_tls_at_load_refuses_a_url_off_loopback_without_verify_full_and_a_root_file":
        ("T104",),
    "test_tls_at_load_refuses_a_url_off_loopback_without_verify_full_and_a_root_file[for-guard]":
        ("T104", "T113"),
    "test_tls_at_load_refuses_a_url_off_loopback_without_verify_full_and_a_root_file[journal-write-id]":
        ("T104", "T114"),
    # T258: until L1-A8 (T110), L4-B3 (T413, T414, T415) and L4-B5 (T417).
    "test_two_writer_logins_write_alike_and_the_log_names_each":
        ("T110", "T413", "T414", "T415", "T417"),
    "test_a_revoked_login_is_refused_69_and_writes_nothing":
        ("T110", "T413", "T414", "T415", "T417"),
    "test_a_write_cut_by_a_revoke_mid_commit_is_in_doubt_and_ends_3_with_nothing_written":
        ("T110", "T413", "T414", "T415", "T417"),
    "test_reader_url_takes_target_session_attrs_primary_not_read_write":
        ("T110", "T413", "T414", "T415", "T417"),
    "test_after_login_rotate_the_old_password_files_write_exits_69_and_the_new_lines_commit_once":
        ("T110", "T413", "T414", "T415", "T417"),
}

#: The admin, as CNPG's `initdb` makes the database's owner (lane 1's T109
#: name, opsXfactory-6's; `[X: hosting]`).
ADMIN = "lanes_register_admin"

#: Design.md section 1.4's roles.
OWNER, WRITER, READER = "lanes_register_owner", "lanes_register_writer", "lanes_register_reader"
INDEXER, DUMP = "lanes_indexer", "lanes_register_dump"
REGISTER, INDEX = "lanes_register", "lanes_index"

#: The bootstrap's inputs.
LABEL, REPOSITORY, LANE = "register-t224", "opensoft/t224-workspace", "t224-managed"

#: Each half's floors as `pg_roles.rolconfig` holds them (the login step,
#: Y:2288-2300), and as `SHOW` prints them in a session of that login.
ROLCONFIG = {"w": ["lock_timeout=2000ms", "statement_timeout=5s",
                   "idle_in_transaction_session_timeout=5s"],
             "r": ["default_transaction_read_only=on", "lock_timeout=1000ms",
                   "statement_timeout=1500ms"]}
SHOWN = {"w": {"lock_timeout": "2s", "statement_timeout": "5s",
               "idle_in_transaction_session_timeout": "5s"},
         "r": {"default_transaction_read_only": "on", "lock_timeout": "1s",
               "statement_timeout": "1500ms"}}
#: What a member made without the login step shows (lane 1's run).
NO_FLOORS = {"lock_timeout": "0", "statement_timeout": "0",
             "idle_in_transaction_session_timeout": "0", "default_transaction_read_only": "off"}

#: One object line of `bootstrap` or `login` (lane 1's `_bootstrap_say`).
OBJECT_LINE = re.compile(r"^(?P<what>[^\n]+?): (?P<state>created|unchanged)(?: \([^\n]*\))?$", re.M)
#: One password-file line (lane 1's `_register_pgpass_line`).
PASS_LINE = re.compile(r"^\*:\*:(?P<db>[^:\n]+):(?P<login>[^:\n]+):(?P<password>[^:\s]+)$", re.M)
#: One of `ready`'s check lines (T119's line form).
CHECK_LINE = re.compile(r"^check (\d+): (ok|FAIL)\b:?[ \t]*(.*)$", re.M)

#: The three database-level statements `--roles-only` runs (T109's option (a)).
DB_LEVEL = ("REVOKE ALL FROM PUBLIC", "GRANT CONNECT", "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")

#: O2's dump command, run as the dump job's login (6722541787).
DUMP_COMMAND = ("umask 077 && pg_dump --no-password --schema=lanes_register "
                "--schema=lanes_index --format=custom --file={file}")

#: The import entry's fields (T222f's form, AT-LR006's first step).
WS, AUTHOR, OPERATOR = "ws-t224", "T224 Fixture <t224@example.invalid>", "operator-t224"
MARKER_COMMIT = "c0ffee" + "4" * 34


def _said(proc: subprocess.CompletedProcess) -> str:
    """`proc` for a failure's message: its exit, each stream's counts and the
    WARNING lines that match a template, through bounds' one helper,
    `_said_safely` (T258l; lane 3's ruling 6946445277 on lane 2's pre-review
    RV9-36 of P09 at `2407ea06`, S2). Before T258l it showed both streams,
    each password-file line's password hidden (`pgcluster._masked`; T224j),
    and every other line whole. The failure messages call `_said_safely`
    themselves; this name stays for T224j's case."""
    return _said_safely(proc)


def _unverified(roles: dict) -> dict:
    """`Managed.role`'s dicts by login, for a failure's message, each without
    its `verifier`: a SCRAM verifier is derived from the login's password, so
    no message shows one (T224m)."""
    return {login: {key: value for key, value in role.items() if key != "verifier"}
            for login, role in roles.items()}


def _private(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


#: Each bounded step of ending a process this module started: `_end_process`'s
#: wait for its exit after TERM and its reap after KILL, and the join of a phase-W
#: writer's reader after them (T258e).
END_S = 10.0

#: How long a phase-W writer's reader waits on its pipes at a time, so a cut
#: reaches it (T258h).
READ_POLL_S = 0.1


def _end_process(proc: subprocess.Popen, *, group: bool, wait: float = 10.0) -> None:
    """`proc` ended and reaped, and never signalled once its pid may be another
    process's (T258e; Codex's review of P09 at `21dd3642`, SHOULD 6 in lane 3's
    numbering, by its BLOCKING's identity-safe form, as the bounds and measure
    modules' own copies have it). A process already reaped, `returncode` set,
    gets no signal. Otherwise each signal is sent while it is still unreaped, so
    its pid, and with `group` the id of the process group `start_new_session=True`
    made it lead, are still its own: TERM; up to `wait` s for its exit, watched by
    `os.waitid(..., WNOWAIT)`, which does not reap it; KILL; then one reap,
    `proc.wait(wait)`, whose `TimeoutExpired` is raised, not suppressed. A reap
    by anything else meanwhile raises `ChildProcessError` from `os.waitid`,
    before the KILL. With `group`, TERM and KILL go to the group, so a child it
    started gets them too."""
    if proc.returncode is not None:
        return
    _signal_unreaped(proc, group=group, wait=wait)
    proc.wait(wait)


def _signal_unreaped(proc: subprocess.Popen, *, group: bool, wait: float) -> None:
    """`_end_process`'s signals, and not its reap (T258f): TERM; up to `wait` s
    for `proc`'s exit, watched by `os.waitid(..., WNOWAIT)`, which leaves it
    unreaped; KILL. `proc` is unreaped throughout, so its pid, and with `group`
    the id of the group it leads, are its own for each signal. Its caller reaps
    it after, as `W258Writer` does once its reader is joined and its pipes are
    closed."""
    def send(sig: int) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            (os.killpg if group else os.kill)(proc.pid, sig)
    send(signal.SIGTERM)
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
            break
        time.sleep(0.05)
    send(signal.SIGKILL)


def _gone(pid: int, started: str) -> bool:
    """Whether the process `pid` that started at `started`, its `/proc` stat
    field 22, has ended: no process has its pid, another process has it now,
    or it is a zombie (T258f)."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except OSError:
        return True
    return fields[19] != started or fields[0] in ("Z", "X")


def _gone_by(pid: int, started: str, deadline: float) -> bool:
    """Whether the process `pid` that started at `started` is seen `_gone`
    before the monotonic `deadline`: the clock is read after each look, and
    absence counts only where that reading is still before the deadline, so
    a pause of the case past it never turns a later end into a pass (T224r;
    Codex's review of P09 at `b8f9e35a`, SHOULD 3)."""
    while True:
        gone = _gone(pid, started)
        if time.monotonic() >= deadline:
            return False
        if gone:
            return True
        time.sleep(0.05)


def _end_if_left(pid: int, started: str) -> None:
    """A case's last clean-up of a process it did not start itself, known by
    its pid and its start time (T258f): pinned by a pidfd, then killed through
    that pidfd only where the pinned process is still the one that started at
    `started`, so no other process is ever signalled."""
    try:
        pinned = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        if not _gone(pid, started):
            with contextlib.suppress(ProcessLookupError):
                signal.pidfd_send_signal(pinned, signal.SIGKILL)
    finally:
        os.close(pinned)


#: One deadline, in seconds, for all of a `_run`: its terminal or stdout pipe and
#: its stderr, read together, and then its exit; and one for a held session's
#: close (T224o).
RUN_S, CLOSE_S = 300.0, 60.0


def _drain(fds: list, deadline: float) -> tuple:
    """Each of `fds` read to its end, all of them together, until the
    monotonic `deadline` (T224o; Codex's review of P09 at `21dd3642`, SHOULD 1
    in lane 3's numbering): no read waits on one while another fills. Returns
    each fd's bytes, in order, and whether every one reached its end. A
    terminal's EIO, once no process holds its other side, is its end."""
    got = {fd: bytearray() for fd in fds}
    live = list(fds)
    while live:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        ready, _, _ = select.select(live, [], [], left)
        for fd in ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if chunk:
                got[fd] += chunk
            else:
                live.remove(fd)
    return [bytes(got[fd]) for fd in fds], not live


def _run(argv: list, env: dict, cwd: Path, *, pty_run: bool) -> subprocess.CompletedProcess:
    """`argv`, its stdout a pipe, or a terminal (`pty.openpty()`) where
    `pty_run`; its stdin is /dev/null and its stderr a pipe. All of it runs
    under one monotonic deadline, `RUN_S` (T224o; Codex's review of P09 at
    `21dd3642`, SHOULD 1 in lane 3's numbering). Through a pipe that is
    `subprocess.run`'s `timeout`. Under the terminal, the run has a session
    of its own, the terminal and stderr are read together (`_drain`), and its
    exit is reaped before the same deadline. A run that does not end by then
    raises `TimeoutExpired`, which carries no output, since a login's stdout
    holds password-file lines. On that and on any other way out unreaped, the
    run is ended with its group by `_end_process`, signalled only while it is
    unreaped, and reaped, both bounded."""
    if not pty_run:
        return subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(cwd),
                              timeout=RUN_S, stdin=subprocess.DEVNULL)
    import pty
    deadline = time.monotonic() + RUN_S
    primary, secondary = pty.openpty()
    try:
        proc = subprocess.Popen(argv, stdout=secondary, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, env=env, cwd=str(cwd),
                                start_new_session=True)
        os.close(secondary)
        secondary = -1
        try:
            (out, err), ended = _drain([primary, proc.stderr.fileno()], deadline)
            if ended:
                try:
                    proc.wait(max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    ended = False
            if not ended:
                raise subprocess.TimeoutExpired(argv, RUN_S)
        finally:
            try:
                _end_process(proc, group=True, wait=END_S)
            finally:
                proc.stderr.close()
    finally:
        os.close(primary)
        if secondary >= 0:
            os.close(secondary)
    return subprocess.CompletedProcess(argv, proc.returncode,
                                       out.decode("utf-8", "replace").replace("\r\n", "\n"),
                                       err.decode("utf-8", "replace"))


def _objects(text: str) -> list:
    """Each object line's (what, state), in order."""
    return [(m.group("what"), m.group("state")) for m in OBJECT_LINE.finditer(text)]


def _passwords(text: str) -> dict:
    """Each password-file line, by login. A login printed twice fails, its
    text masked, and the check is a bool: pytest's report of an assertion
    shows each operand's value, and `found` holds the lines (T224j)."""
    found: dict = {}
    for m in PASS_LINE.finditer(text):
        twice = m.group("login") in found
        assert not twice, (f"{m.group('login')}'s line is printed twice (_passwords is given the "
                           f"text alone, so no exit):\n{_said_safely(text, stream='stdout')}")
        found[m.group("login")] = m.group(0)
    return found


def _checks(text: str) -> dict:
    return {int(m.group(1)): (m.group(2), m.group(3) or "") for m in CHECK_LINE.finditer(text)}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Session:
    """A `psql` session of a login, held open by the test (AT-LRMPG's FIFO):
    its statements go on stdin, each followed by a `\\warn` marker, and the
    test waits for each marker on stderr, which `psql` writes unbuffered. No
    `ON_ERROR_STOP`, so a refused statement leaves the session open."""

    def __init__(self, argv: list, env: dict):
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=env)
        self.err = b""

    def send(self, sql: str, marker: str, deadline: float = 30.0) -> str:
        """`sql`, then the marker; the stderr written until the marker, or
        until `psql` ended."""
        start = len(self.err)
        try:
            self.proc.stdin.write(f"{sql}\n\\warn {marker}\n".encode("utf-8"))
            self.proc.stdin.flush()
        except BrokenPipeError:
            pass
        fd = self.proc.stderr.fileno()
        end = time.monotonic() + deadline
        while marker.encode() not in self.err[start:]:
            assert time.monotonic() < end, (
                f"psql gave no {marker!r} within {deadline:.0f} s, and has no exit, its session still open: "
                f"{_said_safely(self.err[start:], stream='stderr')!r}")
            ready, _, _ = select.select([fd], [], [], 0.2)
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                self.err += chunk
        return self.err[start:].decode("utf-8", "replace")

    def exit_now(self) -> str:
        """Its `psql`'s exit where it has ended, else that it still runs, by
        `poll()` alone, at the moment it is asked (T258s; lane 2's targeted
        check RV9-39 of P09 at `3c5b68bc`, S3: `send` returns where `psql`
        ended too, so a message that said "its session still open" could say
        the opposite of the truth)."""
        code = self.proc.poll()
        return f"its psql exit {code}" if code is not None else "no exit, its psql still running"

    def close(self) -> subprocess.CompletedProcess:
        """`psql`'s stdin closed; then its stdout and stderr read together to
        their ends (`_drain`) and its exit reaped, all under one monotonic
        deadline, `CLOSE_S` (T224o; Codex's review of P09 at `21dd3642`,
        SHOULD 1 in lane 3's numbering). A `psql` that does not end by then
        raises `TimeoutExpired`, with no output. On that and on any other way
        out unreaped, it is ended by `_end_process`, signalled only while it is
        unreaped, and reaped, both bounded."""
        deadline = time.monotonic() + CLOSE_S
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        try:
            (out, err), ended = _drain([self.proc.stdout.fileno(), self.proc.stderr.fileno()],
                                       deadline)
            self.err += err
            if ended:
                try:
                    self.proc.wait(max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    ended = False
            if not ended:
                raise subprocess.TimeoutExpired(self.proc.args, CLOSE_S)
        finally:
            try:
                _end_process(self.proc, group=False, wait=END_S)
            finally:
                self.proc.stdout.close()
                self.proc.stderr.close()
        return subprocess.CompletedProcess([], self.proc.returncode, out.decode("utf-8", "replace"),
                                           self.err.decode("utf-8", "replace"))


def _another_cluster(request, *, data_from: Path | None = None):
    """A second server for a restore: a `pgcluster.Cluster` of the test's
    own, destroyed at its teardown. With `data_from`, it starts on a copy of
    that stopped data directory, which stands for the provider's snapshot or
    point-in-time restore; otherwise it is a new cluster."""
    engine = request.getfixturevalue("pg_engine")
    import pgcluster
    cluster = pgcluster.Cluster(engine.bindir)
    request.addfinalizer(cluster.destroy)
    if data_from is None:
        cluster.start()
        return cluster
    cluster.root = Path(tempfile.mkdtemp(prefix=pgcluster.PREFIX, dir=pgcluster.SOCKET_PARENT))
    (cluster.root / "owner").write_text(f"{os.getpid()} {pgcluster._ticks(os.getpid())}\n")
    shutil.copytree(data_from, cluster.root / "data", symlinks=True)
    (cluster.root / "data").chmod(0o700)
    cluster.launch()
    return cluster


class Managed:
    """One test's managed PostgreSQL: a cluster whose superuser stands for
    the provider, the admin it made, the admin's services, and the
    `lanes-index` runs, each with the test's own `$HOME`."""

    def __init__(self, request, root: Path, *, cluster=None, scram: bool = True):
        # A CLUSTER OF THE TEST'S OWN WITH AN EMPTY TEMPLATE, as the provider's
        # new server is: T227 makes `stoppable_cluster`'s template the bootstrap,
        # with T228's logins, which would leave this admin, no superuser,
        # without ADMIN OPTION on roles it did not make (PostgreSQL 16).
        self.cluster = cluster if cluster is not None else _another_cluster(request)
        import pgcluster
        self.pgcluster = pgcluster
        self.port = int(getattr(self.cluster, "port", pgcluster.PORT))
        self.root = root
        self.home = root / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        (root / "t").mkdir(exist_ok=True)
        self.services: dict = {}
        env = guard_strip_env(os.environ, strip=("T224_", "XDG_"))
        env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(root / "config"),
                   XDG_STATE_HOME=str(root / "state"), TMPDIR=str(root / "t"),
                   LANES_WORKSTATION="Eagle", LANES_NO_GITHUB="1", LC_ALL="C",
                   PATH=os.pathsep.join([str(self.cluster.bindir),
                                         os.environ.get("PATH", os.defpath)]))
        self.env = env
        # THE PROVIDER makes the admin, CNPG's initdb owner: no SUPERUSER.
        self.cluster.psql(f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ADMIN}') THEN "
                          f"CREATE ROLE {ADMIN} LOGIN CREATEROLE CREATEDB NOSUPERUSER; END IF; END $$;")
        # SECTION 5.6'S COUNTING CLUSTER'S LOG: each connection and statement,
        # each line prefixed with its backend's pid.
        self.cluster.psql("ALTER SYSTEM SET log_connections = on;\n"
                          "ALTER SYSTEM SET log_statement = 'all';\n"
                          "ALTER SYSTEM SET log_line_prefix = '%p ';\n"
                          "SELECT pg_reload_conf();\n")
        if scram:
            # SCRAM ON THE SOCKET for every login but the provider and the admin.
            (self.cluster.root / "data" / "pg_hba.conf").write_text(
                f"local all {pgcluster.SUPERUSER} trust\nlocal all {ADMIN} trust\n"
                "local all all scram-sha-256\n", encoding="utf-8")
            self.cluster.psql("SELECT pg_reload_conf();")

    # ------------------------------------------------------------ the server
    def psql(self, sql: str, db: str = "postgres", user: str | None = None,
             check: bool = True) -> subprocess.CompletedProcess:
        """`sql` as the provider (the cluster's superuser), or as `user`
        where trust lets it in: the admin's own maintenance connection."""
        return self.cluster.psql(sql, dbname=db, user=user or self.pgcluster.SUPERUSER,
                                 check=check)

    def value(self, sql: str, db: str) -> str:
        return self.psql(sql, db).stdout.strip()

    def log(self) -> str:
        return (self.cluster.root / "server.log").read_text(encoding="utf-8", errors="replace")

    def database(self, name: str) -> str:
        """The admin's own act (R-P41): he creates the register's database
        through his maintenance connection, so he owns it, and one service
        in `~/.pg_service.conf` names it. Returns the service."""
        self.psql(f"CREATE DATABASE {name};", user=ADMIN)
        return self.service(name)

    def service(self, database: str) -> str:
        service = f"t224_{database}"
        self.services[service] = database
        _private(self.home / ".pg_service.conf", "".join(
            f"[{s}]\nhost={self.cluster.root}\nport={self.port}\nuser={ADMIN}\ndbname={d}\n\n"
            for s, d in self.services.items()))
        return service

    # ------------------------------------------------------------ lanes-index
    def lanes(self, *args: str, pty_run: bool = False,
              config: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(self.env)
        if config is not None:
            env["LANES_INDEX_CONFIG"] = str(config)
        return _run([sys.executable, str(REPO / "lanes-index"), *args], env, self.root,
                    pty_run=pty_run)

    def bootstrap(self, service: str, *flags: str, pty_run: bool = False) -> subprocess.CompletedProcess:
        args = ["bootstrap", "--admin-service", service]
        if "--roles-only" not in flags:
            args += ["--label", LABEL, "--repository", REPOSITORY, "--lane", LANE]
        return self.lanes(*args, *flags, pty_run=pty_run)

    def bootstrapped(self, service: str) -> None:
        proc = self.bootstrap(service, "--no-passwords")
        assert proc.returncode == 0, f"the bootstrap failed:\n{_said_safely(proc)}"

    def login(self, action: str, who: str, service: str, *, pty_run: bool = True) -> subprocess.CompletedProcess:
        target = ["--dump-job"] if who == DUMP else [who]
        return self.lanes("login", action, *target, "--admin-service", service, pty_run=pty_run)

    def logins(self, service: str, *engineers: str, dump: bool = True,
               folder: str = "passfiles") -> dict:
        """`login add` for each engineer, and for the dump job, under the pty:
        each printed line in its login's 0600 file. Returns the files."""
        files: dict = {}
        for who in [*engineers, *([DUMP] if dump else [])]:
            proc = self.login("add", who, service)
            assert proc.returncode == 0, f"login add {who} failed:\n{_said_safely(proc)}"
            files.update(self.passfiles(proc.stdout, folder))
        return files

    def passfiles(self, text: str, folder: str = "passfiles") -> dict:
        return {login: _private(self.home / folder / login, line + "\n")
                for login, line in _passwords(text).items()}

    # ------------------------------------------------------------ the logins
    def login_env(self, login: str, db: str, passfile: Path | None) -> dict:
        env = {k: v for k, v in self.env.items() if not k.startswith("PG")}
        env.update(PGHOST=str(self.cluster.root), PGPORT=str(self.port), PGUSER=login,
                   PGDATABASE=db, PGCONNECT_TIMEOUT="10")
        if passfile is not None:
            env["PGPASSFILE"] = str(passfile)
        return env

    def as_login(self, login: str, db: str, sql: str, passfile: Path | None,
                 **variables) -> subprocess.CompletedProcess:
        """`sql` in a new session of `login`, on the socket, with its
        password file; `VERBOSITY=verbose`, so an error carries its SQLSTATE."""
        argv = [self.cluster.tool("psql"), "-X", "-q", "-A", "-t", "-w", "-v", "ON_ERROR_STOP=1",
                "-v", "VERBOSITY=verbose"]
        for name, value in variables.items():
            argv += ["-v", f"{name}={value}"]
        return subprocess.run(argv + ["-f", "-"], input=sql, capture_output=True, text=True,
                              timeout=60, env=self.login_env(login, db, passfile), check=False)

    def session(self, login: str, db: str, passfile: Path | None) -> Session:
        argv = [self.cluster.tool("psql"), "-X", "-q", "-A", "-t", "-w", "-v", "VERBOSITY=verbose"]
        return Session(argv, self.login_env(login, db, passfile))

    def shown(self, login: str, db: str, passfile: Path | None) -> dict:
        """`SHOW` of the four floors in a session of `login`."""
        names = sorted(NO_FLOORS)
        proc = self.as_login(login, db, "".join(f"SHOW {name};\n" for name in names), passfile)
        assert proc.returncode == 0, f"{login} could not log in to SHOW its floors:\n{_said_safely(proc)}"
        return dict(zip(names, proc.stdout.split()))

    def role(self, login: str) -> dict:
        """A role's attributes, its own settings, its verifier and its groups,
        read by the provider."""
        row = self.value(
            "SELECT json_build_object('canlogin', a.rolcanlogin, 'super', a.rolsuper, "
            "'config', coalesce(r.rolconfig, '{}'), 'verifier', a.rolpassword, "
            "'groups', ARRAY(SELECT g.rolname::text FROM pg_auth_members m JOIN pg_roles g "
            "ON g.oid = m.roleid WHERE m.member = a.oid ORDER BY 1)) "
            f"FROM pg_authid a JOIN pg_roles r ON r.oid = a.oid WHERE a.rolname = '{login}';", "postgres")
        return json.loads(row) if row else {}

    # ------------------------------------------------------------ the register
    def entry(self, db: str, kind: str, path: str, text: str) -> dict:
        """An entry creating `path` with one line (T222f's form): `import` for
        `lanes/LANES.md`, AT-LR006's first step, or `cutover` for
        `lanes/STORE`."""
        clock = self.value("SELECT (clock_timestamp() + interval '60 s')::text;", db)
        journal = {"kind": kind, "verb": kind, "lane": OPERATOR, "workstation": WS,
                   "author": AUTHOR, "message": f"{kind} by {OPERATOR} (T224)"}
        if kind == "import":
            journal.update(git_commit="c" * 40, git_tree="d" * 40)
        return {"journal": journal, "not_after": clock,
                "edits": [{"ord": 1, "op": "create", "path": path},
                          {"ord": 2, "op": "append", "path": path, "new_text": text}],
                "files": [{"path": path, "present": True, "final_newline": True,
                           "sha256": _sha256((text + "\n").encode("utf-8"))}]}

    def commit(self, db: str, login: str, passfile: Path, entry: dict) -> subprocess.CompletedProcess:
        """ONE `commit_write` call as `login`, at SERIALIZABLE (T222f's form)."""
        head = self.value(f"SELECT seq FROM {REGISTER}.register_head;", db)
        client = self.value(f"SELECT version FROM {REGISTER}.schema_version;", db)
        generation = self.value(f"SELECT generation FROM {REGISTER}.register_switch;", db)
        sql = ("BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
               f"SELECT {REGISTER}.commit_write(:base, :'wid'::uuid, :client, :'gen'::uuid, "
               ":'entry'::jsonb);\nCOMMIT;\n")
        return self.as_login(login, db, sql, passfile, base=head, wid=str(uuid.uuid4()),
                             client=client, gen=generation,
                             entry=json.dumps(entry, ensure_ascii=False))

    def to_primary(self, db: str, login: str, passfile: Path) -> None:
        """AT-LR006's route on a bootstrapped database: an `import` entry, a
        `cutover` entry over it, then `record_marker`, as `login`."""
        for kind, path, text in (("import", "lanes/LANES.md", "# Lanes"),
                                 ("cutover", "lanes/STORE", "primary")):
            proc = self.commit(db, login, passfile, self.entry(db, kind, path, text))
            assert proc.returncode == 0, f"the {kind} entry did not commit:\n{_said_safely(proc)}"
        seq = self.value(f"SELECT seq FROM {REGISTER}.register_head;", db)
        client = self.value(f"SELECT version FROM {REGISTER}.schema_version;", db)
        proc = self.as_login(login, db, f"SELECT {REGISTER}.record_marker(:client, :seq, "
                             ":'commit', :'ws');\n", passfile, client=client, seq=seq,
                             commit=MARKER_COMMIT, ws=WS)
        assert proc.returncode == 0 and proc.stdout.strip() == "present", _said_safely(proc)

    def config(self, name: str, register_url: str, register_passfile: Path,
               reader_url: str, reader_passfile: Path) -> Path:
        return _private(self.root / name / "lanes-index.conf", "\n".join([
            "mode=index", f"register_url={register_url}", f"register_passfile={register_passfile}",
            f"reader_url={reader_url}", f"reader_passfile={reader_passfile}",
            f"register_label={LABEL}", ""]))

    def socket_url(self, login: str, db: str) -> str:
        return f"postgresql://{login}@{quote(str(self.cluster.root), safe='')}:{self.port}/{db}"

    def ready(self, config: Path) -> subprocess.CompletedProcess:
        return self.lanes("ready", "--expect", "index", "--release", "0.0.0-t224", "--env",
                          "t224", config=config)

    def dump(self, db: str, passfile: Path, name: str) -> tuple:
        """O2's command as the dump job's login, its connection from its
        environment and `PGPASSFILE` naming its password file."""
        target = self.root / name
        proc = subprocess.run(["bash", "-c", DUMP_COMMAND.format(file=target)],
                              capture_output=True, text=True, timeout=300,
                              env=self.login_env(DUMP, db, passfile), check=False)
        return proc, target

    def catalog(self, db: str) -> list:
        """Both schemas' catalogs: each object, its kind, its owner and its
        ACL as a set of its elements; each function's signature, owner, ACL
        and security; each default ACL; and the roles' attributes and
        memberships. One sorted list."""
        sql = f"""
SELECT json_agg(x ORDER BY x) FROM (
  SELECT format('rel %s.%s %s owner=%s acl=%s', n.nspname, c.relname, c.relkind,
                pg_get_userbyid(c.relowner),
                (SELECT string_agg(a::text, ',' ORDER BY a::text) FROM unnest(c.relacl) a)) AS x
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname IN ('{REGISTER}', '{INDEX}')
  UNION ALL
  SELECT format('fn %s.%s(%s) owner=%s secdef=%s acl=%s', n.nspname, p.proname,
                pg_get_function_identity_arguments(p.oid), pg_get_userbyid(p.proowner),
                p.prosecdef,
                (SELECT string_agg(a::text, ',' ORDER BY a::text) FROM unnest(p.proacl) a))
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname IN ('{REGISTER}', '{INDEX}')
  UNION ALL
  SELECT format('ns %s owner=%s acl=%s', n.nspname, pg_get_userbyid(n.nspowner),
                (SELECT string_agg(a::text, ',' ORDER BY a::text) FROM unnest(n.nspacl) a))
    FROM pg_namespace n WHERE n.nspname IN ('{REGISTER}', '{INDEX}')
  UNION ALL
  SELECT format('defacl %s %s %s %s', pg_get_userbyid(d.defaclrole),
                coalesce(d.defaclnamespace::regnamespace::text, '-'), d.defaclobjtype,
                (SELECT string_agg(a::text, ',' ORDER BY a::text) FROM unnest(d.defaclacl) a))
    FROM pg_default_acl d
  UNION ALL
  SELECT format('role %s login=%s super=%s createrole=%s createdb=%s config=%s', r.rolname,
                r.rolcanlogin, r.rolsuper, r.rolcreaterole, r.rolcreatedb,
                coalesce(array_to_string(r.rolconfig, ' '), '-'))
    FROM pg_roles r WHERE r.rolname LIKE 'lanes%'
  UNION ALL
  SELECT format('member %s of %s inherit=%s set=%s', pg_get_userbyid(m.member),
                pg_get_userbyid(m.roleid), m.inherit_option, m.set_option)
    FROM pg_auth_members m
   WHERE pg_get_userbyid(m.roleid) LIKE 'lanes%' OR pg_get_userbyid(m.member) LIKE 'lanes%'
) AS t(x);
"""
        return json.loads(self.value(sql, db) or "[]")

    def rows(self, db: str) -> str:
        """Both schemas' rows, table by table, each table's rows sorted."""
        tables = self.value(
            "SELECT string_agg(format('%I.%I', schemaname, tablename), ' ' ORDER BY schemaname, tablename) "
            f"FROM pg_tables WHERE schemaname IN ('{REGISTER}', '{INDEX}');", db).split()
        views = self.value(
            "SELECT string_agg(format('%I.%I', schemaname, viewname), ' ' ORDER BY schemaname, viewname) "
            f"FROM pg_views WHERE schemaname IN ('{REGISTER}', '{INDEX}');", db).split()
        return "\n".join(f"{name}: " + self.value(
            f"SELECT coalesce(json_agg(r ORDER BY r::text), '[]') FROM {name} r;", db)
            for name in tables + views)

    def connects(self, login: str, db: str, passfile: Path) -> bool:
        return self.as_login(login, db, "SELECT 1;\n", passfile).returncode == 0


def _no_clear_text(log: str, lines: dict) -> None:
    """The server's log holds each printed password only as a SCRAM
    verifier, never as clear text (O6)."""
    for login, line in lines.items():
        secret = line.rsplit(":", 1)[1]
        leaked = secret in log      # a bool, so pytest's report never shows the secret (T224j)
        assert not leaked, f"the server's log holds {login}'s password in clear text"


# ============================================================ a failure's message (T224j)
def test_a_failure_message_keeps_no_password_of_a_password_file_line():
    """T224j (Codex's review of P09 at `f4f0ebce`, BLOCKING 3; lane 3's
    ruling 6932114864): `_said` and `_passwords`' refusal of a line printed
    twice keep no password, on synthetic text alone, with no database. The
    line is built in the form of lane 1's `_register_pgpass_line`, with a
    fresh uuid as its password. Each check is a bool, so no failure of this
    case prints the password either."""
    secret = uuid.uuid4().hex
    line = ":".join(("*", "*", "t224_reg", "lanes_w_t224", secret))
    proc = subprocess.CompletedProcess([], 1, f"login lanes_w_t224: created\n{line}\n", f"{line}\n")
    said = _said(proc)
    kept = secret in said
    counted = "stdout: 2 line(s)" in said and "stderr: 1 line(s)" in said
    assert not kept and counted, "_said keeps the password, or does not count its streams' lines"
    with pytest.raises(AssertionError) as twice:
        _passwords(f"{line}\n{line}\n")
    kept = secret in str(twice.value)
    assert not kept, "_passwords' refusal of a line printed twice keeps its password"
    found = _passwords(f"{line}\n")
    read = found.get("lanes_w_t224") == line
    assert read, "_passwords no longer reads the line it is given"

    def none_printed(lines: dict) -> None:
        assert lines == {}, "a password line was printed"
    with pytest.raises(AssertionError) as failed:     # T224k: an operand that holds the line
        none_printed(found)
    kept = secret in str(failed.value)
    assert not kept, "a failed assertion whose operand holds the line reports its password"


@pytest.mark.parametrize("case", ["passwords", "no-clear-text"])
def test_pytests_own_report_of_a_password_check_shows_no_password(request, case):
    """T258r (lane 3's ruling 6949488277 on lane 2's pre-review RV9-38 of
    P09 at `3f9fcac4`, B1), with no engine and no process: T224j's checks
    fail with a password-file line's password as their frames' arguments,
    and pytest's own report of the failure, rendered as pytest renders a
    failed test under the suite's own settings (bounds' `_reported`), holds
    no password. T224j checked `str()` alone, and its "a bool, so pytest's
    report never shows the secret" held for the assert's operand, not for
    the frame's arguments, which pytest's default `--tb=auto` prints:
      - `passwords`: `_passwords(text)`, a line printed twice, where `text`
        is a login's stdout holding the line (RV9-38: managed :413);
      - `no-clear-text`: `_no_clear_text(log, lines)`, a server log that
        holds the password in clear text, where `log` and `lines` both hold
        it (RV9-38: managed :795).
    T205e's short style prints no frame's arguments. An explicit
    `--tb=long` or `--fulltrace` is not secret-safe. The password is a
    fresh uuid, no credential of any login."""
    secret = uuid.uuid4().hex
    line = ":".join(("*", "*", "t224_reg", "lanes_w_t224", secret))
    with pytest.raises(AssertionError) as failed:
        if case == "passwords":
            _passwords(f"{line}\n{line}\n")
        else:
            _no_clear_text(f"LOG:  statement: ALTER ROLE lanes_w_t224 PASSWORD '{secret}'\n",
                           {"lanes_w_t224": line})
    shown = secret in _reported(request, failed)
    assert not shown, f"[{case}] the password is in pytest's report"


# ============================================================ one deadline (T224o)
#: T224o's stand-in, run by this Python with `-I`, its mode and a mark file
#: as its arguments. Each mode reads its stdin to the end first. `full-stderr`
#: fills its stderr pipe, 256 KiB, four times a pipe's 64 KiB, before it writes
#: one line to stdout and exits 0. `hung` writes one line and waits, and a child
#: in its group holds its stdout and stderr too; it writes its pid to the mark,
#: and the child writes its pid and start time (`/proc` stat field 22) to the
#: mark's `.child`. `hung-alone` writes one line and waits, alone. Every process
#: of it ends itself by SIGALRM within 8 s, whatever is done to it.
T224O_STAND_IN = """
import os, signal, sys, time
signal.alarm(8)
mode, mark = sys.argv[1], sys.argv[2]
sys.stdin.read()
if mode == "full-stderr":
    sys.stderr.buffer.write(b"e" * 262144)
    sys.stderr.buffer.flush()
    print("done", flush=True)
    sys.exit(0)
if mode == "hung" and os.fork() == 0:
    signal.alarm(8)
    started = open("/proc/self/stat").read().rsplit(")", 1)[1].split()[19]
    open(mark + ".child", "w").write(f"{os.getpid()} {started}")
    time.sleep(8)
    os._exit(0)
open(mark, "w").write(str(os.getpid()))
print("started", flush=True)
time.sleep(8)
"""


#: T224O_STAND_IN's watchdog: each of its processes ends itself by SIGALRM this
#: many seconds after it starts (T224p).
T224O_WATCHDOG_S = 8


def _t224p_hung_run(script: Path, mark: Path, env: dict) -> tuple:
    """T224O_STAND_IN's `hung` run, its mark `mark`, under `_run`'s terminal,
    which must raise `TimeoutExpired`: the monotonic times it started and
    ended (T224p)."""
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        _run([sys.executable, "-I", str(script), "hung", str(mark)], env, mark.parent, pty_run=True)
    return start, time.monotonic()


def _t224p_child_gone_by(mark: Path, start: float) -> bool:
    """Whether the hung run's child, its pid and start time in `mark`'s
    `.child`, is gone by `RUN_S + END_S` after the run's `start` (T224p; the
    coordinator's review of P09 at `d3a2fd5c`, item 2, #165 6938473998).
    With the case's `RUN_S` of 3 s and `END_S` of 2 s that is 5 s after the
    start, at least 3 s before the child's own watchdog, `T224O_WATCHDOG_S`,
    which the child arms after its fork, after `start`: only the run's end
    can satisfy it, never the watchdog. The clock is read after each look,
    so a pause of the case past the deadline fails it (`_gone_by`; T224r)."""
    pid, started = Path(f"{mark}.child").read_text().split()
    return _gone_by(_whole(pid, "the stand-in's pid"), started, start + RUN_S + END_S)


def _t224p_end_child(mark: Path) -> None:
    """The hung run's child, if it wrote its `.child` mark, ended by pidfd
    where it is still that process (`_end_if_left`): each case's last
    clean-up, whatever its oracle found (T224p)."""
    child = Path(f"{mark}.child")
    if child.exists():
        pid, started = child.read_text().split()
        _end_if_left(_whole(pid, "the stand-in's pid"), started)


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="T224O_STAND_IN's hung run forks a child with os.fork(), the child "
                           "names itself by /proc/<pid>/stat field 22, and the case finds it "
                           "gone through /proc: Linux only (T224q)")
def test_run_reads_its_terminal_and_stderr_together_and_ends_a_run_at_its_one_deadline(
        tmp_path, monkeypatch):
    """T224o (Codex's review of P09 at `21dd3642`, SHOULD 1 in lane 3's
    numbering), no database, on T224O_STAND_IN under `_run`'s terminal. A
    run that fills its stderr pipe before it writes to its terminal ends 0
    with all of both, since neither is read only after the other ends. A run
    that does not end, with a child in its group holding both, is ended at
    `RUN_S`: `_run` raises `TimeoutExpired` within `RUN_S + END_S`, 5 s, the
    run is reaped, and its child is seen gone by that same 5 s after the run
    started, at least 3 s before the child's own 8 s watchdog, so the
    watchdog cannot pass the case (T224p; its negative control is the next
    case), nor can a pause of the case past those 5 s (T224r; Codex's review
    of P09 at `b8f9e35a`, SHOULD 3). The child is ended in a finally whatever happened. It runs on Linux
    alone: the stand-in's child comes of `os.fork()` and names itself by
    `/proc/<pid>/stat`, which the oracle reads too (T224q; Codex's review of
    P09 at `d3a2fd5c`, SHOULD 5)."""
    monkeypatch.setitem(globals(), "RUN_S", 3.0)
    monkeypatch.setitem(globals(), "END_S", 2.0)
    script = _private(tmp_path / "stand_in.py", T224O_STAND_IN)
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    full = _run([sys.executable, "-I", str(script), "full-stderr", str(tmp_path / "full")], env,
                tmp_path, pty_run=True)
    said = (full.returncode, full.stdout, len(full.stderr))
    assert said == (0, "done\n", 262144), (
        f"a run that filled its stderr pipe ended {said[0]}, with {said[2]} bytes of stderr, "
        f"not 0 with 262144")
    mark = tmp_path / "hung"
    try:
        start, ended = _t224p_hung_run(script, mark, env)
        took = ended - start
        assert took < RUN_S + END_S, (      # T224r: `_run` itself ends within 5 s
            f"_run ended a hung run after {took:.1f} s, past its {RUN_S + END_S:.0f} s bound")
        try:
            os.waitid(os.P_PID, _whole(mark.read_text(), "the hung run's pid"), os.WEXITED | os.WNOHANG | os.WNOWAIT)
            reaped = False
        except ChildProcessError:
            reaped = True
        assert reaped, "_run did not reap the hung run it ended"
        gone = _t224p_child_gone_by(mark, start)
        assert gone, (f"the hung run's child, in its group, was not gone {RUN_S + END_S:.0f} s "
                      f"after the run started, {T224O_WATCHDOG_S - RUN_S - END_S:.0f} s before "
                      f"its own watchdog")
    finally:
        _t224p_end_child(mark)


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="T224p's oracle reads Linux's /proc and its clean-up pins by a pidfd")
def test_a_leader_only_end_of_a_hung_run_leaves_its_child_and_the_absence_oracle_fails(
        tmp_path, monkeypatch):
    """T224p (the coordinator's review of P09 at `d3a2fd5c`, item 2, #165
    6938473998), no database: the negative control of the case above. Here
    `_run`'s clean-up ends the hung run's leader alone, `_end_process` with
    `group=False`, so its child, in its group, is not ended; the oracle,
    `_t224p_child_gone_by`, must then find it still there at its deadline,
    which comes at least 3 s before the child's own watchdog. Were the
    watchdog able to satisfy the oracle, as the 5 s wait after `_run`'s end
    before T224p let it, this case would fail. The child is ended in a
    finally, by pidfd."""
    monkeypatch.setitem(globals(), "RUN_S", 3.0)
    monkeypatch.setitem(globals(), "END_S", 2.0)
    group_end = _end_process
    monkeypatch.setitem(globals(), "_end_process",
                        lambda proc, *, group, wait=10.0: group_end(proc, group=False, wait=wait))
    script = _private(tmp_path / "stand_in.py", T224O_STAND_IN)
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    mark = tmp_path / "hung"
    try:
        start, _ = _t224p_hung_run(script, mark, env)
        gone = _t224p_child_gone_by(mark, start)
        assert not gone, ("with the leader alone ended, the hung run's child was gone by the "
                          "oracle's deadline: the oracle does not tell a group's end from a "
                          "leader's")
    finally:
        _t224p_end_child(mark)


def test_a_held_sessions_close_reads_both_pipes_together_and_ends_it_at_its_one_deadline(
        tmp_path, monkeypatch):
    """T224o (Codex's review of P09 at `21dd3642`, SHOULD 1 in lane 3's
    numbering), no database, on T224O_STAND_IN as a held session's `psql`.
    One that fills its stderr pipe before it writes its stdout closes with 0
    and all of both. One that does not end once its stdin is closed is ended
    at `CLOSE_S`: `close` raises `TimeoutExpired` within its bounds, and the
    process is reaped."""
    monkeypatch.setitem(globals(), "CLOSE_S", 3.0)
    monkeypatch.setitem(globals(), "END_S", 2.0)
    script = _private(tmp_path / "stand_in.py", T224O_STAND_IN)
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    full = Session([sys.executable, "-I", str(script), "full-stderr", str(tmp_path / "full")],
                   env).close()
    said = (full.returncode, full.stdout, len(full.stderr))
    assert said == (0, "done\n", 262144), (
        f"a session that filled its stderr pipe closed with {said[0]}, with {said[2]} bytes of "
        f"stderr, not 0 with 262144")
    held = Session([sys.executable, "-I", str(script), "hung-alone", str(tmp_path / "hung")], env)
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        held.close()
    took = time.monotonic() - start
    assert took < 3.0 + 2 * 2.0 + 1.5, f"close ended a hung session after {took:.1f} s, past its bounds"
    assert held.proc.returncode is not None, "close did not reap the hung session it ended"


# ============================================================ the bootstrap
def test_bootstrap_without_a_superuser_runs_twice_with_one_catalog(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    first = m.bootstrap(service, "--no-passwords")
    assert first.returncode == 0, f"the first bootstrap, as {ADMIN}, failed:\n{_said_safely(first)}"
    assert m.role(ADMIN)["super"] is False, f"{ADMIN} is a superuser: the case proves nothing"
    catalog = m.catalog("t224_reg")
    second = m.bootstrap(service, "--no-passwords")
    assert second.returncode == 0, f"the second bootstrap failed:\n{_said_safely(second)}"
    states = {state for _what, state in _objects(second.stdout)}
    assert states == {"unchanged"}, f"the second run changed something:\n{_said_safely(second)}"
    assert m.catalog("t224_reg") == catalog, "the second run changed the catalog"
    # A SECURITY DEFINER function owned by a role that cannot log in works:
    # `commit_write`, as a writer login, commits an import entry.
    files = m.logins(service, "e1", dump=False)
    proc = m.commit("t224_reg", "lanes_w_e1", files["lanes_w_e1"],
                    m.entry("t224_reg", "import", "lanes/LANES.md", "# Lanes"))
    assert proc.returncode == 0, f"commit_write as lanes_w_e1 did not commit:\n{_said_safely(proc)}"
    head = m.value(f"SELECT seq FROM {REGISTER}.register_head;", "t224_reg")
    assert head == "0", f"the import as lanes_w_e1 left the register's head at {head!r}, not 0"


def test_bootstrap_refuses_a_database_its_admin_does_not_own(tmp_path, request):
    m = Managed(request, tmp_path)
    m.psql("CREATE DATABASE t224_theirs;")                  # the provider's, not the admin's
    service = m.service("t224_theirs")
    acl = m.value("SELECT coalesce(datacl, acldefault('d', datdba))::text FROM pg_database "
                  "WHERE datname = 't224_theirs';", "postgres")
    proc = m.bootstrap(service, "--no-passwords")
    assert proc.returncode == 2, f"bootstrap on a database its admin does not own is not 2:\n{_said_safely(proc)}"
    assert m.value(f"SELECT count(*) FROM pg_namespace WHERE nspname = '{REGISTER}';",
                   "t224_theirs") == "0", "the refused bootstrap made the register's schema"
    # THE CONTROL: there, as that admin, the database-level REVOKE and GRANT
    # only warn, 01006 and 01007, and `datacl` is unchanged.
    warned = m.psql("\\set VERBOSITY verbose\nREVOKE ALL ON DATABASE t224_theirs FROM PUBLIC;\n"
                    f"GRANT CONNECT ON DATABASE t224_theirs TO {ADMIN};\n", user=ADMIN)
    assert "01006" in warned.stderr and "01007" in warned.stderr, _said_safely(warned)
    kept = m.value("SELECT coalesce(datacl, acldefault('d', datdba))::text FROM pg_database "
                   "WHERE datname = 't224_theirs';", "postgres")
    assert kept == acl, f"the warned REVOKE and GRANT changed t224_theirs's datacl: {acl} -> {kept}"


# ============================================================ the login step
def test_login_add_makes_an_engineers_two_logins_with_their_floors_and_prints_their_lines_once(
        tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    proc = m.login("add", "e1", service)
    assert proc.returncode == 0, f"login add e1 failed:\n{_said_safely(proc)}"
    lines = _passwords(proc.stdout)
    assert sorted(lines) == ["lanes_r_e1", "lanes_w_e1"], _said_safely(proc)
    for key, login in (("register_url=", "lanes_w_e1"), ("reader_url=", "lanes_r_e1")):
        urls = [line for line in proc.stdout.splitlines() if line.startswith(key)]
        assert len(urls) == 1 and f"//{login}@" in urls[0], f"no one {key} line for {login}"
    files = m.passfiles(proc.stdout)
    for login, half, group in (("lanes_w_e1", "w", WRITER), ("lanes_r_e1", "r", READER)):
        role = m.role(login)
        assert role["canlogin"] and role["groups"] == [group], _unverified({login: role})
        assert sorted(role["config"]) == sorted(ROLCONFIG[half]), (login, role["config"])
        assert role["verifier"].startswith("SCRAM-SHA-256$"), f"{login}'s password is not SCRAM"
        floors = {k: v for k, v in m.shown(login, "t224_reg", files[login]).items() if k in SHOWN[half]}
        assert floors == SHOWN[half], f"{login} shows the floors {floors}, not {SHOWN[half]}"
    _no_clear_text(m.log(), lines)
    # THE DUMP JOB: `lanes_register_dump`, a member of READER alone, with the
    # reader's floors, and its one line.
    dump = m.login("add", DUMP, service)
    assert dump.returncode == 0, f"login add --dump-job failed:\n{_said_safely(dump)}"
    assert sorted(_passwords(dump.stdout)) == [DUMP], _said_safely(dump)
    role = m.role(DUMP)
    assert role["groups"] == [READER] and sorted(role["config"]) == sorted(ROLCONFIG["r"]), (
        _unverified({DUMP: role}))
    _no_clear_text(m.log(), _passwords(dump.stdout))


def test_login_add_run_again_puts_back_a_lost_membership_and_changes_nothing_else(
        tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    m.logins(service, "e1", dump=False)
    before = {login: m.role(login) for login in ("lanes_w_e1", "lanes_r_e1")}
    m.psql(f"REVOKE {WRITER} FROM lanes_w_e1 GRANTED BY {ADMIN};")
    assert m.role("lanes_w_e1")["groups"] == [], "the membership was not revoked by hand"
    again = m.login("add", "e1", service)
    assert again.returncode == 0, f"login add e1, run again, failed:\n{_said_safely(again)}"
    printed = sorted(_passwords(again.stdout))     # the logins alone, as pytest reports it (T224j)
    assert printed == [], f"the rerun printed a password line:\n{_said_safely(again)}"
    after = {login: m.role(login) for login in ("lanes_w_e1", "lanes_r_e1")}
    assert after == before, (
        f"the rerun changed more than the membership: {_unverified(before)} -> {_unverified(after)}; "
        f"verifier changed for {sorted(k for k in before if after[k].get('verifier') != before[k].get('verifier'))}")


def test_a_member_made_without_the_login_step_carries_no_floor_and_fails_ready_check_12(
        tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    files = m.logins(service, "e1", dump=False)
    bare = {}
    for login, group in (("lanes_w_bare", WRITER), ("lanes_r_bare", READER)):
        password = uuid.uuid4().hex
        m.psql(f"CREATE ROLE {login} LOGIN PASSWORD '{password}';\nGRANT {group} TO {login};\n")
        bare[login] = _private(m.home / "passfiles" / login, f"*:*:t224_reg:{login}:{password}\n")
        assert m.shown(login, "t224_reg", bare[login]) == NO_FLOORS, login
    config = m.config("bare", m.socket_url("lanes_w_bare", "t224_reg"), bare["lanes_w_bare"],
                      m.socket_url("lanes_r_e1", "t224_reg"), files["lanes_r_e1"])
    proc = m.ready(config)
    state, reason = _checks(proc.stdout).get(12, ("", ""))
    assert proc.returncode == 2 and state == "FAIL", f"check 12 does not fail:\n{_said_safely(proc)}"
    assert "lanes_w_bare" in reason, f"check 12 does not name the login:\n{_said_safely(proc)}"
    for floor in ROLCONFIG["w"]:
        assert floor.split("=", 1)[0] in reason, f"check 12 does not name {floor}:\n{_said_safely(proc)}"


def test_ready_check_12_passes_the_logins_the_step_made(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    files = m.logins(service, "e1", dump=False)
    config = m.config("e1", m.socket_url("lanes_w_e1", "t224_reg"), files["lanes_w_e1"],
                      m.socket_url("lanes_r_e1", "t224_reg"), files["lanes_r_e1"])
    proc = m.ready(config)
    checks = _checks(proc.stdout)
    state, _reason = checks.get(12, ("", ""))
    assert state == "ok", f"check 12 fails the logins the step made:\n{_said_safely(proc)}"
    # "check 12 passes, `check 12: ok`" (lane 3's batch 7, ruling 1: lane 1's
    # bare line stands, Y-ops:457; tasks:572): the line is bare, with no floor.
    assert re.search(r"^check 12: ok$", proc.stdout, re.M), (
        f"check 12's line is not the bare `check 12: ok`:\n{_said_safely(proc)}")
    # Exit 0 where every check passes. On this socket fixture not every check
    # can (check 11 always fails on a Unix socket, AT-LRMPG's own
    # `[unix-socket]`), so the run's exit follows the other checks: 2, with
    # check 12 not among the failures `ready` names.
    failed = sorted(number for number, (said, _why) in checks.items() if said == "FAIL")
    assert proc.returncode == (2 if failed else 0), (
        f"ready's exit does not follow its checks ({failed} failed):\n{_said_safely(proc)}")
    assert 12 not in failed, f"check 12 is among the checks ready fails: {failed}"
    # Check 11 fails on this case's Unix socket by TP:5382-5384's own oracle
    # (`[unix-socket]`), so the exit's 2 arm is always the one exercised
    # (lane 3's batch 11 (3), its optional assertion).
    assert 11 in failed, (
        f"check 11 does not fail on this case's Unix socket, so the exit's 2 arm is not "
        f"exercised:\n{_said_safely(proc)}")


def test_login_rotate_keeps_an_open_session_and_refuses_the_old_password(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    old = m.logins(service, "e1", dump=False)
    held = m.session("lanes_w_e1", "t224_reg", old["lanes_w_e1"])
    assert "ERROR" not in held.send("SELECT 'before';", "t224-before"), "the session did not open"
    proc = m.login("rotate", "e1", service)
    assert proc.returncode == 0, f"login rotate e1 failed:\n{_said_safely(proc)}"
    new = m.passfiles(proc.stdout, "passfiles-new")
    assert sorted(new) == ["lanes_r_e1", "lanes_w_e1"], _said_safely(proc)
    answered = held.send("SELECT 'after';", "t224-after")
    assert "ERROR" not in answered, (f"the session open across the rotation got an error ({held.exit_now()}):"
                                     f"\n{_said_safely(answered, stream='stderr')}")
    ended = held.close()
    assert ended.returncode == 0 and ended.stdout.split() == ["before", "after"], (
        f"the session open across the rotation did not go on:\n{_said_safely(ended)}")
    for login in ("lanes_w_e1", "lanes_r_e1"):
        refused = m.as_login(login, "t224_reg", "SELECT 1;\n", old[login])
        assert refused.returncode == 2 and "password authentication failed" in refused.stderr, (
            f"{login}'s old password file is not refused at login:\n{_said_safely(refused)}")
        assert m.connects(login, "t224_reg", new[login]), f"{login}'s new line does not connect"
    _no_clear_text(m.log(), _passwords(proc.stdout))


#: `login`'s refusals: each argv, and whether it runs under the pty.
LOGIN_REFUSALS = {
    "name": [["login", "add", name, "--admin-service", "t224_admin"]
             for name in ("E1", "1e", "e" * 42)],
    "connection-string": [["login", "add", "e1", "--admin-service", value]
                          for value in ("host=/tmp port=5432 dbname=register_db",
                                        "postgresql://lanes_register_admin@127.0.0.1/register_db")],
    "pipe": [["login", "add", "e1", "--admin-service", "t224_admin"]],
}


class LoginBench:
    """FP: the register's fake `psql` first on `PATH`, logging every call, a
    service file naming a loopback admin, and the test's own `$HOME`."""

    def __init__(self, root: Path):
        self.root = root
        fakebin = root / "fakebin"
        fakebin.mkdir(parents=True)
        (fakebin / "psql").write_text(REGISTER_FAKE_PSQL, encoding="utf-8")
        (fakebin / "psql").chmod(0o755)
        self.log = root / "psql.log"
        home = root / "home"
        home.mkdir()
        (root / "t").mkdir()
        _private(home / ".pg_service.conf", f"[t224_admin]\nhost=127.0.0.1\nport=55432\n"
                                            f"user={ADMIN}\ndbname=register_db\n")
        env = guard_strip_env(os.environ, strip=("T224_", "XDG_"))
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(root / "config"),
                   XDG_STATE_HOME=str(root / "state"), TMPDIR=str(root / "t"),
                   LANES_WORKSTATION="Eagle", LANES_NO_GITHUB="1", FAKE_PSQL_LOG=str(self.log),
                   PATH=os.pathsep.join([str(fakebin), os.environ.get("PATH", os.defpath)]))
        self.env = env

    def run(self, argv: list, *, pty_run: bool) -> subprocess.CompletedProcess:
        return _run([sys.executable, str(REPO / "lanes-index"), *argv], self.env, self.root,
                    pty_run=pty_run)

    def requests(self) -> list:
        if not self.log.exists():
            return []
        entries = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()
                   if line]
        return [entry for entry in entries if entry.get("kind") != "version"]


def _making(entries: list) -> list:
    return [entry for entry in entries
            if re.search(r"\b(CREATE|GRANT|ALTER)\b", entry.get("stdin", ""))]


@pytest.mark.parametrize("case", list(LOGIN_REFUSALS))
def test_login_refuses_a_bad_name_a_connection_string_and_a_pipe(tmp_path, case):
    bench = LoginBench(tmp_path)
    for argv in LOGIN_REFUSALS[case]:
        proc = bench.run(argv, pty_run=(case != "pipe"))
        assert proc.returncode == 2, f"[{case}] {argv[1:3]} is not refused with 2:\n{_said_safely(proc)}"
        assert _making(bench.requests()) == [], f"[{case}] the refused login sent a making statement"
        for value in argv:
            if "=" in value or "://" in value:
                assert value not in proc.stdout + proc.stderr, f"[{case}] the refusal echoed {value}"
    # THE CONTROL: a good name, under the pty, gets past every refusal and
    # reaches the admin service (the fake), so each refusal was the case's.
    control = bench.run(["login", "add", "e1", "--admin-service", "t224_admin"], pty_run=True)
    assert bench.requests(), (
        f"[{case}] the control, a good name under a terminal, sent nothing:\n{_said_safely(control)}")


# ============================================================ the revoke
def test_an_open_session_gets_42501_between_the_revokes_steps_then_57p01(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    files = m.logins(service, "e1", "e2", dump=False)
    held = m.session("lanes_w_e2", "t224_reg", files["lanes_w_e2"])
    opened = held.send("SELECT 1;", "t224-open")
    assert "ERROR" not in opened, (f"e2's session did not open ({held.exit_now()}):"
                                   f"\n{_said_safely(opened, stream='stderr')}")
    # [steps-by-hand]: the revoke block's steps 1 and 2, by the admin.
    m.psql(f"ALTER ROLE lanes_w_e2 NOLOGIN;\nREVOKE {WRITER} FROM lanes_w_e2;\n", "t224_reg",
           user=ADMIN)
    write = held.send(f"SELECT {REGISTER}.commit_write(NULL, NULL, NULL, NULL, NULL);",
                      "t224-write")
    read = held.send(f"SELECT seq FROM {REGISTER}.register_head;", "t224-read")
    for what, said in (("write", write), ("read", read)):
        assert "42501" in said and f"permission denied for schema {REGISTER}" in said, (
            f"the open session's {what} between steps 2 and 3 is not 42501 ({held.exit_now()}): "
            f"{_said_safely(said, stream='stderr')}")
    # Step 3 by hand: its sessions ended.
    m.psql("GRANT lanes_w_e2 TO CURRENT_USER WITH INHERIT TRUE, SET FALSE;\n"
           "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = 'lanes_w_e2';\n"
           "REVOKE lanes_w_e2 FROM CURRENT_USER;\n", "t224_reg", user=ADMIN)
    after = held.send(f"SELECT seq FROM {REGISTER}.register_head;", "t224-after")
    ended = held.close()
    said = after + ended.stderr
    assert "57P01" in said or "terminating connection due to administrator command" in said or \
        "server closed the connection" in said, (
            f"the next statement after step 3 was answered: its stderr then and at its end, "
            f"{_said_safely(said, stream='stderr')}; its end, {_said_safely(ended)}")
    assert "permission denied" not in after, (f"after step 3 a statement got 42501, not 57P01: "
                                              f"{_said_safely(after, stream='stderr')}; its end, "
                                              f"{_said_safely(ended)}")
    assert m.connects("lanes_w_e1", "t224_reg", files["lanes_w_e1"]), "e1 can no longer log in"


# ============================================================ the dump
def test_the_reader_login_dumps_both_schemas_and_still_cannot_write(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    files = m.logins(service, "e1")
    proc = m.commit("t224_reg", "lanes_w_e1", files["lanes_w_e1"],
                    m.entry("t224_reg", "import", "lanes/LANES.md", "# Lanes"))
    assert proc.returncode == 0, _said_safely(proc)
    # The indexer's store, made as the indexer (`lanes-index`'s own #160
    # scripts are not run here: see the report), with a row.
    m.psql(f"SET ROLE {INDEXER};\nCREATE TABLE {INDEX}.t224_rows (id int PRIMARY KEY);\n"
           f"INSERT INTO {INDEX}.t224_rows VALUES (1);\n", "t224_reg")
    dumped, target = m.dump("t224_reg", files[DUMP], "first.dump")
    assert dumped.returncode == 0, f"the dump job's dump failed:\n{_said_safely(dumped)}"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600, "the dump file is not 0600"
    listing = subprocess.run([m.cluster.tool("pg_restore"), "--list", str(target)],
                             capture_output=True, text=True, timeout=120, check=False).stdout
    for name in m.value("SELECT string_agg(schemaname || ' ' || tablename, ',') FROM pg_tables "
                        f"WHERE schemaname IN ('{REGISTER}', '{INDEX}');", "t224_reg").split(","):
        schema, table = name.split()
        assert re.search(rf"TABLE {schema} {table}\b", listing), f"the dump lacks {name}"
    restored = subprocess.run([m.cluster.tool("pg_restore"), "--data-only", f"--schema={REGISTER}",
                               "--table=register_head", "--file=-", str(target)],
                              capture_output=True, text=True, timeout=120, check=False)
    head = restored.stdout
    b = m.value(f"SELECT seq FROM {REGISTER}.register_head;", "t224_reg")
    assert re.search(rf"^1\t{b}\b", head, re.M) or re.search(rf"\t{b}\b", head), (
        f"the dump's register_head does not give the head {b}: pg_restore's "
        f"{_said_safely(restored)}")
    # M6: a sequence the indexer makes later is dumped, by the default privilege.
    m.psql(f"SET ROLE {INDEXER};\nCREATE SEQUENCE {INDEX}.t224_seq_ok;\n", "t224_reg")
    again, _ = m.dump("t224_reg", files[DUMP], "second.dump")
    assert again.returncode == 0, f"a later sequence stopped the dump:\n{_said_safely(again)}"
    # THE CONTROLS: the default privilege revoked before a sequence is made,
    # and the reader's SELECT on doc_lines' sequence revoked.
    m.psql(f"ALTER DEFAULT PRIVILEGES FOR ROLE {INDEXER} IN SCHEMA {INDEX} "
           f"REVOKE SELECT ON SEQUENCES FROM {READER};\n", "t224_reg", user=ADMIN)
    m.psql(f"SET ROLE {INDEXER};\nCREATE SEQUENCE {INDEX}.t224_seq_hidden;\n", "t224_reg")
    hidden, _ = m.dump("t224_reg", files[DUMP], "third.dump")
    assert hidden.returncode != 0 and "t224_seq_hidden" in hidden.stderr, _said_safely(hidden)
    m.psql(f"SET ROLE {INDEXER};\nDROP SEQUENCE {INDEX}.t224_seq_hidden;\n", "t224_reg")
    m.psql(f"SET ROLE {OWNER};\nREVOKE SELECT ON {REGISTER}.doc_lines_line_id_seq FROM {READER};\n",
           "t224_reg")
    seq, _ = m.dump("t224_reg", files[DUMP], "fourth.dump")
    assert seq.returncode != 0 and "doc_lines_line_id_seq" in seq.stderr, _said_safely(seq)
    # STILL CANNOT WRITE: each refused inside BEGIN READ WRITE, then ROLLBACK.
    tries = [f"SELECT nextval('{REGISTER}.doc_lines_line_id_seq')",
             f"UPDATE {REGISTER}.register_head SET seq = seq",
             f"SELECT nextval('{INDEX}.t224_seq_ok')", f"SELECT setval('{INDEX}.t224_seq_ok', 5)",
             f"INSERT INTO {INDEX}.t224_rows VALUES (2)", f"UPDATE {INDEX}.t224_rows SET id = id",
             f"DELETE FROM {INDEX}.t224_rows", f"TRUNCATE {INDEX}.t224_rows"]
    for statement in tries:
        tried = m.as_login(DUMP, "t224_reg", f"BEGIN READ WRITE;\n{statement};\nROLLBACK;\n",
                           files[DUMP])
        assert tried.returncode != 0 and "42501" in tried.stderr, (
            f"the dump login's {statement!r} was not refused with 42501:\n{_said_safely(tried)}")


# ============================================================ the restores
def _source(request, root: Path, *, primary: bool):
    """A bootstrapped register with rows: e1's logins and the dump job's, an
    import, and, where `primary`, the cutover and the marker; and its dump,
    by O2's command."""
    m = Managed(request, root)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    files = m.logins(service, "e1")
    if primary:
        m.to_primary("t224_reg", "lanes_w_e1", files["lanes_w_e1"])
    else:
        proc = m.commit("t224_reg", "lanes_w_e1", files["lanes_w_e1"],
                        m.entry("t224_reg", "import", "lanes/LANES.md", "# Lanes"))
        assert proc.returncode == 0, _said_safely(proc)
    dumped, target = m.dump("t224_reg", files[DUMP], "source.dump")
    assert dumped.returncode == 0, f"the source's dump failed:\n{_said_safely(dumped)}"
    return m, files, target


def _restored(request, root: Path, source_dump: Path):
    """R-P41's order on a new cluster with the admin role: the database
    created first by the admin; then, through one service naming it,
    `bootstrap --roles-only`, `login add e1` and `login add --dump-job`, the
    restore, and `bootstrap`. Returns the target, its runs and its files."""
    target = Managed(request, root, cluster=_another_cluster(request))
    service = target.database("t224_reg")
    roles = target.bootstrap(service, "--roles-only", pty_run=True)
    assert roles.returncode == 0, f"bootstrap --roles-only failed:\n{_said_safely(roles)}"
    files = target.logins(service, "e1", folder="passfiles-new")
    env = {k: v for k, v in target.env.items() if not k.startswith("PG")}
    env["PGSERVICE"] = service
    restore = subprocess.run([target.cluster.tool("pg_restore"), "--exit-on-error", "--no-password",
                              "--dbname=t224_reg", str(source_dump)],
                             capture_output=True, text=True, timeout=300, env=env, check=False)
    assert restore.returncode == 0, f"pg_restore through the admin service failed:\n{_said_safely(restore)}"
    mark = len(target.log())
    after = target.bootstrap(service, pty_run=True)
    assert after.returncode == 0, f"bootstrap after the restore failed:\n{_said_safely(after)}"
    return target, roles, after, files, mark


def test_a_restore_from_the_dump_equals_its_source_with_new_passwords(tmp_path, request):
    source, old, dump = _source(request, tmp_path / "source", primary=False)
    target, roles, after, new, _mark = _restored(request, tmp_path / "target", dump)
    # `--roles-only` prints the indexer's line, and `created` for each of the
    # three database-level statements (option (a)).
    assert sorted(_passwords(roles.stdout)) == [INDEXER], _said_safely(roles)
    objects = dict(_objects(roles.stdout))
    for words in DB_LEVEL:
        assert [state for what, state in objects.items() if words in what] == ["created"], (
            f"--roles-only does not print `created` for {words}:\n{_said_safely(roles)}")
    assert {state for _what, state in _objects(after.stdout)} == {"unchanged"}, _said_safely(after)
    assert target.catalog("t224_reg") == source.catalog("t224_reg"), "the catalogs differ"
    assert target.rows("t224_reg") == source.rows("t224_reg"), "the rows differ"
    for login in ("lanes_w_e1", "lanes_r_e1", DUMP):
        assert not target.connects(login, "t224_reg", old[login]), (
            f"the source's password file for {login} connects to the restore")
        assert target.connects(login, "t224_reg", new[login]), f"{login}'s printed line does not connect"
    _no_clear_text(target.log(), {**_passwords(roles.stdout), **{
        login: path.read_text(encoding="utf-8").strip() for login, path in new.items()}})


def test_a_restore_from_the_providers_copy_keeps_the_roles_and_takes_new_passwords(
        tmp_path, request):
    source, old, _dump = _source(request, tmp_path / "source", primary=False)
    logins = ("lanes_w_e1", "lanes_r_e1", DUMP)
    before = {login: source.role(login) for login in logins}
    source.cluster.stop()
    copy = Managed(request, tmp_path / "copy",
                   cluster=_another_cluster(request, data_from=source.cluster.root / "data"),
                   scram=False)
    for login in logins:
        assert copy.role(login) == before[login], f"{login} differs on the provider's copy"
        assert copy.connects(login, "t224_reg", old[login]), f"{login}'s old file does not connect"
    service = copy.service("t224_reg")
    roles = copy.bootstrap(service, "--roles-only", pty_run=True)
    assert roles.returncode == 0, f"bootstrap --roles-only failed:\n{_said_safely(roles)}"
    assert {state for _what, state in _objects(roles.stdout)} == {"unchanged"}, _said_safely(roles)
    printed = sorted(_passwords(roles.stdout))     # the logins alone, as pytest reports it (T224j)
    assert printed == [], f"--roles-only printed a password line:\n{_said_safely(roles)}"
    new: dict = {}
    for who in ("e1", DUMP):
        proc = copy.login("rotate", who, service)
        assert proc.returncode == 0, f"login rotate {who} failed:\n{_said_safely(proc)}"
        new.update(copy.passfiles(proc.stdout, "passfiles-new"))
        _no_clear_text(copy.log(), _passwords(proc.stdout))
    assert sorted(new) == sorted(logins), f"the rotations printed lines for {sorted(new)}, not {sorted(logins)}"
    for login in logins:
        assert not copy.connects(login, "t224_reg", old[login]), f"{login}'s old file still connects"
        assert copy.connects(login, "t224_reg", new[login]), f"{login}'s new line does not connect"


# ============================================================ check 11
class TlsEnvironment:
    """Check 11's environment on section 5.6's TLS cluster, T229's
    `tls_cluster`, which `tests/pgcluster.py` gives since this line merged
    line FX at T229d. Each id skips with T205's banner where `pg_engine`
    finds none.

    LINE FX'S PLANNED NAMES (the coordinator, 16:50Z), NOT A CONTRACT: a
    `TLSCluster` with `root_cert`, `database_name`, `url(user)`,
    `client_env(user)`, `configuration(directory, database=None,
    mode="index")` and `second_database(label)`. This module uses
    `configuration(directory)`, a 0600 `lanes-index.conf` naming the
    fixture's logins (T228's `lanes_w_fx` and `lanes_r_fx`) on loopback TCP
    with `sslmode=verify-full` and `sslrootcert=` the root alone, and
    `root_cert`. READ FROM F12B'S T229 TEXT, and not in that list: it is a
    `pgcluster.Cluster` (`root`, `bindir`, `stop`, `start_again`), its Unix
    socket at `root`; and its two start options are
    `start_again(leaf_only=True)`, the leaf served without the intermediate
    (T230's `[leaf-only]`), and `start_again(standby=True)`, T229d's, which
    writes `standby.signal`, polls for `ready` as every start does, and
    fails the start unless `pg_is_in_recovery()` is true (the test plan's
    `[in-recovery]`; lane 3's batch 11 (1))."""

    NEEDS = ("configuration", "root_cert", "root", "bindir", "stop", "start_again")

    def __init__(self, request, root: Path):
        request.getfixturevalue("pg_engine")
        import pgcluster
        assert getattr(pgcluster, "tls_cluster", None) is not None, (
            "check 11 needs section 5.6's TLS cluster, T229's, since it always fails on a Unix "
            "socket; tests/pgcluster.py has no tls_cluster yet")
        self.tls = request.getfixturevalue("tls_cluster")
        missing = [name for name in self.NEEDS if not hasattr(self.tls, name)]
        assert not missing, f"T229's tls_cluster has no {', '.join(missing)}"
        self.root = root
        made = Path(self.tls.configuration(root / "conf"))
        self.base = made / "lanes-index.conf" if made.is_dir() else made
        self.lines = self.base.read_text(encoding="utf-8").splitlines()
        self.register_url = next(line.split("=", 1)[1] for line in self.lines
                                 if line.startswith("register_url="))
        self.login = self.register_url.split("//", 1)[1].split("@", 1)[0]
        (root / "home").mkdir(exist_ok=True)
        (root / "t").mkdir(exist_ok=True)
        env = guard_strip_env(os.environ, strip=("T224_", "XDG_"))
        env.update(HOME=str(root / "home"), XDG_CONFIG_HOME=str(root / "config"),
                   XDG_STATE_HOME=str(root / "state"), TMPDIR=str(root / "t"),
                   LANES_WORKSTATION="Eagle", LANES_NO_GITHUB="1", LC_ALL="C",
                   PATH=os.pathsep.join([str(self.tls.bindir), os.environ.get("PATH", os.defpath)]))
        self.env = env

    def url(self, **query: str | None) -> str:
        """The configuration's `register_url=`, with `query`'s parameters set,
        or dropped where None."""
        head, _, tail = self.register_url.partition("?")
        params = dict(piece.split("=", 1) for piece in tail.split("&") if "=" in piece)
        params.update(query)
        tail = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        return head + (f"?{tail}" if tail else "")

    def socket_url(self) -> str:
        """The same URL at the cluster's own Unix socket."""
        head, _, tail = self.register_url.partition("?")
        _scheme, _, rest = head.partition("//")
        port = rest.split("@", 1)[1].split("/", 1)[0].rsplit(":", 1)[1]
        database = rest.split("/", 1)[1]
        return (f"postgresql://{self.login}@{quote(str(self.tls.root), safe='')}:{port}/{database}"
                + (f"?{tail}" if tail else ""))

    def ready(self, register_url: str) -> subprocess.CompletedProcess:
        config = _private(self.root / f"c{uuid.uuid4().hex[:8]}" / "lanes-index.conf", "\n".join(
            [f"register_url={register_url}" if line.startswith("register_url=") else line
             for line in self.lines]) + "\n")
        env = dict(self.env, LANES_INDEX_CONFIG=str(config))
        return _run([sys.executable, str(REPO / "lanes-index"), "ready", "--expect", "index",
                     "--release", "0.0.0-t224", "--env", "t224"], env, self.root, pty_run=False)

    def restart(self, **option: bool) -> None:
        """Stop the TLS cluster and start it again with T229's start option,
        `leaf_only=` (T230's `[leaf-only]`) or `standby=True`
        (`[in-recovery]`). The option is only passed on: T229d's
        `start_again(standby=True)` writes `standby.signal` and proves the
        recovery itself (lane 3's batch 7, ruling 2, and batch 11 (1))."""
        self.tls.stop()
        self.tls.start_again(**option)


#: Check 11's ids: what each does to the environment, and whether it passes.
CHECK_11 = {
    "passes": (lambda env: env.url(), True),
    "sslmode-prefer": (lambda env: env.url(sslmode="prefer"), False),
    "no-sslrootcert": (lambda env: env.url(sslrootcert=None), False),
    "unix-socket": (lambda env: env.socket_url(), False),
    "in-recovery": (lambda env: (env.restart(standby=True), env.url())[1], False),
    # T230 (R2's S3; X's TLS rules and FR-011's server half, R09). Each meets
    # the TLS cluster at a loopback host, so T104's refusal at load lets its
    # URL load and check 11 meets it.
    "leaf-only": (lambda env: (env.restart(leaf_only=True), env.url())[1], False),
    "system-root": (lambda env: env.url(sslrootcert="system"), False),
    "plaintext": (lambda env: env.url(sslmode="disable", sslrootcert=None), False),
}


def _says(*words: str):
    """A failing check-11 case's predicate on check 11's reason: it holds
    each of `words` (T224n). `words` stays on it for a failure's message."""
    def holds(reason: str) -> bool:
        return all(word in reason for word in words)
    holds.words = words
    return holds


#: The fault each failing case is built to show, as a predicate on check 11's reason,
#: one for EVERY failing case (T224l, T224n): a FAIL for another cause, a restart's
#: stale port among them, does not pass. The URL's faults are in the words of
#: `_ready_check_tls` (line R `9bdd317b`), which puts them first in its connection's
#: part of the line. `[leaf-only]`'s is libpq's own, for a chain it cannot verify: the
#: server sends the leaf without its intermediate, so the root alone cannot verify it,
#: and psql 16 says, under the `LC_ALL=C` that `TlsEnvironment` sets, `connection to
#: server at "127.0.0.1", port <port> failed: SSL error: certificate verify failed`,
#: which `_ready_psql_why` puts in the line (Codex's review of P09 at `21dd3642`,
#: SHOULD 5 in lane 3's numbering).
CHECK_11_FAULT = {
    "sslmode-prefer": _says("its URL carries sslmode=prefer, not sslmode=verify-full"),
    "no-sslrootcert": _says("its URL carries no sslrootcert= naming the issuer's root file"),
    "unix-socket": _says("its URL names a Unix socket"),
    "in-recovery": _says("pg_is_in_recovery() is not false"),
    "leaf-only": _says("SSL error: certificate verify failed"),
    "system-root": _says("its sslrootcert= is system"),
    "plaintext": _says("its URL carries sslmode=disable, not sslmode=verify-full"),
}


@pytest.mark.parametrize("case", list(CHECK_11))
def test_ready_check_11_needs_tls_and_the_primary(tmp_path, request, case):
    env = TlsEnvironment(request, tmp_path)
    make, passes = CHECK_11[case]
    proc = env.ready(make(env))
    state, reason = _checks(proc.stdout).get(11, ("", ""))
    if passes:
        assert state == "ok", f"[{case}] check 11 does not pass:\n{_said_safely(proc)}"
    else:
        assert state == "FAIL" and proc.returncode == 2, (
            f"[{case}] check 11 does not fail, or ready does not exit 2:\n{_said_safely(proc)}")
        assert env.login in reason, f"[{case}] check 11 does not name the connection:\n{_said_safely(proc)}"
        fault = CHECK_11_FAULT[case]
        wanted = " and ".join(repr(word) for word in fault.words)
        assert fault(reason), (
            f"[{case}] check 11 fails, but not for {wanted} (T224l, T224n):\n{_said_safely(proc)}")


#: Check 11's reason for each failing case as `ready` would print it, the URL's faults
#: in `_ready_check_tls`'s words (line R `9bdd317b`) and a connection's in libpq 16's
#: (psql under `LC_ALL=C`), for T224n's regression; and a FAIL for another cause, the
#: port a restart did not keep.
CHECK_11_SAID = {
    "sslmode-prefer": "its URL carries sslmode=prefer, not sslmode=verify-full",
    "no-sslrootcert": "its URL carries no sslrootcert= naming the issuer's root file",
    "unix-socket": ("its URL names a Unix socket, where libpq ignores sslmode and nothing is "
                    "encrypted; its own pg_stat_ssl row shows ssl false: the connection is not "
                    "encrypted"),
    "in-recovery": "pg_is_in_recovery() is not false: it reached a server in recovery, not the primary",
    "leaf-only": ('its connection and read failed (c 10 s, N_a 1): psql: error: connection to server '
                  'at "127.0.0.1", port 54321 failed: SSL error: certificate verify failed'),
    "system-root": ("its sslrootcert= is system, whose store holds no private root (C7, design "
                    "Y:2324); its connection and read failed (c 10 s, N_a 1): psql: error: "
                    'connection to server at "127.0.0.1", port 54321 failed: SSL error: '
                    "certificate verify failed"),
    "plaintext": ("its URL carries sslmode=disable, not sslmode=verify-full; its URL carries no "
                  "sslrootcert= naming the issuer's root file"),
}
CHECK_11_STALE_PORT = ('its connection and read failed (c 10 s, N_a 1): psql: error: connection to '
                       'server at "127.0.0.1", port 54321 failed: Connection refused')


def test_each_failing_check_11_case_passes_its_own_fault_and_no_other_cause(tmp_path, monkeypatch):
    """T224n (Codex's review of P09 at `21dd3642`, SHOULD 5 in lane 3's
    numbering): check 11's case itself, run with a stand-in for its TLS
    environment whose `ready` prints one check-11 FAIL line, with no
    database. Each failing case passes its own fault and fails the same FAIL
    for a restart's stale port, `[leaf-only]` among them; and every failing
    case has a predicate. No password is in any line."""
    login = "lanes_w_fx"

    class StandIn:
        said = ""

        def __init__(self, _request, _root):
            self.login = login

        def url(self, **_query) -> str:
            return f"postgresql://{login}@127.0.0.1:54321/t229"

        def socket_url(self) -> str:
            return self.url()

        def restart(self, **_option) -> None:
            pass

        def ready(self, _register_url: str) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(
                [], 2, f"check 11: FAIL: writer {login} (`register_url=`): {StandIn.said}\n", "")

    monkeypatch.setitem(globals(), "TlsEnvironment", StandIn)
    failing = [case for case, (_make, passes) in CHECK_11.items() if not passes]
    for case in failing:
        StandIn.said = CHECK_11_SAID[case]
        test_ready_check_11_needs_tls_and_the_primary(tmp_path, None, case)
        StandIn.said = CHECK_11_STALE_PORT
        with pytest.raises(AssertionError, match=r"check 11 fails, but not for"):
            test_ready_check_11_needs_tls_and_the_primary(tmp_path, None, case)
    missing = sorted(set(failing) - set(CHECK_11_FAULT))
    assert not missing, f"no fault predicate for the failing check-11 cases {missing} (T224n)"


# ============================================================ tls_at_load
#
# T230, lane 1's `tls_at_load` (L1-1; T104; CLI4.5 section 2.5): each item
# through `lanes-index mode`, with `mode=index` in the file, so Q6(c) never
# answers. FP: nothing connects. A refused file is 2 from `mode`, naming the
# key and what is missing and printing no URL; 3 from `journal --write-id`
# (CO-3); and 1 under `register read --for guard`'s prefetch, form 2 (O14).
# That read's `--pid` is a stand-in for the hook started just before it
# (`hook_pid`), so the 1 is the refused file's and never the hook's age.

#: A TCP host that is not loopback, and the loopback stand-ins.
REMOTE = "db.t230.invalid"
LOOPBACK = "127.0.0.1"


def _tls_url(login: str, host: str, query: str = "") -> str:
    return f"postgresql://{login}@{host}:5432/register_db" + (f"?{query}" if query else "")


def _tls_files(root: Path) -> dict:
    """Each item's configuration lines, and what it expects: `index` (it
    loads), or the key its refusal names and the words of what is missing."""
    rootfile = _private(root / "ca" / "root.crt", "not a certificate: only its existence counts\n")
    socket = quote("/tmp/t230-socket", safe="")
    reader = f"reader_url={_tls_url('lanes_r_t230', LOOPBACK)}"
    return {
        "no-sslmode": ([f"register_url={_tls_url('lanes_w_t230', REMOTE)}", reader],
                       ("register_url=", "sslmode")),
        "system-root": ([f"register_url={_tls_url('lanes_w_t230', REMOTE, 'sslmode=verify-full&sslrootcert=system')}",
                         reader], ("register_url=", "system")),
        "missing-root": ([f"register_url={_tls_url('lanes_w_t230', REMOTE, 'sslmode=verify-full&sslrootcert=' + str(root / 'ca' / 'absent.crt'))}",
                          reader], ("register_url=", "sslrootcert")),
        "root-file": ([f"register_url={_tls_url('lanes_w_t230', REMOTE, 'sslmode=verify-full&sslrootcert=' + str(rootfile))}",
                       reader], "index"),
        "socket": ([f"register_url={_tls_url('lanes_w_t230', socket)}", reader], "index"),
        "loopback": ([f"register_url={_tls_url('lanes_w_t230', LOOPBACK)}", reader], "index"),
        "no-register-url": ([f"url={_tls_url('lanes_writer', REMOTE)}",
                             f"reader_url={_tls_url('lanes_reader', REMOTE)}"], "index"),
        "reader-url": ([f"register_url={_tls_url('lanes_w_t230', LOOPBACK)}",
                        f"reader_url={_tls_url('lanes_r_t230', REMOTE)}"], ("reader_url=", "sslmode")),
        "two-hosts": ([f"register_url=postgresql://lanes_w_t230@{LOOPBACK}:5432,{REMOTE}:5432/register_db",
                       reader], ("register_url=", "sslmode")),
    }


@contextlib.contextmanager
def hook_pid():
    """THE HOOK'S `$$`, FOR A GUARD READ'S `--pid` (contract section 3.6:
    "`--pid <pid>` ... is the hook's own pid, `$$`, in forms 2 and 4", and
    "the client reads `T0` from it"). It yields the pid of a stand-in for the
    hook, a `sleep` started just before the read, as a hook's own start is,
    and stops it after the read. T507 cuts a guard read at `T0` + 3.75 s
    from that start, and an age at or above the cut exits 2, "too late to
    verify" (section 3.6's 2; `register_guard_t0`). The pytest process's own
    pid is minutes old on a runner, and with it the measure module's `[m10]`
    ended 2 (lane 1's round 6b census, #165 6827592167, item 2). Here
    `[for-guard]`'s file is refused at load, which merge27's client answers
    1 before it checks the age, so the old pid did not change that case's
    exit there; the stand-in makes its read the hook's, as the contract
    says, whatever order a client checks in. It is AT-F7's stand-in,
    `test_sql_register_outage.py`'s `_stand_in`, at an age of 0, as the
    measure and readers modules' `hook_pid` are."""
    standin = subprocess.Popen(["sleep", "120"], start_new_session=True,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    try:
        yield str(standin.pid)
    finally:
        # Kill it, then a reap bounded at 10 s, as `GuardSession.close()` does: a
        # stand-in that a kill does not take fails the case and never hangs the
        # run (T230c).
        standin.kill()
        try:
            standin.wait(timeout=10)
        except subprocess.TimeoutExpired:
            standin.kill()
            standin.wait(timeout=10)


#: The items, and the two that read the refused file through another verb.
TLS_AT_LOAD = ["no-sslmode", "system-root", "missing-root", "root-file", "socket", "loopback",
               "no-register-url", "reader-url", "two-hosts", "journal-write-id", "for-guard"]


@pytest.mark.parametrize("item", TLS_AT_LOAD)
def test_tls_at_load_refuses_a_url_off_loopback_without_verify_full_and_a_root_file(tmp_path, item):
    bench = LoginBench(tmp_path)
    files = _tls_files(tmp_path)
    lines, expect = files["no-sslmode" if item in ("journal-write-id", "for-guard") else item]
    config = _private(tmp_path / "conf" / "lanes-index.conf", "\n".join(["mode=index", *lines, ""]))
    bench.env["LANES_INDEX_CONFIG"] = str(config)
    urls = [line.split("=", 1)[1] for line in lines]
    if item == "journal-write-id":
        proc = bench.run(["journal", "--write-id", str(uuid.uuid4()), "--not-after", "2000000000",
                          "--generation", str(uuid.uuid4()), "--lane", "t230", "--verb", "append-line",
                          "--args-sha256", "0" * 64], pty_run=False)
        assert proc.returncode == 3, f"[{item}] journal --write-id on a refused file is not 3:\n{_said_safely(proc)}"
    elif item == "for-guard":
        repo = tmp_path / "repo"
        repo.mkdir()
        with hook_pid() as pid:
            proc = bench.run(["register", "read", "--for", "guard", "--prefetch", "--cache",
                              str(tmp_path / "cache"), "--pid", pid, "--repo", str(repo)],
                             pty_run=False)
        assert proc.returncode == 1, (
            f"[{item}] register read --for guard --prefetch on a refused file is not 1:\n{_said_safely(proc)}")
    else:
        proc = bench.run(["mode"], pty_run=False)
        if expect == "index":
            assert (proc.returncode, proc.stdout) == (0, "index\n"), f"[{item}] does not load:\n{_said_safely(proc)}"
        else:
            key, missing = expect
            assert proc.returncode == 2 and proc.stdout == "", f"[{item}] is not refused with 2:\n{_said_safely(proc)}"
            assert key in proc.stderr and missing in proc.stderr, (
                f"[{item}] the refusal does not name {key} and {missing}:\n{_said_safely(proc)}")
    for url in urls:
        if expect != "index" or item in ("journal-write-id", "for-guard"):
            assert url not in proc.stdout + proc.stderr, f"[{item}] the refusal printed a URL"
    assert bench.requests() == [], f"[{item}] a request was sent: nothing connects at load"


# ============================================================ lane 1's two
def test_dump_restore_privileges_hold_after_roles_only_the_restore_and_bootstrap(
        tmp_path, request):
    source, _old, dump = _source(request, tmp_path / "source", primary=True)
    label = source.value(f"SELECT database_label FROM {REGISTER}.register_switch;", "t224_reg")
    target, _roles, after, _new, mark = _restored(request, tmp_path / "target", dump)
    end = len(target.log())
    db = "t224_reg"
    acl = target.value(f"SELECT coalesce(datacl::text, '') FROM pg_database WHERE datname = '{db}';",
                       "postgres")
    assert not re.search(r"(^|[{,])=[A-Za-z]*c", acl), f"PUBLIC holds CONNECT on {db}: {acl}"
    target.psql("CREATE ROLE t224_outsider LOGIN PASSWORD 'outside-t224';")
    outsider = _private(target.home / "passfiles" / "t224_outsider", f"*:*:{db}:t224_outsider:outside-t224\n")
    refused = target.as_login("t224_outsider", db, "SELECT 1;\n", outsider)
    assert refused.returncode == 2 and "permission denied for database" in refused.stderr, _said_safely(refused)
    for role in (WRITER, READER, INDEXER):
        assert target.value(f"SELECT has_database_privilege('{role}', '{db}', 'CONNECT');",
                            "postgres") == "t", f"{role} holds no CONNECT on {db}"
    target.psql(f"SET ROLE {OWNER};\nCREATE FUNCTION {REGISTER}.t224_later() RETURNS int "
                "LANGUAGE sql AS 'SELECT 1';\n", db)
    assert target.value(f"SELECT has_function_privilege('t224_outsider', '{REGISTER}.t224_later()', "
                        "'EXECUTE');", db) == "f", "an outsider may execute a later function of the owner's"
    # `bootstrap` after the restore re-ran no statement and wrote no label.
    assert {state for _what, state in _objects(after.stdout)} == {"unchanged"}, _said_safely(after)
    since = target.log()[mark:end]
    ran = [found.group(1) for found in
           (re.search(r"statement: (CREATE|GRANT|REVOKE|ALTER|INSERT|UPDATE)\b", line)
            for line in since.splitlines()) if found]
    # Only the count and the verbs: a role's statement can hold its password (T258m).
    assert ran == [], (f"bootstrap after the restore re-ran {len(ran)} statement(s): "
                       f"{', '.join(sorted(set(ran)))}; no statement's text is shown")
    restored = target.value(f"SELECT database_label FROM {REGISTER}.register_switch;", db)
    assert restored == label, f"the restored register's label is {restored!r}, not the source's {label!r}"


def test_rotate_dump_job_changes_only_the_dump_logins_password(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    old = m.logins(service, "e1")
    verifiers = {login: m.role(login)["verifier"] for login in ("lanes_w_e1", "lanes_r_e1", DUMP)}
    # Off a terminal it refuses with 2 and changes nothing.
    piped = m.login("rotate", DUMP, service, pty_run=False)
    assert piped.returncode == 2, f"rotate --dump-job through a pipe is not 2:\n{_said_safely(piped)}"
    assert m.role(DUMP)["verifier"] == verifiers[DUMP], "the refused rotation changed the verifier"
    # Neither an engineer nor --dump-job, or both: 64.
    for argv in (["login", "rotate", "--admin-service", service],
                 ["login", "rotate", "e1", "--dump-job", "--admin-service", service]):
        usage = m.lanes(*argv, pty_run=True)
        assert usage.returncode == 64, f"{argv[1:]} is not usage, 64:\n{_said_safely(usage)}"
    proc = m.login("rotate", DUMP, service)
    assert proc.returncode == 0, f"login rotate --dump-job failed:\n{_said_safely(proc)}"
    lines = _passwords(proc.stdout)
    assert sorted(lines) == [DUMP], f"not one line, the dump login's:\n{_said_safely(proc)}"
    new = m.passfiles(proc.stdout, "passfiles-new")
    assert m.role(DUMP)["verifier"] != verifiers[DUMP], "the dump login's verifier did not change"
    for login in ("lanes_w_e1", "lanes_r_e1"):
        assert m.role(login)["verifier"] == verifiers[login], f"{login}'s verifier changed"
    assert not m.connects(DUMP, "t224_reg", old[DUMP]), "the old dump password still logs in"
    dumped, _target = m.dump("t224_reg", new[DUMP], "rotated.dump")
    assert dumped.returncode == 0, f"the new dump password does not dump:\n{_said_safely(dumped)}"
    _no_clear_text(m.log(), lines)


# ============================================================ phase W (T258)
#
# AT-LRMPG'S PHASE W (T258; the test plan's "Phase and kind": the logins'
# writes and reads, which run through the flipped test copy of `lanes-index`,
# test 14's second state, are W). Each case runs on a managed PostgreSQL of
# its own, as phase N's do (`Managed`): the admin's database, the bootstrap,
# and `login add` for the case's engineers, whose printed lines go into 0600
# password files. `PhaseW` then brings the register to `primary` by AT-LR006's
# route (TP:4610-4615), as e1's writer login: an `import` entry of the render
# set at a bare origin's `main`, a `cutover` entry naming `lanes/STORE`, and
# `record_marker`. Each engineer gets a checkout of that origin, a protocol
# root naming it, and a `mode=primary` `lanes-index.conf` whose
# `register_url=` and `reader_url=` name that engineer's own two logins on
# the cluster's socket, each with its own password file (section 1.4, "One
# engineer's file").
#
# A WRITE is `lanes-edit.sh log NOTED lane:<lane> <text>`, a READ is
# `lanes-edit.sh binding <lane>` (S3's table), each from the flipped copy,
# with `lanes-edit.sh` beside it (CLI4.5 section 6's copy rule), as T241's
# and T243's writers run; this module builds the workstation itself, since
# neither of their modules is on this branch. Each run puts T203's shim first
# on `PATH`, in a directory of its own, so the shim's log is that run's calls,
# and the mid-commit case arms its `hold` there. The two writer logins' log
# lines are the server's own: `log_connections` and `log_statement=all`, each
# line prefixed with its backend's pid (`Managed`).
#
# Rotate's write half is the fifth case (lane 3's batch 7, lane 2's item (3);
# TP:5317-5318): with the old password file, e1's write exits 69 at its
# snapshot and the journal gains nothing; with the new lines it commits once.
# T224's rotate case keeps the connection half.
#
# They FAIL UNTIL lane 1's T110 (L1-A8, `lanes-index login`) and lane 4's
# writer on primary land, its attempt loop (L4-B3) and its in-doubt rule and
# pending record (L4-B5): merge10's `lanes-edit.sh` has no primary branch and
# writes the files whatever `mode=` says, so each write case fails at its
# own assertion. `target_session_attrs` (M5) is `psql`'s alone and needs only
# L1-A8. Without PostgreSQL 16 each skips with T205's banner.

W_DB = "t224_reg"
#: Phase W's lanes, one per engineer, and their sessions.
W_LANES = {"e1": "repoE-1", "e2": "repoE-2"}
W_SESSIONS = {"e1": "eeeeeeee-0258-4000-8000-00000000e001",
              "e2": "eeeeeeee-0258-4000-8000-00000000e002"}
W_WS = "Eagle"
#: The register's punctuation, spelled by code point, as the render module
#: spells it: the em dash, the middle dot of a state cell, the arrow.
EM, DOT, ARROW = chr(0x2014), chr(0x00B7), chr(0x2192)
STORE_PATH = "lanes/STORE"
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
#: The pending records (L4-B5): `<state>/openRepoTools/register-pending/<d>`,
#: as T245 reads them.
PENDING = Path("openRepoTools") / "register-pending"
#: Everything a write that wrote nothing leaves as it was (T243's form).
W_STATE_SQL = f"""
SELECT md5(concat_ws('|',
  (SELECT seq::text FROM {REGISTER}.register_head),
  (SELECT string_agg(j::text, ',' ORDER BY j.seq) FROM {REGISTER}.journal j),
  (SELECT string_agg(e::text, ',' ORDER BY e.seq, e.ord) FROM {REGISTER}.journal_edits e),
  (SELECT string_agg(f::text, ',' ORDER BY f.path) FROM {REGISTER}.files f),
  (SELECT string_agg(d::text, ',' ORDER BY d.line_id) FROM {REGISTER}.doc_lines d),
  (SELECT string_agg(s::text, ',') FROM {REGISTER}.register_switch s)));
"""
#: A server log line under `log_line_prefix = '%p '`: the pid, the level and
#: the message. A line without the prefix continues the one before it.
LOG_LINE = re.compile(r"^([0-9]+) ([A-Z]+):  (.*)$")
AUTHORIZED = re.compile(r"connection authorized: user=(\S+)")


def _w_row(lane: str, sid: str) -> str:
    return (f"| `{lane}` | harness `{sid}` | {W_WS} / test / brett | 2026-10-01T00:00Z | none "
            f"| handoffs/{lane}.md | LIVE {DOT} 2026-10-01T01:00:00Z {DOT} working |")


def _w_seed() -> dict:
    """Phase W's register at C: a row and a log for each engineer's lane, an
    empty aliases table; `lanes/repos.tsv` and `lanes/log/README.md`, which
    the checkout gives and the register does not hold."""
    files = {
        "lanes/LANES.md": "\n".join([
            f"# LANES.md {EM} AT-LRMPG's phase W register (T258)", "",
            "| lane | session id | workstation / env / user | started (UTC) | objects owned "
            "| handoff path | state |",
            "|---|---|---|---|---|---|---|",
            *(_w_row(W_LANES[who], W_SESSIONS[who]) for who in W_LANES), ""]),
        "lanes/aliases.tsv": "# old\tnew\tutc\n",
        "lanes/log/README.md": "# the object logs\n",
        "lanes/repos.tsv": "# alias\towner/repo\nrepoE\topensoft/repoE\n",
    }
    for who, lane in W_LANES.items():
        files[f"lanes/log/{lane}.md"] = "\n".join([
            f"# lane {lane} {EM} object log (lane-collision-protocol Amendment 7)",
            f"STARTED {EM} lane {lane}, session {W_SESSIONS[who]}@{W_WS}, 2026-10-01T00:00:00Z, "
            f"lane:{lane} {ARROW} home opensoft/repoE; dir /work/{lane}", ""])
    return files


def _w_creates(files: dict) -> tuple:
    """Each of `files` ({path: text}) created, then its lines appended, and
    its `files` row with its digest as it renders (AT-LR006's first step)."""
    edits: list = []
    rows: list = []
    for path in sorted(files):
        edits.append({"ord": len(edits) + 1, "op": "create", "path": path})
        for text in files[path].rstrip("\n").split("\n"):
            edits.append({"ord": len(edits) + 1, "op": "append", "path": path, "new_text": text})
        rows.append({"path": path, "present": True, "final_newline": True,
                     "sha256": _sha256(files[path].encode("utf-8"))})
    return edits, rows


def _w_git(cwd: Path, env: dict, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env,
                          timeout=120, check=False)
    assert proc.returncode == 0, f"git {' '.join(args)} in {cwd}: {_said_safely(proc)}"
    return proc.stdout


#: `_masked_path`'s mirrors, by each directory's real path (None where the
#: directory holds no masked name), and the one temporary root they share.
_PATH_MIRRORS: dict = {}
_PATH_MIRROR_ROOT: list = []


def _masked_path() -> str:
    """The caller's PATH with every directory kept in its place, and each one
    that holds a `psql`, a `lanes-index` or a name that starts `pg_` swapped
    for a private mirror of it: a directory of links, one to each of its
    entries by its absolute path, those names left out. Neither an installed
    indexer nor a `psql` (or a `pg_` client wrapper shipped beside it) behind
    the shim's back is what a case runs, but the tools beside them are: on a
    GitHub runner `postgresql-16`'s client puts `psql` in `/usr/bin` with
    `git` and `bash` (and `/bin` is a link to it), so dropping the directory
    dropped `git` and `bash` too (lane 1's census, #165 6807454856). A
    directory that holds none of those names passes through unchanged. Each
    mirror is made once per process, under one `mkdtemp` that an `atexit`
    handler removes."""
    parts = []
    for part in os.environ.get("PATH", os.defpath).split(os.pathsep):
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


def _commit_logins(log: str) -> list:
    """The login of each `commit_write` call in `log`: each statement line,
    or a line continuing one, that carries `commit_write(`, tied by its
    backend's pid to that backend's `connection authorized` line."""
    users: dict = {}
    found: list = []
    pid, in_statement = None, False
    for line in log.splitlines():
        m = LOG_LINE.match(line)
        if m:
            pid, level, said = m.groups()
            in_statement = level == "LOG" and said.startswith("statement:")
            authorized = AUTHORIZED.match(said)
            if authorized:
                users[pid] = authorized.group(1)
        else:
            said = line
        if in_statement and "commit_write(" in said:
            found.append(users.get(pid, f"no connection authorized line for pid {pid}"))
            in_statement = False
    return found


class W258Writer:
    """One `lanes-edit.sh` run, its shim's directory and its outcome. `launch`
    starts it in a session of its own (`start_new_session=True`). Its thread
    only reads its two pipes; the reap is the main thread's, in `wait`, or in
    `stop` at the case's teardown (T258e), and it comes last: until the reader
    is joined and the pipes are closed, the run is left unreaped, so the group
    it leads is still its own to end (T258f)."""

    def __init__(self, who: str, proc: subprocess.Popen, psql_dir: Path, state: Path):
        self.who, self.proc, self.psql_dir, self.state = who, proc, psql_dir, state
        self.ended = None
        self.out = self.err = ""
        self.cut = False
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        """Both pipes read to their ends together, as `communicate()` reads
        them, and decoded as its text mode decodes them; then closed, and
        `ended` set. No wait and no reap: those are the main thread's (T258e;
        Codex's review of P09 at `21dd3642`, SHOULD 6 in lane 3's numbering).
        It waits `READ_POLL_S` at a time, so it always ends once `_cancel` is
        set, `cut` then naming pipes left before their ends; and it closes
        both pipes itself, in a `finally`, whichever way it ends (T258h;
        Codex's review of P09 at `b8f9e35a`, SHOULD 4)."""
        pipes = (self.proc.stdout, self.proc.stderr)
        got = {pipe.fileno(): bytearray() for pipe in pipes}
        live = list(got)
        try:
            while live and not self._cancel.is_set():
                ready, _, _ = select.select(live, [], [], READ_POLL_S)
                for fd in ready:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        chunk = b""
                    if chunk:
                        got[fd] += chunk
                    else:
                        live.remove(fd)
        finally:
            self.cut = bool(live)
            self.out, self.err = (bytes(data).decode("utf-8", "replace").replace("\r\n", "\n")
                                  .replace("\r", "\n") for data in got.values())
            for pipe in pipes:
                pipe.close()
            if not live:
                self.ended = time.monotonic()

    def _cut_reader(self) -> None:
        """The reader joined within `END_S`; one still reading then, a process
        outside the group holding a pipe, is cut, `_cancel` set, and joined
        again: it ends within one `READ_POLL_S`, its pipes closed by itself.
        One still alive after that is raised here, so no reap follows it
        (T258h)."""
        self._thread.join(END_S)
        self._cancel.set()
        self._thread.join(END_S)
        if self._thread.is_alive():
            raise RuntimeError(f"{self.who}'s reader did not end {END_S} s after its cut")

    def _exited(self, end: float) -> bool:
        """Whether the run has exited by the monotonic `end`, as
        `os.waitid(..., WNOWAIT)` sees it, which leaves it unreaped (T258f)."""
        while os.waitid(os.P_PID, self.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
            if time.monotonic() >= end:
                return False
            time.sleep(0.05)
        return True

    def _end_unreaped(self) -> None:
        """The run's end, its reap last (T258f; the coordinator's review of P09
        at `d3a2fd5c`, item 1, #165 6938473998). While it is unreaped, the id
        of the group it leads is still its own: `_signal_unreaped` ends that
        group, TERM then KILL; then `_cut_reader` ends the reader, which closes
        both pipes itself: it is joined within `END_S`, and one still reading
        then, a process outside the group holding a pipe, is cut and joined
        again, and raised where it outlives its cut (T258h; Codex's review of
        P09 at `b8f9e35a`, SHOULD 4). This method closes no pipe. Only then is
        the run reaped, `proc.wait(END_S)`, whose `TimeoutExpired` is raised;
        no signal follows the reap, and no reap follows a reader that
        `_cut_reader` raised. `_cut_reader` runs in a `finally`, so a signal
        step that raises (`os.waitid`'s `ChildProcessError`, where something
        else reaped the run) still has the reader ended and its pipes closed
        before its error goes on, with no reap after it (T258g; Codex's review
        of P09 at `d3a2fd5c`, SHOULD 3's last point; this text T258k)."""
        try:
            _signal_unreaped(self.proc, group=True, wait=END_S)
        finally:
            self._cut_reader()
        self.proc.wait(END_S)

    def wait(self, timeout: float = 150) -> int:
        """The run's exit and its reader's end, both within one `timeout`, and
        then its reap (T258e, T258f). The exit is watched by `_exited`, which
        leaves the run unreaped, so the group it leads is still its own while
        the reader is joined. A run that does not exit in time fails the case,
        and `stop` ends it at the teardown. A run that exited while a process of
        its group still holds a pipe fails the case too, after
        `_end_unreaped` has ended that group, joined the reader, closed the
        pipes and only then reaped it."""
        end = time.monotonic() + timeout
        if self.proc.returncode is None and not self._exited(end):
            raise AssertionError(f"{self.who}'s run did not end in {timeout} s")
        self._thread.join(max(0.0, end - time.monotonic()))
        if self.proc.returncode is None and self._thread.is_alive():
            self._end_unreaped()
            raise AssertionError(f"{self.who}'s run ended, but its pipes did not end in "
                                 f"{timeout} s: its group was ended before its reap")
        assert not self._thread.is_alive(), (
            f"{self.who}'s run ended, but its pipes did not end in {timeout} s")
        self.proc.wait(END_S)
        return self.proc.returncode

    def stop(self) -> None:
        """This run's end at the case's teardown (T258e; Codex's review of P09
        at `21dd3642`, SHOULD 6 in lane 3's numbering; T258f): a run already
        reaped, `returncode` set, gets no signal, since `wait` reaps it only
        once its pipes have ended or its group has been ended. Otherwise
        `_end_unreaped` ends its group, its own since `launch` started it in a
        session of its own, while it is unreaped, joins its reader, closes its
        pipes, and only then reaps it, raising a reap that times out. Pipes
        that a process outside its group still holds are raised, not left."""
        if self.proc.returncode is None:
            self._end_unreaped()
        else:
            self._cut_reader()
        if self.cut:
            raise RuntimeError(f"{self.who}'s run is reaped, but its pipes did not end in {END_S} s: "
                               f"a process outside its group holds them")

    @property
    def code(self) -> int:
        return self.proc.returncode

    def said(self) -> str:
        """The writer for a failure's message, through bounds' one helper (T258l)."""
        return _said_safely(subprocess.CompletedProcess([], self.code, self.out, self.err))

    def _jsonl(self, name: str) -> list:
        path = self.psql_dir / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def calls(self) -> list:
        """The shim's calls that carry a request, in order."""
        return [e for e in self._jsonl(PSQL_SHIM_LOG) if e.get("kind") != "version"]

    def commit_calls(self) -> list:
        return [e for e in self.calls() if "commit_write" in (e.get("stdin") or "")]

    def lookups(self) -> list:
        return [e for e in self.calls() if "find_write" in (e.get("stdin") or "")]

    def ends(self) -> dict:
        return {e["call"]: e for e in self._jsonl(PSQL_SHIM_ENDS) if "call" in e}

    def write_ids(self) -> list:
        """Each commit call's write id, `commit_write`'s second argument, as
        T243's `Writer` reads it."""
        found = []
        for call in self.commit_calls():
            m = re.search(r"commit_write\(\s*-?[0-9]+\s*,\s*'(" + UUID_RE + ")'", call.get("stdin") or "")
            assert m, f"{self.who}'s commit call carries no write id: {(call.get('stdin') or '')[:300]}"
            found.append(m.group(1))
        return found

    def pending(self) -> list:
        where = self.state / PENDING
        return sorted(p for p in where.iterdir()
                      if re.fullmatch(r"[0-9a-f]{64}", p.name)) if where.is_dir() else []


class PhaseW:
    """AT-LRMPG's phase W on one test's managed PostgreSQL (see the section's
    head): the server, the register at `primary`, the flipped copy, and a
    workstation for each engineer."""

    def __init__(self, request, root: Path, engineers: tuple = ("e1", "e2")):
        self.root = root
        self.m = Managed(request, root / "server")
        self.service = self.m.database(W_DB)
        self.m.bootstrapped(self.service)
        self.files = self.m.logins(self.service, *engineers, dump=False)
        self.genv = self._git_env(root / "git-home")
        self.seed = _w_seed()
        self.origin = root / "origin.git"
        _w_git(root, self.genv, "init", "-q", "--bare", "-b", "main", str(self.origin))
        seed = root / "seed"
        _w_git(root, self.genv, "clone", "-q", str(self.origin), str(seed))
        for path, text in self.seed.items():
            (seed / path).parent.mkdir(parents=True, exist_ok=True)
            (seed / path).write_bytes(text.encode("utf-8"))
        _w_git(seed, self.genv, "add", "-A")
        _w_git(seed, self.genv, "commit", "-q", "-m", "C: phase W's register (T258)")
        _w_git(seed, self.genv, "push", "-q", "origin", "main")
        self.c = _w_git(seed, self.genv, "rev-parse", "HEAD").strip()
        self.lanes_tree = _w_git(seed, self.genv, "rev-parse", f"{self.c}:lanes").strip()
        self.cut = self._to_primary()
        self.bindir = root / "bin"
        flipped_copy(LANES_INDEX, self.bindir, True)
        for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
            if (REPO / name).exists():
                shutil.copy2(str(REPO / name), str(self.bindir / name))
        self.lanes_edit = self.bindir / "lanes-edit.sh"
        self.fakebin = root / "fakebin"
        self.fakebin.mkdir()
        (self.fakebin / "tmux").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (self.fakebin / "tmux").chmod(0o755)
        self.engineers = {who: self._engineer(who) for who in engineers}
        self.writers: list = []
        self._runs = itertools.count(1)
        request.addfinalizer(self._stop)

    @staticmethod
    def _git_env(home: Path) -> dict:
        home.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GIT_", "PG", "LANES_", "TMUX", "RULE6_", "FAKE_PSQL", "CLAUDE_",
                                    "PROJECTS_ROOT", "XDG_", "T224_"))}
        env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME="T258 estate", GIT_AUTHOR_EMAIL="t258@example.invalid",
                   GIT_COMMITTER_NAME="T258 estate", GIT_COMMITTER_EMAIL="t258@example.invalid",
                   LC_ALL="C")
        return env

    def _commit(self, kind: str, files: dict, **journal) -> int:
        """One entry creating `files`, committed by `commit_write` as e1's
        writer login; its seq."""
        edits, rows = _w_creates(files)
        clock = self.m.value("SELECT (clock_timestamp() + interval '60 s')::text;", W_DB)
        entry = {"journal": {"kind": kind, "verb": kind, "lane": OPERATOR, "workstation": WS,
                             "author": AUTHOR, "message": f"{kind} by {OPERATOR} (T258)", **journal},
                 "not_after": clock, "edits": edits, "files": rows}
        proc = self.m.commit(W_DB, "lanes_w_e1", self.files["lanes_w_e1"], entry)
        assert proc.returncode == 0, f"the {kind} entry did not commit:\n{_said_safely(proc)}"
        return _whole(proc.stdout.split()[-1], f"the {kind} entry's seq")

    def _to_primary(self) -> int:
        """AT-LR006's route over C, as e1's writer login: the render set's
        `import`, a `cutover` entry, then `record_marker`. The cutover's seq."""
        render = {p: t for p, t in self.seed.items() if RENDER_SET_PATH.match(p)}
        self._commit("import", render, git_commit=self.c, git_tree=self.lanes_tree)
        store = "".join(f"{line}\n" for line in (
            "store=primary", f"database={W_DB}", f"import={self.c}",
            f"lanes-tree={self.lanes_tree}", "utc=2026-11-10T00:00:00Z"))
        cut = self._commit("cutover", {STORE_PATH: store})
        client = self.m.value(f"SELECT version FROM {REGISTER}.schema_version;", W_DB)
        proc = self.m.as_login("lanes_w_e1", W_DB, f"SELECT {REGISTER}.record_marker(:client, :seq, "
                               ":'commit', :'ws');\n", self.files["lanes_w_e1"], client=client,
                               seq=cut, commit=MARKER_COMMIT, ws=W_WS)
        assert proc.returncode == 0 and proc.stdout.strip() == "present", _said_safely(proc)
        switch = self.m.value(f"SELECT mode || ' ' || marker_state FROM {REGISTER}.register_switch;",
                              W_DB)
        assert switch == "primary present", f"the register is not at primary with its marker: {switch}"
        return cut

    def _engineer(self, who: str) -> dict:
        lane, where = W_LANES[who], self.root / who
        checkout = where / "checkout"
        _w_git(self.root, self.genv, "clone", "-q", str(self.origin), str(checkout))
        home = where / "home"
        agents = home / ".agents"
        agents.mkdir(parents=True)
        (agents / "workspace.yaml").write_text(f"repository: {self.origin}\npath: {checkout}\n",
                                               encoding="utf-8")
        for name in ("t", "state", "config"):
            (where / name).mkdir()
        conf = _private(where / "conf" / "lanes-index.conf", "\n".join([
            "mode=primary",
            f"register_url={self.m.socket_url(f'lanes_w_{who}', W_DB)}",
            f"register_passfile={self.files[f'lanes_w_{who}']}",
            f"reader_url={self.m.socket_url(f'lanes_r_{who}', W_DB)}",
            f"reader_passfile={self.files[f'lanes_r_{who}']}",
            f"register_label={LABEL}", ""]))
        env = dict(self.genv)
        env.update(HOME=str(home), TMPDIR=str(where / "t"), XDG_STATE_HOME=str(where / "state"),
                   XDG_CONFIG_HOME=str(where / "config"), CLAUDE_CONFIG_DIR=str(home / ".claude"),
                   AGENT_PROTOCOL_ROOT=str(agents), LANES_WORKSTATION=W_WS, LANES_HOST="eagle",
                   LANES_OS="linux", LANES_CONTAINER="none", LANES_IN_CONTAINER="0",
                   LANES_NO_GITHUB="1", LANES_REPO=str(checkout), LANES_INDEX_CONFIG=str(conf),
                   LANES_LANE=lane, LANES_SESSION=W_SESSIONS[who])
        # THE LANE CHECKOUT, made first: on primary the writer takes `<c>` from
        # `lane_checkout_path` and refuses 2 where it does not exist, naming
        # `lane-checkout <lane> --create` (lane 4's T415, B14's text).
        # `lane-checkout` reads the register through `canon_lane`, so it is a
        # decide arm (`lanes-edit.sh:4369` at `refs/l1/V-round5`), and since
        # T504 it prefetches on primary (B15 tasks:725), which needs a `psql`:
        # T203's shim, with no arms, first on `PATH` in a directory of its
        # own, as `launch()` gives a writer (AN13a's B2; line AF13b).
        psql_dir = where / "psql-lane-checkout"
        psql_dir.mkdir()
        (psql_dir / "psql").write_text(PSQL_SHIM, encoding="utf-8")
        (psql_dir / "psql").chmod(0o755)
        (psql_dir / PSQL_SHIM_CONTROL).write_text(json.dumps(
            {"psql": str(self.m.cluster.tool("psql")), "arms": []}), encoding="utf-8")
        made = subprocess.run(["bash", str(self.lanes_edit), "lane-checkout", lane, "--create"],
                              cwd=str(checkout), capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL, check=False,
                              env=dict(env, PATH=os.pathsep.join([str(psql_dir), str(self.fakebin),
                                                                  _masked_path()])))
        assert made.returncode == 0 and Path(made.stdout.strip()).is_dir(), (
            f"lane-checkout {lane} --create did not make {who}'s lane checkout:\n{_said_safely(made)}")
        return {"lane": lane, "checkout": checkout, "env": env, "state": where / "state"}

    # -------------------------------------------------- running the client
    def launch(self, who: str, argv: list, arms: tuple = ()) -> W258Writer:
        """`lanes-edit.sh <argv>` as `who`, with T203's shim, armed with
        `arms`, first on `PATH` in a directory of its own."""
        e = self.engineers[who]
        psql_dir = self.root / f"psql-{next(self._runs):02d}-{who}"
        psql_dir.mkdir()
        (psql_dir / "psql").write_text(PSQL_SHIM, encoding="utf-8")
        (psql_dir / "psql").chmod(0o755)
        (psql_dir / PSQL_SHIM_CONTROL).write_text(json.dumps(
            {"psql": str(self.m.cluster.tool("psql")), "arms": list(arms)}), encoding="utf-8")
        env = dict(e["env"], PATH=os.pathsep.join([str(psql_dir), str(self.fakebin),
                                                   _masked_path()]))
        proc = subprocess.Popen(["bash", str(self.lanes_edit), *argv], cwd=str(e["checkout"]),
                                env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                                start_new_session=True)
        writer = W258Writer(who, proc, psql_dir, e["state"])
        self.writers.append(writer)
        return writer

    def run(self, who: str, argv: list, arms: tuple = ()) -> W258Writer:
        writer = self.launch(who, argv, arms)
        writer.wait()
        return writer

    def note(self, who: str, text: str) -> list:
        """One write: a `NOTED` line in the engineer's lane's log."""
        return ["log", "NOTED", f"lane:{W_LANES[who]}", text]

    def _stop(self) -> None:
        """Each writer's `stop` (T258e), every one tried; what any of them
        could not end is raised after."""
        failed = []
        for writer in self.writers:
            try:
                writer.stop()
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                failed.append(f"{writer.who}: {type(exc).__name__}: {exc}")
        assert not failed, "phase W's teardown did not end every writer:\n" + "\n".join(failed)

    # -------------------------------------------------- the register, read by the provider
    def journal_after(self) -> list:
        """The journal's rows after the cutover: seq, write id, lane and verb."""
        return json.loads(self.m.value(
            "SELECT coalesce(json_agg(j ORDER BY j.seq), '[]') FROM (SELECT seq, write_id::text "
            f"AS write_id, lane, verb FROM {REGISTER}.journal WHERE seq > {self.cut}) j;", W_DB))

    def state(self) -> str:
        return self.m.value(W_STATE_SQL, W_DB)


def _hold_point(fifo: Path, writer: W258Writer, timeout: float = 90):
    """`fifo` opened for writing once `writer`'s call is held on it (the
    shim's `hold`), bounded: a writer that never reaches the call fails the
    case and never hangs it. Closing the handle lets the call go (T243's)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return os.fdopen(os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK), "wb")
        except OSError as error:
            if error.errno != errno.ENXIO:
                raise
        assert writer.ended is None, (
            f"{writer.who}'s run ended before its commit call was held:\n{_said_safely(writer)}")
        assert time.monotonic() < deadline, f"{writer.who}'s commit call was not held in {timeout} s"
        time.sleep(0.05)


def _w_stand_in(who: str, script: str, *args: str) -> W258Writer:
    """A stand-in for a `lanes-edit.sh` run, `bash -c <script>` with `args`,
    started as `PhaseW.launch` starts one, in a session of its own, with no
    database (T258e's regressions)."""
    proc = subprocess.Popen(["bash", "-c", script, "bash", *args], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                            errors="replace", start_new_session=True)
    return W258Writer(who, proc, Path(os.devnull), Path(os.devnull))


def test_a_phase_w_writers_thread_only_reads_its_pipes_and_the_main_thread_reaps_it():
    """T258e (Codex's review of P09 at `21dd3642`, SHOULD 6 in lane 3's
    numbering), no database: a stand-in writer closes both its pipes, then
    ends 0.3 s later. Its reader ends at the pipes' end and leaves it
    unreaped, as `os.waitid(..., WNOWAIT)` sees once it has ended, until the
    main thread's `wait` reaps it."""

    class Phase:
        writers = [_w_stand_in("w-closes", "exec >&- 2>&-; sleep 0.3")]
    writer = Phase.writers[0]
    try:
        writer._thread.join(10)
        assert not writer._thread.is_alive(), "the reader did not end at its pipes' end"
        end, seen = time.monotonic() + 10, None
        while seen is None and time.monotonic() < end:
            try:
                seen = os.waitid(os.P_PID, writer.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            except ChildProcessError:
                seen = "reaped"
            if seen is None:
                time.sleep(0.05)
        assert seen != "reaped", "the reader thread reaped the writer: the reap is the main thread's"
        assert seen is not None, "the stand-in writer did not end in 10 s"
        code = writer.wait(10)
        assert (code, writer.out, writer.err) == (0, "", ""), f"the stand-in ended {code}, not 0"
    finally:
        PhaseW._stop(Phase)


def test_phase_w_teardown_ends_and_reaps_a_hung_writer_and_reports_a_pipe_held_outside_it(
        tmp_path, monkeypatch):
    """T258e (Codex's review of P09 at `21dd3642`, SHOULD 6 in lane 3's
    numbering), no database, with stand-in writers started as `launch`
    starts them. A writer whose pipes a process in a session of its own
    still holds: the teardown ends its group and reaps it, then raises,
    naming it, within its bounds. A hung writer whose group holds its pipes:
    `wait` fails at its bound, and the teardown ends the group, reaps the
    writer and joins its reader. A writer already reaped: the teardown sends
    no signal."""
    monkeypatch.setitem(globals(), "END_S", 2.0)

    class Phase:
        writers: list = []
    started: list = []
    try:
        mark = tmp_path / "held"
        held = _w_stand_in("w-held", '"$2" -c \'import os, sys, time; os.setsid(); '
                           'open(sys.argv[1], "w").write("held"); time.sleep(6)\' "$1" & sleep 20',
                           str(mark), sys.executable)
        started.append(held)
        end = time.monotonic() + 10
        while not (mark.exists() and mark.read_text() == "held"):
            assert time.monotonic() < end, "the stand-in's holder did not start in 10 s"
            time.sleep(0.05)
        Phase.writers = [held]
        with pytest.raises(AssertionError, match="w-held's run is reaped, but its pipes"):
            PhaseW._stop(Phase)
        assert held.proc.returncode is not None, "the teardown did not reap the writer"
        hung = _w_stand_in("w-hung", "sleep 20 & sleep 20")
        started.append(hung)
        with pytest.raises(AssertionError, match="did not end in 0.5 s"):
            hung.wait(0.5)
        Phase.writers = [hung]
        PhaseW._stop(Phase)
        assert hung.proc.returncode is not None and not hung._thread.is_alive(), (
            "the teardown did not reap the hung writer and join its reader")
        done = _w_stand_in("w-done", "exit 0")
        started.append(done)
        assert done.wait(10) == 0, "the stand-in that exits 0 did not"
        sent: list = []
        with monkeypatch.context() as patch:
            patch.setattr(os, "killpg", lambda *call: sent.append(("killpg", *call)))
            patch.setattr(os, "kill", lambda *call: sent.append(("kill", *call)))
            Phase.writers = [done]
            PhaseW._stop(Phase)
        assert sent == [], f"the teardown signalled a writer already reaped: {sent}"
    finally:
        Phase.writers = [writer for writer in started if writer.proc.returncode is None]
        PhaseW._stop(Phase)
        for writer in started:
            writer._thread.join(15)


#: T258f's stand-in writer, `bash -c` with the mark file, this Python and an
#: fd as `$1`, `$2` and `$3`: a descendant in its group closes the fd, its
#: stdout (1) or its stderr (2), writes its pid and start time (`/proc` stat
#: field 22) to the mark and sleeps 30 s, holding the other pipe; the writer
#: exits 0 once the mark is written.
T258F_STAND_IN = (
    '"$2" -c \'import os, sys, time; os.close(int(sys.argv[2])); '
    'f = open("/proc/self/stat").read().rsplit(")", 1)[1].split(); '
    'open(sys.argv[1], "w").write(f"{os.getpid()} {f[19]}"); time.sleep(30)\' "$1" "$3" & '
    'while [ ! -s "$1" ]; do sleep 0.05; done; exit 0')


def _t258f_recorded(monkeypatch, writer: W258Writer, events: list) -> None:
    """Each signal by pid or group, and each reap of `writer` with whether its
    reader is alive and its two pipes are closed at it, appended to `events`
    in order; each is still done (T258f)."""
    real_kill, real_killpg, real_wait = os.kill, os.killpg, writer.proc.wait

    def kill(pid: int, sig: int) -> None:
        events.append(("kill", pid, sig))
        real_kill(pid, sig)

    def killpg(pgid: int, sig: int) -> None:
        events.append(("killpg", pgid, sig))
        real_killpg(pgid, sig)

    def reap(*args, **kwargs):
        events.append(("reap", writer._thread.is_alive(), writer.proc.stdout.closed,
                       writer.proc.stderr.closed))
        return real_wait(*args, **kwargs)
    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(writer.proc, "wait", reap)


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="T258f's case reads Linux's /proc and pins by a pidfd")
@pytest.mark.parametrize("held", ["stdout", "stderr"])
def test_a_phase_w_writer_that_exits_while_its_group_holds_a_pipe_is_reaped_after_the_group_ends(
        tmp_path, monkeypatch, held):
    """T258f (the coordinator's review of P09 at `d3a2fd5c`, item 1, #165
    6938473998), no database: a stand-in writer, started as `launch` starts
    one, exits 0 and leaves a descendant in its group that holds its `held`
    pipe. `wait` sees the exit and leaves the writer unreaped while it joins
    the reader within its bound; the pipe is still held, so it ends the
    group while the writer is unreaped, joins the reader, closes both pipes
    and only then reaps, and fails the case, naming it. Every signal to the
    group comes before the one reap, the descendant is gone within 2 s of
    `wait`'s end, though it sleeps 30 s, the reader is joined, both pipes
    are closed, the exit is the writer's own 0, and the teardown sends no
    signal after. Before T258f `wait` reaped the writer first, so nothing
    ended its group: the reader, the pipes and the descendant were left.
    The descendant's absence counts only where it is seen before those 2 s,
    by `_gone_by`, so a pause of the case past them never turns its own
    30 s end into a pass (T258i; Codex's review of P09 at `b8f9e35a`,
    SHOULD 5: absence was accepted before the deadline was checked)."""
    monkeypatch.setitem(globals(), "END_S", 2.0)

    class Phase:
        writers: list = []
    mark = tmp_path / "descendant"
    writer = _w_stand_in(f"w-{held}", T258F_STAND_IN, str(mark), sys.executable,
                         "2" if held == "stdout" else "1")
    Phase.writers = [writer]
    events: list = []
    pid = started = None
    try:
        end = time.monotonic() + 10
        while os.waitid(os.P_PID, writer.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
            assert time.monotonic() < end, f"[{held}] the stand-in writer did not exit in 10 s"
            time.sleep(0.05)
        pid, started = mark.read_text().split()
        _t258f_recorded(monkeypatch, writer, events)
        with pytest.raises(AssertionError, match=f"w-{held}'s run ended, but its pipes did not"):
            writer.wait(1.0)
        gone = _gone_by(_whole(pid, "the stand-in's pid"), started, time.monotonic() + 2)     # seen before it (T258i)
        kinds = [event[0] for event in events]
        ordered = kinds.count("reap") == 1 and kinds[-1] == "reap" and "killpg" in kinds
        assert ordered and events[-1][1:] == (False, True, True), (
            f"[{held}] the writer was not reaped once, after every signal to its group, with "
            f"its reader joined and both pipes closed: {events}")
        assert gone, f"[{held}] the descendant holding the writer's {held} was not ended"
        code = writer.proc.returncode
        assert code == 0, f"[{held}] the writer's exit is {code}, not its own 0"
        events.clear()
        PhaseW._stop(Phase)
        assert events == [], f"[{held}] the teardown signalled a writer already reaped: {events}"
    finally:
        if pid is not None:
            _end_if_left(_whole(pid, "the stand-in's pid"), started)
        Phase.writers = [writer] if writer.proc.returncode is None else []
        PhaseW._stop(Phase)
        writer._thread.join(15)


def test_a_phase_w_writers_stop_joins_its_reader_and_closes_its_pipes_when_its_signal_step_raises(
        tmp_path, monkeypatch):
    """T258g (Codex's review of P09 at `d3a2fd5c`, SHOULD 3's last point:
    `stop()` skipped its join when `_end_process()` raised), no database: a
    stand-in writer, started as `launch` starts one, holds both pipes until
    a FIFO barrier is released, then 0.3 s more, closes them and lives 0.5 s
    more. Its `stop()` runs with the signal step, `_end_process` or
    `_signal_unreaped`, made to raise `ChildProcessError` as `os.waitid`
    does where something else reaped the run. That step, the signal seam,
    is reached once: it records the reader alive and both pipes open, then
    raises. The barrier is released at the reader's first join, by a wrapper
    set as `writer._thread.join`, and only the clean-up after the seam joins
    the reader. The error must reach the caller, and by then the reader must
    be joined and both pipes closed. Before T258g the error left `stop()`
    before the join, with the reader still reading and both pipes open; with
    that bug no join runs, so the barrier is never released and the case
    fails whatever the timing. The barrier replaces a 0.5 s sleep from the
    stand-in's start, which a delayed case could outlive, so the old code
    passed (T258j; Codex's review of P09 at `b8f9e35a`, SHOULD 6). T258j
    released it at the seam, so a stall of 0.3 s or more after the seam
    could still let the old code pass; it is released at the join instead
    (T258k; lane 2's pre-review RV9-35, NIT 1)."""
    monkeypatch.setitem(globals(), "END_S", 2.0)
    barrier, seen = tmp_path / "barrier", []
    os.mkfifo(barrier)

    def release() -> None:
        """The barrier released: a line written to it, opened without
        blocking once the stand-in has it open to read, within 10 s."""
        end = time.monotonic() + 10
        while True:
            try:
                fd = os.open(barrier, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError as exc:
                assert exc.errno == errno.ENXIO and time.monotonic() < end, (
                    f"the stand-in did not open its barrier in 10 s: {exc}")
                time.sleep(0.05)
        try:
            os.write(fd, b"go\n")
        finally:
            os.close(fd)

    def fails(*args, **kwargs):
        seen.append((writer._thread.is_alive(), writer.proc.stdout.closed,
                     writer.proc.stderr.closed))
        raise ChildProcessError("T258g's stand-in: the run was reaped elsewhere")

    def joins(timeout=None):
        """The reader's join, the barrier released at its first call (T258k)."""
        if not released:
            released.append(True)
            release()
        return join(timeout)
    writer = _w_stand_in("w-raises", 'read -r _ < "$1"; sleep 0.3; exec >&- 2>&-; sleep 0.5',
                         str(barrier))
    join, released = writer._thread.join, []

    class Phase:
        writers = [writer]
    try:
        with monkeypatch.context() as patch:
            patch.setitem(globals(), "_end_process", fails)
            patch.setitem(globals(), "_signal_unreaped", fails)
            patch.setattr(writer._thread, "join", joins)
            with pytest.raises(ChildProcessError, match="reaped elsewhere"):
                writer.stop()
            state = (writer._thread.is_alive(), writer.proc.stdout.closed,
                     writer.proc.stderr.closed)
        assert seen == [(True, False, False)], (
            f"at the signal seam the reader alive, stdout closed and stderr closed are {seen}, "
            f"not once (True, False, False)")
        assert state == (False, True, True), (
            f"stop()'s signal step raised, and the reader alive, stdout closed and stderr "
            f"closed are {state}, not (False, True, True)")
    finally:
        Phase.writers = [writer] if writer.proc.returncode is None else []
        PhaseW._stop(Phase)
        writer._thread.join(15)


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="T258h's case reads Linux's /proc and pins by a pidfd")
def test_a_phase_w_writers_reader_cut_by_a_pipe_held_outside_its_group_ends_and_closes_before_the_reap(
        tmp_path, monkeypatch):
    """T258h (Codex's review of P09 at `b8f9e35a`, SHOULD 4), no database: a
    stand-in writer, started as `launch` starts one, exits 0 and leaves a
    descendant in a session of its own, outside the writer's group, holding
    its stdout; T258f's stand-in run under `setsid`. Its `stop()` ends the
    group, which does not reach the holder, and the reader cannot reach the
    pipe's end: it must be cut, end and close both pipes itself before the
    one reap, and `stop()` must raise the held pipe. Before T258h the reader
    blocked with no timeout: the writer was reaped with its reader alive and
    both pipes open, and they stayed so."""
    monkeypatch.setitem(globals(), "END_S", 2.0)
    mark = tmp_path / "descendant"
    writer = _w_stand_in("w-outside", f"setsid {T258F_STAND_IN}", str(mark), sys.executable, "2")

    class Phase:
        writers = [writer]
    events: list = []
    pid = started = None
    try:
        end = time.monotonic() + 10
        while os.waitid(os.P_PID, writer.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
            assert time.monotonic() < end, "the stand-in writer did not exit in 10 s"
            time.sleep(0.05)
        pid, started = mark.read_text().split()
        assert os.getsid(_whole(pid, "the stand-in's pid")) != writer.proc.pid, "the holder is in the writer's session"
        _t258f_recorded(monkeypatch, writer, events)
        with pytest.raises(RuntimeError, match="a process outside its group holds them"):
            writer.stop()
        reaps = [event for event in events if event[0] == "reap"]
        state = (reaps, writer._thread.is_alive())
        assert state == ([("reap", False, True, True)], False), (
            f"with its stdout held outside its group, the writer's reaps (reader alive, stdout "
            f"closed, stderr closed at each) and its reader alive are {state}")
    finally:
        if pid is not None:
            _end_if_left(_whole(pid, "the stand-in's pid"), started)
        Phase.writers = [writer] if writer.proc.returncode is None else []
        PhaseW._stop(Phase)
        writer._thread.join(15)


def test_two_writer_logins_write_alike_and_the_log_names_each(tmp_path, request):
    """Two writer logins (section 1.4, "One engineer's logins"): E1 and E2,
    each with its own `register_url=` and password file, each make one
    write, and both commit as one login does: one journal row each, at
    consecutive seqs. The server's log ties each commit call, by its
    backend's pid, to its `connection authorized` line, which names E1 or E2
    (`operations.md` act 3's step 1, "Who connected")."""
    w = PhaseW(request, tmp_path)
    marks = [len(w.m.log())]
    writers = []
    for who in ("e1", "e2"):
        writer = w.run(who, w.note(who, f"{who}'s write (T258)"))
        assert writer.code == 0, f"{who}'s write on primary did not exit 0:\n{_said_safely(writer)}"
        writers.append(writer)
        marks.append(len(w.m.log()))
    rows = w.journal_after()
    assert [r["lane"] for r in rows] == [W_LANES["e1"], W_LANES["e2"]], (
        f"the journal after the cutover (seq {w.cut}) is not one row each, e1's then e2's: {rows}")
    assert [r["seq"] for r in rows] == [w.cut + 1, w.cut + 2], (
        f"the two writes are not at consecutive seqs after the cutover's {w.cut}: {rows}")
    for writer, row in zip(writers, rows):
        assert row["write_id"] in writer.write_ids(), (
            f"{writer.who}'s row {row} is not its commit call's write id {writer.write_ids()}")
    log = w.m.log()
    for k, who in enumerate(("e1", "e2")):
        logins = _commit_logins(log[marks[k]:marks[k + 1]])
        assert logins and set(logins) == {f"lanes_w_{who}"}, (
            f"the server's log ties {who}'s commit calls to {logins or 'no commit call'}, "
            f"not to lanes_w_{who}'s connection authorized line")


#: AT-LRMPG's revoked login: `[revoke]`, `lanes-index login revoke e2`; and
#: `[membership-only]`, the revoke block's step 2 alone, by the admin's hand.
#: Each: the words a new connection by each refused login is refused with.
REVOKED = {
    "revoke": {"lanes_w_e2": "is not permitted to log in", "lanes_r_e2": "is not permitted to log in"},
    "membership-only": {"lanes_w_e2": "permission denied for database"},
}


@pytest.mark.parametrize("case", list(REVOKED))
def test_a_revoked_login_is_refused_69_and_writes_nothing(tmp_path, request, case):
    """A revoked login (section 1.4, "What a revoked login sees"; section
    2.4's `revoke`), while a session of `lanes_w_e2` is open and idle, held
    by the test. `[revoke]`: `login revoke e2` prints each step's result; a
    new connection by either of e2's logins is refused, FATAL 28000, so e2's
    write exits 69 with nothing written, since the snapshot sent nothing that
    writes, and e2's read exits 69 (S3's table); the open session's next
    statement gets FATAL 57P01, or a lost connection, and never 42501 or an
    answer; the admin, with no superuser, needed no `pg_signal_backend`; both
    roles still exist; e1 still writes. `[membership-only]`: the revoke
    block's step 2 alone, by the admin, so `lanes_w_e2` keeps `LOGIN` and
    loses its membership: a new connection is refused, FATAL 42501,
    "permission denied for database", and e2's write exits 69 with nothing
    written."""
    w = PhaseW(request, tmp_path)
    m = w.m
    held = m.session("lanes_w_e2", W_DB, w.files["lanes_w_e2"])
    assert "ERROR" not in held.send("SELECT 'open';", "t258-open"), "e2's session did not open"
    if case == "revoke":
        proc = m.login("revoke", "e2", w.service)
        assert proc.returncode == 0, f"login revoke e2 failed:\n{_said_safely(proc)}"
        for login in ("lanes_w_e2", "lanes_r_e2"):
            for step in (1, 2, 3):
                assert re.search(rf"^login {login}, step {step}, ", proc.stdout, re.M), (
                    f"login revoke printed no result for {login}'s step {step}:\n{_said_safely(proc)}")
    else:
        m.psql(f"REVOKE {WRITER} FROM lanes_w_e2;\n", W_DB, user=ADMIN)
        role = m.role("lanes_w_e2")
        assert role["canlogin"] and role["groups"] == [], (
            f"step 2 alone did not keep LOGIN and take the membership: canlogin {role.get('canlogin')}, "
            f"groups {role.get('groups')}")
    for login, words in REVOKED[case].items():
        refused = m.as_login(login, W_DB, "SELECT 1;\n", w.files[login])
        assert refused.returncode == 2 and words in refused.stderr, (
            f"[{case}] a new connection by {login} is not refused with {words!r}:\n{_said_safely(refused)}")
    before = w.state()
    write = w.run("e2", w.note("e2", f"e2's write after [{case}] (T258)"))
    assert write.code == 69, f"[{case}] e2's write on primary did not exit 69:\n{_said_safely(write)}"
    assert write.commit_calls() == [], (
        f"[{case}] e2's refused write sent a commit call: the snapshot must send nothing that writes")
    assert w.state() == before, f"[{case}] e2's refused write changed the register"
    if case != "revoke":
        held.close()
        return
    read = w.run("e2", ["binding", W_LANES["e2"]])
    assert read.code == 69 and read.out == "", f"e2's read on primary did not exit 69:\n{_said_safely(read)}"
    said = held.send(f"SELECT {REGISTER}.commit_write(NULL, NULL, NULL, NULL, NULL);", "t258-next")
    ended = held.close()
    said += ended.stderr
    assert ("57P01" in said or "terminating connection due to administrator command" in said
            or "server closed the connection" in said), (
        f"the open session's next statement after the revoke was not ended: its stderr then and at its "
        f"end, {_said_safely(said, stream='stderr')}; its end, {_said_safely(ended)}")
    assert "42501" not in said and "permission denied" not in said, (
        f"the open session's next statement got 42501, so revoke returned between its steps: its stderr "
        f"then and at its end, {_said_safely(said, stream='stderr')}; its end, {_said_safely(ended)}")
    assert ended.stdout.split() == ["open"], f"the open session got an answer after the revoke: {_said_safely(ended)!r}"
    assert m.value("SELECT count(*) FROM pg_roles WHERE rolname IN ('lanes_w_e2', 'lanes_r_e2');",
                   "postgres") == "2", "a revoked login's role was dropped"
    assert m.role(ADMIN)["super"] is False and m.value(
        f"SELECT pg_has_role('{ADMIN}', 'pg_signal_backend', 'MEMBER');", "postgres") == "f", (
        f"{ADMIN} is a superuser or holds pg_signal_backend: the case proves nothing of the revoke")
    mine = w.run("e1", w.note("e1", "e1 still writes after e2's revoke (T258)"))
    assert mine.code == 0, f"e1's write after e2's revoke did not exit 0:\n{_said_safely(mine)}"
    assert [r["lane"] for r in w.journal_after()] == [W_LANES["e1"]], (
        f"e1's write is not the journal's one new row: {w.journal_after()}")


def test_a_write_cut_by_a_revoke_mid_commit_is_in_doubt_and_ends_3_with_nothing_written(
        tmp_path, request):
    """`[mid-commit]` (section 2.4's `revoke`): the shim's `hold` blocks e2's
    commit call while `login revoke e2` runs, then releases it: its `psql`
    is refused at login and exits 2, which section 1.3's signals table makes
    in doubt for a commit call; its lookup's tries are refused at login too,
    and it exits 3 naming the id, the pending record kept. The journal holds
    no entry for the id, and so answers it; nothing is written. The journal
    is read here by the provider, the cluster's superuser."""
    w = PhaseW(request, tmp_path)
    gate = tmp_path / "mid-commit.fifo"
    os.mkfifo(str(gate))
    before = w.state()
    writer = w.launch("e2", w.note("e2", "e2's write cut mid-commit (T258)"),
                      arms=({"mode": "hold", "match": "commit_write", "call": 1, "fifo": str(gate)},))
    held = _hold_point(gate, writer)
    try:
        revoke = w.m.login("revoke", "e2", w.service)
    finally:
        held.close()
    assert revoke.returncode == 0, f"login revoke e2 failed:\n{_said_safely(revoke)}"
    writer.wait(timeout=150)
    assert writer.code == 3, f"e2's write cut mid-commit did not exit 3:\n{_said_safely(writer)}"
    ids = writer.write_ids()
    assert ids and len(set(ids)) == 1, f"e2's commit calls carried {ids}, not one write id"
    write_id = ids[0]
    assert write_id in writer.err, f"exit 3 does not name the write id {write_id}:\n{_said_safely(writer)}"
    ends = writer.ends()
    first = writer.commit_calls()[0]["call"]
    assert ends.get(first, {}).get("exit") == 2, (
        f"the held commit call's psql was not refused at login with exit 2: {ends.get(first)}")
    tries = writer.lookups()
    assert tries and all(ends.get(t["call"], {}).get("exit") == 2 for t in tries), (
        f"the lookup's tries were not each refused at login: {[ends.get(t['call']) for t in tries]}")
    records = writer.pending()
    assert len(records) == 1 and write_id in records[0].read_text(encoding="utf-8"), (
        f"the pending record naming {write_id} was not kept: {records}")
    assert w.m.value(f"SELECT count(*) FROM {REGISTER}.journal WHERE write_id = '{write_id}';",
                     W_DB) == "0", f"the journal holds an entry for the id {write_id}"
    assert w.state() == before, "the write cut mid-commit changed the register"


#: `target_session_attrs` (M5): each id's login, the value in its URL, and
#: whether it gets in and reads `register_head`.
TARGET_SESSION_ATTRS = {
    "primary": ("lanes_r_e1", "primary", True),
    "read-write": ("lanes_r_e1", "read-write", False),
    "read-write-bare-member": ("lanes_r_bare", "read-write", True),
}


@pytest.mark.parametrize("case", list(TARGET_SESSION_ATTRS))
def test_reader_url_takes_target_session_attrs_primary_not_read_write(tmp_path, request, case):
    """`target_session_attrs` (M5; section 1.4, "TLS and the endpoint"):
    `lanes_r_e1`'s `psql` with `target_session_attrs=primary` in its URL
    connects and reads `register_head`; with `read-write`, the connection is
    refused with libpq's `session is read-only`, since the login step made
    its sessions read-only by default. `lanes_r_bare`, a member made without
    the step, is let in by `read-write`: the floor is the login's own, since
    `ALTER ROLE ... SET` binds the role it names and not its members."""
    login, attrs, gets_in = TARGET_SESSION_ATTRS[case]
    m = Managed(request, tmp_path)
    service = m.database(W_DB)
    m.bootstrapped(service)
    files = m.logins(service, "e1", dump=False)
    if login == "lanes_r_bare":
        password = uuid.uuid4().hex
        m.psql(f"CREATE ROLE {login} LOGIN PASSWORD '{password}';\nGRANT {READER} TO {login};\n")
        files[login] = _private(m.home / "passfiles" / login, f"*:*:{W_DB}:{login}:{password}\n")
    env = {k: v for k, v in m.env.items() if not k.startswith("PG")}
    env.update(PGPASSFILE=str(files[login]), PGCONNECT_TIMEOUT="10")
    url = f"{m.socket_url(login, W_DB)}?target_session_attrs={attrs}"
    proc = subprocess.run([m.cluster.tool("psql"), "-X", "-q", "-A", "-t", "-w", "-v", "ON_ERROR_STOP=1",
                           "-d", url, "-c", f"SELECT seq FROM {REGISTER}.register_head;"],
                          capture_output=True, text=True, timeout=60, env=env, check=False)
    head = m.value(f"SELECT seq FROM {REGISTER}.register_head;", W_DB)
    if gets_in:
        assert proc.returncode == 0 and proc.stdout.strip() == head, (
            f"[{case}] {login} with target_session_attrs={attrs} did not read the head {head}:\n"
            f"{_said_safely(proc)}")
    else:
        assert proc.returncode == 2 and "session is read-only" in proc.stderr, (
            f"[{case}] {login} with target_session_attrs={attrs} was not refused with "
            f"`session is read-only`:\n{_said_safely(proc)}")


def test_after_login_rotate_the_old_password_files_write_exits_69_and_the_new_lines_commit_once(
        tmp_path, request):
    """Rotate's write half (TP:5317-5318; lane 3's batch 7, lane 2's item
    (3)): after `login rotate e1`, e1's write with the old password file
    exits 69 at its snapshot, since a refused login is "refused in any other
    way" (CLI:336), and the journal gains nothing; with the new lines written
    into the files e1's configuration names, the write exits 0 and commits
    once."""
    w = PhaseW(request, tmp_path, engineers=("e1",))
    proc = w.m.login("rotate", "e1", w.service)
    assert proc.returncode == 0, f"login rotate e1 failed:\n{_said_safely(proc)}"
    new = _passwords(proc.stdout)
    assert sorted(new) == ["lanes_r_e1", "lanes_w_e1"], _said_safely(proc)
    before = w.state()
    old = w.run("e1", w.note("e1", "e1's write with the old password file (T258)"))
    assert old.code == 69, f"e1's write with the old password file did not exit 69:\n{_said_safely(old)}"
    assert old.commit_calls() == [], "e1's refused write sent a commit call: the 69 is the snapshot's"
    assert w.state() == before, "e1's refused write changed the register"
    for login, line in new.items():
        _private(w.files[login], line + "\n")
    wrote = w.run("e1", w.note("e1", "e1's write with the new lines (T258)"))
    assert wrote.code == 0, f"e1's write with the new lines did not exit 0:\n{_said_safely(wrote)}"
    rows = w.journal_after()
    assert [r["lane"] for r in rows] == [W_LANES["e1"]], f"the journal did not gain one row, e1's: {rows}"
    assert set(wrote.write_ids()) == {rows[0]["write_id"]}, (
        f"the row's write id is not the one e1's commit calls carried: {wrote.write_ids()}")
