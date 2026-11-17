# SPDX-License-Identifier: Apache-2.0
"""The guard's quote of form 2's stderr ends on a character boundary (007, T507).

`reg_guard_prefetch` in `lanes-edit.sh` quotes what `lanes-index register
read --for guard --prefetch` printed on stderr, `RG_SAID`, in the refusals
of rows 2 and 78, in S3's outage text and in the files-mode warning: its
first 1000 bytes as one line, newline, CR and tab made spaces and every
other C0 byte dropped. Lane 3's ruling on item 31, (a)
(opensoft/openRepoTools#165 comment 6826938656), puts that cut on a
character boundary, as lane 1's 4.23 states it at register-cli.md:768.
Before T507's NIT round the cut was `head -c 1000` alone, so a stderr whose
1000th byte fell inside a UTF-8 character was quoted with that character's
first bytes, and the quote ended in bytes that are not UTF-8.

The function that runs here is the file's own, cut out of `lanes-edit.sh`
and run in `bash`, with stand-ins for what it calls: a configured
workstation, a stand-in `lanes-index` that prints the case's stderr and
exits 64, and `reg_guard_files`, whose argument, the files-mode warning's
`exited 64 (<quote>)`, is written to a file. Each case runs under the C
locale and under a UTF-8 one, and with and without form 2's fallback line
ahead of what it said. Where the UTF-8 locale is not installed, bash falls
back to C with a `setlocale` warning, so a UTF-8 id would pass as a second
C run and prove nothing about that locale: it is skipped instead, and the
skip quotes bash's warning (lane 5's Claude pre-review of P19, NIT 6). The
cases whose 1000th byte splits a character are red on the cut before the
NIT round; the others are its controls, green before and after.

The next case holds S3's outage text to the register-service spec's SHALL,
"The guard fails closed during a database outage": the refusal names the
store, the cause and the two ways out, and the first of them is to wait for
the database (lane 5's answer to spec#58's disagreement 2). It runs
`reg_guard_s3` as the file writes it, cut out and run in `bash` with the
same stand-ins, and is red on the text that named the status and rollback
commands alone.

The cases after it are lane 3's Codex review of T507's chain 2 at
`4801cb83` (#165 6933947760), each held in this module where its fixtures
reach: the too-late refusal's words (SHOULD 5), run through
`reg_guard_prefetch` as the file writes it, with a stand-in `lanes-index`
that ends 2; and form C's tip read against a `git` that never answers
(SHOULD 2), run in `lanes-index` loaded as a module, as the suite's other
modules load it; and E1's first cause line (SHOULD 3), run through
`cmd_register_read` in that module, with its configuration, its
declaration, its `T0` and its direct read stood in for; and the post-bind
refill off primary (SHOULD 4), `guard_bind_refill` with the file's own
`reg_prefetch` and `reg_read_files`, cut out and run twice in `bash`, as its
two call sites run it, against a stand-in `lanes-index`.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None, reason="the guard is a bash command")]

#: The quote's bound in bytes (contract 3.6; register-cli.md:768).
LIMIT = 1000

#: Form 2's fallback line, which the guard relays once, on a line of its own,
#: and leaves out of the quote (T507's part F1).
FALLBACK = b"guard: direct (service unavailable)"

#: The UTF-8 locale of each case's second run. Where it is not installed the
#: run is skipped (`_locale_missing`).
UTF8 = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"

#: Three characters, built from their code points: two, three and four bytes
#: in UTF-8.
E_ACUTE, EURO, GRIN = chr(0xE9), chr(0x20AC), chr(0x1F600)

#: What `reg_guard_prefetch` calls, stood in for, and the globals it reads.
#: Its arguments: the stand-in `lanes-index`, the warning's file, the quote's
#: file and the cache file.
STANDINS = r'''
set -u
qc_stub="$1"; qc_warn="$2"; qc_said="$3"
SE_CACHE_FILE="$4"; LANES_REPO="${4%/*}"; SCRIPT_DIR="${4%/*}"; G_WINNAME=lane-q
GUARD_BUDGET_START_MS=3750; REG_MODE=""; REG_STORE=""
reg_config_present() { return 0; }
lanes_index_bin() { printf '%s\n' "$qc_stub"; }
reg_flush() { :; }
reg_guard_files() { printf '%s' "$1" > "$qc_warn"; REG_MODE=files; REG_STORE=files; }
reg_guard_outage() { printf '%s' "outage" > "$qc_warn"; return 2; }
guard_refuse() { printf '%s' "$1" > "$qc_warn"; return 2; }
guard_bypass() { :; }
'''

RUN = r'''
reg_guard_prefetch
printf '%s' "$RG_SAID" > "$qc_said"
'''


def _function(name: str) -> str:
    """One top-level function of `lanes-edit.sh` as it is written there."""
    text = (REPO / "lanes-edit.sh").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\(\) \{{[^\n]*\n.*?^\}}\n", text, re.M | re.S)
    assert match, f"`{name}() {{` ... `}}` is no longer in lanes-edit.sh"
    return match.group(0)


@functools.lru_cache(maxsize=None)
def _locale_missing(locale: str) -> str:
    """Bash's own `setlocale` warning where it cannot take `locale` and falls
    back to C, else "": asked of `bash -c :` once per locale, in the case's
    own environment, `PATH` and `LC_ALL` alone."""
    res = subprocess.run(["bash", "-c", ":"], capture_output=True,
                         env={"PATH": os.environ["PATH"], "LC_ALL": locale},
                         timeout=60, check=False)
    said = res.stderr.decode("utf-8", "replace").splitlines()
    return next((line.strip() for line in said if "setlocale" in line), "")


def _at(prefix: int, char: str) -> bytes:
    """`prefix` ASCII bytes, then `char`, then more of what form 2 said."""
    return ((b"0123456789" * 100)[:prefix] + char.encode("utf-8")
            + b" and the rest of what form 2 said" * 3)


def _whole_prefix(data: bytes) -> bytes:
    """The longest prefix of `data` that is whole UTF-8."""
    for end in range(len(data), -1, -1):
        try:
            data[:end].decode("utf-8")
        except UnicodeDecodeError:
            continue
        return data[:end]
    return b""


def _expected(said: bytes) -> bytes:
    """The quote the contract describes: the first `LIMIT` bytes, newline, CR
    and tab made spaces and every other C0 byte dropped, cut back to the
    longest prefix that ends where a character ends, trailing spaces off."""
    line = bytes(0x20 if b in b"\n\r\t" else b for b in said[:LIMIT]
                 if b >= 0x20 or b in b"\n\r\t")
    return _whole_prefix(line).rstrip(b" ")


#: (id, what form 2 said, the quote's length where the case pins it). The
#: first six split a character at byte 1000, so their length is under 1000;
#: the rest are controls.
CASES = [
    ("two-byte-split-after-its-lead", _at(999, E_ACUTE), 999),
    ("three-byte-split-after-its-lead", _at(999, EURO), 999),
    ("three-byte-split-after-two-bytes", _at(998, EURO), 998),
    ("four-byte-split-after-its-lead", _at(999, GRIN), 999),
    ("four-byte-split-after-two-bytes", _at(998, GRIN), 998),
    ("four-byte-split-after-three-bytes", _at(997, GRIN), 997),
    ("three-byte-ending-at-byte-1000", _at(997, EURO), 1000),
    ("four-byte-ending-at-byte-1000", _at(996, GRIN), 1000),
    ("ascii-with-control-bytes", b"line one\nline\ttwo\r\x01three \x1b[0m " * 60, None),
    ("short-and-whole", f"na{E_ACUTE}ve {EURO}5 {GRIN} short".encode("utf-8"), None),
]


@pytest.mark.parametrize("locale", ["C", UTF8], ids=["c-locale", "utf-8-locale"])
@pytest.mark.parametrize("fallback", [False, True], ids=["direct", "after-the-fallback-line"])
@pytest.mark.parametrize("said,length", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_the_guards_quote_of_form_2_ends_on_a_character_boundary(
        tmp_path, said, length, fallback, locale):
    """The quote is whole UTF-8, at most 1000 bytes, and the longest such
    prefix of what form 2 said, cut as the contract cuts it; ASCII is quoted
    as before; and it reaches the warning whole. A UTF-8 id whose locale is
    not installed is skipped, naming bash's warning, never run as C."""
    missing = _locale_missing(locale) if locale != "C" else ""
    if missing:
        pytest.skip(f"the {locale} locale is not installed here, so bash would run this "
                    f"case under C and prove nothing about {locale}: {missing}")
    splits = _whole_prefix(said[:LIMIT]) != said[:LIMIT]
    assert splits == (length is not None and length < LIMIT), "the case table has changed"
    err = tmp_path / "form-2-stderr"
    err.write_bytes(FALLBACK + b"\n" + said if fallback else said)
    stub = tmp_path / "lanes-index"
    stub.write_text('#!/bin/sh\ncat "$QUOTE_CUT_STDERR" >&2\nexit 64\n', encoding="utf-8")
    stub.chmod(0o755)
    warn, out = tmp_path / "warning", tmp_path / "quote"
    script = STANDINS + _function("reg_guard_prefetch") + RUN
    env = {"PATH": os.environ["PATH"], "LC_ALL": locale, "QUOTE_CUT_STDERR": str(err)}
    res = subprocess.run(["bash", "-c", script, "bash", str(stub), str(warn), str(out),
                          str(tmp_path / "cache")],
                         capture_output=True, env=env, timeout=60, check=False)
    assert res.returncode == 0, res.stderr
    quote = out.read_bytes()
    assert len(quote) <= LIMIT, len(quote)
    try:
        quote.decode("utf-8")
    except UnicodeDecodeError as error:
        pytest.fail(f"the quote is not whole UTF-8 ({error}); it ends {quote[-8:]!r}")
    want = _expected(said)
    assert quote == want, (len(quote), quote[-8:], len(want), want[-8:])
    if length is not None:
        assert len(quote) == length, len(quote)
    assert warn.read_bytes() == b"exited 64 (" + want + b")"
    lines = res.stderr.splitlines()
    assert lines.count(FALLBACK) == (1 if fallback else 0), res.stderr
    assert b"Illegal byte sequence" not in res.stderr, res.stderr


