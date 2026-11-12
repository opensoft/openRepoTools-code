# SPDX-License-Identifier: Apache-2.0
"""Explicit opt-in only; this module is placed on PYTHONPATH for the CI run."""
import os

if os.environ.get("ORT_SONAR_INVENTORY") and os.environ.get("COVERAGE_PROCESS_START"):
    import coverage
    coverage.process_startup()
