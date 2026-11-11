# SPDX-License-Identifier: Apache-2.0
"""Feature 007's test 8, section 4.2 and AT-F1: the rollback (L2-G4; L2-G5's
AT-F1; AT-8; T273; FR-051, FR-052, FR-059; also US6) (opensoft/openRepoTools#165).

T273 writes this module. Its one phase-1 test is T304's own,
`test_rollback_steps_0_and_1_run_only_against_a_scratch_schema` (R-F10-34;
NOTES question 6; B10 tasks:1011-1024; `PLACEMENT.md` section 4), which lane
3's T304 selects with its word `sql_register_rollback and scratch`: those six
ids and nothing else. No other name or id in this module holds that word.

T304'S OWN TEST: steps 0 and 1 of `lanes-index rollback` (lane 3's T304), run
by the shipped `lanes-index` with Q6(c)'s constant unset (`RENDER_GIT_HALF =
False`), as the operator lane, `LANES_LANE=<operator lane>` (B10 tasks:1015),
with this workstation's name and git's author set, on a database of the
session cluster that `lanes-index bootstrap` made for a scratch
`register_schema=` (T109's DEC-23 rendering), brought to `primary` with the
marker `present` by AT-LR006's route (TP:4610-4615). A scratch schema is any
`register_schema=` but the default `lanes_register` (Y:2323; lane 2's
reading). Its ids:

  * `[diverged-refuses-2]`: with `mirror_state.diverged_sha` set, it exits 2,
    and the switch, the marker and the head do not move (B10 tasks:1016);
  * `[step-1-one-transaction]`: one transaction leaves the switch at `files`,
    the head at `k+1`, an operator entry removing `lanes/STORE` last, and the
    marker `removing` (tasks:1017). The case asserts the database's state, not
    the exit after step 1, which T326's steps follow;
  * `[outage-declared-with-mirror-seq]`: its start declares the outage,
    marked as from a rollback, through `outage declare --rollback --mirror-seq
    <k>` (tasks:1020; T121);
  * `[lost-turn-rechecks-step-0]`: a second session holds the head row past
    `rollback`'s `lock_timeout`, so step 1 meets 55P03, and records a
    divergence meanwhile; once released, the rollback goes back to step 0 with
    the head read afresh and exits 2, with the switch and the marker unchanged
    (tasks:1018, :1016);
  * `[database-unreachable-69]`: 69, with neither the switch nor the marker
    changed (tasks:1021);
  * `[not-a-scratch-schema-2]`: with `register_schema=` unset and the constant
    unset, 2 (tasks:1023; `exit-codes.md` :145 at `23e4494`; Y:4872).

D7's 75 (tasks:1019) and the rerun's step 2 (tasks:1022) stay with the phase
G cases (T273b). Each id fails until T107, T109's rendering, T121 and T304
land (L1-A6, L1-A7, L1-A18; R-F10-34). Every id is RE: it asks for the
session cluster, and without PostgreSQL 16 it skips with T205's banner.

READINGS, NOT FOUND IN A CONTRACT:
- AT-LR006'S ROUTE is the documented functions as REGISTER-WRITER, by direct
  calls, as T231's cases reach `primary`: `commit_write` with an `import`
  entry at seq 0, then a `cutover` entry at 1, then `record_marker`, then one
  write at 2, so the rollback's `k` (2) is neither the import's seq nor the
  cutover's.
- "ONE TRANSACTION" is read as: of every `psql` call the rollback makes, one
  alone carries a function that writes (`commit_write`, `record_marker`,
  `switch_to_files`, `record_mirror_state`), and that call is step 1's one
  request, `BEGIN ISOLATION LEVEL SERIALIZABLE`, the `commit_write` call,
  then `COMMIT` (section 3.2's shim logs each call as sent). The database
  then holds what that one call leaves.
- THE SECOND SESSION of `[lost-turn-rechecks-step-0]` is the fixture's
  superuser holding `register_head`'s row `FOR UPDATE`. The divergence is
  recorded in that same session, as REGISTER-WRITER by `record_mirror_state`,
  so its `COMMIT` records it and releases the row at once. The shim holds the
  rollback's second read (the second call carrying `diverged_sha`) until
  then, so the read after the lost turn is the one that finds the divergence,
  whatever the machine's speed.
- "THE DATABASE UNREACHABLE" is a configuration whose URLs name the cluster's
  socket directory at a port where no server listens. The database itself,
  read by the test, shows the switch, the marker and the head unchanged.
- THE CONSTANT: the shipped `lanes-index` must carry `RENDER_GIT_HALF =
  False`. Each id says so where it does not (lane 3's T328 sets it True), since
  the scratch-schema rule holds only while it is unset.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest

from conftest import WINDOWS_SKIP
from pgcluster import SUPERUSER, Database
from sql_register_helpers import (LANES_INDEX, PSQL_SHIM, PSQL_SHIM_CONTROL, PSQL_SHIM_LOG,
                                  RENDER_GIT_HALF_LINE, guard_strip_env)

pytestmark = [WINDOWS_SKIP]

#: The scratch schema the cases bootstrap: any `register_schema=` but the
#: default (Y:2323; lane 2's reading, NOTES question 6).
SCRATCH = "t273_scratch"
DEFAULT_SCHEMA = "lanes_register"
WRITER, READER = "lanes_register_writer", "lanes_register_reader"

#: The logins `lanes-index` connects as, made once per cluster (roles are
#: cluster-wide), members of the writer and the reader groups, with no
#: password: the cluster's socket trusts them.
LOGIN_WRITER, LOGIN_READER = "t273_register_writer", "t273_register_reader"

#: The bootstrap's admin service and the switch's label, which the
#: configuration's `register_label=` names too (the declaration's `database=`).
ADMIN_SERVICE = "t273_admin"
LABEL = "t273"

#: The operator lane (D24; F12), this workstation (Rule 10) and git's author
#: (D15), through git's own variables and no git configuration.
OPERATOR_LANE = "t273-operator"
WS = "ws-t273"
AUTHOR = "T273 operator <t273@example.invalid>"
OPERATOR_GIT = {"GIT_AUTHOR_NAME": "T273 operator", "GIT_AUTHOR_EMAIL": "t273@example.invalid",
                "GIT_COMMITTER_NAME": "T273 operator",
                "GIT_COMMITTER_EMAIL": "t273@example.invalid",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}

#: What AT-LR006's entries carry.
COMMIT_C, TREE_C, MARKER_COMMIT = "c" * 40, "d" * 40, "e" * 40
ARGS_SHA256 = "a" * 64
NOT_AFTER = "2100-01-01T00:00:00Z"
LANES_MD = ["# Lanes"]
STORE_UTC = "2026-11-11T10:00:00Z"
STORE_LINES = ("store=primary", f"database={LABEL}", f"import={COMMIT_C}",
               f"lanes-tree={TREE_C}", f"utc={STORE_UTC}")

#: The divergences the cases record, and who records them.
SHA_DIVERGED, SHA_MEANWHILE = "1" * 40, "2" * 40
WS_MEANWHILE = "ws-t273-meanwhile"

#: The configuration's own values (`c`, `n_a`), so neither is the default.
CONNECT_TIMEOUT, ADDRESSES = 3, 2

#: The functions that write, which "one transaction" counts.
WRITE_CALLS = ("commit_write(", "record_marker(", "switch_to_files(", "record_mirror_state(")

#: The declaration's file, beside the configuration (D20; config.md section 6.1).
OUTAGE_FILE = "register-outage"

#: The second session's `application_name`, which the case waits on.
HOLDER = "t273-holder"


def _private(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def _said(proc) -> str:
    return (f"exit {proc.returncode}\n--- stdout ---\n{(proc.stdout or '')[-3000:]}"
            f"\n--- stderr ---\n{(proc.stderr or '')[-3000:]}")


def _constant_unset() -> None:
    """The shipped `lanes-index` carries Q6(c)'s constant unset: the
    scratch-schema rule this test checks holds only while it does."""
    found = RENDER_GIT_HALF_LINE.findall(LANES_INDEX.read_bytes())
    assert found == [b"False"], (
        f"{LANES_INDEX} carries {found!r} for `RENDER_GIT_HALF = `, not one False line: T304's "
        f"own test runs the shipped lanes-index with the constant unset (B10 tasks:1015), and "
        f"lane 3's T328 sets it")


# ------------------------------------------------------------------ AT-LR006's entries
def _rendered(lines) -> str:
    """The sha256 of a file of `lines`, LF-joined with a final LF, as
    `render_file` renders it."""
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def _entry(kind: str, verb: str, **parts) -> dict:
    """One `commit_write` entry: the journal object, `not_after`, and `parts`."""
    journal = {"kind": kind, "verb": verb, "lane": OPERATOR_LANE, "workstation": WS,
               "author": AUTHOR, "message": f"t273: {kind}"}
    journal.update(parts.pop("journal", {}))
    return {"journal": journal, "not_after": NOT_AFTER, **parts}


def _import_entry() -> dict:
    edits = [{"ord": 1, "op": "create", "path": "lanes/LANES.md"}]
    edits += [{"ord": n, "op": "append", "path": "lanes/LANES.md", "new_text": text}
              for n, text in enumerate(LANES_MD, start=2)]
    return _entry("import", "import", journal={"git_commit": COMMIT_C, "git_tree": TREE_C},
                  edits=edits, files=[{"path": "lanes/LANES.md", "present": True,
                                       "sha256": _rendered(LANES_MD), "final_newline": True}])


def _cutover_entry() -> dict:
    edits = [{"ord": 1, "op": "create", "path": "lanes/STORE"}]
    edits += [{"ord": n, "op": "append", "path": "lanes/STORE", "new_text": line}
              for n, line in enumerate(STORE_LINES, start=2)]
    return _entry("cutover", "cutover", edits=edits,
                  files=[{"path": "lanes/STORE", "present": True,
                          "sha256": _rendered(STORE_LINES), "final_newline": True}])


def _write_entry(text: str) -> dict:
    """A write that appends `text` to `lanes/LANES.md`."""
    return _entry("write", "log", journal={"args_sha256": ARGS_SHA256},
                  edits=[{"ord": 1, "op": "append", "path": "lanes/LANES.md", "new_text": text}],
                  files=[{"path": "lanes/LANES.md", "present": True,
                          "sha256": _rendered([*LANES_MD, text]), "final_newline": True}])


def _open_when_held(fifo: Path, proc: subprocess.Popen, seconds: float = 120):
    """The FIFO's write end, opened once the shim holds a call on it; None
    where `proc` ends, or the time runs out, first. Closing it releases the
    call."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            return os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            time.sleep(0.05)
    return None


