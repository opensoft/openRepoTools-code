# SPDX-License-Identifier: Apache-2.0
"""SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's parts 22 to 26
(`l5/007-T502-followup-1925`): lane 3's ruling 5, "No rewrite creates a record",
and its point 26, ruled again (opensoft/openRepoTools#165 6885771975, taking
6885751796); the same rule for the hook's own writes on the offer it answered
(the head copy, the rewrite to binding, choice 1's allow; lane 3 confirmed it in
#165 6886113842); and the comments on the body's facts. This file lives only on
the branch `scratch/t502r3-proof`.

THIS FORM RUNS THE BASH PROOF AND READS ITS ANSWERS, it does not re-implement its
cases: `scratch/t502r7-proof-1114.sh` (a new copy of `t502r6-proof-1114.sh` with
the round 7 cases added, every one of which runs a TEST-ONLY COPY of the tree's
`lanes-edit.sh`, lane 3's point 23: no seam in the shipped script) is run ONCE per
module, hermetically (`env -i`, PATH /usr/bin:/bin, `LANES_HOST` and
`LANES_IN_CONTAINER=0` pinned inside the proof), against the tree's own
`lanes-edit.sh`, and each round 7 case is one test here that reads its line:
`PASS <case>` or `FAIL <case>: <state>`. A last test holds that no case of any
round failed and that the set of round 7 cases is the set below, so a case cannot
be dropped without this file saying so. The cases named `r7-red-*` and the flag
cases fail at `beeae571` (part 21) and pass at part 26; `r7-control-*` pass at
both. Run: `tests/run.sh -k t502r7`; the red run is `T502R7_SCRIPT=<beeae571's
lanes-edit.sh> tests/run.sh -k t502r7`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

pytestmark = [WINDOWS_SKIP, pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("pgrep") is None
    or not Path("/proc/self/stat").exists(),
    reason="the proof's detached outer is waited for with pgrep, and the bind's liveness test reads /proc")]

# `T502R7_SCRIPT` names another `lanes-edit.sh` to run the proof against (the red run
# names beeae571's, so no tracked file is overlaid); unset, it is the tree's own.
SCRIPT = Path(os.environ.get("T502R7_SCRIPT") or REPO / "lanes-edit.sh")
PROOF = REPO / "scratch" / "t502r7-proof-1114.sh"
BASE_PATH = "/usr/bin:/bin"   # nothing installed under /usr/local/bin is ever reached

R7_CASES = [
    "r7-red-answer-2-head-copy-offer-gone-refused-nothing-made-window-back",
    "r7-red-answer-2-binding-rewrite-offer-gone-refused-nothing-made-window-back",
    "r7-red-answer-2-binding-rewrite-offer-gone-at-the-open-refused-nothing-made-window-back",
    "r7-red-answer-2-back-out-offer-gone-writes-nothing-says-dropped-window-back",
    "r7-control-back-out-offer-there-goes-back-to-the-question-and-is-kept",
    "r7-control-ordinary-answer-2-binds-window-stays-renamed-outer-ends-bound",
    "r7-control-ordinary-answer-2-binds-and-copies-the-prefetch-keys",
    "r7-red-answer-2-head-copy-a-bind-record-made-meanwhile-is-left-byte-for-byte-and-answered-as-in-progress",
    "r7-red-answer-2-head-copy-a-bound-record-made-meanwhile-is-heard-as-the-first-read-hears-it-and-no-outer-started",
    "r7-red-answer-2-head-copy-a-bind-failed-record-made-meanwhile-is-answered-as-failed-and-no-outer-started",
    "r7-red-answer-2-head-copy-an-allowance-made-meanwhile-is-left-byte-for-byte-window-back-and-3",
    "r7-red-answer-2-binding-rewrite-a-bind-record-made-meanwhile-is-left-byte-for-byte-and-answered-as-in-progress",
    "r7-red-answer-2-binding-rewrite-a-bound-record-made-meanwhile-is-heard-as-the-first-read-hears-it-and-no-outer-started",
    "r7-red-answer-2-binding-rewrite-a-bind-failed-record-made-meanwhile-is-answered-as-failed-and-no-outer-started",
    "r7-red-answer-2-binding-rewrite-an-allowance-made-meanwhile-is-left-byte-for-byte-window-back-and-3",
    "r7-red-answer-2-a-record-with-another-mode-is-left-says-changed-window-back",
    "r7-red-answer-2-back-out-on-a-record-that-is-no-longer-its-binding-writes-nothing",
    "r7-red-choice-1-offer-gone-writes-nothing-says-dropped-nothing-renamed",
    "r7-red-choice-1-a-bind-record-made-meanwhile-is-left-byte-for-byte-and-answered-as-in-progress",
    "r7-red-choice-1-a-bound-record-made-meanwhile-is-heard-as-the-first-read-hears-it",
    "r7-red-choice-1-an-allowance-made-meanwhile-is-left-byte-for-byte-and-3",
    "r7-control-ordinary-choice-1-writes-the-allow-and-says-so",
    "r7-red-bind-site-bind-failed-record-gone-nothing-written-refusal-no-rename-no-choices",
    "r7-red-bind-site-stale-other-host-record-gone-nothing-written-refusal-no-rename-no-choices",
    "r7-red-bind-site-stale-with-copies-record-gone-nothing-written-refusal-no-rename-no-choices",
    "r7-control-bind-site-bind-failed-rewritten-to-the-question-window-back-choices-printed",
    "r7-control-bind-site-stale-other-host-rewritten-to-the-question-choices-printed",
    "r7-control-bind-site-stale-with-copies-rewritten-to-the-question-with-its-copies",
    "r7-flag-exist-on-a-binding-record-writes-and-returns-0",
    "r7-flag-exist-on-a-bound-record-writes-and-returns-0",
    "r7-flag-exist-on-a-bind-failed-record-writes-and-returns-0",
    "r7-flag-exist-on-a-name-drift-record-writes-and-returns-0",
    "r7-flag-exist-on-a-allow-record-writes-and-returns-0",
    "r7-flag-exist-on-a-nomode-record-writes-and-returns-0",
    "r7-flag-exist-on-an-absent-record-returns-2-nothing-made",
    "r7-flag-exist-record-gone-at-the-open-returns-2-nothing-made",
    "r7-control-flag-exist-a-failed-write-returns-1-unchanged",
    "r7-flag-offer-on-a-binding-record-returns-2-unchanged",
    "r7-flag-offer-on-a-bound-record-returns-2-unchanged",
    "r7-flag-offer-on-a-bind-failed-record-returns-2-unchanged",
    "r7-flag-offer-on-a-allow-record-returns-2-unchanged",
    "r7-flag-offer-on-a-nomode-record-returns-2-unchanged",
    "r7-flag-offer-on-a-name-drift-record-writes-and-returns-0",
    "r7-flag-offer-reads-the-first-mode-line-as-the-loader-does",
    "r7-flag-offer-on-an-absent-record-returns-2-nothing-made",
    "r7-flag-offer-record-gone-at-the-open-returns-2-nothing-made",
    "r7-control-flag-offer-a-failed-write-returns-1-unchanged",
    "r7-red-race-guard-offer-after-the-bind-ended-bound-leaves-the-record-byte-for-byte-and-says-nothing",
    "r7-red-race-guard-run-after-the-bind-ended-bound-hears-the-outcome-and-asks-nothing",
    "r7-red-window-a-binding-record-put-in-place-before-the-create-is-left-byte-for-byte-guard-offer-says-3",
    "r7-red-window-a-bound-record-put-in-place-before-the-create-is-left-byte-for-byte-guard-offer-says-3",
    "r7-red-window-a-bind-failed-record-put-in-place-before-the-create-is-left-byte-for-byte-guard-offer-says-3",
    "r7-red-window-a-allow-record-put-in-place-before-the-create-is-left-byte-for-byte-guard-offer-says-3",
    "r7-red-window-a-name-drift-record-put-in-place-before-the-create-is-left-byte-for-byte-guard-offer-says-3",
    "r7-red-guard-run-on-a-binding-record-says-in-progress-and-leaves-it",
    "r7-red-guard-run-on-a-bound-record-hears-the-outcome-as-the-first-read-would",
    "r7-red-guard-run-on-a-bind-failed-record-says-it-failed-and-keeps-its-keys",
    "r7-red-guard-run-on-an-allowance-that-fits-passes-the-prompt-with-its-warning",
    "r7-red-guard-run-on-an-offer-made-meanwhile-answers-it-with-this-prompt",
    "r7-red-stale-allow-whose-drop-fails-is-not-written-over-the-prompt-is-refused",
    "r7-red-stale-offer-whose-drop-fails-is-not-written-over-the-prompt-is-refused",
    "r7-red-the-next-prompt-meets-the-same-stale-allow-and-the-same-refusal",
    "r7-control-stale-allow-whose-drop-works-is-replaced-by-the-offer-which-asks",
    "r7-control-stale-offer-whose-drop-works-is-replaced-by-the-offer-which-asks",
    "r7-control-ordinary-offer-is-made-eight-lines-mode-0600-and-asks",
    "r7-control-ordinary-offer-makes-offers-dir-0700",
    "r7-control-where-hard-links-are-refused-the-offer-is-made-by-noclobber",
    "r7-red-where-hard-links-are-refused-noclobber-leaves-a-bound-record-byte-for-byte",
    "r7-red-comment-files-list-says-the-facts-reach-the-outcome-only-where-the-body-ended-on-its-own",
    "r7-red-comment-three-results-says-the-outcome-is-in-the-record-only-on-the-rewrites-0",
    "r7-red-comment-facts-says-the-outer-folds-them-where-the-body-ended-on-its-own",
]


@pytest.fixture(scope="module")
def proof(tmp_path_factory):
    work = tmp_path_factory.mktemp("t502r7-proof")
    home = work / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": BASE_PATH, "TMPDIR": str(work), "LC_ALL": "C"}
    got = subprocess.run(["bash", str(PROOF), str(SCRIPT), str(work)], env=env,
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1500)
    lines = {}
    failed = []
    for line in got.stdout.splitlines():
        if line.startswith("PASS "):
            lines[line[5:]] = "PASS"
        elif line.startswith("FAIL "):
            name, _, why = line[5:].partition(": ")
            lines[name] = "FAIL " + why
            failed.append(name)
    return {"lines": lines, "failed": failed, "rc": got.returncode, "stderr": got.stderr[-2000:],
            "stdout": got.stdout}


@pytest.mark.parametrize("case", R7_CASES)
def test_t502r7(proof, case):
    assert case in proof["lines"], f"the proof did not report {case}: {proof['stderr']}"
    assert proof["lines"][case] == "PASS", proof["lines"][case]


def test_t502r7_no_case_of_any_round_failed_and_the_round_7_set_is_whole(proof):
    assert proof["failed"] == [], proof["failed"]
    assert proof["rc"] == 0, (proof["rc"], proof["stderr"])
    reported = sorted(name for name in proof["lines"] if name.startswith(("r7-", "r7_")))
    assert reported == sorted(R7_CASES), sorted(set(reported) ^ set(R7_CASES))
