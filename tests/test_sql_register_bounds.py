# SPDX-License-Identifier: Apache-2.0
"""Feature 007's test D9, the timeouts table, its phase-N rows (AT-D9, L2-N5;
section 4.4; T220), and lane 1's T106 case (R-F9-3)
(opensoft/openRepoTools#165).

LANE 1'S T106 ALONE, `test_postgres_store_register_roles_connect_by_their_own_
url_with_one_joined_request` (R-F9-3; lane 1, #165 6752661856), needs no
engine. It loads `lanes-index` in process, as `test_lanes_index.py`'s
`load_indexer` does, puts T203's register fake `psql` first on `PATH` behind
this module's `--version` wrapper, sets an inherited `PGHOSTADDR`,
`PGSSLMODE=disable`, `PGOPTIONS` and `PGTARGETSESSIONATTRS`, and makes one
`request(statements, row)` call of two statements through
`PostgresStore(cfg, role)`. It fails until lane 1's T106 lands: at `a2073eae`
`load_config` does not know `register_url=`, and `PostgresStore` has no
register role. Its `[J3]` word is `sql_register_bounds and
postgres_store_register_roles`.

- THE `--version` WRAPPER (`VERSION_WRAPPER`): T106 asks `psql --version` once
  per process (L1v4.10:152), and T203's fake as built does not answer it. The
  wrapper answers `psql (PostgreSQL) 16.4`, logs the probe apart, and hands
  every other call to the fake, whose log then holds only the calls that
  carry a request. Lane 2's T203b gives the fake that answer; this wrapper
  goes once it is in.

D9'S PHASE-N ROWS are real-engine tests, on `tests/pgcluster.py`'s `pg`. The
test plan names the rows but gives them no ids, so each row has a word that
leads its id (the block's T220): `guard`, `answer-2`, `reader`,
`renderer-reads`, `reconcile`, `import`, `status`, `migration`,
`outage-probe` and `mode-query` here. T257, T278 and T237 add theirs to the
same two functions. The faults (AT-D9, "Fixture"):

- F1, a listener on loopback that accepts and never speaks (`SilentListener`);
- F2, a relay to the cluster's socket that goes silent once the startup has
  completed, at the server's first ReadyForQuery (`StartupRelay`);
- F3, an `ALTER TABLE` in an open transaction of the test's own session on
  the table the path reads;
- F4, a slow statement the test creates in its own database: a row-level
  security policy that sleeps, for the path's group role. F4 is the second
  function's, `test_a_slow_statement_meets_57014_before_the_client_timer`.

`c` is 2 s and `N_a` 1: no configuration sets `connect_timeout=` or
`register_addresses=`. Each bound is asserted at twice its value, and the
guard's two rows under 4.5 s strictly; each measured time is recorded with
its margin (section 1.2's timing rules 1 to 3). The paths are lane 1's
commands, and lane 5's guard through `lanes-edit.sh guard`, from T203's
flipped copy where the path reads on primary. They fail until L1-A2, L1-A13,
L1-A15, L1-A18 and L5-A3 land, on T227's template and T228's logins; until
T228 a path's login is made here, in the row's group role.

THE TIMING WRAPPER (`TIMING_PSQL`): T203's shim records neither a call's
start time nor its stderr, so F4's oracle, "the call ending with 57014 ... no
earlier than the path's `statement_timeout` after the call's start", reads
this module's own wrapper in front of the real `psql`, which logs each
call's start and end on the monotonic clock and its stderr's first line.
"""

from __future__ import annotations

import json
import os
import pty
import re
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

INDEXER = REPO / "lanes-index"
LANES_EDIT = REPO / "lanes-edit.sh"
SCHEMA = "lanes_register"
#: `c` and `N_a` when no configuration sets them (D9; CLI4.10 section 2.4).
C, N_A = 2, 1

# =============================================================== lane 1's T106

#: Two statements, sent as ONE request (CLI4.10 section 2.3).
STATEMENTS = ["SELECT seq FROM register_head", "SELECT mode, marker_state FROM register_switch"]
#: CLI4.10:206, "the argv is §2.2's exactly" (lane 1, #165 6752661856).
REGISTER_ARGV = ["--no-psqlrc", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                 "-v", "VERBOSITY=verbose", "-v", "SHOW_CONTEXT=never"]
#: Inherited by the caller, and never to reach `psql` on a register path
#: (L1v4.10:147; lane 3's R-PG-1; NOTES question 26).
INHERITED = {"PGHOSTADDR": "192.0.2.9", "PGSSLMODE": "disable",
             "PGOPTIONS": "-c search_path=inherited", "PGTARGETSESSIONATTRS": "read-write"}
