# SPDX-License-Identifier: Apache-2.0
"""SCRATCH: LANE 4'S SLOW-L4 CHECK (2026-11-15). IT NEVER GOES IN A PULL REQUEST.

It rides only lane 4's two scratch commits, one on each probe, and runs on
hosted CI on `verify/l4/SLOW*` branches:
- probe A is line R merge212 `7f4dc16b` with lane 2's T257p (`e7b81610`)
  picked, `bda9174c`;
- probe B is merge212 itself, the control without T257p.

WHAT IT SHOWS. It shows what ONE writer does when its `lanes-index mode`
question takes longer than the 2 s timer in `lanes-edit.sh`
(`reg_mode_query`, `timeout -k 1 2`). Lane 4 read the one `[two-logins]`
failure of the burst test this way (opensoft/openRepoTools#165 6899400726):
- the writer's question is cut at 2 s;
- `reg_mode_files` warns that the verb "runs in files mode";
- the files-mode `set-row-state` commits to git and ends 0 with no journal row,
  because the bench's origin carries no `lanes/STORE`, so `cs_marker_refuse`
  never refuses.
T257p makes `Bench.to_primary` push `lanes/STORE` to the bench's origin. The
same writer should then end 69, "configure `mode=primary`", with nothing
written.

HOW IT RUNS. It uses the bounds module's own harness, by import, as
`test_the_lookups_wait_counts_from_the_snapshot_calls_end_and_gets_no_lr011`
runs one writer on `pg`:
- `Bench`, `Bench.to_primary`, `Bench.login` and `Bench.config`;
- `_writer` for the write itself: `lanes-edit.sh set-row-state` on the
  bench's lane, from the bench's flipped copy, under D7's 30 s.

WHY A WRAPPER AND NOT THE SHIM. `lanes-index mode` reads only the
configuration and runs no `psql` (`lanes-index`'s `cmd_mode`). T203's `psql`
shim (`_shim`) arms `psql` calls alone, so it cannot slow the question.
Instead:
- `lanes_index_bin` finds `$SCRIPT_DIR/lanes-index` first, which is the
  bench's flipped copy, `<tool>/lanes-index`;
- that copy is renamed beside itself, and a `/bin/sh` wrapper takes its place;
- the wrapper sleeps `SLOW_S` s only when its first argument is `mode`, then
  `exec`s the real copy, so every other call goes straight through;
- the real copy still finds `lanes-edit.sh` and `repos.tsv` beside its own
  real path.
The wrapper logs each call's first argument, so the test can show that the
question reached it.

ONE BODY, TWO CASES. Each case records five facts and asserts what it expects:
- (i) the writer's exit;
- (ii) whether its stderr says "runs in files mode";
- (iii) the journal rows past the head read just before the write;
- (iv) whether its stderr says "configure `mode=primary`";
- (v) whether the bench's origin gained a commit.

`[slow-mode]` sleeps 3 s in `mode`. Its expectation depends on whether the
bench's origin carries `lanes/STORE` once `to_primary` has run:
- with STORE (probe A): 69, (ii) and (iv) true, no row, no origin commit;
- without STORE (probe B): 0, (ii) true, no row, and an origin commit.

`[control]` is the same wrapper with no sleep. Expected: 0, one journal row,
and no files-mode warning.

Every case prints its facts, as one JSON line headed `SLOW-L4`, in two ways:
- to the terminal past the capture (`capsys.disabled()`), so a passing run's
  log shows them under `-q`;
- inside every assertion message, so a failure reports them too.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import pytest

import test_sql_register_bounds as bounds
from conftest import WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None,
    reason="the lane tooling is bash over git")]

#: How long `mode` sleeps in `[slow-mode]`, past `lanes-edit.sh`'s 2 s timer.
SLOW_S = 3
#: `reg_mode_files`' own words, as the burst test reads them.
FILES_MODE = "runs in files mode"
#: `cs_marker_refuse`'s refusal, which is printed with `die ... 69`.
CONFIGURE_PRIMARY = "configure `mode=primary`"
#: Where the real flipped copy is put, beside the wrapper that takes its name.
REAL_NAME = "lanes-index.l4real"

#: The wrapper. @SLOW@, @LOG@ and @REAL@ are filled in by `_slow_mode`.
WRAPPER = """#!/bin/sh
# SLOW-L4, scratch: the bench's lanes-index. Only `mode` sleeps, @SLOW@ s,
# then every call is handed to the real flipped copy by exec.
printf '%s begin %s\\n' "$(date +%s.%N)" "${1-}" >> @LOG@
if [ "${1-}" = mode ] && [ @SLOW@ -gt 0 ]; then
  sleep @SLOW@
  printf '%s slept %s\\n' "$(date +%s.%N)" "${1-}" >> @LOG@