# ------------------------------------------------------------------ the register
class RollbackRegister:
    """A database of the session cluster, from `template0`, bootstrapped by
    `lanes-index bootstrap` for `SCRATCH` (T109; DEC-23), brought to `primary`
    with the marker `present` by AT-LR006's route at head `k`, and section
    3.2's shim in front of the real `psql` for every `lanes-index` run here."""

    def __init__(self, cluster, root: Path):
        self.cluster, self.root = cluster, root
        root.mkdir(parents=True, exist_ok=True)
        name = f"t273_{uuid.uuid4().hex[:8]}"
        cluster.psql(f"CREATE DATABASE {name} TEMPLATE template0;")
        self.db = Database(cluster, name)
        try:
            self._bootstrap()
            for login, group in ((LOGIN_WRITER, WRITER), (LOGIN_READER, READER)):
                self.sql(f"DO $l$ BEGIN CREATE ROLE {login} LOGIN IN ROLE {group}; "
                         f"EXCEPTION WHEN duplicate_object THEN NULL; END $l$;")
            self.k = self._to_primary()
        except BaseException:
            cluster.drop_database(name)
            raise
        self.shim = root / "shim"
        self.shim.mkdir()
        (self.shim / "psql").write_text(PSQL_SHIM, encoding="utf-8")
        (self.shim / "psql").chmod(0o755)
        self.arm([])
        (root / "operator").mkdir()

    def drop(self) -> None:
        self.cluster.drop_database(self.db.name)

    # ---------------------------------------------------------------- the SQL side
    def psql(self, script: str, role: str = None, appname: str = "t273") -> subprocess.CompletedProcess:
        """One `psql` as the fixture's superuser, as `role` where one is named,
        with the commit call's settings, so a refusal's first stderr line is
        `ERROR:  <SQLSTATE>: <message>`."""
        head = "\\set VERBOSITY verbose\n\\set SHOW_CONTEXT never\nSET client_encoding = 'UTF8';\n"
        if role:
            head += f"SET ROLE {role};\n"
        return subprocess.run([self.db.psql_bin, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
                              input=head + script, capture_output=True, encoding="utf-8",
                              errors="replace", env=self.db.env(appname=appname), timeout=120,
                              check=False)

    def sql(self, script: str, role: str = None) -> str:
        proc = self.psql(script, role)
        assert proc.returncode == 0, (f"psql{' as ' + role if role else ''} exited "
                                      f"{proc.returncode}: {proc.stderr.strip()}\n{script}")
        return proc.stdout.strip()

    def _bootstrap(self) -> None:
        """`lanes-index bootstrap` through the admin service, with a
        configuration that holds `register_schema=` `SCRATCH` alone."""
        home = self.root / "admin"
        _private(home / ".pg_service.conf",
                 f"[{ADMIN_SERVICE}]\nhost={self.db.host}\nport={self.db.port}\n"
                 f"dbname={self.db.name}\nuser={SUPERUSER}\n")
        conf = _private(self.root / "boot" / "lanes-index.conf", f"register_schema={SCRATCH}\n")
        env = guard_strip_env(os.environ, strip=("XDG_",))
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_STATE_HOME=str(self.root / "admin-state"), LANES_WORKSTATION=WS,
                   LANES_INDEX_CONFIG=str(conf))
        proc = subprocess.run([sys.executable, str(LANES_INDEX), "bootstrap", "--admin-service",
                               ADMIN_SERVICE, "--label", LABEL, "--repository", "opensoft/t273",
                               "--lane", OPERATOR_LANE, "--no-passwords"],
                              capture_output=True, encoding="utf-8", errors="replace", env=env,
                              timeout=300, stdin=subprocess.DEVNULL, check=False)
        assert proc.returncode == 0, (f"the scratch schema's bootstrap (T109's DEC-23 rendering) "
                                      f"failed:\n{_said(proc)}")
        schemas = self.sql(f"SELECT string_agg(nspname, ',' ORDER BY nspname) FROM pg_namespace "
                           f"WHERE nspname IN ('{SCRATCH}', '{DEFAULT_SCHEMA}');")
        assert schemas == SCRATCH, (f"the bootstrap for {SCRATCH} made the schemas {schemas!r}, "
                                    f"not {SCRATCH} alone")

    def window(self) -> dict:
        return json.loads(self.sql(f"SELECT to_jsonb(v) FROM {SCRATCH}.schema_version v;"))

    def commit(self, base: int, body: dict, what: str) -> int:
        """The commit call as a writer sends it (section 1.3's step 3; AT-LR006's
        fixture): one SERIALIZABLE transaction around `commit_write`, as
        REGISTER-WRITER. Returns the entry's seq."""
        literal = json.dumps(body, ensure_ascii=True).replace("'", "''")
        proc = self.psql(f"BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
                         f"SELECT {SCRATCH}.commit_write({base}, '{uuid.uuid4()}'::uuid, "
                         f"{self.window()['version']}, '{self.switch()['generation']}'::uuid, "
                         f"'{literal}'::jsonb);\nCOMMIT;\n", WRITER)
        assert proc.returncode == 0, f"{what}: commit_write refused it: {proc.stderr.strip()}"
        return int(proc.stdout.strip().splitlines()[-1])

    def _to_primary(self) -> int:
        """AT-LR006's route (TP:4610-4615): an import, a cutover and
        `record_marker`, then one write. Returns the head, `k`."""
        imported = self.commit(self.head(), _import_entry(), "the import")
        cut = self.commit(imported, _cutover_entry(), "the cutover")
        marker = self.sql(f"SELECT {SCRATCH}.record_marker({self.window()['version']}, {cut}, "
                          f"'{MARKER_COMMIT}', '{WS}');", WRITER)
        assert marker == "present", f"record_marker answered {marker!r}, not present"
        k = self.commit(cut, _write_entry("t273: a write after the cutover"), "the write")
        switch = self.switch()
        assert (switch["mode"], switch["marker_state"], k) == ("primary", "present", 2), (
            f"AT-LR006's route left the switch {switch} and the head {k}, not primary, present "
            f"and 2")
        return k

    def switch(self) -> dict:
        return json.loads(self.sql(f"SELECT to_jsonb(s) FROM {SCRATCH}.register_switch s;"))

    def head(self) -> int:
        return int(self.sql(f"SELECT seq FROM {SCRATCH}.register_head;"))

    def mirror(self) -> dict:
        return json.loads(self.sql(f"SELECT to_jsonb(m) FROM {SCRATCH}.mirror_state m;"))

    def journal(self) -> list:
        """Each entry's seq, kind and generated `operator` flag, by seq."""
        return json.loads(self.sql(
            f"SELECT coalesce(jsonb_agg(jsonb_build_array(j.seq, j.kind, j.operator) "
            f"ORDER BY j.seq), '[]') FROM {SCRATCH}.journal j;"))

    def state(self) -> dict:
        """The switch whole, the head and the journal: what "does not move" compares."""
        return {"switch": self.switch(), "head": self.head(), "journal": self.journal()}

    def wait_sql(self, count_query: str, what: str, ceiling: float = 10.0) -> None:
        """Poll `count_query` in 0.05 s steps under `ceiling` until it counts
        one row or more."""
        end = time.monotonic() + ceiling
        while time.monotonic() < end:
            if self.sql(count_query) != "0":
                return
            time.sleep(0.05)
        pytest.fail(f"{what}: not seen within {ceiling} s")

    # ---------------------------------------------------------------- lanes-index
    def config(self, name: str, *, schema: str | None = SCRATCH, port: int | None = None) -> Path:
        """A 0600 `lanes-index.conf` in a directory of its own: `mode=index`,
        the URLs of the cluster's socket (at `port` where it is given), the
        label, and `register_schema=` `schema` where it is not None."""
        where = (f"{quote(str(self.db.host), safe='')}:{self.db.port if port is None else port}"
                 f"/{self.db.name}?connect_timeout={CONNECT_TIMEOUT}")
        lines = ["mode=index", f"register_url=postgresql://{LOGIN_WRITER}@{where}",
                 f"reader_url=postgresql://{LOGIN_READER}@{where}",
                 f"register_addresses={ADDRESSES}", f"register_label={LABEL}"]
        if schema is not None:
            lines.append(f"register_schema={schema}")
        return _private(self.root / name / "lanes-index.conf", "\n".join(lines) + "\n")

    def env(self, conf: Path) -> dict:
        """The operator lane's environment (D24): no inherited `PG*`, lane,
        session, git or XDG variable; `LANES_LANE`, this workstation, git's
        author, the configuration, and the shim first on `PATH`."""
        env = guard_strip_env(os.environ, strip=("GIT_", "XDG_", "EMAIL"))
        env.update(HOME=str(self.root / "home"), XDG_STATE_HOME=str(self.root / "state"),
                   XDG_CONFIG_HOME=str(self.root / "config"), LANES_INDEX_CONFIG=str(conf),
                   LANES_LANE=OPERATOR_LANE, LANES_WORKSTATION=WS,
                   PATH=f"{self.shim}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                   **OPERATOR_GIT)
        return env

    def argv(self) -> list:
        return [sys.executable, str(LANES_INDEX), "rollback"]

    def rollback(self, conf: Path) -> subprocess.CompletedProcess:
        """`lanes-index rollback`, the shipped one, in the operator's directory."""
        return subprocess.run(self.argv(), capture_output=True, encoding="utf-8",
                              errors="replace", env=self.env(conf), cwd=str(self.root / "operator"),
                              timeout=180, stdin=subprocess.DEVNULL, check=False)

    def arm(self, arms: list) -> None:
        (self.shim / PSQL_SHIM_CONTROL).write_text(
            json.dumps({"psql": self.db.psql_bin, "arms": arms}), encoding="utf-8")

    def calls(self) -> list:
        """The shim's entries that carried a request, in call order."""
        log = self.shim / PSQL_SHIM_LOG
        if not log.exists():
            return []
        entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
                   if line]
        return [entry for entry in entries if entry.get("kind") != "version"]

    def writes(self) -> list:
        """The calls that carried a function that writes (`WRITE_CALLS`)."""
        return [c for c in self.calls() if any(w in c.get("sent", "") for w in WRITE_CALLS)]


