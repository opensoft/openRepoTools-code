#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inventory exact assembly sources and fail closed on missing Sonar acceptance."""
from __future__ import annotations

import argparse
import base64
import os
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

PROJECT = "opensoft_openRepoTools"
INVENTORY = "inventory.json"
COVERAGE_REPORT = "coverage.xml"
PROVENANCE_PROBE = "provenance-probe.json"
GATE = {
    "new_security_rating": ("GT", "1"),
    "new_reliability_rating": ("GT", "1"),
    "new_maintainability_rating": ("GT", "1"),
    "new_coverage": ("LT", "80"),
    "new_duplicated_lines_density": ("GT", "3"),
    "new_security_hotspots_reviewed": ("LT", "100"),
}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def language(path, data):
    first = data.split(b"\n", 1)[0]
    if path.endswith(".py") or first.startswith(b"#!") and b"python" in first:
        return "py"
    if path.endswith((".sh", ".bash")) or first.startswith(b"#!") and any(
            shell in first for shell in (b"/bash", b"env bash", b"/sh", b"env sh")):
        return "shell"
    return None


def source_record(repo, prefix, metadata, name):
    mode, kind, oid = metadata.split()
    path = repo / name
    relative = prefix + name
    if kind == "commit":
        if git(path, "rev-parse", "HEAD").decode().strip() != oid:
            raise ValueError("gitlink mismatch: " + relative)
        return path, relative + "/"
    if mode not in ("100644", "100755"):
        return None
    data = path.read_bytes()
    if git(repo, "hash-object", "--", name).decode().strip() != oid:
        raise ValueError("source bytes differ from commit: " + relative)
    lang = language(relative, data)
    if not lang:
        return None
    data.decode("utf-8")
    return {"path": relative, "language": lang, "test": "tests" in Path(relative).parts,
            "sha256": hashlib.sha256(data).hexdigest(), "lines": len(data.splitlines())}


def inventory(root):
    records, commits = [], {}

    def visit(repo, prefix=""):
        commits[prefix or "."] = git(repo, "rev-parse", "HEAD").decode().strip()
        if git(repo, "diff", "--name-only", "HEAD", "--", ".").strip():
            raise ValueError("tracked source changes in " + (prefix or "."))
        for row in git(repo, "ls-tree", "-rz", "HEAD").split(b"\0"):
            if not row:
                continue
            metadata, raw_path = row.split(b"\t", 1)
            record = source_record(repo, prefix, metadata.decode(), raw_path.decode("utf-8"))
            if isinstance(record, tuple):
                visit(*record)
            elif record:
                records.append(record)
    visit(Path(root).resolve())
    return {"schema": 1, "commits": commits,
            "files": sorted(records, key=lambda item: item["path"])}


def write_configuration(root, out, manifest):
    out = Path(out).resolve()
    root = Path(root).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / INVENTORY).write_text(json.dumps(manifest, indent=2) + "\n")
    patterns = {}
    for lang in ("py", "shell"):
        patterns[lang] = [item["path"] for item in manifest["files"]
                          if item["language"] == lang]
    properties = {
        "sonar.projectKey": PROJECT, "sonar.organization": "opensoft",
        "sonar.sources": ".", "sonar.tests": ".",
        "sonar.test.inclusions": ",".join(item["path"] for item in manifest["files"] if item["test"]),
        "sonar.exclusions": ",".join(item["path"] for item in manifest["files"] if item["test"]),
        "sonar.sourceEncoding": "UTF-8", "sonar.python.version": "3.9",
        "sonar.lang.patterns.py": ",".join(patterns["py"]),
        "sonar.lang.patterns.shell": ",".join(patterns["shell"]),
        "sonar.coverage.exclusions": "",
        "sonar.coverageReportPaths": str(out / COVERAGE_REPORT),
        "sonar.qualitygate.wait": "true", "sonar.qualitygate.timeout": "600",
        "sonar.scm.revision": manifest["commits"]["."],
    }
    (out / "scanner.properties").write_text(
        "".join(key + "=" + value + "\n" for key, value in properties.items()),
        encoding="utf-8")
    return properties


def coverage_lines(file, item):
    numbers = set()
    total = {"covered": 0, "lines": 0}
    for line in file:
        number = int(line.get("lineNumber", "0"))
        covered = line.get("covered")
        if (line.tag != "lineToCover" or number in numbers or
                not 1 <= number <= item["lines"] or
                covered not in ("true", "false")):
            raise ValueError("invalid coverage line for " + item["path"])
        numbers.add(number)
        total["lines"] += 1
        total["covered"] += covered == "true"
    return total


