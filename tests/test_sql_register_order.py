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
"""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import uuid
from typing import List, Optional, Sequence, Tuple

import pytest

from pgcluster import Database

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
