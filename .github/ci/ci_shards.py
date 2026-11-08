# SPDX-License-Identifier: Apache-2.0
"""The shard planner and the count check behind `.github/workflows/tests.yml`.

WHAT IT IS FOR. `tests` and `tests-no-submodule` used to be one job each, 58 to
81 minutes serial. They are now a matrix of SHARD jobs (`tests-shard`,
`tests-no-submodule-shard`) and two small jobs that keep the release gate's
names, `tests` and `tests-no-submodule`, and wait for the shards. This file is
the one place that says which test file runs in which shard, and the one place
that proves, afterwards, that the shards ran exactly what `pytest tests` runs.

THE PLAN IS COMPUTED, NOT LISTED. `plan()` reads `tests/test_*.py` as they are
and `weights.json` (seconds per file) and deals the files to the pytest shards
longest-first, each to the lightest shard so far, ties to the lowest index:
deterministic, so every shard job and the aggregator compute the same plan
from the same checkout. A file with no weight costs `default_seconds` and
still runs, so adding a test file never needs an edit here and can never fall
out of a shard. `weights.json` is only what makes the shards even.

THE LANE HELPERS' SHELL SUITE IS ITS OWN SHARD (`shell`). It is ONE pytest
item, `tests/test_lane_helpers_suite.py::test_the_lane_helper_suite_passes`,
and about 27 of the 70 minutes. The pytest shards deselect it and the shell
shard runs it alone, so it runs once and is counted once. With
`shell_shards` above 1 the suite itself is cut by section (see
`OPENREPOTOOLS_SHELL_SECTIONS` in `plan()`), which needs a suite that honours
it; `plan()` refuses to plan that for a suite that does not.

THE COUNT CHECK (`verify`). Each shard writes `shard.json`, `junit.xml` and
`collected.txt` (the node ids pytest selected, written by this file's own
`pytest_collection_finish` hook, loaded with `-p ci_shards`). The aggregator
collects the whole suite the way a serial run does and requires: every shard
present and exit 0; each shard executed what it collected; no node id in two
pytest shards; and the pytest shards' ids plus the shell suite's one id equal
the full collection, id for id. It then prints the total the serial run
would have printed, `N passed, M skipped`.

Standard library only, so it runs on any runner Python.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = Path(__file__).with_name("weights.json")

#: The one pytest item that runs `tests/test_lane_helpers.sh`.
WRAPPER = "tests/test_lane_helpers_suite.py::test_the_lane_helper_suite_passes"
SUITE = "tests/test_lane_helpers.sh"
SECTIONS_VARIABLE = "OPENREPOTOOLS_SHELL_SECTIONS"

#: The workflow's job ids, which are the release gate's names, and what each
#: one's shard jobs are called.
VARIANTS = ("tests", "tests-no-submodule")
#: What each variant's shard artifacts are called, `<prefix>-<shard>-a<attempt>`.
#: The attempt is in the name because an artifact name can be uploaded once per
#: run: a "Re-run failed jobs" attempt uploads its shard again, and the newest
#: attempt of each shard is the report that counts.
ARTIFACT = {"tests": "shard-tests", "tests-no-submodule": "shard-nosub"}
NODE_ID = re.compile(r"^tests/[^\s:]+\.py::")
HEADING = re.compile(r'^section "== (.*) =="\s*$')


# --- the pytest plugin half: write the node ids a run selected -----------------

def pytest_collection_finish(session):
    """Write every selected item's node id to `$CI_SHARDS_COLLECTED`, one a
    line, after `--deselect` has taken its items out. A no-op without it."""
    target = os.environ.get("CI_SHARDS_COLLECTED")
    if target:
        Path(target).write_text(
            "".join(item.nodeid + "\n" for item in session.items), encoding="utf-8")


# --- the plan ---------------------------------------------------------------------

def load_weights(path: Path = WEIGHTS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def list_test_files(root: Path = ROOT) -> list:
    return sorted(path.name for path in (root / "tests").glob("test_*.py"))


def suite_headings(root: Path = ROOT) -> list:
    """The `section "== … =="` headings of the shell suite, in file order."""
    text = (root / SUITE).read_text(encoding="utf-8")
    # A heading is written inside double quotes, where \` is a backtick, and
    # the suite prints (and clocks) it that way: so does this.
    return [m.group(1).replace("\\`", "`")
            for m in map(HEADING.match, text.splitlines()) if m]


def deal(costs: dict, count: int, names: list) -> dict:
    """`costs` ({item: seconds}) dealt longest-first, each to the lightest of
    `names`' `count` bins so far, ties to the lowest. Returns bin -> items."""
    bins = {name: {"items": [], "seconds": 0.0} for name in names}
    for item in sorted(costs, key=lambda i: (-costs[i], i)):
        pick = min(names, key=lambda n: (bins[n]["seconds"], names.index(n)))
        bins[pick]["items"].append(item)
        bins[pick]["seconds"] += costs[item]
    return bins