def coverage_summary(report, expected):
    if report.tag != "coverage" or report.attrib != {"version": "1"}:
        raise ValueError("invalid coverage report")
    seen = set()
    summary = {"files": len(expected), "languages": {}}
    for file in report:
        path = file.get("path")
        if file.tag != "file" or path not in expected or path in seen:
            raise ValueError("coverage source inventory differs from the tested checkout")
        seen.add(path)
        measured = coverage_lines(file, expected[path])
        total = summary["languages"].setdefault(
            expected[path]["language"], {"covered": 0, "lines": 0})
        for key, value in measured.items():
            total[key] += value
    if seen != set(expected):
        raise ValueError("coverage source inventory is incomplete")
    if set(summary["languages"]) != {"py", "shell"} or any(
            not value["covered"] or not value["lines"]
            for value in summary["languages"].values()):
        raise ValueError("coverage is missing measured Python or shell execution")
    return summary


def rebind_evidence(root, out):
    """Accept test evidence only for the identical commits and source bytes."""
    manifest = inventory(root)
    recorded = json.loads((out / INVENTORY).read_text())
    if recorded != manifest:
        raise ValueError("test evidence differs from this exact checkout")
    probe = json.loads((out / PROVENANCE_PROBE).read_text())
    if set(probe) != {"exact", "modified"} or probe["exact"] <= 0 or probe["modified"] != 0:
        raise ValueError("test evidence has no successful source-copy provenance probe")
    expected = {item["path"]: item for item in manifest["files"] if not item["test"]}
    summary = coverage_summary(ET.parse(out / COVERAGE_REPORT).getroot(), expected)
    if summary != json.loads((out / "coverage-summary.json").read_text()):
        raise ValueError("coverage summary differs from the measured report")
    write_configuration(root, out, manifest)
    return summary


def combine_evidence(root, out):
    """Union real observations from both mandatory complete suites."""
    from sonar_coverage import write_report

    manifest = inventory(root)
    measurements = {item["path"]: {} for item in manifest["files"] if not item["test"]}
    inputs = {}
    for label in ("composed", "provider"):
        directory = Path(os.environ["RUNNER_TEMP"]).resolve() / ("sonar-" + label)
        summary = rebind_evidence(root, directory)
        data = (directory / COVERAGE_REPORT).read_bytes()
        for file in ET.fromstring(data):
            lines = measurements[file.attrib["path"]]
            for line in file:
                number = int(line.attrib["lineNumber"])
                lines[number] = lines.get(number, False) or line.attrib["covered"] == "true"
        inputs[label] = {
            "commits": manifest["commits"], "coverage_sha256": hashlib.sha256(data).hexdigest(),
            "summary": summary,
            "probe": json.loads((directory / PROVENANCE_PROBE).read_text())}
    out.mkdir(parents=True, exist_ok=True)
    write_configuration(root, out, manifest)
    summary = write_report(out, manifest, measurements)
    # Both independent probes passed; diagnostic observations never enter
    # measurements. Retain each exact result plus a conservative roll-up.
    probe = {"exact": min(item["probe"]["exact"] for item in inputs.values()), "modified": 0}
    (out / PROVENANCE_PROBE).write_text(json.dumps(probe, indent=2) + "\n")
    (out / "evidence-inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    return summary


def verify_gate(status, conditions, require_period=True, require_coverage=True):
    actual = {row["metric"]: (row["op"], str(row["error"]))
              for row in conditions}
    if actual != GATE:
        raise ValueError("quality gate thresholds differ from the reviewed Sonar way gate")
    gate = status["projectStatus"]
    if gate.get("status") != "OK" or not gate.get("conditions"):
        raise ValueError("quality gate did not compute and pass: " + json.dumps(gate))
    evaluated = {row["metricKey"] for row in gate["conditions"]}
    if require_coverage and ("new_coverage" not in evaluated or gate.get("ignoredConditions")):
        raise ValueError("quality gate did not evaluate new coverage")
    if require_period and not gate.get("periods") and not gate.get("period"):
        raise ValueError("quality gate has no new-code period")
    return gate



def sonar_api(endpoint, parameters):
    token = os.environ["SONAR_TOKEN"]
    query = urllib.parse.urlencode(parameters)
    request = urllib.request.Request(
        "https://sonarcloud.io/api/" + endpoint + "?" + query,
        headers={"Authorization": "Basic " + base64.b64encode(
            (token + ":").encode()).decode()})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)



def measure_value(measure):
    if "value" in measure:
        return measure["value"]
    if "period" in measure:
        return measure["period"]["value"]
    return measure["periods"][0]["value"]


def verify_coverage_measures(measured, pull_request):
    if not pull_request:
        if "coverage" not in measured or int(measured.get("lines_to_cover", {}).get("value", "0")) <= 0:
            raise ValueError("Sonar did not import measured coverage")
        return True
    # PR APIs expose new-code metrics only. A root PR changing YAML/gitlinks
    # has no eligible new lines; it cannot establish complete main coverage.
    if "new_lines_to_cover" not in measured:
        raise ValueError("Sonar did not report PR coverage eligibility")
    eligible = int(measure_value(measured["new_lines_to_cover"]))
    if eligible < 0 or eligible > 0 and "new_coverage" not in measured:
        raise ValueError("Sonar did not compute eligible PR coverage")
    return eligible > 0


