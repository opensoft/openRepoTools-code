# SPDX-License-Identifier: Apache-2.0
"""AT-LR5's `LANDING EXPIRED` (F13) and take-with-no-UTC (U3) cases (#165, L2-W4).

PHASE N, ON A REAL POSTGRESQL 16: `commit_write`'s step 7 is lane 1's SQL
(design.md §1.3's step 7, §1.3.1), so each case calls it directly, with no
verb; the verb is AT-F13's. The rest of AT-LR5 is T232's, in this module too.

THE FIXTURE, AT-LR006'S, ON A CLONE OF ITS OWN: each case clones
`tmpl_imported` (section 3.1; T227), runs §1.4's two database-level
statements on the clone, since a clone does not copy `pg_database.datacl`,
and drops it `WITH (FORCE)` at the end. `Clone.to_primary` then brings it to
`primary` with the marker `present` by the documented functions, as
REGISTER-WRITER: `commit_write` with a `cutover` entry over the template's
import, then `record_marker` (TP:4610–4615; the plan's fixtures at TP:4354
and :4806). Every call logs in as the fixture's writer login, `lanes_w_fx`
(T228), whose privileges come through REGISTER-WRITER, in the commit call's
own form:

    psql -X -q -A -t -v ON_ERROR_STOP=1 -v VERBOSITY=verbose -v SHOW_CONTEXT=never
    BEGIN ISOLATION LEVEL SERIALIZABLE;
    SELECT lanes_register.commit_write(:base, :'wid'::uuid, :client, :'gen'::uuid, :'entry'::jsonb);
    COMMIT;

with the script on stdin, so a refusal's first stderr line is
`ERROR:  <SQLSTATE>: <message>` and its second `DETAIL:  <token>` (U7).

EACH ENTRY IS AN APPEND OF ONE LINE TO `lanes/LANES.md`, built as AT-LR006
builds one: the edit, the file's digest after it (`render_file`'s bytes,
computed here from `doc_lines` as the superuser reads them), and the line's
`register_lines` row, whose fields the test sets as the client would parse
them. Lines name `opensoft/r9`, which `lanes/repos.tsv` maps from `r9`, so a
row's `repo_spellings` is `{opensoft/r9,r9}` where the case says both. A
take's `utc_ts` is set from the database's clock at the snapshot, past Rule
6's 30 minutes where the case says so, so no case waits for the window.

THE ORACLE OF A REFUSAL: `psql` exits 3; its first stderr line is the
code's, naming the rule; its second is exactly the rule's `DETAIL:` token;
and the head, the journal, its edits, the files, `doc_lines`,
`register_lines` and the switch equal their values before, with the write id
absent.

Every case FAILS UNTIL lane 1's T107 (L1-A6, `commit_write` and its step 7)
and T118 (L1-A16, the kinds' slots), and lane 2's T227 (`tmpl_imported`) and
T228 (`lanes_w_fx`) land. Without PostgreSQL 16 each skips.

THE MODULE ALSO HOLDS, each at its own section below, in this order: T243's
test 4, C10, D19 and section 4.1 (phase W, the client's writers on a real
register); T248's AT-F14 (phase W); T233's AT-F5 group A (phase N, the act's
client half, its off-primary and walk cases with no engine); T252's AT-F5
group B (phase W);
T232's AT-LR5 and AT-LR009 (phase N, `commit_write` called directly on this
section's `Clone`, as here), whose rollback steps fail until T304; and, last,
T243d's `register commit` path refusal (lane 1's follow-up 2: phase W, as
T243's, but with no engine).
"""

from __future__ import annotations

import errno
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from pgcluster import SUPERUSER, Database
from sql_register_helpers import (LANES_INDEX, PSQL_SHIM, PSQL_SHIM_CONTROL, PSQL_SHIM_ENDS,
                                  PSQL_SHIM_LOG, REPO, flipped_copy)
from test_lane_start_claude_current import Sandbox, _write

REGISTER = "lanes_register"
IMPORTED = "tmpl_imported"
WRITER_LOGIN = "lanes_w_fx"
CONNECT_TO = "lanes_register_writer, lanes_register_reader, lanes_indexer"
LANES_MD, STORE = "lanes/LANES.md", "lanes/STORE"
WS, AUTHOR = "ws-t223", "T223 Fixture <t223@example.invalid>"
OPERATOR = "operator-t223"
MARKER_COMMIT = "c0ffee" + "0" * 34
GIT_COMMIT, GIT_TREE = "1" * 40, "2" * 40

#: The lanes and the repository of the cases: L1 holds, L2 writes the
#: release, L3 holds nothing on `opensoft/r9`.
L1, L2, L3 = "L1-t223", "L2-t223", "L3-t223"
KEY, ALIAS, OTHER_KEY = "opensoft/r9", "r9", "opensoft/r8"
BOTH = [KEY, ALIAS]
PR, OTHER_PR = 7, 8
BAD_STAMP = "2026-13-45T99:99Z"

#: Q17 (B)'s slots for the kinds these cases write (lane 1's REGISTER_SLOTS).
SLOTS = {"HOLD": ("take", "hold"), "LANDING": ("take", "landing"),
         "LANDED": ("close", "landing"), "LANDING EXPIRED": ("close", "landing"),
         "HOLD (refresh)": (None, None), None: (None, None)}

COMMIT_SQL = ("BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
              f"SELECT {REGISTER}.commit_write(:base, :'wid'::uuid, :client, :'gen'::uuid, :'entry'::jsonb);\n"
              "COMMIT;\n")
MARKER_SQL = f"SELECT {REGISTER}.record_marker(:client, :seq, :'commit', :'ws');\n"

#: Everything a refused call must leave as it was.
STATE_SQL = f"""
SELECT md5(concat_ws('|',
  (SELECT seq::text FROM {REGISTER}.register_head),
  (SELECT string_agg(j::text, ',' ORDER BY j.seq) FROM {REGISTER}.journal j),
  (SELECT string_agg(e::text, ',' ORDER BY e.seq, e.ord) FROM {REGISTER}.journal_edits e),
  (SELECT string_agg(f::text, ',' ORDER BY f.path) FROM {REGISTER}.files f),
  (SELECT string_agg(d::text, ',' ORDER BY d.line_id) FROM {REGISTER}.doc_lines d),
  (SELECT string_agg(r::text, ',' ORDER BY r.line_id) FROM {REGISTER}.register_lines r),
  (SELECT string_agg(s::text, ',') FROM {REGISTER}.register_switch s)));
"""

_NAMES = itertools.count(1)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rendered(lines: Sequence[str], final_newline: bool) -> bytes:
    """`render_file`'s bytes: the lines joined by LF, and a last LF where
    the file ends with one and holds a line."""
    text = "\n".join(lines) + ("\n" if final_newline and lines else "")
    return text.encode("utf-8")


class Clone:
    """One clone of `tmpl_imported`, and the documented functions called on
    it as REGISTER-WRITER, through `lanes_w_fx` (AT-LR006's fixture)."""

    def __init__(self, cluster, name: str) -> None:
        self.cluster, self.name = cluster, name
        self.db = Database(cluster, name)

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

    def stamp(self, minutes_ago: float) -> Tuple[str, str]:
        """The database's clock less `minutes_ago`: the line's UTC, as a line
        spells it, and `utc_ts`."""
        said = self.value(
            "SELECT to_char(t AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI\"Z\"') || '|' || t::text "
            f"FROM (SELECT clock_timestamp() - make_interval(secs => {minutes_ago * 60}) AS t) s;")
        utc, utc_ts = said.split("|")
        return utc, utc_ts

    def not_after(self, seconds: float = 60) -> str:
        return self.value(f"SELECT (clock_timestamp() + make_interval(secs => {seconds}))::text;")

    def file(self, path: str) -> Tuple[Optional[bool], List[str]]:
        """`files.final_newline` (None where there is no such file) and the lines."""
        said = self.json(
            f"SELECT json_build_object('nl', (SELECT final_newline FROM {REGISTER}.files WHERE path = '{path}'), "
            f"'lines', (SELECT coalesce(jsonb_agg(text ORDER BY line_no), '[]') FROM {REGISTER}.doc_lines "
            f"WHERE path = '{path}'));")
        return said["nl"], said["lines"]

    def open_takes(self, lane: str, slot_kind: str) -> List[List[str]]:
        out = self.value(f"SELECT coalesce(json_agg(json_build_array(repo_key, pr) ORDER BY line_id), '[]') "
                         f"FROM {REGISTER}.main_slots WHERE lane = '{lane}' AND slot_kind = '{slot_kind}';")
        return json.loads(out)

    def no_taker(self) -> None:
        """The cases' lines must meet no take of the template's own."""
        held = self.value(f"SELECT count(*) FROM {REGISTER}.main_slots WHERE repo_key IN "
                          f"('{KEY}', '{ALIAS}', '{OTHER_KEY}') OR repo_spellings && "
                          f"ARRAY['{KEY}', '{ALIAS}', '{OTHER_KEY}'];")
        assert held == "0", f"{IMPORTED} holds {held} open take(s) on {KEY}, which every case here writes"

    # -------------------------------------------------- the calls, as the writer
    def call(self, sql: str, **variables) -> subprocess.CompletedProcess:
        argv = [self.db.psql_bin, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                "-v", "VERBOSITY=verbose", "-v", "SHOW_CONTEXT=never"]
        for name, value in variables.items():
            argv += ["-v", f"{name}={value}"]
        return subprocess.run(argv, input=sql, capture_output=True, text=True, timeout=60,
                              env=self.db.env(WRITER_LOGIN), check=False)

    def commit(self, entry: dict, *, base: Optional[int] = None, write_id: Optional[str] = None,
               generation: Optional[str] = None) -> Tuple[subprocess.CompletedProcess, str]:
        write_id = write_id or str(uuid.uuid4())
        proc = self.call(COMMIT_SQL, base=self.head() if base is None else base, wid=write_id,
                         client=self.client(), gen=generation or self.switch()["generation"],
                         entry=json.dumps(entry, ensure_ascii=False))
        return proc, write_id

    def committed(self, entry: dict, **options) -> int:
        proc, _ = self.commit(entry, **options)
        assert proc.returncode == 0, (
            f"commit_write as {WRITER_LOGIN} exited {proc.returncode}: {proc.stderr.strip()[-800:]}")
        return int(proc.stdout.strip())

    # -------------------------------------------------- entries
    def journal(self, kind: str, verb: str, lane: str, **extra) -> dict:
        row = {"kind": kind, "verb": verb, "lane": lane, "workstation": WS, "author": AUTHOR,
               "message": f"{verb} by {lane} (T223)"}
        row.update(extra)
        return row

    def appended(self, path: str, texts: Sequence[str], *, create: bool = False) -> Tuple[list, list, int]:
        """The edits and the files row of appending `texts` to `path`, and the
        first appended line's number."""
        final_newline, lines = (None, []) if create else self.file(path)
        edits = []
        if final_newline is None:
            edits.append({"ord": 1, "op": "create", "path": path})
            final_newline = True
        for text in texts:
            edits.append({"ord": len(edits) + 1, "op": "append", "path": path, "new_text": text})
        files = [{"path": path, "present": True, "sha256": sha256(rendered([*lines, *texts], final_newline)),
                  "final_newline": final_newline}]
        return edits, files, len(lines) + 1

    def append(self, lane: str, line: str, row: dict, *, verb: str = "append-line") -> dict:
        """A write entry: one line appended to `lanes/LANES.md`, and its row."""
        edits, files, line_no = self.appended(LANES_MD, [line])
        args = sha256(f"{lane}\0{verb}\0{line}".encode("utf-8"))
        return {"journal": self.journal("write", verb, lane, args_sha256=args),
                "not_after": self.not_after(), "edits": edits, "files": files,
                "register_lines": [dict(row, path=LANES_MD, line_no=line_no, raw=line, workstation=WS)]}

    def write(self, lane: str, line_row: Tuple[str, dict]) -> int:
        line, row = line_row
        return self.committed(self.append(lane, line, row))

    def to_primary(self) -> int:
        """A `cutover` entry over the template's import, then `record_marker`:
        `primary`, the marker `present`. Returns the cutover's seq."""
        sw = self.switch()
        assert (sw["mode"], sw["marker_state"]) == ("files", "absent"), sw
        head = self.head()
        last_import = int(self.value(f"SELECT coalesce(max(seq), -2) FROM {REGISTER}.journal WHERE kind = 'import';"))
        assert last_import == head >= 0, f"{IMPORTED}'s head {head} is not its import ({last_import})"
        edits, files, _ = self.appended(STORE, ["primary"])
        seq = self.committed({"journal": self.journal("cutover", "cutover", OPERATOR),
                              "not_after": self.not_after(), "edits": edits, "files": files})
        marked = self.call(MARKER_SQL, client=self.client(), seq=seq, commit=MARKER_COMMIT, ws=WS)
        assert (marked.returncode, marked.stdout.strip()) == (0, "present"), marked.stderr
        sw = self.switch()
        assert (sw["mode"], sw["marker_state"]) == ("primary", "present"), sw
        return seq

    def refused(self, entry: dict, code: str, detail: Optional[str], *says: str) -> List[str]:
        """The call ends with `code` and `detail`, and writes nothing."""
        before = self.state()
        proc, write_id = self.commit(entry)
        lines = proc.stderr.splitlines()
        assert proc.returncode == 3, f"exit {proc.returncode}, not 3: {proc.stderr.strip()}"
        assert lines and lines[0].startswith(f"ERROR:  {code}: "), lines
        if detail is not None:
            assert lines[1:2] == [f"DETAIL:  {detail}"], lines
        for text in says:
            assert text in lines[0], f"{text!r} is not in {lines[0]!r}"
        assert self.state() == before, "the refused call changed the register"
        assert self.value(f"SELECT count(*) FROM {REGISTER}.journal WHERE write_id = '{write_id}';") == "0"
        return lines


# ------------------------------------------------------------ the lines
def line(c: Clone, kind: Optional[str], lane: str, *, repo: str = KEY, key: Optional[str] = None,
         spellings: Optional[List[str]] = None, pr: Optional[int] = PR, age: Optional[float] = 0,
         stamp: Optional[str] = None, for_lane: Optional[str] = None,
         slot: Optional[Tuple[Optional[str], Optional[str]]] = None, text: Optional[str] = None) -> Tuple[str, dict]:
    """A LANES.md line of `kind` and its `register_lines` row. `age` is in
    minutes by the database's clock; None, a line with no UTC, or with
    `stamp`, a UTC that cannot be read."""
    utc, utc_ts = c.stamp(age) if age is not None else (stamp, None)
    tail = f" — {utc}" if utc else ""
    pr_part = f"PR #{pr} into {repo} main" if pr is not None else f"{repo} main"
    if text is None:
        if kind == "LANDING EXPIRED":
            names = f" for lane {for_lane}" if for_lane else ""
            text = f"{kind} — lane {lane} — {pr_part}{names}{tail}"
        elif kind == "LANDED":
            text = f"{kind} — lane {lane} — {pr_part} → 0123abc{tail}"
        else:
            text = f"{kind} — lane {lane} — {pr_part}{tail}"
    slot_role, slot_kind = slot if slot is not None else SLOTS[kind]
    row = {"kind": kind, "slot_role": slot_role, "slot_kind": slot_kind, "lane": lane, "repo": repo,
           "repo_key": key or repo, "repo_spellings": spellings, "pr": pr, "tip": None, "utc": utc,
           "utc_ts": utc_ts, "session": None, "for_lane": for_lane}
    return text, row


def landing(c: Clone, lane: str = L1, **options) -> Tuple[str, dict]:
    return line(c, "LANDING", lane, **options)


def hold(c: Clone, lane: str, **options) -> Tuple[str, dict]:
    return line(c, "HOLD", lane, pr=None, **options)


def expired(c: Clone, lane: str = L2, for_lane: str = L1, **options) -> Tuple[str, dict]:
    return line(c, "LANDING EXPIRED", lane, for_lane=for_lane, **options)


@pytest.fixture()
def clones(pg_cluster):
    """Clones of `tmpl_imported`, each the case's own, dropped at the end."""
    made: List[str] = []

    def clone() -> Clone:
        found = pg_cluster.psql(f"SELECT datname FROM pg_database WHERE datname = '{IMPORTED}';").stdout.split()
        assert found == [IMPORTED], f"no {IMPORTED} on the session cluster: lane 2's T227 builds it"
        name = f"t223_{next(_NAMES)}"
        pg_cluster.psql(f"CREATE DATABASE {name} TEMPLATE {IMPORTED};")
        made.append(name)
        pg_cluster.psql(f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
                        f"GRANT CONNECT ON DATABASE {name} TO {CONNECT_TO};\n")
        return Clone(pg_cluster, name)

    yield clone
    for name in made:
        pg_cluster.drop_database(name)


def primary(clones) -> Clone:
    c = clones()
    c.to_primary()
    c.no_taker()
    return c


# ------------------------------------------------------------ F13
def test_a_landing_expired_for_a_stale_landing_commits_and_frees_main_in_main_slots(clones):
    """[stale]: a stale LANDING still takes `main`, so L2's HOLD is refused
    `main-held`; L2's LANDING EXPIRED for L1 commits at the next seq, frees
    `main` in `main_slots` and holds `for_lane` L1; L2's HOLD then commits."""
    c = primary(clones)
    c.write(L1, landing(c, age=40))
    hold_line, hold_row = hold(c, L2)
    c.refused(c.append(L2, hold_line, hold_row), "LR005", "main-held", "(D18)")

    head = c.head()
    seq = c.write(L2, expired(c))
    assert (seq, c.head()) == (head + 1, head + 1)
    assert c.open_takes(L1, "landing") == []
    assert c.value(f"SELECT for_lane FROM {REGISTER}.register_lines WHERE seq = {seq};") == L1
    c.committed(c.append(L2, hold_line, hold_row))
    assert c.open_takes(L2, "hold") == [[KEY, None]]


def test_a_landing_expired_closes_only_the_holders_landings_for_that_pr_and_repository(clones):
    """[closes-only-its-own]: the release for L1's PR closes both of that
    PR's posts, as L1's LANDED would; L1's HOLD, its other PR's LANDING and
    L3's LANDING on another repository stay open, and no LANDED is written."""
    c = primary(clones)
    c.write(L1, hold(c, L1, age=50))
    c.write(L1, landing(c, age=50))
    c.write(L1, landing(c, age=40))
    c.write(L1, landing(c, pr=OTHER_PR, age=40))
    c.write(L3, landing(c, L3, repo=OTHER_KEY, age=40))
    head = c.head()

    c.write(L2, expired(c))
    assert c.open_takes(L1, "landing") == [[KEY, OTHER_PR]]
    assert c.open_takes(L1, "hold") == [[KEY, None]]
    assert c.open_takes(L3, "landing") == [[OTHER_KEY, PR]]
    assert c.value(f"SELECT count(*) FROM {REGISTER}.register_lines WHERE kind = 'LANDED' AND seq > {head};") == "0"


def test_the_holder_may_write_its_own_landing_expired(clones):
    """[holder-writes]: a close is matched by `coalesce(for_lane, lane)`, so
    L1's own LANDING EXPIRED, `for_lane` L1, commits and frees `main`."""
    c = primary(clones)
    c.write(L1, landing(c, age=40))
    seq = c.write(L1, expired(c, L1, for_lane=L1))
    assert seq == c.head()
    assert c.open_takes(L1, "landing") == []


def _imported_take(c: Clone) -> dict:
    """Test 7's imported LANDING whose UTC cannot be read, still open."""
    takes = c.json(f"SELECT coalesce(json_agg(json_build_object('lane', t.lane, 'pr', t.pr, 'key', t.repo_key, "
                   f"'spellings', t.repo_spellings, 'line_id', t.line_id) ORDER BY t.line_id), '[]') "
                   f"FROM {REGISTER}.register_lines t JOIN {REGISTER}.main_slots m ON m.line_id = t.line_id "
                   f"WHERE t.slot_role = 'take' AND t.slot_kind = 'landing' AND t.utc_ts IS NULL;")
    assert takes, f"{IMPORTED} holds no open LANDING whose UTC cannot be read (test 7's register; T227)"
    take = takes[-1]
    newer = c.value(f"SELECT count(*) FROM {REGISTER}.register_lines WHERE slot_role = 'take' "
                    f"AND slot_kind = 'landing' AND lower(lane) = lower('{take['lane']}') AND pr = {take['pr']} "
                    f"AND line_id > {take['line_id']};")
    assert newer == "0", f"a newer LANDING follows the imported one: {take}"
    return take


def _setup(c: Clone, case: str) -> Tuple[str, dict, str, Tuple[str, ...]]:
    """Each case's lines, then the LANDING EXPIRED it sends, its token and
    what its message says."""
    young = ("is too young (F13)", "its age by the database's clock is ")
    if case == "fresh":
        c.write(L1, landing(c, age=0))
        return (*expired(c), "expired-young", young)
    if case == "posted-again":
        c.write(L1, landing(c, age=40))
        c.write(L1, landing(c, age=10))
        return (*expired(c), "expired-young", young)
    if case in ("posted-again-two-spellings", "newest-keyed-another-way"):
        c.write(L1, landing(c, key=KEY, spellings=BOTH, age=40))
        c.write(L1, landing(c, repo=ALIAS, key=ALIAS, spellings=BOTH, age=10))
        if case == "posted-again-two-spellings":
            return (*expired(c, repo=ALIAS, key=ALIAS, spellings=BOTH), "expired-young", young)
        return (*expired(c, key=KEY, spellings=BOTH), "expired-none",
                (f"no open LANDING by {L1} for PR #{PR} under repo_key {KEY} (F13)",
                 f"its newest is keyed {ALIAS}"))
    if case == "unreadable-utc":
        take = _imported_take(c)
        text, row = expired(c, for_lane=take["lane"], pr=take["pr"], repo=take["key"], key=take["key"],
                            spellings=take["spellings"])
        return text, row, "expired-young", ("is too young (F13)",
                                            "is unknown, since its UTC cannot be read")
    if case == "wrong-lane":
        c.write(L1, landing(c, age=40))
        return (*expired(c, for_lane=L3), "expired-none",
                (f"no open LANDING by {L3} for PR #{PR} under repo_key {KEY} (F13)",))
    if case == "wrong-pr":
        c.write(L1, landing(c, age=40))
        return (*expired(c, pr=OTHER_PR), "expired-none",
                (f"no open LANDING by {L1} for PR #{OTHER_PR} under repo_key {KEY} (F13)",))
    if case == "other-spelling":
        c.write(L1, landing(c, key=KEY, spellings=BOTH, age=40))
        return (*expired(c, repo=ALIAS, key=ALIAS, spellings=BOTH), "expired-none",
                (f"under repo_key {ALIAS} (F13)", f"its newest is keyed {KEY}"))
    if case == "already-closed":
        c.write(L1, landing(c, age=40))
        c.write(L1, line(c, "LANDED", L1, age=20))
        return (*expired(c), "expired-closed", (f"is already closed, by a LANDED of {L1} (F13)",))
    if case == "closed-under-another-spelling":
        c.write(L1, landing(c, key=KEY, spellings=BOTH, age=40))
        c.write(L1, line(c, "LANDED", L1, repo=ALIAS, key=ALIAS, spellings=BOTH, age=20))
        return (*expired(c, key=KEY, spellings=BOTH), "expired-closed",
                (f"is already closed, by a LANDED of {L1} (F13)",))
    if case == "already-released":
        c.write(L1, landing(c, age=40))
        c.write(L2, expired(c))
        return (*expired(c), "expired-closed", (f"is already closed, by a LANDING EXPIRED of {L2} (F13)",))
    raise AssertionError(case)


