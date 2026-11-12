# SPDX-License-Identifier: Apache-2.0
"""Explicit opt-in only; this module is placed on PYTHONPATH for the CI run."""
import os

if os.environ.get("ORT_SONAR_INVENTORY") and os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage
    except ModuleNotFoundError as exc:
        if exc.name != "coverage":
            raise
        # Tests deliberately create clean product environments. Preserve their
        # dependency isolation; unobserved executions receive no coverage credit.
    else:
        coverage.process_startup()