@pytest.fixture
def rb_register(pg_cluster, tmp_path):
    reg = RollbackRegister(pg_cluster, tmp_path / "reg")
    try:
        yield reg
    finally:
        reg.drop()


# =================================================================== T304's own test
def _diverged_refuses_2(reg: RollbackRegister) -> None:
    proc = reg.psql(f"SELECT {SCRATCH}.record_mirror_state('{WS}', '{SHA_DIVERGED}', NULL);",
                    WRITER)
    assert proc.returncode == 0, f"record_mirror_state refused the divergence: {proc.stderr}"
    before = reg.state()
    conf = reg.config("conf")
    proc = reg.rollback(conf)
    assert proc.returncode == 2, f"a rollback with a divergence recorded is not refused 2:\n{_said(proc)}"
    assert f"diverged at {SHA_DIVERGED}" in proc.stderr, _said(proc)
    for way in ("import --single", "render --revert"):
        assert way in proc.stderr, f"the refusal does not name S2's way out {way!r}:\n{_said(proc)}"
    assert reg.writes() == [], (
        f"step 0's database half did not refuse before step 1: a call that writes was sent: "
        f"{[c.get('sent') for c in reg.writes()]}")
    assert reg.state() == before, "the refused rollback moved the switch, the marker or the head"
    assert not (conf.parent / OUTAGE_FILE).exists(), "the refused rollback declared the outage"