@pytest.mark.parametrize("case", [
    "fresh", "posted-again", "posted-again-two-spellings", "unreadable-utc",
    "wrong-lane", "wrong-pr", "other-spelling", "newest-keyed-another-way",
    "already-closed", "closed-under-another-spelling", "already-released",
])
def test_a_landing_expired_that_names_no_stale_landing_is_lr005_and_writes_nothing(clones, case):
    """Each of F13's eleven: LR005, its reason's token (`expired-young`,
    `expired-none`, `expired-closed`) and nothing written."""
    c = primary(clones)
    text, row, token, says = _setup(c, case)
    lines = c.refused(c.append(L2, text, row), "LR005", token, *says)
    if case == "fresh":
        assert "unknown" not in lines[0], lines[0]


# ------------------------------------------------------------ U3
@pytest.mark.parametrize("case", ["hold", "landing", "bad-stamp", "behind-d18"])
def test_on_primary_a_take_with_no_readable_utc_is_lr005_take_no_utc_and_writes_nothing(clones, case):
    """On primary a take whose UTC cannot be read is LR005 `take-no-utc`,
    the message quoting its line; behind another lane's HOLD it is still
    `take-no-utc`, not `main-held`, since U3's test comes first."""
    c = primary(clones)
    if case == "behind-d18":
        c.write(L1, hold(c, L1, age=0))
    if case in ("hold", "behind-d18"):
        text, row = hold(c, L2, age=None)
        kind = "HOLD"
    else:
        text, row = landing(c, L2, age=None, stamp=BAD_STAMP if case == "bad-stamp" else None)
        kind = "LANDING"
    if case == "bad-stamp":
        assert BAD_STAMP in text and row["utc_ts"] is None
    c.refused(c.append(L2, text, row), "LR005", "take-no-utc",
              f"a {kind} take with no readable UTC (U3): {text}")


@pytest.mark.parametrize("case", ["hold-refresh", "no-kind", "import-at-files"])
def test_a_refresh_or_a_line_of_no_kind_with_no_utc_commits_and_a_take_with_none_loads_at_files(clones, case):
    """A `HOLD (refresh)` with no UTC takes nothing and a line of no kind is
    no take, so each commits on primary; at `files`, before the clone's
    cutover, an `import` carrying the takes with no UTC commits, each line
    loaded as it stands, since U3 binds only a write on primary."""
    if case != "import-at-files":
        c = primary(clones)
        kind = "HOLD (refresh)" if case == "hold-refresh" else None
        text = f"HOLD (refresh) — lane {L2} — {KEY} main" if kind else f"HOLD REQUESTED — lane {L2} — {KEY} main"
        text, row = line(c, kind, L2, pr=None, age=None, text=text)
        seq = c.write(L2, (text, row))
        said = c.json(f"SELECT json_build_array(kind, slot_role, utc_ts, mode) FROM {REGISTER}.register_lines "
                      f"WHERE seq = {seq};")
        assert said == [kind, None, None, "primary"], said
        return

    c = clones()
    sw = c.switch()
    assert (sw["mode"], sw["marker_state"]) == ("files", "absent"), sw
    takes = [hold(c, L2, age=None), landing(c, L2, age=None), landing(c, L3, age=None, stamp=BAD_STAMP)]
    edits, files, _ = c.appended(LANES_MD, [t for t, _ in takes], create=True)
    rows = [dict(row, path=LANES_MD, line_no=n, raw=text, workstation=WS)
            for n, (text, row) in enumerate(takes, start=1)]
    seq = c.committed({"journal": c.journal("import", "import", OPERATOR, git_commit=GIT_COMMIT, git_tree=GIT_TREE),
                       "not_after": c.not_after(), "edits": edits, "files": files, "register_lines": rows})
    said = c.json(f"SELECT json_agg(json_build_array(kind, slot_role, utc, utc_ts, mode, raw) ORDER BY line_id) "
                  f"FROM {REGISTER}.register_lines WHERE seq = {seq};")
    assert said == [[r["kind"], "take", r["utc"], None, "files", r["raw"]] for r in rows], said


# ------------------------------------------------------------ the table's checks
@pytest.mark.parametrize("case", ["for-lane-on-a-hold", "no-for-lane", "closes-a-hold"])
def test_the_for_lane_checks_refuse_a_for_lane_off_a_landing_expired_and_a_landing_expired_that_closes_no_landing(
        clones, case):
    """`register_lines`' CHECKs: `for_lane` on a line of another kind, a
    LANDING EXPIRED with none, and one that closes a HOLD are each 23514 at
    the insert, and the whole entry rolls back."""
    c = primary(clones)
    if case == "for-lane-on-a-hold":
        text, row = hold(c, L2)
        row["for_lane"] = L1
    elif case == "no-for-lane":
        text, row = expired(c, for_lane=None)
        row["for_lane"] = None
    else:
        c.write(L1, hold(c, L1, age=0))
        text, row = expired(c, pr=None, slot=("close", "hold"))
    c.refused(c.append(L2, text, row), "23514", None,
              'new row for relation "register_lines" violates check constraint')


# ============================================================ PHASE W: test 4, C10, D19 and 4.1 (T243)
#
# THE CLIENT'S WRITERS ON A REAL REGISTER (AT-4's fixture, TP:876-898). Each
# case's register is a clone of `tmpl` (T227), brought by AT-LR006's route, as
# T222f's cases bring theirs: an `import` entry at seq 0 holding the case's
# files (`Clone.import_files`), then `Clone.to_primary`'s `cutover` entry at
# seq 1 and `record_marker`, so the first write is seq 2 and the objects are
# free. The workstation (`Estate`):
#   * one configuration at `mode=primary`, naming the clone through T228's
#     `lanes_w_fx`, and one `XDG_STATE_HOME`, so every writer shares one
#     `lanes-index` state directory and one image cache, `register-images/`;
#   * T203's flipped copy of `lanes-index` beside `lanes-edit.sh`,
#     `repos.tsv` and `lane-start`;
#   * a bare origin at the register's files with `lanes/repos.tsv` beside
#     them, and one checkout per writer (a reading: AT-4 names one
#     configuration, and the writers' git fetches are kept off one index);
#   * a fake `gh` that logs each call with its body (AT-D8's form);
#   * per writer, a `psql` directory of its own: a stamp wrapper, which logs
#     each call's start time, in front of T203's shim (section 3.2), so each
#     writer's arms, log and counters are its own;
#   * the start barrier: each writer is launched through a launcher that blocks
#     on a FIFO the test opens only once all N launchers wait (TP:886-888).
# The window W is the shim's `window` arm on `commit_write`, the attempt's
# second call (TP:889-893). Lines are written by the client's own verbs.
#
# They FAIL UNTIL lane 1's T107 (L1-A6), lane 4's attempt loop on primary
# (L4-B3) and `claim`'s register seq (L4-B8), lane 1's T302 (the image cache),
# and lane 2's T227 (`tmpl`) and T228 (`lanes_w_fx`) land. Without PostgreSQL
# 16 each skips.

EM, ARROW, DOT = chr(0x2014), chr(0x2192), chr(0x00B7)
W_TEMPLATE = "tmpl"
W_WS = "Eagle"
REPOS_PATH = "lanes/repos.tsv"
#: Test 4's lanes: ten burst writers, and the pairs of C10, D19 and (a)-(h).
BURST = [f"repoW{k:02d}-1" for k in range(1, 11)]
LA, LB, LC = "repoA-1", "repoB-1", "repoC-1"
W_LANES = [LA, LB, LC, *BURST]
#: Object O, and X: X's repository becomes an alias of O's at T1 (C10, D19).
ALIAS_REPO = "oldname/r9"
OBJ = f"{KEY}#41"
OBJ_X = f"{ALIAS_REPO}#41"
REPOS_T0 = f"# alias\towner/repo\n{ALIAS}\t{KEY}\n"
REPOS_T1 = REPOS_T0 + f"{ALIAS_REPO}\t{KEY}\n"
#: The busy text's words (D7; P231-233) and the default's (AT-4 (h)).
BUSY_WORDS = ("register busy", "nothing", "retry")
D7_S, TWICE_D7_S = 30, 60
UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
SEQ_SAID = re.compile(r"register seq ([0-9]+)")


def session_of(lane: str) -> str:
    k = int(hashlib.sha256(lane.encode()).hexdigest()[:8], 16)
    return f"{k:08x}-0243-4000-8000-{k:012x}"


def w_row(lane: str) -> str:
    return (f"| `{lane}` | harness `{session_of(lane)}` | {W_WS} / test / brett | 2026-05-01T00:00Z "
            f"| none | handoffs/{lane}.md | LIVE {DOT} 2026-05-01T00:00:00Z {DOT} working |")


def estate_files(lanes: Sequence[str]) -> Dict[str, str]:
    """The register's render set: a row per lane, an empty event list, the
    aliases table and a log per lane."""
    table = "\n".join([f"# LANES.md {EM} test 4's register (T243)", "",
                       "| lane | session id | workstation / env / user | started (UTC) "
                       "| objects owned | handoff path | state |",
                       "|---|---|---|---|---|---|---|", *(w_row(lane) for lane in lanes), ""])
    files = {LANES_MD: table, "lanes/aliases.tsv": "# old\tnew\tutc\n",
             "lanes/log/README.md": "# the object logs\n"}
    for lane in lanes:
        files[f"lanes/log/{lane}.md"] = f"# lane {lane} {EM} object log (Amendment 7)\n"
    return files


def import_files(c: "Clone", files: Dict[str, str]) -> int:
    """AT-LR006's first step on a clone of `tmpl` (T222f's `Clone.imported`):
    one `import` entry creating `files`, each with its last LF."""
    sw = c.switch()
    assert (sw["mode"], sw["marker_state"], c.head()) == ("files", "absent", -1), (
        f"a clone of {W_TEMPLATE} is not at files, marker absent, with an empty journal: {sw}, head {c.head()}")
    edits, rows = [], []
    for path in sorted(p for p in files if p != "lanes/log/README.md"):
        lines = files[path].rstrip("\n").split("\n")
        edits.append({"ord": len(edits) + 1, "op": "create", "path": path})
        edits += [{"ord": len(edits) + 1 + k, "op": "append", "path": path, "new_text": text}
                  for k, text in enumerate(lines)]
        rows.append({"path": path, "present": True, "final_newline": True,
                     "sha256": sha256(rendered(lines, True))})
    return c.committed({"journal": c.journal("import", "import", OPERATOR, git_commit=GIT_COMMIT,
                                             git_tree=GIT_TREE),
                        "not_after": c.not_after(), "edits": edits, "files": rows})


def run_git(cwd, *args: str, env: dict) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env,
                          check=False)
    assert proc.returncode == 0, f"git {' '.join(args)} in {cwd}: {proc.stderr}{proc.stdout}"
    return proc.stdout


_STAMP = r'''#!/usr/bin/env python3
# T243's stamp: each psql call's start time and argv, then T203's shim.
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "stamps.log"), "a", encoding="utf-8") as log:
    log.write(json.dumps({"t": time.time(), "argv": sys.argv[1:]}) + "\n")
shim = os.path.join(HERE, "shim", "psql")
os.execv(shim, [shim] + sys.argv[1:])
'''

_LAUNCHER = r'''#!/usr/bin/env python3
# T243's start barrier: wait on the FIFO, then become the writer.
import os, sys
ready, fifo, argv = sys.argv[1], sys.argv[2], sys.argv[3:]
open(ready, "w").close()
fd = os.open(fifo, os.O_RDONLY)
open(ready + ".go", "w").close()
os.close(fd)
os.execvp(argv[0], argv)
'''

_GH = r'''#!/usr/bin/env python3
# AT-D8's fake gh (T243): each call logged with its body; nothing answered.
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
body = sys.stdin.read() if not sys.stdin.isatty() else ""
with open(os.path.join(HERE, "gh.log"), "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "stdin": body}) + "\n")
'''


class Barrier:
    """TP:886-888: N launchers wait on one FIFO, released together."""

    def __init__(self, root: Path, count: int) -> None:
        self.fifo, self.ready, self.count = root / "start.fifo", root / "ready", count
        os.mkfifo(str(self.fifo))
        self.ready.mkdir()

    def _seen(self, suffix: str) -> int:
        return sum(1 for p in self.ready.iterdir() if p.name.endswith(".go") == (suffix == ".go"))

    def release(self) -> float:
        deadline = time.monotonic() + 60
        while self._seen("") < self.count:
            assert time.monotonic() < deadline, f"only {self._seen('')} of {self.count} launchers wait"
            time.sleep(0.05)
        fd = os.open(str(self.fifo), os.O_WRONLY)
        released = time.monotonic()
        while self._seen(".go") < self.count:
            assert time.monotonic() < deadline + 30, f"only {self._seen('.go')} launchers passed"
            time.sleep(0.01)
        os.close(fd)
        return released


class Writer:
    """One `lanes-edit.sh` run: its psql directory, and its outcome."""

    def __init__(self, name: str, lane: str, proc: subprocess.Popen, psql_dir: Path) -> None:
        self.name, self.lane, self.proc, self.psql_dir = name, lane, proc, psql_dir
        self.started, self.ended = time.monotonic(), None
        self.out = self.err = ""
        self._thread = threading.Thread(target=self._wait, daemon=True)
        self._thread.start()

    def _wait(self) -> None:
        self.out, self.err = self.proc.communicate()
        self.ended = time.monotonic()

    def wait(self, timeout: float = 150) -> int:
        self._thread.join(timeout)
        assert not self._thread.is_alive(), f"{self.name} ({self.lane}) did not end in {timeout} s"
        return self.proc.returncode

    @property
    def code(self) -> int:
        return self.proc.returncode

    def _jsonl(self, name: str) -> List[dict]:
        path = self.psql_dir / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def calls(self) -> List[dict]:
        """The shim's calls that carry a request, in order."""
        return [e for e in self._jsonl("shim/" + PSQL_SHIM_LOG) if e.get("kind") != "version"]

    def commit_calls(self) -> List[dict]:
        return [e for e in self.calls() if "commit_write" in (e.get("stdin") or "")]

    def snapshot_calls(self) -> List[dict]:
        return [e for e in self.calls() if "commit_write" not in (e.get("stdin") or "")
                and "find_write" not in (e.get("stdin") or "")]

    def ends(self) -> Dict[int, dict]:
        return {e["call"]: e for e in self._jsonl("shim/" + PSQL_SHIM_ENDS) if "call" in e}

    def stamps(self) -> List[dict]:
        """Each request's start time, paired in order with the shim's log."""
        times = [s["t"] for s in self._jsonl("stamps.log") if s["argv"] != ["--version"]]
        return [dict(call, t=t) for call, t in zip(self.calls(), times)]

    def write_ids(self) -> List[str]:
        """Each commit call's write id, `commit_write`'s second argument."""
        found = []
        for call in self.commit_calls():
            m = re.search(r"commit_write\(\s*-?[0-9]+\s*,\s*'(" + UUID_RE + ")'", call.get("stdin") or "")
            assert m, f"{self.name}'s commit call carries no write id: {(call.get('stdin') or '')[:300]}"
            found.append(m.group(1))
        return found

    def seq_said(self) -> Optional[int]:
        m = SEQ_SAID.search(self.out)
        return int(m.group(1)) if m else None


