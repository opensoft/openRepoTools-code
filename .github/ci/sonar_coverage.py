#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure complete Python/shell source scope without crediting modified copies."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
HELPERS = HERE / "sonar_coverage"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_sources(root, manifest):
    for item in manifest["files"]:
        path = root / item["path"]
        if digest(path) != item["sha256"]:
            raise ValueError("coverage source changed: " + item["path"])


def prepare(root, out, kcov):
    root, out = root.resolve(), out.resolve()
    manifest = json.loads((out / "inventory.json").read_text())
    checked_sources(root, manifest)
    sources = out / "shell-sources"
    sources.mkdir()
    hashes = []
    for item in manifest["files"]:
        if item["language"] != "shell" or item["test"]:
            continue
        target = sources / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / item["path"], target)
        hashes.append(item["sha256"])
    launcher = out / "parse-shell.sh"
    launcher.write_text("#!/usr/bin/env bash\n:\n", encoding="utf-8")
    subprocess.run([
        str(kcov), "--bash-dont-parse-binary-dir",
        "--bash-parse-files-in-dir=" + str(sources),
        "--include-path=" + str(sources), "--output-interval=0",
        str(out / "shell-baseline"), str(launcher)], check=True)
    reports = [path for path in (out / "shell-baseline").glob("*/sonarqube.xml")
               if path.parent.name != "kcov-merged"]
    if len(reports) != 1:
        raise ValueError("expected exactly one kcov shell denominator report")
    shutil.copyfile(reports[0], out / "shell-baseline.xml")
    config = out / "coverage.rc"
    config.write_text(
        "[run]\nparallel = true\nsigterm = true\nplugins = provenance\n"
        "data_file = " + str(out / ".coverage") + "\n"
        "omit =\n    */site-packages/*\n    /usr/*\n"
        "disable_warnings = no-data-collected, module-not-measured\n",
        encoding="utf-8")
    env = {
        "ORT_SONAR_ROOT": str(root), "ORT_SONAR_INVENTORY": str(out / "inventory.json"),
        "COVERAGE_PROCESS_START": str(config),
        "PYTHONPATH": str(HELPERS) + (os.pathsep + os.environ["PYTHONPATH"]
                                    if os.environ.get("PYTHONPATH") else ""),
        "BASH_ENV": str(HELPERS / "bash-env.sh"),
        "ORT_SONAR_SHELL_HASHES": ":".join(sorted(set(hashes))),
        "ORT_SONAR_SHELL_HITS": str(out / "shell-hits"),
    }
    (out / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    if os.environ.get("GITHUB_ENV"):
        with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as stream:
            for key, value in env.items():
                if "\n" in value or "\r" in value:
                    raise ValueError("multiline coverage environment")
                stream.write(key + "=" + value + "\n")
    return env


def shell_lines(root, out, manifest):
    result = {}
    by_hash = {}
    for item in manifest["files"]:
        if item["language"] == "shell" and not item["test"]:
            result[item["path"]] = {}
            by_hash.setdefault(item["sha256"], []).append(item)
    sources = (out / "shell-sources").resolve()
    for element in ET.parse(out / "shell-baseline.xml").getroot().findall("file"):
        path = Path(element.attrib["path"]).resolve()
        relative = path.relative_to(sources).as_posix()
        if relative not in result:
            raise ValueError("unknown shell denominator source: " + relative)
        expected = next(item for item in manifest["files"] if item["path"] == relative)
        if digest(path) != expected["sha256"]:
            raise ValueError("shell denominator bytes changed: " + relative)
        result[relative] = {
            int(line.attrib["lineNumber"]): False
            for line in element.findall("lineToCover")}
    absent = [name for name, lines in result.items() if not lines]
    if absent:
        raise ValueError("kcov omitted shell source denominators: " + ", ".join(absent))
    for path in out.glob("shell-hits.*"):
        for row in path.read_text().splitlines():
            checksum, value = row.split("\t")
            if checksum not in by_hash:
                raise ValueError("unknown shell hit source")
            number = int(value)
            for item in by_hash[checksum]:
                if not 1 <= number <= item["lines"]:
                    raise ValueError("shell hit outside source: " + item["path"])
                # Real DEBUG events can include closing constructs kcov's static
                # parser omitted. Retain those events rather than invent a hit.
                result[item["path"]][number] = True
    return result


def python_lines(root, out, manifest):
    from coverage import Coverage
    from coverage.parser import PythonParser

    cov = Coverage(config_file=str(out / "coverage.rc"))
    cov.combine(data_paths=[str(out)], strict=True)
    cov.save()
    data = cov.get_data()
    by_hash = {}
    for item in manifest["files"]:
        if item["language"] == "py" and not item["test"]:
            by_hash.setdefault(item["sha256"], set()).update(
                data.lines(str(root / item["path"])) or [])
    result = {}
    for item in manifest["files"]:
        if item["language"] != "py" or item["test"]:
            continue
        parser = PythonParser(filename=str(root / item["path"]))
        parser.parse_source()
        hits = by_hash[item["sha256"]]
        if any(not 1 <= number <= item["lines"] for number in hits):
            raise ValueError("Python hit outside source: " + item["path"])
        result[item["path"]] = {
            number: number in hits for number in parser.statements | hits}
    return result


def write_report(out, manifest, measurements):
    expected = {item["path"] for item in manifest["files"] if not item["test"]}
    if set(measurements) != expected:
        raise ValueError("coverage source inventory is incomplete")
    xml = ET.Element("coverage", version="1")
    summary = {"files": len(expected), "languages": {}}
    for item in manifest["files"]:
        if item["test"]:
            continue
        lines = measurements[item["path"]]
        if any(not 1 <= number <= item["lines"] for number in lines):
            raise ValueError("coverage line outside source: " + item["path"])
        element = ET.SubElement(xml, "file", path=item["path"])
        for number, covered in sorted(lines.items()):
            ET.SubElement(element, "lineToCover", lineNumber=str(number),
                          covered="true" if covered else "false")
        total = summary["languages"].setdefault(item["language"],
                                                {"covered": 0, "lines": 0})
        total["covered"] += sum(lines.values())
        total["lines"] += len(lines)
    for lang, total in summary["languages"].items():
        if not total["covered"] or not total["lines"]:
            raise ValueError("no measured " + lang + " coverage")
    ET.indent(xml)
    ET.ElementTree(xml).write(out / "coverage.xml", encoding="utf-8",
                              xml_declaration=True)
    (out / "coverage-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "report", "run"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--kcov", type=Path)
    parser.add_argument("test_args", nargs="*")
    args = parser.parse_args()
    root, out = args.root.resolve(), args.out.resolve()
    if args.command == "prepare":
        prepare(root, out, args.kcov)
    elif args.command == "run":
        env = json.loads((out / "environment.json").read_text())
        subprocess.run(["bash", "code/tests/run.sh", *args.test_args],
                       cwd=root, env={**os.environ, **env}, check=True)
    else:
        manifest = json.loads((out / "inventory.json").read_text())
        checked_sources(root, manifest)
        measurements = python_lines(root, out, manifest)
        measurements.update(shell_lines(root, out, manifest))
        write_report(out, manifest, measurements)


if __name__ == "__main__":
    main()