#: S3's outage text, first clause, byte for byte: the store and why the read
#: refuses. The register-service spec's SHALL names the store, the cause and
#: the two ways out, and these words are the store's.
S3_FIRST_CLAUSE = (
    "the register's SQL store did not answer the guard's read, so the ROW cannot be read "
    "and the triple cannot be verified, and an indeterminate read refuses "
    "(Amendment 12(d); feature 007, S3).")

#: What `lanes-index` says on stderr of form 2's 69, quoted as the cause.
S3_CAUSE = "the register could not be read (database register_db at 127.0.0.1:55432): connection refused"

#: `reg_guard_s3`'s argument where a declaration was in place and did not
#: open the mirror path.
S3_WHY = "An outage is declared for it, but no mirror path opened."

#: What `guard_bypass` prints, stood in for by a marker, so that the case sees
#: where the refusal ends.
S3_BYPASS = "BYPASS-LINE"


@pytest.mark.parametrize("why", ["", S3_WHY], ids=["no-declaration", "after-a-declaration"])
def test_the_guards_outage_refusal_names_waiting_for_the_database_first(tmp_path, why):
    """S3's refusal exits 2 and names the store, the cause and the two ways
    out, wait for the database first (the register-service spec's SHALL, "The
    guard fails closed during a database outage"): wait, and send the prompt
    again once `lanes-index status` says the database is reached; or, on
    Brett's word, `lanes-index rollback`, which needs the database, so with
    the database lost for good the second way out is the disaster procedure
    in the manual's runbook, "The database lost for good" (lane 3's ruling
    on Q2, #165 6932653746); each command from a shell or a
    `CLAUDE_NO_LANE=1` session. The store's clause, the cause and the
    commands are as they were.

    It fails on the text that named `lanes-index status` and `lanes-index
    rollback` and never said to wait."""
    warn = tmp_path / "refusal"
    script = (STANDINS + f"guard_bypass() {{ printf '%s' {S3_BYPASS}; }}\n"
              + _function("reg_guard_s3")
              + f'RG_SAID="{S3_CAUSE}"\nreg_guard_s3 "$5"\n')
    res = subprocess.run(["bash", "-c", script, "bash", str(tmp_path / "unused"), str(warn),
                          str(tmp_path / "quote"), str(tmp_path / "cache"), why],
                         capture_output=True, env={"PATH": os.environ["PATH"], "LC_ALL": "C"},
                         timeout=60, check=False)
    assert res.returncode == 2, (res.returncode, res.stderr)
    text = warn.read_text(encoding="utf-8")
    assert text.startswith(S3_FIRST_CLAUSE + " `lanes-index register read --for guard --prefetch` "
                           "exited 69: "), text
    ahead = f"{S3_CAUSE}. {why + ' ' if why else ''}The two ways out: "
    assert ahead in text, text
    ways = text.split(ahead, 1)[1]
    assert ways.startswith("wait for the database, and send the prompt again once "), ways
    wait = ways.index("wait for the database")
    again = ways.index("send the prompt again")
    status = ways.index("`lanes-index status`, which says whether this workstation reaches "
                        "the database and what is in place for it")
    word = ways.index("on Brett's word, `lanes-index rollback`, which takes the estate back to "
                      "the files")
    where = ways.index("from a shell or a `CLAUDE_NO_LANE=1` session")
    assert wait < again < status < word < where, ways
    needs = ways.index("which takes the estate back to the files and needs the database, so ")
    lost = ways.index("with the database lost for good the second way out is instead the disaster "
                      "procedure in the manual's runbook, \"The database lost for good\"")
    assert word < needs < lost < where, ways
    assert ways.endswith(f"session. {S3_BYPASS}"), ways