class Estate:
    """Test 4's workstation over one clone at `primary` (see the section's
    head)."""

    def __init__(self, root: Path, c: Clone, lanes: Sequence[str] = W_LANES,
                 repos: str = REPOS_T0, aliases: str = "") -> None:
        self.root, self.c = root, c
        self.files = estate_files(lanes)
        self.files["lanes/aliases.tsv"] += aliases
        import_files(c, self.files)
        assert c.to_primary() == 1, "test 4's cutover is not at seq 1 (AT-4's fixture)"
        home = root / "home"
        (home / ".agents").mkdir(parents=True)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GIT_", "PG", "LANES_", "TMUX", "RULE6_", "FAKE_PSQL", "CLAUDE_",
                                    "PROJECTS_ROOT", "XDG_"))}
        env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME="T243 estate", GIT_AUTHOR_EMAIL="t243@example.invalid",
                   GIT_COMMITTER_NAME="T243 estate", GIT_COMMITTER_EMAIL="t243@example.invalid",
                   LC_ALL="C")
        self.env = env
        self.origin = root / "origin.git"
        run_git(root, "init", "-q", "--bare", "-b", "main", str(self.origin), env=env)
        seed = root / "seed"
        run_git(root, "clone", "-q", str(self.origin), str(seed), env=env)
        for path, text in {**self.files, REPOS_PATH: repos}.items():
            (seed / path).parent.mkdir(parents=True, exist_ok=True)
            (seed / path).write_bytes(text.encode("utf-8"))
        run_git(seed, "add", "-A", env=env)
        run_git(seed, "commit", "-q", "-m", "T0: test 4's register", env=env)
        run_git(seed, "push", "-q", "origin", "main", env=env)
        self.seed = seed
        self.bindir = root / "bin"
        flipped_copy(LANES_INDEX, self.bindir, True)
        for name in ("lanes-edit.sh", "repos.tsv", "lane-start"):
            shutil.copy2(str(REPO / name), str(self.bindir / name))
        self.lanes_edit = self.bindir / "lanes-edit.sh"
        conf = root / "lanes-index.conf"
        conf.write_text(f"mode=primary\nregister_url={c.db.url(WRITER_LOGIN)}\n"
                        f"reader_url={c.db.url()}\n", encoding="utf-8")
        conf.chmod(0o600)
        self.gh_dir = root / "gh"
        self.gh_dir.mkdir()
        (self.gh_dir / "gh").write_text(_GH, encoding="utf-8")
        (self.gh_dir / "gh").chmod(0o755)
        (self.gh_dir / "tmux").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        (self.gh_dir / "tmux").chmod(0o755)
        self.launcher = root / "launch.py"
        self.launcher.write_text(_LAUNCHER, encoding="utf-8")
        self.state = root / "state"
        for d in ("state", "config", "tmp"):
            (root / d).mkdir(exist_ok=True)
        path = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                               if p and not os.path.exists(os.path.join(p, "lanes-index"))
                               and not os.path.exists(os.path.join(p, "psql")))
        env.update(TMPDIR=str(root / "tmp"), XDG_STATE_HOME=str(self.state),
                   XDG_CONFIG_HOME=str(root / "config"), CLAUDE_CONFIG_DIR=str(home / ".claude"),
                   LANES_WORKSTATION=W_WS, LANES_HOST="eagle", LANES_OS="linux",
                   LANES_CONTAINER="none", LANES_IN_CONTAINER="0", LANES_INDEX_CONFIG=str(conf),
                   PATH=str(self.gh_dir) + os.pathsep + path)
        self._n = itertools.count(1)
        self.writers: List[Writer] = []

    # -------------------------------------------------- the workstation's parts
    def checkout(self, name: str, origin: Optional[Path] = None) -> Tuple[Path, Path]:
        """A clone of the origin, and the protocol root naming it."""
        where = self.root / f"co-{name}"
        run_git(self.root, "clone", "-q", str(origin or self.origin), str(where), env=self.env)
        agents = self.root / f"agents-{name}"
        agents.mkdir()
        (agents / "workspace.yaml").write_text(f"repository: {origin or self.origin}\npath: {where}\n",
                                               encoding="utf-8")
        return where, agents

    def psql_dir(self, name: str, arms: Sequence[dict] = ()) -> Path:
        where = self.root / f"psql-{name}"
        (where / "shim").mkdir(parents=True)
        (where / "psql").write_text(_STAMP, encoding="utf-8")
        (where / "psql").chmod(0o755)
        (where / "shim" / "psql").write_text(PSQL_SHIM, encoding="utf-8")
        (where / "shim" / "psql").chmod(0o755)
        (where / "shim" / PSQL_SHIM_CONTROL).write_text(
            json.dumps({"psql": self.c.db.psql_bin, "arms": list(arms)}), encoding="utf-8")
        return where

    def push_alias(self) -> None:
        """T1: a person's commit adding X's repository as an alias of O's,
        pushed by a third clone (AT-C10's fixture)."""
        (self.seed / REPOS_PATH).write_text(REPOS_T1, encoding="utf-8")
        run_git(self.seed, "commit", "-q", "-am", "T1: alias oldname/r9 for opensoft/r9", env=self.env)
        run_git(self.seed, "push", "-q", "origin", "main", env=self.env)

    def mirror_at_t0(self) -> Path:
        """A second origin frozen at T0, for a clone kept behind the alias."""
        frozen = self.root / "origin-t0.git"
        run_git(self.root, "clone", "-q", "--bare", str(self.origin), str(frozen), env=self.env)
        return frozen

    # -------------------------------------------------- running writers
    def launch(self, lane: str, argv: Sequence[str], arms: Sequence[dict] = (), extra: dict = None,
               barrier: Optional[Barrier] = None, origin: Optional[Path] = None,
               first: Sequence[Path] = (), script: Optional[Path] = None) -> Writer:
        name = f"{next(self._n):02d}-{lane}"
        where, agents = self.checkout(name, origin)
        psql = self.psql_dir(name, arms)
        env = dict(self.env)
        env.update(LANES_LANE=lane, LANES_SESSION=session_of(lane), LANES_REPO=str(where),
                   AGENT_PROTOCOL_ROOT=str(agents),
                   PATH=os.pathsep.join([*map(str, first), str(psql), self.env["PATH"]]))
        env.update(extra or {})
        command = ["bash", str(script or self.lanes_edit), *argv]
        if barrier is not None:
            command = [sys.executable, "-I", str(self.launcher), str(barrier.ready / name),
                       str(barrier.fifo), *command]
        proc = subprocess.Popen(command, cwd=str(where), env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                                errors="replace", start_new_session=True)
        writer = Writer(name, lane, proc, psql)
        self.writers.append(writer)
        return writer

    def run(self, lane: str, argv: Sequence[str], **options) -> Writer:
        writer = self.launch(lane, argv, **options)
        writer.wait()
        return writer

    def gh_calls(self) -> List[dict]:
        log = self.gh_dir / "gh.log"
        return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l] if log.exists() else []

    # -------------------------------------------------- the register's reads
    def rows(self, query: str) -> list:
        return self.c.json(f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({query}) t;")

    def journal_after(self, seq: int = 1) -> list:
        return self.rows(f"SELECT seq, write_id::text AS write_id, verb, lane FROM {REGISTER}.journal "
                         f"WHERE seq > {seq} ORDER BY seq")

    def has_write(self, write_id: str) -> bool:
        return self.c.value(f"SELECT count(*) FROM {REGISTER}.journal WHERE write_id = '{write_id}';") != "0"

    def claimed(self, *objects: str) -> list:
        """The live `CLAIMED` holds on `objects`, (object, lane)."""
        names = ", ".join(f"'{o}'" for o in objects)
        return [(r["object"], r["lane"]) for r in self.rows(
            f"SELECT object, lane FROM {REGISTER}.object_holds WHERE object IN ({names}) "
            f"AND verb = 'CLAIMED' AND superseded_by IS NULL ORDER BY object, lane")]

    def log_lines(self, verb: str, obj: str) -> int:
        return int(self.c.value(f"SELECT count(*) FROM {REGISTER}.log_lines WHERE verb = '{verb}' "
                                f"AND object = '{obj}';"))

    def utc(self, minutes_ago: float = 0) -> str:
        return self.c.value("SELECT to_char((clock_timestamp() - make_interval(secs => "
                            f"{minutes_ago * 60})) AT TIME ZONE 'UTC', "
                            "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"');")

    def open_slots(self, lane: str) -> List[List]:
        return [[r["slot_kind"], r["repo_key"], r["pr"]] for r in self.rows(
            f"SELECT slot_kind, repo_key, pr FROM {REGISTER}.main_slots WHERE lane = '{lane}' "
            "ORDER BY line_id")]

    def hold_row_locked(self) -> subprocess.Popen:
        """The test's admin session holding the head row `FOR UPDATE` in an
        open transaction, as AT-D9's F3 row does."""
        admin = self.c.db.session(appname="t243-admin")
        admin.stdin.write(f"BEGIN;\nSELECT seq FROM {REGISTER}.register_head FOR UPDATE;\n")
        admin.stdin.flush()
        said = admin.stdout.readline().strip()
        assert said.isdigit(), f"the admin session did not lock the head row: {said!r}"
        return admin

    @staticmethod
    def unlock(admin: subprocess.Popen) -> None:
        admin.stdin.write("ROLLBACK;\n")
        admin.stdin.close()
        admin.wait(timeout=30)

    def waits_on_lock(self, write_id: str) -> bool:
        """D19's barrier: the backend whose query carries `write_id` waits on
        a lock, polled at 0.1 s steps under one 1.5 s ceiling."""
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            if self.c.value("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                            f"AND query LIKE '%{write_id}%';") != "0":
                return True
            time.sleep(0.1)
        return False


@pytest.fixture()
def estates(pg_cluster, tmp_path):
    """Test 4's estates, each on a clone of `tmpl` of its own."""
    made: List[str] = []
    alive: List[Estate] = []

    def make(**options) -> Estate:
        name = f"t243_{next(_NAMES)}"
        pg_cluster.psql(f"CREATE DATABASE {name} TEMPLATE {W_TEMPLATE};")
        made.append(name)
        found = pg_cluster.psql(f"SELECT to_regclass('{REGISTER}.register_head') IS NOT NULL;", dbname=name)
        assert found.stdout.strip() == "t", (
            f"{W_TEMPLATE} holds no {REGISTER} schema: lane 2's T227 builds it by the bootstrap")
        pg_cluster.psql(f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
                        f"GRANT CONNECT ON DATABASE {name} TO {CONNECT_TO};\n")
        root = tmp_path / f"estate-{len(made)}"
        root.mkdir()
        alive.append(Estate(root, Clone(pg_cluster, name), **options))
        return alive[-1]

    yield make
    for e in alive:
        for w in e.writers:
            if w.ended is None and w.proc.poll() is None:
                os.killpg(w.proc.pid, 9)
    for name in made:
        pg_cluster.drop_database(name)


def hold_point(fifo: Path, writer: Writer, timeout: float = 90):
    """`fifo` opened for writing once `writer`'s call is held on it (the
    shim's `hold`), bounded: a writer that never reaches the call fails the
    case and never hangs it. Closing the handle lets the call go."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return os.fdopen(os.open(str(fifo), os.O_WRONLY | os.O_NONBLOCK), "wb")
        except OSError as error:
            if error.errno != errno.ENXIO:
                raise
        assert writer.ended is None, (
            f"{writer.name} exited {writer.code} before its commit call was held: {writer.err[-400:]}")
        assert time.monotonic() < deadline, f"{writer.name}'s commit call was not held in {timeout} s"
        time.sleep(0.05)


CLIENT = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                            reason="the lane tooling is bash over git")
WINDOW = {"mode": "window", "match": "commit_write", "ms": 200}


def claim(obj: str, *more: str) -> List[str]:
    return ["claim", obj, "--home", KEY, *more]


def burst(e: Estate, objects: Sequence[str], window_ms: int, extra: dict = None) -> Tuple[List[Writer], float]:
    """Writers on `objects`, one lane each, released together; returns them,
    and the drain from the release to the last exit."""
    barrier = Barrier(e.root, len(objects))
    arms = [dict(WINDOW, ms=window_ms)]
    writers = [e.launch(lane, claim(obj, "--no-github"), arms=arms, barrier=barrier, extra=extra)
               for lane, obj in zip(BURST, objects)]
    released = barrier.release()
    for w in writers:
        w.wait()
    return writers, max(w.ended for w in writers) - released


def record(name: str, **figures) -> None:
    """A figure recorded beside the result, never asserted (TP:7556-7559)."""
    print(f"[T243 {name}] " + ", ".join(f"{k}={v}" for k, v in figures.items()))


@CLIENT
def test_two_claimants_one_claimed_and_the_other_exits_2(estates):
    """AT-4 (a): two lanes claim O through the barrier, W = 200 ms. One
    `CLAIMED`, in the journal and the line store; exits {0, 2}; the journal
    grew by one; the loser's write id is absent; no `CLAIM-LOST`; the winner
    prints `register seq <n>`, its entry's seq, and the claim comment its
    tail posts through the fake `gh` cites the same `<n>`."""
    e = estates()
    barrier = Barrier(e.root, 2)
    writers = [e.launch(lane, claim(OBJ), arms=[WINDOW], barrier=barrier) for lane in (LA, LB)]
    barrier.release()
    codes = sorted(w.wait() for w in writers)
    assert codes == [0, 2], [(w.lane, w.code, w.err[-400:]) for w in writers]
    win, lose = sorted(writers, key=lambda w: w.code)
    grew = e.journal_after()
    assert [(r["verb"], r["lane"]) for r in grew] == [("claim", win.lane)], grew
    assert e.claimed(OBJ) == [(OBJ, win.lane)]
    assert e.log_lines("CLAIMED", OBJ) == 1
    assert all(not e.has_write(w) for w in lose.write_ids()), "the loser's write id is in the journal"
    assert e.c.value(f"SELECT count(*) FROM {REGISTER}.doc_lines WHERE text LIKE '%CLAIM-LOST%';") == "0"
    seq = grew[0]["seq"]
    assert win.seq_said() == seq, f"the winner printed {win.seq_said()}, its entry is seq {seq}: {win.out!r}"
    cites = [g for g in e.gh_calls() if f"register seq {seq}" in json.dumps(g)]
    assert cites, f"no claim comment through gh cites register seq {seq}: {e.gh_calls()}"


@CLIENT
def test_the_later_hold_exits_2_and_prints_the_earlier_line(estates):
    """AT-4 (b): two `HOLD`s on one repository's `main`, through the barrier.
    The journal grew by one, the first writer's `HOLD`; it exits 0; the
    second exits 2, writes nothing, and its stderr carries the earlier line
    verbatim with its register seq (D18)."""
    e = estates()
    texts = {lane: f"HOLD {EM} lane {lane} ({W_WS}), {e.utc()}: {KEY} main for T243's case (b)"
             for lane in (LA, LB)}
    barrier = Barrier(e.root, 2)
    writers = [e.launch(lane, ["append-line", texts[lane]], arms=[WINDOW], barrier=barrier)
               for lane in (LA, LB)]
    barrier.release()
    for w in writers:
        w.wait()
    grew = e.journal_after()
    assert len(grew) == 1, grew
    first = next(w for w in writers if w.lane == grew[0]["lane"])
    later = next(w for w in writers if w is not first)
    assert (first.code, later.code) == (0, 2), [(w.lane, w.code, w.err[-400:]) for w in writers]
    assert texts[first.lane] in later.err, f"the later HOLD's stderr lacks the earlier line: {later.err!r}"
    assert re.search(rf"\bseq {grew[0]['seq']}\b", later.err), f"no register seq in {later.err!r}"
    assert all(not e.has_write(w) for w in later.write_ids())


@CLIENT
def test_ten_writers_released_together_all_commit_in_order(estates):
    """AT-4 (c), section 4.1's oracle: ten writers on ten free objects, W =
    200 ms, `LANES_REGISTER_DEADLINE_S` unset (D7's 30 s). All exit 0, none
    75 or 69; seqs 2 to 11, no gap and no repeat; ten distinct write ids; one
    `CLAIMED` per object; the head reads 11. The drain is asserted under 60 s
    and recorded beside D7's 30 s, with each writer's attempts."""
    e = estates()
    objects = [f"{KEY}#{100 + k}" for k in range(10)]
    writers, drain = burst(e, objects, 200)
    assert [w.code for w in writers] == [0] * 10, [(w.lane, w.code, w.err[-300:]) for w in writers]
    grew = e.journal_after()
    assert [r["seq"] for r in grew] == list(range(2, 12)), grew
    assert len({r["write_id"] for r in grew}) == 10
    assert e.claimed(*objects) == sorted(zip(objects, BURST))
    assert e.c.head() == 11
    assert drain < TWICE_D7_S, f"the burst drained in {drain:.1f} s, past twice D7's {D7_S} s"
    record("burst", drain_s=round(drain, 2), margin_vs_30s=round(D7_S / max(drain, 0.01), 2),
           attempts={w.lane: len(w.snapshot_calls()) for w in writers})


@CLIENT
def test_a_write_that_cannot_get_its_turn_exits_75_register_busy(estates):
    """AT-4 (d): two writers on distinct objects, W = 2 s, deadline 1 s. One
    exits 0, the other 75; the busy writer's write id is absent; its stderr
    says nothing was written and a retry in seconds is safe (P231-233)."""
    e = estates()
    barrier = Barrier(e.root, 2)
    writers = [e.launch(lane, claim(obj, "--no-github"), arms=[dict(WINDOW, ms=2000)], barrier=barrier,
                        extra={"LANES_REGISTER_DEADLINE_S": "1"})
               for lane, obj in ((LA, f"{KEY}#51"), (LB, f"{KEY}#52"))]
    barrier.release()
    assert sorted(w.wait() for w in writers) == [0, 75], [(w.lane, w.code, w.err[-400:]) for w in writers]
    busy = next(w for w in writers if w.code == 75)
    assert all(not e.has_write(w) for w in busy.write_ids())
    said = busy.err.lower()
    assert all(word in said for word in BUSY_WORDS), f"the busy text lacks {BUSY_WORDS}: {busy.err!r}"
    assert len(e.journal_after()) == 1


@CLIENT
def test_the_default_deadline_is_30_s_for_a_write_that_never_gets_its_turn(estates):
    """AT-4 (h): `LANES_REGISTER_DEADLINE_S` unset; the admin session holds
    the head row `FOR UPDATE` for the whole case, so each commit call gets
    55P03 at its `lock_timeout`, a lost turn. The writer exits 75, its write
    ids absent, its stderr carrying the busy text with "attempts in 30 s";
    it exits no earlier than 29 s after its launch (timing rule 3) and under
    2 x (30 + 8 + 8) = 92 s, and no snapshot call starts more than 60 s after
    the first (timing rule 2). Both times are recorded against 46 s and
    30 s."""
    e = estates()
    admin = e.hold_row_locked()
    try:
        w = e.run(LA, claim(f"{KEY}#61", "--no-github"))
    finally:
        e.unlock(admin)
    took = w.ended - w.started
    assert w.code == 75, f"exit {w.code}, not 75: {w.err[-600:]}"
    assert w.write_ids() and all(not e.has_write(x) for x in w.write_ids())
    assert "register busy" in w.err.lower() and f"attempts in {D7_S} s" in w.err, w.err
    assert took >= D7_S - 1, f"it exited {took:.1f} s after its launch, before D7's {D7_S} s less 1 s"
    assert took < 2 * (D7_S + 8 + 8), f"it exited {took:.1f} s after its launch, past 92 s"
    starts = [s["t"] for s in w.stamps() if "commit_write" not in (s.get("stdin") or "")]
    spread = max(starts) - min(starts) if starts else 0.0
    assert spread <= TWICE_D7_S, f"a snapshot call started {spread:.1f} s after the first"
    record("default-deadline", exit_s=round(took, 2), vs_46s=round(46 - took, 2),
           snapshot_spread_s=round(spread, 2), vs_30s=round(D7_S - spread, 2), attempts=len(starts))


#: AT-4 (f), with lane 3's text for T243 (#165 6772120103, "T243 (:2232)"):
#: each case's lines before, the line `append-line` sends, and what it must
#: do: refused with 2 and nothing written, or committed with 0, taking or
#: freeing what Q17 (B) says (`main_slots` for the writer's lane).
NO_REPO = {
    "hold-no-repo": ([], "HOLD {em} lane {lane} ({ws}), {utc}: for a frozen window", 2, None),
    "landing-no-repo": ([], "LANDING {em} lane {lane}, session {sid}@{ws}, {utc}, PR #{pr}", 2, None),
    "take-no-utc": ([], "HOLD {em} lane {lane} ({ws}): {key} main for a frozen window", 2, None),
    "free-text": ([], "NOTE {em} lane {lane}: the register's free text (T243)", 0, []),
}

#: Test 4 (f)'s slot lines of another shape, which commit 0 (lane 3,
#: 6771569269: "`append-line` writes these lines on primary ... T424 does not
#: change"), in a function of their own, outside T424's word
#: `hold_line_that_names_no_repository` (lane 3's batch 7, ruling 4). The same
#: columns as `NO_REPO`'s.
OTHER_SHAPE = {
    "landed-no-repo": (["LANDING {em} lane {lane}, session {sid}@{ws}, {utc}, PR #{pr} into {key} main"],
                       "LANDED {em} lane {lane}, session {sid}@{ws}, {utc}, PR #{pr} {arrow} abc1234", 0, []),
    "hold-released-no-repo": (["HOLD {em} lane {lane} ({ws}), {utc}: {key} main for a frozen window"],
                              "HOLD RELEASED {em} lane {lane} ({ws}), {utc}", 0, [["hold", KEY, None]]),
    "landing-no-pr": ([], "LANDING {em} lane {lane}, session {sid}@{ws}, {utc}, into {key} main", 0, []),
}


@CLIENT
@pytest.mark.parametrize("case", list(NO_REPO))
def test_a_hold_line_that_names_no_repository_is_refused_with_2(estates, case):
    """AT-4 (f) (`design.md` S6): on primary, `append-line` with a line
    matching `HOLD ` or `LANDING ` from which no repository can be read exits
    2 and writes nothing, and so does a take whose UTC cannot be read (U3;
    its client half is AT-F13 (b)). A line of another shape is written as free
    text."""
    append_line_case(estates(), case, NO_REPO[case])


@CLIENT
@pytest.mark.parametrize("case", list(OTHER_SHAPE))
def test_a_slot_line_of_another_shape_commits_0(estates, case):
    """Test 4 (f)'s lines of another shape (lane 3, 6771569269): on primary a
    `LANDED` naming no repository commits 0 and frees its pair in
    `main_slots`; a `HOLD RELEASED` naming none and a `LANDING` naming no PR
    commit 0 and take or free nothing. T424's classifier must let them
    through (lane 3's batch 7, ruling 4)."""
    append_line_case(estates(), case, OTHER_SHAPE[case])


def append_line_case(e: Estate, case: str, row: tuple) -> None:
    """One case of test 4 (f): `row`'s lines before, then its line, and its
    exit, and what the register then holds."""
    before_lines, text, code, slots = row

    def spell(form: str) -> str:
        return form.format(em=EM, arrow=ARROW, lane=LA, ws=W_WS, sid=session_of(LA), utc=e.utc(),
                           pr=PR, key=KEY)

    for line_form in before_lines:
        assert e.run(LA, ["append-line", spell(line_form)]).code == 0
    if before_lines:
        assert e.open_slots(LA) == [[("landing" if "LANDING" in before_lines[0] else "hold"), KEY,
                                     PR if "LANDING" in before_lines[0] else None]], e.open_slots(LA)
    head, state = e.c.head(), e.c.state()
    w = e.run(LA, ["append-line", spell(text)])
    assert w.code == code, f"[{case}] exit {w.code}, not {code}: {w.err[-600:]}"
    if code == 2:
        assert e.c.state() == state, f"[{case}] the refusal changed the register"
        assert w.commit_calls() == [], f"[{case}] a commit call was sent"
        return
    assert e.c.head() == head + 1
    said = e.rows(f"SELECT kind, slot_role FROM {REGISTER}.register_lines WHERE seq = {head + 1}")
    role = "close" if case == "landed-no-repo" else None
    assert len(said) == 1 and said[0]["slot_role"] == role, f"[{case}] {said}, its slot_role not {role}"
    assert e.open_slots(LA) == slots, f"[{case}] main_slots for {LA}: {e.open_slots(LA)}, not {slots}"


#: Q17 (B)'s table (lane 1's `REGISTER_SLOTS`, T118): each kind's line, the
#: line before it that it pairs with, and whether `main` is taken after it.
KINDS = {
    "hold": ([], "HOLD", True),
    "hold-refresh": ([], "HOLD (refresh)", False),
    "hold-run-id": ([], "HOLD (run id)", False),
    "hold-released": (["HOLD"], "HOLD RELEASED", False),
    "hold-withdrawn": (["HOLD"], "HOLD WITHDRAWN", False),
    "hold-expired": (["HOLD"], "HOLD EXPIRED", False),
    "queued-hold": ([], "QUEUED-HOLD", False),
    "landing": ([], "LANDING", True),
    "landed": (["LANDING"], "LANDED", False),
    "landing-expired": (["LANDING"], "LANDING EXPIRED", False),
    "landing-withdrawn": ([], "LANDING WITHDRAWN", False),
}


def kind_line(e: Estate, kind: str, lane: str, minutes_ago: float = 0) -> str:
    utc = e.utc(minutes_ago)
    if kind.startswith("LANDING") or kind == "LANDED":
        tail = f" {ARROW} abc1234" if kind == "LANDED" else ""
        return f"{kind} {EM} lane {lane}, session {session_of(lane)}@{W_WS}, {utc}, PR #{PR} into {KEY} main{tail}"
    return f"{kind} {EM} lane {lane} ({W_WS}), {utc}: {KEY} main for T243's table"


@CLIENT
@pytest.mark.parametrize("kind", list(KINDS))
def test_each_line_kind_takes_or_releases_main_as_q17_b_says(estates, kind):
    """After each kind's line, `main_slots` shows `main` taken or released as
    Q17 (B)'s table says, and another lane's `HOLD` then exits 0 or 2 to
    match. `LANDING EXPIRED` is written by AT-F13's form over a `LANDING`
    composed with a UTC 31 minutes back (TP:975-980)."""
    e = estates()
    before, name, taken = KINDS[kind]
    for pair in before:
        ago = 31 if name == "LANDING EXPIRED" else 0
        assert e.run(LA, ["append-line", kind_line(e, pair, LA, ago)]).code == 0
    if name == "LANDING EXPIRED":
        argv = ["append-line", "--landing-expired", LA, "--pr", str(PR), "--repo", KEY,
                "--word", "Release the stale LANDING (Recommended)", "--word-where",
                "lane openRepoTools-2's session", "--word-utc", e.utc(1)]
        w = e.run(LB, argv)
    else:
        w = e.run(LA, ["append-line", kind_line(e, name, LA)])
    assert w.code == 0, f"[{kind}] exit {w.code}: {w.err[-600:]}"
    slots = e.open_slots(LA)
    assert bool(slots) == taken, f"[{kind}] main_slots for {LA}: {slots}"
    other = e.run(LC, ["append-line", kind_line(e, "HOLD", LC)])
    assert other.code == (2 if taken else 0), f"[{kind}] another lane's HOLD exited {other.code}: {other.err[-400:]}"


@CLIENT
def test_claim_prints_its_register_seq(estates):
    """Q19 (A), GB section 4.3 (R29): `claim` prints `register seq <n>`, its
    entry's seq, the first write after the cutover, 2."""
    e = estates()
    w = e.run(LA, claim(OBJ, "--no-github"))
    assert w.code == 0, w.err[-600:]
    grew = e.journal_after()
    assert [(r["seq"], r["verb"]) for r in grew] == [(2, "claim")], grew
    assert w.seq_said() == 2, f"claim printed {w.out!r}"


@CLIENT
def test_a_serialization_failure_is_retried_never_reported_as_69(estates):
    """AT-4 (e): in case (a)'s race the loser's first commit call fails (its
    snapshot predates the winner's commit), and the loser re-runs from the
    pre-check and exits 2, never 69 or 75; its write ids are absent."""
    e = estates()
    barrier = Barrier(e.root, 2)
    writers = [e.launch(lane, claim(OBJ, "--no-github"), arms=[WINDOW], barrier=barrier) for lane in (LA, LB)]
    barrier.release()
    for w in writers:
        w.wait()
    lose = next((w for w in writers if w.code != 0), None)
    assert lose is not None and lose.code == 2, [(w.lane, w.code, w.err[-400:]) for w in writers]
    assert not {69, 75} & {w.code for w in writers}, [w.code for w in writers]
    calls = lose.commit_calls()
    assert calls, "the loser made no commit call: its snapshot did not predate the winner's commit"
    first = lose.ends().get(calls[0]["call"], {})
    assert first.get("psql") not in (None, 0), f"the loser's first commit call did not fail: {first}"
    assert len(lose.snapshot_calls()) >= 2, "the loser did not re-read after its failed commit"
    assert all(not e.has_write(x) for x in lose.write_ids())


def _objects_named(e: Estate) -> Dict[str, Path]:
    objects = e.state / "openRepoTools" / "register-images" / "objects"
    return {p.name: p for p in objects.iterdir()} if objects.exists() else {}


@CLIENT
def test_the_image_cache_stays_content_addressed_under_the_burst_and_a_corrupt_object_is_refetched(estates):
    """AT-4 (g): in the state directory the burst's writers shared, every
    object is named by the sha256 of its bytes and no temporary file is left;
    `head` never decreases in the samples taken during the burst and ends no
    higher than the journal's head; its manifest lists only present objects.
    An object corrupted under its name is not used: the next write exits 0,
    and its render is byte-identical to a full render."""
    e = estates()
    cache = e.state / "openRepoTools" / "register-images"
    samples: List[int] = []
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            try:
                samples.append(int((cache / "head").read_text().strip()))
            except (OSError, ValueError):
                pass
            time.sleep(0.05)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        writers, _ = burst(e, [f"{KEY}#{200 + k}" for k in range(10)], 200)
    finally:
        stop.set()
        sampler.join(5)
    assert [w.code for w in writers] == [0] * 10
    named = _objects_named(e)
    assert named, f"the burst left no object under {cache}"
    for name, path in named.items():
        assert re.fullmatch(r"[0-9a-f]{64}", name), f"a file that is not an object is left: {name}"
        assert sha256(path.read_bytes()) == name, f"{name} is not named by its bytes"
    assert samples == sorted(samples), f"register-images/head went back: {samples}"
    head = int((cache / "head").read_text().strip())
    assert head <= e.c.head()
    listed = [line.split("\t")[1] for line in (cache / "seq" / str(head)).read_text().splitlines() if line]
    assert set(listed) <= set(named), f"manifest {head} lists absent objects: {set(listed) - set(named)}"

    victim = named[listed[0]]
    victim.write_bytes(victim.read_bytes() + b"corrupt\n")
    _, lines = e.c.file(LANES_MD)
    text = f"NOTE {EM} lane {LA}: written after the corrupt object (T243)"
    w = e.run(LA, ["append-line", text])
    assert w.code == 0, f"the write after the corruption exited {w.code}: {w.err[-600:]}"
    nl, after = e.c.file(LANES_MD)
    assert after == [*lines, text]
    digest = e.c.value(f"SELECT sha256 FROM {REGISTER}.files WHERE path = '{LANES_MD}';")
    assert digest == sha256(rendered(after, bool(nl))), "the render after the corruption is not a full render's"


@CLIENT
@pytest.mark.parametrize("order", ["alias-holder-first", "behind-the-alias-first"])
def test_an_alias_edit_racing_a_claim_cannot_let_two_claims_of_one_object_pass(estates, order):
    """AT-C10, both orders. [alias-holder-first]: A, at T0, claims O and is
    held at its commit call; T1 adds X as O's alias; B claims X and commits;
    A, released, loses its turn, and its next snapshot's pre-check refuses it
    with 2: one commit call from A. [behind-the-alias-first]: A, at T0,
    claims X and commits; after T1, B claims O and is refused LR005
    `claim-spellings` on its commit call, its write id absent."""
    e = estates()
    if order == "alias-holder-first":
        fifo = e.root / "hold-a.fifo"
        os.mkfifo(str(fifo))
        a = e.launch(LA, claim(OBJ, "--no-github"),
                     arms=[{"mode": "hold", "match": "commit_write", "call": 1, "fifo": str(fifo)}])
        held = hold_point(fifo, a)
        e.push_alias()
        b = e.run(LB, claim(OBJ_X, "--no-github"))
        held.close()
        a.wait()
        assert (a.code, b.code) == (2, 0), [(w.lane, w.code, w.err[-400:]) for w in (a, b)]
        assert e.claimed(OBJ, OBJ_X) == [(OBJ, LB)]
        assert len(a.commit_calls()) == 1, "A made a second commit call"
        assert a.ends()[a.commit_calls()[0]["call"]].get("psql") not in (None, 0)
    else:
        a = e.run(LA, claim(OBJ_X, "--no-github"))
        assert a.code == 0, a.err[-600:]
        e.push_alias()
        b = e.run(LB, claim(OBJ, "--no-github"))
        assert b.code == 2, f"B exited {b.code}: {b.err[-600:]}"
        assert "LR005" in b.err and "claim-spellings" in b.err, b.err
        assert b.commit_calls(), "B's refusal came before its commit call, not from the spelling check"
        assert all(not e.has_write(x) for x in b.write_ids())
        assert e.claimed(OBJ, OBJ_X) == [(OBJ_X, LA)]
    assert e.c.value(f"SELECT count(*) FROM {REGISTER}.object_holds WHERE object = '{OBJ_X}' "
                     f"AND lane = '{LB}';") == "0"


@CLIENT
@pytest.mark.parametrize("tip", ["same-tip", "behind-the-alias"])
def test_two_spellings_of_one_object_claimed_at_once_leave_one_claimed_and_exit_2(estates, tip):
    """AT-D19: L1 claims O and L2 claims X, each held at its first commit
    call after both snapshots read `n`; the admin session holds the head row;
    L1's call is released and waits on the lock, then L2's; the admin rolls
    back, so L1 takes the head row first. L1 exits 0 and prints `register
    seq <n+1>`; L2's first commit fails, it re-reads and exits 2, never 69
    or 75, its stderr naming L1's claim; the journal grew by one; L1's
    `object_holds` row carries O as typed, the key O and the alias X; one
    live `CLAIMED` holds O and no line holds X."""
    e = estates()
    origin_l2 = e.mirror_at_t0() if tip == "behind-the-alias" else None
    e.push_alias()
    n = e.c.head()
    fifos = {lane: e.root / f"hold-{lane}.fifo" for lane in (LA, LB)}
    for f in fifos.values():
        os.mkfifo(str(f))
    arms = {lane: [{"mode": "hold", "match": "commit_write", "call": 1, "fifo": str(fifos[lane])}]
            for lane in (LA, LB)}
    l1 = e.launch(LA, claim(OBJ, "--no-github"), arms=arms[LA])
    l2 = e.launch(LB, claim(OBJ_X, "--no-github"), arms=arms[LB], origin=origin_l2)
    holds = {LA: hold_point(fifos[LA], l1), LB: hold_point(fifos[LB], l2)}  # both snapshots read n
    admin = e.hold_row_locked()
    try:
        holds[LA].close()
        assert e.waits_on_lock(l1.write_ids()[0]), "L1's commit never waited on the head row"
        holds[LB].close()
        assert e.waits_on_lock(l2.write_ids()[0]), "L2's commit never waited on the head row"
    finally:
        e.unlock(admin)
    l1.wait()
    l2.wait()
    assert (l1.code, l2.code) == (0, 2), [(w.lane, w.code, w.err[-400:]) for w in (l1, l2)]
    assert l1.seq_said() == n + 1
    assert l2.ends()[l2.commit_calls()[0]["call"]].get("psql") not in (None, 0)
    assert len(l2.snapshot_calls()) >= 2, "L2 did not re-read at n+1"
    assert LA in l2.err, f"L2's refusal does not name L1's claim: {l2.err!r}"
    assert [r["lane"] for r in e.journal_after(n)] == [LA]
    spellings = e.c.value(f"SELECT spellings::text FROM {REGISTER}.object_holds WHERE object = '{OBJ}' "
                          f"AND lane = '{LA}';")
    assert all(s in spellings for s in (OBJ, OBJ_X)), spellings
    assert all(not e.has_write(x) for x in l2.write_ids())
    assert e.claimed(OBJ, OBJ_X) == [(OBJ, LA)]
    assert e.log_lines("CLAIMED", OBJ_X) == 0
    if tip == "behind-the-alias":
        assert "LR005" in l2.err and "claim-spellings" in l2.err, l2.err


@CLIENT
def test_the_claim_behind_the_alias_is_refused_by_lr005_on_its_spellings(estates):
    """AT-D19 [behind-the-alias], by itself: L1 at the tip with the alias
    claims O and commits; L2, at the tip before the alias, claims X. Neither
    the verb's check nor `one_live_claim` sees L1's claim, so the refusal is
    LR005 `claim-spellings` on L2's last commit call: exit 2, its write id
    absent, one live `CLAIMED` on O."""
    e = estates()
    frozen = e.mirror_at_t0()
    e.push_alias()
    l1 = e.run(LA, claim(OBJ, "--no-github"))
    assert l1.code == 0, l1.err[-600:]
    l2 = e.run(LB, claim(OBJ_X, "--no-github"), origin=frozen)
    assert l2.code == 2, f"L2 exited {l2.code}: {l2.err[-600:]}"
    assert "LR005" in l2.err and "claim-spellings" in l2.err, l2.err
    calls = l2.commit_calls()
    assert calls and l2.ends()[calls[-1]["call"]].get("psql") not in (None, 0), "no refused commit call"
    assert all(not e.has_write(x) for x in l2.write_ids())
    assert e.claimed(OBJ, OBJ_X) == [(OBJ, LA)]


@CLIENT
def test_the_burst_window_is_effective_a_short_deadline_sends_writers_busy(estates):
    """Section 4.1's companion: the same burst with a 1 s deadline. At least
    one writer exits 75, none exits 69, and each busy writer's write ids are
    absent from the journal."""
    e = estates()
    writers, drain = burst(e, [f"{KEY}#{300 + k}" for k in range(10)], 200,
                           extra={"LANES_REGISTER_DEADLINE_S": "1"})
    codes = [w.code for w in writers]
    assert 75 in codes and 69 not in codes, codes
    assert set(codes) <= {0, 75}, codes
    for w in writers:
        if w.code == 75:
            assert all(not e.has_write(x) for x in w.write_ids()), f"{w.lane} busy, yet written"
    record("window-effective", busy=codes.count(75), drain_s=round(drain, 2))


# ============================================================ PHASE W: AT-F14, output once (T248)
#
# F14 (S1, "Output and side effects, once"; lane 4's section): the verb runs
# as a child that stops at the seam; only the deciding attempt's output is
# replayed, stdout first; every side effect outside the register runs once,
# after COMMIT; one run makes one journal entry. On test 4's estate (T243's
# `Estate`), with logging fakes for `gh`, `tmux` and a `git` wrapper that log
# their environment (TP:6847-6851). The child's state directory is read as
# `<XDG_STATE_HOME>/openRepoTools/register-writes/` (a reading: lane 4 names
# `<state>/register-writes/`). They FAIL UNTIL L4-B3 and L4-B7 land (T413,
# T414, T415), with T243's own; without PostgreSQL 16 each skips.

_ENV_LOGGER = r'''#!/usr/bin/env python3
# T248's logging stand-in: its name, argv, whether the flag reached it, and
# each seam.out it can see; then the real tool, where one is named.
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
NAME = os.path.basename(sys.argv[0])
REAL = REAL_TOOL
STATE = STATE_DIR
seams = {p: open(p, encoding="utf-8", errors="replace").read()
         for p in glob.glob(os.path.join(STATE, "**", "seam.out"), recursive=True)}
with open(os.path.join(HERE, "tools.log"), "a", encoding="utf-8") as log:
    log.write(json.dumps({"tool": NAME, "argv": sys.argv[1:], "scratch": os.environ.get(
        "LANES_REGISTER_SCRATCH"), "seams": seams}) + "\n")
if REAL:
    os.execv(REAL, [REAL] + sys.argv[1:])
'''


def loggers(e: Estate) -> Path:
    """`git` (a wrapper), `gh` and `tmux` (fakes), each logging to
    `tools.log` beside them."""
    where = e.root / "loggers"
    where.mkdir(exist_ok=True)
    for tool, real in (("git", shutil.which("git")), ("gh", None), ("tmux", None)):
        (where / tool).write_text(_ENV_LOGGER.replace("REAL_TOOL", repr(real))
                                  .replace("STATE_DIR", repr(str(e.state))), encoding="utf-8")
        (where / tool).chmod(0o755)
    return where


def tool_calls(where: Path, tool: Optional[str] = None) -> List[dict]:
    log = where / "tools.log"
    calls = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l] if log.exists() else []
    return [c for c in calls if tool is None or c["tool"] == tool]


def register_writes(e: Estate) -> Path:
    return e.state / "openRepoTools" / "register-writes"


def seam_outs(e: Estate) -> Dict[str, str]:
    return {str(p): p.read_text(encoding="utf-8", errors="replace")
            for p in register_writes(e).rglob("seam.out")} if register_writes(e).exists() else {}


@CLIENT
def test_a_writer_prints_its_output_once_however_many_attempts_it_made(estates):
    """Test 4's burst of ten: each committed writer's stdout carries its
    success text exactly once, however many attempts it made, and its stderr
    no line twice (only the deciding attempt's)."""
    e = estates()
    writers, _ = burst(e, [f"{KEY}#{400 + k}" for k in range(10)], 200)
    assert [w.code for w in writers] == [0] * 10, [(w.lane, w.code, w.err[-300:]) for w in writers]
    for w in writers:
        assert len(SEQ_SAID.findall(w.out)) == 1, f"{w.lane} printed its success text not once: {w.out!r}"
        lines = [l for l in w.err.splitlines() if l.strip()]
        assert len(lines) == len(set(lines)), f"{w.lane}'s stderr repeats an attempt's lines: {w.err!r}"
    record("output-once", attempts={w.lane: len(w.snapshot_calls()) for w in writers})


@CLIENT
def test_a_refused_writer_replays_its_output_then_the_refusal(estates):
    """Test 4's case (a): the writer refused at its commit prints its
    buffered output, then the refusal, last, naming the holder, and no
    success text."""
    e = estates()
    barrier = Barrier(e.root, 2)
    writers = [e.launch(lane, claim(OBJ, "--no-github"), arms=[WINDOW], barrier=barrier) for lane in (LA, LB)]
    barrier.release()
    assert sorted(w.wait() for w in writers) == [0, 2]
    win, lose = sorted(writers, key=lambda w: w.code)
    assert not SEQ_SAID.search(lose.out), f"the refused writer printed success text: {lose.out!r}"
    lines = [l for l in lose.err.splitlines() if l.strip()]
    assert lines and win.lane in lines[-1], f"the refusal naming {win.lane} is not last: {lose.err!r}"
    assert len(lines) == len(set(lines)), f"the refused writer's stderr repeats lines: {lose.err!r}"


@CLIENT
@pytest.mark.parametrize("effect", ["tmux", "gh"])
def test_a_side_effect_runs_once_after_commit_and_never_for_a_refusal(estates, effect):
    """[gh]: two claimants on O; the fake `gh` is called once, by the
    committed claim, citing its seq, never by the refused one. [tmux]: two
    `request-handoff`s for one lane; the fake `tmux` is called by the
    committed one only, after its COMMIT (the journal holds it when `tmux`
    runs), and never by a refused one."""
    e = estates()
    where = loggers(e)
    barrier = Barrier(e.root, 2)
    if effect == "gh":
        writers = [e.launch(lane, claim(OBJ), arms=[WINDOW], barrier=barrier, first=[where])
                   for lane in (LA, LB)]
    else:
        writers = [e.launch(lane, ["request-handoff", LC, "--session", session_of(LC)], arms=[WINDOW],
                            barrier=barrier, first=[where]) for lane in (LA, LB)]
    barrier.release()
    for w in writers:
        w.wait()
    committed = [w for w in writers if w.code == 0]
    grew = e.journal_after()
    assert len(committed) == len(grew) >= 1, ([(w.lane, w.code, w.err[-300:]) for w in writers], grew)
    calls = tool_calls(where, effect)
    assert len(calls) == len(committed), f"{effect} ran {len(calls)} times for {len(committed)} commits: {calls}"
    if effect == "gh":
        assert f"register seq {grew[0]['seq']}" in json.dumps(calls), calls
    for call in calls:
        assert set(call["seams"].values()) <= {"tail", "tail\n"}, f"{effect} ran before COMMIT: {call}"


#: The test copy of `lanes-edit.sh` whose writes reach the seam twice: its
#: `commit_publish` (T414's seam) is renamed and called twice by a wrapper.
TWICE = ('commit_publish() { commit_publish_t248_once "$@" || return; '
         'commit_publish_t248_once "$@"; }\n')


@CLIENT
def test_a_second_reach_of_the_seam_in_one_run_exits_2(estates):
    """One run, one journal entry: an arm the test copy makes reach the seam
    twice exits 2, "a second register write in one run", naming the first
    seq, and the journal holds that one entry."""
    e = estates()
    text = e.lanes_edit.read_text(encoding="utf-8")
    assert text.count("\ncommit_publish() {") == 1, "lanes-edit.sh has no commit_publish, T414's seam"
    twice = e.bindir / "lanes-edit-twice.sh"
    twice.write_text(text.replace("\ncommit_publish() {", "\n" + TWICE + "commit_publish_t248_once() {", 1),
                     encoding="utf-8")
    w = e.run(LA, ["append-line", f"NOTE {EM} lane {LA}: one run, two reaches (T248)"], script=twice)
    grew = e.journal_after()
    assert w.code == 2, f"exit {w.code}, not 2: {w.err[-600:]}"
    assert len(grew) == 1, grew
    assert "a second register write in one run" in w.err and str(grew[0]["seq"]) in w.err, w.err


@CLIENT
@pytest.mark.parametrize("case", ["outside-register-writes", "wrong-mode", "other-parent"])
def test_the_scratch_flag_is_honoured_only_for_its_own_attempt_directory(estates, case):
    """A write run with `LANES_REGISTER_SCRATCH` exported, naming a directory
    outside `<state>/register-writes/`, one of mode 0755, or one whose
    `parent.pid` is not the run's parent, does not take it as the flag: the
    shim's log shows the run's own snapshot and commit calls, and it
    commits."""
    e = estates()
    base = e.root / "elsewhere" if case == "outside-register-writes" else register_writes(e)
    attempt = base / "attempt-t248"
    attempt.mkdir(parents=True)
    attempt.chmod(0o755 if case == "wrong-mode" else 0o700)
    (attempt / "parent.pid").write_text("1\n" if case == "other-parent" else f"{os.getpid()}\n",
                                        encoding="utf-8")
    w = e.run(LA, ["append-line", f"NOTE {EM} lane {LA}: the flag refused, {case} (T248)"],
              extra={"LANES_REGISTER_SCRATCH": str(attempt)})
    assert w.code == 0, f"[{case}] exit {w.code}: {w.err[-600:]}"
    assert w.snapshot_calls() and w.commit_calls(), f"[{case}] the run made no snapshot or commit call"
    assert len(e.journal_after()) == 1


@CLIENT
def test_the_scratch_flag_never_reaches_git_gh_or_tmux(estates):
    """The child unsets `LANES_REGISTER_SCRATCH` at once, so the logged
    environments of the `git` wrapper, the fake `gh` and the fake `tmux`
    never hold it, over a committed claim and a refused one."""
    e = estates()
    where = loggers(e)
    barrier = Barrier(e.root, 2)
    writers = [e.launch(lane, claim(OBJ), arms=[WINDOW], barrier=barrier, first=[where]) for lane in (LA, LB)]
    barrier.release()
    assert sorted(w.wait() for w in writers) == [0, 2]
    calls = tool_calls(where)
    assert {c["tool"] for c in calls} >= {"git", "gh"}, f"the loggers saw too little: {calls[:3]}"
    held = [c for c in calls if c["scratch"]]
    assert held == [], f"LANES_REGISTER_SCRATCH reached {sorted({c['tool'] for c in held})}"


@CLIENT
@pytest.mark.parametrize("case", ["parent-gone", "cap"])
def test_a_child_at_the_seam_stops_with_none_and_runs_no_tail(estates, case):
    """With its parent killed ([parent-gone]) or stopped by SIGSTOP at the
    cap (`LANES_REGISTER_SEAM_CAP_S=3`, [cap]) while it waits at the seam,
    the child writes `seam.out` as `none` and runs no tail: the fake `gh` is
    not called, and nothing is written. The parent's commit call is held by
    the shim and never sent."""
    e = estates()
    where = loggers(e)
    fifo = e.root / "hold.fifo"
    os.mkfifo(str(fifo))
    w = e.launch(LA, claim(OBJ), first=[where], extra={"LANES_REGISTER_SEAM_CAP_S": "3"},
                 arms=[{"mode": "hold", "match": "commit_write", "call": 1, "fifo": str(fifo)}])
    held = hold_point(fifo, w)
    try:
        os.kill(w.proc.pid, 9 if case == "parent-gone" else 19)
        deadline = time.monotonic() + 20
        while "none" not in "".join(seam_outs(e).values()):
            assert time.monotonic() < deadline, f"[{case}] no seam.out reads none: {seam_outs(e)}"
            time.sleep(0.1)
        time.sleep(0.5)
        assert tool_calls(where, "gh") == [], f"[{case}] the tail ran: {tool_calls(where, 'gh')}"
        assert e.journal_after() == []
    finally:
        if case == "cap":
            os.kill(w.proc.pid, 18)
    assert held is not None  # never closed: the held commit call is never sent


@CLIENT
@pytest.mark.parametrize("decision", ["committed", "abandon"])
def test_seam_out_is_written_once_before_the_child_acts(estates, decision):
    """`seam.out` is written once, with noclobber: `tail` before the child
    acts on `committed` (the fake `gh`, the claim's tail, sees `tail`), and
    `none` before it acts on `abandon` (the refused claim's child runs no
    tail). No `seam.out` holds anything else."""
    e = estates()
    where = loggers(e)
    if decision == "committed":
        w = e.run(LA, claim(OBJ), first=[where])
        assert w.code == 0, w.err[-600:]
        gh = tool_calls(where, "gh")
        assert gh and all(set(c["seams"].values()) == {"tail"} or set(c["seams"].values()) == {"tail\n"}
                          for c in gh), f"gh saw no seam.out reading tail: {gh}"
    else:
        assert e.run(LB, claim(OBJ, "--no-github")).code == 0
        w = e.run(LA, claim(OBJ), first=[where])
        assert w.code == 2, w.err[-600:]
        assert tool_calls(where, "gh") == [], "the abandoned attempt ran its tail"
    for path, said in seam_outs(e).items():
        assert said.strip() in ("tail", "none") and said.count("\n") <= 1, f"{path}: {said!r}"


# ============================================================ PHASE N: AT-F5 group A, the act's client half (T233)
#
# AT-F5 (TP:5818-5946; Y:5567-5624): lane 4's L4-A2, group A, which is T410's
# `act-begin` with `--rebase` and the client's checks on `LANES_ACT` and
# `LANES_EXPECT`, and T411's `canon-lane --walk`. They are written to the
# test plan's text and B14's T410 and T411 bullets: L4-A2 is in no bundle
# lane 4 has shared (its share folder holds T409, T413 and T419 only), and
# neither verb is in line R's merge10.
#
# Off primary, and `canon-lane --walk`, they run in files mode with no engine,
# on `test_lane_start_claude_current`'s `Sandbox` (`LANES_INDEX=off`) with a
# `psql` first on `PATH` that only logs its calls, so they are red at the base
# by their own assertions. The others run on test 4's estate at `primary`
# (T243's `Estate`), each writer with its own `psql` log, and skip without
# PostgreSQL 16. Every case FAILS UNTIL L4-A2 (lane 4's T410 and T411) and
# L1-A9 land.

WALK_A, WALK_B = "repoWA-1", "repoWB-1"
#: The walk's alias lines on test 4's estate: `a` to `b`, `b` to `c` (LC, which has a row).
WALK_ALIASES = f"{WALK_A}\t{WALK_B}\t2026-10-01T00:00:00Z\n{WALK_B}\t{LC}\t2026-10-01T00:00:00Z\n"
_ACT_ID = re.compile(r"^([0-9a-f]{32})@")


class FilesBox(Sandbox):
    """A files-mode workstation (`Sandbox`) with rows of its own, an alias
    table, and a `psql` that logs each call and answers nothing."""

    def __init__(self, root: Path, rows: Sequence[str] = (), aliases: Sequence[Tuple[str, str]] = ()) -> None:
        super().__init__(root)
        self.psql_log = root / "psql.log"
        _write(self.fakebin / "psql", f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{self.psql_log}"\nexit 2\n')
        lanes = self.wip / "lanes"
        with open(lanes / "LANES.md", "a", encoding="utf-8") as handle:
            for lane in rows:
                handle.write(f"| `{lane}` | harness `{session_of(lane)}` | Eagle / test / brett "
                             f"| 2026-10-01T00:00Z | none | handoffs/{lane}.md "
                             f"| LIVE {DOT} 2026-10-01T00:00:00Z {DOT} working |\n")
        if aliases:
            (lanes / "aliases.tsv").write_text(
                "# old\tnew\tutc\n" + "".join(f"{old}\t{new}\t2026-10-01T00:00:00Z\n" for old, new in aliases),
                encoding="utf-8")
        if rows or aliases:
            self.git("-C", str(self.wip), "add", "-A")
            self.git("-C", str(self.wip), "commit", "-q", "-m", "T233's register")
            self.git("-C", str(self.wip), "push", "-q", "origin", "main")
            self.git("-C", str(self.ws), "pull", "-q", "--ff-only")

    def edit(self, *argv: str, env: Optional[dict] = None) -> subprocess.CompletedProcess:
        full = dict(self.env, **(env or {}))
        return subprocess.run([str(self.bin / "lanes-edit.sh"), *argv], env=full, cwd=str(self.lane_dir),
                              capture_output=True, text=True, timeout=120, check=False,
                              stdin=subprocess.DEVNULL)

    def psql_calls(self) -> List[str]:
        return self.psql_log.read_text(encoding="utf-8").splitlines() if self.psql_log.exists() else []


def test_act_begin_prints_its_base_and_touches_no_database_off_primary(tmp_path):
    """Off primary `act-begin` prints `<act-id>@files`, the id 32 lower-case
    hex digits, new for every act, and touches no database: the `psql` on
    `PATH` is never called (TP:5828-5830; Y:5571-5575; T410)."""
    box = FilesBox(tmp_path / "box")
    first, second = box.edit("act-begin"), box.edit("act-begin")
    for r in (first, second):
        assert r.returncode == 0, f"act-begin exited {r.returncode}: {r.stderr[-600:]}"
        assert re.fullmatch(r"[0-9a-f]{32}@files\n", r.stdout), f"act-begin printed {r.stdout!r}"
    assert first.stdout != second.stdout, "two acts were given one id"
    assert box.psql_calls() == [], f"act-begin off primary called psql: {box.psql_calls()}"


#: `canon-lane --walk`'s cases (TP:5866-5873): the rows, the alias lines, the
#: typed name, and the names the walk prints.
WALKS = {
    "two-hops": ((LC,), ((WALK_A, WALK_B), (WALK_B, LC)), WALK_A, [WALK_A, WALK_B, LC]),
    "no-alias": ((LC,), (), LC, [LC]),
    "refused": (("repoWR-1", "RepoWR-1"), (), "repoWR-1", []),
}


@pytest.mark.parametrize("case", list(WALKS))
def test_canon_lane_walk_prints_each_hop_with_canon_lanes_exit_code(tmp_path, case):
    """[two-hops]: alias lines lead `a` to `b` and `b` to `c`, which has a
    row; `canon-lane --walk a` prints `a`, `b` and `c`, one per line, the typed
    name first, and exits as `canon-lane a` does. [no-alias]: the lane alone.
    [refused]: where `canon-lane` refuses (two rows that differ only by case,
    its 2), the walk exits with the same code and prints nothing on stdout
    (T411)."""
    rows, aliases, typed, names = WALKS[case]
    box = FilesBox(tmp_path / "box", rows, aliases)
    plain = box.edit("canon-lane", typed)
    walk = box.edit("canon-lane", "--walk", typed)
    assert (plain.returncode != 0) == (case == "refused"), f"[{case}] canon-lane exited {plain.returncode}"
    assert walk.returncode == plain.returncode, (
        f"[{case}] the walk exited {walk.returncode}, canon-lane {plain.returncode}: {walk.stderr[-600:]}")
    assert walk.stdout.splitlines() == names, f"[{case}] the walk printed {walk.stdout!r}, not {names}"
    if case == "refused":
        # The refusal is canon-lane's own (its two-rows note), not a refusal of the flag.
        assert "differ only by case" in walk.stderr, f"[{case}] not canon-lane's refusal: {walk.stderr[-600:]}"


@CLIENT
@pytest.mark.parametrize("case", ["present", "switch-at-files", "snapshot-fails"])
def test_act_begin_on_primary_prints_id_seq_and_generation(estates, case):
    """[present]: on primary `act-begin` prints 32 lower-case hex digits, `@`,
    the head seq with no leading zero, `:` and the switch's generation as a
    lower-case uuid, and the shim's log holds its one snapshot call.
    [switch-at-files] (the cutover aborted by `switch_to_files`) and
    [snapshot-fails] (the shim fails the call): exit 69, nothing on stdout
    (TP:5874-5878; T410)."""
    e = estates()
    arms = []
    if case == "switch-at-files":
        aborted = e.c.call(ABORT_SQL, client=e.c.client(), seq=e.c.head(), lane=OPERATOR, ws=WS)
        assert aborted.returncode == 0 and e.c.switch()["mode"] == "files", aborted.stderr
    elif case == "snapshot-fails":
        arms = [{"mode": "fail-call", "call": 1}]
    w = e.run(LA, ["act-begin"], arms=arms)
    if case != "present":
        assert (w.code, w.out) == (69, ""), f"[{case}] exit {w.code}, stdout {w.out!r}: {w.err[-600:]}"
        return
    gen = e.c.switch()["generation"]
    assert w.code == 0, f"exit {w.code}: {w.err[-600:]}"
    assert re.fullmatch(r"[0-9a-f]{32}@" + str(e.c.head()) + ":" + re.escape(gen) + r"\n", w.out), (
        f"act-begin printed {w.out!r}, not <id>@{e.c.head()}:{gen}")
    assert len(w.calls()) == 1, f"act-begin made {len(w.calls())} calls, not its one snapshot"


@CLIENT
def test_act_begin_rebase_keeps_the_id_and_takes_the_new_base(estates):
    """`act-begin`; a rival touches one of the act's scopes; `act-begin
    --rebase` prints the same id with the head seq then and the switch's
    generation; the act's write on that scope commits; a second rival entry
    after the new base on the same scope still refuses it with 2
    (TP:5850-5858; Y:5591-5595; T410)."""
    e = estates()
    act = act_begin(e)
    scope = f"objects:{LA.lower()}"
    other = {"LANES_SESSION": "dddddddd-0233-4000-8000-00000000d233"}
    assert e.run(LA, act_write(e, "objects", tag="rival-1"), extra=other).code == 0
    rebased = e.run(LA, ["act-begin", "--rebase"], extra={"LANES_ACT": act})
    gen = e.c.switch()["generation"]
    assert rebased.code == 0, f"--rebase exited {rebased.code}: {rebased.err[-600:]}"
    assert rebased.out == f"{_ACT_ID.match(act).group(1)}@{e.c.head()}:{gen}\n", (
        f"--rebase printed {rebased.out!r}; the act was {act}, the head is {e.c.head()}")
    new = rebased.out.strip()
    w = e.run(LA, act_write(e, "objects", tag="after-rebase"), extra=acted(new, scope))
    assert w.code == 0, f"the act's write after its rebase exited {w.code}: {w.err[-600:]}"
    assert e.run(LA, act_write(e, "objects", tag="rival-2"), extra=other).code == 0
    late = e.run(LA, act_write(e, "objects", tag="after-rival-2"), extra=acted(new, scope))
    assert late.code == 2 and f"expectation: {scope} changed" in late.err, (late.code, late.err[-600:])


@CLIENT
@pytest.mark.parametrize("case", ["malformed", "files-base", "generation-changed"])
def test_act_begin_rebase_refuses_with_2(estates, case):
    """`act-begin --rebase` refuses with 2, printing nothing and writing
    nothing, where `LANES_ACT` is malformed (the old `<id>@<seq>`), where its
    base is `files` on primary, and where its generation is not the switch's
    (TP:5859-5861; T410)."""
    e = estates()
    act = {"malformed": f"{'a' * 32}@{e.c.head()}", "files-base": f"{'a' * 32}@files",
           "generation-changed": f"{'a' * 32}@{e.c.head()}:{uuid.uuid4()}"}[case]
    state = e.c.state()
    w = e.run(LA, ["act-begin", "--rebase"], extra={"LANES_ACT": act})
    assert (w.code, w.out) == (2, ""), f"[{case}] exit {w.code}, stdout {w.out!r}: {w.err[-600:]}"
    assert e.c.state() == state


#: The client's checks before the first snapshot (TP:5879-5887; Y:5597-5605):
#: each case's `LANES_ACT` and `LANES_EXPECT` pairs, `None` for unset, and the
#: variable the refusal names. `{act}` is a well-formed base from `act-begin`.
BAD_ACTS = {
    "malformed": ([(f"{'a' * 32}@1", "objects:{lane}"), (f"{'a' * 32}@1:{'A' * 8}-0000-4000-8000-{'0' * 12}", ""),
                   ("{id}@01:{gen}", "")], "LANES_ACT"),
    "expect-without-act": ([(None, "objects:{lane}"), ("", "objects:{lane}")], "LANES_EXPECT"),
    "bad-scope": ([("{act}", "*"), ("{act}", "row:*"), ("{act}", "lane:{lane}")], "LANES_EXPECT"),
    "files-base": ([("{id}@files", "objects:{lane}")], "LANES_ACT"),
}


@CLIENT
@pytest.mark.parametrize("case", list(BAD_ACTS))
def test_the_client_refuses_a_bad_act_with_2_before_any_call(estates, case):
    """On primary a write whose `LANES_ACT` is malformed (the old form, an
    upper-case uuid, a seq with a leading zero), whose `LANES_EXPECT` is set
    with no `LANES_ACT`, whose scope is outside the six forms (`*` and `row:*`
    among them), or whose base is `files` (the text naming `<id>@files`)
    exits 2 naming the variable, with the shim's log empty and nothing
    written (TP:5879-5887; T410)."""
    e = estates()
    act = act_begin(e)
    ident, gen = _ACT_ID.match(act).group(1), e.c.switch()["generation"]
    pairs, variable = BAD_ACTS[case]
    for raw_act, raw_expect in pairs:
        state = e.c.state()
        extra = {"LANES_EXPECT": raw_expect.format(lane=LA.lower())}
        if raw_act is not None:
            extra["LANES_ACT"] = raw_act.format(act=act, id=ident, gen=gen)
        w = e.run(LA, act_write(e, "objects", tag=case), extra=extra)  # unset: the estate never carries it
        assert w.code == 2, f"[{case}] {extra}: exit {w.code}: {w.err[-600:]}"
        assert variable in w.err, f"[{case}] {extra}: the refusal does not name {variable}: {w.err[-600:]}"
        if case == "files-base":
            assert f"{ident}@files" in w.err, w.err[-600:]
        assert w.calls() == [], f"[{case}] {extra}: a call was made: {w.calls()}"
        assert e.c.state() == state, f"[{case}] {extra}: the register changed"


# ============================================================ PHASE W: AT-F5 group B, acts racing (T252)
#
# F5 (D5; lane 4's section, "The acts and their expectations"): an act runs
# `act-begin`, exports `LANES_ACT=<id>@<n>:<generation>`, and each write
# carries `LANES_EXPECT="<scope> ..."`; the commit refuses with LR009, the
# writer with 2, `expectation: <scope> changed at seq <k> by <lane>/<verb>`,
# when an entry of another act touched a listed scope after the base. The two
# race functions run lane 4's acts to each write of its tables, on a world of
# their own (T252b, below). The other cases run on test 4's estate (T243's
# `Estate`), where the writes are `append-line` of a row-shaped line
# (`row:<L>`) and `log` (`objects:<L>`), a reading of lane 1's derived keys.
# The three conditions and the launches are read from lane 4's tools' text (a
# reading: their flows are T428-T432's, and lane 3's batch 7 asks that they
# run the flows). They FAIL UNTIL L1-A6, L4-A2 (T410), L4-B3 and L4-B14 land;
# without PostgreSQL 16 the RE cases skip.

ACT_RE = re.compile(r"^[0-9a-f]{32}@[1-9][0-9]*:" + UUID_RE + r"$|^[0-9a-f]{32}@0:" + UUID_RE + r"$")


def act_begin(e: Estate, lane: str = LA) -> str:
    w = e.run(lane, ["act-begin"])
    act = w.out.strip()
    assert w.code == 0 and ACT_RE.match(act), f"act-begin exited {w.code}, printed {w.out!r}: {w.err[-300:]}"
    return act


def act_write(e: Estate, scope: str, lane: str = LA, tag: str = "") -> List[str]:
    """The act's write on `scope`, `row` or `objects`."""
    if scope == "row":
        return ["append-line", f"| `{lane}` | harness `{session_of(lane)}` | {W_WS} / test / brett "
                               f"| 2026-05-01T00:00Z | none | handoffs/{lane}.md | T252 row {tag} |"]
    return ["log", "NOTED", f"{KEY}#77", f"T252 {tag}"]


def acted(act: str, *scopes: str) -> dict:
    return {"LANES_ACT": act, "LANES_EXPECT": " ".join(scopes)}


# ---------------------------------------- the race, on each write of lane 4's tables (T252b)
#
# TP:5848-5853 parametrise the race "for each write of lane 4's tables", and
# lane 3's batch 7 (ruling 5) takes one id per write and drops `[row|objects]`,
# since T233's group A cases hold the commit's half. So each case runs the act,
# lane 4's own tool, to that write on a workstation at `primary`; the shim
# holds that write's commit call; a rival from a second session commits; and
# the hold is let go (TP:5854-5856). The rival writes the lane's own `PAUSED`
# in its log, as a forced release does (Y:5675): a lane-kind line, `bind:<L>`,
# which every write of the tables lists (Y:5640-5680), W1's new lane aside,
# whose rival is a row line for it, `row:<L>`. The held case's rival writes
# the same line for another lane, which no write of the act lists.
#
# THE WORLD is `test_lane_start_claude_current`'s `Sandbox` (fake `tmux`,
# `claude` and `gh`) holding the register N1's arms run on (lane 2's T217):
# repoA-1 PAUSED here, repoA-2 LIVE here, repoA-3 LIVE on Falcon, repoH-1
# PAUSED here long ago, and no repoZ-1. It is imported into a clone of `tmpl`
# that `Clone.to_primary` brings to `primary`, with the flipped `lanes-index`
# beside `lanes-edit.sh` and `mode=primary` configured, as test 4's estate is.
# Readings: each act's argv (N1's arms at `2a057a6d`, with `--no-launch` for
# W1, `lane-end --retire-dormant` and `lane --request-handoff`); the write's
# commit call, found by a text its entry's JSON carries (its verb, or its
# line's kind, lane or state); the skill's step-4 block, the fenced block of
# its section 4 that opens with `act-begin`; and the guard's child, run as
# T502 writes its body, `guard-bind --body <uuid>`, whose record's path T502
# owns.
#
# They FAIL UNTIL L1-A6, L4-A2 (T410, T411), L4-B3, L4-B5 and L4-B14 (T428 to
# T432) land; the skill's id also until T431's block, and the guard's until
# T502's `guard-bind` and T510's expectations on its `set-row-state`. Without
# PostgreSQL 16 each skips.

#: The em dash as the entry's ASCII JSON spells it.
EM_JSON = json.dumps(EM)[1:-1]
#: The world's lanes (N1's arms) and their sessions.
R_PAUSED, R_HERE, R_FAR, R_DORMANT, R_NEW = "repoA-1", "repoA-2", "repoA-3", "repoH-1", "repoZ-1"
R_SID = {R_PAUSED: "aaaaaaaa-0002-4000-8000-00000000a002", R_HERE: "aaaaaaaa-0003-4000-8000-00000000a003",
         R_FAR: "aaaaaaaa-0253-4000-8000-00000000a253", R_DORMANT: "aaaaaaaa-0254-4000-8000-00000000a254",
         R_NEW: "aaaaaaaa-0255-4000-8000-00000000a255"}
#: For each lane, a lane that none of its acts' writes lists (the held case).
R_OTHER = {R_PAUSED: R_FAR, R_HERE: R_FAR, R_FAR: R_HERE, R_DORMANT: R_FAR, R_NEW: R_FAR}


def verb_is(verb: str) -> str:
    return f'"verb":"{verb}"'


def lane_line(kind: str, lane: str) -> str:
    return f"{kind} {EM_JSON} lane {lane}"


class ActWrite:
    """One write of lane 4's tables: the act that makes it (`tool`, `argv`),
    the lane it writes, its commit call (`match`, a text its entry carries,
    the first commit call that carries it), the rival's line (`bind`, the
    lane's `PAUSED`; `row`, a row line), and the act's exit where lane 4's
    arm names one for a refused write (`code`; else only never 0)."""

    def __init__(self, tool: str, argv: Tuple[str, ...], lane: str, match: str, rival: str = "bind",
                 code: Optional[int] = None, env: Optional[dict] = None) -> None:
        self.tool, self.argv, self.lane, self.match = tool, argv, lane, match
        self.rival, self.code, self.env = rival, code, env or {}


_HANDOFF = ("--lane", R_HERE, "T252b's race")
#: TP:5848-5853's list, in its order: `lane-start`'s W1, W8 and `start-record`
#: (W2 to W7); `lane-handoff`'s late `log PAUSED --utc`, W9, W11 and W12;
#: `lane-end`'s W13, W14 and `retire-rows`; the handoff skill's step-4 writes;
#: the guard's answer 2, its child's `set-row-state` on the lane left; and
#: `lane`'s `request-handoff`. The codes: `start-record`'s and W1's 2 die 2
#: (T428, "any 2 dies"); W8's arm passes the code (T428); `:2817` keeps 2
#: (T429); W13 under `set -e` and W14's note arm exit with the writer's code
#: (T430); `lane`'s arm keeps 1 for a 2 (T432).
ACT_WRITES = {
    "lane-start-w1-add-row": ActWrite("lane-start", ("repoZ", "1", "--no-launch"), R_NEW,
                                      verb_is("add-row"), rival="row", code=2),
    "lane-start-w8-request-handoff": ActWrite("lane-start", ("repoA", "3", "--request-handoff", "--dir",
                                                             "{lane_dir}"), R_FAR,
                                              verb_is("request-handoff"), code=2),
    "lane-start-start-record": ActWrite("lane-start", ("repoA", "1"), R_PAUSED, verb_is("start-record"),
                                        code=2),
    "lane-handoff-late-paused": ActWrite("lane-handoff", ("--late", "--at", "{utc}", *_HANDOFF), R_HERE,
                                         lane_line("PAUSED", R_HERE), code=2),
    "lane-handoff-w9-log-paused": ActWrite("lane-handoff", _HANDOFF, R_HERE, lane_line("PAUSED", R_HERE)),
    "lane-handoff-w11-append-line": ActWrite("lane-handoff", _HANDOFF, R_HERE, verb_is("append-line")),
    "lane-handoff-w12-set-row-state": ActWrite("lane-handoff", _HANDOFF, R_HERE, verb_is("set-row-state")),
    "lane-end-w13-set-row-state": ActWrite("lane-end", (R_HERE,), R_HERE, verb_is("set-row-state"), code=2),
    "lane-end-w14-log-ended": ActWrite("lane-end", (R_HERE,), R_HERE, lane_line("ENDED", R_HERE), code=2),
    "lane-end-retire-rows": ActWrite("lane-end", ("--retire-dormant", "30", "--yes", "--reason=T252b's race"),
                                     R_DORMANT, verb_is("retire-rows"), env={"LANES_LANE": R_HERE}),
    "skill-step-4-writes": ActWrite("skill", (), R_HERE, lane_line("PAUSED", R_HERE)),
    "guard-answer-2-child": ActWrite("guard", ("guard-bind", "--body", R_SID[R_PAUSED]), R_HERE,
                                     verb_is("set-row-state"), env={"LANES_LANE": R_PAUSED}),
    "lane-request-handoff": ActWrite("lane", (R_FAR, "--request-handoff"), R_FAR, verb_is("request-handoff"),
                                     code=1),
}


class ActWorld(Sandbox):
    """A workstation at `primary` whose lanes' acts run their own tools (see
    the section's head)."""

    def __init__(self, root: Path, c: "Clone") -> None:
        super().__init__(root)
        self.c = c
        for name in ("lane-end", "lane", "lane-handoff", "lanes"):
            shutil.copy2(str(REPO / name), str(self.bin / name))
            (self.bin / name).chmod(0o755)
        self.resolver()
        seat = "Eagle / test / brett"
        rows = [(R_PAUSED, seat, "2026-10-01T00:00Z", f"PAUSED {DOT} 2026-10-01T01:00:00Z {DOT} parked"),
                (R_HERE, seat, "2026-10-01T02:00Z", f"LIVE {DOT} 2026-10-01T02:00:00Z {DOT} working"),
                (R_FAR, "Falcon / test / brett", "2026-10-01T02:30Z",
                 f"LIVE {DOT} 2026-10-01T02:30:00Z {DOT} working elsewhere"),
                (R_DORMANT, seat, "2026-10-01T03:00Z", f"PAUSED {DOT} 2026-10-01T03:30:00Z {DOT} parked")]
        lanes = self.wip / "lanes"
        (lanes / "log").mkdir(exist_ok=True)
        with open(lanes / "LANES.md", "a", encoding="utf-8") as handle:
            for lane, ws, utc, state in rows:
                handle.write(f"| `{lane}` | harness `{R_SID[lane]}` | {ws} | {utc} | none "
                             f"| handoffs/{lane}.md | {state} |\n")
        for lane, ws, utc, state in rows:
            host = ws.split(" ")[0]
            text = (f"STARTED {EM} lane {lane}, session {R_SID[lane]}@{host}, {utc[:-1]}:00Z, "
                    f"lane:{lane} {ARROW} home opensoft/repoA; dir {self.lane_dir}; profile team-01a\n")
            if state.startswith("PAUSED"):
                text += (f"PAUSED {EM} lane {lane}, session {R_SID[lane]}@{host}, {state.split(' ')[2]}, "
                         f"lane:{lane} {ARROW} dir {self.lane_dir}; profile team-01a; agent claude; "
                         f"transcript {R_SID[lane]}\n")
            (lanes / "log" / f"{lane}.md").write_text(text, encoding="utf-8")
        self.git("-C", str(self.wip), "add", "-A")
        self.git("-C", str(self.wip), "commit", "-q", "-m", "T252b's register")
        self.git("-C", str(self.wip), "push", "-q", "origin", "main")
        self.git("-C", str(self.ws), "pull", "-q", "--ff-only")
        import_files(c, {str(p.relative_to(self.wip)): p.read_text(encoding="utf-8")
                         for p in sorted(lanes.rglob("*.md"))})
        assert c.to_primary() == 1, "T252b's cutover is not at seq 1"
        flipped_copy(LANES_INDEX, self.bin, True)
        conf = self.home / ".config" / "openRepoTools" / "lanes-index.conf"
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text(f"mode=primary\nregister_url={c.db.url(WRITER_LOGIN)}\nreader_url={c.db.url()}\n",
                        encoding="utf-8")
        conf.chmod(0o600)
        path = os.pathsep.join(p for p in self.env["PATH"].split(os.pathsep)
                               if p and not os.path.exists(os.path.join(p, "psql"))
                               and (p == str(self.bin) or not os.path.exists(os.path.join(p, "lanes-index"))))
        self.env.pop("LANES_INDEX", None)
        self.env.update(PATH=path, LANES_INDEX_CONFIG=str(conf), LANES_EDIT=str(self.bin / "lanes-edit.sh"),
                        XDG_STATE_HOME=str(root / "state"), FAKE_CC_PATH=str(self.resolved),
                        LANES_HOST="eagle", LANES_OS="linux", LANES_CONTAINER="none", LANES_IN_CONTAINER="0")
        self._n = itertools.count(1)
        self.writers: List[Writer] = []

    def psql_dir(self, name: str, arms: Sequence[dict] = ()) -> Path:
        return Estate.psql_dir(self, name, arms)  # the same stamp and shim as test 4's

    def launch(self, name: str, command: Sequence[str], lane: str, arms: Sequence[dict] = (),
               extra: Optional[dict] = None) -> Writer:
        psql = self.psql_dir(f"{next(self._n):02d}-{name}", arms)
        env = dict(self.env, LANES_LANE=lane, LANES_SESSION=R_SID[lane])
        env.update(extra or {})
        env["PATH"] = str(psql) + os.pathsep + env["PATH"]
        proc = subprocess.Popen(list(command), cwd=str(self.lane_dir), env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                                errors="replace", start_new_session=True)
        writer = Writer(name, lane, proc, psql)
        self.writers.append(writer)
        return writer

    def act(self, write: ActWrite, arms: Sequence[dict]) -> Writer:
        """The act that makes `write`, run by its own tool."""
        if write.tool == "skill":
            block = skill_step_4_block()
            return self.launch("skill", ["bash", "-c", block], write.lane, arms, write.env)
        if write.tool == "guard":
            return self.launch("guard", ["bash", str(self.bin / "lanes-edit.sh"), *write.argv], write.lane,
                               arms, write.env)
        utc = self.c.value("SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"');")
        argv = [a.format(lane_dir=self.lane_dir, utc=utc) for a in write.argv]
        return self.launch(write.tool, [str(self.bin / write.tool), *argv], write.lane, arms, write.env)

    def rival(self, kind: str, lane: str) -> Writer:
        """A second session's write: `bind`, the lane's own `PAUSED` in its
        log (lane-handoff's W9 form); `row`, a row line for the lane."""
        edit = ["bash", str(self.bin / "lanes-edit.sh")]
        if kind == "bind":
            argv = ["log", "PAUSED", f"lane:{lane}", ARROW, "T252b's rival", "the rival's release"]
        else:
            argv = ["append-line", f"| `{lane}` | harness `{R_SID[lane]}` | Eagle / test / brett "
                                   f"| 2026-11-01T00:00Z | none | handoffs/{lane}.md | T252b's rival row |"]
        w = self.launch("rival", [*edit, *argv], lane)
        w.wait()
        return w


def skill_step_4_block() -> str:
    """The handoff skill's step-4 block that opens with `act-begin` (T431;
    Y:5678), the first fenced `bash` block of its section 4 that holds it."""
    text = (REPO / "skills" / "handoff" / "SKILL.md").read_text(encoding="utf-8")
    section = text.split("\n## 4.", 1)[-1].split("\n## 5.", 1)[0]
    blocks = re.findall(r"```(?:bash|sh)\n(.*?)```", section, re.S)
    found = [b for b in blocks if "act-begin" in b]
    assert found, "skills/handoff/SKILL.md's step 4 has no block that opens with act-begin (T431)"
    return found[0]


@pytest.fixture()
def act_worlds(pg_cluster, tmp_path):
    """T252b's worlds, each on a clone of `tmpl` of its own."""
    made: List[str] = []
    alive: List[ActWorld] = []

    def make() -> ActWorld:
        name = f"t252_{next(_NAMES)}"
        pg_cluster.psql(f"CREATE DATABASE {name} TEMPLATE {W_TEMPLATE};")
        made.append(name)
        found = pg_cluster.psql(f"SELECT to_regclass('{REGISTER}.register_head') IS NOT NULL;", dbname=name)
        assert found.stdout.strip() == "t", (
            f"{W_TEMPLATE} holds no {REGISTER} schema: lane 2's T227 builds it by the bootstrap")
        pg_cluster.psql(f"REVOKE ALL ON DATABASE {name} FROM PUBLIC;\n"
                        f"GRANT CONNECT ON DATABASE {name} TO {CONNECT_TO};\n")
        alive.append(ActWorld(tmp_path / f"world-{len(made)}", Clone(pg_cluster, name)))
        return alive[-1]

    yield make
    for world in alive:
        for w in world.writers:
            if w.ended is None and w.proc.poll() is None:
                os.killpg(w.proc.pid, 9)
    for name in made:
        pg_cluster.drop_database(name)


def race(world: ActWorld, write: ActWrite, rival_lane: str) -> Tuple[Writer, Writer, List[str]]:
    """The act run to `write`, its commit call held while the rival commits
    on `rival_lane`; then let go. Returns the act, which may still run (a
    `lane-start` whose W8 committed waits for the holder), the rival, and
    the held write's id, read from the shim's log, which logs a call before
    its hold."""
    fifo = world.root / "hold.fifo"
    os.mkfifo(str(fifo))
    act = world.act(write, [{"mode": "hold", "match": write.match, "call": 1, "fifo": str(fifo)}])
    held = hold_point(fifo, act)
    calls = [c.get("stdin") or "" for c in act.commit_calls() if write.match in (c.get("stdin") or "")]
    ids = [m.group(1) for m in (re.search(r"commit_write\(\s*-?[0-9]+\s*,\s*'(" + UUID_RE + ")'", s)
                                for s in calls[:1]) if m]
    assert ids, f"the held commit call carries no write id: {calls[:1]}"
    rival = world.rival(write.rival, rival_lane)
    assert rival.code == 0, f"the rival exited {rival.code}: {rival.err[-400:]}"
    held.close()
    return act, rival, ids


@CLIENT
@pytest.mark.parametrize("write", list(ACT_WRITES))
def test_an_act_whose_scope_changed_before_its_commit_writes_nothing(act_worlds, write):
    """TP:5854-5862: the act runs to `write`, held at its commit call; a rival
    from a second session commits on one of its scopes. On release the act's
    commit refuses with 2 and `expectation: <scope> changed at seq <k> by
    <lane>/<verb>`, naming the rival's seq, lane and verb; the held write is
    not in the journal; and the act exits with the code lane 4's arm gives,
    never 0."""
    world = act_worlds()
    w = ACT_WRITES[write]
    act, rival, ids = race(world, w, w.lane)
    act.wait(240)
    k = max(int(r["seq"]) for r in world.c.json(
        f"SELECT coalesce(jsonb_agg(q), '[]'::jsonb) FROM (SELECT seq FROM {REGISTER}.journal "
        f"WHERE write_id = ANY(ARRAY{rival.write_ids()}::uuid[])) q;"))
    scope = f"{'bind' if w.rival == 'bind' else 'row'}:{w.lane.lower()}"
    verb = "log" if w.rival == "bind" else "append-line"
    said = f"expectation: {scope} changed at seq {k} by {w.lane}/{verb}"
    assert said in act.err + act.out, f"[{write}] {said!r} is not in {act.err[-900:]!r}"
    assert all(world.c.value(f"SELECT count(*) FROM {REGISTER}.journal WHERE write_id = '{x}';") == "0"
               for x in ids), f"[{write}] the held write is in the journal"
    if w.code is not None:
        assert act.code == w.code, f"[{write}] the act exited {act.code}, not {w.code}: {act.err[-600:]}"
    assert act.code != 0, f"[{write}] the act exited 0 after its write was refused: {act.err[-600:]}"


@CLIENT
@pytest.mark.parametrize("write", list(ACT_WRITES))
def test_an_act_whose_scopes_held_commits(act_worlds, write):
    """TP:5863-5864: with a rival that touches no scope the write lists,
    another lane's `PAUSED` (or row line), the held write commits."""
    world = act_worlds()
    w = ACT_WRITES[write]
    act, _, ids = race(world, w, R_OTHER[w.lane])
    deadline = time.monotonic() + 60
    while True:
        ended = act.ended is not None
        if all(world.c.value(f"SELECT count(*) FROM {REGISTER}.journal WHERE write_id = '{x}';") == "1"
               for x in ids):
            break
        assert not ended and time.monotonic() < deadline, (
            f"[{write}] the held write {ids} did not commit; the act "
            f"{'exited ' + str(act.code) if ended else 'still runs after 60 s'}: {act.err[-600:]}")
        time.sleep(0.2)


@CLIENT
def test_an_acts_own_earlier_write_never_refuses_its_later_one(estates):
    """Two writes of one act on one scope: the second commits, since the
    first carries the same `act_id`."""
    e = estates()
    act = act_begin(e)
    for tag in ("first", "second"):
        w = e.run(LA, act_write(e, "objects", tag=tag), extra=acted(act, f"objects:{LA.lower()}"))
        assert w.code == 0, f"the {tag} write exited {w.code}: {w.err[-600:]}"
    assert len(e.journal_after(1)) == 2


@CLIENT
def test_a_handoff_request_never_refuses_the_holders_own_handoff(estates):
    """A `HANDOFF-REQUESTED` line is not a lane-kind line: another lane's
    request after the holder's base does not refuse the holder's write on
    `row:<L>` and `bind:<L>`."""
    e = estates()
    act = act_begin(e)
    rival = e.run(LB, ["request-handoff", LA, "--session", session_of(LA)])
    assert rival.code == 0, f"the request exited {rival.code}: {rival.err[-400:]}"
    w = e.run(LA, act_write(e, "row", tag="handoff"), extra=acted(act, f"row:{LA.lower()}", f"bind:{LA.lower()}"))
    assert w.code == 0, f"the holder's write exited {w.code}: {w.err[-600:]}"


@CLIENT
def test_act_variables_change_nothing_in_files_mode(estates):
    """At `mode=files`, a write with `LANES_ACT` and `LANES_EXPECT` set
    behaves as one without them: both commit to origin, and no `psql` call
    is made."""
    e = estates()
    conf = e.root / "files.conf"
    conf.write_text("mode=files\n", encoding="utf-8")
    conf.chmod(0o600)
    files = {"LANES_INDEX_CONFIG": str(conf)}
    plain = e.run(LA, ["append-line", f"NOTE {EM} lane {LA}: files mode, plain (T252)"], extra=files)
    act = dict(files, **acted(f"{'a' * 32}@files", f"row:{LA.lower()}"))
    with_act = e.run(LA, ["append-line", f"NOTE {EM} lane {LA}: files mode, act set (T252)"], extra=act)
    assert (plain.code, with_act.code) == (0, 0), [(w.code, w.err[-300:]) for w in (plain, with_act)]
    assert plain.calls() == [] and with_act.calls() == []
    shown = run_git(e.origin, "show", "main:lanes/LANES.md", env=e.env)
    assert "files mode, plain" in shown and "files mode, act set" in shown


#: The three conditions (Brett's "Accept all three", 6721583757, row 22), each
#: read from its tool's text: the file, and what it must hold.
CONDITIONS = {
    "lane-start-reread": ("lane-start", ("act-begin --rebase",)),
    "skill-step-4": ("skills/handoff/SKILL.md", ("act-begin",)),
    "lane-end-gate": ("lane-end", ("LANES_ACT",)),
}


@pytest.mark.parametrize("condition", list(CONDITIONS))
def test_each_of_the_three_conditions_holds(condition):
    """[lane-start-reread]: `lane-start` re-bases with `act-begin --rebase`
    before its second `binding` read; [skill-step-4]: the skill's step 4
    opens with `act-begin` and re-derives the identity; [lane-end-gate]:
    `lane-end`'s gate inherits `LANES_ACT`. Read from each tool's text
    (FP): red until T428, T431 and T430 land."""
    path, needs = CONDITIONS[condition]
    target = REPO / path
    assert target.exists(), f"[{condition}] no {path} in this tree"
    text = target.read_text(encoding="utf-8", errors="replace")
    for need in needs:
        assert need in text, f"[{condition}] {path} does not hold {need!r}"


#: Before a launch `LANES_ACT` is unset: the tool, and the launch's word.
LAUNCHES = {"exec": ("lane-start", "exec"), "respawn-pane": ("lane-handoff", "respawn-pane")}


@pytest.mark.parametrize("launch", list(LAUNCHES))
def test_lanes_act_is_unset_before_a_launch(launch):
    """`LANES_ACT` is unset before `exec` (`lane-start`) and before
    `respawn-pane` (`lane-handoff`), so the session and its guard never
    inherit it: every line carrying the launch's word unsets it, or runs
    under `env -u LANES_ACT`, within the five lines before. Read from the
    tool's text (FP): red until T428 and T429 land."""
    path, word = LAUNCHES[launch]
    lines = (REPO / path).read_text(encoding="utf-8", errors="replace").split("\n")
    sites = [k for k, l in enumerate(lines) if re.search(rf"\b{re.escape(word)}\b", l)
             and not l.lstrip().startswith("#")]
    assert sites, f"[{launch}] {path} has no {word}"
    bare = [k + 1 for k in sites
            if not any("unset LANES_ACT" in l or "-u LANES_ACT" in l for l in lines[max(0, k - 5):k + 1])]
    assert bare == [], f"[{launch}] {path}:{bare} launch without unsetting LANES_ACT"


@CLIENT
def test_an_act_that_decided_on_canon_lane_is_refused_by_a_row_added_on_its_walk(estates):
    """Alias lines lead `a` to `b` and `b` to `c`, which has a row: an act that
    decided on `canon-lane a` takes the names from `canon-lane --walk a` and
    lists `row:` and `alias:` for each (Y:5624), so a rival `add-row` for `b`
    after the base refuses its write with 2, LR009 naming `row:b`
    (TP:5871-5873; lane 3's batch 7, ask 3)."""
    e = estates(aliases=WALK_ALIASES)
    act = act_begin(e, LC)
    walked = e.run(LC, ["canon-lane", "--walk", WALK_A])
    names = walked.out.split()
    assert walked.code == 0 and names == [WALK_A, WALK_B, LC], (
        f"canon-lane --walk {WALK_A} exited {walked.code} and printed {walked.out!r}: {walked.err[-400:]}")
    expect = [f"{kind}:{name.lower()}" for name in names for kind in ("row", "alias")]
    rival = e.run(WALK_B, ["add-row", w_row(WALK_B)])
    assert rival.code == 0, f"the rival add-row exited {rival.code}: {rival.err[-400:]}"
    w = e.run(LC, act_write(e, "objects", lane=LC, tag="walk"), extra=acted(act, *expect))
    assert w.code == 2 and f"expectation: row:{WALK_B.lower()} changed" in w.err, (w.code, w.err[-600:])


@CLIENT
@pytest.mark.parametrize("case", ["after-loss-cutover", "base-past-n"])
def test_the_client_refuses_an_acts_stale_base_with_2_at_the_snapshot(estates, case):
    """An act whose generation is not the switch's, or whose base is past
    `n`: exit 2 at the snapshot, no commit call, nothing written."""
    e = estates()
    gen = e.c.switch()["generation"]
    n = e.c.head()
    act = (f"{'b' * 32}@{n}:{uuid.uuid4()}" if case == "after-loss-cutover"
           else f"{'b' * 32}@{n + 5}:{gen}")
    state = e.c.state()
    w = e.run(LA, act_write(e, "objects", tag=case), extra=acted(act, f"objects:{LA.lower()}"))
    assert w.code == 2, f"[{case}] exit {w.code}: {w.err[-600:]}"
    assert w.commit_calls() == [] and e.c.state() == state


@pytest.mark.parametrize("case", ["generation", "base-past-head"])
def test_the_commits_act_backstops_are_lr007_act_generation_and_lr004(clones, case):
    """The client's checks bypassed by a direct commit call (T223's
    `Clone`): an act of another generation gets LR007 `act-generation`, a
    base past the head LR004; nothing is written."""
    c = primary(clones)
    entry = c.append(L1, *hold(c, L1))
    head, gen = c.head(), c.switch()["generation"]
    entry["act"] = ({"id": "c" * 32, "base": head, "generation": str(uuid.uuid4())} if case == "generation"
                    else {"id": "c" * 32, "base": head + 5, "generation": gen})
    if case == "generation":
        c.refused(entry, "LR007", "act-generation")
    else:
        c.refused(entry, "LR004", None)


@CLIENT
@pytest.mark.parametrize("case", ["space", "no-break-space"])
def test_a_line_deriving_a_key_that_is_not_a_scope_exits_2_on_lr010_once(estates, case):
    """`append-line` with a row-shaped line whose first backticked token holds
    a space or a no-break space: the commit refuses LR010, the writer exits
    2 naming the path, the line and the key, with one commit call, never
    retried, and nothing written."""
    e = estates()
    gap = " " if case == "space" else chr(0x00A0)
    line = f"| `x{gap}y` | T252 | a key that is not a scope |"
    state = e.c.state()
    w = e.run(LA, ["append-line", line])
    assert w.code == 2, f"[{case}] exit {w.code}: {w.err[-600:]}"
    assert "LR010" in w.err and LANES_MD in w.err and f"row:x{gap}y" in w.err, w.err
    assert len(w.commit_calls()) == 1 and e.c.state() == state


# ============================================================ PHASE N: AT-LR5's other cases and AT-LR009 (T232)
#
# LR005'S RULES AND THE ACT'S KEY, ON `commit_write`'S SIDE (AT-LR5,
# TP:4310-4476; AT-LR009, TP:4834-4941). The test plan puts them in phase W;
# F13's block writes them in phase N, as T223's above, since they check the
# same function (R1's M3; FR-059): each case is a direct `commit_write` call as
# `lanes_w_fx`, in the commit call's own form, on a clone of `tmpl_imported`
# that `Clone.to_primary` brings to `primary`, with the entry built here as the
# client builds it. AT-F5 holds the client's half (T233, T252). The forms are
# lane 1's, read at `refs/l1/T112-fu2` and `refs/l1/R-merge6`, `lanes-index`:
#   * the entry's keys and its `act`, `{id, base, generation, expect}`, the
#     scopes in lower case in the order given: `commit_write`'s head comment
#     and its act checks, and `register_act_of_env`;
#   * a log line's `log_lines` row, and a lane's `object_holds` row on its
#     object, with D19's spellings on a claim's alone: `_register_log_row`,
#     `_register_last_hold` and `register_object_spellings`;
#   * a slot line's `repo_key`, canonical and lower case, and its
#     `repo_spellings`, the spelling as typed first: `_register_slot_row`;
#   * a row's `lanes` row: `_register_lane_row`; the cutover's abort:
#     `switch_to_files` in one SERIALIZABLE transaction (R-merge6);
#   * the stray entries' kinds, verbs and `git_commit`: lane 2's T221
#     (`test_sql_register_schema.py` at line W3b's `8f645fce`).
# THE ROLLBACK'S ENTRY IS WRITTEN NOWHERE YET: each step that needs one FAILS
# UNTIL T304 (`lanes-index rollback`'s transaction) by its own assertion, and
# sends nothing (`rollback_entry`).
# Readings: the lines' texts (a row's cells, `RENAMED`'s words) are this
# module's, in the grammar `lanes-edit.sh` and `parse_log_line` read; only the
# keys they derive are asserted. `rename-lane` and `archive-rows` need step 6's
# derived deletes (ERR-48), which R-merge6 has and T112-fu2 alone has not.
# Every case FAILS UNTIL L1-A6 (T107's `commit_write`, its steps 3b, 5a, 7 and
# 8a) and lane 2's T227 and T228 land, as T223's do; without PostgreSQL 16
# each skips.

LA5, LB5, LC5, LD5 = "L1-t232", "L2-t232", "L3-t232", "L4-t232"
LB5_NEW = "L2b-t232"
FOO = "foo-03"
#: Each lane's session uuid, fixed so a case can name its `sid:` key.
SID5 = {lane: str(uuid.uuid5(uuid.NAMESPACE_URL, f"t232/{lane}")) for lane in (LA5, LB5, LC5, LD5)}
OBJ5, OBJ5_ALIAS, OBJ5_FREE = f"{KEY}#41", f"{ALIAS}#41", f"{OTHER_KEY}#9"
RETIRED_MD, ALIASES_TSV = "lanes/archive/LANES-retired.md", "lanes/aliases.tsv"
STRAY_COMMIT = "3" * 40
ACT_ID = "act-t232"
#: D18's and D19's spellings of a repository as a line types it, the spelling
#: as typed first (`register_repo_spellings`), with `repos.tsv` mapping `r9`.
REPO_SPELLINGS = {KEY: [KEY, ALIAS], ALIAS: [ALIAS, KEY], OTHER_KEY: [OTHER_KEY]}
CLAIM_VERBS = ("CLAIMED", "TAKEOVER")
#: Every table a refused call must leave as it was (AT-LR5's and AT-LR009's oracles).
TABLES5 = ("register_head", "journal", "journal_edits", "journal_files", "journal_scopes", "files",
           "doc_lines", "lanes", "log_lines", "object_holds", "register_lines", "register_switch")
#: A call made while a session holds the head row: past its lock_timeout it would end 55P03.
LOCKED_SQL = "SET lock_timeout = '1500ms';\n" + COMMIT_SQL
#: The cutover's abort, as R-merge6's `cutover --abort` sends it, less its read of the switch.
ABORT_SQL = ("BEGIN ISOLATION LEVEL SERIALIZABLE;\n"
             f"SELECT {REGISTER}.switch_to_files(:client, :seq, :'lane', :'ws');\n"
             "COMMIT;\n")
_ARGS5 = itertools.count(1)


def log_path(lane: str) -> str:
    return f"lanes/log/{lane}.md"


def object_spellings(obj: str) -> Optional[List[str]]:
    """`register_object_spellings`: the object as written, then the same
    object under each of its repository's spellings; a lane's has none."""
    if obj.startswith("lane:"):
        return None
    repo, _, rest = obj.partition("#")
    return [spelling + "#" + rest for spelling in REPO_SPELLINGS.get(repo, [repo])]


def stamp5(c: Clone, minutes_ago: float = 0.0) -> Tuple[str, str]:
    """A log line's UTC, to the second as `log_lines`' primary CHECK takes it,
    and its `utc_ts`, by the database's clock less `minutes_ago`."""
    said = c.value("SELECT to_char(t AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') || '|' || t::text "
                   f"FROM (SELECT date_trunc('second', clock_timestamp() - make_interval(secs => {minutes_ago * 60})) "
                   "AS t) s;")
    utc, utc_ts = said.split("|")
    return utc, utc_ts


def row_text(lane: str, sid: Optional[str], state: str = "ACTIVE", note: str = "") -> str:
    """A `lanes/LANES.md` row: the lane's backticked name first (ROW_AWK), then
    the cells `_register_lane_row` reads: the sessions, the workstation, the
    start, the objects, the handoff and the state."""
    return (f"| `{lane}`{note} | {sid or '—'} | {WS} | 2026-11-10T09:00Z | — | "
            f"lanes/handoff-{lane}.md | {state} |")


class Draft:
    """One entry, built against the clone's files as `register_commit_entry`
    builds it: the edits in order, each touched path's `files` row as it
    stands after them, and the structured rows of the lines written."""

    def __init__(self, c: Clone, lane: str, verb: str, kind: str = "write", **journal) -> None:
        self.c, self.lane, self.verb, self.kind, self.extra = c, lane, verb, kind, journal
        self.images: Dict[str, list] = {}
        self.touched: List[str] = []
        self.gone: List[str] = []
        self.edits: List[dict] = []
        self.rows: Dict[str, list] = {"lanes": [], "log_lines": [], "register_lines": [], "object_holds": []}

    def _image(self, path: str) -> list:
        if path not in self.images:
            final_newline, lines = self.c.file(path)
            self.images[path] = [final_newline, list(lines)]
        return self.images[path]

    def _edit(self, **edit) -> None:
        edit["ord"] = len(self.edits) + 1
        self.edits.append(edit)
        for path in (edit["path"], edit.get("to_path")):
            if path and path not in self.touched:
                self.touched.append(path)

    def lines(self, path: str) -> List[str]:
        return list(self._image(path)[1])

    def append(self, path: str, text: str) -> int:
        image = self._image(path)
        if image[0] is None:
            self._edit(op="create", path=path)
            image[0] = True
        image[1].append(text)
        self._edit(op="append", path=path, new_text=text)
        return len(image[1])

    def replace(self, path: str, line_no: int, text: str) -> None:
        image = self._image(path)
        old = image[1][line_no - 1]
        self._edit(op="replace", path=path, line_no=line_no, old_sha256=sha256(old.encode("utf-8")),
                   new_text=text)
        image[1][line_no - 1] = text

    def delete(self, path: str, line_no: int) -> None:
        image = self._image(path)
        old = image[1].pop(line_no - 1)
        self._edit(op="delete", path=path, line_no=line_no, old_sha256=sha256(old.encode("utf-8")))

    def rename(self, path: str, to_path: str) -> None:
        self.images[to_path] = self._image(path)
        del self.images[path]
        self.gone.append(path)
        self._edit(op="rename", path=path, to_path=to_path)

    def row(self, path: str, lane: str, text: str, line_no: int, *, archived: bool = False,
            aliases: Sequence[str] = ()) -> None:
        """The `lanes` row of a row line, as `_register_lane_row` derives it."""
        cells = [cell.strip(" \t") for cell in text.split("|")]
        ids = re.findall(UUID_RE, cells[2].lower())
        self.rows["lanes"].append({
            "path": path, "line_no": line_no, "raw": text, "lane_key": lane.lower(), "lane": lane,
            "aliases": list(aliases), "home": None, "workstation": cells[3], "started_utc": cells[4],
            "handoff_path": cells[6], "state_phrase": cells[7], "objects_cell": cells[5],
            "session_ids": ids, "last_session": ids[-1] if ids else None, "archived": archived,
            "owner": None})

    def hold(self, obj: str, lane: str, verb: str, utc_ts: Optional[str], path: str, ordinal: int) -> None:
        """A lane's `object_holds` row: its last line on the object."""
        holds = [h for h in self.rows["object_holds"] if (h["object"], h["lane_key"]) != (obj, lane.lower())]
        holds.append({"object": obj, "lane_key": lane.lower(), "lane": lane, "verb": verb, "utc_ts": utc_ts,
                      "file": path, "ordinal": ordinal,
                      "spellings": object_spellings(obj) if verb in CLAIM_VERBS else None, "exempt": False})
        self.rows["object_holds"] = holds

    def log(self, verb: str, lane: str, obj: str, minutes_ago: float = 0.0, *, sid: Optional[str] = None,
            words: str = "") -> int:
        """A line appended to `lane`'s log, its `log_lines` row, and its
        lane's `object_holds` row where the object is not a lane's."""
        path, sid = log_path(lane), sid or SID5[lane]
        utc, utc_ts = stamp5(self.c, minutes_ago)
        text = f"{verb} — lane {lane}, session {sid}@{WS}, {utc}, {obj}" + (f" — {words}" if words else "")
        line_no = self.append(path, text)
        self.rows["log_lines"].append({
            "path": path, "line_no": line_no, "raw": text, "lane": lane, "verb": verb, "session": sid,
            "workstation": WS, "utc": utc, "utc_ts": utc_ts, "object": obj, "ref": "", "payload": "",
            "payload_fields": {}, "free_text": words, "written_lane": lane, "unreadable": False,
            "unreadable_why": None})
        if not obj.startswith("lane:"):
            self.hold(obj, lane, verb, utc_ts, path, line_no)
        return line_no

    def entry(self, act: Optional[dict] = None) -> dict:
        files = []
        for path in self.touched:
            if path in self.gone:
                files.append({"path": path, "present": False, "sha256": None, "final_newline": None})
            else:
                final_newline, lines = self.images[path]
                files.append({"path": path, "present": True, "sha256": sha256(rendered(lines, final_newline)),
                              "final_newline": final_newline})
        extra = dict(self.extra)
        if self.kind == "write":
            extra["args_sha256"] = sha256(f"{self.lane}\0{self.verb}\0{next(_ARGS5)}".encode("utf-8"))
        entry = {"journal": self.c.journal(self.kind, self.verb, self.lane,
                                           message=f"{self.verb} by {self.lane} (T232)", **extra),
                 "not_after": self.c.not_after(), "edits": self.edits, "files": files, **self.rows}
        if act is not None:
            entry["act"] = act
        return entry


# ------------------------------------------------------------ the entries
def claim5(c: Clone, lane: str, obj: str, verb: str = "CLAIMED", act: Optional[dict] = None,
           minutes_ago: float = 0.0) -> dict:
    """`claim` (or `release`): one log line on the object, and the lane's hold."""
    d = Draft(c, lane, "release" if verb == "RELEASED" else "claim")
    d.log(verb, lane, obj, minutes_ago)
    return d.entry(act)


def row_line(c: Clone, lane: str) -> Tuple[int, str]:
    _, lines = c.file(LANES_MD)
    for line_no, text in enumerate(lines, 1):
        if text.startswith(f"| `{lane}`"):
            return line_no, text
    raise AssertionError(f"no row for {lane} in {LANES_MD}")


def set_row_state(c: Clone, lane: str, state: str = "PAUSED", act: Optional[dict] = None) -> dict:
    """`set-row-state`: the lane's row replaced, its state cell changed."""
    d = Draft(c, lane, "set-row-state")
    line_no, _ = row_line(c, lane)
    text = row_text(lane, SID5[lane], state)
    d.replace(LANES_MD, line_no, text)
    d.row(LANES_MD, lane, text, line_no)
    return d.entry(act)


def rename_lane(c: Clone, old: str = LB5, new: str = LB5_NEW) -> dict:
    """`rename-lane <old> <new>` (Amendment 16): the row's key cell
    `` `<new>` *(ex `<old>`, renamed <UTC>)* ``, the log renamed and a
    `RENAMED` line appended to it, and `<old>\\t<new>\\t<UTC>` appended to
    `lanes/aliases.tsv`; with the new lane's `lanes` row and its hold on each
    object its log names, at its last line on it."""
    d = Draft(c, old, "rename-lane")
    line_no, _ = row_line(c, old)
    text = row_text(new, SID5[old], note=f" *(ex `{old}`, renamed 2026-11-10T10:00Z)*")
    d.replace(LANES_MD, line_no, text)
    d.row(LANES_MD, new, text, line_no, aliases=[old])
    d.append(ALIASES_TSV, f"{old}\t{new}\t2026-11-10T10:00:00Z")
    held = c.json(f"SELECT coalesce(json_agg(json_build_array(object, verb, utc_ts::text, ordinal) ORDER BY ordinal), "
                  f"'[]') FROM {REGISTER}.log_lines WHERE file = '{log_path(old)}' AND NOT unreadable "
                  "AND object NOT LIKE 'lane:%';")
    d.rename(log_path(old), log_path(new))
    d.log("RENAMED", new, f"lane:{new}", sid=SID5[old], words=f"renamed from {old}")
    for obj, verb, utc_ts, ordinal in held:
        d.hold(obj, new, verb, utc_ts, log_path(new), ordinal)
    return d.entry()


def archive_rows(c: Clone, lane: str = FOO) -> dict:
    """`archive-rows`: the row moved from `lanes/LANES.md` to
    `lanes/archive/LANES-retired.md`, and its `lanes` row archived there."""
    d = Draft(c, LA5, "archive-rows")
    line_no, text = row_line(c, lane)
    d.delete(LANES_MD, line_no)
    d.row(RETIRED_MD, lane, text, d.append(RETIRED_MD, text), archived=True)
    return d.entry()


def stray_import(c: Clone, lane: str = LA5, obj: str = OBJ5_FREE) -> dict:
    """A `stray-import` (`import --single`), as T221's: a stray commit's line,
    here a claim, taken into the register."""
    d = Draft(c, lane, "import --single", kind="stray-import", git_commit=STRAY_COMMIT)
    d.log("CLAIMED", lane, obj)
    return d.entry()


def stray_revert(c: Clone) -> dict:
    """A `stray-revert` (`render --revert`), as T221's: no edit."""
    return {"journal": c.journal("stray-revert", "render --revert", OPERATOR, git_commit=STRAY_COMMIT,
                                 message="render --revert (T232)"), "not_after": c.not_after()}


def rollback_entry(c: Clone) -> dict:
    """The rollback's entry (S5's step 1; TP's AT-SET fixture: "`commit_write`
    with a `rollback` entry, as REGISTER-WRITER"). No lane has written its
    form yet, so the step FAILS UNTIL T304, `lanes-index rollback`'s
    transaction, and sends nothing (lane 2's brief: never invent a form)."""
    pytest.fail("FAILS UNTIL T304: no rollback entry form is written yet (lanes-index rollback's "
                "transaction), so this step sends nothing", pytrace=False)


def act5(c: Clone, base: int, expect, act_id: str = ACT_ID) -> dict:
    """The entry's `act`, as `register_act_of_env` returns it."""
    return {"id": act_id, "base": base, "generation": c.switch()["generation"], "expect": expect}


# ------------------------------------------------------------ the reads
def tables(c: Clone) -> Dict[str, str]:
    """Each table's digest, row by row."""
    parts = ", ".join(f"'{t}', (SELECT md5(coalesce(string_agg(x::text, ',' ORDER BY x::text), '')) "
                      f"FROM {REGISTER}.{t} x)" for t in TABLES5)
    return c.json(f"SELECT json_build_object({parts});")


def scopes_at(c: Clone, seq: int) -> List[str]:
    return c.json(f"SELECT coalesce(json_agg(scope ORDER BY scope), '[]') FROM {REGISTER}.journal_scopes "
                  f"WHERE seq = {seq};")


def act_ids(c: Clone) -> Dict[int, Optional[str]]:
    said = c.json(f"SELECT coalesce(json_object_agg(seq, act_id), '{{}}') FROM {REGISTER}.journal;")
    return {int(seq): act_id for seq, act_id in said.items()}


def orphans(c: Clone) -> int:
    """`journal_scopes` rows at a seq the journal no longer holds."""
    return int(c.value(f"SELECT count(*) FROM {REGISTER}.journal_scopes s WHERE NOT EXISTS "
                       f"(SELECT 1 FROM {REGISTER}.journal j WHERE j.seq = s.seq);"))


def refused5(c: Clone, entry: dict, code: str, detail: Optional[str], first: Optional[str] = None) -> List[str]:
    """`Clone.refused`, and every table as it was; `first`, where given, is
    the first stderr line's message exactly."""
    before = tables(c)
    lines = c.refused(entry, code, detail)
    if first is not None:
        assert lines[0] == f"ERROR:  {code}: {first}", lines
    after = tables(c)
    assert after == before, f"the refused call changed {[t for t in TABLES5 if after[t] != before[t]]}"
    return lines


def lr5(clones) -> Clone:
    """A clone on `primary`, with no hold on the cases' objects."""
    c = primary(clones)
    held = c.value(f"SELECT count(*) FROM {REGISTER}.object_holds WHERE object IN ('{OBJ5}', '{OBJ5_ALIAS}', "
                   f"'{OBJ5_FREE}') OR spellings && ARRAY['{OBJ5}', '{OBJ5_ALIAS}', '{OBJ5_FREE}'];")
    assert held == "0", f"{IMPORTED} holds {held} row(s) on {OBJ5} or {OBJ5_FREE}, which the cases claim"
    return c


def estate5(clones) -> Clone:
    """AT-LR009's register (TP:4855-4858), on primary: L1, L2 and L3, each with
    a row holding its session uuid and a log opened by `STARTED`; an alias
    line; a row named `foo-03`, holding none; and an object, `opensoft/r9#41`,
    that L2 claimed five hours before. One write, before every case's base."""
    c = lr5(clones)
    d = Draft(c, LA5, "append-line")
    for lane in (LA5, LB5, LC5):
        text = row_text(lane, SID5[lane])
        d.row(LANES_MD, lane, text, d.append(LANES_MD, text))
    text = row_text(FOO, None, "RETIRED")
    d.row(LANES_MD, FOO, text, d.append(LANES_MD, text))
    d.append(ALIASES_TSV, f"L0-t232\t{LA5}\t2026-11-10T08:00:00Z")
    for lane in (LA5, LB5, LC5):
        d.log("STARTED", lane, f"lane:{lane}")
    d.log("CLAIMED", LB5, OBJ5, minutes_ago=300)
    c.committed(d.entry())
    return c


@pytest.fixture()
def head_holder(pg_cluster):
    """A superuser session holding the head row (`SELECT … FOR UPDATE`),
    confirmed in `pg_stat_activity`, rolled back at the test's end."""
    started: List[subprocess.Popen] = []

    def hold(c: Clone, appname: str = "t232-holder") -> subprocess.Popen:
        proc = c.db.session(SUPERUSER, appname)
        proc.stdin.write(f"BEGIN;\nSELECT 1 FROM {REGISTER}.register_head WHERE id = 1 FOR UPDATE;\n")
        proc.stdin.flush()
        started.append(proc)
        deadline = time.monotonic() + 20
        while c.value(f"SELECT count(*) FROM pg_stat_activity WHERE application_name = '{appname}' "
                      "AND state = 'idle in transaction';") != "1":
            assert time.monotonic() < deadline, "the holder never took the head row"
            time.sleep(0.05)
        return proc

    yield hold
    for proc in started:
        if proc.poll() is None:
            try:
                proc.stdin.write("ROLLBACK;\n")
                proc.stdin.close()
            except (BrokenPipeError, ValueError):
                pass
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


# ------------------------------------------------------------ AT-LR5: LR005's rules
def test_lr005_refuses_a_claim_whose_spellings_meet_another_lanes_live_claim(clones):
    """D19: L1 claims `opensoft/r9#41`; L2's claim of `r9#41`, another object
    whose spellings meet L1's, is LR005 `claim-spellings`, and nothing is
    written."""
    c = lr5(clones)
    c.committed(claim5(c, LA5, OBJ5))
    refused5(c, claim5(c, LB5, OBJ5_ALIAS), "LR005", "claim-spellings",
             "a claim's spellings overlap another lane's live claim (D19)")


def test_lr005_refuses_a_hold_over_another_lanes_open_taker(clones):
    """D18: L1's HOLD on `opensoft/r9` commits; L2's later HOLD on it is
    LR005 `main-held`, and nothing is written."""
    c = lr5(clones)
    c.write(LA5, hold(c, LA5, spellings=REPO_SPELLINGS[KEY]))
    refused5(c, c.append(LB5, *hold(c, LB5, spellings=REPO_SPELLINGS[KEY])), "LR005", "main-held",
             "another lane holds main for this repository first (D18)")
    assert c.open_takes(LA5, "hold") == [[KEY, None]] and c.open_takes(LB5, "hold") == []


@pytest.mark.parametrize("case", ["hold-key-first", "landing-key-first", "hold-alias-first",
                                  "landing-alias-first"])
def test_two_spellings_of_one_repository_hold_one_main(clones, case):
    """Lane 1's v2.3, in four forms: L2 takes one spelling of the repository,
    then L4 the other (`r9` after `opensoft/r9`, or the reverse), each line's
    `repo_key` the canonical key and its `repo_spellings` both; L4's take is
    LR005 `main-held`, and main has one taker."""
    c = lr5(clones)
    kind, first = case.split("-", 1)
    typed = [KEY, ALIAS] if first == "key-first" else [ALIAS, KEY]
    pr = None if kind == "hold" else PR
    slot = "HOLD" if kind == "hold" else "LANDING"

    def take(lane: str, repo: str) -> Tuple[str, dict]:
        return line(c, slot, lane, repo=repo, key=KEY, spellings=REPO_SPELLINGS[repo], pr=pr)

    c.write(LB5, take(LB5, typed[0]))
    refused5(c, c.append(LD5, *take(LD5, typed[1])), "LR005", "main-held",
             "another lane holds main for this repository first (D18)")
    assert c.open_takes(LB5, kind) == [[KEY, pr]] and c.open_takes(LD5, kind) == []


def test_lr005_rolls_back_the_head_and_every_row(clones):
    """LR005 is raised after the head moved, the journal row went in, the
    edits applied and the structured rows went in (steps 4 to 7): the head,
    the journal, its edits and files, `doc_lines`, `log_lines` and
    `object_holds` all equal their values before, and the write id is absent."""
    c = lr5(clones)
    c.committed(claim5(c, LA5, OBJ5))
    head, before = c.head(), tables(c)
    proc, write_id = c.commit(claim5(c, LB5, OBJ5_ALIAS))
    assert proc.returncode == 3 and proc.stderr.startswith("ERROR:  LR005: "), proc.stderr
    after = tables(c)
    for table in TABLES5:
        assert after[table] == before[table], f"{table} changed under LR005"
    assert c.head() == head
    assert c.value(f"SELECT count(*) FROM {REGISTER}.journal WHERE seq > {head} OR write_id = '{write_id}';") == "0"
    assert c.value(f"SELECT count(*) FROM {REGISTER}.doc_lines WHERE path = '{log_path(LB5)}';") == "0"


def test_lr005_does_not_fire_on_a_released_claims_spellings(clones):
    """L1 claims `opensoft/r9#41` and releases it; L2's claim of `r9#41` then
    commits: a released hold carries no spellings and is no live claim."""
    c = lr5(clones)
    c.committed(claim5(c, LA5, OBJ5))
    c.committed(claim5(c, LA5, OBJ5, verb="RELEASED"))
    seq = c.committed(claim5(c, LB5, OBJ5_ALIAS))
    said = c.json(f"SELECT json_agg(json_build_array(object, lane_key, verb, superseded_by, spellings) "
                  f"ORDER BY object, lane_key) FROM {REGISTER}.object_holds WHERE object IN ('{OBJ5}', '{OBJ5_ALIAS}');")
    assert said == [[OBJ5, LA5.lower(), "RELEASED", None, None],
                    [OBJ5_ALIAS, LB5.lower(), "CLAIMED", None, [OBJ5_ALIAS, OBJ5]]], said
    assert seq == c.head()


@pytest.mark.parametrize("token", ["one-live-claim", "claim-spellings", "main-held"])
def test_each_claim_and_main_rule_lr005_carries_its_detail_token(clones, token):
    """U7: each rule's LR005 names it in its message, and its DETAIL is
    exactly the rule's token: L2's claim of L1's object (one_live_claim's
    23505, raised again), of its other spelling (D19), and L2's HOLD behind
    L1's (D18)."""
    c = lr5(clones)
    if token == "main-held":
        c.write(LA5, hold(c, LA5, spellings=REPO_SPELLINGS[KEY]))
        refused5(c, c.append(LB5, *hold(c, LB5, spellings=REPO_SPELLINGS[KEY])), "LR005", token,
                 "another lane holds main for this repository first (D18)")
        return
    c.committed(claim5(c, LA5, OBJ5))
    if token == "claim-spellings":
        refused5(c, claim5(c, LB5, OBJ5_ALIAS), "LR005", token,
                 "a claim's spellings overlap another lane's live claim (D19)")
    else:
        lines = refused5(c, claim5(c, LB5, OBJ5), "LR005", token)
        assert lines[0].startswith("ERROR:  LR005: the object is held (one_live_claim): "), lines


# ------------------------------------------------------------ AT-LR009: the act's key
MALFORMED_ACTS = {
    "id-with-an-at": {"id": "act@t232"},
    "id-with-a-space": {"id": "act t232"},
    "id-not-a-string": {"id": 232},
    "base-a-string": {"base": "head"},
    "base-negative": {"base": -1},
    "base-not-whole": {"base": 1.5},
    "generation-not-a-uuid": {"generation": "generation-t232"},
    "expect-not-a-list": {"expect": "row:l1-t232"},
    "element-not-a-string": {"expect": [232]},
    "element-a-star": {"expect": ["*"]},
    "element-row-with-no-name": {"expect": ["row:"]},
    "element-with-white-space": {"expect": ["row:l1 t232"]},
    "on-an-import": None,
}


@pytest.mark.parametrize("case", list(MALFORMED_ACTS))
def test_a_malformed_act_is_refused_lr004_before_the_head_lock(clones, head_holder, case):
    """Each of the test plan's rewrites of the `act` key, and an `act` on an
    import entry, by a direct call: LR004, `the entry's act is not well
    formed`, while a session holds the head row throughout, so a check after
    the lock would end 55P03 at the call's lock_timeout; nothing is written."""
    c = lr5(clones)
    head = c.head()
    if case == "on-an-import":
        edits, files, _ = c.appended(LANES_MD, ["# Lanes (T232)"], create=True)
        entry = {"journal": c.journal("import", "import", OPERATOR, git_commit=GIT_COMMIT, git_tree=GIT_TREE),
                 "not_after": c.not_after(), "edits": edits, "files": files,
                 "act": act5(c, head, [f"row:{LA5.lower()}"])}
    else:
        act = act5(c, head, [f"row:{LA5.lower()}"])
        act.update(MALFORMED_ACTS[case])
        if case == "base-a-string":
            act["base"] = str(head)
        entry = claim5(c, LA5, OBJ5_FREE, act=act)
    before = tables(c)
    head_holder(c)
    write_id = str(uuid.uuid4())
    proc = c.call(LOCKED_SQL, base=head, wid=write_id, client=c.client(), gen=c.switch()["generation"],
                  entry=json.dumps(entry, ensure_ascii=False))
    lines = proc.stderr.splitlines()
    assert proc.returncode == 3, f"exit {proc.returncode}: {proc.stderr.strip()}"
    assert lines[:1] == ["ERROR:  LR004: the entry's act is not well formed"], lines
    assert "55P03" not in proc.stderr, proc.stderr
    assert tables(c) == before
    assert c.value(f"SELECT count(*) FROM {REGISTER}.journal WHERE write_id = '{write_id}';") == "0"


def test_act_id_is_the_acts_id_on_a_write_and_null_on_every_other_entry(clones):
    """`journal.act_id`: a write made in an act stores the act's id as
    given; a write outside any act, the import, the cutover, a
    `stray-import`, a `stray-revert` and a rollback store NULL."""
    c = estate5(clones)
    said = c.json(f"SELECT json_object_agg(kind, seq) FROM (SELECT kind, max(seq) AS seq FROM {REGISTER}.journal "
                  "WHERE kind IN ('import', 'cutover') GROUP BY kind) k;")
    in_act = c.committed(claim5(c, LA5, OBJ5_FREE, act=act5(c, c.head(), [])))
    outside = c.committed(set_row_state(c, LA5))
    stray = c.committed(stray_import(c, LC5, f"{OTHER_KEY}#10"))
    revert = c.committed(stray_revert(c))
    ids = act_ids(c)
    assert ids[in_act] == ACT_ID
    for name, seq in (("a write outside any act", outside), ("the import", said["import"]),
                      ("the cutover", said["cutover"]), ("a stray-import", stray), ("a stray-revert", revert)):
        assert ids[seq] is None, f"{name}, seq {seq}, stores act_id {ids[seq]!r}"
    rollback = c.committed(rollback_entry(c))
    assert act_ids(c)[rollback] is None


def test_the_act_id_checks_refuse_an_act_id_on_another_kind_and_a_malformed_one(clones):
    """As the admin under `SET ROLE lanes_register_owner`: `act_id` set on the
    cutover's row fails 23514 on `journal_act_id_write`, and a write's set to
    `a@b` or `a b` fails 23514 on `journal_act_id_check`."""
    c = estate5(clones)
    write = c.committed(claim5(c, LA5, OBJ5_FREE, act=act5(c, c.head(), [])))
    cases = [("kind = 'cutover'", ACT_ID, "journal_act_id_write"),
             (f"seq = {write}", "a@b", "journal_act_id_check"),
             (f"seq = {write}", "a b", "journal_act_id_check")]
    for where, value, constraint in cases:
        proc = c.db.psql("\\set VERBOSITY verbose\nSET ROLE lanes_register_owner;\n"
                         f"UPDATE {REGISTER}.journal SET act_id = '{value}' WHERE {where};\n", check=False)
        assert proc.returncode != 0 and "ERROR:  23514: " in proc.stderr, f"{where} = {value!r}: {proc.stderr}"
        assert f'violates check constraint "{constraint}"' in proc.stderr, proc.stderr
    assert act_ids(c)[write] == ACT_ID


@pytest.mark.parametrize("case", ["set-row-state", "lane-kind-line", "claim", "takeover", "rename-lane",
                                  "archive-rows"])
def test_each_entry_stores_the_keys_its_lines_derive(clones, case):
    """Steps 5a and 8a: each committed entry's `journal_scopes` holds exactly
    the keys the scopes table's rules give its lines, step 5a's old side and
    step 8a's new side, `objects:` for every lane holding an object it wrote
    a hold for, and never a key the client sent."""
    c = estate5(clones)
    l1, l2, l3, l2b = (lane.lower() for lane in (LA5, LB5, LC5, LB5_NEW))
    if case == "set-row-state":
        entry, want = set_row_state(c, LA5), {f"row:{l1}", f"sid:{SID5[LA5]}"}
    elif case == "lane-kind-line":
        d = Draft(c, LA5, "log")
        d.log("PAUSED", LA5, f"lane:{LA5}")
        entry, want = d.entry(), {f"bind:{l1}", f"sid:{SID5[LA5]}"}
    elif case == "claim":
        entry, want = claim5(c, LA5, OBJ5_FREE), {f"objects:{l1}"}
    elif case == "takeover":
        d = Draft(c, LC5, "claim")
        d.log("TAKEOVER", LC5, OBJ5)
        entry, want = d.entry(), {f"objects:{l3}", f"objects:{l2}"}
    elif case == "rename-lane":
        entry = rename_lane(c)
        want = {f"row:{l2}", f"row:{l2b}", f"sid:{SID5[LB5]}", f"bind:{l2}", f"bind:{l2b}",
                f"objects:{l2}", f"objects:{l2b}", f"alias:{l2}", f"alias:{l2b}"}
    else:
        entry, want = archive_rows(c), {f"row:{FOO}", f"archive:{FOO}", "archive:foo-3"}
    seq = c.committed(entry)
    got = scopes_at(c, seq)
    assert set(got) == want, f"[{case}] stores {got}, not {sorted(want)}"
    if case == "claim":
        assert not [k for k in got if k.startswith("bind:")], got


def test_an_import_a_cutover_and_a_rollback_store_only_the_star_key(clones):
    """`*` is the one key of an import, a cutover and a rollback."""
    c = clones()
    imported = c.head()
    assert c.value(f"SELECT kind FROM {REGISTER}.journal WHERE seq = {imported};") == "import"
    assert scopes_at(c, imported) == ["*"]
    cutover = c.to_primary()
    assert scopes_at(c, cutover) == ["*"]
    rollback = c.committed(rollback_entry(c))
    assert scopes_at(c, rollback) == ["*"]


def test_a_stray_import_stores_its_keys_and_a_stray_revert_none(clones):
    """A `stray-import` stores its lines' keys as a write does; a
    `stray-revert` stores none."""
    c = estate5(clones)
    stray = c.committed(stray_import(c))
    assert scopes_at(c, stray) == [f"objects:{LA5.lower()}"]
    revert = c.committed(stray_revert(c))
    assert scopes_at(c, revert) == []


def test_an_aborted_cutover_and_a_reimport_leave_no_scopes_at_a_deleted_seq(clones):
    """The cascade: a cutover aborted by `switch_to_files`, then an import's
    reset before any confirmed cutover, each succeed and leave no
    `journal_scopes` row at a seq the journal no longer holds."""
    c = clones()
    imported = c.head()
    edits, files, _ = c.appended(STORE, ["primary"])
    cutover = c.committed({"journal": c.journal("cutover", "cutover", OPERATOR), "not_after": c.not_after(),
                           "edits": edits, "files": files})
    assert scopes_at(c, cutover) == ["*"]
    proc = c.call(ABORT_SQL, client=c.client(), seq=cutover, lane=OPERATOR, ws=WS)
    assert (proc.returncode, proc.stdout.strip()) == (0, str(imported)), proc.stderr
    assert scopes_at(c, cutover) == [] and orphans(c) == 0
    edits, files, _ = c.appended(LANES_MD, ["# Lanes (T232's import)"], create=True)
    seq = c.committed({"journal": c.journal("import", "import", OPERATOR, git_commit=GIT_COMMIT, git_tree=GIT_TREE),
                       "not_after": c.not_after(), "edits": edits, "files": files})
    assert scopes_at(c, seq) == ["*"] and orphans(c) == 0
    assert c.value(f"SELECT count(*) FROM {REGISTER}.journal_scopes WHERE seq > {seq};") == "0"


def test_lr009_names_the_first_changed_scope_its_seq_lane_and_verb(clones):
    """Step 3b: with two entries outside the act after its base, at k1 < k2,
    each touching `row:l1`, LR009 names k1, its lane and its verb; with one
    entry touching two listed scopes, it names the first in byte order."""
    c = estate5(clones)
    row1, sid1 = f"row:{LA5.lower()}", f"sid:{SID5[LA5]}"
    base = c.head()
    k1 = c.committed(set_row_state(c, LA5, "PAUSED"))
    k2 = c.committed(set_row_state(c, LA5, "ACTIVE"))
    assert k1 < k2
    refused5(c, claim5(c, LA5, OBJ5_FREE, act=act5(c, base, [row1])), "LR009", None,
             f"expectation: {row1} changed at seq {k1} by {LA5}/set-row-state")
    base = c.head()
    k3 = c.committed(set_row_state(c, LA5, "PAUSED"))
    assert {row1, sid1} <= set(scopes_at(c, k3))
    refused5(c, claim5(c, LA5, OBJ5_FREE, act=act5(c, base, [sid1, row1])), "LR009", None,
             f"expectation: {row1} changed at seq {k3} by {LA5}/set-row-state")


def test_an_entry_outside_any_act_refuses_an_acts_write_lr009(clones):
    """Step 3b: an entry after the act's base, made outside any act
    (`act_id` NULL), that touched `row:l1` refuses the act's write with
    LR009; an `expect` sent as `ROW:L1` is compared in lower case and refused
    the same way."""
    c = estate5(clones)
    row1 = f"row:{LA5.lower()}"
    base = c.head()
    k = c.committed(set_row_state(c, LA5))
    assert act_ids(c)[k] is None
    for expect in ([row1], [row1.upper()]):
        refused5(c, claim5(c, LA5, OBJ5_FREE, act=act5(c, base, expect)), "LR009", None,
                 f"expectation: {row1} changed at seq {k} by {LA5}/set-row-state")


def test_a_star_key_after_the_base_is_reported_as_the_first_listed_scope(clones):
    """`*` after the base: an act based at the import, before the cutover's
    `*`, is refused LR009 naming its first listed scope, not the first in
    byte order, at the cutover's seq, by the cutover's lane and verb."""
    c = clones()
    base = c.head()
    cutover = c.to_primary()
    assert cutover == base + 1
    expect = [f"row:{LC5.lower()}", f"row:{LA5.lower()}"]
    refused5(c, claim5(c, LA5, OBJ5_FREE, act=act5(c, base, expect)), "LR009", None,
             f"expectation: {expect[0]} changed at seq {cutover} by {OPERATOR}/cutover")


def test_an_empty_expectation_records_act_id_and_checks_nothing(clones):
    """An empty `LANES_EXPECT`, sent as `expect: []`, records the act's id and
    checks nothing, so the write commits after an entry that touched
    `row:l1`."""
    c = estate5(clones)
    base = c.head()
    c.committed(set_row_state(c, LA5))
    seq = c.committed(claim5(c, LA5, OBJ5_FREE, act=act5(c, base, [])))
    assert seq == c.head() and act_ids(c)[seq] == ACT_ID


def test_lr002_comes_before_lr009_after_a_rollback(clones):
    """A direct call after a rollback's entry has set the switch to `files`
    gets LR002, not LR009, though an entry after its base touched its listed
    scope: step 3 comes before step 3b."""
    c = estate5(clones)
    base = c.head()
    c.committed(set_row_state(c, LA5))
    c.committed(rollback_entry(c))
    sw = c.switch()
    assert (sw["mode"], sw["marker_state"]) == ("files", "removing"), sw
    refused5(c, claim5(c, LA5, OBJ5_FREE, act=act5(c, base, [f"row:{LA5.lower()}"])), "LR002", None,
             "register switch is files with the marker removing")


# ============================================================ PHASE W, NO ENGINE: `register commit`'s path refusal (T243d)
#
# LANE 1'S FOLLOW-UP 2 (line R's merge13, `3a30ba89`, tag `l1-007-R-pathre`;
# #165 6783763467): `register commit` refuses with 2, before the store opens,
# a path that holds a control character, U+0085, U+2028 or U+2029, where
# `changes.tsv` stages it and on either side of a `renames.tsv` line
# (`register_path_unrenderable`, called from `read_attempt_dir`). No render of
# the register could write such a path as one `file=` row, and the database's
# CHECKs admit every character but `/`, so this refusal is the only guard.
# Lane 1: "no test covers the attempt directory's path checks".
#
# NO ENGINE. T203's flipped copy runs `register commit` under a `mode=primary`
# configuration whose URLs name 127.0.0.1, with a `psql` first on `PATH` that
# only logs its calls: "before the store opens" is that log left empty. Each
# attempt directory is contract section 3.3's, whole, as lane 1's hand checks
# build it (`runs/R-pathre/mkattempt.py`): a scratch tree at seq n, then
# `snapshot`, `not_after`, `changes.tsv`, `images/`, `files`, `msg` and
# `author`. A `changes` case adds a log at the path (an A line). A `renames`
# case appends a line to its lane's log (an M line) and names the path on one
# side of a `renames.tsv` line that `changes.tsv` does not name, since a side
# that `changes.tsv` also stages is refused first, as `changes.tsv stages`.
# The place asserted is lane 1's text: the file, the side, and the path as
# `repr` prints it. On merge12 a `changes` case reaches the store, and a
# `renames` case is refused by the D and A check, which names no side, so
# each FAILS there by its own assertion; from merge13 on each passes.

PATH_LANE, PATH_WS, PATH_N = "L1-t243d", "ws-t243d", 41
#: Each case: the file that names the path, the side of the `renames.tsv`
#: line (None for `changes.tsv`), and the character the path holds.
UNRENDERABLE = {
    "changes-u0001": ("changes.tsv", None, 0x0001),
    "changes-u0085": ("changes.tsv", None, 0x0085),
    "changes-u2028": ("changes.tsv", None, 0x2028),
    "changes-u2029": ("changes.tsv", None, 0x2029),
    "renames-old-u2028": ("renames.tsv", "<from>", 0x2028),
    "renames-new-u2029": ("renames.tsv", "<to>", 0x2029),
}
#: The prefixes of the test's own environment that the run of `lanes-index` does not inherit.
PATH_DROPPED = ("GIT_", "PG", "LANES_", "TMUX", "RULE6_", "FAKE_PSQL", "CLAUDE_", "PROJECTS_ROOT",
                "XDG_", "OPENREPOTOOLS_BIN_DIR", "AGENT_PROTOCOL_ROOT")


def unrenderable_attempt(root: Path, case: str, env: dict) -> Tuple[Path, List[str], str]:
    """`case`'s whole attempt directory under `root`, the `register commit`
    argv that sends it, and the place its refusal must name."""
    where, side, code = UNRENDERABLE[case]
    bad = f"lanes/log/a{chr(code)}b.md"
    att = root / "attempt"
    tree = att / "tree"
    tree.mkdir(parents=True)
    sid = session_of(PATH_LANE)

    def log_line(verb: str, lane: str, utc: str, what: str) -> str:
        return f"{verb} {EM} lane {lane}, session {sid}@{PATH_WS}, {utc}, {what}\n"

    def log_head(lane: str) -> str:
        return f"# lane {lane} {EM} object log (lane-collision-protocol Amendment 7)\n"

    log = f"lanes/log/{PATH_LANE}.md"
    register = {"lanes/LANES.md": "# Lanes\n", "lanes/repos.tsv": "# alias\towner/repo\nr9\topensoft/r9\n",
                "lanes/aliases.tsv": "# old\tnew\tutc\n", "lanes/log/README.md": "# logs\n",
                log: log_head(PATH_LANE) + log_line("STARTED", PATH_LANE, "2026-11-01T00:00:00Z",
                                                    f"lane:{PATH_LANE} home opensoft/r9")}
    for path, text in register.items():
        (tree / path).parent.mkdir(parents=True, exist_ok=True)
        (tree / path).write_bytes(text.encode("utf-8"))
    run_git(tree, "init", "-q", "-b", "main", env=env)
    run_git(tree, "add", "-A", env=env)
    run_git(tree, "commit", "-q", "-m", f"register snapshot at seq {PATH_N}", env=env)
    if where == "changes.tsv":
        path, verb, old = bad, "log", None
        new = (log_head("added") + log_line("STARTED", "added", "2026-11-09T12:00:00Z",
                                            "lane:added home opensoft/r9")).encode("utf-8")
    else:
        path, verb, old = log, "claim", register[log].encode("utf-8")
        new = old + log_line("CLAIMED", PATH_LANE, "2026-11-09T12:00:00Z", "opensoft/r9#7").encode("utf-8")
        sides = (bad, f"lanes/log/{PATH_LANE}-moved.md") if side == "<from>" else (log, bad)
        (att / "renames.tsv").write_bytes(("\t".join(sides) + "\n").encode("utf-8"))
    image = att / "images" / path
    image.parent.mkdir(parents=True)
    image.write_bytes(new)
    new_blob = run_git(tree, "hash-object", "--no-filters", str(image), env=env).strip()
    base_blob = "0" * 40 if old is None else run_git(tree, "rev-parse", f"HEAD:{path}", env=env).strip()
    (att / "changes.tsv").write_bytes(
        f"{'A' if old is None else 'M'}\t{path}\t{base_blob}\t{new_blob}\n".encode("utf-8"))
    (att / "files").write_bytes(f"{path}\t1\t{hashlib.sha256(new).hexdigest()}\n".encode("utf-8"))
    write_id, generation, clock = str(uuid.uuid4()), str(uuid.uuid4()), int(time.time())
    repos_blob = run_git(tree, "rev-parse", "HEAD:lanes/repos.tsv", env=env).strip()
    snapshot = {"format": 1, "generation": generation, "write_id": write_id, "switch": "primary",
                "marker": "present", "n": PATH_N, "clock": clock, "not_after": clock + 10, "schema": 1,
                "repos_blob": repos_blob, "c": 2, "n_a": 1}
    (att / "snapshot").write_text("".join(f"{k}={v}\n" for k, v in snapshot.items()), encoding="utf-8")
    (att / "not_after").write_text(f"{clock + 10}\n", encoding="utf-8")
    (att / "msg").write_text(f"LANES({PATH_LANE}@{PATH_WS}): {verb} {EM} T243d's case\n", encoding="utf-8")
    (att / "author").write_text("T243d Tester <t243d@example.invalid>\n", encoding="utf-8")
    argv = ["register", "commit", "--write-id", write_id, "--generation", generation, "--lane", PATH_LANE,
            "--verb", verb, "--args-sha256", hashlib.sha256(case.encode("utf-8")).hexdigest(),
            "--workstation", PATH_WS, str(att)]
    place = f"changes.tsv stages {bad!r}" if side is None else f"renames.tsv line 1's {side} is {bad!r}"
    return att, argv, place


@CLIENT
@pytest.mark.parametrize("case", list(UNRENDERABLE))
def test_register_commit_refuses_an_unrenderable_path_with_2_before_the_store_opens(tmp_path, case):
    """Lane 1's follow-up 2 (#165 6783763467): an attempt directory whose
    `changes.tsv` stages a path holding U+0001, U+0085, U+2028 or U+2029
    ([changes-*]), or whose `renames.tsv` line holds U+2028 on its `<from>`
    side ([renames-old-u2028]) or U+2029 on its `<to>` side
    ([renames-new-u2029]), makes `register commit` exit 2, with stderr naming
    the file, the side and the path, and no `psql` call: the store is never
    opened."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(PATH_DROPPED)}
    (tmp_path / "home").mkdir()
    env.update(HOME=str(tmp_path / "home"), XDG_STATE_HOME=str(tmp_path / "state"),
               XDG_CONFIG_HOME=str(tmp_path / "config"), GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME="T243d", GIT_AUTHOR_EMAIL="t243d@example.invalid",
               GIT_COMMITTER_NAME="T243d", GIT_COMMITTER_EMAIL="t243d@example.invalid", LC_ALL="C")
    _att, argv, place = unrenderable_attempt(tmp_path, case, env)
    copy = flipped_copy(LANES_INDEX, tmp_path / "bin", True)
    (tmp_path / "bin" / "repos.tsv").write_text("# alias\towner/repo\n", encoding="utf-8")
    conf = tmp_path / "lanes-index.conf"
    conf.write_text("mode=primary\nregister_url=postgresql://lanes_w_t243d@127.0.0.1:9/t243d\n"
                    "reader_url=postgresql://lanes_r_t243d@127.0.0.1:9/t243d\n", encoding="utf-8")
    conf.chmod(0o600)
    calls = tmp_path / "psql.log"
    _write(tmp_path / "fakebin" / "psql", f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{calls}"\nexit 2\n')
    env.update(LANES_INDEX_CONFIG=str(conf),
               PATH=str(tmp_path / "fakebin") + os.pathsep + env.get("PATH", os.defpath))
    r = subprocess.run([sys.executable, str(copy), *argv], cwd=str(tmp_path), env=env, capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120, stdin=subprocess.DEVNULL, check=False)
    sent = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    assert r.returncode == 2, (
        f"[{case}] register commit exited {r.returncode}, not 2, after {len(sent)} psql calls: {r.stderr[-900:]}")
    assert sent == [], f"[{case}] register commit called psql before it refused: {sent}"
    assert place in r.stderr, f"[{case}] stderr does not name {place!r}: {r.stderr[-900:]}"
