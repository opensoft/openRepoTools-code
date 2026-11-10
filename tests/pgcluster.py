# SPDX-License-Identifier: Apache-2.0
"""A REAL POSTGRESQL 16 FOR THE TESTS THAT NEED ONE (#165, L2-0a and L2-0b).

What only an engine decides, a fake `psql` cannot show: a SERIALIZABLE
conflict's 40001, a GRANT that refuses, a COMMIT whose session dies. This is
the fixture those tests run on, R1's option (a) as the test plan's section
3.1 settles it, from the fixture probe's prototype (sha256 `5f20d742…`).
Python 3.9 or later, standard library only. `tests/conftest.py` registers it
as a pytest plugin from its `pytest_configure`.

ONE DISPOSABLE CLUSTER PER SESSION. `initdb -N` into a 0700
`mkdtemp(prefix="orpg-", dir="/tmp")`, whose socket path is 32 bytes whatever
`TMPDIR` is; a postmaster started by `Popen` on that Unix socket alone, with
no TCP; and one database per test, cloned from the session's template. A
`Popen` postmaster stays in pytest's process group, so `tests/run.sh`'s stop
of the group reaches it, where `pg_ctl`'s would not; on Linux it also dies
with a SIGKILLed pytest, and the next session's start sweeps what a killed
one left.

THE FIXTURES:

  * `pg_engine`, session-scoped: the binaries, found once. EVERY CLUSTER
    DEPENDS ON IT, so a test whose fixture closure holds it is a real-engine
    test, which is how `test_sql_register_fixture.py` tells one apart;
  * `pg_template_sql`, session-scoped and overridable: how the template is
    built. By default it is `Bootstrap()`, P8's bootstrap (T227, below); a
    module may return SQL of its own instead, run on an empty `tmpl`;
  * `pg_cluster`, session-scoped: the session's cluster, with the template
    `tmpl` built, then closed to connections, and `tmpl_imported` beside it;
  * `pg`, one database per test, `CREATE DATABASE t_<n> TEMPLATE tmpl`, then
    section 1.4's two database-level statements, and dropped `WITH (FORCE)`
    at its teardown;
  * `stoppable_cluster`, a cluster of the test's own, built like the
    session's, for the tests that stop the database: `stop()` is a fast
    shutdown, SIGINT and a wait, and `start_again()` starts it on the same
    data and socket directories.

THE TEMPLATES (T227; the test plan's section 3.1, "The templates"). `tmpl` is
built on each cluster by P8's bootstrap, `lanes-index bootstrap --no-passwords`
(lane 1's T109, L1-A7), run through the admin service as AT-P8's fixture runs
it: a libpq service in `~/.pg_service.conf` of the cluster's own 0700 `admin`
home, naming the cluster's socket, its superuser and the database, so no
connection string is ever an argument. It makes the schema, the owner, the
groups REGISTER-WRITER and READER, the indexer's login and their GRANTs, and
labels the switch `register-test`. Then the fixture's logins are made (T228:
`lanes-index login add fx` and `login add --dump-job`, through the same service
under a pty, since `login` refuses off a terminal): `lanes_w_fx` and
`lanes_r_fx`, as which every session a test runs as REGISTER-WRITER or as
READER logs in, and `lanes_register_dump`; their passwords stay in memory for
`passfile()`. Then `tmpl` is marked `IS_TEMPLATE true
ALLOW_CONNECTIONS false`. A clone does not copy `pg_database.datacl`, so each
clone runs section 1.4's `REVOKE ALL ON DATABASE` and `GRANT CONNECT`, with
`-v db=` its name; the first run prints what a clone's `datacl` held before
them (open point 12). On the session cluster, `tmpl_imported` is cloned from
`tmpl`, with test 7's fixture register (T211's `FixtureRegister`) imported by
`lanes-index import --at` (lane 1's T115, L1-A13). Until that imports, there is
no `tmpl_imported`, the run's foot says why, and the cases that clone it fail;
a bootstrap that fails fails each real-engine test, saying so.

The binaries' directory goes first on `PATH` while a cluster is up, so the
code under test runs the `psql` of the server it talks to, and every
subprocess the fixture runs has no inherited `PG*` variable.

THE SWITCH, `OPENREPOTOOLS_REQUIRE_PG`, unset, `0` or `1`, and nothing else.
Where no PostgreSQL 16 is found, or the run is root (`initdb` refuses root):

  * unset or `0`, every real-engine test SKIPS, naming each place tried,
    `PG_BIN` and the package, and a banner says so even under `-q`;
  * `1`, as CI sets it, `pytest_configure` refuses the run before any test,
    `UsageError`, exit 4. The refusal is EAGER: a run that selects no
    real-engine test is refused too, so a job cannot go green without the
    engine it was promised.

The binaries are `PG_BIN`, which is final (one that fails is reported, never
replaced), then `pg_config --bindir`, then `/usr/lib/postgresql/16/bin`. Each
candidate needs `initdb`, `pg_ctl`, `postgres` and `psql`, all saying
`(PostgreSQL) 16`. Where they were found is printed at the run's foot whenever
they were looked for, which under the switch is every run (open point 12).

THE SMOKE, `python3 -I -B tests/pgcluster.py --smoke <name>…`, runs without
pytest. `session` starts a cluster, clones a database from an empty template
and runs `SELECT 1` in it; `stoppable` starts a cluster, stops it by SIGINT,
starts it again on the same directories and runs `SELECT 1`. It exits 0 when
each named smoke passes, 1 when one fails or there is no engine, and 2 for a
name it does not know.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

#: THE SMOKE IMPORTS NO PYTEST: run as a script, this module is standard
#: library only, and the fixtures below are plain functions it never calls.
if __name__ == "__main__":
    pytest = None
else:
    import pytest

#: The name `tests/conftest.py` registers this plugin under.
PLUGIN_NAME = "openrepotools-pg"

ENV_REQUIRE = "OPENREPOTOOLS_REQUIRE_PG"
MAJOR, PACKAGE = 16, "postgresql-16"
DEBIAN_BIN = Path("/usr/lib/postgresql/16/bin")
TOOLS = ("initdb", "pg_ctl", "postgres", "psql")
SUPERUSER, PORT, TEMPLATE = "lanes_test", 5432, "tmpl"
SOCKET_PARENT, PREFIX = "/tmp", "orpg-"   # /tmp/orpg-XXXXXXXX/.s.PGSQL.5432 = 32 bytes
SOCKET_MAX = 100                          # sun_path: 107 usable on Linux, 103 on macOS
FAST = ("fsync=off", "synchronous_commit=off", "full_page_writes=off")
DEADLINE, POLL = 30.0, 0.005
SKIP_TAG = "real PostgreSQL 16"
DIE_WITH_PYTEST = True                    # Linux: PR_SET_PDEATHSIG(SIGQUIT) on the postmaster
DEVNULL = subprocess.DEVNULL
_SKIPPED: List[str] = []
_SWEPT: List[str] = []

#: THE CODE UNDER TEST'S `lanes-index`, which the template's build runs.
REPO = Path(__file__).resolve().parent.parent
LANES_INDEX = REPO / "lanes-index"

#: THE TEMPLATES (T227): the imported template's name, and the bootstrap's
#: inputs. The label is the one the import, outage and bounds modules name in
#: their `register_label=`; the others fill the switch's and the migrations
#: row's columns, whose CHECKs ask only that each is not empty.
IMPORTED = "tmpl_imported"
FX_LABEL = "register-test"
FX_REPOSITORY = "opensoft/openRepoTools-fixture"
FX_LANE = "fixture"
FX_WORKSTATION = "fixture"

#: SECTION 1.4'S TWO DATABASE-LEVEL STATEMENTS, as lane 1's role block holds
#: them (Y:2243-2244; `lanes-index`'s `_REGISTER_ROLE_BLOCK`), with `-v db=`.
DATABASE_LEVEL = ('REVOKE ALL ON DATABASE :"db" FROM PUBLIC;\n'
                  'GRANT CONNECT ON DATABASE :"db" TO lanes_register_writer, '
                  'lanes_register_reader, lanes_indexer;\n')

#: What the admin's `lanes-index` never inherits: the configuration's and the
#: workspace's variables. `PG*` goes too, as everywhere here.
ADMIN_ENV_DROPPED = ("LANES_", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "AGENT_PROTOCOL_ROOT",
                     "PROJECTS_", "TMUX", "CLAUDE_")
_DATACL: List[str] = []
_IMPORTED: List[str] = []

#: THE FIXTURE'S LOGINS (T228): the engineer `login add` is run for, and the
#: three logins it and `login add --dump-job` make. Every session a test runs
#: as REGISTER-WRITER or as READER logs in as the writer or the reader.
FX_ENGINEER = "fx"
FX_WRITER, FX_READER, FX_DUMP = "lanes_w_fx", "lanes_r_fx", "lanes_register_dump"
FX_LOGINS = (FX_WRITER, FX_READER, FX_DUMP)

#: A password-file line as `login add` prints it once, to a terminal:
#: `*:*:<database>:<login>:<password>` (lane 1's `_register_pgpass_line`).
PASSWORD_LINE = re.compile(r"^\*:\*:(?:[^:\\\n]|\\.)*:(lanes_[a-z0-9_]+):([^:\s]+)$", re.M)
_SECRET_FIELD = re.compile(r"^(\*:\*:.*:)[^:\n]*$", re.M)


def _fixture(**options):
    """`pytest.fixture(**options)`; in the smoke, which runs without pytest,
    the function as it is."""
    if pytest is None:
        return lambda function: function
    return pytest.fixture(**options)


def switch_problem(environ=os.environ) -> Optional[str]:
    """Why the switch's value is refused, or None for unset, `0` or `1`."""
    value = environ.get(ENV_REQUIRE, "")
    if value in ("", "0", "1"):
        return None
    return (f"{ENV_REQUIRE}={value!r} is neither 1 (the real-engine tests are "
            f"required, as in CI) nor 0 or unset (they skip, loudly, where "
            f"PostgreSQL {MAJOR} is missing)")