def verify_main_revision(analysis_id, revision):
    analyses = sonar_api("project_analyses/search", {
        "project": PROJECT, "branch": "main", "ps": 100})["analyses"]
    selected = next((item for item in analyses if item["key"] == analysis_id), None)
    if selected is None or selected.get("revision") != revision:
        raise ValueError("Sonar analysis revision differs from the tested assembly")
    return selected["revision"]


def verify_analysis(out, task_file, pull_request=None):
    task = {key: value for line in task_file.read_text().splitlines() if "=" in line
            for key, value in [line.split("=", 1)]}
    if task.get("projectKey") != PROJECT:
        raise ValueError("scanner submitted a different project")
    completed = sonar_api("ce/task", {"id": task["ceTaskId"]})["task"]
    if completed["status"] != "SUCCESS":
        raise ValueError("Sonar compute task did not succeed")
    analysis_id = completed["analysisId"]
    status = sonar_api("qualitygates/project_status", {"analysisId": analysis_id})
    assigned = sonar_api("qualitygates/get_by_project", {"project": PROJECT, "organization": "opensoft"})
    gate_id = assigned["qualityGate"]["id"]
    gate = sonar_api("qualitygates/show", {"id": gate_id, "organization": "opensoft"})
    scope = {"component": PROJECT}
    if pull_request:
        scope["pullRequest"] = pull_request
    components = []
    page = 1
    while True:
        result = sonar_api("components/tree", {
            **scope, "strategy": "leaves", "ps": 500, "p": page})
        components.extend(result["components"])
        if len(components) >= result["paging"]["total"]:
            break
        page += 1
    manifest = json.loads((out / INVENTORY).read_text())
    actual = {item["path"]: item.get("language") for item in components if "path" in item}
    # Sonar's PR component API returns changed files only. Main is the
    # authoritative complete-index receipt; a PR must not pretend to prove it.
    expected = {item["path"]: item["language"] for item in manifest["files"]}
    verified = {path: lang for path, lang in expected.items()
                if not pull_request or path in actual}
    missing = [path for path, lang in verified.items() if actual.get(path) != lang]
    if missing:
        raise ValueError("Sonar omitted or misclassified sources: " + ", ".join(missing))
    measures = sonar_api("measures/component", {
        **scope, "metricKeys": "coverage,lines_to_cover,uncovered_lines,new_coverage,new_lines_to_cover"})
    measured = {row["metric"]: row for row in measures["component"]["measures"]}
    require_coverage = verify_coverage_measures(measured, pull_request)
    verify_gate(status, gate["conditions"], require_period=not pull_request,
                require_coverage=require_coverage)
    server_revision = (None if pull_request else
                       verify_main_revision(analysis_id, manifest["commits"]["."]))
    receipt = {"analysisId": analysis_id, "taskId": task["ceTaskId"],
               "revision": manifest["commits"]["."], "indexed_sources": len(verified),
               "configured_sources": len(expected), "full_index_verified": not bool(pull_request),
               "coverage_import_verified": not bool(pull_request),
               "coverage_condition_evaluated": require_coverage, "server_revision": server_revision,
               "qualityGate": gate, "projectStatus": status["projectStatus"],
               "measures": measures["component"]["measures"]}
    (out / "acceptance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return receipt


def ci_paths(root, out):
    """CLI arguments must agree with the CI-owned checkout and report directory."""
    expected_root = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    expected_out = Path(os.environ["RUNNER_TEMP"]).resolve() / "sonar"
    if root.resolve() != expected_root or out.resolve() != expected_out:
        raise ValueError("analysis paths must match this CI checkout and RUNNER_TEMP/sonar")
    return expected_root, expected_out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "rebind", "combine", "verify-analysis"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pull-request")
    args = parser.parse_args()
    root, out = ci_paths(args.root, args.out)
    if args.command == "prepare":
        manifest = inventory(root)
        write_configuration(root, out, manifest)
        print(json.dumps({"commits": manifest["commits"],
                          "files": len(manifest["files"]),
                          "commands_without_suffix": [
                              item["path"] for item in manifest["files"]
                              if not Path(item["path"]).suffix and not item["test"]]},
                         indent=2))
    elif args.command == "combine":
        combine_evidence(root, out)
    elif args.command == "rebind":
        print(json.dumps(rebind_evidence(root, out), indent=2))
    else:
        verify_analysis(out, root / ".scannerwork/report-task.txt", args.pull_request)


if __name__ == "__main__":
    main()
