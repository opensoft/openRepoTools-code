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

THE FIXTURE, AT-LR006'S, ON A CLONE OF ITS OWN: each test clones
`tmpl_imported` (section 3.1; T227), runs §1.4's two database-level
statements on the clone, and drops it `WITH (FORCE)` at the end:

  * database R, between a re-import's bootstrap and its cutover: the clone as
    it is, at `files` with the marker `absent`, whose generation is `g1`;
    `g0`, the lost database's, is a uuid of the test's own;
  * database S, a restore: the clone brought to `primary` with the marker
    `present` by `Clone.to_primary` (a `cutover` entry over the template's
    import, then `record_marker`: TP:4610–4615), standing in for a restored
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
`find_write`) and T114 (L1-A12) land, with lane 2's T227 (`tmpl_imported`)
and T228 (`lanes_w_fx`). Without PostgreSQL 16 each skips.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import time
import uuid
from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from pgcluster import SUPERUSER, Database

REGISTER = "lanes_register"
IMPORTED = "tmpl_imported"
WRITER_LOGIN = "lanes_w_fx"
CONNECT_TO = "lanes_register_writer, lanes_register_reader, lanes_indexer"
LANES_MD, STORE = "lanes/LANES.md", "lanes/STORE"
WS, AUTHOR = "ws-t222", "T222 Fixture <t222@example.invalid>"
OPERATOR = "operator-t222"
MARKER_COMMIT = "c0ffee" + "1" * 34
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
    """One clone of `tmpl_imported`, and the documented functions called on
    it as REGISTER-WRITER, through `lanes_w_fx` (AT-LR006's fixture)."""

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

    def to_primary(self) -> int:
        """A `cutover` entry over the template's import, then `record_marker`."""
        sw = self.switch()
        assert (sw["mode"], sw["marker_state"]) == ("files", "absent"), sw
        head = self.head()
        last_import = int(self.value(f"SELECT coalesce(max(seq), -2) FROM {REGISTER}.journal WHERE kind = 'import';"))
        assert last_import == head >= 0, f"{IMPORTED}'s head {head} is not its import ({last_import})"
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
    """Clones of `tmpl_imported`, each the test's own, dropped at the end."""
    made: List[str] = []

    def clone() -> Clone:
        found = pg_cluster.psql(f"SELECT datname FROM pg_database WHERE datname = '{IMPORTED}';").stdout.split()
        assert found == [IMPORTED], f"no {IMPORTED} on the session cluster: lane 2's T227 builds it"
        name = f"t222_{next(_NAMES)}"
        pg_cluster.psql(f"CREATE DATABASE {name} TEMPLATE {IMPORTED};")
        made.append(name)
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
    head = c.head()
    g0 = str(uuid.uuid4())
    c.refused(c.write_entry(), "LR007", "generation", f"belongs to register generation {g0}",
              generation=g0, base=head if base == "current-base" else head - 1)


def test_the_switchs_own_generation_at_files_still_gets_lr002(clones):
    """In R, a write of `g1`, the switch's own, with the base current: LR002."""
    c = clones()
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