def required(environ=os.environ) -> bool:
    """Whether the real-engine tests must run: a usage error, exit 4, for a
    value that is neither."""
    problem = switch_problem(environ)
    if problem:
        raise pytest.UsageError(problem)
    return environ.get(ENV_REQUIRE, "") == "1"


# ------------------------------------------------------------ the binaries
def check_bindir(bindir: Path) -> Optional[str]:
    """None where `bindir` holds the four tools at major 16, else why not."""
    if not bindir.is_dir():
        return f"{bindir} is not a directory"
    missing = [t for t in TOOLS if not os.access(str(bindir / t), os.X_OK) or (bindir / t).is_dir()]
    if missing:
        return f"{bindir} has no {', '.join(missing)}"
    for tool in TOOLS:
        try:
            said = subprocess.run([str(bindir / tool), "--version"], stdin=DEVNULL, capture_output=True,
                                  text=True, timeout=20, check=False).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            said = f"<{exc}>"
        m = re.search(r"\(PostgreSQL\) (\d+)", said)
        if not m or int(m.group(1)) != MAJOR:
            return f"{bindir / tool} is not PostgreSQL {MAJOR}: it says {said!r}"
    return None


def find_bindir(environ=os.environ) -> Tuple[Optional[Path], str]:
    """(directory, how found), or (None, every place tried and why not)."""
    named = environ.get("PG_BIN", "")
    if named:
        why = check_bindir(Path(named))
        return ((Path(named), "PG_BIN") if why is None else
                (None, f"PG_BIN={named}, and {why}; a named PG_BIN is never replaced by a found one"))
    tried = ["PG_BIN is unset"]
    pg_config = shutil.which("pg_config", path=environ.get("PATH", os.defpath))
    if pg_config:
        try:
            out = subprocess.run([pg_config, "--bindir"], stdin=DEVNULL, capture_output=True,
                                 text=True, timeout=20, check=False).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            out = ""
        why = check_bindir(Path(out)) if out else "it printed nothing"
        if why is None:
            return Path(out), f"`{pg_config} --bindir`"
        tried.append(f"`{pg_config} --bindir` says {out or '-'}, and {why}")
    else:
        tried.append("no pg_config on PATH")
    why = check_bindir(DEBIAN_BIN)
    if why is None:
        return DEBIAN_BIN, "the Debian and Ubuntu layout"
    return None, "; ".join(tried + [why])


