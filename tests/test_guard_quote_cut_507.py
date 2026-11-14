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
ahead of what it said. The cases whose 1000th byte splits a character are
red on the cut before the NIT round; the others are its controls, green
before and after.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None, reason="the guard is a bash command")]

#: The quote's bound in bytes (contract 3.6; register-cli.md:768).
LIMIT = 1000

#: Form 2's fallback line, which the guard relays once, on a line of its own,
#: and leaves out of the quote (T507's part F1).
FALLBACK = b"guard: direct (service unavailable)"

#: The UTF-8 locale of each case's second run.
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
    as before; and it reaches the warning whole."""
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