#: Each role: `PostgresStore`'s role, a D9 row of that role (T106's
#: `REGISTER_BOUNDS`: a writer's snapshot, a reader's read), and the keys and
#: login its connection comes from (L1v4.10:148-149; CLI4.10:211-214).
ROLES = {
    "register-writer": ("register_writer", "snapshot", "register_url", "register_passfile",
                        "t220_writer"),
    "register-reader": ("register_reader", "read", "reader_url", "reader_passfile",
                        "t220_reader"),
}

VERSION_WRAPPER = r'''#!/usr/bin/env python3
# T220's `psql --version` wrapper: the version T106 asks for once per process
# (L1v4.10:152), logged apart; every other call goes to T203's register fake.
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
if sys.argv[1:] == ["--version"]:
    with open(os.path.join(here, "psql-version.log"), "a", encoding="utf-8") as handle:
        handle.write("--version\n")
    sys.stdout.write("psql (PostgreSQL) 16.4\n")
    sys.exit(0)
fake = os.path.join(here, "register-fake-psql")
os.execv(fake, [fake] + sys.argv[1:])
'''


def load_indexer():
    """`lanes-index` as a module, fresh, as `test_lanes_index.py` loads it.
    Called inside a test, never at import."""
    import importlib.util
    loader = SourceFileLoader("lanes_index_bounds_module", str(INDEXER))
    spec = importlib.util.spec_from_loader("lanes_index_bounds_module", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _private(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("role", list(ROLES))
def test_postgres_store_register_roles_connect_by_their_own_url_with_one_joined_request(
        tmp_path, monkeypatch, role):
    """T106 alone (R-F9-3): one `request(statements, row)` call of two
    statements through `PostgresStore(cfg, role)` is ONE `psql` call that
    carries the request; its argv is exactly CLI4.10's list, with no `-d`
    and no URL; its connection is the role's own URL and password file, the
    reader's never the writer's; no inherited `PGHOSTADDR`, `PGSSLMODE` or
    `PGTARGETSESSIONATTRS` reaches it, and `PGOPTIONS` is not the inherited
    value; and its stdin is the two statements joined by `\\;`. Each URL is
    a loopback host with no query parameter, and each configuration carries
    `register_url=`, the reader's too, since a file with none is #160's.

    NOT ASSERTED HERE, PENDING LANE 2'S ANSWER: F9b's `search_path` oracle
    (L1v4.10:150) and its `COPY` marker oracle (CLI4.10:234; L1v4.10:151).
    T106's `request()` sends only the statements it is given; both are the
    snapshot's statements (`_query_many` with a `row`), which F9b's NOTES
    question 27 (a) keeps out of this case."""
    from sql_register_helpers import REGISTER_FAKE_PSQL
    store_role, row, url_key, pass_key, login = ROLES[role]
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, text in (("register-fake-psql", REGISTER_FAKE_PSQL), ("psql", VERSION_WRAPPER)):
        (bindir / name).write_text(text, encoding="utf-8")
        (bindir / name).chmod(0o755)
    passfiles = {"register_passfile": _private(tmp_path / "writer.pgpass"),
                 "reader_passfile": _private(tmp_path / "reader.pgpass")}
    config = _private(tmp_path / "conf" / "lanes-index.conf", "\n".join([
        "mode=index",
        "register_url=postgresql://t220_writer@127.0.0.1:55432/register_db",
        f"register_passfile={passfiles['register_passfile']}",
        "reader_url=postgresql://t220_reader@127.0.0.1:55432/register_db",
        f"reader_passfile={passfiles['reader_passfile']}",
        "register_schema=lanes_register_t220",
        ""]))
    log = tmp_path / "psql.log"
    for key in list(os.environ):
        if key.startswith("PG") or key in ("FAKE_PSQL_ANSWERS", "FAKE_PSQL_VERSION_FILE"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("LANES_INDEX_CONFIG", str(config))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("FAKE_PSQL_LOG", str(log))
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", os.defpath))
    for key, value in INHERITED.items():
        monkeypatch.setenv(key, value)

    mod = load_indexer()
    error = None
    try:
        store = mod.PostgresStore(mod.load_config(), store_role)
        store.request(list(STATEMENTS), row)
    except Exception as exc:  # the code under test, not this test, failed
        error = exc
    assert error is None, (f"PostgresStore(cfg, {store_role!r}).request(<2 statements>, "
                           f"{row!r}) raised {error!r}")

    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    calls = [r for r in records if r["argv"] != ["--version"]]
    assert len(calls) == 1, f"one psql call carries the request: {len(calls)}"
    call = calls[0]
    assert "refused" not in call, call["refused"]
    assert call["argv"] == REGISTER_ARGV
    pg = call["pg"]
    assert (pg.get("PGHOST"), pg.get("PGPORT"), pg.get("PGDATABASE"), pg.get("PGUSER")) == \
        ("127.0.0.1", "55432", "register_db", login), f"{url_key}='s mapping: {pg}"
    assert pg.get("PGPASSFILE") == str(passfiles[pass_key])
    other = "reader_passfile" if pass_key == "register_passfile" else "register_passfile"
    assert pg.get("PGPASSFILE") != str(passfiles[other])
    for key in ("PGHOSTADDR", "PGSSLMODE", "PGTARGETSESSIONATTRS"):
        assert key not in pg, f"the inherited {key} reached psql: {pg[key]!r}"
    assert pg.get("PGOPTIONS") != INHERITED["PGOPTIONS"], "the inherited PGOPTIONS reached psql"
    request = call["stdin"].strip()
    assert request.endswith(";") and "\n" not in request, f"one request: {call['stdin']!r}"
    assert [part.strip() for part in request[:-1].split("\\;")] == STATEMENTS
    probes = bindir / "psql-version.log"
    assert not probes.exists() or len(probes.read_text().splitlines()) <= 1, \
        "psql --version is asked once per process"


# ====================================================== D9's rows (real engine)

class SilentListener:
    """F1: a listener on loopback, port 0, that accepts and never speaks."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]
        self.held, self.done = [], False
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        self.sock.settimeout(0.2)
        while not self.done:
            try:
                conn, _ = self.sock.accept()
                self.held.append(conn)
            except OSError:
                continue

    def close(self):
        self.done = True
        for conn in self.held:
            conn.close()
        self.sock.close()


class StartupRelay(SilentListener):
    """F2: a relay on loopback to the cluster's Unix socket that forwards
    until the startup completes, at the server's first ReadyForQuery
    (`Z`, length 5), then goes silent, holding both ends open."""

    READY = re.compile(rb"Z\x00\x00\x00\x05[ITE]")

    def __init__(self, unix_path: str):
        self.unix_path = unix_path
        super().__init__()

    def _accept(self):
        self.sock.settimeout(0.2)
        while not self.done:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            upstream.connect(self.unix_path)
            self.held += [conn, upstream]
            threading.Thread(target=self._pump, args=(conn, upstream), daemon=True).start()

    def _pump(self, client, server):
        seen, silent = b"", False
        while not self.done:
            ready, _, _ = select.select([client, server], [], [], 0.2)
            for end in ready:
                try:
                    data = end.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                if silent:
                    continue
                if end is server:
                    seen = (seen + data)[-64:]
                    (client.sendall(data))
                    if self.READY.search(seen):
                        silent = True
                else:
                    server.sendall(data)


TIMING_PSQL = r'''#!/usr/bin/env python3
# T220's timing wrapper in front of the real psql: each call's start and end
# on the monotonic clock, its exit and its stderr's first line, one JSON
# object per call in psql-timing.log beside it.
import json, os, subprocess, sys, time
here = os.path.dirname(os.path.abspath(__file__))
real = os.environ["T220_REAL_PSQL"]
data = sys.stdin.buffer.read() if sys.argv[1:] != ["--version"] else b""
start = time.monotonic()
proc = subprocess.run([real] + sys.argv[1:], input=data, capture_output=True)
end = time.monotonic()
err = proc.stderr.decode("utf-8", "replace")
with open(os.path.join(here, "psql-timing.log"), "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"argv": sys.argv[1:], "start": start, "end": end,
                             "exit": proc.returncode,
                             "first": (err.strip().splitlines() or [""])[0]}) + "\n")
sys.stdout.buffer.write(proc.stdout)
sys.stderr.buffer.write(proc.stderr)
sys.exit(proc.returncode)
'''

#: FAKE `tmux` for the guard's rows: the window is the lane.
FAKE_TMUX = """#!/bin/sh
case "$*" in *display-message*) printf '%s\\n' "${T220_WINDOW:-repoA-2}" ;; esac
exit 0
"""

#: D9'S PHASE-N ROWS (AT-D9's table; the block's T220): the word that leads
#: each id; how the path runs; the group role its login is in; its expected
#: exit; the design's bound on the elapsed time in s; whether that bound is
#: the guard's, strict (timing rule 1), or asserted at twice its value (rule
#: 2); the faults the first function gives it; its `statement_timeout` in ms
#: where it sets one (F4, the second function's); and the table its reads
#: wait on. `import` runs FP only for its 330 s timer, and has F1 alone.
ROWS = {
    "guard":          dict(group="lanes_register_reader", exit=2, bound=4.5, strict=True,
                           faults=("F1", "F2", "F3"), statement_ms=1500, table="register_head"),
    "answer-2":       dict(group="lanes_register_reader", exit=2, bound=4.5, strict=True,
                           faults=("F1",), statement_ms=None, table=None),
    "reader":         dict(group="lanes_register_reader", exit=69, bound=6, strict=False,
                           faults=("F1", "F2", "F3"), statement_ms=3000, table="register_head"),
    "renderer-reads": dict(group="lanes_register_reader", exit=None, bound=15, strict=False,
                           faults=("F1", "F2", "F3"), statement_ms=10000, table="register_head"),
    "reconcile":      dict(group="lanes_register_reader", exit=69, bound=15, strict=False,
                           faults=("F1", "F2", "F3"), statement_ms=10000, table="register_head"),
    "import":         dict(group="lanes_register_writer", exit=69, bound=330, strict=False,
                           faults=("F1",), statement_ms=None, table=None),
    "status":         dict(group="lanes_register_reader", exit=69, bound=8, strict=False,
                           faults=("F1", "F2", "F3"), statement_ms=5000, table="register_head"),
    "migration":      dict(group=None, exit=None, bound=None, strict=False,
                           faults=("F1",), statement_ms=None, table="register_head"),
    "outage-probe":   dict(group="lanes_register_writer", exit=0, bound=8, strict=False,
                           faults=("F1", "F2", "F3"), statement_ms=5000, table="register_switch"),
    "mode-query":     dict(group=None, exit=0, bound=2, strict=False,
                           faults=("F1",), statement_ms=None, table=None),
}

FIRST_CASES = [f"{row}-{fault}" for row, spec in ROWS.items() for fault in spec["faults"]]
SLOW_ROWS = [row for row, spec in ROWS.items() if spec["statement_ms"] and row != "import"]


class Bench:
    """One test's bench: a scratch workspace with a bare origin, a copy of
    `lanes-edit.sh` beside T203's flipped `lanes-index` (the copy rule, CLI4.5
    section 6), a configuration naming the endpoint the fault gives, a login
    of the row's group where it needs one, and the timing wrapper first on
    `PATH`."""

    def __init__(self, pg, tmp_path: Path, request):
        from sql_register_helpers import flipped_copy
        self.pg, self.root = pg, tmp_path
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.copy = flipped_copy(INDEXER, tmp_path / "tool", True)
        for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
            if (REPO / name).exists():
                shutil.copy2(REPO / name, tmp_path / "tool" / name)
        (self.bin / "psql").write_text(TIMING_PSQL, encoding="utf-8")
        (self.bin / "psql").chmod(0o755)
        (self.bin / "tmux").write_text(FAKE_TMUX, encoding="utf-8")
        (self.bin / "tmux").chmod(0o755)
        self.timing = self.bin / "psql-timing.log"
        self.passfile = _private(tmp_path / "conf" / "pgpass")
        self.origin = tmp_path / "origin.git"
        self.wip = tmp_path / "wip"
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("LANES_", "CLAUDE_", "TMUX", "PG"))}
        env.update(HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"),
                   XDG_CONFIG_HOME=str(tmp_path / "config"), TMPDIR=str(tmp_path),
                   LANES_WORKSTATION="Eagle", LANES_NO_GITHUB="1", LANES_REPO=str(self.wip),
                   T220_REAL_PSQL=pg.psql_bin, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
                   PATH=str(self.bin) + os.pathsep + os.environ.get("PATH", os.defpath))
        self.env = env
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)],
                       check=True, env=env)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.wip)], check=True,
                       env=env, capture_output=True)
        (self.wip / "lanes" / "log").mkdir(parents=True)
        (self.wip / "lanes" / "LANES.md").write_text("# LANES.md\n", encoding="utf-8")
        for argv in (["add", "-A"], ["commit", "-q", "-m", "C"], ["push", "-q", "origin", "main"]):
            subprocess.run(["git", *argv], cwd=str(self.wip), check=True, env=env,
                           capture_output=True)
        self.c = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(self.wip), env=env,
                                capture_output=True, text=True, check=True).stdout.strip()
        self.request = request

    def login(self, group: str) -> str:
        """A login of `group`, made here until T228's logins exist."""
        name = f"t220_{uuid.uuid4().hex[:12]}"
        self.pg.psql(f"CREATE ROLE {name} LOGIN IN ROLE {group};")
        self.request.addfinalizer(lambda: self.pg.cluster.psql(f"DROP ROLE IF EXISTS {name};",
                                                               check=False))
        return name

    def config(self, host: str, port: int, user: str, mode: str = "primary") -> Path:
        """A configuration whose two URLs name `host:port` and this test's
        database, as `user`; no `connect_timeout=` or `register_addresses=`,
        so `c` is 2 and `N_a` 1."""
        url = f"postgresql://{user}@{host}:{port}/{self.pg.name}"
        return _private(self.root / "conf" / "lanes-index.conf", "\n".join([
            f"mode={mode}", f"register_url={url}", f"register_passfile={self.passfile}",
            f"reader_url={url}", f"reader_passfile={self.passfile}",
            "register_label=register-test", f"register_schema={SCHEMA}", ""]))

    def run(self, row: str, config: Path, *, stdin: str | None = None) -> tuple:
        """Run `row`'s path; return (the process, its elapsed seconds)."""
        env = dict(self.env, LANES_INDEX_CONFIG=str(config), LANES_LANE="repoA-2")
        tool = self.copy.parent
        index = [sys.executable, str(self.copy)]
        if row in ("guard", "answer-2"):
            argv = ["bash", str(tool / "lanes-edit.sh"), "guard"]
            env.update(TMUX="/tmp/t220,1,0", TMUX_PANE="%1", T220_WINDOW="repoA-2")
            stdin = json.dumps({"hook_event_name": "UserPromptSubmit",
                                "session_id": str(uuid.uuid4()), "cwd": str(self.wip),
                                "prompt": "2" if row == "answer-2" else "hello"})
        elif row == "reader":
            argv = index + ["register", "read", "--prefetch", "--cache",
                            str(self.root / "cache" / "reg"), "--files", "register,aliases"]
            (self.root / "cache").mkdir(exist_ok=True)
        elif row == "renderer-reads":
            argv = index + ["journal", "--since", "0"]
        elif row == "reconcile":
            argv = index + ["reconcile"]
        elif row == "import":
            argv = index + ["import", "--at", self.c]
        elif row == "status":
            argv = index + ["status"]
        elif row == "outage-probe":
            argv = index + ["outage", "declare", "--until", "2999-01-01T00:00:00Z",
                            "--reason", "D9's probe row"]
        elif row == "mode-query":
            argv = index + ["mode"]
        else:
            raise AssertionError(f"no path for {row}")
        start = time.monotonic()
        proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, env=env,
                              cwd=str(self.wip), timeout=700,
                              stdin=None if stdin is not None else subprocess.DEVNULL)
        return proc, time.monotonic() - start

    def calls(self) -> list:
        if not self.timing.exists():
            return []
        return [json.loads(l) for l in self.timing.read_text(encoding="utf-8").splitlines()
                if l and json.loads(l)["argv"] != ["--version"]]


