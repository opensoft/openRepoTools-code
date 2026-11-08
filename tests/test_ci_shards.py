# SPDX-License-Identifier: Apache-2.0
"""`.github/ci/ci_shards.py`: the plan the CI matrix runs, and the check that the shards add up.

OFFLINE AND QUICK. The plan is read from `tests/test_*.py` as they are and
from `.github/ci/weights.json`; the count check is run here over reports this
file writes into a temporary directory, so no test of this file runs a
suite, a shard or `pytest`. What is held:

- every test file is dealt to exactly one pytest shard, whatever `weights.json`
  says or leaves out, so a file nobody weighed still runs;
- the plan is the same twice, and the shards are even to within one file;
- a shell suite that cannot be cut by section is never planned as cut;
- `verify` passes the shards of a whole suite and names each way they can fail
  to be one: a shard that left no report, one that failed, one that ran fewer
  items than it chose, an item in two shards, an item in none, an item no
  full collection has, and a gate whose shards did not all succeed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from conftest import REPO

HELPER = REPO / ".github" / "ci" / "ci_shards.py"


@pytest.fixture(scope="module")
def ci():
    spec = importlib.util.spec_from_file_location("_ci_shards_under_test", str(HELPER))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def weights_of(files, pytest_shards=2, shell_shards=1, **extra):
    """A weights table for `files`, one second each unless `extra` says."""
    spec = {"pytest_shards": pytest_shards, "shell_shards": shell_shards,
            "default_seconds": 1, "shell_seconds": 100,
            "files": {name: 1 for name in files}}
    spec["files"].update(extra)
    return {"variants": {"tests": spec, "tests-no-submodule": dict(spec)},
            "shell_sections": {"always": [], "seconds": {}}}


# --- the plan --------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ["tests", "tests-no-submodule"])
def test_every_test_file_is_in_exactly_one_pytest_shard_and_the_shell_suite_is_alone(
        ci, variant):
    files = ci.list_test_files()
    shards = ci.plan(variant, files, ci.load_weights())
    dealt = [name for shard in shards.values() if shard["kind"] == "pytest"
             for name in shard["files"]]
    assert sorted(dealt) == files, "a test file is in no shard, or in two"
    assert all(shard["files"] for shard in shards.values() if shard["kind"] == "pytest")
    assert [sid for sid, shard in shards.items() if shard["kind"] == "shell"] == ["shell"]


def test_a_file_no_weight_names_still_runs_and_the_plan_is_the_same_twice(ci):
    files = ["test_a.py", "test_b.py", "test_c.py", "test_unweighed.py"]
    weights = weights_of(files[:3])
    first = ci.plan("tests", files, weights)
    assert first == ci.plan("tests", files, weights)
    dealt = [name for shard in first.values() if shard["kind"] == "pytest"
             for name in shard["files"]]
    assert sorted(dealt) == files


def test_the_pytest_shards_differ_by_no_more_than_one_file(ci):
    files = [f"test_{i:02d}.py" for i in range(13)]
    costs = {name: 3 + (i * 7) % 11 for i, name in enumerate(files)}
    shards = ci.plan("tests", files, weights_of(files, pytest_shards=4, **costs))
    seconds = [shard["seconds"] for shard in shards.values() if shard["kind"] == "pytest"]
    assert max(seconds) - min(seconds) <= max(costs.values()), seconds


def test_more_pytest_shards_than_files_is_refused(ci):
    with pytest.raises(SystemExit):
        ci.plan("tests", ["test_a.py"], weights_of(["test_a.py"], pytest_shards=2))


def test_the_weights_name_the_shell_suites_headings_as_the_suite_prints_them(ci):
    """A heading is read as the suite prints it (its escaped backticks are
    backticks), so the weights file's names match what the suite clocks. Held
    for the always-run list at all times, and for every heading once a variant
    asks for more than one shell shard, where an unnamed section would be
    dealt as a guess."""
    weights = ci.load_weights()
    headings = ci.suite_headings()
    sections = weights["shell_sections"]
    assert [name for name in sections["always"] if name not in headings] == []
    if any(spec["shell_shards"] > 1 for spec in weights["variants"].values()):
        assert [h for h in headings if h not in sections["seconds"]] == []
        assert [name for name in sections["seconds"] if name not in headings] == []


def test_a_shell_suite_that_cannot_be_cut_is_never_planned_as_cut(ci, tmp_path):
    (tmp_path / "tests").mkdir()
    suite = tmp_path / "tests" / "test_lane_helpers.sh"
    suite.write_text('section "== one =="\nsection "== two =="\n', encoding="utf-8")
    weights = weights_of(["test_a.py", "test_b.py"], shell_shards=2)
    with pytest.raises(SystemExit):
        ci.plan("tests", ["test_a.py", "test_b.py"], weights, tmp_path)


def test_a_shell_suite_that_can_be_cut_is_dealt_each_section_once_and_the_always_ones_everywhere(
        ci, tmp_path):
    (tmp_path / "tests").mkdir()
    headings = ["fixtures", "alpha", "beta", "gamma", "delta"]
    suite = tmp_path / "tests" / "test_lane_helpers.sh"
    suite.write_text("# honours OPENREPOTOOLS_SHELL_SECTIONS\n" + "".join(
        f'section "== {h} =="\nrun something\n' for h in headings), encoding="utf-8")
    weights = weights_of(["test_a.py", "test_b.py"], shell_shards=2)
    weights["shell_sections"] = {"always": ["fixtures"],
                                 "seconds": {"fixtures": 10, "alpha": 40, "beta": 30,
                                             "gamma": 20, "delta": 10}}
    shards = ci.plan("tests", ["test_a.py", "test_b.py"], weights, tmp_path)
    shell = {sid: shard["sections"] for sid, shard in shards.items() if shard["kind"] == "shell"}
    assert sorted(shell) == ["shell-1", "shell-2"]
    assert all(sections[0] == "1" for sections in shell.values()), shell
    dealt = sorted(n for sections in shell.values() for n in sections if n != "1")
    assert dealt == ["2", "3", "4", "5"], shell
    weights["shell_sections"]["groups"] = [["alpha", "delta"]]
    again = ci.plan("tests", ["test_a.py", "test_b.py"], weights, tmp_path)
    together = [set(shard["sections"]) for shard in again.values() if shard["kind"] == "shell"]
    assert any({"2", "5"} <= sections for sections in together), together
    assert not any(("2" in sections) != ("5" in sections) for sections in together), together


# --- the count check --------------------------------------------------------------------

def write_shard(results, sid, ids, exit_code=0, skipped=0, extra_cases=0, attempt=1):
    """One shard's report folder, as the workflow uploads it."""
    folder = results / f"shard-tests-{sid}-a{attempt}"
    folder.mkdir(parents=True)
    (folder / "shard.json").write_text(json.dumps(
        {"shard": sid, "exit_code": exit_code, "planned_seconds": 1, "seconds": 1}),
        encoding="utf-8")
    (folder / "collected.txt").write_text("".join(i + "\n" for i in ids), encoding="utf-8")
    cases = []
    for number, node in enumerate(ids):
        path, name = node.split("::", 1)
        inner = "<skipped/>" if number < skipped else ""
        cases.append(f'<testcase classname="{path[:-3].replace("/", ".")}" name="{name}" '
                     f'time="0.5">{inner}</testcase>')
    cases += ['<testcase classname="tests.test_x" name="test_extra" time="0.1"/>'] * extra_cases
    (folder / "junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
        + "".join(cases) + "</testsuite></testsuites>", encoding="utf-8")