class Probe:
    """Where the binaries are and how they were found, or the problem."""

    def __init__(self) -> None:
        self.bindir, self.how = find_bindir()
        self.problem: Optional[str] = None
        if self.bindir is None:
            self.problem = (f"no {SKIP_TAG} for the real-engine tests ({self.how}): install the "
                            f"package {PACKAGE} (server and client), or set PG_BIN to a directory "
                            f"holding {', '.join(TOOLS)} of major version {MAJOR}")
        elif hasattr(os, "geteuid") and os.geteuid() == 0:
            self.problem = (f"{SKIP_TAG} is at {self.bindir} ({self.how}), but this run is root, and "
                            f"initdb refuses to run as root: run the suite as an ordinary user")

    def found(self) -> str:
        return f"{SKIP_TAG} at {self.bindir} ({self.how})"


_PROBE: Optional[Probe] = None


def probe() -> Probe:
    global _PROBE
    if _PROBE is None:
        _PROBE = Probe()
    return _PROBE


def _engine_first(bindir: Path, path: str) -> str:
    """`path` with `bindir` first, once."""
    rest = [entry for entry in path.split(os.pathsep) if entry and entry != str(bindir)]
    return os.pathsep.join([str(bindir), *rest])


def _without_pg(environ=os.environ) -> Dict[str, str]:
    """`environ` with no variable whose name begins `PG`: a person's
    `PGHOST`, `PGSERVICE` or `PGPASSWORD` never steers a test."""
    return {k: v for k, v in environ.items() if not k.startswith("PG")}


# ------------------------------------------------------------ the cluster
def _ticks(pid: int) -> str:
    """The process's start time (Linux), so a reused pid is not taken for its owner."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return "-"


def _running(pid: int, ticks: str = "-") -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        if Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z":
            return False                  # a zombie counts as dead
    except (OSError, IndexError):
        pass
    return ticks == "-" or _ticks(pid) == ticks


def _stop_orphan(root: Path) -> None:
    """Stop the postmaster a dead session left in `root`, if it is still that one."""
    try:
        pid, datadir = (root / "data" / "postmaster.pid").read_text().splitlines()[:2]
        pid_n = int(pid)
        cmd = Path(f"/proc/{pid_n}/cmdline").read_bytes() if Path("/proc").is_dir() else b""
    except (OSError, ValueError):
        return
    if datadir != str(root / "data") or (cmd and os.fsencode(datadir) not in cmd):
        return
    for sig in (signal.SIGQUIT, signal.SIGKILL):
        try:
            os.kill(pid_n, sig)
        except (ProcessLookupError, PermissionError):
            return
        end = time.monotonic() + 10
        while time.monotonic() < end and _running(pid_n):
            time.sleep(0.02)
        if not _running(pid_n):
            return


def sweep_stale() -> List[str]:
    """What a SIGKILLed session left: this user's PREFIX dirs whose owner is gone."""
    swept = []
    for root in Path(SOCKET_PARENT).glob(PREFIX + "*"):
        try:
            info = root.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                continue
            owner = (root / "owner").read_text().split() if (root / "owner").exists() else []
        except OSError:
            continue
        if len(owner) == 2 and owner[0].isdigit() and _running(int(owner[0]), owner[1]):
            continue
        if not owner and time.time() - info.st_mtime < 60:
            continue                      # being made this instant: not ours to judge yet
        _stop_orphan(root)
        shutil.rmtree(root, ignore_errors=True)
        swept.append(str(root))
    return swept


