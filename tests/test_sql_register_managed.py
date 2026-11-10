# SPDX-License-Identifier: Apache-2.0
"""Feature 007's AT-LRMPG, a managed PostgreSQL, its phase-N cases (T224;
FR-009, FR-053, FR-054, FR-055, FR-059) (opensoft/openRepoTools#165).

The test plan's thirteen phase-N names, byte for byte (AT-LRMPG, "Tests."),
and lane 1's two new since v3f, `dump_restore_privileges` (L1-2, T109's option
(a)) and `rotate_dump_job` (L1-3, T110's `rotate --dump-job`): 15 tests. The
phase-W cases, the logins' writes and reads through the flipped copy, are
T258's and are not here.

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
`tests/pgcluster.py` does not give yet: each id fails by `TlsEnvironment`'s
own assertion until T229 lands, and skips with T205's banner where there is
no engine. What this module reads of that fixture, from F12b's T229 text and
not from a contract, is `TlsEnvironment`'s docstring.

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
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import REPO, WINDOWS_SKIP
from sql_register_helpers import REGISTER_FAKE_PSQL, guard_strip_env

pytestmark = [WINDOWS_SKIP]

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


@pytest.fixture(scope="session")
def pg_template_sql():
    """AN EMPTY TEMPLATE FOR THIS MODULE'S CLUSTERS. `pg_template_sql` is the
    fixture's overridable hook, and T227 makes its default the bootstrap,
    with T228's logins, on every cluster. AT-LRMPG's server is a new one
    whose only admin is CNPG's `initdb` owner, which runs the bootstrap and
    makes the logins itself: roles a superuser made first would leave that
    admin without ADMIN OPTION on them (PostgreSQL 16) and give `login add`
    logins that exist already. So each `stoppable_cluster` here starts
    empty, as the provider's does."""
    return ""


def _said(proc: subprocess.CompletedProcess) -> str:
    return f"exit {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"