def plan(variant: str, files: list, weights: dict, root: Path = ROOT) -> dict:
    """shard id -> {"kind", "files" | "sections", "seconds"} for `variant`."""
    if variant not in VARIANTS:
        raise SystemExit(f"::error::unknown variant {variant!r}; one of {VARIANTS}")
    spec = weights["variants"][variant]
    pytest_n, shell_n = int(spec["pytest_shards"]), int(spec["shell_shards"])
    default = float(spec["default_seconds"])
    costs = {f: float(spec["files"].get(f, default)) for f in files}
    if pytest_n < 1 or shell_n < 1 or len(costs) < pytest_n:
        raise SystemExit(f"::error::{variant}: {pytest_n} pytest shards for {len(costs)} files")
    names = [f"pytest-{i + 1}" for i in range(pytest_n)]
    out = {name: {"kind": "pytest", "files": sorted(bin["items"]),
                  "seconds": round(bin["seconds"], 1)}
           for name, bin in deal(costs, pytest_n, names).items()}
    shell_seconds = float(spec["shell_seconds"])
    if shell_n == 1:
        out["shell"] = {"kind": "shell", "sections": [], "seconds": shell_seconds}
        return out
    # The suite cut by section. Refused for a suite that cannot be cut.
    if SECTIONS_VARIABLE not in (root / SUITE).read_text(encoding="utf-8"):
        raise SystemExit(f"::error::{variant} asks for {shell_n} shell shards, and {SUITE} "
                         f"does not honour {SECTIONS_VARIABLE}, so it can only run whole")
    section_spec = weights["shell_sections"]
    always = set(section_spec.get("always", []))
    headings = suite_headings(root)
    secs = section_spec["seconds"]
    scale = shell_seconds / max(sum(secs.values()), 1.0)
    # Sections that must share a shard are dealt as one item, named by the first.
    first = {h: group[0] for group in section_spec.get("groups", []) for h in group}
    units = {}
    for h in headings:
        if h not in always:
            units.setdefault(first.get(h, h), []).append(h)
    cost = {u: sum(float(secs.get(h, 60.0)) for h in members) * scale
            for u, members in units.items()}
    prefix = sum(float(secs.get(h, 60.0)) * scale for h in headings if h in always)
    ids = [f"shell-{i + 1}" for i in range(shell_n)]
    for sid, bin in deal(cost, shell_n, ids).items():
        chosen = {h for u in bin["items"] for h in units[u]} | always
        numbers = [str(i + 1) for i, h in enumerate(headings) if h in chosen]
        out[sid] = {"kind": "shell", "sections": numbers,
                    "seconds": round(bin["seconds"] + prefix, 1)}
    return out


def shard_ids(variant: str) -> list:
    return list(plan(variant, list_test_files(), load_weights()))


# --- running one shard ---------------------------------------------------------------

