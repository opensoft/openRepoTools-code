# SPDX-License-Identifier: Apache-2.0
"""Advisory PR scope only. Never an admission receipt or a CI skip decision.

Read event JSON as data and inspect local git objects. No API calls, label/body
authority, shell evaluation, network, or writes to repository/profile/lane state.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCOPE = {"claude-current": "100755", "tests/test_claude_current.py": "100644"}
OBSERVE = {"opened", "synchronize", "reopened", "edited", "labeled",
           "unlabeled", "ready_for_review"}
SHA = re.compile(r"[0-9a-f]{40}\Z")


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=20).stdout


def classify(event_name: str, event: dict, root: Path, repository: str) -> dict:
    """Unknown, unreadable and unsafe inputs always retain full scope/checks."""
    result = {"mode": "shadow", "candidate_scope": "full", "required_ci": "full",
              "queue_admission": False, "reason": "unsupported-event",
              "base": None, "head": None, "files": []}
    if event_name != "pull_request" or not isinstance(event, dict):
        return result
    pr = event.get("pull_request")
    if not isinstance(pr, dict):
        result["reason"] = "missing-pr"
        return result
    action = event.get("action")
    if not isinstance(action, str) or action not in OBSERVE or pr.get("state") != "open":
        result["reason"] = "inactive-or-unsupported-pr-event"
        return result
    if pr.get("draft") is not False:
        result["reason"] = "draft-or-unknown-draft-state"
        return result
    try:
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        local = (repository and pr["base"]["repo"]["full_name"] == repository
                 and pr["head"]["repo"]["full_name"] == repository)
        if not local or not isinstance(base, str) or not isinstance(head, str):
            raise ValueError("foreign or missing identities")
        if not SHA.fullmatch(base) or not SHA.fullmatch(head):
            raise ValueError("invalid identities")
        result.update(base=base, head=head)
        merge_base = git(root, "merge-base", base, head).decode("ascii").strip()
        # --no-renames makes a rename include its deletion, which is full scope.
        raw = git(root, "diff", "--name-status", "-z", "--no-renames",
                  merge_base, head, "--").decode("utf-8", errors="strict")
        fields = raw.split("\0")
        if fields.pop() != "" or len(fields) % 2:
            raise ValueError("malformed diff")
        changes = list(zip(fields[::2], fields[1::2]))
        result["files"] = [name for _, name in changes]
        if not changes:
            result["reason"] = "empty-diff"
            return result
        for status, name in changes:
            if status not in {"A", "M"} or name not in SCOPE:
                result["reason"] = "mixed-or-unsupported-change"
                return result
            entry = git(root, "ls-tree", head, "--", name).decode("utf-8")
            if not entry.startswith(SCOPE[name] + " blob "):
                result["reason"] = "nonregular-or-changed-file-mode"
                return result
        result.update(candidate_scope="claude-current", reason="allowlisted-shadow-only")
    except (KeyError, TypeError, ValueError, OSError, UnicodeError,
            subprocess.SubprocessError):
        result["reason"] = "unreadable-or-invalid-context"
    return result


def main() -> None:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        event = {}
    result = classify(os.environ.get("GITHUB_EVENT_NAME", ""), event,
                      Path.cwd(), os.environ.get("GITHUB_REPOSITORY", ""))
    print(json.dumps(result, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        # Only fixed vocabulary is rendered; never a filename, body or label.
        with open(summary, "a", encoding="utf-8") as output:
            output.write("### CI-only pilot (advisory)\n\n"
                         f"Shadow scope: `{result['candidate_scope']}`; "
                         f"reason: `{result['reason']}`.\n\n"
                         "Full CI remains required. Queue admission: **no**.\n")


if __name__ == "__main__":
    main()