#: What form 2 says where it is too late to verify (contract 3.6's exits
#: table, 2; `cmd_register_read`): its mode line on stdout, then the cause on
#: stderr, and exit 2.
TOO_LATE_STUB = ("#!/bin/sh\nprintf 'mode primary\\n'\n"
                 "printf 'lanes-index: too late to verify\\n' >&2\nexit 2\n")


def _figure(name: str, pattern: str) -> str:
    """One figure as the file `name` writes it, on a line of its own."""
    match = re.search(pattern, (REPO / name).read_text(encoding="utf-8"), re.M)
    assert match, f"{pattern!r} is no longer in {name}"
    return match.group(1)


def test_the_guards_too_late_refusal_names_the_declared_outages_floor_and_cap(tmp_path):
    """Form 2's 2, "too late to verify", is refused 2 by `reg_guard_prefetch`,
    and the refusal gives, in this order: the start line, `T0` + 3750 ms; under
    a declared outage, less than 0.5 s left before the earlier cap, `T0` +
    3650 ms; "or was cut there"; then form 2's own words. Each figure is the
    one the code holds: `GUARD_BUDGET_START_MS` in `lanes-edit.sh`, and
    `REGISTER_GUARD_CUT_S`, `REGISTER_GUARD_DECLARED_CUT_S` and
    `REGISTER_GUARD_FLOOR_S` in `lanes-index` (lane 5's Claude pre-review of
    P19, NIT 4, `87408c5a`; lane 3's Codex review of chain 2, SHOULD 5).

    It fails on the refusal that named the start line alone."""
    start_ms = _figure("lanes-edit.sh", r"^GUARD_BUDGET_START_MS=([0-9]+)$")
    cut_s = _figure("lanes-index", r"^REGISTER_GUARD_CUT_S = ([0-9.]+)$")
    declared_s = _figure("lanes-index", r"^REGISTER_GUARD_DECLARED_CUT_S = ([0-9.]+)$")
    floor_s = _figure("lanes-index", r"^REGISTER_GUARD_FLOOR_S = ([0-9.]+)$")
    assert start_ms == str(round(float(cut_s) * 1000)), (start_ms, cut_s)
    declared_ms = round(float(declared_s) * 1000)
    stub = tmp_path / "lanes-index"
    stub.write_text(TOO_LATE_STUB, encoding="utf-8")
    stub.chmod(0o755)
    warn = tmp_path / "refusal"
    script = (STANDINS + f"GUARD_BUDGET_START_MS={start_ms}\n" + _function("reg_guard_prefetch")
              + 'reg_guard_prefetch\nexit "$?"\n')
    res = subprocess.run(["bash", "-c", script, "bash", str(stub), str(warn),
                          str(tmp_path / "quote"), str(tmp_path / "cache")],
                         capture_output=True, env={"PATH": os.environ["PATH"], "LC_ALL": "C"},
                         timeout=60, check=False)
    assert res.returncode == 2, (res.returncode, res.stderr)
    text = warn.read_text(encoding="utf-8")
    assert text.startswith("it is too late in the hook's 5 s to verify the triple: the guard's "
                           "register read would have started at or past "), text
    start = text.index(f"its start line, T0 + {start_ms} ms")
    floor = text.index(f"(under a declared outage, with less than {floor_s} s left before its "
                       f"cap, T0 + {declared_ms} ms)")
    cut = text.index(", or was cut there")
    said = text.index("(`lanes-index register read --for guard --prefetch` exited 2: "
                      "lanes-index: too late to verify)")
    assert start < floor < cut < said, text
    assert text.endswith("(Amendment 12(d); feature 007, SVC-8)."), text