def _step_1_one_transaction(reg: RollbackRegister) -> None:
    k = reg.k
    proc = reg.rollback(reg.config("conf"))
    switch = reg.switch()
    assert (switch["mode"], switch["marker_state"]) == ("files", "removing"), (
        f"step 1 left the switch {switch}, not files with the marker removing:\n{_said(proc)}")
    assert (switch["set_seq"], switch["marker_seq"]) == (k + 1, k + 1), (
        f"set_seq and marker_seq are not the rollback's own seq {k + 1}: {switch}")
    assert reg.head() == k + 1, f"the head is {reg.head()}, not k+1 = {k + 1}:\n{_said(proc)}"
    journal = reg.journal()
    assert journal[-1] == [k + 1, "rollback", True], (
        f"the last entry is {journal[-1]}, not the operator's rollback entry at {k + 1}: {journal}")
    assert [seq for seq, _kind, _operator in journal] == list(range(k + 2)), journal
    edits = json.loads(reg.sql(
        f"SELECT coalesce(jsonb_agg(jsonb_build_array(e.ord, e.op, e.path) ORDER BY e.ord), '[]') "
        f"FROM {SCRATCH}.journal_edits e WHERE e.seq = {k + 1};"))
    assert edits == [[1, "remove", "lanes/STORE"]], f"the rollback's entry's edits are {edits}"
    files = json.loads(reg.sql(
        f"SELECT coalesce(jsonb_agg(jsonb_build_array(f.path, f.present) ORDER BY f.path), '[]') "
        f"FROM {SCRATCH}.journal_files f WHERE f.seq = {k + 1};"))
    assert files == [["lanes/STORE", False]], f"the rollback's entry's files rows are {files}"
    writes = reg.writes()
    assert len(writes) == 1 and "commit_write(" in writes[0]["sent"], (
        f"not one call that writes, step 1's commit call: "
        f"{[c.get('sent', '')[:300] for c in writes]}")
    sent = writes[0]["sent"]
    begin, call, end = (sent.find("BEGIN ISOLATION LEVEL SERIALIZABLE"),
                        sent.find("commit_write("), sent.rfind("COMMIT"))
    assert 0 <= begin < call < end, (
        f"step 1's call is not one SERIALIZABLE transaction around commit_write: {sent[:600]}")


