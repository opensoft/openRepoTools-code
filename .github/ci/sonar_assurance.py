#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inventory exact assembly sources and fail closed on missing Sonar acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

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


def inventory(root):
    root = Path(root).resolve()
    records, commits = [], {}

    def visit(repo, prefix=""):
        commits[prefix or "."] = git(repo, "rev-parse", "HEAD").decode().strip()
        if git(repo, "diff", "--name-only", "HEAD", "--", ".").strip():
            raise ValueError("tracked source changes in " + (prefix or "."))
        for row in git(repo, "ls-tree", "-rz", "HEAD").split(b"\0"):
            if not row:
                continue
            metadata, raw_path = row.split(b"\t", 1)
            mode, kind, oid = metadata.decode().split()
            name = raw_path.decode("utf-8")
            path = repo / name
            relative = prefix + name
            if kind == "commit":
                if git(path, "rev-parse", "HEAD").decode().strip() != oid:
                    raise ValueError("gitlink mismatch: " + relative)
                visit(path, relative + "/")
            elif mode in ("100644", "100755"):
                data = path.read_bytes()
                if git(repo, "hash-object", "--", name).decode().strip() != oid:
                    raise ValueError("source bytes differ from commit: " + relative)
                lang = language(relative, data)
                if lang:
                    data.decode("utf-8")  # analysis must not silently replace bytes
                    parts = Path(relative).parts
                    records.append({
                        "path": relative, "language": lang,
                        "test": "tests" in parts,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "lines": len(data.splitlines()),
                    })
    visit(root)
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


def verify_gate(status, conditions):
    actual = {row["metric"]: (row["op"], str(row["error"]))
              for row in conditions}
    if actual != GATE:
        raise ValueError("quality gate thresholds differ from the reviewed Sonar way gate")
    gate = status["projectStatus"]
    if gate.get("status") != "OK" or not gate.get("conditions"):
        raise ValueError("quality gate did not compute and pass: " + json.dumps(gate))
    if not gate.get("periods") and not gate.get("period"):
        raise ValueError("quality gate has no new-code period")
    return gate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--root", type=Path, required=True)
    prepare.add_argument("--out", type=Path, required=True)
    gate = sub.add_parser("verify-gate")
    gate.add_argument("--status", type=Path, required=True)
    gate.add_argument("--gate", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        manifest = inventory(args.root)
        write_configuration(args.root, args.out, manifest)
        print(json.dumps({"commits": manifest["commits"],
                          "files": len(manifest["files"]),
                          "commands_without_suffix": [
                              item["path"] for item in manifest["files"]
                              if not Path(item["path"]).suffix and not item["test"]]},
                         indent=2))
    else:
        result = verify_gate(json.loads(args.status.read_text()),
                             json.loads(args.gate.read_text())["qualityGate"]["conditions"])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