#: A `git` that logs its arguments and then never answers, as a `--repo` on a
#: stalled mount does: `exec` makes the stall the process `lanes-index`
#: starts, so its timeout ends it and nothing is left behind.
STALLED_GIT = ("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$STALLED_GIT_LOG\"\n"
               "exec sleep 30\n")

#: The longest a cut call may take: far below the stall's 30 s, far above the
#: 1 s each case leaves before its deadline. It catches a call that waits out
#: the stall and a cleanup that hangs; the 1 s itself is held by the
#: `timeout=` each call is given, which the case records.
STALL_BOUND_S = 10

#: Form C's tip read, as `tip_of` and `register_guard_tip` give it, at the
#: end of the stalled `git`'s logged arguments.
TIP_READ = "rev-parse --verify -q refs/remotes/origin/main^{commit}"


def _indexer():
    """`lanes-index` as a module, fresh, as `test_sql_register_bounds.py`'s
    `load_indexer` loads it. Called inside a test, never at import."""
    loader = SourceFileLoader("lanes_index_507_module", str(REPO / "lanes-index"))
    spec = importlib.util.spec_from_loader("lanes_index_507_module", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _stall_git(tmp_path, monkeypatch):
    """Put `STALLED_GIT` first on `PATH`, for the `main` branch, and return
    the file it logs to."""
    bin_dir = tmp_path / "stalled-bin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text(STALLED_GIT, encoding="utf-8")
    git.chmod(0o755)
    log = tmp_path / "git.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STALLED_GIT_LOG", str(log))
    monkeypatch.delenv("LANES_BRANCH", raising=False)
    return log