FILES = ["test_a.py", "test_b.py"]
A = ["tests/test_a.py::test_one", "tests/test_a.py::test_two"]
B = ["tests/test_b.py::test_three"]


def whole_suite(ci, tmp_path, leave_out=(), **per_shard):
    """Reports for the plan over FILES. With `test_a.py` the heavier, `plan`
    deals it to `pytest-1` and `test_b.py` to `pytest-2`; the shell shard has
    the one item. `per_shard` is write_shard's keywords by shard id."""
    weights = weights_of(FILES, **{"test_a.py": 5})
    plan = ci.plan("tests", FILES, weights)
    assert {sid: shard["files"] for sid, shard in plan.items() if shard["kind"] == "pytest"} == {
        "pytest-1": ["test_a.py"], "pytest-2": ["test_b.py"]}
    results = tmp_path / "results"
    results.mkdir(parents=True)
    ids = {"pytest-1": A, "pytest-2": B, "shell": [ci.WRAPPER]}
    for sid in plan:
        if sid not in leave_out:
            write_shard(results, sid, ids[sid], **per_shard.get(sid, {}))
    return weights, results, A + B + [ci.WRAPPER]


def run_verify(ci, weights, results, full, needs="success"):
    return ci.verify("tests", results, needs, full, FILES, weights)