def _record(row: str, elapsed: float, bound: float, rule: str) -> None:
    """Timing rule 2's record: the measured time, the design's bound, its
    margin."""
    print(f"D9 {row}: {elapsed:.2f} s against the design's {bound:g} s ({rule}); "
          f"margin {bound - elapsed:+.2f} s")


def _hold(pg, table: str):
    """F3: an `ALTER TABLE` on `table` in an open transaction of the test's
    own session, held until the session is closed. Returns the session once
    the lock is granted."""
    session = pg.session(appname="t220-f3")
    session.stdin.write(f"BEGIN;\nALTER TABLE {SCHEMA}.{table} ADD COLUMN t220_f3 integer;\n")
    session.stdin.flush()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        held = pg.psql("SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a USING (pid) "
                       "WHERE a.application_name = 't220-f3' AND l.granted "
                       "AND l.mode = 'AccessExclusiveLock';").stdout.strip()
        if held not in ("", "0"):
            return session
        time.sleep(0.1)
    session.kill()
    raise AssertionError("F3's lock was never granted")


def _end(session) -> None:
    try:
        session.stdin.write("ROLLBACK;\n")
        session.stdin.close()
        session.wait(timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        session.kill()


@pytest.mark.parametrize("case", FIRST_CASES)
def test_each_database_path_exits_inside_its_bound(pg, tmp_path, request, case):
    """D9: each phase-N path exits with its row's expiry outcome inside its
    bound, under F1 (a silent listener, met at the connect), F2 (a relay
    silent after the startup) and F3 (a lock on the table it reads). It owns
    test 10's per-path cases (section 4.4). `migration` is the dedicated
    test's below, and its F1 case here is the migration's connect, which
    `test_a_waiting_migration_gives_up_at_its_own_lock_timeout` runs."""
    row, fault = case.rsplit("-", 1)
    spec = ROWS[row]
    bench = Bench(pg, tmp_path, request)
    user = bench.login(spec["group"]) if spec["group"] else "lanes_test"
    if row == "migration":
        _migration(bench, fault)
        return
    listener, session = None, None
    try:
        if fault == "F1":
            listener = SilentListener()
            config = bench.config("127.0.0.1", listener.port, user)
        elif fault == "F2":
            listener = StartupRelay(f"{pg.host}/.s.PGSQL.{pg.port}")
            config = bench.config("127.0.0.1", listener.port, user)
        else:
            session = _hold(pg, spec["table"])
            config = bench.config("localhost", pg.port, user)
        if row == "mode-query":
            config.write_text(config.read_text().replace("mode=primary", "mode=index"))
        proc, elapsed = bench.run(row, config)
    finally:
        if listener is not None:
            listener.close()
        if session is not None:
            _end(session)
    if spec["exit"] is not None:
        assert proc.returncode == spec["exit"], f"{case}: {proc.returncode}: {proc.stderr}"
    else:
        assert proc.returncode != 0, f"{case}: the path ended without its read"
    if row == "reader":
        assert proc.stdout == "", "a reader's 69 has nothing on stdout"
    if row == "answer-2":
        assert "BINDING" in proc.stdout + proc.stderr
    if row == "mode-query":
        assert proc.stdout == "index\n" and bench.calls() == [], "the query reads no database"
    if spec["strict"]:
        assert elapsed < spec["bound"], f"{case}: {elapsed:.2f} s, not under {spec['bound']} s"
        _record(case, elapsed, spec["bound"], "timing rule 1")
    else:
        assert elapsed < 2 * spec["bound"], f"{case}: {elapsed:.2f} s against {spec['bound']} s"
        _record(case, elapsed, spec["bound"], "timing rule 2")


def _slow_statement(pg, table: str, group: str, seconds: float) -> None:
    """F4: a sleep the test creates in its own database, never the
    template: a row-level security policy on `table` for `group` that sleeps
    past the path's `statement_timeout`."""
    pg.psql(f"SET search_path TO {SCHEMA};\n"
            f"CREATE FUNCTION t220_slow() RETURNS boolean LANGUAGE sql VOLATILE AS "
            f"$$ SELECT pg_sleep({seconds}) IS NOT NULL $$;\n"
            f"GRANT EXECUTE ON FUNCTION t220_slow() TO {group};\n"
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY t220_slow ON {table} FOR ALL TO {group} USING (t220_slow());\n")


@pytest.mark.parametrize("row", SLOW_ROWS)
def test_a_slow_statement_meets_57014_before_the_client_timer(pg, tmp_path, request, row):
    """F4, on every phase-N row that sets a `statement_timeout`: the call
    ends with 57014, the server's bound and not the client timer, no earlier
    than the path's `statement_timeout` after the call's start (timing rule
    3) and under twice it (timing rule 2), and the path exits with its row's
    outcome (AT-D9, "Oracle")."""
    spec = ROWS[row]
    bench = Bench(pg, tmp_path, request)
    user = bench.login(spec["group"])
    statement_s = spec["statement_ms"] / 1000
    _slow_statement(pg, spec["table"], spec["group"], 4 * statement_s + 5)
    proc, elapsed = bench.run(row, bench.config("localhost", pg.port, user))
    ended = [c for c in bench.calls() if "57014" in c["first"]]
    assert ended, f"{row}: no call ended with 57014: {bench.calls()}"
    took = ended[0]["end"] - ended[0]["start"]
    assert statement_s <= took < 2 * statement_s, f"{row}: 57014 after {took:.2f} s"
    if spec["exit"] is not None:
        assert proc.returncode == spec["exit"], f"{row}: {proc.returncode}: {proc.stderr}"
    _record(f"{row}-F4", took, statement_s, "timing rules 2 and 3")


@pytest.mark.parametrize("case", ["F1-word", "F2-word", "F3-word", "F1-rollback", "F2-rollback",
                                  "F3-rollback"])
def test_the_outage_declare_probe_ends_inside_its_bound_and_the_declaration_follows_the_rule(
        pg, tmp_path, request, case):
    """`outage declare`'s database probe (section 2.5's row): 2 s, 2000 ms,
    5000 ms, 8 s. On a person's word, the declaration is written, since the
    database does not answer from this host; in the `--rollback` form, 2 and
    no file, the switch being unread. The probe ends inside twice its 8 s
    (AT-D9's table)."""
    fault, form = case.split("-", 1)
    bench = Bench(pg, tmp_path, request)
    user = bench.login("lanes_register_writer")
    listener, session = None, None
    try:
        if fault == "F1":
            listener = SilentListener()
            config = bench.config("127.0.0.1", listener.port, user)
        elif fault == "F2":
            listener = StartupRelay(f"{pg.host}/.s.PGSQL.{pg.port}")
            config = bench.config("127.0.0.1", listener.port, user)
        else:
            session = _hold(pg, "register_switch")
            config = bench.config("localhost", pg.port, user)
        argv = [sys.executable, str(bench.copy), "outage", "declare", "--until",
                "2999-01-01T00:00:00Z", "--reason", "D9's probe"]
        if form == "rollback":
            argv.append("--rollback")
        env = dict(bench.env, LANES_INDEX_CONFIG=str(config), LANES_LANE="repoA-2")
        start = time.monotonic()
        proc = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(bench.wip),
                              timeout=120, stdin=subprocess.DEVNULL)
        elapsed = time.monotonic() - start
    finally:
        if listener is not None:
            listener.close()
        if session is not None:
            _end(session)
    declaration = config.parent / "register-outage"
    if form == "word":
        assert proc.returncode == 0, proc.stderr
        assert declaration.exists(), "the declaration is written"
    else:
        assert proc.returncode == 2, proc.stderr
        assert not declaration.exists(), "no file in the --rollback form"
    assert elapsed < 2 * 8, f"{case}: {elapsed:.2f} s"
    _record(f"outage-probe-{case}", elapsed, 8, "timing rule 2")


def _migration(bench: Bench, fault: str) -> None:
    """The migration's path, through `lanes-index bootstrap` under a pty
    (T218: it refuses when stdout is not a terminal), its admin reached only
    as `PGSERVICE` (T218). Under F1 its connect meets the silent listener
    and it is refused, writing nothing."""
    listener = SilentListener()
    try:
        service = bench.root / "pg_service.conf"
        service.write_text(f"[t220-admin]\nhost=127.0.0.1\nport={listener.port}\n"
                           f"dbname={bench.pg.name}\nuser=lanes_test\n", encoding="utf-8")
        env = dict(bench.env, PGSERVICEFILE=str(service))
        code, elapsed, timed_out = _in_pty([sys.executable, str(bench.copy), "bootstrap",
                                            "--service", "t220-admin", "--label",
                                            "register-test"], env, bench.wip)
    finally:
        listener.close()
    assert not timed_out and code != 0, "a migration that cannot connect is refused"
    assert elapsed < 2 * (N_A * C + 1), f"{elapsed:.2f} s, against its connect, c"
    _record(f"migration-{fault}", elapsed, N_A * C + 1, "timing rule 2")


def _in_pty(argv: list, env: dict, cwd: Path, *, timeout: float = 120) -> tuple:
    """Run `argv` with its stdout on a pty; return (its exit, its elapsed
    seconds, whether this helper's own timeout killed it)."""
    master, slave = pty.openpty()
    start = time.monotonic()
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=slave, stderr=slave, env=env,
                            cwd=str(cwd))
    os.close(slave)
    timed_out = False
    while True:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                os.read(master, 65536)
            except OSError:
                ready = []
        if proc.poll() is not None and not ready:
            break
        if time.monotonic() - start > timeout:
            proc.kill()
            timed_out = True
            break
    os.close(master)
    return proc.wait(), time.monotonic() - start, timed_out