class ClusterError(Exception):
    pass


class Bootstrap:
    """`pg_template_sql`'S DEFAULT (T227): build `tmpl` by P8's bootstrap,
    then make the fixture's logins (T228) unless `logins` is False, then run
    `sql`, if any, on it. A plain string instead is SQL run on an empty
    `tmpl`, as the smokes' clusters have it."""

    def __init__(self, sql: str = "", logins: bool = True) -> None:
        self.sql, self.logins = sql, logins

    def __repr__(self) -> str:
        return f"Bootstrap(sql={self.sql!r}, logins={self.logins!r})"


def _masked(text: str) -> str:
    """`text` with each password-file line's last field, the password, hidden."""
    return _SECRET_FIELD.sub(lambda m: m.group(1) + "<password>", text or "")


def _tail(proc: subprocess.CompletedProcess, size: int = 800) -> str:
    """A command's last words, stdout then stderr, on one line."""
    said = " | ".join(line.strip() for line in f"{proc.stdout or ''}\n{proc.stderr or ''}".splitlines()
                      if line.strip())
    return said[-size:] or "<nothing>"


def _client_env(host: Path, user: str, dbname: str, appname: str, bindir: Path) -> dict:
    env = _without_pg()
    env.update(PGHOST=str(host), PGPORT=str(PORT), PGUSER=user, PGDATABASE=dbname,
               PGAPPNAME=appname, PGCONNECT_TIMEOUT="10", LC_ALL="C",
               PATH=_engine_first(bindir, env.get("PATH", os.defpath)))
    return env


def _die_with_parent(parent: int):
    if not (DIE_WITH_PYTEST and sys.platform.startswith("linux")):
        return None
    import ctypes
    prctl = ctypes.CDLL(None, use_errno=True).prctl

    def preexec() -> None:
        prctl(1, int(signal.SIGQUIT), 0, 0, 0)               # PR_SET_PDEATHSIG
        if os.getppid() != parent:
            os._exit(70)
    return preexec


