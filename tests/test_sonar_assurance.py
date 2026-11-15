# SPDX-License-Identifier: Apache-2.0
"""Acceptance is complete source inventory and a computed, unchanged gate."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]


@pytest.fixture
def assurance():
    spec = importlib.util.spec_from_file_location(
        "sonar_assurance_test", HERE / ".github/ci/sonar_assurance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repo(tmp_path, files):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", *files], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test",
                    "-c", "user.email=test@invalid", "commit", "-qm", "fixture"], check=True)
    return tmp_path


def test_inventory_includes_extensionless_and_tests_and_rejects_source_drift(assurance, tmp_path):
    root = repo(tmp_path, {"command": b"#!/usr/bin/env bash\necho hello\n",
                           "index": b"#!/usr/bin/env python3\nprint(1)\n",
                           "tests/test_sample.py": b"assert True\n",
                           "README.md": b"notes\n"})
    manifest = assurance.inventory(root)
    assert {(item["path"], item["language"], item["test"]) for item in manifest["files"]} == {
        ("command", "shell", False), ("index", "py", False),
        ("tests/test_sample.py", "py", True)}
    (root / "command").write_text("changed\n")
    with pytest.raises(ValueError, match="tracked source changes"):
        assurance.inventory(root)


def test_configuration_covers_each_command_and_removes_automatic_coverage_exclusion(assurance, tmp_path):
    manifest = {"commits": {".": "a" * 40},
                "files": [{"path": "code/lane", "language": "shell", "test": False},
                          {"path": "code/lanes-index", "language": "py", "test": False},
                          {"path": "code/tests/test_sample.py", "language": "py", "test": True}]}
    config = assurance.write_configuration(tmp_path, tmp_path / "out", manifest)
    assert config["sonar.lang.patterns.shell"] == "code/lane"
    assert config["sonar.lang.patterns.py"] == "code/lanes-index,code/tests/test_sample.py"
    assert config["sonar.coverage.exclusions"] == ""
    assert config["sonar.python.version"] == "3.9"
    assert config["sonar.qualitygate.wait"] == "true"
    assert config["sonar.exclusions"] == "code/tests/test_sample.py"
    assert config["sonar.test.inclusions"] == config["sonar.exclusions"]


@pytest.mark.parametrize("status,period,conditions", [
    ("NONE", [], []), ("OK", [], [{"metricKey": "new_coverage"}]),
    ("ERROR", [{"index": 1}], [{"metricKey": "new_coverage"}]),
])
def test_gate_rejects_neutral_missing_period_and_failures(assurance, status, period, conditions):
    thresholds = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    with pytest.raises(ValueError):
        assurance.verify_gate({"projectStatus": {
            "status": status, "periods": period, "conditions": conditions}}, thresholds)


def test_gate_rejects_relaxed_thresholds_and_accepts_computed_result(assurance):
    thresholds = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    status = {"projectStatus": {"status": "OK", "periods": [{"index": 1}],
                                "conditions": [{"metricKey": "new_coverage", "status": "OK"}]}}
    assert assurance.verify_gate(status, thresholds)["status"] == "OK"
    thresholds[0]["error"] = "5"
    with pytest.raises(ValueError, match="thresholds"):
        assurance.verify_gate(status, thresholds)


def test_ci_paths_refuse_other_checkouts_and_arbitrary_report_paths(assurance, tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    runner = tmp_path / "runner"
    monkeypatch.setenv("GITHUB_WORKSPACE", str(root))
    monkeypatch.setenv("RUNNER_TEMP", str(runner))
    assert assurance.ci_paths(root, runner / "sonar") == (root, runner / "sonar")
    with pytest.raises(ValueError, match="paths must match"):
        assurance.ci_paths(tmp_path / "other", runner / "sonar")
    with pytest.raises(ValueError, match="paths must match"):
        assurance.ci_paths(root, runner / "elsewhere")


def test_pr_gate_is_computed_without_a_main_branch_period(assurance):
    thresholds = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    status = {"projectStatus": {"status": "OK", "periods": [],
                                "conditions": [{"metricKey": "new_coverage", "status": "OK"}]}}
    assert assurance.verify_gate(status, thresholds, require_period=False)["status"] == "OK"


@pytest.mark.parametrize("conditions,ignored", [
    ([{"metricKey": "new_reliability_rating"}], False),
    ([{"metricKey": "new_coverage"}], True),
])
def test_gate_refuses_unevaluated_or_ignored_coverage(assurance, conditions, ignored):
    thresholds = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    with pytest.raises(ValueError, match="evaluate new coverage"):
        assurance.verify_gate({"projectStatus": {
            "status": "OK", "periods": [{"index": 1}],
            "conditions": conditions, "ignoredConditions": ignored}}, thresholds)


@pytest.mark.parametrize("failure", [
    None, "wrong-project", "compute-pending", "missing-source",
    "wrong-language", "missing-coverage", "neutral-gate", "wrong-revision",
    "pr-zero-coverage", "pr-covered", "pr-no-metric",
])
def test_analysis_verifies_the_submitted_task_sources_and_coverage(
        assurance, tmp_path, monkeypatch, failure):
    manifest = {"commits": {".": "b" * 40},
                "files": [{"path": "code/lane", "language": "shell"}]}
    (tmp_path / "inventory.json").write_text(json.dumps(manifest))
    task = tmp_path / "report-task.txt"
    project = "wrong" if failure == "wrong-project" else assurance.PROJECT
    task.write_text("projectKey=" + project + "\nceTaskId=task-123\n")
    conditions = [{"metric": key, "op": op, "error": threshold}
                  for key, (op, threshold) in assurance.GATE.items()]
    calls = []
    pull_request = "361" if failure and failure.startswith("pr-") else None
    positive = failure in (None, "pr-zero-coverage", "pr-covered")

    def api(endpoint, parameters):
        calls.append((endpoint, parameters))
        if endpoint == "ce/task":
            return {"task": {"status": "PENDING" if failure == "compute-pending" else "SUCCESS",
                             "analysisId": "analysis-123"}}
        if endpoint == "qualitygates/project_status":
            return {"projectStatus": {
                "status": "NONE" if failure == "neutral-gate" else "OK",
                "periods": [] if pull_request else [{"index": 1}],
                "conditions": [{"metricKey": "new_reliability_rating" if failure == "pr-zero-coverage"
                                else "new_coverage"}]}}
        if endpoint == "qualitygates/get_by_project":
            assert parameters["organization"] == "opensoft"
            return {"qualityGate": {"id": 9}}
        if endpoint == "qualitygates/show":
            assert parameters["organization"] == "opensoft"
            return {"id": 9, "conditions": conditions}
        if endpoint == "components/tree":
            files = [] if failure in ("missing-source", "pr-zero-coverage") else [{
                "path": "code/lane", "language": "py" if failure == "wrong-language" else "shell"}]
            return {"paging": {"total": len(files)}, "components": files}
        if endpoint == "measures/component":
            measures = [] if failure == "missing-coverage" else [
                {"metric": "coverage", "value": "90.0"}, {"metric": "lines_to_cover", "value": "100"}]
            if pull_request:
                measures = [] if failure == "pr-no-metric" else [{
                    "metric": "new_lines_to_cover", "periods": [
                        {"index": 1, "value": "0" if failure == "pr-zero-coverage" else "100"}]}]
                if failure == "pr-covered":
                    measures.append({"metric": "new_coverage", "periods": [{"index": 1, "value": "90.0"}]})
            return {"component": {"measures": measures}}
        if endpoint == "project_analyses/search":
            revision = "c" * 40 if failure == "wrong-revision" else "b" * 40
            return {"analyses": [{"key": "analysis-123", "revision": revision}]}
        raise AssertionError(endpoint)

    monkeypatch.setattr(assurance, "sonar_api", api)
    if not positive:
        with pytest.raises(ValueError):
            assurance.verify_analysis(tmp_path, task, pull_request)
        assert not (tmp_path / "acceptance.json").exists()
    else:
        receipt = assurance.verify_analysis(tmp_path, task, pull_request)
        assert receipt["analysisId"] == "analysis-123"
        assert receipt["indexed_sources"] == (0 if failure == "pr-zero-coverage" else 1)
        assert receipt["full_index_verified"] == (not bool(pull_request))
        assert receipt["coverage_import_verified"] == (not bool(pull_request))
        assert calls[1][1] == {"analysisId": "analysis-123"}
        assert (tmp_path / "acceptance.json").exists()


@pytest.mark.parametrize("failure", [
    None, "revision", "source", "missing-probe", "modified-probe",
    "missing-source", "duplicate-source", "bad-line", "empty-language", "summary",
])
def test_evidence_rebind_requires_exact_commits_sources_and_complete_reports(
        assurance, tmp_path, failure):
    root = repo(tmp_path / "checkout", {
        "command": b"#!/usr/bin/env bash\necho hello\n",
        "index": b"#!/usr/bin/env python3\nprint(1)\n"})
    out = tmp_path / "evidence"
    out.mkdir()
    manifest = assurance.inventory(root)
    recorded = json.loads(json.dumps(manifest))
    if failure == "revision":
        recorded["commits"]["."] = "f" * 40
    if failure == "source":
        recorded["files"][0]["sha256"] = "f" * 64
    (out / "inventory.json").write_text(json.dumps(recorded))
    (out / "provenance-probe.json").write_text(json.dumps({
        "exact": 1, "modified": 1 if failure == "modified-probe" else 0}))
    if failure == "missing-probe":
        (out / "provenance-probe.json").unlink()
    files = ['<file path="' + item["path"] + '"><lineToCover lineNumber="' +
             ("999" if failure == "bad-line" else "2") + '" covered="' +
             ("false" if failure == "empty-language" and item["language"] == "py"
              else "true") + '"/></file>' for item in manifest["files"]]
    if failure == "missing-source":
        files.pop()
    if failure == "duplicate-source":
        files.append(files[0])
    (out / "coverage.xml").write_text('<coverage version="1">' + "".join(files) + '</coverage>')
    summary = {"files": 2, "languages": {
        "py": {"covered": 1, "lines": 1}, "shell": {"covered": 1, "lines": 1}}}
    if failure == "summary":
        summary["files"] = 3
    (out / "coverage-summary.json").write_text(json.dumps(summary))
    if failure:
        with pytest.raises((ValueError, FileNotFoundError)):
            assurance.rebind_evidence(root, out)
        assert not (out / "scanner.properties").exists()
    else:
        assert assurance.rebind_evidence(root, out) == summary
        assert "sonar.coverageReportPaths=" + str(out / "coverage.xml") in (
            out / "scanner.properties").read_text()


@pytest.mark.parametrize("failure", [None, "missing-provider", "foreign-provider", "incomplete-provider", "different-denominator"])
def test_combination_requires_both_exact_complete_suites_and_unions_real_hits(
        assurance, tmp_path, monkeypatch, failure):
    monkeypatch.syspath_prepend(str(HERE / ".github/ci"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    root = repo(tmp_path / "checkout", {
        "command": b"#!/usr/bin/env bash\necho one\necho two\n",
        "index": b"#!/usr/bin/env python3\nprint(1)\nprint(2)\n"})
    manifest = assurance.inventory(root)
    for label in ("composed", "provider"):
        if failure == "missing-provider" and label == "provider":
            continue
        directory = tmp_path / ("sonar-" + label)
        directory.mkdir()
        recorded = json.loads(json.dumps(manifest))
        if failure == "foreign-provider" and label == "provider":
            recorded["commits"]["."] = "f" * 40
        (directory / "inventory.json").write_text(json.dumps(recorded))
        (directory / "provenance-probe.json").write_text(json.dumps({"exact": 2, "modified": 0}))
        files = ['<file path="' + item["path"] + '">' +
                 '<lineToCover lineNumber="2" covered="' +
                 ("true" if label == "composed" else "false") + '"/>' +
                 '<lineToCover lineNumber="3" covered="' +
                 ("true" if label == "provider" else "false") + '"/></file>'
                 for item in manifest["files"]]
        if failure == "incomplete-provider" and label == "provider":
            files.pop()
        if failure == "different-denominator" and label == "provider":
            files = [file.replace('lineNumber="2"', 'lineNumber="1"') for file in files]
        (directory / "coverage.xml").write_text('<coverage version="1">' + "".join(files) + '</coverage>')
        (directory / "coverage-summary.json").write_text(json.dumps({
            "files": 2, "languages": {
                "py": {"covered": 1, "lines": 2}, "shell": {"covered": 1, "lines": 2}}}))
    out = tmp_path / "sonar"
    if failure:
        with pytest.raises((ValueError, FileNotFoundError)):
            assurance.combine_evidence(root, out)
        assert not (out / "coverage.xml").exists()
    else:
        summary = assurance.combine_evidence(root, out)
        assert summary == {"files": 2, "languages": {
            "py": {"covered": 2, "lines": 2}, "shell": {"covered": 2, "lines": 2}}}
        inputs = json.loads((out / "evidence-inputs.json").read_text())
        assert set(inputs) == {"composed", "provider"}
        assert all(item["commits"] == manifest["commits"] for item in inputs.values())


def pin_pr_context(tmp_path, monkeypatch, change="code"):
    """Real Git objects for the root PR merge, without network or real legs."""
    root = repo(tmp_path / "checkout", {
        "contracts/code-pin.yaml": b"code old\n",
        "contracts/spec-pin.yaml": b"spec old\n",
        "command": b"#!/usr/bin/env bash\necho before\n",
        "README.md": b"before\n"})

    def run(*args):
        return subprocess.check_output([
            "git", "-C", str(root), "-c", "user.name=Test",
            "-c", "user.email=test@invalid", *args]).decode().strip()

    revisions = {}
    for leg in ("code", "spec"):
        leg_root = root / leg
        repo(leg_root, {"sample": b"before\n"})
        old = run("-C", str(leg_root), "rev-parse", "HEAD")
        repo(leg_root, {"sample": b"after\n"})
        revisions[leg] = run("-C", str(leg_root), "rev-parse", "HEAD")
        run("-C", str(leg_root), "checkout", "--detach", "-q", old)
        run("update-index", "--add", "--cacheinfo", "160000," + old + "," + leg)
    if change == "create":
        run("rm", "contracts/code-pin.yaml")
    run("commit", "-qm", "base pins")
    base = run("rev-parse", "HEAD")
    legs = ("spec",) if change == "spec" else ("code", "spec") if change == "both" else ("code",)
    for leg in legs:
        if change != "pin-without-link" and change != "empty":
            run("-C", str(root / leg), "checkout", "--detach", "-q", revisions[leg])
            run("update-index", "--cacheinfo", "160000," + revisions[leg] + "," + leg)
        if change != "link-without-pin" and change != "empty":
            (root / "contracts" / (leg + "-pin.yaml")).write_text(leg + " new\n")
            run("add", "--", "contracts/" + leg + "-pin.yaml")
    if change in ("source", "docs"):
        path = "command" if change == "source" else "README.md"
        (root / path).write_text("#!/usr/bin/env bash\necho after\n")
        run("add", "--", path)
    if change == "mode":
        run("update-index", "--chmod=+x", "contracts/code-pin.yaml")
    if change == "rename":
        run("mv", "contracts/code-pin.yaml", "contracts/other-pin.yaml")
    if change == "delete":
        (root / "contracts/code-pin.yaml").unlink()
        run("add", "--update", "--", "contracts/code-pin.yaml")
    if change == "symlink":
        (root / "contracts/code-pin.yaml").unlink()
        (root / "contracts/code-pin.yaml").symlink_to("elsewhere")
        run("add", "--", "contracts/code-pin.yaml")
    run("commit", "--allow-empty", "-qm", "head")
    head = run("rev-parse", "HEAD")
    merge = run("commit-tree", "HEAD^{tree}", "-p", base, "-p", head, "-m", "PR test merge")
    run("checkout", "--detach", "-q", merge)
    event = {"number": 363, "pull_request": {
        "number": 363, "base": {"sha": base, "ref": "main", "repo": {"full_name": "opensoft/openRepoTools"}},
        "head": {"sha": head, "repo": {"full_name": "opensoft/openRepoTools"}}}}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))
    for name, value in {
        "GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_SHA": merge, "GITHUB_REPOSITORY": "opensoft/openRepoTools",
        "GITHUB_REF": "refs/pull/363/merge",
    }.items():
        monkeypatch.setenv(name, value)
    return {"root": root, "run": run, "event": event, "event_path": event_path,
            "manifest": {"commits": {".": merge}}, "base": base, "head": head, "merge": merge}


@pytest.mark.parametrize("change", ["code", "spec", "both"])
def test_pin_only_proof_binds_exact_ci_merge_and_paired_paths(assurance, tmp_path, monkeypatch, change):
    context = pin_pr_context(tmp_path, monkeypatch, change)
    proof = assurance.pin_only_pr_proof(context["root"], context["manifest"], "363")
    assert proof["base"] == context["base"]
    assert proof["head"] == context["head"]
    assert proof["merge"] == context["merge"]
    assert set(proof["paths"]) == ({"code", "contracts/code-pin.yaml", "spec", "contracts/spec-pin.yaml"}
                                  if change == "both" else {change, "contracts/" + change + "-pin.yaml"})


@pytest.mark.parametrize("change", [
    "source", "docs", "mode", "rename", "delete", "create", "symlink", "pin-without-link", "link-without-pin", "empty",
])
def test_pin_only_proof_refuses_nonpaired_or_uncertain_changes(assurance, tmp_path, monkeypatch, change):
    context = pin_pr_context(tmp_path, monkeypatch, change)
    assert assurance.pin_only_pr_proof(context["root"], context["manifest"], "363") is None


@pytest.mark.parametrize("failure", [
    "event-name", "repository", "ref", "ci-sha", "inventory-sha", "number", "base-ref",
    "head-repo", "base-repo", "parents", "nonmerge", "missing-event", "malformed-event", "missing-base", "dirty",
    "option-base", "range-base", "nonhex-base",
])
def test_pin_only_proof_refuses_unbound_event_or_git_identity(assurance, tmp_path, monkeypatch, failure):
    context = pin_pr_context(tmp_path, monkeypatch)
    event = context["event"]
    env = {"event-name": ("GITHUB_EVENT_NAME", "push"),
           "repository": ("GITHUB_REPOSITORY", "other/repo"),
           "ref": ("GITHUB_REF", "refs/heads/main"), "ci-sha": ("GITHUB_SHA", context["head"])}
    if failure in env:
        monkeypatch.setenv(*env[failure])
    elif failure == "inventory-sha":
        context["manifest"]["commits"]["."] = context["head"]
    elif failure == "number":
        event["number"] = 364
    elif failure == "base-ref":
        event["pull_request"]["base"]["ref"] = "other"
    elif failure in ("head-repo", "base-repo"):
        event["pull_request"][failure.split("-")[0]]["repo"]["full_name"] = "other/repo"
    elif failure == "parents":
        event["pull_request"]["base"]["sha"], event["pull_request"]["head"]["sha"] = context["head"], context["base"]
    elif failure == "nonmerge":
        context["run"]("checkout", "--detach", "-q", context["head"])
        context["manifest"]["commits"]["."] = context["head"]
        monkeypatch.setenv("GITHUB_SHA", context["head"])
    elif failure == "missing-base":
        event["pull_request"]["base"]["sha"] = "f" * 40
    elif failure == "dirty":
        (context["root"] / "command").write_text("#!/usr/bin/env bash\necho changed\n")
    elif failure in ("option-base", "range-base", "nonhex-base"):
        event["pull_request"]["base"]["sha"] = {
            "option-base": "--output=/tmp/not-a-revision", "range-base": context["base"] + "..HEAD",
            "nonhex-base": "z" * 40}[failure]
    context["event_path"].write_text(json.dumps(event))
    if failure == "missing-event":
        context["event_path"].unlink()
    elif failure == "malformed-event":
        context["event_path"].write_text("not json")
    assert assurance.pin_only_pr_proof(context["root"], context["manifest"], "363") is None


@pytest.mark.parametrize("failure", [
    None, "changed-component", "new-metric", "new-lines", "new-uncovered", "boolean-total",
    "real-source", "missing-event", "main",
])
def test_absent_pr_metric_requires_positive_pin_only_proof_in_analysis(
        assurance, tmp_path, monkeypatch, failure):
    context = pin_pr_context(tmp_path, monkeypatch, "source" if failure == "real-source" else "code")
    manifest = context["manifest"]
    manifest["files"] = [{"path": "code/lane", "language": "shell"}]
    out = tmp_path / "evidence"
    out.mkdir()
    (out / "inventory.json").write_text(json.dumps(manifest))
    task = tmp_path / "report-task.txt"
    task.write_text("projectKey=" + assurance.PROJECT + "\nceTaskId=task-123\n")
    if failure == "missing-event":
        context["event_path"].unlink()

    def api(endpoint, parameters):
        if endpoint == "ce/task":
            return {"task": {"status": "SUCCESS", "analysisId": "analysis-123"}}
        if endpoint == "qualitygates/project_status":
            return {"projectStatus": {"status": "OK", "conditions": [{"metricKey": "new_reliability_rating"}]}}
        if endpoint == "qualitygates/get_by_project":
            return {"qualityGate": {"id": 9}}
        if endpoint == "qualitygates/show":
            return {"conditions": [{"metric": key, "op": op, "error": value}
                                   for key, (op, value) in assurance.GATE.items()]}
        if endpoint == "components/tree":
            files = [{"path": "code/lane", "language": "shell"}] if failure == "changed-component" else []
            return {"paging": {"total": False if failure == "boolean-total" else len(files)}, "components": files}
        if endpoint == "measures/component":
            # Matches PR363's real omitted-eligibility response. These overall
            # metrics are diagnostic only: never credit complete main coverage.
            measures = [] if failure == "main" else [{"metric": "coverage", "value": "86.1"},
                                                       {"metric": "lines_to_cover", "value": "56163"}]
            if failure == "new-metric":
                measures.append({"metric": "new_coverage", "value": "90"})
            if failure in ("new-lines", "new-uncovered"):
                measures.append({"metric": "new_lines" if failure == "new-lines" else "new_uncovered_lines", "value": "1"})
            return {"component": {"measures": measures}}
        raise AssertionError(endpoint)

    monkeypatch.setattr(assurance, "sonar_api", api)
    pull_request = None if failure == "main" else "363"
    if failure:
        with pytest.raises(ValueError):
            assurance.verify_analysis(out, task, pull_request, root=context["root"])
        assert not (out / "acceptance.json").exists()
    else:
        receipt = assurance.verify_analysis(out, task, pull_request, root=context["root"])
        assert receipt["pin_only_pr"]["merge"] == context["merge"]
        assert receipt["coverage_condition_evaluated"] is False
        assert receipt["full_index_verified"] is False
        assert receipt["coverage_import_verified"] is False
        assert receipt["server_revision"] is None
        assert all(row["metric"] != "new_lines_to_cover" for row in receipt["measures"])