def _private(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def _run(argv: list, env: dict, cwd: Path, *, pty_run: bool) -> subprocess.CompletedProcess:
    """`argv`, its stdout a pipe, or a terminal (`pty.openpty()`) where
    `pty_run`; its stdin is /dev/null and its stderr a pipe."""
    if not pty_run:
        return subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(cwd),
                              timeout=300, stdin=subprocess.DEVNULL)
    import pty
    primary, secondary = pty.openpty()
    try:
        proc = subprocess.Popen(argv, stdout=secondary, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, env=env, cwd=str(cwd))
        os.close(secondary)
        secondary = -1
        out = b""
        while True:
            try:
                chunk = os.read(primary, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        err = proc.stderr.read().decode("utf-8", "replace")
        proc.wait(timeout=300)
    finally:
        os.close(primary)
        if secondary >= 0:
            os.close(secondary)
    return subprocess.CompletedProcess(argv, proc.returncode,
                                       out.decode("utf-8", "replace").replace("\r\n", "\n"), err)


def _objects(text: str) -> list:
    """Each object line's (what, state), in order."""
    return [(m.group("what"), m.group("state")) for m in OBJECT_LINE.finditer(text)]


def _passwords(text: str) -> dict:
    """Each password-file line, by login."""
    found: dict = {}
    for m in PASS_LINE.finditer(text):
        assert m.group("login") not in found, f"{m.group('login')}'s line is printed twice:\n{text}"
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
                f"psql gave no {marker!r} within {deadline:.0f} s: {self.err[start:]!r}")
            ready, _, _ = select.select([fd], [], [], 0.2)
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                self.err += chunk
        return self.err[start:].decode("utf-8", "replace")

    def close(self) -> subprocess.CompletedProcess:
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        out = self.proc.stdout.read().decode("utf-8", "replace")
        self.err += self.proc.stderr.read()
        self.proc.wait(timeout=60)
        return subprocess.CompletedProcess([], self.proc.returncode, out,
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
        self.cluster = cluster if cluster is not None else request.getfixturevalue(
            "stoppable_cluster")
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
        self.cluster.psql(f"CREATE ROLE {ADMIN} LOGIN CREATEROLE CREATEDB NOSUPERUSER;")
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
        assert proc.returncode == 0, f"the bootstrap failed:\n{_said(proc)}"

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
            assert proc.returncode == 0, f"login add {who} failed:\n{_said(proc)}"
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
        assert proc.returncode == 0, f"{login} could not log in to SHOW its floors:\n{_said(proc)}"
        return dict(zip(names, proc.stdout.split()))

    def role(self, login: str) -> dict:
        """A role's attributes, its own settings, its verifier and its groups,
        read by the provider."""
        row = self.value(
            "SELECT json_build_object('canlogin', a.rolcanlogin, 'super', a.rolsuper, "
            "'config', coalesce(a.rolconfig, '{}'), 'verifier', a.rolpassword, "
            "'groups', ARRAY(SELECT g.rolname::text FROM pg_auth_members m JOIN pg_roles g "
            "ON g.oid = m.roleid WHERE m.member = a.oid ORDER BY 1)) "
            f"FROM pg_authid a WHERE a.rolname = '{login}';", "postgres")
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
            assert proc.returncode == 0, f"the {kind} entry did not commit:\n{_said(proc)}"
        seq = self.value(f"SELECT seq FROM {REGISTER}.register_head;", db)
        client = self.value(f"SELECT version FROM {REGISTER}.schema_version;", db)
        proc = self.as_login(login, db, f"SELECT {REGISTER}.record_marker(:client, :seq, "
                             ":'commit', :'ws');\n", passfile, client=client, seq=seq,
                             commit=MARKER_COMMIT, ws=WS)
        assert proc.returncode == 0 and proc.stdout.strip() == "present", _said(proc)

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
            "SELECT string_agg(format('%I.%I', schemaname, tablename), ' ' ORDER BY 1) "
            f"FROM pg_tables WHERE schemaname IN ('{REGISTER}', '{INDEX}');", db).split()
        views = self.value(
            "SELECT string_agg(format('%I.%I', schemaname, viewname), ' ' ORDER BY 1) "
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
        assert secret not in log, f"the server's log holds {login}'s password in clear text"


# ============================================================ the bootstrap
def test_bootstrap_without_a_superuser_runs_twice_with_one_catalog(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    first = m.bootstrap(service, "--no-passwords")
    assert first.returncode == 0, f"the first bootstrap, as {ADMIN}, failed:\n{_said(first)}"
    assert m.role(ADMIN)["super"] is False, f"{ADMIN} is a superuser: the case proves nothing"
    catalog = m.catalog("t224_reg")
    second = m.bootstrap(service, "--no-passwords")
    assert second.returncode == 0, f"the second bootstrap failed:\n{_said(second)}"
    states = {state for _what, state in _objects(second.stdout)}
    assert states == {"unchanged"}, f"the second run changed something:\n{_said(second)}"
    assert m.catalog("t224_reg") == catalog, "the second run changed the catalog"
    # A SECURITY DEFINER function owned by a role that cannot log in works:
    # `commit_write`, as a writer login, commits an import entry.
    files = m.logins(service, "e1", dump=False)
    proc = m.commit("t224_reg", "lanes_w_e1", files["lanes_w_e1"],
                    m.entry("t224_reg", "import", "lanes/LANES.md", "# Lanes"))
    assert proc.returncode == 0, f"commit_write as lanes_w_e1 did not commit:\n{_said(proc)}"
    assert m.value(f"SELECT seq FROM {REGISTER}.register_head;", "t224_reg") == "0"


def test_bootstrap_refuses_a_database_its_admin_does_not_own(tmp_path, request):
    m = Managed(request, tmp_path)
    m.psql("CREATE DATABASE t224_theirs;")                  # the provider's, not the admin's
    service = m.service("t224_theirs")
    acl = m.value("SELECT coalesce(datacl::text, '-') FROM pg_database "
                  "WHERE datname = 't224_theirs';", "postgres")
    proc = m.bootstrap(service, "--no-passwords")
    assert proc.returncode == 2, f"bootstrap on a database its admin does not own is not 2:\n{_said(proc)}"
    assert m.value(f"SELECT count(*) FROM pg_namespace WHERE nspname = '{REGISTER}';",
                   "t224_theirs") == "0", "the refused bootstrap made the register's schema"
    # THE CONTROL: there, as that admin, the database-level REVOKE and GRANT
    # only warn, 01006 and 01007, and `datacl` is unchanged.
    warned = m.psql("\\set VERBOSITY verbose\nREVOKE ALL ON DATABASE t224_theirs FROM PUBLIC;\n"
                    f"GRANT CONNECT ON DATABASE t224_theirs TO {ADMIN};\n", user=ADMIN)
    assert "01006" in warned.stderr and "01007" in warned.stderr, _said(warned)
    assert m.value("SELECT coalesce(datacl::text, '-') FROM pg_database "
                   "WHERE datname = 't224_theirs';", "postgres") == acl


# ============================================================ the login step
def test_login_add_makes_an_engineers_two_logins_with_their_floors_and_prints_their_lines_once(
        tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    proc = m.login("add", "e1", service)
    assert proc.returncode == 0, f"login add e1 failed:\n{_said(proc)}"
    lines = _passwords(proc.stdout)
    assert sorted(lines) == ["lanes_r_e1", "lanes_w_e1"], _said(proc)
    for key, login in (("register_url=", "lanes_w_e1"), ("reader_url=", "lanes_r_e1")):
        urls = [line for line in proc.stdout.splitlines() if line.startswith(key)]
        assert len(urls) == 1 and f"//{login}@" in urls[0], f"no one {key} line for {login}"
    files = m.passfiles(proc.stdout)
    for login, half, group in (("lanes_w_e1", "w", WRITER), ("lanes_r_e1", "r", READER)):
        role = m.role(login)
        assert role["canlogin"] and role["groups"] == [group], (login, role)
        assert sorted(role["config"]) == sorted(ROLCONFIG[half]), (login, role["config"])
        assert role["verifier"].startswith("SCRAM-SHA-256$"), f"{login}'s password is not SCRAM"
        assert {k: v for k, v in m.shown(login, "t224_reg", files[login]).items()
                if k in SHOWN[half]} == SHOWN[half]
    _no_clear_text(m.log(), lines)
    # THE DUMP JOB: `lanes_register_dump`, a member of READER alone, with the
    # reader's floors, and its one line.
    dump = m.login("add", DUMP, service)
    assert dump.returncode == 0, f"login add --dump-job failed:\n{_said(dump)}"
    assert sorted(_passwords(dump.stdout)) == [DUMP], _said(dump)
    role = m.role(DUMP)
    assert role["groups"] == [READER] and sorted(role["config"]) == sorted(ROLCONFIG["r"]), role
    _no_clear_text(m.log(), _passwords(dump.stdout))


def test_login_add_run_again_puts_back_a_lost_membership_and_changes_nothing_else(
        tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    m.logins(service, "e1", dump=False)
    before = {login: m.role(login) for login in ("lanes_w_e1", "lanes_r_e1")}
    m.psql(f"REVOKE {WRITER} FROM lanes_w_e1;")
    assert m.role("lanes_w_e1")["groups"] == [], "the membership was not revoked by hand"
    again = m.login("add", "e1", service)
    assert again.returncode == 0, f"login add e1, run again, failed:\n{_said(again)}"
    assert _passwords(again.stdout) == {}, f"the rerun printed a password line:\n{_said(again)}"
    after = {login: m.role(login) for login in ("lanes_w_e1", "lanes_r_e1")}
    assert after == before, f"the rerun changed more than the membership: {before} -> {after}"


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
    assert proc.returncode == 2 and state == "FAIL", f"check 12 does not fail:\n{_said(proc)}"
    assert "lanes_w_bare" in reason, f"check 12 does not name the login:\n{_said(proc)}"
    for floor in ROLCONFIG["w"]:
        assert floor.split("=", 1)[0] in reason, f"check 12 does not name {floor}:\n{_said(proc)}"


def test_ready_check_12_passes_the_logins_the_step_made(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    files = m.logins(service, "e1", dump=False)
    config = m.config("e1", m.socket_url("lanes_w_e1", "t224_reg"), files["lanes_w_e1"],
                      m.socket_url("lanes_r_e1", "t224_reg"), files["lanes_r_e1"])
    proc = m.ready(config)
    state, reason = _checks(proc.stdout).get(12, ("", ""))
    assert state == "ok", f"check 12 fails the logins the step made:\n{_said(proc)}"
    # "check 12 passes and prints each login's floors" (AT-LRMPG's oracle).
    for half in ("w", "r"):
        for floor in ROLCONFIG[half]:
            assert floor.split("=", 1)[0] in reason, (
                f"check 12's line does not print {floor}:\n{_said(proc)}")


def test_login_rotate_keeps_an_open_session_and_refuses_the_old_password(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    old = m.logins(service, "e1", dump=False)
    held = m.session("lanes_w_e1", "t224_reg", old["lanes_w_e1"])
    assert "ERROR" not in held.send("SELECT 'before';", "t224-before"), "the session did not open"
    proc = m.login("rotate", "e1", service)
    assert proc.returncode == 0, f"login rotate e1 failed:\n{_said(proc)}"
    new = m.passfiles(proc.stdout, "passfiles-new")
    assert sorted(new) == ["lanes_r_e1", "lanes_w_e1"], _said(proc)
    assert "ERROR" not in held.send("SELECT 'after';", "t224-after")
    ended = held.close()
    assert ended.returncode == 0 and ended.stdout.split() == ["before", "after"], (
        f"the session open across the rotation did not go on:\n{_said(ended)}")
    for login in ("lanes_w_e1", "lanes_r_e1"):
        refused = m.as_login(login, "t224_reg", "SELECT 1;\n", old[login])
        assert refused.returncode == 2 and "28P01" in refused.stderr + refused.stdout, (
            f"{login}'s old password file is not refused at login:\n{_said(refused)}")
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
        assert proc.returncode == 2, f"[{case}] {argv[1:3]} is not refused with 2:\n{_said(proc)}"
        assert _making(bench.requests()) == [], f"[{case}] the refused login sent a making statement"
        for value in argv:
            if "=" in value or "://" in value:
                assert value not in proc.stdout + proc.stderr, f"[{case}] the refusal echoed {value}"
    # THE CONTROL: a good name, under the pty, gets past every refusal and
    # reaches the admin service (the fake), so each refusal was the case's.
    control = bench.run(["login", "add", "e1", "--admin-service", "t224_admin"], pty_run=True)
    assert bench.requests(), (
        f"[{case}] the control, a good name under a terminal, sent nothing:\n{_said(control)}")


# ============================================================ the revoke
def test_an_open_session_gets_42501_between_the_revokes_steps_then_57p01(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    files = m.logins(service, "e1", "e2", dump=False)
    held = m.session("lanes_w_e2", "t224_reg", files["lanes_w_e2"])
    assert "ERROR" not in held.send("SELECT 1;", "t224-open")
    # [steps-by-hand]: the revoke block's steps 1 and 2, by the admin.
    m.psql(f"ALTER ROLE lanes_w_e2 NOLOGIN;\nREVOKE {WRITER} FROM lanes_w_e2;\n", "t224_reg",
           user=ADMIN)
    write = held.send(f"SELECT {REGISTER}.commit_write(NULL, NULL, NULL, NULL, NULL);",
                      "t224-write")
    read = held.send(f"SELECT seq FROM {REGISTER}.register_head;", "t224-read")
    for what, said in (("write", write), ("read", read)):
        assert "42501" in said and f"permission denied for schema {REGISTER}" in said, (
            f"the open session's {what} between steps 2 and 3 is not 42501: {said}")
    # Step 3 by hand: its sessions ended.
    m.psql("GRANT lanes_w_e2 TO CURRENT_USER WITH INHERIT TRUE, SET FALSE;\n"
           "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = 'lanes_w_e2';\n"
           "REVOKE lanes_w_e2 FROM CURRENT_USER;\n", "t224_reg", user=ADMIN)
    after = held.send(f"SELECT seq FROM {REGISTER}.register_head;", "t224-after")
    ended = held.close()
    said = after + ended.stderr
    assert "57P01" in said or "terminating connection due to administrator command" in said or \
        "server closed the connection" in said, f"the next statement after step 3 was answered: {said}"
    assert "permission denied" not in after, f"after step 3 a statement got 42501, not 57P01: {after}"
    assert m.connects("lanes_w_e1", "t224_reg", files["lanes_w_e1"]), "e1 can no longer log in"


# ============================================================ the dump
def test_the_reader_login_dumps_both_schemas_and_still_cannot_write(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    files = m.logins(service, "e1")
    proc = m.commit("t224_reg", "lanes_w_e1", files["lanes_w_e1"],
                    m.entry("t224_reg", "import", "lanes/LANES.md", "# Lanes"))
    assert proc.returncode == 0, _said(proc)
    # The indexer's store, made as the indexer (`lanes-index`'s own #160
    # scripts are not run here: see the report), with a row.
    m.psql(f"SET ROLE {INDEXER};\nCREATE TABLE {INDEX}.t224_rows (id int PRIMARY KEY);\n"
           f"INSERT INTO {INDEX}.t224_rows VALUES (1);\n", "t224_reg")
    dumped, target = m.dump("t224_reg", files[DUMP], "first.dump")
    assert dumped.returncode == 0, f"the dump job's dump failed:\n{_said(dumped)}"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600, "the dump file is not 0600"
    listing = subprocess.run([m.cluster.tool("pg_restore"), "--list", str(target)],
                             capture_output=True, text=True, timeout=120, check=False).stdout
    for name in m.value("SELECT string_agg(schemaname || ' ' || tablename, ',') FROM pg_tables "
                        f"WHERE schemaname IN ('{REGISTER}', '{INDEX}');", "t224_reg").split(","):
        schema, table = name.split()
        assert re.search(rf"TABLE {schema} {table}\b", listing), f"the dump lacks {name}"
    head = subprocess.run([m.cluster.tool("pg_restore"), "--data-only", f"--schema={REGISTER}",
                           "--table=register_head", "--file=-", str(target)],
                          capture_output=True, text=True, timeout=120, check=False).stdout
    b = m.value(f"SELECT seq FROM {REGISTER}.register_head;", "t224_reg")
    assert re.search(rf"^1\t{b}\b", head, re.M) or re.search(rf"\t{b}\b", head), (
        f"the dump's register_head does not give the head {b}:\n{head}")
    # M6: a sequence the indexer makes later is dumped, by the default privilege.
    m.psql(f"SET ROLE {INDEXER};\nCREATE SEQUENCE {INDEX}.t224_seq_ok;\n", "t224_reg")
    again, _ = m.dump("t224_reg", files[DUMP], "second.dump")
    assert again.returncode == 0, f"a later sequence stopped the dump:\n{_said(again)}"
    # THE CONTROLS: the default privilege revoked before a sequence is made,
    # and the reader's SELECT on doc_lines' sequence revoked.
    m.psql(f"ALTER DEFAULT PRIVILEGES FOR ROLE {INDEXER} IN SCHEMA {INDEX} "
           f"REVOKE SELECT ON SEQUENCES FROM {READER};\n", "t224_reg", user=ADMIN)
    m.psql(f"SET ROLE {INDEXER};\nCREATE SEQUENCE {INDEX}.t224_seq_hidden;\n", "t224_reg")
    hidden, _ = m.dump("t224_reg", files[DUMP], "third.dump")
    assert hidden.returncode != 0 and "t224_seq_hidden" in hidden.stderr, _said(hidden)
    m.psql(f"SET ROLE {INDEXER};\nDROP SEQUENCE {INDEX}.t224_seq_hidden;\n", "t224_reg")
    m.psql(f"SET ROLE {OWNER};\nREVOKE SELECT ON {REGISTER}.doc_lines_line_id_seq FROM {READER};\n",
           "t224_reg")
    seq, _ = m.dump("t224_reg", files[DUMP], "fourth.dump")
    assert seq.returncode != 0 and "doc_lines_line_id_seq" in seq.stderr, _said(seq)
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
            f"the dump login's {statement!r} was not refused with 42501:\n{_said(tried)}")


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
        assert proc.returncode == 0, _said(proc)
    dumped, target = m.dump("t224_reg", files[DUMP], "source.dump")
    assert dumped.returncode == 0, f"the source's dump failed:\n{_said(dumped)}"
    return m, files, target


def _restored(request, root: Path, source_dump: Path):
    """R-P41's order on a new cluster with the admin role: the database
    created first by the admin; then, through one service naming it,
    `bootstrap --roles-only`, `login add e1` and `login add --dump-job`, the
    restore, and `bootstrap`. Returns the target, its runs and its files."""
    target = Managed(request, root, cluster=_another_cluster(request))
    service = target.database("t224_reg")
    roles = target.bootstrap(service, "--roles-only", pty_run=True)
    assert roles.returncode == 0, f"bootstrap --roles-only failed:\n{_said(roles)}"
    files = target.logins(service, "e1", folder="passfiles-new")
    env = {k: v for k, v in target.env.items() if not k.startswith("PG")}
    env["PGSERVICE"] = service
    restore = subprocess.run([target.cluster.tool("pg_restore"), "--exit-on-error", "--no-password",
                              "--dbname=t224_reg", str(source_dump)],
                             capture_output=True, text=True, timeout=300, env=env, check=False)
    assert restore.returncode == 0, f"pg_restore through the admin service failed:\n{_said(restore)}"
    mark = len(target.log())
    after = target.bootstrap(service, pty_run=True)
    assert after.returncode == 0, f"bootstrap after the restore failed:\n{_said(after)}"
    return target, roles, after, files, mark


def test_a_restore_from_the_dump_equals_its_source_with_new_passwords(tmp_path, request):
    source, old, dump = _source(request, tmp_path / "source", primary=False)
    target, roles, after, new, _mark = _restored(request, tmp_path / "target", dump)
    # `--roles-only` prints the indexer's line, and `created` for each of the
    # three database-level statements (option (a)).
    assert sorted(_passwords(roles.stdout)) == [INDEXER], _said(roles)
    objects = dict(_objects(roles.stdout))
    for words in DB_LEVEL:
        assert [state for what, state in objects.items() if words in what] == ["created"], (
            f"--roles-only does not print `created` for {words}:\n{_said(roles)}")
    assert {state for _what, state in _objects(after.stdout)} == {"unchanged"}, _said(after)
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
    assert roles.returncode == 0, f"bootstrap --roles-only failed:\n{_said(roles)}"
    assert {state for _what, state in _objects(roles.stdout)} == {"unchanged"}, _said(roles)
    assert _passwords(roles.stdout) == {}, f"--roles-only printed a password line:\n{_said(roles)}"
    new: dict = {}
    for who in ("e1", DUMP):
        proc = copy.login("rotate", who, service)
        assert proc.returncode == 0, f"login rotate {who} failed:\n{_said(proc)}"
        new.update(copy.passfiles(proc.stdout, "passfiles-new"))
        _no_clear_text(copy.log(), _passwords(proc.stdout))
    assert sorted(new) == sorted(logins)
    for login in logins:
        assert not copy.connects(login, "t224_reg", old[login]), f"{login}'s old file still connects"
        assert copy.connects(login, "t224_reg", new[login]), f"{login}'s new line does not connect"


# ============================================================ check 11
class TlsEnvironment:
    """Check 11's environment on section 5.6's TLS cluster, T229's
    `tls_cluster`, which `tests/pgcluster.py` does not give yet. Until it
    does, each id fails here by its own assertion on an engine bench, and
    skips with T205's banner where `pg_engine` finds none.

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
    (T230's `[leaf-only]`), and `start_again(standby=True)`, whose readiness
    poll takes `standby` in place of `ready` (the test plan's
    `[in-recovery]`)."""

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
        import inspect
        accepted = inspect.signature(self.tls.start_again).parameters
        for name in option:
            assert name in accepted, f"T229's tls_cluster.start_again takes no {name}= option"
        self.tls.stop()
        if option.get("standby"):
            (Path(self.tls.root) / "data" / "standby.signal").touch()
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


@pytest.mark.parametrize("case", list(CHECK_11))
def test_ready_check_11_needs_tls_and_the_primary(tmp_path, request, case):
    env = TlsEnvironment(request, tmp_path)
    make, passes = CHECK_11[case]
    proc = env.ready(make(env))
    state, reason = _checks(proc.stdout).get(11, ("", ""))
    if passes:
        assert state == "ok", f"[{case}] check 11 does not pass:\n{_said(proc)}"
    else:
        assert state == "FAIL" and proc.returncode == 2, (
            f"[{case}] check 11 does not fail, or ready does not exit 2:\n{_said(proc)}")
        assert env.login in reason, f"[{case}] check 11 does not name the connection:\n{_said(proc)}"


# ============================================================ tls_at_load
#
# T230, lane 1's `tls_at_load` (L1-1; T104; CLI4.5 section 2.5): each item
# through `lanes-index mode`, with `mode=index` in the file, so Q6(c) never
# answers. FP: nothing connects. A refused file is 2 from `mode`, naming the
# key and what is missing and printing no URL; 3 from `journal --write-id`
# (CO-3); and 1 under `register read --for guard`'s prefetch, form 2 (O14).

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
        assert proc.returncode == 3, f"[{item}] journal --write-id on a refused file is not 3:\n{_said(proc)}"
    elif item == "for-guard":
        repo = tmp_path / "repo"
        repo.mkdir()
        proc = bench.run(["register", "read", "--for", "guard", "--prefetch", "--cache",
                          str(tmp_path / "cache"), "--pid", str(os.getpid()), "--repo", str(repo)],
                         pty_run=False)
        assert proc.returncode == 1, (
            f"[{item}] register read --for guard --prefetch on a refused file is not 1:\n{_said(proc)}")
    else:
        proc = bench.run(["mode"], pty_run=False)
        if expect == "index":
            assert (proc.returncode, proc.stdout) == (0, "index\n"), f"[{item}] does not load:\n{_said(proc)}"
        else:
            key, missing = expect
            assert proc.returncode == 2 and proc.stdout == "", f"[{item}] is not refused with 2:\n{_said(proc)}"
            assert key in proc.stderr and missing in proc.stderr, (
                f"[{item}] the refusal does not name {key} and {missing}:\n{_said(proc)}")
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
    db = "t224_reg"
    acl = target.value(f"SELECT coalesce(datacl::text, '') FROM pg_database WHERE datname = '{db}';",
                       "postgres")
    assert not re.search(r"(^|[{,])=[A-Za-z]*c", acl), f"PUBLIC holds CONNECT on {db}: {acl}"
    target.psql("CREATE ROLE t224_outsider LOGIN PASSWORD 'outside-t224';")
    outsider = _private(target.home / "passfiles" / "t224_outsider", f"*:*:{db}:t224_outsider:outside-t224\n")
    refused = target.as_login("t224_outsider", db, "SELECT 1;\n", outsider)
    assert refused.returncode == 2 and "permission denied for database" in refused.stderr, _said(refused)
    for role in (WRITER, READER, INDEXER):
        assert target.value(f"SELECT has_database_privilege('{role}', '{db}', 'CONNECT');",
                            "postgres") == "t", f"{role} holds no CONNECT on {db}"
    target.psql(f"SET ROLE {OWNER};\nCREATE FUNCTION {REGISTER}.t224_later() RETURNS int "
                "LANGUAGE sql AS 'SELECT 1';\n", db)
    assert target.value(f"SELECT has_function_privilege('t224_outsider', '{REGISTER}.t224_later()', "
                        "'EXECUTE');", db) == "f", "an outsider may execute a later function of the owner's"
    # `bootstrap` after the restore re-ran no statement and wrote no label.
    assert {state for _what, state in _objects(after.stdout)} == {"unchanged"}, _said(after)
    since = target.log()[mark:]
    ran = [line for line in since.splitlines()
           if re.search(r"statement: .*\b(CREATE|GRANT|REVOKE|ALTER|INSERT|UPDATE)\b", line)]
    assert ran == [], f"bootstrap after the restore re-ran statements: {ran}"
    assert target.value(f"SELECT database_label FROM {REGISTER}.register_switch;", db) == label


def test_rotate_dump_job_changes_only_the_dump_logins_password(tmp_path, request):
    m = Managed(request, tmp_path)
    service = m.database("t224_reg")
    m.bootstrapped(service)
    old = m.logins(service, "e1")
    verifiers = {login: m.role(login)["verifier"] for login in ("lanes_w_e1", "lanes_r_e1", DUMP)}
    # Off a terminal it refuses with 2 and changes nothing.
    piped = m.login("rotate", DUMP, service, pty_run=False)
    assert piped.returncode == 2, f"rotate --dump-job through a pipe is not 2:\n{_said(piped)}"
    assert m.role(DUMP)["verifier"] == verifiers[DUMP], "the refused rotation changed the verifier"
    # Neither an engineer nor --dump-job, or both: 64.
    for argv in (["login", "rotate", "--admin-service", service],
                 ["login", "rotate", "e1", "--dump-job", "--admin-service", service]):
        usage = m.lanes(*argv, pty_run=True)
        assert usage.returncode == 64, f"{argv[1:]} is not usage, 64:\n{_said(usage)}"
    proc = m.login("rotate", DUMP, service)
    assert proc.returncode == 0, f"login rotate --dump-job failed:\n{_said(proc)}"
    lines = _passwords(proc.stdout)
    assert sorted(lines) == [DUMP], f"not one line, the dump login's:\n{_said(proc)}"
    new = m.passfiles(proc.stdout, "passfiles-new")
    assert m.role(DUMP)["verifier"] != verifiers[DUMP], "the dump login's verifier did not change"
    for login in ("lanes_w_e1", "lanes_r_e1"):
        assert m.role(login)["verifier"] == verifiers[login], f"{login}'s verifier changed"
    assert not m.connects(DUMP, "t224_reg", old[DUMP]), "the old dump password still logs in"
    dumped, _target = m.dump("t224_reg", new[DUMP], "rotated.dump")
    assert dumped.returncode == 0, f"the new dump password does not dump:\n{_said(dumped)}"
    _no_clear_text(m.log(), lines)