def test_form_cs_tip_read_is_cut_at_the_mirror_paths_start_line(tmp_path, monkeypatch, capsys):
    """Form C's first git call, the tip read, is cut at the deadline it is
    given, the mirror path's start line, `T0` + 3.75 s, and never waits on a
    `--repo` that does not answer (lane 5's Claude pre-review of P19, SHOULD
    1, `6d8262ec`; lane 3's Codex review of chain 2, SHOULD 2). With 1 s
    left, `register_guard_tip` makes one `rev-parse`, cuts it, and raises
    `StoreUnusable` of kind `unread`, saying it ran out of time before the
    start line; with none left it starts no git at all; and
    `register_guard_outage`, form C itself, with 1 s left before `T0` + 3.75
    s, returns inside the bound, notes why, and writes no `.outage` and no
    temporary beside `--cache`, so the guard refuses with S3's outage text.
    Each of the two calls launched is given a `timeout=` above 0 and at most
    the 1 s left (lane 3's Codex review of chain 2 at `d0bac791`, SHOULD 1):
    `subprocess.run` is wrapped to record it, and still runs the call.

    It fails on the tip read through `tip_of`, which has no timeout and waits
    out the stall's 30 s, and on a tip read given a timeout longer than the
    time left, which the 10 s bound alone lets through."""
    mod = _indexer()
    log = _stall_git(tmp_path, monkeypatch)
    real_run = mod.subprocess.run
    given = []

    def recording_run(argv, *args, **kwargs):
        given.append((list(argv), kwargs.get("timeout")))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", recording_run)
    repo = tmp_path / "mirror"
    repo.mkdir()
    began = time.monotonic()
    with pytest.raises(mod.StoreUnusable) as cut:
        mod.register_guard_tip(str(repo), began + 1.0)
    took = time.monotonic() - began
    assert took < STALL_BOUND_S, f"the tip read took {took:.1f} s, past its deadline"
    assert cut.value.kind == "unread", cut.value
    assert "ran out of time" in cut.value.detail, cut.value.detail
    assert f"T0 + {mod.REGISTER_GUARD_CUT_S:g} s" in cut.value.detail, cut.value.detail
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1 and calls[0].endswith(TIP_READ), calls

    with pytest.raises(mod.StoreUnusable) as late:
        mod.register_guard_tip(str(repo), time.monotonic() - 0.01)
    assert late.value.kind == "unread" and "ran out of time" in late.value.detail, late.value
    assert log.read_text(encoding="utf-8").splitlines() == calls, "git ran with no time left"

    cache = tmp_path / "cache"
    opts = {"repo": str(repo), "cache": str(cache),
            "t0": time.monotonic() - mod.REGISTER_GUARD_CUT_S + 1.0}
    declared = {"kind": "word", "utc": "2026-11-17T00:00:00Z", "why": "test", "mirror-seq": "1"}
    capsys.readouterr()
    began = time.monotonic()
    mod.register_guard_outage(opts, declared)
    took = time.monotonic() - began
    assert took < STALL_BOUND_S, f"form C took {took:.1f} s, past the start line"
    assert not list(tmp_path.glob("cache*")), sorted(p.name for p in tmp_path.iterdir())
    err = capsys.readouterr().err
    assert "form C could not read the mirror's Register-Seq (" in err, err
    assert "ran out of time" in err and "so no .outage was written" in err, err
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2 and calls[1].endswith(TIP_READ), calls
    assert len(given) == 2 and all("rev-parse" in argv for argv, _ in given), given
    for argv, timeout in given:
        assert isinstance(timeout, (int, float)) and not isinstance(timeout, bool) \
            and 0 < timeout <= 1.0, f"a tip read was given timeout={timeout!r}: {argv}"