def test_the_shards_of_a_whole_suite_add_up_and_say_the_serial_runs_line(ci, tmp_path):
    weights, results, full = whole_suite(ci, tmp_path)
    problems, lines = run_verify(ci, weights, results, full)
    assert problems == [], problems
    assert any("4 items collected, 4 reported across 3 shards: 4 passed, 0 skipped" in line
               for line in lines), lines
    assert any("would read: 4 passed, 0 skipped" in line for line in lines), lines


def test_skips_are_counted_as_skips(ci, tmp_path):
    weights, results, full = whole_suite(ci, tmp_path, **{"pytest-1": {"skipped": 1}})
    problems, lines = run_verify(ci, weights, results, full)
    assert problems == [], problems
    assert any("would read: 3 passed, 1 skipped" in line for line in lines), lines


@pytest.mark.parametrize("changes, fragment", [
    ({"leave_out": ("pytest-2",)}, "left no readable report"),
    ({"leave_out": ("shell",)}, "missing from every shard"),
    ({"pytest-2": {"exit_code": 1}}, "exited 1"),
    ({"pytest-1": {"extra_cases": 1}}, "selected 2 items and its report holds 3"),
], ids=["no-report", "no-shell-shard", "a-failed-shard", "report-disagrees"])
def test_a_bad_shard_is_named(ci, tmp_path, changes, fragment):
    weights, results, full = whole_suite(ci, tmp_path, **changes)
    problems, _ = run_verify(ci, weights, results, full)
    assert any(fragment in problem for problem in problems), problems


def test_an_item_in_none_an_item_nobody_collected_and_an_item_in_two_shards_are_named(
        ci, tmp_path):
    weights, results, full = whole_suite(ci, tmp_path)
    problems, _ = run_verify(ci, weights, results, full + ["tests/test_c.py::test_four"])
    assert any("missing from every shard" in problem for problem in problems), problems
    problems, _ = run_verify(ci, weights, results, [i for i in full if i != A[0]])
    assert any("not in the full collection" in problem for problem in problems), problems
    weights, results, full = whole_suite(ci, tmp_path / "twice", **{"pytest-2": {}})
    write_shard(results, "pytest-2", A[:1] + B, attempt=2)
    problems, _ = run_verify(ci, weights, results, full)
    assert any("is in shards pytest-1 and pytest-2" in problem for problem in problems), problems


def test_the_newest_attempt_of_a_shard_is_the_report_that_counts(ci, tmp_path):
    weights, results, full = whole_suite(ci, tmp_path, **{"pytest-2": {"exit_code": 1}})
    problems, _ = run_verify(ci, weights, results, full)
    assert any("exited 1" in problem for problem in problems), problems
    write_shard(results, "pytest-2", B, attempt=2)
    problems, _ = run_verify(ci, weights, results, full)
    assert problems == [], problems


def test_a_gate_whose_shards_did_not_all_succeed_is_red_whatever_the_reports_say(ci, tmp_path):
    weights, results, full = whole_suite(ci, tmp_path)
    for result in ("failure", "cancelled", "skipped"):
        problems, _ = run_verify(ci, weights, results, full, needs=result)
        assert any(f"{result!r}" in problem for problem in problems), (result, problems)
