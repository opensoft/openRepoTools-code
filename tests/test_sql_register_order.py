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

THE MODULE ALSO HOLDS, each at its own section below: T243's test 4, C10,
D19 and section 4.1 (phase W, the client's writers on a real register); T232's
AT-LR5 and AT-LR009 (phase N, `commit_write` called directly, as here); T248's
AT-F14 (phase W); and T252's AT-F5 group B (phase W).
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

from pgcluster import Database
from sql_register_helpers import (LANES_INDEX, PSQL_SHIM, PSQL_SHIM_CONTROL, PSQL_SHIM_ENDS,
                                  PSQL_SHIM_LOG, REPO, flipped_copy)

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
    for path in sorted(files):
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
        return sum(1 for p in self.ready.iterdir() if p.name.endswith(suffix) == (suffix == ".go"))

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
                 repos: str = REPOS_T0) -> None:
        self.root, self.c = root, c
        self.files = estate_files(lanes)
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


#: AT-4 (f), with lane 3's text for T243 (#165 6772120103, "T243 (:2232)";
#: 6771569269): each case's lines before, the line `append-line` sends, and
#: what it must do: refused with 2 and nothing written, or committed with 0,
#: taking or freeing what Q17 (B) says (`main_slots` for the writer's lane).
NO_REPO = {
    "hold-no-repo": ([], "HOLD {em} lane {lane} ({ws}), {utc}: for a frozen window", 2, None),
    "landing-no-repo": ([], "LANDING {em} lane {lane}, session {sid}@{ws}, {utc}, PR #{pr}", 2, None),
    "take-no-utc": ([], "HOLD {em} lane {lane} ({ws}): {key} main for a frozen window", 2, None),
    "free-text": ([], "NOTE {em} lane {lane}: the register's free text (T243)", 0, []),
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
    text. Lane 3's text (6771569269): a `LANDED` naming no repository commits
    0 and frees its pair in `main_slots`; a `HOLD RELEASED` naming none and a
    `LANDING` naming no PR commit 0 and take or free nothing."""
    e = estates()
    before_lines, text, code, slots = NO_REPO[case]

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