def test_a_waiting_migration_gives_up_at_its_own_lock_timeout(pg, tmp_path, request):
    """A migration waiting behind a reader's open transaction is refused at
    its own `lock_timeout`, and a rerun succeeds once the reader's
    transaction ends; a new plain read is not held longer than that
    `lock_timeout` (AT-D9's migration row)."""
    bench = Bench(pg, tmp_path, request)
    reader = bench.login("lanes_register_reader")
    held = pg.session(user=reader, appname="t220-reader")
    held.stdin.write(f"BEGIN;\nSELECT seq FROM {SCHEMA}.register_head;\n")
    held.stdin.flush()
    time.sleep(1)
    service = tmp_path / "pg_service.conf"
    service.write_text(f"[t220-admin]\nhost={pg.host}\nport={pg.port}\ndbname={pg.name}\n"
                       f"user=lanes_test\n", encoding="utf-8")
    env = dict(bench.env, PGSERVICEFILE=str(service))
    argv = [sys.executable, str(bench.copy), "bootstrap", "--service", "t220-admin",
            "--label", "register-test"]
    try:
        code, elapsed, timed_out = _in_pty(argv, env, bench.wip, timeout=60)
        assert not timed_out, "the migration waited past 60 s instead of giving up"
        assert code != 0, "the waiting migration is refused"
        _record("migration-lock", elapsed, 60, "its own lock_timeout, not given here")
        start = time.monotonic()
        pg.psql(f"SELECT seq FROM {SCHEMA}.register_head;", user=reader)
        assert time.monotonic() - start < 60, "a plain read was held"
    finally:
        _end(held)
    code, _, timed_out = _in_pty(argv, env, bench.wip)
    assert not timed_out and code == 0, "the rerun succeeds once the reader's transaction ends"


