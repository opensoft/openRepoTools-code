# SPDX-License-Identifier: Apache-2.0
"""SCRATCH, NEVER LANDED: ROUND 11, lane 5's failing-first proof for T502's part 51
(`l5/007-T502-followup-1925`; BRIEF-T502P51-1115.md, lane 5's adversarial review of
parts 48 to 50: SHOULD-A and NIT-A), run on `scratch/t502r11-proof-1115.sh`, a new
copy of round 10's file with the round 11 cases added; every round 7 to 10 case is
kept, with its name. The cases named `r11-red-*` fail at `6dd8bbbd` (part 50) and
pass at part 51; `r11-control-*` pass at both. `T502R11_SCRIPT` names another
`lanes-edit.sh` for the red run. Run: `tests/run.sh -k t502r11`. Part 52's cases
(BRIEF-T502P52-1115.md, lane 5's check of part 51) follow: four that fill round
11's gaps, red at `6dd8bbbd` and green at parts 51 and 52, and NIT-2's case, red
at `6dd8bbbd` and at `e79dbf17` (part 51), green at part 52. Part 53's cases
(BRIEF-T502P53-1115.md, lane 2's independent review of part 51) are red at
`80d83fc6` (part 52) and green at part 53; part 53 RETIRES
`r11-control-case-6-still-the-record-loaded-keeps-its-default-form-and-its-choices`,
whose oracle was false, for `r11-red-case-6-still-prints-no-choices-since-the-next-prompt-is-case-6-again`.
Part 54's red case (BRIEF-T502P54-1115.md, lane 2's further notes on part 51) is
red at `b392fb53` (part 53) and green at part 54; its control passes at both.

Round 10's text follows, as it was.

SCRATCH, NEVER LANDED: lane 5's failing-first proof for T502's parts 42 to 47
(`l5/007-T502-followup-1925`): Codex's S1, S2, S3 and S6 and NITs 1 to 3 on
spec#47's draft 17 (lane 3's Codex delta review at 8bc6b29e), lane 5's final check
of 6253b0ed (C, E and H) and lane 5's wording note to lane 2 (#165 6888777622)
(BRIEF-T502P42-1115.md; Codex's findings and lane 5's, not lane 3's rulings and not
Brett's), with round 7's, round 8's and round 9's cases, which still pass. This
file lives only on the branch `scratch/t502r3-proof`.

THIS FORM RUNS THE BASH PROOF AND READS ITS ANSWERS, it does not re-implement its
cases: `scratch/t502r10-proof-1115.sh` (a new copy of round 9's construction with
the round 10 cases added, every one of which runs a TEST-ONLY COPY of the tree's
`lanes-edit.sh`, lane 3's point 23: no seam in the shipped script) is run ONCE per
module, hermetically (`env -i`, PATH /usr/bin:/bin, `LANES_HOST` and
`LANES_IN_CONTAINER=0` pinned inside the proof), against the tree's own
`lanes-edit.sh`, and each round 7, 8, 9 and 10 case is one test here that reads
its line: `PASS <case>` or `FAIL <case>: <state>`. A case the proof prints `SKIP`
for (as root, `r8-red-f2` and `r8-red-nit8`) is skipped here, not failed with "did
not report". A last test holds that no case of any round failed and that the set
of round 7 to 10 cases is the set below, so a case cannot be dropped without this
file saying so. The cases named `r10-red-*` fail at `6253b0ed` (part 41) and pass
at part 47; `r10-control-*` pass at both, and the round 7, 8 and 9 cases still
pass. The four `r10-red-p48-*` cases (BRIEF-T502P48-1115.md) also fail at
`1c61300e` (part 47) and pass at part 48. The four `r10-red-p49-*` cases
(BRIEF-T502P49-1115.md, lane 5's adversarial review of parts 42 to 47) fail at
`3e6dc617` (part 48) and pass at part 49. The `r10-red-p50-*` case (lane 5's
ruling on part 49's doubt) fails at `88d76394` (part 49) and passes at part 50.
The four `r10-control-fold-*` cases show spec#47's draft 19 at bind-record.md:458:
the outer folds the body's facts into its outcome only where the body ended on
its own. Run: `tests/run.sh -k t502r10`.
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

# `T502R11_SCRIPT` names another `lanes-edit.sh` to run the proof against (the red run
# names 6dd8bbbd's, so no tracked file is overlaid); unset, it is the tree's own.
SCRIPT = Path(os.environ.get("T502R11_SCRIPT") or REPO / "lanes-edit.sh")
PROOF = REPO / "scratch" / "t502r11-proof-1115.sh"
BASE_PATH = "/usr/bin:/bin"   # nothing installed under /usr/local/bin is ever reached

R11_CASES = [
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
    "r8-red-f1-guard-run-stale-allow-then-bound-hears-moved-and-the-owed-note-and-asks-nothing",
    "r8-red-f1-guard-run-stale-allow-then-binding-keeps-the-record-and-the-live-out-and-says-in-progress",
    "r8-red-f1-guard-run-three-agree-row-keeps-a-bound-record-and-its-out-byte-for-byte",
    "r8-control-guard-run-passes-an-allowance-that-fits",
    "r8-control-guard-run-drops-a-stale-allowance-and-asks-once",
    "r8-red-f2-offers-not-writable-with-a-stale-allow-refuses-with-no-question-and-leaves-the-record",
    "r8-red-f3-a-record-that-vanishes-after-the-failed-create-is-not-answered-as-unreadable-and-the-offer-is-made",
    "r8-red-f4-case-6-7-a-bind-failed-record-changed-to-a-newer-binding-is-not-written-over",
    "r8-red-f4-case-10-a-bound-record-written-meanwhile-by-another-hosts-outer-is-heard-not-made-stale",
    "r8-red-f4-case-9-a-record-of-another-attempt-is-not-made-stale",
    "r8-red-f5-answer-2-refusal-says-could-not-be-renamed-back-where-the-rename-back-fails",
    "r8-red-f5-back-out-refusal-says-could-not-be-renamed-back-where-the-rename-back-fails",
    "r8-red-f5-answer-2-refusal-says-renamed-back-only-after-it-was",
    "r8-red-nit1-a-dir-at-the-records-path-is-a-record-there-and-nothing-is-left-inside-it",
    "r8-red-nit1-a-link-at-the-records-path-is-a-record-there-and-nothing-is-left-inside-it",
    "r8-red-nit2-answer-2-a-re-made-offer-for-another-to-is-left-and-no-outer-is-started",
    "r8-red-nit2-choice-1-a-re-made-offer-for-another-to-is-left-and-no-allow-is-written",
    "r8-control-f6b-a-record-put-in-place-just-before-the-noclobber-create-survives-byte-for-byte",
    "r8-control-f6b-without-set-C-the-same-case-overwrites-the-record-so-the-case-needs-it",
    "r8-red-nit4-a-failed-cat-after-the-noclobber-create-is-this-writers-own-partial-file-and-is-removed",
    "r8-red-nit3-inside-the-site-an-allowance-that-guard-answer-found-passes",
    "r8-red-nit5-back-out-io-failure-says-the-record-still-says-binding-and-not-kept",
    "r8-red-nit6-bind-gone-says-the-prompt-is-read-afresh",
    "r8-red-nit8-choice-1-on-an-unreadable-record-takes-k4s-1-path",
    "r9-red-a-guard-bind-rewrite-has-no-here-string",
    "r9-control-a-mode-check-holds-with-a-tmpdir-that-cannot-take-a-file",
    "r9-control-a-two-matches-both-held-writes-and-returns-0",
    "r9-control-a-second-match-not-held-returns-2-unchanged",
    "r9-control-a-the-first-line-of-a-key-is-the-one-matched",
    "r9-red-b-back-out-io-failure-words-say-what-the-next-prompts-do-and-they-do-it",
    "r9-red-c-noclobber-empty-instant-record-remove-d-is-not-recreated-or-written-over",
    "r9-red-c-noclobber-empty-instant-record-replace-d-is-not-recreated-or-written-over",
    "r9-red-nit1-an-ln-that-fails-after-making-the-link-is-this-writers-create",
    "r9-red-d-case-6-7-a-bind-failed-record-of-another-attempt-is-answered-as-that-attempt",
    "r9-red-e-a-dangling-link-at-the-records-path-is-dropped-and-the-offer-made",
    "r9-red-e-a-directory-at-the-records-path-is-for-the-person-to-remove",
    "r9-red-f-an-inherited-gbt-moved-does-not-skip-the-first-round",
    "r9-red-h-an-allowance-that-became-a-bind-record-is-answered-once-and-not-refused",
    "r9-red-window-a-fresh-out-that-appears-after-the-re-read-survives-the-drop",
    "r9-control-window-a-bind-file-listed-before-the-re-read-is-removed-with-the-offer",
    "r10-red-s2-case-5-paused-after-its-load-leaves-a-newer-live-bind-and-its-out-and-answers-it",
    "r10-red-s3-answers-1-and-2-at-once-keep-the-live-out-and-say-so-plainly",
    "r10-red-s3-choice-1-never-sweeps-a-name-above-the-offers-own-attempt",
    "r10-control-s3-choice-1-sweeps-the-offers-own-attempts-files",
    "r10-red-s1-a-directory-made-between-the-test-and-ln-keeps-no-link-inside-it",
    "r10-red-s6-case-6-io-failure-is-worded-on-the-record-read-again",
    "r10-red-s6-case-9-io-failure-is-worded-on-the-record-read-again",
    "r10-red-s6-case-10-io-failure-is-worded-on-the-record-read-again",
    "r10-red-s6-answer-2-head-copy-io-failure-is-worded-on-the-record-read-again",
    "r10-red-s6-answer-2-binding-rewrite-io-failure-is-worded-on-the-record-read-again",
    "r10-red-s6-back-out-io-failure-is-worded-on-the-record-read-again",
    "r10-control-s6-case-6-io-failure-with-the-record-unchanged-keeps-its-words",
    "r10-red-nit2-a-fifo-at-the-records-path-is-not-a-regular-file-and-not-a-directory",
    "r10-red-nit1-noclobber-success-is-proved-on-the-descriptor-and-a-replacement-is-not-taken-for-it",
    "r10-red-h-an-allowance-that-became-an-offer-is-answered-as-the-first-read-would",
    "r10-red-a-the-rename-back-note-keeps-its-first-clause-and-says-no-offer-is-kept",
    "r10-control-a-case-6-keeps-its-rename-back-note",
    "r10-red-nit3-the-three-comments-are-corrected",
    "r10-red-p48-the-answer-2-that-meets-an-allowance-renames-back-in-nones-words",
    "r10-red-p48-the-answer-2-that-meets-an-allowance-and-cannot-rename-back-says-it-started-no-bind",
    "r10-red-p48-case-6-whose-restore-fails-on-a-changed-record-says-no-offer-is-kept",
    "r10-red-p48-case-9-whose-restore-fails-on-a-changed-record-says-no-offer-is-kept",
    "r10-red-p49-nit2-a-failed-binding-rewrite-after-the-head-copy-wrote-names-that-write",
    "r10-red-p49-nit3-case-6-whose-restore-fails-on-a-record-that-cannot-be-read-again-says-only-that",
    "r10-red-p49-nit4-a-link-to-dev-null-put-before-the-noclobber-open-is-not-made",
    "r10-red-p49-nit6-the-s3-note-says-the-answer-2-may-have-started-a-bind",
    "r10-red-p50-case-6-whose-restore-fails-on-a-record-that-cannot-be-read-again-renames-back-in-unreads-words",
    "r10-control-fold-a-body-stopped-by-its-bound-has-neither-its-facts-why-nor-its-note-in-the-outcome",
    "r10-control-fold-a-body-stopped-by-a-signal-has-neither-its-facts-why-nor-its-note-in-the-outcome",
    "r10-control-fold-a-body-that-ends-on-its-own-with-0-has-its-facts-note-in-the-outcome",
    "r10-control-fold-a-body-that-ends-on-its-own-nonzero-has-its-facts-why-in-the-outcome",
    "r11-red-case-6-changed-prints-no-choices-after-its-note-that-no-offer-is-kept",
    "r11-red-case-9-changed-prints-no-choices-after-its-note-that-no-offer-is-kept",
    "r11-red-case-10-changed-prints-no-choices-after-its-note-that-the-record-is-no-longer-the-one-it-read",
    "r11-red-case-10-unread-prints-no-choices-after-its-note-that-the-record-could-not-be-read-again",
    "r11-red-case-6-unread-prints-no-choices-after-its-note-that-the-record-could-not-be-read-again",
    "r11-red-case-6-still-prints-no-choices-since-the-next-prompt-is-case-6-again",
    "r11-control-case-6-an-offer-between-the-same-lanes-keeps-its-default-form-and-its-choices",
    "r11-control-case-6-restored-another-attempts-bind-failed-keeps-lane-2s-three-strings-and-its-choices",
    "r11-red-nit-a-a-change-between-the-two-reads-gives-no-contradictory-notes",
    "r11-red-case-7-changed-prints-no-choices-after-its-note-that-no-offer-is-kept",
    "r11-red-case-9-unread-prints-no-choices-after-its-note-that-the-record-could-not-be-read-again",
    "r11-red-case-6-unread-on-a-regular-file-that-cannot-be-read-prints-no-choices",
    "r11-red-nit-a-case-9-a-change-between-the-two-reads-gives-no-contradictory-notes",
    "r11-red-nit-2-a-record-that-appears-after-the-read-found-nothing-is-gone-now-to-the-note",
    "r11-red-case-7-a-re-made-offer-in-place-counts-its-own-attempts-in-the-choices",
    "r11-red-unread-on-a-file-the-user-cannot-read-prints-no-raw-permission-denied-line",
    "r11-red-case-6-says-its-output-was-written-to-the-out-and-never-that-it-is-kept-there",
    "r11-red-case-6-a-newer-attempts-bind-record-in-place-is-not-renamed-back-over",
    "r11-control-case-6-a-changed-record-that-is-not-a-bind-record-is-still-renamed-back",
]


@pytest.fixture(scope="module")
def proof(tmp_path_factory):
    work = tmp_path_factory.mktemp("t502r11-proof")
    home = work / "home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": BASE_PATH, "TMPDIR": str(work), "LC_ALL": "C"}
    got = subprocess.run(["bash", str(PROOF), str(SCRIPT), str(work)], env=env,
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1500)
    lines = {}
    failed = []
    skipped = []
    for line in got.stdout.splitlines():
        if line.startswith("SKIP "):
            # `SKIP <case prefix> (<why>)`: a case the proof does not run here (as root,
            # which reads any file and writes any directory), so it is skipped, not failed
            skipped.append(line[5:].split(" ", 1)[0])
        elif line.startswith("PASS "):
            lines[line[5:]] = "PASS"
        elif line.startswith("FAIL "):
            name, _, why = line[5:].partition(": ")
            lines[name] = "FAIL " + why
            failed.append(name)
    return {"lines": lines, "failed": failed, "skipped": skipped, "rc": got.returncode,
            "stderr": got.stderr[-2000:], "stdout": got.stdout}


def is_skipped(proof, case):
    return any(case == s or case.startswith(s + "-") for s in proof["skipped"])


@pytest.mark.parametrize("case", R11_CASES)
def test_t502r11(proof, case):
    if is_skipped(proof, case):
        pytest.skip("the proof reports SKIP for this case on this runner (it runs as root)")
    assert case in proof["lines"], f"the proof did not report {case}: {proof['stderr']}"
    assert proof["lines"][case] == "PASS", proof["lines"][case]


def test_t502r11_no_case_of_any_round_failed_and_the_round_7_to_11_set_is_whole(proof):
    assert proof["failed"] == [], proof["failed"]
    assert proof["rc"] == 0, (proof["rc"], proof["stderr"])
    reported = sorted(name for name in proof["lines"] if name.startswith(("r7-", "r8-", "r9-", "r10-", "r11-")))
    expected = sorted(case for case in R11_CASES if not is_skipped(proof, case))
    assert reported == expected, sorted(set(reported) ^ set(expected))
