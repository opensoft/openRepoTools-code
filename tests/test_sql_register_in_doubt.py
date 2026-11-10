# SPDX-License-Identifier: Apache-2.0
"""AT-LR007 and AT-LR011: the order of `commit_write`'s first checks, and
`find_write` (#165; FR-008, FR-016).

PHASE N, ON A REAL POSTGRESQL 16, by direct calls to lane 1's SQL (design.md
§1.3, §1.3.1). `commit_write` takes the head row's lock, then checks the
generation (LR007 `generation`), then the write id (LR006, or LR007
`another-write` for another write's entry), and only then the head (LR001),
the version (LR003) and the switch (LR002), so a write id of another
generation never ends in 69 or 0 (V2's S-3). `find_write`, F3's one lookup,
waits on the server's clock, holding no lock, until it has passed
`p_not_after`, at most 3 s (LR011 past that); then it takes the head row's
lock under the caller's `lock_timeout`, checks the clock again, then the
generation, then the entry, and returns the write's seq, or NULL.

THE FIXTURE, AT-LR006'S, ON A CLONE OF ITS OWN: each test clones `tmpl`
(T205 makes it, T227 builds it by the bootstrap), as T221's `[new-write]`
does, runs §1.4's two database-level statements on the clone, and drops it
`WITH (FORCE)` at the end. Nothing needs `tmpl_imported` (lane 3, #165
6768050756 point 1, which lane 2 accepts; R-F11-23), so T114 need not wait for
T115. A clone of `tmpl` is at `files` with the marker `absent` and an empty
journal, and each test brings it where it needs by AT-LR006's route
(TP:4610–4615), by the documented functions as `lanes_w_fx` and nothing else:
`Clone.imported` commits an `import` entry (one file, `lanes/LANES.md`, of one
line), which is what a clone of `tmpl_imported` held, and `Clone.to_primary`
goes on with a `cutover` entry over that import, then `record_marker`:

  * database R, between a re-import's bootstrap and its cutover: the clone
    after `Clone.imported`, at `files` with the marker `absent`, whose
    generation is `g1`; `g0`, the lost database's, is a uuid of the test's
    own;
  * database S, a restore: the clone brought to `primary` with the marker
    `present` by `Clone.to_primary` (the import, a `cutover` entry over it,
    then `record_marker`: TP:4610–4615), standing in for a restored
    backup. W0 and W1 commit under its generation `g0`; then its restore-form
    cutover, an after-loss `cutover` entry whose label is not the switch's,
    sets a new generation `g1`, and `record_marker` confirms it; then W2
    commits under `g1`;
  * AT-LR011's: S's route to `primary`, with write W committed (lane L1,
    verb V, `args_sha256` a).

Every call logs in as the fixture's writer login, `lanes_w_fx` (T228), in
the commit call's own form, `psql -X -q -A -t -v ON_ERROR_STOP=1 -v
VERBOSITY=verbose -v SHOW_CONTEXT=never` with the script on stdin, so a
refusal's first stderr line is `ERROR:  <SQLSTATE>: <message>` and its second
the `DETAIL:` token. A lookup runs at READ COMMITTED in a transaction the test
rolls back, with D9's bounds set in it (`lock_timeout=2000ms`,
`statement_timeout=6000ms`). A holder of the head row is a superuser session
fed on stdin, and every barrier is a state polled in `pg_stat_activity`, by
the session's `application_name`. No elapsed time is asserted: the one time
read, `clock_timestamp()` not before `p_not_after`, is a bound on the
server's own clock.

Each refused call writes nothing: the head, the journal and the switch equal
their values before.

Every case FAILS UNTIL lane 1's T107 (L1-A6: `commit_write` and
`find_write`) and T114 (L1-A12) land, with lane 2's T227 (`tmpl` holding the
register) and T228 (`lanes_w_fx`). A clone of `tmpl` with no register is
refused by the fixture's own assertion. Without PostgreSQL 16 each skips.

THE MODULE ALSO HOLDS, each at its own section below: T244's test 12 (AT-12)
and section 4.3's rival, and T245's D8 and AT-F34 (phase W, the client's
writers on a real register, through the shim), with T245's texts for 3, which
read the scripts and run with no engine.

PHASE W'S WORKSTATION IS T243's: `Estate`, its `estates` fixture, and the
logging tools of T248 are imported from `test_sql_register_order`, as
`test_handoff_skill_80_85` imports its sibling's `Sandbox`, so one
workstation serves both modules and neither keeps a copy.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import re
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from pgcluster import SUPERUSER, TEMPLATE, Database
from test_sql_register_order import (CLIENT, EM, LA, LB, LC, OBJ, UUID_RE, Barrier, Estate, Writer,  # noqa: F401
                                     claim, estates, hold_point, kind_line, loggers, session_of,
                                     tool_calls)

REGISTER = "lanes_register"
WRITER_LOGIN = "lanes_w_fx"
CONNECT_TO = "lanes_register_writer, lanes_register_reader, lanes_indexer"
LANES_MD, STORE = "lanes/LANES.md", "lanes/STORE"
WS, AUTHOR = "ws-t222", "T222 Fixture <t222@example.invalid>"
OPERATOR = "operator-t222"
MARKER_COMMIT = "c0ffee" + "1" * 34
IMPORT_COMMIT, IMPORT_TREE = "c" * 40, "d" * 40
IMPORT_LINES = ["# Lanes"]
RESTORED_LABEL = "restored-t222"
L1, L2, VERB, OTHER_VERB = "L1-t222", "L2-t222", "append-line", "lane-end"

COMMIT_SQL = ("BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
              "{set}"
              f"SELECT {REGISTER}.commit_write(:base, :'wid'::uuid, :client, :'gen'::uuid, :'entry'::jsonb);\n"
              "COMMIT;\n")
MARKER_SQL = f"SELECT {REGISTER}.record_marker(:client, :seq, :'commit', :'ws');\n"

#: F3's lookup: READ COMMITTED, D9's bounds, the call, the clock read next in
#: the same transaction, and the rollback.
LOOKUP_SQL = ("BEGIN ISOLATION LEVEL READ COMMITTED;\n"
              "SET LOCAL lock_timeout = '2000ms';\n"
              "SET LOCAL statement_timeout = '6000ms';\n"
              f"SELECT coalesce({REGISTER}.find_write(:'wid'::uuid, :'not_after'::timestamptz, :'gen'::uuid, "
              ":'lane', :'verb', nullif(:'args', ''))::text, 'NULL');\n"
              "SELECT clock_timestamp() >= :'not_after'::timestamptz;\n"
              "ROLLBACK;\n")

#: What a refused call must leave as it was: the head, the journal, the switch.
STATE_SQL = f"""
SELECT md5(concat_ws('|',
  (SELECT seq::text FROM {REGISTER}.register_head),
  (SELECT string_agg(j::text, ',' ORDER BY j.seq) FROM {REGISTER}.journal j),
  (SELECT string_agg(s::text, ',') FROM {REGISTER}.register_switch s)));