def write_summary(text: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def cmd_run(args) -> int:
    shards = plan(args.variant, list_test_files(), load_weights())
    if args.shard not in shards:
        print(f"::error::{args.shard!r} is no shard of {args.variant}: the plan has {sorted(shards)}; "
              "the workflow's matrix and weights.json disagree")
        return 1
    shard, out = shards[args.shard], Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CI_SHARDS_COLLECTED"] = str(out / "collected.txt")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).resolve().parent)] + [p for p in [env.get("PYTHONPATH")] if p])
    if shard["kind"] == "pytest":
        selection = [f"tests/{name}" for name in shard["files"]]
        extra = ["--deselect", WRAPPER]
    else:
        selection, extra = [WRAPPER], []
        if shard["sections"]:
            env[SECTIONS_VARIABLE] = ",".join(shard["sections"])
    flags = ["-q"] + (["-rs"] if args.variant == "tests-no-submodule" else [])
    command = [sys.executable, "-m", "pytest", "-p", "ci_shards", *selection, *extra,
               *flags, f"--junitxml={out / 'junit.xml'}"]
    print(f"{args.variant} / {args.shard}: {len(selection)} "
          f"{'files' if shard['kind'] == 'pytest' else 'item'}, planned {shard['seconds']:.0f} s", flush=True)
    started = time.time()
    code = subprocess.run(command, env=env, check=False).returncode
    meta = {"variant": args.variant, "shard": args.shard, "kind": shard["kind"],
            "files": shard.get("files", []), "sections": shard.get("sections", []),
            "planned_seconds": shard["seconds"], "seconds": round(time.time() - started, 1),
            "exit_code": code}
    (out / "shard.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    write_summary(f"| {args.variant} | {args.shard} | planned {shard['seconds']:.0f} s | "
                  f"ran {meta['seconds']:.0f} s | exit {code} |")
    return code


# --- the count check -------------------------------------------------------------------

def newest_report(results: Path, variant: str, shard: str) -> Path:
    """The folder of `shard`'s report from the highest attempt in `results`."""
    pattern = re.compile(rf"^{re.escape(ARTIFACT[variant])}-{re.escape(shard)}-a(\d+)$")
    found = sorted((int(m.group(1)), entry) for entry in results.iterdir()
                   if entry.is_dir() for m in [pattern.match(entry.name)] if m)
    if not found:
        raise OSError(f"no {ARTIFACT[variant]}-{shard}-a<attempt> folder in {results}")
    return found[-1][1]


def read_junit(path: Path) -> list:
    """(file, outcome, seconds) for each test case of a pytest JUnit report."""
    root = ElementTree.parse(path).getroot()
    cases = []
    for case in root.iter("testcase"):
        outcome = "passed"
        for tag, name in (("error", "error"), ("failure", "failed"), ("skipped", "skipped")):
            if case.find(tag) is not None:
                outcome = name
                break
        module = (case.get("classname") or "").split(".")
        cases.append((module[1] + ".py" if len(module) > 1 else "?",
                      outcome, float(case.get("time") or 0.0)))
    return cases


def read_ids(path: Path) -> list:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if NODE_ID.match(line)]


def verify(variant: str, results: Path, needs_result: str, full_ids: list,
           files: list, weights: dict, root: Path = ROOT) -> tuple:
    """(problems, lines): what is wrong with the shards' reports, and the text
    that says what they add up to. Pure but for reading `results`."""
    shards = plan(variant, files, weights, root)
    problems, per_file, rows = [], {}, []
    if needs_result != "success":
        problems.append(f"the shard jobs' combined result is {needs_result!r}, not 'success'")
    seen, counts, wrapper = {}, {"passed": 0, "skipped": 0, "failed": 0, "error": 0}, []
    for sid, shard in shards.items():
        folder = results
        try:
            folder = newest_report(results, variant, sid)
            meta = json.loads((folder / "shard.json").read_text(encoding="utf-8"))
            ids = read_ids(folder / "collected.txt")
            cases = read_junit(folder / "junit.xml")
        except (OSError, ValueError, ElementTree.ParseError) as error:
            problems.append(f"shard {sid} left no readable report in {folder}: {error}")
            continue
        if meta.get("exit_code") != 0:
            problems.append(f"shard {sid} exited {meta.get('exit_code')}")
        if len(cases) != len(ids):
            problems.append(f"shard {sid} selected {len(ids)} items and its report holds {len(cases)}")
        if shard["kind"] == "shell":
            if ids != [WRAPPER]:
                problems.append(f"shard {sid} selected {ids[:3]}, not the shell suite's one item")
            wrapper += [outcome for _, outcome, _ in cases]
            per_file["shell:" + sid] = round(sum(sec for _, _, sec in cases), 1)
        else:
            for node in ids:
                if node in seen:
                    problems.append(f"{node} is in shards {seen[node]} and {sid}")
                seen[node] = sid
            for name, outcome, seconds in cases:
                counts[outcome] += 1
                per_file[name] = round(per_file.get(name, 0.0) + seconds, 1)
        rows.append(f"| {sid} | {len(ids)} | {meta.get('planned_seconds')} | {meta.get('seconds')} |")
    if wrapper:
        worst = ("error" if "error" in wrapper else "failed" if "failed" in wrapper
                 else "skipped" if set(wrapper) == {"skipped"} else "passed")
        counts[worst] += 1          # the shell suite is ONE item, however many shards cut it
    covered = set(seen) | ({WRAPPER} if wrapper else set())
    full = set(full_ids)
    if len(full) != len(full_ids):
        problems.append("the full collection names a node id twice")
    for label, ids in (("missing from every shard", sorted(full - covered)),
                       ("in a shard and not in the full collection", sorted(covered - full))):
        if ids:
            problems.append(f"{len(ids)} item(s) {label}: {ids[:5]}")
    total = sum(counts.values())
    if total != len(full):
        problems.append(f"the shards report {total} items and the full collection has {len(full)}")
    lines = [f"{variant}: {len(full)} items collected, {total} reported across {len(shards)} shards: "
             f"{counts['passed']} passed, {counts['skipped']} skipped, {counts['failed']} failed, "
             f"{counts['error']} in error",
             f"the serial run's last line would read: {counts['passed']} passed, {counts['skipped']} skipped",
             "| shard | items | planned s | ran s |", "|---|---:|---:|---:|", *rows]
    lines.append("measured seconds per file, for `ci_shards.py reweigh`: " + json.dumps(
        {k: v for k, v in sorted(per_file.items())}, separators=(",", ":")))
    return problems, lines