class Cluster:
    """One cluster: its private directory, its postmaster and its template."""

    def __init__(self, bindir: Path, template_sql="", imported: bool = False) -> None:
        """`template_sql` is `pg_template_sql`'s value: a `Bootstrap`, or SQL
        for an empty `tmpl` (the smokes' default). `imported` builds
        `tmpl_imported` too."""
        self.bindir, self.template_sql, self.imported = bindir, template_sql, imported
        self.root: Optional[Path] = None
        self.proc: Optional[subprocess.Popen] = None
        self.count, self.timings = 0, {}
        #: The switch's label where the bootstrap built `tmpl`, else None.
        self.label: Optional[str] = None
        #: Why there is no `tmpl_imported`, where it was asked for and is not.
        self.imported_problem: Optional[str] = None
        #: The fixture's logins' passwords, as `login add` printed them once
        #: (T228). Kept in memory for `passfile()`, never printed.
        self.passwords: Dict[str, str] = {}

    def tool(self, name: str) -> str:
        return str(self.bindir / name)

    def server_env(self) -> dict:
        env = _without_pg()
        env.update(LC_ALL="C", TZ="UTC", PATH=_engine_first(self.bindir, env.get("PATH", os.defpath)))
        return env

    def psql(self, sql: str, dbname: str = "postgres", user: str = SUPERUSER,
             check: bool = True, appname: str = "pytest",
             variables: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        argv = [self.tool("psql"), "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
        for name, value in (variables or {}).items():
            argv += ["-v", f"{name}={value}"]
        proc = subprocess.run([*argv, "-f", "-"], input=sql, capture_output=True, text=True,
                              timeout=120, env=_client_env(self.root, user, dbname, appname,
                                                           self.bindir),
                              check=False)
        if check and proc.returncode != 0:
            raise ClusterError(f"psql as {user} on {dbname} exited {proc.returncode}: {proc.stderr.strip()}")
        return proc

    def log_tail(self) -> str:
        try:
            return " | ".join((self.root / "server.log").read_text().splitlines()[-5:])
        except OSError:
            return "<no log>"

    def ready(self) -> bool:
        """The postmaster's own `ready` status, line 8 of postmaster.pid: what pg_ctl -w reads."""
        try:
            lines = (self.root / "data" / "postmaster.pid").read_text().splitlines()
        except OSError:
            return False
        return len(lines) >= 8 and lines[0] == str(self.proc.pid) and lines[7].strip() == "ready"

    def start(self) -> None:
        """Sweep, make the directory, `initdb`, start, and build the template."""
        t0 = time.monotonic()
        _SWEPT.extend(sweep_stale())
        self.root = Path(tempfile.mkdtemp(prefix=PREFIX, dir=SOCKET_PARENT))   # mode 0700
        (self.root / "owner").write_text(f"{os.getpid()} {_ticks(os.getpid())}\n")
        sock = self.root / f".s.PGSQL.{PORT}"
        if len(os.fsencode(str(sock))) > SOCKET_MAX:
            raise ClusterError(f"the socket path {sock} is over {SOCKET_MAX} bytes")
        t1 = time.monotonic()
        init = subprocess.run([self.tool("initdb"), "-D", str(self.root / "data"), "-N", "-A", "trust",
                               "-U", SUPERUSER, "-E", "UTF8", "--locale=C"], stdin=DEVNULL,
                              capture_output=True, text=True, env=self.server_env(), timeout=120,
                              check=False)
        if init.returncode != 0:
            raise ClusterError(f"initdb exited {init.returncode}: {init.stderr.strip()}")
        t2 = time.monotonic()
        self.launch()
        t3 = time.monotonic()
        self.build_template()
        t4 = time.monotonic()
        self.timings = {"initdb": t2 - t1, "ready": t3 - t2, "template": t4 - t3, "start": t4 - t0}

    # -------------------------------------------------------- the templates (T227)
    def build_template(self) -> None:
        """`tmpl`, by the bootstrap or by SQL, then `tmpl_imported` where it
        was asked for, then `tmpl` closed to connections."""
        self.psql(f"CREATE DATABASE {TEMPLATE};")
        sql = self.template_sql
        if isinstance(sql, Bootstrap):
            self.bootstrap(TEMPLATE, FX_LABEL)
            self.label = FX_LABEL
            if sql.logins:
                self.make_logins(TEMPLATE)
            sql = sql.sql
        if sql.strip():
            self.psql(sql, dbname=TEMPLATE)
        if self.imported:
            self.build_imported()
        self.psql(f"ALTER DATABASE {TEMPLATE} WITH IS_TEMPLATE true ALLOW_CONNECTIONS false;")

    def admin_env(self) -> dict:
        """THE ADMIN'S `lanes-index` ENVIRONMENT: no `PG*`, no configuration or
        workspace variable, `HOME` the cluster's own `admin` directory (where
        `~/.pg_service.conf` is, and no `lanes-index.conf`, so `load_config`
        reads its defaults), the workstation named, and the engine's tools
        first on `PATH`, so its `psql` is the server's."""
        env = {k: v for k, v in _without_pg().items() if not k.startswith(ADMIN_ENV_DROPPED)}
        env.update(HOME=str(self.root / "admin"), LANES_WORKSTATION=FX_WORKSTATION, LC_ALL="C",
                   TZ="UTC", PATH=_engine_first(self.bindir, env.get("PATH", os.defpath)))
        return env

    def admin_service(self, database: str) -> str:
        """The admin service naming `database`: a section of the admin home's
        `.pg_service.conf`, 0600, with the cluster's socket and superuser.
        The socket's trust needs no `~/.pgpass`."""
        home = self.root / "admin"
        home.mkdir(mode=0o700, exist_ok=True)
        name, path = f"fx_{database}", home / ".pg_service.conf"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if f"[{name}]\n" not in text:
            text += (f"[{name}]\nhost={self.root}\nport={PORT}\nuser={SUPERUSER}\n"
                     f"dbname={database}\n\n")
            path.write_text(text, encoding="utf-8")
            path.chmod(0o600)
        return name

    def lanes_index(self, argv: List[str]) -> subprocess.CompletedProcess:
        """The code under test's `lanes-index`, as the admin, from the
        cluster's directory."""
        return subprocess.run([sys.executable, str(LANES_INDEX), *argv], stdin=DEVNULL,
                              capture_output=True, text=True, env=self.admin_env(),
                              cwd=str(self.root), timeout=300, check=False)

    def lanes_index_tty(self, argv: List[str]) -> Tuple[int, str, str]:
        """`lanes_index` with its stdout a pty, for `login`, which refuses off
        a terminal (operations.md section 2.4): (exit, stdout, stderr), the
        pty's CR LF read back as LF. A run that outlasts the admin's 300 s is
        killed."""
        import pty
        import select
        primary, secondary = pty.openpty()
        try:
            proc = subprocess.Popen([sys.executable, str(LANES_INDEX), *argv], stdin=DEVNULL,
                                    stdout=secondary, stderr=subprocess.PIPE,
                                    env=self.admin_env(), cwd=str(self.root))
        except OSError:
            os.close(primary)
            raise
        finally:
            os.close(secondary)
        out, end = [], time.monotonic() + 300
        try:
            while time.monotonic() < end:
                ready, _, _ = select.select([primary], [], [], max(0.0, end - time.monotonic()))
                if not ready:
                    break
                try:
                    chunk = os.read(primary, 65536)
                except OSError:                     # EIO: the child closed its end
                    break
                if not chunk:
                    break
                out.append(chunk)
        finally:
            os.close(primary)
        if proc.poll() is None and time.monotonic() >= end:
            proc.kill()
        err = proc.stderr.read().decode("utf-8", "replace")
        proc.stderr.close()
        code = proc.wait(timeout=DEADLINE)
        return code, b"".join(out).decode("utf-8", "replace").replace("\r\n", "\n"), err

    def make_logins(self, database: str) -> None:
        """THE FIXTURE'S LOGINS (T228; section 3.1, "The fixture's logins"),
        once per cluster, after the bootstrap: `lanes-index login add fx`,
        then `login add --dump-job`, each through the admin service on
        `database` and under a pty (lane 1's T110, L1-A8). They make
        `lanes_w_fx` in REGISTER-WRITER and `lanes_r_fx` in READER, each with
        its own floors, and `lanes_register_dump` in READER, each with a
        SCRAM verifier lane 1's code computes. The passwords each prints
        once are kept for `passfile()`: the socket's trust ignores them, a
        TLS cluster's SCRAM does not. No error text here holds one."""
        service = self.admin_service(database)
        for argv in (["login", "add", FX_ENGINEER, "--admin-service", service],
                     ["login", "add", "--dump-job", "--admin-service", service]):
            code, out, err = self.lanes_index_tty(argv)
            if code != 0:
                raise ClusterError(f"`lanes-index {' '.join(argv[:3])}` through the admin service "
                                   f"on {database} exited {code}, so the fixture has no logins "
                                   f"(lane 1's T110, L1-A8, builds `login`): "
                                   f"{_masked(out)[-400:]} | {_masked(err)[-400:]}")
            self.passwords.update(PASSWORD_LINE.findall(out))
        names = ", ".join(f"'{login}'" for login in FX_LOGINS)
        can = self.psql(f"SELECT rolname FROM pg_catalog.pg_roles WHERE rolcanlogin AND "
                        f"rolname IN ({names}) ORDER BY 1;").stdout.split()
        missing = sorted(set(FX_LOGINS) - set(can)) + sorted(set(FX_LOGINS) - set(self.passwords))
        if missing:
            raise ClusterError(f"after `login add`, these logins cannot log in or printed no "
                               f"password line: {', '.join(missing)}")

    def passfile(self, login: str) -> Path:
        """A 0600 libpq password file holding `login`'s line at any host,
        port and database, in the cluster's private `secrets` directory:
        what a `register_passfile=` or `reader_passfile=` names."""
        if login not in self.passwords:
            raise ClusterError(f"no password for {login}: only the fixture's logins have one")
        secrets = self.root / "secrets"
        secrets.mkdir(mode=0o700, exist_ok=True)
        path = secrets / f"{login}.pgpass"
        path.write_text(f"*:*:*:{login}:{self.passwords[login]}\n", encoding="utf-8")
        path.chmod(0o600)
        return path

    def bootstrap(self, database: str, label: str) -> str:
        """P8's bootstrap on `database`, through the admin service, with
        `--no-passwords`: the roles are global, so a second run on a cluster
        finds them `unchanged`. Its output, which holds no secret."""
        proc = self.lanes_index(["bootstrap", "--admin-service", self.admin_service(database),
                                 "--label", label, "--repository", FX_REPOSITORY,
                                 "--lane", FX_LANE, "--no-passwords"])
        if proc.returncode != 0:
            raise ClusterError(f"`lanes-index bootstrap --no-passwords` through the admin "
                               f"service on {database} exited {proc.returncode}, so the "
                               f"template has no register (lane 1's T109, L1-A7, builds the "
                               f"bootstrap): {_tail(proc)}")
        return proc.stdout

    def build_imported(self) -> None:
        """`tmpl_imported`: a clone of `tmpl`, with section 1.4's two
        statements, and test 7's fixture register imported into it by
        `lanes-index import --at <C>` as T211 runs it (its `FixtureRegister`,
        on the cluster's socket as the superuser), then closed to
        connections. Where any step fails, there is no `tmpl_imported`, and
        `imported_problem` says why: the session goes on, and only the cases
        that clone it fail."""
        if self.label is None:
            self.imported_problem = "tmpl was not built by the bootstrap, so it holds no register"
        else:
            try:
                from test_sql_register_import import FixtureRegister
            except ImportError as exc:
                self.imported_problem = (f"test 7's fixture register, T211's FixtureRegister in "
                                         f"tests/test_sql_register_import.py, cannot be loaded: {exc}")
        if self.imported_problem is None:
            self.psql(f"CREATE DATABASE {IMPORTED} TEMPLATE {TEMPLATE};")
            self.psql(DATABASE_LEVEL, variables={"db": IMPORTED})
            path = os.environ.get("PATH", os.defpath)
            os.environ["PATH"] = _engine_first(self.bindir, path)   # the import's `psql`
            try:
                register = FixtureRegister(self.root / "imported")
                proc = register.import_at(Database(self, IMPORTED), register.c)
                if proc.returncode != 0:
                    self.imported_problem = (f"`lanes-index import --at {register.c}` exited "
                                             f"{proc.returncode} (lane 1's T115, L1-A13, builds "
                                             f"it): {_tail(proc)}")
            except Exception as exc:          # the register's own build: git, lanes-edit.sh
                self.imported_problem = f"test 7's fixture register was not built: {exc!r}"[:1200]
            finally:
                os.environ["PATH"] = path
            if self.imported_problem is not None:
                self.drop_database(IMPORTED)
        if self.imported_problem is not None:
            _IMPORTED.append(self.imported_problem)
            return
        self.psql(f"ALTER DATABASE {IMPORTED} WITH IS_TEMPLATE true ALLOW_CONNECTIONS false;")

    def launch(self) -> None:
        """`postgres` by `Popen` on this cluster's directories, and wait until it is ready."""
        argv = [self.tool("postgres"), "-D", str(self.root / "data"), "-p", str(PORT),
                "-c", "listen_addresses=", "-c", f"unix_socket_directories={self.root}"]
        for setting in FAST:
            argv += ["-c", setting]
        with open(self.root / "server.log", "ab") as log:
            self.proc = subprocess.Popen(argv, stdin=DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                         env=self.server_env(), preexec_fn=_die_with_parent(os.getpid()))
        end = time.monotonic() + DEADLINE
        while not self.ready():
            if self.proc.poll() is not None:
                raise ClusterError(f"postgres exited {self.proc.returncode} starting: {self.log_tail()}")
            if time.monotonic() > end:
                raise ClusterError(f"postgres was not ready in {DEADLINE:.0f} s: {self.log_tail()}")
            time.sleep(POLL)

    def stop(self) -> None:
        """A fast shutdown: SIGINT to the postmaster this cluster started, and a wait."""
        if self.proc is None or self.proc.poll() is not None:
            raise ClusterError("the cluster is not running, so it cannot be stopped")
        self.proc.send_signal(signal.SIGINT)
        try:
            self.proc.wait(timeout=DEADLINE)
        except subprocess.TimeoutExpired:
            raise ClusterError(f"postgres did not stop in {DEADLINE:.0f} s after SIGINT: "
                               f"{self.log_tail()}") from None

    def start_again(self) -> None:
        """Start the stopped cluster on the same data and socket directories."""
        if self.proc is not None and self.proc.poll() is None:
            raise ClusterError("the cluster is running, so it cannot be started again")
        self.launch()

    def new_database(self, template: str = TEMPLATE) -> str:
        """`CREATE DATABASE t_<n> TEMPLATE <template>`, then, where the
        bootstrap built the template, section 1.4's two database-level
        statements with `-v db=t_<n>`, since a clone does not copy
        `pg_database.datacl`. The first such clone of a run records what its
        `datacl` held before them, which the run's foot prints (open point
        12)."""
        self.count += 1
        name = f"t_{self.count}"
        self.psql(f"CREATE DATABASE {name} TEMPLATE {template};")
        if self.label is not None:
            if not _DATACL:
                acl = self.psql("SELECT coalesce(datacl::text, 'NULL') FROM pg_catalog.pg_database "
                                "WHERE datname = :'db';", variables={"db": name}).stdout.strip()
                _DATACL.append(f"{'empty (NULL)' if acl == 'NULL' else acl}, on {name}, a clone "
                               f"of {template}")
            self.psql(DATABASE_LEVEL, variables={"db": name})
        return name

    def drop_database(self, name: str) -> None:
        self.psql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE);")

    def destroy(self) -> None:
        """SIGQUIT, a wait (SIGKILL after the deadline), and the directory removed."""
        try:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.send_signal(signal.SIGQUIT)          # immediate shutdown
                try:
                    self.proc.wait(timeout=DEADLINE)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait()
        finally:
            if self.root is not None:
                shutil.rmtree(self.root, ignore_errors=True)


class Database:
    """One test's database, and how to reach it as each role."""

    def __init__(self, cluster: Cluster, name: str) -> None:
        self.cluster, self.name, self.host, self.port = cluster, name, cluster.root, PORT
        self.psql_bin = cluster.tool("psql")

    def url(self, user: str = SUPERUSER) -> str:
        return f"postgresql://{user}@{quote(str(self.host), safe='')}:{PORT}/{self.name}"

    def env(self, user: str = SUPERUSER, appname: str = "pytest") -> dict:
        return _client_env(self.host, user, self.name, appname, self.cluster.bindir)

    def psql(self, sql: str, user: str = SUPERUSER, check: bool = True) -> subprocess.CompletedProcess:
        return self.cluster.psql(sql, dbname=self.name, user=user, check=check)

    def session(self, user: str = SUPERUSER, appname: str = "pytest") -> subprocess.Popen:
        """A psql of its own, fed on stdin: a separate session, for concurrency."""
        return subprocess.Popen([self.psql_bin, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=self.env(user, appname))


# ------------------------------------------------------------ pytest
def pytest_configure(config) -> None:
    if required() and probe().problem:
        raise pytest.UsageError(f"{ENV_REQUIRE}=1, so the real-engine tests must run, and they "
                                f"cannot - this run is refused rather than let them skip: "
                                f"{probe().problem}")


def pytest_runtest_logreport(report) -> None:
    if report.skipped and SKIP_TAG in str(report.longrepr):
        _SKIPPED.append(report.nodeid)


def pytest_terminal_summary(terminalreporter) -> None:
    """LOUD, where -q cannot hide it: the skips, where the binaries were found
    whenever they were looked for, and anything a killed session left."""
    if _SKIPPED:
        terminalreporter.write_sep("!", f"{len(_SKIPPED)} real-engine test(s) SKIPPED", yellow=True)
        terminalreporter.write_line(probe().problem or "")
    elif _PROBE is not None and _PROBE.problem is None:
        terminalreporter.write_line(f"real-engine: {_PROBE.found()}")
    if _SWEPT:
        terminalreporter.write_line(f"real-engine: removed {len(_SWEPT)} cluster(s) a killed "
                                    f"session left: {', '.join(_SWEPT)}")
    if _DATACL:
        terminalreporter.write_line(f"real-engine: a clone's datacl before section 1.4's two "
                                    f"statements (open point 12): {_DATACL[0]}")
    for why in _IMPORTED:
        terminalreporter.write_line(f"real-engine: no {IMPORTED}, so the cases that clone it "
                                    f"fail: {why}")


def _started(found: Probe, template_sql, imported: bool = False) -> Cluster:
    cluster = Cluster(found.bindir, template_sql, imported)
    try:
        cluster.start()
    except (ClusterError, OSError, subprocess.SubprocessError) as exc:
        cluster.destroy()
        pytest.fail(f"{SKIP_TAG} is at {found.bindir} ({found.how}), and its cluster did not "
                    f"start: {exc}", pytrace=False)
    return cluster


@_fixture(scope="session")
def pg_engine() -> Probe:
    """The binaries every cluster runs: a skip without them, or under the
    switch a failure (the run was refused already, so this is a guard)."""
    found = probe()
    if found.problem:
        if required():
            pytest.fail(found.problem, pytrace=False)
        pytest.skip(found.problem)
    return found


@_fixture(scope="session")
def pg_template_sql():
    """How `tmpl` is built (T227): P8's bootstrap, `lanes-index bootstrap
    --no-passwords` through the admin service, which makes the schema, the
    roles and their GRANTs. A module may override it with `Bootstrap(sql)`,
    to run its SQL after the bootstrap, or with plain SQL for an empty
    `tmpl`."""
    return Bootstrap()


@_fixture(scope="session")
def pg_cluster(pg_engine, pg_template_sql):
    cluster = _started(pg_engine, pg_template_sql, imported=True)
    patch = pytest.MonkeyPatch()
    patch.setenv("PATH", _engine_first(pg_engine.bindir, os.environ.get("PATH", os.defpath)))
    try:
        yield cluster
    finally:
        patch.undo()
        cluster.destroy()


@_fixture()
def pg(pg_cluster):
    name = pg_cluster.new_database()
    yield Database(pg_cluster, name)
    pg_cluster.drop_database(name)


@_fixture()
def stoppable_cluster(pg_engine, pg_template_sql):
    """A cluster of the test's own, on the same `Cluster` class: `stop()` and
    `start_again()`, and its own template."""
    cluster = _started(pg_engine, pg_template_sql)
    patch = pytest.MonkeyPatch()
    patch.setenv("PATH", _engine_first(pg_engine.bindir, os.environ.get("PATH", os.defpath)))
    try:
        yield cluster
    finally:
        patch.undo()
        cluster.destroy()


# ------------------------------------------------------------ the smoke
def _select_1(cluster: Cluster, dbname: str = "postgres") -> None:
    said = cluster.psql("SELECT 1;", dbname=dbname).stdout.strip()
    if said != "1":
        raise ClusterError(f"SELECT 1 on {dbname} answered {said!r}")


def _smoke_session(found: Probe) -> str:
    cluster = Cluster(found.bindir)
    try:
        cluster.start()
        name = cluster.new_database()
        _select_1(cluster, name)
        cluster.drop_database(name)
        return (f"{name} cloned from the empty {TEMPLATE} in {cluster.root}, and SELECT 1 "
                f"answered 1; started in {cluster.timings['start']:.2f} s")
    finally:
        cluster.destroy()


def _smoke_stoppable(found: Probe) -> str:
    cluster = Cluster(found.bindir)
    try:
        cluster.start()
        first = cluster.proc.pid
        cluster.stop()
        cluster.start_again()
        _select_1(cluster)
        return (f"postmaster {first} stopped by SIGINT, {cluster.proc.pid} started again on "
                f"{cluster.root}, and SELECT 1 answered 1")
    finally:
        cluster.destroy()


SMOKES = {"session": _smoke_session, "stoppable": _smoke_stoppable}


def main(argv: List[str]) -> int:
    """`--smoke <name>…`: 0 when each passes, 1 when one fails, 2 for a usage error."""
    if len(argv) < 2 or argv[0] != "--smoke":
        print(f"usage: python3 -I -B tests/pgcluster.py --smoke <{'|'.join(SMOKES)}>...",
              file=sys.stderr)
        return 2
    unknown = [name for name in argv[1:] if name not in SMOKES]
    if unknown:
        print(f"pgcluster: no smoke named {', '.join(unknown)}; the smokes are "
              f"{', '.join(SMOKES)}", file=sys.stderr)
        return 2
    found = Probe()
    if found.problem:
        print(f"pgcluster: FAIL: {found.problem}", file=sys.stderr)
        return 1
    print(f"pgcluster: {found.found()}")
    failed = 0
    for name in argv[1:]:
        try:
            said = SMOKES[name](found)
        except (ClusterError, OSError, subprocess.SubprocessError) as exc:
            print(f"pgcluster: smoke {name}: FAIL: {exc}", file=sys.stderr)
            failed += 1
        else:
            print(f"pgcluster: smoke {name}: ok: {said}")
    for root in _SWEPT:
        print(f"pgcluster: removed {root}, which a killed session left")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
