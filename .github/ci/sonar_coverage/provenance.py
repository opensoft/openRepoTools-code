# SPDX-License-Identifier: Apache-2.0
"""Claim Python files only after hashing their bytes, including fixture copies."""
import hashlib
import json
import os
from pathlib import Path

from coverage import CoveragePlugin, FileTracer


class Source(FileTracer):
    def __init__(self, filename):
        self.filename = filename

    def source_filename(self):
        return self.filename


class Provenance(CoveragePlugin):
    def __init__(self, options):
        root = Path(os.environ["ORT_SONAR_ROOT"]).resolve()
        manifest = json.loads(Path(os.environ["ORT_SONAR_INVENTORY"]).read_text())
        self.sources = {}
        for item in manifest["files"]:
            if item["language"] == "py" and not item["test"]:
                self.sources.setdefault(item["sha256"], str(root / item["path"]))

    def file_tracer(self, filename):
        try:
            digest = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
        except OSError:
            return None
        canonical = self.sources.get(digest)
        return Source(canonical) if canonical else None

    def file_reporter(self, filename):
        return "python"


def coverage_init(registry, options):
    registry.add_file_tracer(Provenance(options))
