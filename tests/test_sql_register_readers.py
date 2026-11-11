# SPDX-License-Identifier: Apache-2.0
"""THE SQL REGISTER'S READERS: `lanes --decide`, ACCEPTED AND IGNORED (feature
007, T502 part 1).

LANE 5'S SEED FOR LANE 2'S MODULE. Lane openRepoTools-5 wrote this file for
T502 part 1, under lane 3's ruling A on opensoft/openRepoTools#165 (comment
6745206209): T502's acceptance of `lanes --decide` goes first, as a local
commit of its own, so that lane 4's T408 can build on it.

  * Lane 2's module of this name SUPERSEDES this file when it arrives.
  * The one test here keeps the guessed name
    `test_lanes_accepts_decide_and_reads_as_without_it`, which `tasks.md:627`
    at `722078c9` selects `[J3]`, and takes lane 2's `[J3]` name when that
    name arrives.

WHAT IT HOLDS (R38, as lane 3 amended it). The `lanes` arm of `lanes-edit.sh`
accepts `--decide` and reads exactly as it reads without it: the same exit,
the same stdout and the same stderr, with the flag alone and beside the arm's
other flags, before them or after them. Its unknown-argument `die` still meets
every argument but `--decide`. T509 gives the flag its meaning.

NO DATABASE ENGINE. The read is the listing's own, over `test_lanes_index`'s
fixture register - a bare origin and its clone under `tmp_path`, a temporary
`$HOME`, and no network - so the test passes with `OPENREPOTOOLS_REQUIRE_PG=1`
set, and it never skips.
"""

from __future__ import annotations

import re

from test_lanes_index import estate

__all__ = ["estate"]  # the fixture, imported so that pytest finds it here

#: THE ONE VALUE MASKED: each row's AGE column. `lanes_rows` prints seventeen
#: tab-separated columns, and the ninth is `age_of`'s `<h>h <mm>m`, the time
#: since the lane's last stamp counted against `date -u +%s` at the moment of
#: each read (`age unknown` for a row with no stamp). Two reads either side of a
#: minute's turn differ there and nowhere else, so that column is masked on both
#: sides and every other byte is compared.
COLUMNS = 17
AGE_COLUMN = 8
AGE_SHAPE = re.compile(r"[0-9]+h [0-9]{2}m|age unknown")

#: The listings compared, each without `--decide`, then with it after and before
#: the other flags: the bare listing; `--all`; `--closed`, which adds the
#: CLOSED and DORMANT rows, so a flag beside `--decide` that changes the answer
#: is seen to be read still; and `--lane <name>`, a flag that takes a value.
LISTINGS = [(), ("--all",), ("--closed",), ("--lane", "repoA-1")]

#: Arguments the arm still refuses, with its 64: one it never knew, one a letter
#: past `--decide`, and one after `--decide`, which the loop must still reach.
REFUSED = [("--no-such-flag",), ("--decided",), ("--decide", "--no-such-flag")]


def _masked(stdout: str) -> str:
    """`stdout` with each row's age column replaced by `<AGE>`. Every line must
    be a row of the listing whose age column holds `age_of`'s answer: a mask
    over anything else would hide a difference rather than the clock."""
    out = []
    for line in stdout.splitlines(keepends=True):
        body = line.rstrip("\n")
        fields = body.split("\t")
        assert len(fields) == COLUMNS, (len(fields), line)
        assert AGE_SHAPE.fullmatch(fields[AGE_COLUMN]), (fields[AGE_COLUMN], line)
        fields[AGE_COLUMN] = "<AGE>"
        out.append("\t".join(fields) + line[len(body):])
    return "".join(out)


def test_lanes_accepts_decide_and_reads_as_without_it(estate):
    """`lanes --decide` IS `lanes` UNTIL T509 (T502 part 1, R38 as lane 3
    amended it). Lane 4's `--decide` callers - `lane` in T408 and `lane-end
    --retire-dormant` in T403 - land after T502 and before the flag means
    anything, so the arm must take the flag and answer as if it were not there:
    the same exit, stdout byte for byte with the age column masked, and the
    same stderr. Before T502 the arm's unknown-argument `die` met `--decide`
    and exited 64. It still meets every other argument, before `--decide` or
    after it."""
    bare = estate.edit("lanes")
    assert bare.returncode == 0 and bare.stdout, (bare.returncode, bare.stderr)  # rows: not vacuous
    closed = estate.edit("lanes", "--closed")
    assert closed.returncode == 0, (closed.returncode, closed.stderr)
    assert _masked(closed.stdout) != _masked(bare.stdout), closed.stdout  # a flag that is seen
    for listing in LISTINGS:
        without = estate.edit("lanes", *listing)
        assert without.returncode == 0 and without.stdout, \
            (listing, without.returncode, without.stderr)
        for argv in dict.fromkeys([(*listing, "--decide"), ("--decide", *listing)]):
            with_it = estate.edit("lanes", *argv)
            assert with_it.returncode == without.returncode, \
                (argv, with_it.returncode, with_it.stdout, with_it.stderr)
            assert _masked(with_it.stdout) == _masked(without.stdout), \
                (argv, with_it.stdout, without.stdout)
            assert with_it.stderr == without.stderr, (argv, with_it.stderr, without.stderr)
    for argv in REFUSED:
        refused = estate.edit("lanes", *argv)
        assert refused.returncode == 64, (argv, refused.returncode, refused.stdout, refused.stderr)
        assert refused.stdout == "", (argv, refused.stdout)
        assert f"unknown argument '{argv[-1]}' for lanes" in refused.stderr, (argv, refused.stderr)