#: The guard's reader URL: a user and a query parameter, both kept out of the
#: name the cause line gives (AT-P3); `load_config` refuses a password in it.
E1_READER_URL = "postgresql://t507_reader@db.example:6543/register_db?connect_timeout=2"

#: The name `register_guard_store_name` gives for it.
E1_NAME = "database register_db at db.example:6543"


def test_e1s_cause_line_names_the_database_from_reader_url(tmp_path, monkeypatch, capsys):
    """E1 (register-cli.md :776; lane 3's ruling, #165 6807694145): under an
    unexpired word's declaration, form 2's direct read stopped at the declared
    cap once a request reached `psql` ends 69, starts form C, and its first
    stderr line, the cause the guard quotes, names the database as
    `reader_url=` gives it, through `register_guard_store_name`, with no user
    and no query parameter (AT-P3; register-cli.md :767; lane 5's Claude
    pre-review of P19, NIT 3, `7f226784`; lane 3's Codex review of chain 2,
    SHOULD 3). `cmd_register_read` runs as `lanes-index` writes it, with its
    configuration, the declaration, `T0`, the store, the service and the
    direct read stood in for: the read raises `PsqlFailed` with its timer
    expired after `psql` ran, as a silent database leaves it.

    It fails on the E1 line that named no database."""
    mod = _indexer()
    cfg = {"mode": "primary", "reader_url": E1_READER_URL}
    declared = {"kind": "word", "utc": "2026-11-17T00:00:00Z", "why": "test", "mirror-seq": "1"}
    started = []

    def cut_read(store, cfg, opts, served=None):
        raise mod.PsqlFailed("unreachable", "the request was stopped at its timer",
                             timer_expired=True, ran=True)

    monkeypatch.setattr(mod, "load_config", lambda: cfg)
    monkeypatch.setattr(mod, "PostgresStore", lambda cfg, role: object())
    monkeypatch.setattr(mod, "register_guard_t0", lambda pid: time.monotonic())
    monkeypatch.setattr(mod, "register_guard_declared", lambda cfg: declared)
    monkeypatch.setattr(mod, "register_read_ask", lambda cfg, opts: (None, False))
    monkeypatch.setattr(mod, "_register_read_prefetch", cut_read)
    monkeypatch.setattr(mod, "register_guard_outage",
                        lambda opts, given: started.append(given))
    code = mod.cmd_register_read(["--for", "guard", "--prefetch", "--cache",
                                  str(tmp_path / "cache"), "--pid", "1", "--repo",
                                  str(tmp_path), "--lane=lane-q"])
    out, err = capsys.readouterr()
    assert code == 69, (code, err)
    assert out == "mode primary\n", out
    lines = err.splitlines()
    assert lines and lines[0] == (
        f"lanes-index: register read: the register ({E1_NAME}) did not answer by the declared "
        f"outage's cap, T0 + {mod.REGISTER_GUARD_DECLARED_CUT_S:g} s (the request was stopped "
        f"at its timer), so the read failed (E1)"), err
    assert "t507_reader" not in err and "connect_timeout" not in err, err
    assert started == [declared], "form C did not start once after E1's line"


