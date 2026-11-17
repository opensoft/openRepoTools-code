# SPDX-License-Identifier: Apache-2.0
"""Disabled P07/P09 preparation only; never imported by live delivery readers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import shadow_scope as common
import v13_shadow as projection

CONFIG = ".github/ci/v13-prepared-cohort.json"
SCOPE = "sql-register-v13-next-preparation"
TASKS = {
    "P07": ["T210", "T240", "T241", "T270", "T271", "T273"],
    "P09": ["T213", "T214", "T215", "T219", "T220", "T224", "T226", "T229",
            "T230", "T237", "T253", "T254", "T255", "T257", "T258", "T274",
            "T276", "T278", "T279"],
}
SOURCES = {
    "P07": (97, "007-p07-render-writes-shape-divergence-rollback-2"),
    "P09": (103, "007-p09-guard-measure-writes-disaster-drill-rollback"),
}
# Preparation ceilings only; every exact head and complete ordered chain is
# still bound separately. Never infer a new source binding from these limits.
HISTORY_LIMITS = {"P07": 40, "P09": 24}
FILES = {
    "P07": {**{f"tests/test_sql_register_{name}.py": "A" for name in
               ("divergence", "render", "renderer_git", "rollback", "shape", "writes")},
            "tests/fixtures/lanes-edit-v1.1.0/SHA256SUMS": "A",
            "tests/sql_register_cleanup.py": "A",
            "tests/fixtures/lanes-edit-v1.1.0/lanes-edit.sh": "A"},
    "P09": {**{f"tests/test_sql_register_{name}.py": "A" for name in
               ("bounds", "disaster", "drill", "guard", "landing_expired", "managed",
                "measure", "outage")},
            "tests/test_sql_register_fixture.py": "M", "tests/pgcluster.py": "M"},
}
FULL = {"mode": "preparation", "required_ci": "full", "skip_ci": False,
        "queue_admission": False, "activation": False,
        "review_references": "not-authenticated"}


def require(condition):
    if not condition:
        raise ValueError("Invalid disabled cohort preparation")


def read_policy(root):
    raw = (root / CONFIG).read_bytes()
    require(len(raw) <= 65536)
    policy = json.loads(raw, object_pairs_hook=projection.unique_pairs)
    require(isinstance(policy, dict) and set(policy) == {
        "schema_version", "enabled", "scope", "base", "prerequisite", "spec_revision",
        "owner_coordination", "held_prs", "order", "profiles"})
    require(type(policy["schema_version"]) is int and policy["schema_version"] == 1
            and policy["enabled"] is False and policy["scope"] == SCOPE
            and policy["held_prs"] == [106] and type(policy["held_prs"][0]) is int
            and policy["order"] == ["P07", "P09"]
            and type(policy["owner_coordination"]) is int and policy["owner_coordination"] > 0
            and isinstance(policy["profiles"], dict) and set(policy["profiles"]) == set(SOURCES))
    for key in ("base", "prerequisite", "spec_revision"):
        common.sha(policy[key])
    for name, profile in policy["profiles"].items():
        require(isinstance(profile, dict) and set(profile) == {
            "source", "observed_head", "owner_consent", "review", "tasks", "files"})
        common.sha(profile["observed_head"])
        require(profile["tasks"] == TASKS[name] and profile["files"] == FILES[name])
        source = profile["source"]
        require(isinstance(source, dict) and set(source) == {"number", "branch", "anchor", "head", "commits"})
        common.sha(source["anchor"])
        require(type(source["number"]) is int
                and (source["number"], source["branch"]) == SOURCES[name])
        commits = source["commits"]
        if source["head"] is None:
            require(commits == [] and profile["owner_consent"] is None and profile["review"] is None)
            continue
        common.sha(source["head"])
        require(isinstance(commits, list) and 1 <= len(commits) <= HISTORY_LIMITS[name]
                and all(isinstance(commit, str) for commit in commits)
                and len(set(commits)) == len(commits) and commits[-1] == source["head"])
        for commit in commits:
            common.sha(commit)
        for key in ("owner_consent", "review"):
            reference = profile[key]
            require(reference is None or (isinstance(reference, dict)
                    and set(reference) == {"head", "comment"}
                    and reference["head"] == source["head"]
                    and type(reference["comment"]) is int and reference["comment"] > 0))
    return policy, hashlib.sha256(raw).hexdigest()


def source_tree(root, policy, profile):
    projected = {**profile, "files": list(profile["files"])}
    anchor, head = profile["source"]["anchor"], profile["source"]["head"]
    common.git(root, "merge-base", "--is-ancestor", policy["prerequisite"], anchor)
    common.git(root, "merge-base", "--is-ancestor", anchor, policy["base"])
    require(projection.source_lineage(root, anchor, projected))
    changes = common.git(root, "diff", "--name-status", "--no-renames", anchor, head).decode()
    rows = [line.split("\t") for line in changes.splitlines()]
    require(all(len(row) == 2 for row in rows))
    expected = {**profile["files"], **{projection.MARKERS + task: "A" for task in profile["tasks"]}}
    require(len(rows) == len(expected) and {path: status for status, path in rows} == expected)


def inspect(root, main):
    result = {**FULL, "status": "refused", "reason": "invalid-preparation-context"}
    try:
        policy, digest = read_policy(root)
        require(common.sha(main) == policy["base"])
        common.git(root, "merge-base", "--is-ancestor", policy["prerequisite"], main)
        result["manifest_sha256"] = digest
        profiles = policy["profiles"]
        if any(profile["source"]["head"] is None for profile in profiles.values()):
            return {**result, "status": "pending-owner-heads", "reason": "unbound-source"}
        for profile in profiles.values():
            source_tree(root, policy, profile)
        heads = [profiles[name]["source"]["head"] for name in policy["order"]]
        require(common.git(root, "merge-base", "--all", *heads).decode().split()
                == [policy["prerequisite"]])
        previous, trees = main, []
        for name, head in zip(policy["order"], heads):
            tree = common.sha(common.git(root, "merge-tree", "--write-tree", previous, head).decode().strip())
            require(projection.scoped_diff(root, previous, tree, {
                **profiles[name], "files": list(profiles[name]["files"])}))
            trees.append({"profile": name, "tree": tree})
            if len(trees) == 1:
                previous = common.git(root, "-c", "user.name=Preparation preview",
                    "-c", "user.email=preview@example.invalid", "-c", "commit.gpgSign=false",
                    "commit-tree", tree, "-p", main, "-p", head,
                    "-m", "Preparation-only object; never a queue receipt").decode().strip()
        foundation = {}
        for path in projection.P01_FILES:
            before = common.git(root, "rev-parse", f"{main}:{path}").decode().strip()
            after = common.git(root, "rev-parse", f"{trees[-1]['tree']}:{path}").decode().strip()
            if before != after:
                foundation[path] = {"before": before, "after": after}
        ready = all(profile[key] is not None for profile in profiles.values()
                    for key in ("owner_consent", "review"))
        return {**result, "status": "preview-ready-for-review" if ready else "preview-pending-owner-reviews",
                "reason": "disabled-preparation-only", "base": main, "previews": trees,
                "foundation_changes_requiring_activation_review": foundation}
    except common.ERRORS:
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", required=True, help="Explicit observed main; never discovered or updated here")
    args = parser.parse_args()
    result = inspect(Path(__file__).resolve().parents[2], args.main)
    print(json.dumps(result, sort_keys=True))
    if result["status"] == "refused":
        parser.exit(1, "Preparation refused invalid, stale or unsupported evidence.\n")


if __name__ == "__main__":
    main()
