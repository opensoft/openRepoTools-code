# SPDX-License-Identifier: Apache-2.0
r"""`quoted()` in `lane-start` and `lane-handoff` reads back on bash 3.2.

`quoted` prints its arguments as shell words that read back, for the messages
a person copies and runs: the `--no-launch` print of a launch, the one-line
restart command. Each of the two lane tools carries its own copy, a word of
safe characters bare and anything else in single quotes with its own single
quotes spelled `'\''`.

THE DEFECT (openRepoTools-4's review of #165, RC-W12f's SHOULD). The quote was
spelled by `"${q_a//\'/\'\\\'\'}"`. INSIDE DOUBLE QUOTES bash 3.2 (3.2.57, what
Apple ships), and bash 5.2 under `BASH_COMPAT` 31 to 42, keep the backslashes
of the replacement half, so `/p/it's here` printed `'/p/it\'\\'\'s here'` on
3.2 (`'/p/it\'\'\'s here'` on 5.2 at `BASH_COMPAT=32`) and `eval` of that line
failed. A space, a double quote, a backslash, `$` and a newline read back
exactly all along; only the single quote did not. Bash 4.3 and later, and any
`BASH_COMPAT` above 42, strip those backslashes, which is why every GNU runner
was green.

THE FIX keeps the spelling in a variable (`q_r="'\\''"`) and substitutes
`"${q_a//\'/$q_r}"`. A variable's value is not read again, so every bash gives
`'\''`.

WHAT THIS HOLDS. Each copy is cut out of the shipped file as it is written
there and run in `bash`, with `BASH_COMPAT` unset and at 32 and 42, which are
the levels that keep the backslashes; on a real bash 3.2 (macOS's `/bin/bash`)
the variable is ignored and the run IS 3.2. What it printed is then read back
by `eval` in `bash` and in `sh`, and each argument must come out exactly as it
went in. Both readers are asked because the line is meant for whatever shell
the person pastes it into.

No PostgreSQL, no network, no `tmux` and no file written: the function is the
only code run.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [pytest.mark.skipif(shutil.which("bash") is None,
                                 reason="the lane tools are bash scripts"),
              WINDOWS_SKIP]

TOOLS = ["lane-start", "lane-handoff"]

#: `BASH_COMPAT` as a case sets it: unset, then the two ends of what keeps the
#: backslashes (32 is the macOS bash's own level; 42 is the last one below
#: bash 4.3's change).
COMPATS = [None, "32", "42"]

#: (id, the arguments). The first rows are the quote's own shapes; the rest are
#: what already read back and must keep doing so.
CASES = [
    ("one-quote", ["it's"]),
    ("the-defect-path", ["/p/it's here"]),
    ("two-quotes-in-a-row", ["a''b"]),
    ("three-quotes-in-a-row", ["a'''b"]),
    ("quote-at-the-start", ["'x"]),
    ("quote-at-the-end", ["x'"]),
    ("quote-at-each-end", ["'x'"]),
    ("only-a-quote", ["'"]),
    ("only-two-quotes", ["''"]),
    ("space", ["a b"]),
    ("double-quote", ['say "hi"']),
    ("backslash", ["a\\b"]),
    ("backslash-then-quote", ["a\\'b"]),
    ("dollar", ["$HOME ${x} $(id)"]),
    ("backtick", ["`id`"]),
    ("glob", ["*"]),
    ("newline", ["first line\nsecond line"]),
    ("empty", [""]),
    ("plain-word", ["plain"]),
    ("safe-punctuation", ["/a/b-c_d.e:f=g@h%i+j,k"]),
    ("em-dash", ["a \u2014 b"]),
    ("several-words", ["/p/it's here", "--flag", "", "x y", "plain", "it's"]),
    ("no-words", []),
]


def _function(name: str) -> str:
    """`quoted() { ... }` of one shipped file, as it is written there. Both
    copies close on a `}` in column 0, whatever indent their bodies use."""
    text = (REPO / name).read_text(encoding="utf-8")
    match = re.search(r"^quoted\(\) \{[^\n]*\n.*?^\}\n", text, re.M | re.S)
    assert match, f"`quoted() {{` ... `}}` is no longer in {name}"
    return match.group(0)


def _bashes():
    """`bash` on PATH, and macOS's `/bin/bash` (3.2.57) where that is a
    different file: the second is the one that has the defect without help."""
    found = [("bash", shutil.which("bash"))]
    system = Path("/bin/bash")
    if system.is_file() and os.access(system, os.X_OK):
        if os.path.realpath(system) != os.path.realpath(found[0][1]):
            found.append(("bin-bash", str(system)))
    return found


def _env(compat):
    env = {"PATH": os.environ["PATH"]}
    if compat is not None:
        env["BASH_COMPAT"] = compat
    return env


def printed(source: str, shell: str, compat, args) -> bytes:
    """What `quoted` prints for `args`, run under `shell` with `set -euo
    pipefail` as the lane tools run it."""
    script = "set -euo pipefail\n" + source + '\nquoted "$@"\n'
    res = subprocess.run([shell, "-c", script, "bash", *args],
                         capture_output=True, check=False, env=_env(compat))
    assert res.returncode == 0, (args, res.stderr)
    assert res.stderr == b"", (args, res.stderr)
    return res.stdout


def read_back(reader: str, line: bytes):
    """The words `reader` gets from `eval set -- <line>`, or the error it gave."""
    script = 'eval "set -- $1"; for a in "$@"; do printf "%s\\0" "$a"; done'
    res = subprocess.run([reader, "-c", script, "reader", line.decode("utf-8")],
                         capture_output=True, check=False,
                         env={"PATH": os.environ["PATH"]})
    if res.returncode != 0:
        return f"exit {res.returncode}: {res.stderr.decode('utf-8', 'replace').strip()}"
    return res.stdout.split(b"\0")[:-1]


def mismatches(source: str, shell: str, compat) -> list:
    """Every case whose printed line does not read back as its arguments, in
    `bash` and in `sh`."""
    bad = []
    for cid, args in CASES:
        line = printed(source, shell, compat, args)
        want = [a.encode("utf-8") for a in args]
        for reader in ("bash", "sh"):
            got = read_back(reader, line)
            if got != want:
                bad.append(f"{cid}: printed {line!r}; {reader} read {got!r}, "
                           f"wanted {want!r}")
    return bad


@pytest.mark.parametrize("compat", COMPATS, ids=lambda c: f"compat-{c or 'unset'}")
@pytest.mark.parametrize("tool", TOOLS)
def test_quoted_prints_a_line_that_reads_back_whatever_the_bash(tool, compat):
    """Every argument comes back exactly, from `eval` in `bash` and in `sh`,
    on this bash and (where it is a different file) on `/bin/bash`, with
    `BASH_COMPAT` unset and at 32 and 42."""
    source = _function(tool)
    bad = []
    for label, shell in _bashes():
        bad += [f"[{label}] {m}" for m in mismatches(source, shell, compat)]
    assert not bad, (
        f"{tool}'s quoted() printed a line that does not read back "
        f"(BASH_COMPAT={compat}):\n  " + "\n  ".join(bad))