"""

HOLD_HEAD = f"BEGIN;\nSELECT 1 FROM {REGISTER}.register_head WHERE id = 1 FOR UPDATE;\n"

_NAMES = itertools.count(1)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rendered(lines: Sequence[str], final_newline: bool) -> bytes:
    """`render_file`'s bytes: the lines joined by LF, and a last LF where
    the file ends with one and holds a line."""
    return ("\n".join(lines) + ("\n" if final_newline and lines else "")).encode("utf-8")


class Clone:
    """One clone of `tmpl`, and the documented functions called on it as
    REGISTER-WRITER, through `lanes_w_fx` (AT-LR006's fixture)."""

    def __init__(self, cluster, name: str) -> None:
        self.cluster, self.name = cluster, name
        self.db = Database(cluster, name)
        self.made = 0

    # -------------------------------------------------- the superuser's reads
    def value(self, sql: str) -> str:
        return self.db.psql(sql).stdout.strip()

    def json(self, sql: str):
        return json.loads(self.value(sql))

    def switch(self) -> dict:
        return self.json(f"SELECT row_to_json(s) FROM {REGISTER}.register_switch s;")

    def head(self) -> int:
        return int(self.value(f"SELECT seq FROM {REGISTER}.register_head;"))

    def client(self) -> int:
        return int(self.value(f"SELECT version FROM {REGISTER}.schema_version;"))

    def state(self) -> str:
        return self.value(STATE_SQL)

    def clock(self, seconds: float = 0) -> str:
        """The database's clock, plus `seconds`."""
        return self.value(f"SELECT (clock_timestamp() + make_interval(secs => {seconds}))::text;")

    def file(self, path: str) -> Tuple[Optional[bool], List[str]]:
        said = self.json(
            f"SELECT json_build_object('nl', (SELECT final_newline FROM {REGISTER}.files WHERE path = '{path}'), "
            f"'lines', (SELECT coalesce(jsonb_agg(text ORDER BY line_no), '[]') FROM {REGISTER}.doc_lines "
            f"WHERE path = '{path}'));")
        return said["nl"], said["lines"]

    def activity(self, appname: str) -> List[List[str]]:
        """Each backend of `appname`: pid, wait_event_type, wait_event."""
        out = self.value(
            "SELECT coalesce(json_agg(json_build_array(pid, wait_event_type, wait_event)), '[]') "
            f"FROM pg_stat_activity WHERE application_name = '{appname}' AND state = 'active';")
        return json.loads(out)

    def head_locks(self, pid: int) -> int:
        """The locks `pid` holds or waits for on the head row's table, its
        tuples, or a transaction id."""
        return int(self.value(
            f"SELECT count(*) FROM pg_locks WHERE pid = {pid} AND (relation = '{REGISTER}.register_head'::regclass "
            "OR locktype IN ('tuple', 'transactionid'));"))

    # -------------------------------------------------- the calls, as the writer
    def argv(self, variables: Dict[str, object]) -> List[str]:
        argv = [self.db.psql_bin, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                "-v", "VERBOSITY=verbose", "-v", "SHOW_CONTEXT=never"]
        for name, value in variables.items():
            argv += ["-v", f"{name}={value}"]
        return argv

    def call(self, sql: str, appname: str = "t222", **variables) -> subprocess.CompletedProcess:
        return subprocess.run(self.argv(variables), input=sql, capture_output=True, text=True, timeout=60,
                              env=self.db.env(WRITER_LOGIN, appname), check=False)

    def start(self, sql: str, appname: str, user: str = WRITER_LOGIN, **variables) -> subprocess.Popen:
        """The same call, in the background: its script sent and its stdin closed."""
        proc = subprocess.Popen(self.argv(variables), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=self.db.env(user, appname))
        proc.stdin.write(sql)
        proc.stdin.close()
        return proc

    def commit_variables(self, entry: dict, base: Optional[int], write_id: str,
                         generation: Optional[str]) -> Dict[str, object]:
        return {"base": self.head() if base is None else base, "wid": write_id, "client": self.client(),
                "gen": generation or self.switch()["generation"],
                "entry": json.dumps(entry, ensure_ascii=False)}

    def commit(self, entry: dict, *, base: Optional[int] = None, write_id: Optional[str] = None,
               generation: Optional[str] = None) -> Tuple[subprocess.CompletedProcess, str]:
        write_id = write_id or str(uuid.uuid4())
        proc = self.call(COMMIT_SQL.format(set=""), **self.commit_variables(entry, base, write_id, generation))
        return proc, write_id

    def committed(self, entry: dict, **options) -> Tuple[int, str]:
        proc, write_id = self.commit(entry, **options)
        assert proc.returncode == 0, (
            f"commit_write as {WRITER_LOGIN} exited {proc.returncode}: {proc.stderr.strip()[-800:]}")
        return int(proc.stdout.strip()), write_id

    def lookup(self, write_id: str, not_after: str, *, generation: Optional[str] = None, lane: str = L1,
               verb: str = VERB, args: str = "") -> subprocess.CompletedProcess:
        return self.call(LOOKUP_SQL, appname="t222-lookup", **self.lookup_variables(
            write_id, not_after, generation, lane, verb, args))

    def lookup_variables(self, write_id, not_after, generation, lane, verb, args) -> Dict[str, object]:
        return {"wid": write_id, "not_after": not_after,
                "gen": generation or self.switch()["generation"], "lane": lane, "verb": verb, "args": args}

    # -------------------------------------------------- entries
    def journal(self, kind: str, verb: str, lane: str, **extra) -> dict:
        row = {"kind": kind, "verb": verb, "lane": lane, "workstation": WS, "author": AUTHOR,
               "message": f"{verb} by {lane} (T222)"}
        row.update(extra)
        return row

    def appended(self, path: str, texts: Sequence[str]) -> Tuple[list, list]:
        final_newline, lines = self.file(path)
        edits = []
        if final_newline is None:
            edits.append({"ord": 1, "op": "create", "path": path})
            final_newline = True
        for text in texts:
            edits.append({"ord": len(edits) + 1, "op": "append", "path": path, "new_text": text})
        return edits, [{"path": path, "present": True, "final_newline": final_newline,
                        "sha256": sha256(rendered([*lines, *texts], final_newline))}]

    def write_entry(self, lane: str = L1, verb: str = VERB, *, seconds: float = 60) -> dict:
        """A write: one line of no kind appended to `lanes/LANES.md`."""
        self.made += 1
        text = f"t222 note {self.made} — lane {lane}"
        edits, files = self.appended(LANES_MD, [text])
        args = sha256(f"{lane}\0{verb}\0{text}".encode("utf-8"))
        return {"journal": self.journal("write", verb, lane, args_sha256=args),
                "not_after": self.clock(seconds), "edits": edits, "files": files}

    def operator_entry(self, **switch) -> dict:
        edits, files = self.appended(STORE, ["primary"])
        entry = {"journal": self.journal("cutover", "cutover", OPERATOR), "not_after": self.clock(60),
                 "edits": edits, "files": files}
        if switch:
            entry["switch"] = switch
        return entry

    def mark(self, seq: int) -> None:
        marked = self.call(MARKER_SQL, client=self.client(), seq=seq, commit=MARKER_COMMIT, ws=WS)
        assert (marked.returncode, marked.stdout.strip()) == (0, "present"), marked.stderr
        sw = self.switch()
        assert (sw["mode"], sw["marker_state"]) == ("primary", "present"), sw

    def imported(self) -> int:
        """AT-LR006's route, its first step (TP:4610-4615): an `import` entry
        on the clone of `tmpl`, at `files` with the marker `absent` and an
        empty journal, as T221's `bring_to_primary` starts. It creates
        `lanes/LANES.md` with `IMPORT_LINES`, so the clone holds what a clone
        of `tmpl_imported` did, and the switch stays as it was."""
        sw = self.switch()
        assert (sw["mode"], sw["marker_state"], self.head()) == ("files", "absent", -1), (
            f"a clone of {TEMPLATE} is not at files, marker absent, with an empty journal: {sw}, head {self.head()}")
        edits, files = self.appended(LANES_MD, IMPORT_LINES)
        entry = {"journal": self.journal("import", "import", OPERATOR, git_commit=IMPORT_COMMIT,
                                         git_tree=IMPORT_TREE),
                 "not_after": self.clock(60), "edits": edits, "files": files}
        seq, _ = self.committed(entry)
        sw = self.switch()
        assert (sw["mode"], sw["marker_state"]) == ("files", "absent"), sw
        return seq

    def to_primary(self) -> int:
        """AT-LR006's route (TP:4610-4615): `imported`, then a `cutover`
        entry over that import, then `record_marker`."""
        self.imported()
        head = self.head()
        last_import = int(self.value(f"SELECT coalesce(max(seq), -2) FROM {REGISTER}.journal WHERE kind = 'import';"))
        assert last_import == head >= 0, f"the clone's head {head} is not its import ({last_import})"
        seq, _ = self.committed(self.operator_entry())
        self.mark(seq)
        return seq

    def refused(self, entry: dict, code: str, detail: Optional[str], *says: str, **options) -> List[str]:
        """The call ends with `code` and `detail`, and writes nothing."""
        before = self.state()
        proc, _ = self.commit(entry, **options)
        return self.check_refused(proc, before, code, detail, *says)

    def check_refused(self, proc, before: Optional[str], code: str, detail: Optional[str], *says: str) -> List[str]:
        lines = proc.stderr.splitlines()
        assert proc.returncode == 3, f"exit {proc.returncode}, not 3: {proc.stderr.strip()}"
        assert lines and lines[0].startswith(f"ERROR:  {code}: "), lines
        if detail is not None:
            assert lines[1:2] == [f"DETAIL:  {detail}"], lines
        for text in says:
            assert text in lines[0], f"{text!r} is not in {lines[0]!r}"
        if before is not None:
            assert self.state() == before, "the refused call changed the head, the journal or the switch"
        return lines


@pytest.fixture()
def clones(pg_cluster):
    """Clones of `tmpl`, each the test's own, dropped at the end."""
    made: List[str] = []

    def clone() -> Clone:
        name = f"t222_{next(_NAMES)}"
        pg_cluster.psql(f"CREATE DATABASE {name} TEMPLATE {TEMPLATE};")
        made.append(name)
        found = pg_cluster.psql(f"SELECT to_regclass('{REGISTER}.register_head') IS NOT NULL;", dbname=name)
        assert found.stdout.strip() == "t", (
            f"{TEMPLATE} holds no {REGISTER} schema: lane 2's T227 builds it by the bootstrap, "
            "which waits for lane 1's L1-A7")
        pg_cluster.psql(f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
                        f"GRANT CONNECT ON DATABASE {name} TO {CONNECT_TO};\n")
        return Clone(pg_cluster, name)

    yield clone
    for name in made:
        pg_cluster.drop_database(name)


@pytest.fixture()
def holders(pg_cluster):
    """Superuser sessions fed on stdin, each ended at the test's end."""
    started: List[subprocess.Popen] = []

    def hold(c: Clone, appname: str = "t222-holder") -> subprocess.Popen:
        proc = c.db.session(SUPERUSER, appname)
        proc.stdin.write(HOLD_HEAD)
        proc.stdin.flush()
        started.append(proc)
        until(c, lambda: c.value(f"SELECT count(*) FROM pg_stat_activity WHERE application_name = '{appname}' "
                                 "AND state = 'idle in transaction';") == "1", "the holder took the head row")
        return proc

    yield hold
    for proc in started:
        end(proc)


def end(proc: subprocess.Popen) -> None:
    """Roll the holder back and let it exit."""
    if proc.poll() is None:
        try:
            proc.stdin.write("ROLLBACK;\n")
            proc.stdin.close()
        except (BrokenPipeError, ValueError):
            pass
        try:
            proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()


def until(c: Clone, ready, what: str, deadline: float = 20.0):
    """Poll `ready` until it answers truly, or fail naming `what`."""
    end_at = time.monotonic() + deadline
    while True:
        said = ready()
        if said:
            return said
        assert time.monotonic() < end_at, f"not seen within {deadline:.0f} s: {what}"
        time.sleep(0.05)


def restored(clones) -> Tuple[Clone, Dict[str, dict]]:
    """Database S: W0 and W1 under `g0`, the restore-form cutover to `g1`,
    confirmed, then W2 under `g1`. Returns each write's id, entry and seq."""
    c = clones()
    c.to_primary()
    writes: Dict[str, dict] = {}
    for name in ("W0", "W1"):
        entry = c.write_entry()
        seq, write_id = c.committed(entry)
        writes[name] = {"id": write_id, "entry": entry, "seq": seq, "gen": c.switch()["generation"]}
    g0 = writes["W0"]["gen"]
    assert c.switch()["database_label"] != RESTORED_LABEL
    seq, _ = c.committed(c.operator_entry(after_loss=True, database_label=RESTORED_LABEL))
    sw = c.switch()
    assert (sw["mode"], sw["marker_state"], sw["database_label"]) == ("primary", "adding", RESTORED_LABEL), sw
    assert sw["generation"] != g0
    c.mark(seq)
    entry = c.write_entry()
    seq, write_id = c.committed(entry)
    writes["W2"] = {"id": write_id, "entry": entry, "seq": seq, "gen": c.switch()["generation"]}
    return c, writes


def at_lr011(clones) -> Tuple[Clone, dict]:
    """A clone on `primary` with write W committed: lane L1, verb V, args a."""
    c = clones()
    c.to_primary()
    entry = c.write_entry()
    seq, write_id = c.committed(entry)
    return c, {"id": write_id, "seq": seq, "args": entry["journal"]["args_sha256"],
               "gen": c.switch()["generation"]}


# ------------------------------------------------------------ AT-LR007
@pytest.mark.parametrize("base", ["current-base", "stale-base"])
def test_a_write_of_another_generation_at_files_gets_lr007_not_lr002_or_lr001(clones, base):
    """In R, at `files`: a write of `g0` is LR007 `generation`, not LR002,
    with the base current, and not LR001 with it stale."""
    c = clones()
    c.imported()
    head = c.head()
    g0 = str(uuid.uuid4())
    c.refused(c.write_entry(), "LR007", "generation", f"belongs to register generation {g0}",
              generation=g0, base=head if base == "current-base" else head - 1)


def test_the_switchs_own_generation_at_files_still_gets_lr002(clones):
    """In R, a write of `g1`, the switch's own, with the base current: LR002."""
    c = clones()
    c.imported()
    c.refused(c.write_entry(), "LR002", None, "register switch is files with the marker absent")


@pytest.mark.parametrize("base", ["current-base", "stale-base"])
def test_an_old_generation_id_after_a_restore_form_cutover_gets_lr007_not_lr006(clones, base):
    """In S, after the restore form's cutover, W0's id with `g0`, found in
    the restored journal: LR007 `generation`, not LR006."""
    c, writes = restored(clones)
    w0 = writes["W0"]
    head = c.head()
    c.refused(w0["entry"], "LR007", "generation", f"write {w0['id']} belongs to register generation {w0['gen']}",
              write_id=w0["id"], generation=w0["gen"], base=head if base == "current-base" else head - 1)


@pytest.mark.parametrize("base", ["current-base", "stale-base"])
def test_a_same_generation_id_after_a_restore_form_cutover_gets_lr006(clones, base):
    """In S, W2's id with `g1` and W2's own lane, verb and `args_sha256`:
    LR006, naming its seq."""
    c, writes = restored(clones)
    w2 = writes["W2"]
    head = c.head()
    c.refused(w2["entry"], "LR006", None, f"write {w2['id']} is in the journal at seq {w2['seq']}",
              write_id=w2["id"], generation=w2["gen"], base=head if base == "current-base" else head - 1)


def test_an_id_in_the_journal_for_another_lane_gets_lr007(clones):
    """In S, W2's id with `g1` and another lane: LR007 `another-write`."""
    c, writes = restored(clones)
    w2 = writes["W2"]
    other = json.loads(json.dumps(w2["entry"]))
    other["journal"]["lane"] = L2
    c.refused(other, "LR007", "another-write", f"write {w2['id']} is seq {w2['seq']}, another write's (F10)",
              write_id=w2["id"], generation=w2["gen"])


# ------------------------------------------------------------ AT-LR011
@pytest.mark.parametrize("case", ["found", "absent"])
def test_find_write_returns_this_writes_seq_or_null(clones, case):
    """With `p_not_after` passed, W's id with its own generation, lane, verb
    and `args_sha256` returns W's seq; an id not in the journal, NULL."""
    c, w = at_lr011(clones)
    write_id = w["id"] if case == "found" else str(uuid.uuid4())
    proc = c.lookup(write_id, c.clock(-1), args=w["args"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == [str(w["seq"]) if case == "found" else "NULL", "t"]


@pytest.mark.parametrize("case", ["lane", "verb", "args", "null-args"])
def test_find_write_refuses_another_writes_entry_lr007(clones, case):
    """W's id with another lane, another verb, another `args_sha256`, or a
    NULL one, which never matches a write's entry: LR007 `another-write`."""
    c, w = at_lr011(clones)
    options = {"lane": L1, "verb": VERB, "args": w["args"]}
    options.update({"lane": {"lane": L2}, "verb": {"verb": OTHER_VERB},
                    "args": {"args": sha256(b"another write")}, "null-args": {"args": ""}}[case])
    proc = c.lookup(w["id"], c.clock(-1), **options)
    c.check_refused(proc, None, "LR007", "another-write", f"write {w['id']} is seq {w['seq']}")


@pytest.mark.parametrize("case", ["found", "absent"])
def test_find_write_refuses_another_generation_lr007(clones, case):
    """W's id, and an id not in the journal, each with a generation not the
    switch's: LR007 `generation`."""
    c, w = at_lr011(clones)
    write_id = w["id"] if case == "found" else str(uuid.uuid4())
    other = str(uuid.uuid4())
    proc = c.lookup(write_id, c.clock(-1), generation=other, args=w["args"])
    c.check_refused(proc, None, "LR007", "generation", f"belongs to register generation {other}")


def test_find_write_gives_lr011_before_lr007(clones):
    """With `p_not_after` 4 s ahead and a generation not the switch's: LR011."""
    c, w = at_lr011(clones)
    proc = c.lookup(w["id"], c.clock(4), generation=str(uuid.uuid4()), args=w["args"])
    c.check_refused(proc, None, "LR011", None, "past the 3 s wait")


def test_find_write_waits_on_the_server_clock_holding_no_lock(clones, holders):
    """With `p_not_after` 2 s ahead and the head row held, the lookup's
    backend is seen first in `PgSleep`, holding no lock, then waiting on a
    `Lock`; once the holder ends it returns W's seq, and the clock read next
    is not before `p_not_after`."""
    c, w = at_lr011(clones)
    holder = holders(c)
    not_after = c.clock(2)
    proc = c.start(LOOKUP_SQL, "t222-lookup", **c.lookup_variables(w["id"], not_after, None, L1, VERB, w["args"]))
    try:
        pid = until(c, lambda: [a[0] for a in c.activity("t222-lookup") if a[2] == "PgSleep"],
                    "the lookup sleeping in PgSleep")[0]
        assert c.head_locks(pid) == 0, "the lookup holds a lock while it sleeps"
        until(c, lambda: [a for a in c.activity("t222-lookup") if a[1] == "Lock"], "the lookup waiting on a Lock")
    finally:
        end(holder)
        out, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, err
    assert out.split() == [str(w["seq"]), "t"]


def test_a_lookup_held_at_the_head_row_ends_55p03_inside_its_statement_timeout(clones, holders):
    """With `p_not_after` 2.9 s ahead and the head row held throughout, the
    lookup ends with 55P03 from its `lock_timeout`, not 57014: its wait and
    its lock fit its `statement_timeout`."""
    c, w = at_lr011(clones)
    holder = holders(c)
    try:
        proc = c.lookup(w["id"], c.clock(2.9), args=w["args"])
    finally:
        end(holder)
    c.check_refused(proc, None, "55P03", None)


def test_an_orphan_that_takes_the_lock_past_its_not_after_gets_lr008_and_the_lookup_finds_it_absent(clones, holders):
    """Commit call O of write X, `not_after` 2 s ahead, waits on the head row
    behind a holder, under `SET LOCAL lock_timeout = '5s'`; the lookup for X
    waits past `not_after`, then queues. The holder rolls back once the
    clock is past `not_after` and both wait on a `Lock`. Whichever takes the
    lock first, O ends LR008, the lookup returns NULL, and no journal row
    holds X's id."""
    c, w = at_lr011(clones)
    holder = holders(c)
    entry = c.write_entry(seconds=2)
    write_id = str(uuid.uuid4())
    variables = c.commit_variables(entry, None, write_id, None)
    orphan = c.start(COMMIT_SQL.format(set="SET LOCAL lock_timeout = '5s';\n"), "t222-orphan", **variables)
    lookup = c.start(LOOKUP_SQL, "t222-lookup", **c.lookup_variables(
        write_id, entry["not_after"], variables["gen"], L1, VERB, entry["journal"]["args_sha256"]))
    try:
        until(c, lambda: c.value(f"SELECT clock_timestamp() > '{entry['not_after']}'::timestamptz;") == "t"
              and any(a[1] == "Lock" for a in c.activity("t222-orphan"))
              and any(a[1] == "Lock" for a in c.activity("t222-lookup")),
              "the clock past not_after, with the orphan and the lookup each waiting on a Lock")
    finally:
        end(holder)
        orphan_out, orphan_err = orphan.communicate(timeout=30)
        lookup_out, lookup_err = lookup.communicate(timeout=30)
    c.check_refused(subprocess.CompletedProcess(orphan.args, orphan.returncode, orphan_out, orphan_err),
                    None, "LR008", None, f"write {write_id} reached its end")
    assert lookup.returncode == 0, lookup_err
    assert lookup_out.split() == ["NULL", "t"]
    assert c.value(f"SELECT count(*) FROM {REGISTER}.journal WHERE write_id = '{write_id}';") == "0"


# ============================================================ PHASE W: AT-12 and section 4.3's rival (T244)
#
# A COMMIT IN DOUBT (AT-12, ADV-C3; TP:2245-2420), ON T243's WORKSTATION: a
# clone of `tmpl` brought to `primary` by AT-LR006's route, one configuration
# naming it through `lanes_w_fx`, and per writer a `psql` directory holding
# T203's shim, armed by its control file for the writer's FIRST commit call
# only. Commit calls are the requests carrying `commit_write`, lookup tries
# those carrying `find_write`, and the snapshots lane 1's one read-only
# request, `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY` (`lanes-index`'s
# `_query_many`). The oracle never matches on stderr where AT-12 says so: the
# shim's `FATAL` line is one a real loss does not print.
#
# The lookup's timer is D9's `T_L`, `N_a`·`c` + 7 s, 9 s at `c` = 2 (open
# point 37). YS:685 as amended (R-F10-2): where `request-handoff` already
# wrote, its refusal names what it wrote; which of `[tail-sent]`,
# `[tail-done]` and `[no-record]` follow a committed write is NOTES question
# 33, so each asserts the journal's one entry and no `send-keys`.
#
# They FAIL UNTIL lane 1's T107 (L1-A6) and T114 (L1-A12, `journal
# --write-id`), lane 4's attempt loop on primary (L4-B2), its in-doubt rule
# and pending record (L4-B5) and its tail, once (L4-B15) land, with lane 2's
# T227 and T228. Without PostgreSQL 16 each skips.

SNAPSHOT_TEXT = "REPEATABLE READ READ ONLY"
AFTER = {"mode": "after", "match": "commit_write", "call": 1}
BEFORE = {"mode": "before", "match": "commit_write", "call": 1}
#: D9's commit-call timer, `C`, and AT-12's figures from it (TP:2331-2357).
C_S, WINDOW_S, T_L_S = 8, 10, 9
#: The tries' spacing, with lane 2's tolerance (T246's bullet; NOTES question 34).
GAP_S, LATE_S = 0.75, 1.25
PENDING = Path("openRepoTools") / "register-pending"
WRITE_ID_SAID = re.compile(r"LANES_WRITE_ID=(" + UUID_RE + r")")
GENERATION_SAID = re.compile(r"LANES_WRITE_GENERATION=(" + UUID_RE + r")")
NOT_AFTER_SAID = re.compile(r'"not_after"\s*:\s*"([^"]+)"')
LAST_COMMIT = re.compile(r"\bCOMMIT\b[ \t]*;?(?![\s\S]*\bCOMMIT\b)", re.I)


def note(lane: str, tag: str) -> List[str]:
    """A plain write: one `NOTE` line, by `append-line`."""
    return ["append-line", f"NOTE {EM} lane {lane}: {tag} (T244)"]


def one_entry(e: Estate, w: Writer, grew: int = 1) -> str:
    """AT-12's oracle: every commit call of `w` carried one write id, the
    journal grew by exactly `grew`, and that id appears once."""
    ids = w.write_ids()
    assert ids and len(set(ids)) == 1, f"{w.name}'s commit calls carried {ids}, not one write id"
    rows = e.journal_after()
    assert len(rows) == grew, f"the journal grew by {len(rows)}, not {grew}: {rows}"
    assert [r["write_id"] for r in rows].count(ids[0]) == 1, (ids[0], rows)
    return ids[0]


def lookups(w: Writer) -> List[dict]:
    return [c for c in w.stamps() if "find_write" in (c.get("stdin") or "")]


def pending(e: Estate) -> List[Path]:
    """The pending records, `<state>/openRepoTools/register-pending/<d>`."""
    where = e.state / PENDING
    return sorted(p for p in where.iterdir() if re.fullmatch(r"[0-9a-f]{64}", p.name)) if where.is_dir() else []


def until_seen(what: str, ready, w: Optional[Writer] = None, deadline: float = 90.0):
    end_at = time.monotonic() + deadline
    while True:
        said = ready()
        if said:
            return said
        if w is not None:
            assert w.ended is None, f"{w.name} exited {w.code} before {what}: {w.err[-400:]}"
        assert time.monotonic() < end_at, f"not seen within {deadline:.0f} s: {what}"
        time.sleep(0.05)


def fifo(e: Estate, name: str) -> Path:
    path = e.root / f"{name}.fifo"
    os.mkfifo(str(path))
    return path


def first_not_after(w: Writer) -> str:
    m = NOT_AFTER_SAID.search(w.commit_calls()[0].get("stdin") or "")
    assert m, "the first commit call's entry carries no not_after"
    return m.group(1)


def db_past(e: Estate, utc: str) -> bool:
    return e.c.value(f"SELECT clock_timestamp() >= '{utc}'::timestamptz;") == "t"


# ------------------------------------------------------------ AT-12: after, before, timer
@CLIENT
def test_a_commit_that_landed_before_the_connection_was_lost_ends_with_one_entry_and_exit_0(estates):
    """`after`: the first COMMIT lands, then its backend is terminated. One
    entry, its write id once, exit 0."""
    e = estates()
    w = e.run(LA, note(LA, "after"), arms=[AFTER])
    assert w.code == 0, w.err[-800:]
    one_entry(e, w)


@CLIENT
def test_a_commit_lost_before_it_landed_is_retried_cleanly_and_ends_with_one_entry(estates):
    """`before`: the first COMMIT never lands. The writer retries cleanly,
    under the same write id, and exits 0 with one entry."""
    e = estates()
    w = e.run(LA, note(LA, "before"), arms=[BEFORE])
    assert w.code == 0, w.err[-800:]
    assert len(w.commit_calls()) >= 2, "the lost commit was not retried"
    one_entry(e, w)


@CLIENT
def test_an_outer_timer_expiry_is_in_doubt_like_exit_2(estates):
    """`timer`: the real `psql` commits, then the shim sleeps past the
    commit call's 8 s client timer (D9), whose expiry is in doubt as an exit
    2 is. One entry, exit 0; the time is recorded, not asserted."""
    e = estates()
    started = time.monotonic()
    w = e.run(LA, note(LA, "timer"), arms=[{"mode": "timer", "match": "commit_write", "call": 1,
                                                 "ms": 3 * C_S * 1000}])
    assert w.code == 0, w.err[-800:]
    one_entry(e, w)
    print(f"[T244 timer] took={time.monotonic() - started:.1f}s against C={C_S}s")


# ------------------------------------------------------------ AT-12: the half-open case
@CLIENT
@pytest.mark.parametrize("ending", ["rollback", "commit", "idle"])
def test_a_retry_with_the_old_connection_still_open_writes_no_second_row(estates, ending):
    """`before` loses the first commit call; the old connection, still open,
    is the test's session as `lanes_w_fx`, replaying that call's script
    without its COMMIT, so it holds the head row with the row inserted. The
    shim's `hold` keeps the next snapshot until the replay has returned.
    While the session is open no second row exists; [rollback]: the retry
    inserts once; [commit]: the waiting retry gets 40001, the next snapshot
    finds the id, and no commit call starts after the session's COMMIT;
    [idle]: the role's 5 s idle bound ends the session, and the writer
    commits once. One row, exit 0, in each."""
    e = estates()
    gate = fifo(e, "snapshot-2")
    w = e.launch(LA, note(LA, f"half-open {ending}"),
                 arms=[BEFORE, {"mode": "hold", "match": SNAPSHOT_TEXT, "call": 2, "fifo": str(gate)}])
    first = until_seen("the first commit call", lambda: w.commit_calls()[:1], w)[0]
    script = LAST_COMMIT.sub("", first["stdin"], count=1)
    assert "commit_write" in script and script != first["stdin"], "the first commit call has no COMMIT to drop"
    session = e.c.db.session(WRITER_LOGIN, "t244-half-open")
    try:
        if ending != "idle":
            session.stdin.write("SET idle_in_transaction_session_timeout = 0;\n")
        session.stdin.write(script.rstrip() + "\n")
        session.stdin.flush()
        until_seen("the replay holding the head row", lambda: e.c.value(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name = 't244-half-open' "
            "AND state = 'idle in transaction';") == "1", w)
        write_id = w.write_ids()[0]
        hold_point(gate, w).close()
        if ending != "idle":
            until_seen("a retry's commit call", lambda: len(w.commit_calls()) >= 2, w)
            assert not e.has_write(write_id), "a second row exists while the old transaction is open"
            closed = time.time()
            session.stdin.write("ROLLBACK;\n" if ending == "rollback" else "COMMIT;\n")
            session.stdin.flush()
        session.stdin.close()
        assert w.wait() == 0, w.err[-800:]
    finally:
        if session.poll() is None:
            session.kill()
        session.communicate()
    assert one_entry(e, w) == write_id
    if ending == "commit":
        late = [c for c in w.stamps() if "commit_write" in (c.get("stdin") or "") and c["t"] > closed]
        assert not late, f"a commit call started after the old transaction committed: {late}"


# ------------------------------------------------------------ AT-12: no-reconnect, and the rerun
@CLIENT
@pytest.mark.parametrize("rerun", ["write-id", "plain"])
def test_a_callers_rerun_after_a_failed_reconnect_reuses_the_write_id(estates, rerun):
    """`no-reconnect`: the first commit call is lost, and every later call
    exits 2. The writer waits about 8 s, makes at least two lookup tries in
    the 10 s window, each at least 1 s after the last (with lane 2's 0.75 s
    tolerance) and none past 20 s from the first, and exits 3 no earlier than
    about 17 s after its snapshot and under 54 s. Its report names the id and
    the rerun, read from it. [write-id]: the rerun under `LANES_WRITE_ID`
    and `LANES_WRITE_GENERATION`; [plain]: the same command line, which finds
    the pending record. Either exits 0, never mints a new id, never 69, and
    the journal holds one row for the id."""
    e = estates()
    argv = claim(OBJ, "--no-github")
    w = e.run(LA, argv, arms=[{"mode": "no-reconnect", "as": "before", "match": "commit_write", "call": 1}])
    assert w.code == 3, f"exit {w.code}, not 3: {w.err[-800:]}"
    snap = w.stamps()[0]["t"]
    tries = lookups(w)
    assert len(tries) >= 2, f"{len(tries)} lookup tries"
    assert tries[0]["t"] - snap >= C_S - 1, "a lookup try started before the client's wait ended"
    for k, (last, this) in enumerate(zip(tries, tries[1:]), 2):
        assert this["t"] - last["t"] >= GAP_S, f"try {k} started {this['t'] - last['t']:.2f} s after the last"
    assert tries[-1]["t"] - tries[0]["t"] <= 2 * WINDOW_S, "a try started past twice the window"
    took = time.time() - (time.monotonic() - w.ended) - snap
    assert 17 <= took < 2 * (C_S + WINDOW_S + T_L_S), f"exit 3 after {took:.1f} s"
    print(f"[T244 no-reconnect] exit3={took:.1f}s against {C_S + WINDOW_S + T_L_S}s, "
          f"spread={tries[-1]['t'] - tries[0]['t']:.1f}s against {WINDOW_S}s")
    ids, gens = WRITE_ID_SAID.findall(w.err), GENERATION_SAID.findall(w.err)
    assert ids and gens, f"the report names no LANES_WRITE_ID rerun: {w.err[-800:]}"
    write_id = ids[-1]
    assert write_id == w.write_ids()[0]
    assert f"lanes-index journal --write-id {write_id}" in w.err
    extra = {"LANES_WRITE_ID": write_id, "LANES_WRITE_GENERATION": gens[-1]} if rerun == "write-id" else {}
    again = e.run(LA, argv, extra=extra)
    assert again.code == 0, f"the {rerun} rerun exited {again.code}: {again.err[-800:]}"
    assert set(again.write_ids()) <= {write_id}, f"the rerun minted a new id: {again.write_ids()}"
    assert [r["write_id"] for r in e.journal_after()].count(write_id) == 1
    assert e.claimed(OBJ) == [(OBJ, LA)] and e.log_lines("CLAIMED", OBJ) == 1


@CLIENT
@pytest.mark.parametrize("mode", ["after", "before", "timer"])
def test_an_in_doubt_claim_never_leaves_two_claimed_lines_or_a_false_69(estates, mode):
    """`claim` in doubt by `after`, `before` or `timer`: exit 0, never 69,
    one entry, and the object has exactly one `CLAIMED` line."""
    e = estates()
    arm = {"after": AFTER, "before": BEFORE,
           "timer": {"mode": "timer", "match": "commit_write", "call": 1, "ms": 3 * C_S * 1000}}[mode]
    w = e.run(LA, claim(OBJ, "--no-github"), arms=[arm])
    assert w.code == 0, f"exit {w.code}: {w.err[-800:]}"
    one_entry(e, w)
    assert e.claimed(OBJ) == [(OBJ, LA)]
    assert e.log_lines("CLAIMED", OBJ) == 1


# ------------------------------------------------------------ AT-12: a next attempt refused for another reason
@CLIENT
@pytest.mark.parametrize("reason,code", [("database", 69), ("register", 2), ("verb", 2)])
def test_an_in_doubt_write_whose_next_attempt_is_refused_makes_its_lookup_before_it_exits(estates, reason, code):
    """The first commit call is lost before it lands, so the write is in
    doubt with no row; the second attempt is refused. [database]: `claim`,
    whose second commit's entry breaks a CHECK (test 2's late failure),
    23514; [register]: a `HOLD` line, whose second snapshot is held while
    another lane commits a `HOLD` for the same repository, LR005; [verb]:
    `claim`, held the same way while another lane claims the object, refused
    by the verb's own pre-check. In each the writer makes a `find_write` call
    after the refused attempt, once the database's clock has passed the
    first call's `not_after`, and exits with the refusal's own code; the
    journal holds no row for its id, and the pending record is removed."""
    e = estates()
    gate = fifo(e, "snapshot-2")
    arms = [BEFORE]
    if reason == "database":
        arms.append({"mode": "edit-entry", "match": "commit_write", "call": 2, "field": "journal.kind",
                     "value": "t244-no-such-kind"})
        argv = claim(OBJ, "--no-github")
    else:
        arms.append({"mode": "hold", "match": SNAPSHOT_TEXT, "call": 2, "fifo": str(gate)})
        argv = (["append-line", kind_line(e, "HOLD", LA)] if reason == "register"
                else claim(OBJ, "--no-github"))
    w = e.launch(LA, argv, arms=arms)
    if reason != "database":
        held = hold_point(gate, w)
        rival = (["append-line", kind_line(e, "HOLD", LB)] if reason == "register"
                 else claim(OBJ, "--no-github"))
        assert e.run(LB, rival).code == 0
        held.close()
    assert w.wait() == code, f"exit {w.code}, not {code}: {w.err[-800:]}"
    write_id = w.write_ids()[0]
    stamps = w.stamps()
    attempts = [c for c in stamps if (SNAPSHOT_TEXT if reason == "verb" else "commit_write") in (c.get("stdin") or "")]
    assert len(attempts) >= 2, f"no second attempt: {len(attempts)}"
    assert [t for t in lookups(w) if t["t"] > attempts[1]["t"]], "no find_write call after the refused attempt"
    assert db_past(e, first_not_after(w)), "the writer exited before the first call's not_after"
    assert not e.has_write(write_id)
    assert pending(e) == [], f"the pending record was kept: {pending(e)}"


# ------------------------------------------------------------ AT-12: request-handoff runs none of its tail
@CLIENT
@pytest.mark.parametrize("state", ["tail-sent", "tail-done", "no-record"])
def test_a_request_handoff_that_runs_none_of_its_tail_exits_2_and_writes_nothing(estates, state):
    """GB §4.3's case (R29): `request-handoff`, with T248's fake `tmux` on
    `PATH`, is killed after its commit call returned, so the row has landed
    and its pending record holds a `call` line and no `tail` key. The rerun
    of the same command line, with the record at `tail=sent`, `tail=done`, or
    removed and rerun under `LANES_WRITE_ID`, finds its write id and exits 2,
    not 0; the journal holds one entry for the id (YS:685 as amended: the
    write committed, so the refusal names it), the fake `tmux` logs no
    `send-keys` from the rerun, and stderr names the tail it did not run."""
    e = estates()
    where = loggers(e)
    gate = fifo(e, "commit-1")
    argv = ["request-handoff", LC, "--session", session_of(LC)]
    w = e.launch(LA, argv, arms=[{"mode": "timer", "match": "commit_write", "call": 1, "fifo": str(gate)}],
                 first=[where])
    write_id = until_seen("the first commit call", lambda: w.commit_calls()[:1] and w.write_ids()[0], w)
    until_seen("the row landed", lambda: e.has_write(write_id), w)
    os.killpg(w.proc.pid, signal.SIGKILL)
    w.wait()
    records = pending(e)
    assert len(records) == 1, records
    text = records[0].read_text(encoding="utf-8")
    assert "\ncall=" in "\n" + text and "\ntail=" not in "\n" + text, text
    seq = e.journal_after()[-1]["seq"]
    extra = {}
    if state == "no-record":
        for path in records[0].parent.glob(records[0].name + "*"):
            path.unlink()
        extra = {"LANES_WRITE_ID": write_id}
    else:
        with records[0].open("a", encoding="utf-8") as record:
            record.write(f"tail=sent {seq} {e.utc()}\n" if state == "tail-sent"
                         else f"tail=done {seq} 0 {e.utc()}\n")
    before = len(tool_calls(where, "tmux"))
    again = e.run(LA, argv, extra=extra, first=[where])
    assert again.code == 2, f"the rerun exited {again.code}, not 2: {again.err[-800:]}"
    assert [r["write_id"] for r in e.journal_after()].count(write_id) == 1
    sent = [c for c in tool_calls(where, "tmux")[before:] if "send-keys" in c["argv"]]
    assert not sent, f"the rerun typed into a pane: {sent}"
    assert "tail" in again.err, f"stderr names no tail: {again.err[-800:]}"


# ------------------------------------------------------------ section 4.3: the rival
@CLIENT
def test_a_lookup_never_mistakes_a_rivals_row_for_the_lost_write(estates):
    """Section 4.3's rival: LA's first commit is lost before it lands, and
    LA's next call, its lookup try or its retry's snapshot, is held while LB
    commits the same line's text. A lookup by LA's id finds LA's write
    absent, never LB's row: LA retries under its own id and exits 0, and
    the journal holds each id once."""
    e = estates()
    gate = fifo(e, "call-3")
    argv = note(LA, "rival")
    w = e.launch(LA, argv, arms=[BEFORE, {"mode": "hold", "call": 3, "fifo": str(gate)}])
    held = hold_point(gate, w)
    rival = e.run(LB, argv)
    assert rival.code == 0, rival.err[-800:]
    held.close()
    assert w.wait() == 0, w.err[-800:]
    mine, theirs = w.write_ids()[0], rival.write_ids()[0]
    assert mine != theirs
    assert set(w.write_ids()) == {mine}, "the lost write's retry took another id"
    ids = [r["write_id"] for r in e.journal_after()]
    assert ids.count(mine) == 1 and ids.count(theirs) == 1, ids


# ============================================================ PHASE W: D8 and AT-F34 (T245)
#
# THE PENDING RECORD'S RERUN AND THE TAIL, ONCE (AT-D8, TP:3265-3528; AT-F34,
# TP:6941-7036), on T244's workstation and shim. The record is
# `<state>/openRepoTools/register-pending/<d>`, `key=value` lines with one
# `call=<base> <clock> <not_after> <files> <dir>` line per commit call that
# may have committed; its claim files are `<d>.take.<k>`; the done mark is
# `<state>/openRepoTools/register-done/<write_id>`. Every kill is sent on a
# FIFO signal, never after a sleep: the shim's `timer` joined to a FIFO
# blocks once the real `psql` has returned, and the test kills the run's
# process group there, so the row has landed and the writer cannot print.
#
# THE TAKEOVER (Q-L2-6; R26, lane 4's answer to 36): on this host a run that
# takes a killed run's record over waits past that call's `not_after`,
# whether its own snapshot passes or fails, on the record's clock when it
# has none of its own; `[snapshot-fails]` holds it. A record from another
# host keeps "calls at once" (T246's `[too-early]`).
#
# `found`'s two lines (R-F13-2, R-F13-7; F13b-OWED items 11 and 15): every
# `found` answer the shim and the fakes give here carries `workstation=` and
# `utc=` after its seq line, as lane 1's T114-fu3 prints them (`found <seq>`,
# `workstation=<name>`, `utc=<epoch s>`, then the `file=` rows), and AT-F34's
# no-record reruns choose Y:5347's text for this host or another by
# `workstation=`, naming the entry's UTC from `utc=`.
#
# They FAIL UNTIL L4-B2, L4-B5 and L4-B6 land; `[snapshot-fails]` until lane
# 4's T417 and lane 1's T114 take the record's clock (Q-L1-1); the texts for 3
# until lane 4's T417, T433 and T434; and the `found` lines until lane 1's
# T114 and lane 5's T111 print them. Without PostgreSQL 16 each skips, except
# the texts for 3, which read the scripts and run here.

DONE = Path("openRepoTools") / "register-done"
CALL_LINE = re.compile(r"^-?[0-9]+ \S+ \S+ [0-9a-f]{64} /\S+$")
NO_RECONNECT = {"mode": "no-reconnect", "as": "before", "match": "commit_write", "call": 1}
#: D8's text for 3 (R29; GB §4.3; W:459-460, W:5647-5649; R2's S5), byte for byte.
D8_TEXT_3 = "may not be written; run the printed `LANES_WRITE_ID` rerun, which writes it once or finds it"
_KILLS = itertools.count(1)


def killed(e: Estate, lane: str, argv: Sequence[str], **options) -> Tuple[Writer, str]:
    """AT-D8's killed write: the first commit call's real `psql` returns,
    the shim blocks on its FIFO, and the test kills the run's group there."""
    gate = fifo(e, f"killed-{next(_KILLS)}")
    arms = [*options.pop("arms", ()), {"mode": "timer", "match": "commit_write", "call": 1, "fifo": str(gate)}]
    w = e.launch(lane, argv, arms=arms, **options)
    held = hold_point(gate, w)
    os.killpg(w.proc.pid, signal.SIGKILL)
    held.close()
    w.wait()
    write_id = w.write_ids()[0]
    assert e.has_write(write_id), "the killed call's row has not landed"
    return w, write_id


def exit3(e: Estate, lane: str, argv: Sequence[str], **options) -> Tuple[Writer, str, str]:
    """A run ended 3 by `no-reconnect`: the writer, its id and generation,
    read from its report."""
    w = e.run(lane, argv, arms=[NO_RECONNECT], **options)
    assert w.code == 3, f"exit {w.code}, not 3: {w.err[-800:]}"
    ids, gens = WRITE_ID_SAID.findall(w.err), GENERATION_SAID.findall(w.err)
    assert ids and gens, f"the report names no LANES_WRITE_ID rerun: {w.err[-800:]}"
    return w, ids[-1], gens[-1]


def the_record(e: Estate) -> dict:
    """The one pending record: its path, its first value of each key, and
    its `call` lines."""
    records = pending(e)
    assert len(records) == 1, f"{len(records)} pending records"
    fields: Dict[str, str] = {}
    calls: List[str] = []
    for line in records[0].read_text(encoding="utf-8").splitlines():
        key, eq, value = line.partition("=")
        if eq and key == "call":
            calls.append(value)
        elif eq:
            fields.setdefault(key, value)
    return {"path": records[0], "fields": fields, "calls": calls}


def take_files(e: Estate) -> List[str]:
    where = e.state / PENDING
    return sorted(p.name for p in where.glob("*.take.*")) if where.is_dir() else []


def mark_of(e: Estate, write_id: str) -> Path:
    return e.state / DONE / write_id


def comments(where: Path) -> List[dict]:
    return [c for c in tool_calls(where, "gh") if "comment" in " ".join(c["argv"])]


def sidecars(e: Estate) -> Path:
    root = e.root / "lane-state"
    for lane in (LA, LB, LC):
        (root / lane).mkdir(parents=True, exist_ok=True)
        (root / lane / "lane-state.yaml").write_text(f"lane: {lane}\nstate: RUNNING\ngeneration: 1\n",
                                                     encoding="utf-8")
    return root


def generation_of(root: Path, lane: str) -> str:
    for line in (root / lane / "lane-state.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("generation:"):
            return line.split(":", 1)[1].strip()
    return ""


def tail_rerun(e: Estate, lane: str, argv: Sequence[str], where: Path, extra: Optional[dict] = None):
    """AT-D8's tail oracle around a killed write: no effect before the rerun;
    the rerun exits 0 with one row; the record wrote `tail=sent`, then
    `tail=done`, and is removed; the mark holds `done`; a second rerun under
    the id runs nothing. Returns the rerun and the id."""
    _, write_id = killed(e, lane, argv, first=[where], extra=extra)
    before = len(tool_calls(where))
    again = e.run(lane, argv, first=[where], extra=extra)
    assert again.code == 0, f"the rerun exited {again.code}: {again.err[-800:]}"
    assert [r["write_id"] for r in e.journal_after()].count(write_id) == 1
    assert pending(e) == [] and take_files(e) == []
    assert "done" in mark_of(e, write_id).read_text(encoding="utf-8")
    after = len(tool_calls(where))
    third = e.run(lane, argv, first=[where], extra=dict(extra or {}, LANES_WRITE_ID=write_id))
    assert third.code == 0 and len(tool_calls(where)) == after, "a second rerun ran the tail again"
    return again, write_id, before


# ------------------------------------------------------------ D8: the record
@CLIENT
def test_a_committed_write_leaves_no_pending_record(estates):
    """After a committed write no record and no claim file remains, and the
    done mark does: 0600 in a 0700 directory, holding the id, the seq and
    the `tail` value, `done`."""
    e = estates()
    w = e.run(LA, note(LA, "committed"))
    assert w.code == 0, w.err[-800:]
    write_id = one_entry(e, w)
    assert pending(e) == [] and take_files(e) == []
    mark = mark_of(e, write_id)
    assert mark.stat().st_mode & 0o777 == 0o600 and mark.parent.stat().st_mode & 0o777 == 0o700
    text = mark.read_text(encoding="utf-8")
    assert write_id in text and str(e.journal_after()[-1]["seq"]) in text and "done" in text, text


@CLIENT
def test_a_plain_rerun_reuses_the_pending_write_id_once_and_says_so(estates):
    """After exit 3 the record names the id and holds the call's `call` line
    (base, clock, `not_after`, the `files` digest, the attempt directory),
    and no other key says the write is in doubt. A plain rerun says on
    stderr that it reuses the id, exits 0, leaves one row and removes the
    record; a second plain rerun is a new write, under a new id."""
    e = estates()
    argv = note(LA, "plain rerun")
    _, write_id, _ = exit3(e, LA, argv)
    rec = the_record(e)
    assert rec["fields"].get("write_id", "").lower() == write_id
    assert len(rec["calls"]) == 1 and CALL_LINE.match(rec["calls"][0]), rec["calls"]
    again = e.run(LA, argv)
    assert again.code == 0, again.err[-800:]
    assert write_id in again.err and "reus" in again.err.lower(), again.err[-800:]
    assert [r["write_id"] for r in e.journal_after()].count(write_id) == 1
    assert pending(e) == []
    third = e.run(LA, argv)
    assert third.code == 0 and set(third.write_ids()) and write_id not in third.write_ids()


@CLIENT
def test_a_write_killed_by_an_outer_timer_is_retried_under_its_own_id(estates):
    """A write killed after its call returned prints nothing; its plain
    rerun reuses the id, exits 0, and leaves one row."""
    e = estates()
    argv = note(LA, "killed")
    _, write_id = killed(e, LA, argv)
    again = e.run(LA, argv)
    assert again.code == 0, again.err[-800:]
    assert set(again.write_ids()) <= {write_id}
    assert [r["write_id"] for r in e.journal_after()].count(write_id) == 1


@CLIENT
def test_a_rerun_with_other_arguments_does_not_take_the_pending_id(estates):
    """A rerun with other arguments is a write of its own: it never sends
    the pending id, and the record stays."""
    e = estates()
    _, write_id, _ = exit3(e, LA, note(LA, "first arguments"))
    other = e.run(LA, note(LA, "other arguments"))
    assert other.code == 0, other.err[-800:]
    assert write_id not in other.write_ids()
    assert the_record(e)["fields"].get("write_id", "").lower() == write_id


@CLIENT
def test_lanes_write_id_wins_over_a_pending_record(estates):
    """`LANES_WRITE_ID`, set explicitly, wins over the record of the same
    command line."""
    e = estates()
    argv = note(LA, "explicit id")
    _, pending_id, generation = exit3(e, LA, argv)
    mine = str(uuid.uuid4())
    w = e.run(LA, argv, extra={"LANES_WRITE_ID": mine, "LANES_WRITE_GENERATION": generation})
    assert w.code == 0, w.err[-800:]
    assert set(w.write_ids()) == {mine} and pending_id not in w.write_ids()


@CLIENT
@pytest.mark.parametrize("case", ["absent", "found"])
def test_status_lists_and_resolves_pending_records(estates, case):
    """`lanes-index status` lists each pending record and reports whether
    its id is in the journal: [absent], the first call lost before it
    landed; [found], after it."""
    e = estates()
    arm = dict(NO_RECONNECT, **{"as": "before" if case == "absent" else "after"})
    w = e.run(LA, note(LA, f"status {case}"), arms=[arm])
    assert w.code == 3, w.err[-800:]
    write_id = WRITE_ID_SAID.findall(w.err)[-1]
    env = dict(e.env, PATH=os.pathsep.join([str(e.psql_dir(f"status-{case}")), e.env["PATH"]]))
    status = subprocess.run([str(e.bindir / "lanes-index"), "status"], capture_output=True, text=True,
                            env=env, check=False, timeout=120)
    assert write_id in status.stdout, status.stdout[-800:]
    line = next(l for l in status.stdout.splitlines() if write_id in l)
    if case == "found":
        assert str(e.journal_after()[-1]["seq"]) in line, line
    else:
        assert "absent" in line or "not in the journal" in line, line


# ------------------------------------------------------------ D8: each verb's tail
@CLIENT
def test_a_rerun_that_finds_its_write_committed_runs_the_verbs_after_commit_tail(estates):
    """`rename-lane`'s tail: `lane_state_rename` moves the old control root
    to the new name once; the handoff file at the new path holds one
    `RENAMED from <old>` line; the fake `gh` logs one comment per held claim
    (none here)."""
    e = estates()
    where, root = loggers(e), sidecars(e)
    new = "repoA-9"
    extra = {"LANES_LANE_STATE_ROOT": str(root)}
    again, _, _ = tail_rerun(e, LA, ["rename-lane", LA, new, "T245", "--no-github"], where, extra)
    assert (root / new).is_dir() and not (root / LA).exists()
    handoffs = list(e.root.glob(f"co-*/handoffs/{new}.md"))
    assert handoffs and all(h.read_text(encoding="utf-8").count(f"RENAMED from {LA}") <= 1 for h in handoffs)
    assert comments(where) == []


@CLIENT
@pytest.mark.parametrize("verb", ["RESUMED", "ENDED", "RESUMED-moved-since"])
def test_the_after_commit_tail_of_log_runs_once_when_a_rerun_finds_the_write(estates, verb):
    """`log`'s tail for a verb `lane_state_follow` moves: the sidecar goes
    from g to g+1 once. [RESUMED-moved-since]: another act moved the lane
    since the kill, the replay's fence refuses, the sidecar stays as that act
    left it, a note says the lifecycle moved under the line, exit 0."""
    e = estates()
    where, root = loggers(e), sidecars(e)
    extra = {"LANES_LANE_STATE_ROOT": str(root)}
    argv = ["log", verb.split("-")[0], f"lane:{LA}", f"T245 {verb}"]
    _, write_id = killed(e, LA, argv, first=[where], extra=extra)
    assert generation_of(root, LA) == "1", "the tail ran before the rerun"
    if verb == "RESUMED-moved-since":
        (root / LA / "lane-state.yaml").write_text(f"lane: {LA}\nstate: RUNNING\ngeneration: 7\n",
                                                   encoding="utf-8")
    again = e.run(LA, argv, first=[where], extra=extra)
    assert again.code == 0, again.err[-800:]
    assert [r["write_id"] for r in e.journal_after()].count(write_id) == 1
    if verb == "RESUMED-moved-since":
        assert generation_of(root, LA) == "7" and "moved" in again.err, again.err[-800:]
    else:
        assert generation_of(root, LA) == "2"


@CLIENT
def test_the_after_commit_tail_of_release_runs_once_when_a_rerun_finds_the_write(estates):
    """`release`: its one comment, once, after the rerun finds the write."""
    e = estates()
    where = loggers(e)
    assert e.run(LA, claim(OBJ, "--no-github")).code == 0
    tail_rerun(e, LA, ["release", OBJ, "T245", "--home", OBJ.split("#")[0]], where)
    assert len(comments(where)) == 1, comments(where)


@CLIENT
def test_the_after_commit_tail_of_request_handoff_types_once_in_the_kept_child_and_polls(estates):
    """`request-handoff`: the kept child ran the tail, so the fake `tmux`
    logs one `send-keys`, and the poll reads and ends the run; the request is
    in the register once. Run with `--wait 2` and `LANES_POLL_SECONDS=1`."""
    e = estates()
    where = loggers(e)
    w = e.run(LA, ["request-handoff", LC, "--session", session_of(LC), "--wait", "2"], arms=[AFTER],
              first=[where], extra={"LANES_POLL_SECONDS": "1"})
    assert w.code in (0, 2), w.err[-800:]
    one_entry(e, w)
    sent = [c for c in tool_calls(where, "tmux") if "send-keys" in c["argv"]]
    assert len(sent) == 1, sent
    assert len(tool_calls(where, "tmux")) > 1, "the poll never read the pane"


@CLIENT
def test_the_after_commit_tail_of_retire_rows_runs_once_when_a_rerun_finds_the_write(estates):
    """`retire-rows`: each retired lane's sidecar goes through its follow
    once, with its own pre-image."""
    e = estates()
    where, root = loggers(e), sidecars(e)
    tail_rerun(e, LA, ["retire-rows", LB, LC, "--reason", "T245"], where, {"LANES_LANE_STATE_ROOT": str(root)})
    assert generation_of(root, LB) == "2" and generation_of(root, LC) == "2"


@CLIENT
def test_the_after_commit_tail_of_start_record_runs_once_when_a_rerun_finds_the_write(estates):
    """`start-record`: `lane_state_follow` runs once after the lock: one
    move of the lane's sidecar."""
    e = estates()
    where, root = loggers(e), sidecars(e)
    tail_rerun(e, LA, ["start-record", LA, "--session", session_of(LA)], where,
               {"LANES_LANE_STATE_ROOT": str(root)})
    assert generation_of(root, LA) == "2"


@CLIENT
def test_a_rerun_after_a_3_replays_the_verbs_tail_once(estates):
    """`no-reconnect` ends the first `claim` with 3 (its first call landed),
    abandoning its kept child, with no comment made. A plain rerun finds the
    record, its snapshot finds the id, it replays at `s-1` (one `--at` call)
    and runs the tail: one comment, exit 0."""
    e = estates()
    where = loggers(e)
    argv = claim(OBJ)
    w = e.run(LA, argv, arms=[dict(NO_RECONNECT, **{"as": "after"})], first=[where])
    assert w.code == 3 and comments(where) == [], w.err[-800:]
    again = e.run(LA, argv, first=[where])
    assert again.code == 0, again.err[-800:]
    assert len(comments(where)) == 1, comments(where)


@CLIENT
@pytest.mark.parametrize("state", ["sent-child-never-read", "owed-mark"])
def test_a_sent_record_whose_child_never_read_committed_replays_and_an_owed_mark_runs_no_tail(estates, state):
    """[sent-child-never-read]: a record holding `tail=sent` while the dead
    child's `seam.out` says `none`: the owner removes `tail` and replays,
    one comment, exit 0. [owed-mark]: a mark holding `owed <utc>`; a rerun
    under `LANES_WRITE_ID` runs no tail, adds no comment, and names the
    steps as owed again."""
    e = estates()
    where = loggers(e)
    argv = claim(OBJ)
    _, write_id = killed(e, LA, argv, first=[where])
    rec = the_record(e)
    if state == "sent-child-never-read":
        with rec["path"].open("a", encoding="utf-8") as f:
            f.write(f"tail=sent {e.journal_after()[-1]['seq']} {e.utc()}\n")
        for seam in e.state.rglob("seam.out"):
            seam.write_text("none\n", encoding="utf-8")
        again = e.run(LA, argv, first=[where])
        assert again.code == 0 and len(comments(where)) == 1, (again.err[-800:], comments(where))
    else:
        mark = mark_of(e, write_id)
        mark.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        mark.write_text(f"{write_id} {e.journal_after()[-1]['seq']} owed {e.utc()}\n", encoding="utf-8")
        rec["path"].unlink()
        again = e.run(LA, argv, first=[where], extra={"LANES_WRITE_ID": write_id})
        assert again.code == 0 and comments(where) == [] and "owed" in again.err, again.err[-800:]


@CLIENT
@pytest.mark.parametrize("case", ["rename-lane-stops", "rename-lane-differs", "request-handoff-differs"])
def test_a_replay_of_rename_lane_or_request_handoff_that_stops_or_differs_runs_none_of_the_tail(estates, case):
    """The write is committed either way. [rename-lane-stops]: the handoff
    file removed, so the replay stops before its write; [rename-lane-differs]:
    the handoff moved by hand, so the change set differs. Each writes the
    mark `owed <utc>`, removes the record, prints one WARNING, exits 0 and
    runs no tail. [request-handoff-differs]: the fake `tmux` reports the
    holder's window gone; the run exits 2, saying the request is written at
    seq `<s>` and it did not wait for the release."""
    e = estates()
    where, root = loggers(e), sidecars(e)
    extra = {"LANES_LANE_STATE_ROOT": str(root)}
    argv = (["request-handoff", LC, "--session", session_of(LC)] if case.startswith("request")
            else ["rename-lane", LA, "repoA-9", "T245", "--no-github"])
    _, write_id = killed(e, LA, argv, first=[where], extra=extra)
    seq = e.journal_after()[-1]["seq"]
    handoffs = list(e.root.glob(f"co-*/handoffs/{LA}.md"))
    if case == "rename-lane-stops":
        for h in handoffs:
            h.unlink()
    elif case == "rename-lane-differs":
        for h in handoffs:
            h.rename(h.with_name("repoA-9.md"))
    else:
        (where / "tmux").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    again = e.run(LA, argv, first=[where], extra=extra)
    if case.startswith("request"):
        assert again.code == 2 and f"seq {seq}" in again.err, again.err[-800:]
    else:
        assert again.code == 0 and again.err.count("WARNING") == 1, again.err[-800:]
        assert "owed" in mark_of(e, write_id).read_text(encoding="utf-8")
        assert (root / LA).is_dir(), "the tail ran"
    assert pending(e) == []


# ------------------------------------------------------------ D8: the takeover, the call lines, the claims
@CLIENT
@pytest.mark.parametrize("when", ["before-the-send", "mid-call"])
@pytest.mark.parametrize("snapshot", ["snapshot-passes", "snapshot-fails"])
def test_a_run_killed_after_its_call_line_or_mid_call_is_taken_over_in_doubt_and_waits_past_not_after(
        estates, when, snapshot):
    """A `claim` killed after its `call` line is written ([before-the-send]:
    the shim holds the call before `psql`) or mid-call (the admin session
    holds the head row while the call runs, then rolls back). Another lane
    then claims the object. A plain rerun takes the record over, in doubt
    from its start. [snapshot-passes]: its verb refuses at the snapshot with
    2, sending no commit call, and it exits only after the database's clock
    has passed the record's `not_after`. [snapshot-fails] (Q-L2-6; R26): the
    shim fails the takeover's snapshot; with no clock of its own it waits on
    the record's (`--clock` from the newest `call` line, `--clock-age` from
    `updated_utc`), makes its lookup and ends by it, never LR011's 3. The
    journal never holds two rows for the id; the record goes."""
    e = estates()
    gate = fifo(e, "commit-1")
    argv = claim(OBJ, "--no-github")
    admin = e.hold_row_locked() if when == "mid-call" else None
    arms = [{"mode": "hold", "match": "commit_write", "call": 1, "fifo": str(gate)}] if admin is None else []
    w = e.launch(LA, argv, arms=arms)
    if admin is None:
        held = hold_point(gate, w)
    else:
        until_seen("the shim logging the commit call's start", lambda: w.commit_calls()[:1], w)
    rec = the_record(e)
    assert len(rec["calls"]) == 1, "the call line was not written before the send"
    os.killpg(w.proc.pid, signal.SIGKILL)
    w.wait()
    if admin is not None:
        e.unlock(admin)
    else:
        held.close()
    write_id = rec["fields"]["write_id"].lower()
    not_after = rec["calls"][0].split()[2]
    landed = e.has_write(write_id)
    rival = e.run(LB, argv)
    arms = [{"mode": "fail-match", "match": SNAPSHOT_TEXT, "call": 1}] if snapshot == "snapshot-fails" else []
    again = e.run(LA, argv, arms=arms)
    assert [r["write_id"] for r in e.journal_after()].count(write_id) <= 1
    if landed:
        assert (rival.code, again.code) == (2, 0), (rival.err[-300:], again.err[-300:])
    else:
        assert rival.code == 0 and again.code == 2, again.err[-800:]
        assert snapshot == "snapshot-fails" or again.commit_calls() == []
        assert db_past(e, not_after), "the takeover exited before the record's not_after"
    assert "LR011" not in again.err
    assert pending(e) == []


@CLIENT
@pytest.mark.parametrize("case", ["before-the-send", "lost-turn", "refusal", "in-doubt"])
def test_the_pending_records_call_lines_are_written_before_the_send_and_dropped_only_for_a_call_that_did_not_commit(
        estates, case):
    """[before-the-send]: while the shim holds the first commit call, the
    record already holds its line. [lost-turn]: after a 40001 from a rival's
    commit, the record read while the next call is held holds one line, the
    next call's, with base n+1. [refusal]: after a refusal the record is
    gone. [in-doubt]: after a call in doubt it keeps the line, and the
    attempt directory keeps `snapshot`, `files` and `preimages`."""
    e = estates()
    if case == "before-the-send":
        gate = fifo(e, "commit-1")
        w = e.launch(LA, note(LA, case), arms=[{"mode": "hold", "match": "commit_write", "call": 1,
                                                 "fifo": str(gate)}])
        held = hold_point(gate, w)
        assert len(the_record(e)["calls"]) == 1
        held.close()
        assert w.wait() == 0
    elif case == "lost-turn":
        gates = fifo(e, "commit-1"), fifo(e, "commit-2")
        w = e.launch(LA, note(LA, case), arms=[
            {"mode": "hold", "match": "commit_write", "call": 1, "fifo": str(gates[0])},
            {"mode": "hold", "match": "commit_write", "call": 2, "fifo": str(gates[1])}])
        first = hold_point(gates[0], w)
        base = int(the_record(e)["calls"][0].split()[0])
        assert e.run(LB, note(LB, "the rival")).code == 0
        first.close()
        second = hold_point(gates[1], w)
        calls = the_record(e)["calls"]
        assert len(calls) == 1 and int(calls[0].split()[0]) == base + 1, calls
        second.close()
        assert w.wait() == 0
    elif case == "refusal":
        assert e.run(LB, claim(OBJ, "--no-github")).code == 0
        w = e.run(LA, claim(OBJ, "--no-github"))
        assert w.code == 2 and pending(e) == []
    else:
        w, _, _ = exit3(e, LA, note(LA, case))
        calls = the_record(e)["calls"]
        assert len(calls) == 1
        attempt = Path(calls[0].split()[-1])
        assert all((attempt / name).is_file() for name in ("snapshot", "files", "preimages")), attempt


@CLIENT
@pytest.mark.parametrize("case", ["take-0", "take-1", "two-reruns"])
def test_a_pending_record_is_owned_through_numbered_claim_files_and_two_reruns_never_both_take_it(estates, case):
    """[take-0]: a run with no record creates `<d>.take.0`, read while the
    shim holds the first commit call, holding the run's pid, start time,
    host, container and UTC. [take-1]: after a kill a rerun creates
    `<d>.take.1`. [two-reruns]: two printed reruns under `LANES_WRITE_ID`
    released together against a dead owner, in 10 rounds: one create of
    `<d>.take.1` succeeds, one comment and one row each round, both exit 0.
    After a run's end no record and no claim file remains."""
    e = estates()
    if case == "take-0":
        gate = fifo(e, "commit-1")
        w = e.launch(LA, note(LA, case), arms=[{"mode": "hold", "match": "commit_write", "call": 1,
                                                 "fifo": str(gate)}])
        held = hold_point(gate, w)
        takes = take_files(e)
        assert [t.rsplit(".", 1)[1] for t in takes] == ["0"], takes
        text = (e.state / PENDING / takes[0]).read_text(encoding="utf-8")
        assert str(w.proc.pid) in text or "pid" in text, text
        held.close()
        assert w.wait() == 0
    elif case == "take-1":
        argv = note(LA, case)
        killed(e, LA, argv)
        assert [t.rsplit(".", 1)[1] for t in take_files(e)] == ["0"]
        assert e.run(LA, argv).code == 0
    else:
        where = loggers(e)
        for k in range(10):
            obj = f"opensoft/r9#{100 + k}"
            argv = claim(obj)
            _, write_id = killed(e, LA, argv, first=[where])
            generation = e.c.switch()["generation"]
            (e.root / f"round-{k}").mkdir()
            barrier = Barrier(e.root / f"round-{k}", 2)
            before = len(comments(where))
            pair = [e.launch(LA, argv, barrier=barrier, first=[where],
                             extra={"LANES_WRITE_ID": write_id, "LANES_WRITE_GENERATION": generation})
                    for _ in range(2)]
            barrier.release()
            assert [p.wait() for p in pair] == [0, 0], [p.err[-300:] for p in pair]
            assert len(comments(where)) - before == 1, f"round {k}: {len(comments(where)) - before} comments"
            assert [r["write_id"] for r in e.journal_after()].count(write_id) == 1
    assert pending(e) == [] and take_files(e) == []


# ------------------------------------------------------------ AT-F34: the tail, once
def learnt(e: Estate, way: str, where: Path, *, gone: bool = False, script: Optional[Path] = None) -> Writer:
    """A `claim` whose first commit call committed while in doubt, learnt by
    [snapshot] (`after`, then the next snapshot), [lr006] (the first call
    forked and held as AT-F3's orphan, the shim exiting 2 at once; the next
    commit call held until the orphan has committed, so it gets LR006) or
    [lookup] (`after`, the next snapshot failed, so AT-F3's lookup finds
    it). The call that learns it is held; with `gone`, until the kept
    child's `seam.out` says `none` under `LANES_REGISTER_SEAM_CAP_S=3`."""
    gate = fifo(e, f"learn-{way}")
    if way == "lr006":
        orphan = fifo(e, "orphan")
        arms = [{"mode": "fork", "match": "commit_write", "call": 1, "fifo": str(orphan), "exit": True},
                {"mode": "hold", "match": "commit_write", "call": 2, "fifo": str(gate)}]
    elif way == "snapshot":
        arms = [AFTER, {"mode": "hold", "match": SNAPSHOT_TEXT, "call": 2, "fifo": str(gate)}]
    else:
        arms = [AFTER, {"mode": "fail-match", "match": SNAPSHOT_TEXT, "call": 2},
                {"mode": "hold", "match": "find_write", "call": 1, "fifo": str(gate)}]
    extra = {"LANES_REGISTER_SEAM_CAP_S": "3"} if gone else {}
    w = e.launch(LA, claim(OBJ), first=[where], arms=arms, extra=extra, script=script)
    held = hold_point(gate, w)
    if way == "lr006":
        hold_point(orphan, w).close()
        until_seen("the orphan's commit", lambda: e.journal_after(), w)
    if gone:
        until_seen("the kept child's seam.out saying none", lambda: any(
            p.read_text(encoding="utf-8").strip() == "none" for p in e.state.rglob("seam.out")), w)
    held.close()
    return w


@CLIENT
@pytest.mark.parametrize("way", ["snapshot", "lr006", "lookup"])
def test_a_call_in_doubt_that_committed_runs_its_tail_once_from_the_kept_child(estates, way):
    """The call in doubt committed, learnt by [snapshot], [lr006] or
    [lookup] (`learnt`). The kept child's `seam.out` says `tail` and every
    other child's `none`; the fake `gh` is called once, after the COMMIT;
    the mark keeps `done`; exit 0, one row."""
    e = estates()
    where = loggers(e)
    w = learnt(e, way, where)
    assert w.wait() == 0, w.err[-800:]
    write_id = one_entry(e, w)
    seams = sorted(p.read_text(encoding="utf-8").strip() for p in e.state.rglob("seam.out"))
    assert seams.count("tail") == 1 and set(seams) <= {"tail", "none"}, seams
    assert len(comments(where)) == 1, comments(where)
    assert "done" in mark_of(e, write_id).read_text(encoding="utf-8")


@CLIENT
@pytest.mark.parametrize("way", ["snapshot", "lr006", "lookup"])
def test_with_the_kept_child_gone_a_replay_runs_the_tail_once(estates, way):
    """The same three, with the cap ending the kept child first. The run
    replays at `s-1` (lanes-index's `register snapshot --tree <dir> --at
    <s-1>`, which the shim does not see, so its count is lane 4's to log)
    and sends no commit call after it; the fake `gh` is called once."""
    e = estates()
    where = loggers(e)
    w = learnt(e, way, where, gone=True)
    assert w.wait() == 0, w.err[-800:]
    one_entry(e, w)
    assert len(comments(where)) == 1, comments(where)


@CLIENT
def test_a_replay_of_request_handoff_types_into_no_pane(estates):
    """With the kept child gone, `request-handoff`'s replay runs its tail
    with no `guard_type`: the fake `tmux` logs no `send-keys`, and the poll
    runs."""
    e = estates()
    where = loggers(e)
    argv = ["request-handoff", LC, "--session", session_of(LC), "--wait", "2"]
    killed(e, LA, argv, first=[where])
    before = len(tool_calls(where, "tmux"))
    again = e.run(LA, argv, first=[where], extra={"LANES_POLL_SECONDS": "1"})
    assert again.code in (0, 2), again.err[-800:]
    later = tool_calls(where, "tmux")[before:]
    assert not [c for c in later if "send-keys" in c["argv"]], later
    assert later, "the poll never ran"


@CLIENT
def test_a_rerun_that_finds_tail_sent_runs_no_tail_and_writes_the_done_mark(estates):
    """The record holds `tail=sent` from a run killed after `sent` and
    before the child's exit. A plain rerun takes it over, finds its id at
    the snapshot and `tail` sent, runs no tail, writes the mark with `sent`,
    removes the record, exits 0, and says the steps may have run at the
    record's UTC in its pid."""
    e = estates()
    where = loggers(e)
    argv = claim(OBJ)
    _, write_id = killed(e, LA, argv, first=[where])
    rec = the_record(e)
    utc = e.utc()
    with rec["path"].open("a", encoding="utf-8") as f:
        f.write(f"tail=sent {e.journal_after()[-1]['seq']} {utc}\n")
    again = e.run(LA, argv, first=[where])
    assert again.code == 0 and comments(where) == [], again.err[-800:]
    assert "sent" in mark_of(e, write_id).read_text(encoding="utf-8")
    assert pending(e) == [] and utc in again.err, again.err[-800:]


def replay_copy(e: Estate, control: Path) -> Path:
    """AT-F34's test copy (TP:6962-6965): a `lanes-edit.sh` whose runs under
    the seam's scratch flag read `control` once the test writes it: `stops`
    exits 1 before `ready`, and `differs` adds one more word to the line, so
    a replay stops or reaches the seam with another change set."""
    text = e.lanes_edit.read_text(encoding="utf-8")
    shebang, rest = text.split("\n", 1)
    quoted = "'" + str(control).replace("'", "'\\''") + "'"
    hook = (f'if [ -n "${{LANES_REGISTER_SCRATCH:-}}" ] && [ -f {quoted} ]; then\n'
            f'  case "$(cat {quoted})" in\n'
            '    stops) echo "T245: the replay stops" >&2; exit 1 ;;\n'
            '    differs) set -- "$@" "T245 differs" ;;\n'
            '  esac\nfi\n')
    copy = e.bindir / "lanes-edit-t245.sh"
    copy.write_text(shebang + "\n" + hook + rest, encoding="utf-8")
    copy.chmod(0o755)
    return copy


@CLIENT
@pytest.mark.parametrize("case", ["stops", "differs"])
def test_a_replay_that_stops_or_differs_runs_no_tail_and_warns(estates, case):
    """With the kept child gone and the test copy's control file written,
    the replay exits 1 before `ready` ([stops]) or reaches the seam with one
    more word ([differs]). The run exits 0 with one WARNING naming the seq;
    the fake `gh` is not called, and the record is removed."""
    e = estates()
    where = loggers(e)
    control = e.root / "t245-replay"
    script = replay_copy(e, control)
    argv = claim(OBJ)
    killed(e, LA, argv, first=[where], script=script)
    seq = e.journal_after()[-1]["seq"]
    control.write_text(case + "\n", encoding="utf-8")
    again = e.run(LA, argv, first=[where], script=script)
    assert again.code == 0 and again.err.count("WARNING") == 1 and str(seq) in again.err, again.err[-800:]
    assert comments(where) == [] and pending(e) == []


@CLIENT
@pytest.mark.parametrize("case", ["done-mark", "this-host", "other-host"])
def test_a_run_with_no_record_runs_no_tail_and_names_it(estates, case):
    """A rerun under `LANES_WRITE_ID` of a write committed and settled, with
    no record here, exits 0 and runs no tail. [done-mark]: it says what the
    mark's `tail` says; [this-host]: with the mark removed and
    `journal.workstation` this host (`found`'s `workstation=`), it says the
    steps may already have run here, naming the entry's UTC from `utc=`;
    [other-host]: the write made from ws2, it names ws2 and says to rerun
    there if that run ended 3."""
    e = estates()
    where = loggers(e)
    argv = claim(OBJ)
    extra = {"LANES_WORKSTATION": "ws2"} if case == "other-host" else {}
    w = e.run(LA, argv, first=[where], extra=extra)
    assert w.code == 0
    write_id = w.write_ids()[-1]
    if case != "done-mark":
        mark_of(e, write_id).unlink()
    before = len(comments(where))
    again = e.run(LA, argv, first=[where], extra={"LANES_WRITE_ID": write_id})
    assert again.code == 0 and len(comments(where)) == before, again.err[-800:]
    if case == "other-host":
        assert "ws2" in again.err and "rerun" in again.err, again.err[-800:]
    elif case == "this-host":
        assert "may already have run" in again.err, again.err[-800:]
    else:
        assert "done" in again.err, again.err[-800:]


# ------------------------------------------------------------ GB §4.3: the texts for 3 (runs here)
#: Each site's file, and the clause it must hold: the writer's exit table's
#: row 3 primary clause (lane 4's T417, R21); `lane-rename`'s header and
#: default arm (T433); `lane-worktrees`' note (T434).
TEXTS_FOR_3 = {"exit-table": "lanes-edit.sh", "lane-rename": "lane-rename", "lane-worktrees": "lane-worktrees"}


@pytest.mark.parametrize("site", list(TEXTS_FOR_3))
def test_the_texts_for_3_say_may_not_be_written_and_relay_the_writers_rerun(site):
    """On exit 3 on primary each site prints D8's text for 3, byte for byte
    with its backticks, relays the writer's printed rerun verbatim, and never
    prints its own hint, "was NOT added" or "NOT WRITTEN". Read from the
    scripts, with no engine: each must hold D8's text and none of the
    refused hints, where its exit-3 arm stands."""
    from sql_register_helpers import REPO
    path = REPO / TEXTS_FOR_3[site]
    assert path.is_file(), f"{path.name} is not in the code root"
    text = path.read_text(encoding="utf-8")
    forms = [D8_TEXT_3, D8_TEXT_3.replace("`", "\\`")]
    assert any(form in text for form in forms), f"{path.name} does not hold D8's text for 3: {D8_TEXT_3!r}"
    for refused in ("was NOT added", "NOT WRITTEN"):
        near = [m.start() for form in forms for m in re.finditer(re.escape(form), text)]
        assert not any(refused in text[max(0, k - 400):k + 400] for k in near), (
            f"{path.name} prints {refused!r} beside D8's text for 3")