def collect_full(root: Path = ROOT) -> list:
    """The ids `pytest tests` would run, collected as a serial run does."""
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "full.txt"
        env = dict(os.environ, CI_SHARDS_COLLECTED=str(target), PYTHONPATH=os.pathsep.join(
            [str(Path(__file__).resolve().parent)] + [p for p in [os.environ.get("PYTHONPATH")] if p]))
        done = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "ci_shards",
                               "tests"], cwd=str(root), env=env, capture_output=True, text=True, check=False)
        if done.returncode != 0:
            sys.exit(f"::error::collecting the whole suite exited {done.returncode}:\n"
                     f"{done.stdout[-2000:]}{done.stderr[-2000:]}")
        return read_ids(target)


def cmd_verify(args) -> int:
    problems, lines = verify(args.variant, Path(args.results), args.needs_result,
                             collect_full(), list_test_files(), load_weights())
    print("\n".join(lines))
    write_summary("### " + args.variant + " shards\n\n" + "\n".join(lines))
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


def cmd_plan(args) -> int:
    shards = plan(args.variant, list_test_files(), load_weights())
    if args.json:
        print(json.dumps(shards, indent=1))
    else:
        for sid, shard in shards.items():
            what = (f"{len(shard['files'])} files" if shard["kind"] == "pytest"
                    else f"sections {','.join(shard['sections']) or 'all'}")
            print(f"{sid:10s} {shard['seconds']:7.0f} s  {what}")
    return 0


def cmd_ids(args) -> int:
    print(",".join(shard_ids(args.variant)))
    return 0


def cmd_reweigh(args) -> int:
    """Print weights.json's `files` for `variant` from the measured line the
    aggregator prints (a JSON object of seconds per file), rounded."""
    measured = json.loads(Path(args.measured).read_text(encoding="utf-8"))
    print(json.dumps({k: round(v) for k, v in sorted(measured.items())
                      if k.endswith(".py")}, indent=1))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("plan", cmd_plan), ("ids", cmd_ids), ("run", cmd_run),
                     ("verify", cmd_verify), ("reweigh", cmd_reweigh)):
        one = sub.add_parser(name)
        one.set_defaults(fn=fn)
        if name != "reweigh":
            one.add_argument("--variant", required=True, choices=VARIANTS)
        if name == "plan":
            one.add_argument("--json", action="store_true")
        if name == "run":
            one.add_argument("--shard", required=True)
            one.add_argument("--out", required=True)
        if name == "verify":
            one.add_argument("--results", required=True)
            one.add_argument("--needs-result", required=True)
        if name == "reweigh":
            one.add_argument("measured")
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