def _outage_declared_with_mirror_seq(reg: RollbackRegister) -> None:
    k = reg.k
    conf = reg.config("conf")
    proc = reg.rollback(conf)
    path = conf.parent / OUTAGE_FILE
    assert path.exists(), (f"the rollback's start declared no outage beside its configuration "
                           f"({path}):\n{_said(proc)}")
    lines = path.read_text(encoding="utf-8").splitlines()
    fields = dict(line.split("=", 1) for line in lines)
    assert lines[0] == "format=1", lines
    assert (fields.get("kind"), fields.get("mirror-seq")) == ("rollback", str(k)), (
        f"the declaration is not marked as from a rollback with mirror-seq k = {k}: {lines}")
    assert (fields.get("database"), fields.get("host")) == (LABEL, WS), lines
    assert "until" not in fields, f"a rollback's declaration carries an expiry: {lines}"
    assert "outage declared:" in proc.stdout, _said(proc)


def _lost_turn_rechecks_step_0(reg: RollbackRegister) -> None:
    k = reg.k
    before = reg.state()
    fifo = reg.root / "hold.fifo"
    os.mkfifo(str(fifo), 0o600)
    # The rollback's second read, the second call carrying `diverged_sha`, is held.
    reg.arm([{"mode": "hold", "fifo": str(fifo), "match": "diverged_sha", "call": 2}])
    holder = reg.db.session(appname=HOLDER)
    proc, fd = None, None
    try:
        holder.stdin.write(f"BEGIN;\nSELECT seq FROM {SCRATCH}.register_head WHERE id = 1 "
                           f"FOR UPDATE;\n")
        holder.stdin.flush()
        reg.wait_sql(f"SELECT count(*) FROM pg_stat_activity WHERE application_name = '{HOLDER}' "
                     f"AND state = 'idle in transaction' AND backend_xid IS NOT NULL;",
                     "the second session's lock on the head row")
        proc = subprocess.Popen(reg.argv(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                env=reg.env(reg.config("conf")), cwd=str(reg.root / "operator"))
        fd = _open_when_held(fifo, proc)
        assert fd is not None, "the rollback never reached a second read: it did not lose its turn"
        # Step 1's call has ended; the divergence is recorded and the row released at once.
        out, err = holder.communicate(
            input=(f"SET ROLE {WRITER};\nSELECT {SCRATCH}.record_mirror_state('{WS_MEANWHILE}', "
                   f"'{SHA_MEANWHILE}', NULL);\nCOMMIT;\n"), timeout=60)
        assert holder.returncode == 0, f"the second session could not record the divergence: {err}"
        assert reg.mirror()["diverged_sha"] == SHA_MEANWHILE, reg.mirror()
        os.close(fd)
        fd = None
        out, err = proc.communicate(timeout=120)
    finally:
        if fd is not None:
            os.close(fd)
        for p in (proc, holder):
            if p is not None and p.poll() is None:
                p.kill()
                p.wait()
    ended = f"exit {proc.returncode}\n--- stdout ---\n{out[-3000:]}\n--- stderr ---\n{err[-3000:]}"
    assert proc.returncode == 2, f"the rollback did not end 2 after its lost turn:\n{ended}"
    assert "55P03" in err and "lost its turn" in err, (
        f"step 1 did not meet 55P03 at rollback's lock_timeout and go back:\n{ended}")
    assert f"diverged at {SHA_MEANWHILE}" in err, (
        f"step 0 did not refuse the divergence recorded meanwhile:\n{ended}")
    kinds = ["write" if any(w in c.get("sent", "") for w in WRITE_CALLS) else
             "read" if "diverged_sha" in c.get("sent", "") else "other" for c in reg.calls()]
    assert kinds == ["read", "write", "read"], (
        f"not step 0's read, step 1's one lost call, then step 0's read afresh: {kinds}")
    after = reg.state()
    assert after == before, f"the switch, the marker or the head moved: {before} -> {after}"
    assert after["head"] == k


def _database_unreachable_69(reg: RollbackRegister) -> None:
    port = reg.db.port + 1
    assert not (Path(reg.db.host) / f".s.PGSQL.{port}").exists()
    before = reg.state()
    conf = reg.config("unreachable", port=port)
    proc = reg.rollback(conf)
    assert proc.returncode == 69, f"a rollback that cannot reach the database is not 69:\n{_said(proc)}"
    assert "could not be read" in proc.stderr, _said(proc)
    assert reg.calls(), "the rollback sent no read, so it never met the database's silence"
    assert reg.writes() == [], "a call that writes was sent"
    assert reg.state() == before, "the switch, the marker or the head moved"
    assert not (conf.parent / OUTAGE_FILE).exists(), "the failed rollback declared the outage"


def _not_a_scratch_schema_2(reg: RollbackRegister) -> None:
    before = reg.state()
    conf = reg.config("default-schema", schema=None)
    proc = reg.rollback(conf)
    assert proc.returncode == 2, (f"a rollback with register_schema= unset is not refused 2 "
                                  f"while the constant is unset:\n{_said(proc)}")
    assert f"register_schema={DEFAULT_SCHEMA}" in proc.stderr and "scratch schema" in proc.stderr, (
        f"the refusal does not name the default schema and the scratch-schema rule:\n{_said(proc)}")
    assert reg.calls() == [], f"the refused rollback sent a request: {reg.calls()}"
    assert reg.state() == before, "the switch, the marker or the head moved"
    assert not (conf.parent / OUTAGE_FILE).exists(), "the refused rollback declared the outage"


T304_CASES = {
    "diverged-refuses-2": _diverged_refuses_2,
    "step-1-one-transaction": _step_1_one_transaction,
    "outage-declared-with-mirror-seq": _outage_declared_with_mirror_seq,
    "lost-turn-rechecks-step-0": _lost_turn_rechecks_step_0,
    "database-unreachable-69": _database_unreachable_69,
    "not-a-scratch-schema-2": _not_a_scratch_schema_2,
}


@pytest.mark.parametrize("case", list(T304_CASES))
def test_rollback_steps_0_and_1_run_only_against_a_scratch_schema(rb_register, case):
    """T304's own test (R-F10-34): steps 0 and 1 of the shipped `lanes-index
    rollback`, the constant unset, on `SCRATCH` at `primary` with the marker
    `present` and head `k`. Each id is in the module's docstring."""
    _constant_unset()
    T304_CASES[case](rb_register)