#: A `lanes-index` for the refill: it logs its arguments, then answers as
#: `REFILL_ANSWER` says: `mode index`, `mode primary`, or a refused
#: configuration's 1, which the door reads as files mode with a warning.
REFILL_STUB = ("#!/bin/sh\nprintf 'call %s\\n' \"$*\" >> \"$REFILL_LOG\"\n"
               "case \"$REFILL_ANSWER\" in\n"
               "  index) printf 'mode index\\n' ;;\n"
               "  primary) printf 'mode primary\\n' ;;\n"
               "  *) printf 'lanes-index: REFUSED: a refused configuration\\n' >&2; exit 1 ;;\n"
               "esac\n")

#: What `guard_bind_refill` and `reg_prefetch` call, stood in for, and the
#: globals they read. Its arguments: the stand-in `lanes-index`, the log, the
#: cache file. `reg_flush` and `reg_fail` log that they ran.
REFILL_STANDINS = r'''
set -u
qc_stub="$1"; qc_log="$2"; SE_CACHE_FILE="$3"; SCRIPT_DIR="${3%/*}"; cmd=guard
GB_REFILLED=0; REG_MODE=""; REG_STORE=""; RO_FAILED=""; RO_WHY=""
note() { printf 'lanes-edit: %s\n' "$*" >&2; }
reg_config_present() { return 0; }
lanes_index_bin() { printf '%s\n' "$qc_stub"; }
reg_flush() { printf 'flush\n' >> "$qc_log"; }
reg_fail() { printf 'fail\n' >> "$qc_log"; return 69; }
REG_BACKSTOP=(); REG_BACKSTOP_S=""
reg_backstop() { REG_BACKSTOP=(); REG_BACKSTOP_S=""; }
'''

