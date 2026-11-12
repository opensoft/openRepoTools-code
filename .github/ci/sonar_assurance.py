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

PROJECT = "opensoft_openRepoTools"
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
    (out / "inventory.json").write_text(json.dumps(manifest, indent=2) + "\n")
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
        "sonar.coverageReportPaths": str(out / "coverage.xml"),
        "sonar.qualitygate.wait": "true", "sonar.qualitygate.timeout": "600",
        "sonar.scm.revision": manifest["commits"]["."],
    }
    (out / "scanner.properties").write_text(
        "".join(key + "=" + value + "\n" for key, value in properties.items()),
        encoding="utf-8")
    return properties


def verify_gate(status, conditions, require_period=True):
    actual = {row["metric"]: (row["op"], str(row["error"]))
              for row in conditions}
    if actual != GATE:
        raise ValueError("quality gate thresholds differ from the reviewed Sonar way gate")
    gate = status["projectStatus"]
    if gate.get("status") != "OK" or not gate.get("conditions"):
        raise ValueError("quality gate did not compute and pass: " + json.dumps(gate))
    evaluated = {row["metricKey"] for row in gate["conditions"]}
    if "new_coverage" not in evaluated or gate.get("ignoredConditions"):
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
    verify_gate(status, gate["conditions"], require_period=not pull_request)
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
    manifest = json.loads((out / "inventory.json").read_text())
    actual = {item["path"]: item.get("language") for item in components if "path" in item}
    missing = [item["path"] for item in manifest["files"]
               if actual.get(item["path"]) != item["language"]]
    if missing:
        raise ValueError("Sonar omitted or misclassified sources: " + ", ".join(missing))
    measures = sonar_api("measures/component", {
        **scope, "metricKeys": "coverage,lines_to_cover,uncovered_lines,new_coverage"})
    measured = {row["metric"]: row for row in measures["component"]["measures"]}
    if "coverage" not in measured or int(measured.get("lines_to_cover", {}).get("value", "0")) <= 0:
        raise ValueError("Sonar did not import measured coverage")
    receipt = {"analysisId": analysis_id, "taskId": task["ceTaskId"],
               "revision": manifest["commits"]["."], "indexed_sources": len(manifest["files"]),
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
    parser.add_argument("command", choices=("prepare", "verify-analysis"))
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
    else:
        verify_analysis(out, root / ".scannerwork/report-task.txt", args.pull_request)


if __name__ == "__main__":
    main()