def test_import_and_reconcile_set_their_bounds_at_connect(tmp_path):
    """FP: `import` carries `PGCONNECT_TIMEOUT=2`, `c` here, and sets
    `lock_timeout=2000` and `statement_timeout=300s` at connect, under a
    330 s client timer; `reconcile` carries its row's bounds, 1000 ms and
    10 s, at connect (AT-D9's table; T106's `PGOPTIONS`, Y:1573). No engine:
    T203's register fake, behind the `--version` wrapper, records each call."""
    from sql_register_helpers import REGISTER_FAKE_PSQL
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, text in (("register-fake-psql", REGISTER_FAKE_PSQL), ("psql", VERSION_WRAPPER)):
        (bindir / name).write_text(text, encoding="utf-8")
        (bindir / name).chmod(0o755)
    passfile = _private(tmp_path / "conf" / "pgpass")
    url = "postgresql://t220_fp@127.0.0.1:55432/register_db"
    config = _private(tmp_path / "conf" / "lanes-index.conf", "\n".join([
        "mode=index", f"register_url={url}", f"register_passfile={passfile}",
        f"reader_url={url}", f"reader_passfile={passfile}", "register_label=register-test",
        ""]))
    origin, wip = tmp_path / "origin.git", tmp_path / "wip"
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("LANES_", "CLAUDE_", "TMUX", "PG", "FAKE_PSQL"))}
    env.update(HOME=str(tmp_path), XDG_STATE_HOME=str(tmp_path / "state"),
               XDG_CONFIG_HOME=str(tmp_path / "config"), LANES_INDEX_CONFIG=str(config),
               LANES_LANE="repoA-2", LANES_REPO=str(wip), FAKE_PSQL_LOG=str(tmp_path / "fake.log"),
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
               PATH=str(bindir) + os.pathsep + os.environ.get("PATH", os.defpath))
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, env=env)
    subprocess.run(["git", "clone", "-q", str(origin), str(wip)], check=True, env=env,
                   capture_output=True)
    (wip / "lanes").mkdir()
    (wip / "lanes" / "LANES.md").write_text("# LANES.md\n", encoding="utf-8")
    for argv in (["add", "-A"], ["commit", "-q", "-m", "C"], ["push", "-q", "origin", "main"]):
        subprocess.run(["git", *argv], cwd=str(wip), check=True, env=env, capture_output=True)
    c = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(wip), env=env, capture_output=True,
                       text=True, check=True).stdout.strip()
    log = tmp_path / "fake.log"
    for argv, options in (
            (["import", "--at", c], ("-c lock_timeout=2000", "-c statement_timeout=300000")),
            (["reconcile"], ("-c lock_timeout=1000", "-c statement_timeout=10000"))):
        if log.exists():
            log.unlink()
        subprocess.run([sys.executable, str(INDEXER), *argv], capture_output=True, text=True,
                       env=env, cwd=str(wip), timeout=120, stdin=subprocess.DEVNULL)
        calls = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
        calls = [c for c in calls if c["argv"] != ["--version"]]
        assert calls, f"{argv[0]} made no psql call"
        for call in calls:
            assert call["connect_timeout"] == str(C), (argv[0], call["connect_timeout"])
            assert all(o in (call["options"] or "") for o in options), (argv[0], call["options"])