#: The bind's two calls: `guard_bind_bg`'s after `lane-start`, then
#: `guard_bound_check`'s, each followed by the state it leaves.
REFILL_RUN = r'''
for qc_call in 1 2; do
  guard_bind_refill
  printf 'after %s %s %s %s\n' "$qc_call" "$GB_REFILLED" "$REG_MODE" "${REG_STORE:-none}" >> "$qc_log"
done
'''


@pytest.mark.parametrize("answer,mode,refilled,store,warnings", [
    ("index", "index", "2", "none", 0),
    ("refused", "files", "2", "none", 1),
    ("primary", "primary", "1", "sql", 0),
], ids=["off-primary-index", "off-primary-files-mode-fallback", "primary"])
def test_the_post_bind_refill_asks_once_and_off_primary_later_only_flushes(
        tmp_path, answer, mode, refilled, store, warnings):
    """The post-bind refill makes one form-1 read, `register read --prefetch
    --cache <file> --files register,aliases`, never `--for guard`, however
    many times the bind calls it (lane 5's Claude pre-review of P19, NIT 5,
    `7b5cad67`; lane 3's Codex review of chain 2, SHOULD 4). Off primary on a
    configured workstation, `mode index` or a call that fell to files mode,
    it records `GB_REFILLED=2`, and the second call, `guard_bound_check`'s,
    only flushes, so the next read is a fresh files read, with no second
    prefetch and, after a fall to files mode, no second WARNING. On primary
    (`GB_REFILLED=1`) the second call does nothing, as before; that id is the
    control.

    The two off-primary ids fail on the refill that left `GB_REFILLED` at 0
    off primary, which asked `lanes-index` again and warned again."""
    stub = tmp_path / "lanes-index"
    stub.write_text(REFILL_STUB, encoding="utf-8")
    stub.chmod(0o755)
    log = tmp_path / "refill.log"
    script = (REFILL_STANDINS + _function("reg_prefetch") + _function("reg_read_files")
              + _function("guard_bind_refill") + REFILL_RUN)
    res = subprocess.run(["bash", "-c", script, "bash", str(stub), str(log),
                          str(tmp_path / "cache")],
                         capture_output=True, timeout=60, check=False,
                         env={"PATH": os.environ["PATH"], "LC_ALL": "C",
                              "REFILL_LOG": str(log), "REFILL_ANSWER": answer})
    assert res.returncode == 0, res.stderr
    lines = log.read_text(encoding="utf-8").splitlines()
    calls = [line for line in lines if line.startswith("call ")]
    assert len(calls) == 1, f"the refill asked lanes-index {len(calls)} times: {lines}"
    assert calls[0].startswith("call register read --prefetch --cache ") \
        and calls[0].endswith(" --files register,aliases") and "--for" not in calls[0], calls
    first_end = lines.index(f"after 1 {refilled} {mode} {store}")
    assert lines[0] == "flush" and calls[0] in lines[:first_end], lines
    second = ["flush"] if refilled == "2" else []
    assert lines[first_end + 1:] == [*second, f"after 2 {refilled} {mode} {store}"], lines
    assert res.stderr.count(b"WARNING:") == warnings, res.stderr