fi
exec @REAL@ "$@"
"""


def _slow_mode(bench, seconds: int) -> Path:
    """Puts the wrapper where `lanes_index_bin` looks first,
    `<tool>/lanes-index`, and moves the bench's real flipped copy beside it,
    as `REAL_NAME`. Returns the wrapper's log."""
    tool = bench.copy.parent
    real = tool / REAL_NAME
    assert bench.copy.name == "lanes-index" and bench.copy.is_file(), bench.copy
    assert not real.exists(), f"{real} is there already"
    log = bench.root / "slow-mode.log"
    os.replace(bench.copy, real)
    text = (WRAPPER.replace("@SLOW@", str(int(seconds)))
            .replace("@LOG@", shlex.quote(str(log)))
            .replace("@REAL@", shlex.quote(str(real))))
    bench.copy.write_text(text, encoding="utf-8")
    bench.copy.chmod(0o755)
    return log


def _origin(bench, *argv: str) -> str:
    """`git <argv>` in the bench's bare origin: its stdout, stripped, or ''
    where git failed."""
    proc = subprocess.run(["git", "--git-dir", str(bench.origin), *argv], env=bench.env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return proc.stdout.strip() if proc.returncode == 0 else ""


@pytest.mark.parametrize("case", ["slow-mode", "control"])
def test_l4_scratch_one_writer_whose_mode_question_outlasts_its_2_s_timer(
        pg, tmp_path, request, capsys, case):
    """See the module's docstring. The bench is brought to primary by
    `Bench.to_primary`, so on probe A its origin carries T257p's `lanes/STORE`.
    The writer is `_writer`'s: `set-row-state repoA-2` from the bench's copy of
    `lanes-edit.sh`, on a login of the writer group, with
    `LANES_REGISTER_DEADLINE_S` unset."""
    bench = bounds.Bench(pg, tmp_path, request)
    bench.to_primary()
    user = bench.login("lanes_register_writer")
    config = bench.config(quote(str(pg.host), safe=""), pg.port, user)
    bench.lane_checkout()
    store = bool(_origin(bench, "ls-tree", "--name-only", "refs/heads/main", "--",
                         "lanes/STORE"))
    log = _slow_mode(bench, SLOW_S if case == "slow-mode" else 0)
    head = int(pg.psql(f"SELECT seq FROM {bounds.SCHEMA}.register_head;").stdout.strip() or 0)
    before = _origin(bench, "rev-parse", "-q", "--verify", "refs/heads/main")
    start = time.monotonic()
    writer = bounds._writer(bench, config, f"PAUSED {bounds.DOT} L4 SLOW scratch, {case}")
    try:
        _, err = writer.communicate(timeout=300)
    finally:
        if writer.poll() is None:
            writer.kill()
            writer.wait()
    took = time.monotonic() - start
    err = err or ""
    after = _origin(bench, "rev-parse", "-q", "--verify", "refs/heads/main")
    rows = pg.psql(f"SELECT seq, write_id FROM {bounds.SCHEMA}.journal WHERE seq > {head} "
                   f"ORDER BY seq;").stdout.split()
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    begun = [line.split()[2] if len(line.split()) > 2 else "" for line in calls
             if line.split()[1:2] == ["begin"]]
    facts = {
        "case": case,
        "store_on_origin": store,
        "exit": writer.returncode,                                    # (i)
        "files_mode": FILES_MODE in err,                              # (ii)
        "journal_rows_past_head": len(rows),                          # (iii)
        "configure_primary": CONFIGURE_PRIMARY in err,                # (iv)
        "origin_gained_commit": bool(after) and after != before,      # (v)
        "head": head,
        "rows": rows,
        "origin_before": before[:12],
        "origin_after": after[:12],
        "origin_subject": _origin(bench, "log", "-1", "--format=%s", "refs/heads/main")
        if after != before else "",
        "mode_asked": begun.count("mode"),
        "mode_slept_through": any(line.split()[1:3] == ["slept", "mode"] for line in calls),
        "wrapper_calls": begun,
        "timeout": shutil.which("timeout", path=bench.env.get("PATH")),
        "slow_s": SLOW_S if case == "slow-mode" else 0,
        "took_s": round(took, 2),
        "stderr_tail": err[-1200:],
    }
    report = "SLOW-L4 " + json.dumps(facts, sort_keys=True)
    print(report)
    with capsys.disabled():
        print("\n" + report, flush=True)

    # THE HARNESS FIRST: the wrapper stood where `lanes_index_bin` looks, and the
    # writer's mode question reached it. Without that, no case would show anything.
    assert facts["mode_asked"] >= 1, \
        f"the writer's `lanes-index mode` question never reached the wrapper:\n{report}"
    if case == "control":
        expected = {"exit": 0, "files_mode": False, "journal_rows_past_head": 1}
    elif store:
        expected = {"exit": 69, "files_mode": True, "configure_primary": True,
                    "journal_rows_past_head": 0, "origin_gained_commit": False}
    else:
        expected = {"exit": 0, "files_mode": True, "journal_rows_past_head": 0,
                    "origin_gained_commit": True}
    wrong = {key: {"seen": facts[key], "expected": value}
             for key, value in expected.items() if facts[key] != value}
    where = "carries" if store else "does not carry"
    assert not wrong, (f"SLOW-L4 [{case}], with the bench's origin that {where} lanes/STORE: "
                       f"{json.dumps(wrong, sort_keys=True)}\n{report}")
