#!/usr/bin/env python3
"""ThermalIntel V2 Phase 5 Validation Runner.

Unified executable entry point for the full production validation suite.
Runs all Phase 5 test categories and emits both machine-readable JSON
and human-readable terminal output.

Usage:
    python scripts/validation/run_validation.py [--json] [--suite <name>]

Exit codes:
    0  All validation suites passed
    1  One or more suites failed
    2  Runner error (misconfiguration, missing venv, etc.)
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PYTEST_BIN = REPO_ROOT.parent.parent / "thermalintel" / ".venv" / "bin" / "pytest"
if not PYTEST_BIN.exists():
    PYTEST_BIN = Path(sys.executable).parent / "pytest"

SUITES: Dict[str, Dict] = {
    "e2e": {
        "label": "End-to-End Pipeline (E2E)",
        "paths": ["tests/e2e/"],
        "description": "Full canonical pipeline from ProviderRun → Observation → Incident → Alert with SQLite persistence",
    },
    "integration_idempotency": {
        "label": "Idempotency & Duplicate Safety",
        "paths": ["tests/integration/test_idempotency_and_duplicates.py"],
        "description": "SHA-256 dedup, upsert idempotency, concurrent duplicate ingestion safety",
    },
    "integration_incident_lifecycle": {
        "label": "Incident Lifecycle Integrity",
        "paths": ["tests/integration/test_incident_lifecycle_integrity.py"],
        "description": "Stable identity, spatial/temporal continuity, severity escalation, quieting, reopening",
    },
    "integration_merge_split": {
        "label": "Merge/Split Integrity",
        "paths": ["tests/integration/test_merge_split_integrity.py"],
        "description": "Deterministic merge survivor selection, history non-erasure, split lineage",
    },
    "integration_alert_lifecycle": {
        "label": "Alert Lifecycle Integrity",
        "paths": ["tests/integration/test_alert_lifecycle_integrity.py"],
        "description": "Transition-driven AlertV2, deduplication, acknowledgement, flood protection",
    },
    "integration_degraded_cache": {
        "label": "Degraded Modes & Cache Behavior",
        "paths": ["tests/integration/test_degraded_modes_and_cache.py"],
        "description": "Cache fallback, stale detection, DEMO mode, upstream outage safety",
    },
    "fault_injection": {
        "label": "Fault Injection",
        "paths": ["tests/fault_injection/"],
        "description": "Upstream timeout, partial batch corruption, key redaction, provider isolation, graceful degradation",
    },
    "property": {
        "label": "Property-Based Invariants",
        "paths": ["tests/property/"],
        "description": "10 deterministic invariants: ID purity, idempotence, ordering invariance, quarantine safety, referential integrity, replay determinism",
    },
    "validation_timestamps": {
        "label": "Timestamp Provenance & Confidence",
        "paths": ["tests/validation/test_timestamp_provenance_confidence.py"],
        "description": "6 distinct timestamp semantics, zero fabrication, confidence score non-overlap",
    },
    "validation_replay": {
        "label": "Replay/Golden Determinism",
        "paths": ["tests/validation/test_replay_golden_determinism.py"],
        "description": "4 golden scenarios: industrial spike, vegetation fire, weak detection, provider degradation",
    },
    "baseline": {
        "label": "Existing V2 Baseline (Regression Guard)",
        "paths": [
            "tests/test_v2_contracts.py",
            "tests/test_v2_database.py",
            "tests/test_v2_canonical_pipeline_e2e.py",
            "tests/test_v2_normalization_quarantine.py",
            "tests/test_v2_identity_and_persistence.py",
            "tests/test_v2_firms_client.py",
            "tests/test_v2_api_routes.py",
            "tests/test_v2_migrations.py",
            "tests/test_v2_cache_and_seed_performance.py",
            "tests/test_normalization.py",
            "tests/test_repository.py",
            "tests/test_cache.py",
            "tests/test_data_service.py",
            "tests/test_v1_baseline_snapshot.py",
        ],
        "description": "All pre-existing V2 tests (364 tests) serving as regression guard",
    },
}

PHASE5_SUITES = [
    "e2e",
    "integration_idempotency",
    "integration_incident_lifecycle",
    "integration_merge_split",
    "integration_alert_lifecycle",
    "integration_degraded_cache",
    "fault_injection",
    "property",
    "validation_timestamps",
    "validation_replay",
]

ALL_SUITES = PHASE5_SUITES + ["baseline"]


def _run_suite(suite_key: str, suite: Dict, verbose: bool = False) -> Dict:
    """Execute a single test suite via pytest subprocess and return structured results."""
    paths = [str(REPO_ROOT / p) for p in suite["paths"]]
    cmd = [str(PYTEST_BIN), *paths, "--tb=short", "-q"]
    if verbose:
        cmd = [str(PYTEST_BIN), *paths, "--tb=short", "-v"]

    start = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    elapsed = round(time.time() - start, 2)

    # Parse pytest output for pass/fail/error counts
    passed = failed = errors = 0
    for line in result.stdout.splitlines():
        if " passed" in line:
            for part in line.split(","):
                part = part.strip()
                if "passed" in part:
                    try:
                        passed = int(part.split()[0])
                    except (ValueError, IndexError):
                        pass
                if "failed" in part:
                    try:
                        failed = int(part.split()[0])
                    except (ValueError, IndexError):
                        pass
                if "error" in part:
                    try:
                        errors = int(part.split()[0])
                    except (ValueError, IndexError):
                        pass

    success = result.returncode == 0

    return {
        "suite": suite_key,
        "label": suite["label"],
        "description": suite["description"],
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "elapsed_seconds": elapsed,
        "exit_code": result.returncode,
        "success": success,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _print_results(results: List[Dict], total_elapsed: float) -> None:
    """Print a concise human-readable summary to stdout."""
    WIDTH = 80
    print()
    print("=" * WIDTH)
    print("  ThermalIntel V2 Phase 5 Validation Report")
    print("=" * WIDTH)

    passed_suites = [r for r in results if r["success"]]
    failed_suites = [r for r in results if not r["success"]]
    total_tests = sum(r["passed"] for r in results)
    total_failures = sum(r["failed"] + r["errors"] for r in results)

    for r in results:
        icon = "✓" if r["success"] else "✗"
        status = "PASS" if r["success"] else "FAIL"
        count_str = f"{r['passed']} passed"
        if r["failed"]:
            count_str += f", {r['failed']} failed"
        if r["errors"]:
            count_str += f", {r['errors']} errors"
        print(f"  {icon} [{status}] {r['label']:<45} {count_str} ({r['elapsed_seconds']}s)")

    print("-" * WIDTH)
    print(f"  Suites: {len(passed_suites)}/{len(results)} passed")
    print(f"  Tests:  {total_tests} passed, {total_failures} failed")
    print(f"  Time:   {round(total_elapsed, 2)}s")
    print("=" * WIDTH)

    if failed_suites:
        print()
        print("FAILED SUITES:")
        for r in failed_suites:
            print(f"\n  ── {r['label']} ──")
            for line in r["stdout"].splitlines()[-20:]:
                print(f"    {line}")
        print()

    overall = "ALL PASS ✓" if not failed_suites else "FAILURES DETECTED ✗"
    print(f"\n  Overall: {overall}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ThermalIntel V2 Phase 5 Validation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available suites: {', '.join(ALL_SUITES)}",
    )
    parser.add_argument(
        "--suite",
        choices=list(SUITES.keys()) + ["all", "phase5"],
        default="phase5",
        help="Which suite(s) to run (default: phase5 — all Phase 5 tests)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Also write machine-readable JSON report to validation_report.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Pass -v to pytest for per-test output",
    )
    args = parser.parse_args()

    if args.suite == "all":
        suite_keys = ALL_SUITES
    elif args.suite == "phase5":
        suite_keys = PHASE5_SUITES
    else:
        suite_keys = [args.suite]

    print(f"\n[validation] Running {len(suite_keys)} suite(s): {', '.join(suite_keys)}")

    results: List[Dict] = []
    global_start = time.time()

    for key in suite_keys:
        suite = SUITES[key]
        print(f"\n[validation] ► {suite['label']} ...")
        result = _run_suite(key, suite, verbose=args.verbose)
        results.append(result)
        icon = "✓" if result["success"] else "✗"
        print(f"[validation] {icon} {result['label']}: {result['passed']} passed in {result['elapsed_seconds']}s")

    total_elapsed = time.time() - global_start
    _print_results(results, total_elapsed)

    if args.emit_json:
        report_path = REPO_ROOT / "validation_report.json"
        safe_results = [{k: v for k, v in r.items() if k not in ("stdout", "stderr")} for r in results]
        summary = {
            "suites_run": len(results),
            "suites_passed": sum(1 for r in results if r["success"]),
            "total_tests_passed": sum(r["passed"] for r in results),
            "total_failures": sum(r["failed"] + r["errors"] for r in results),
            "total_elapsed_seconds": round(total_elapsed, 2),
            "all_passed": all(r["success"] for r in results),
            "results": safe_results,
        }
        report_path.write_text(json.dumps(summary, indent=2))
        print(f"[validation] JSON report written to {report_path}")

    # Exit 0 iff all suites passed
    return 0 if all(r["success"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
