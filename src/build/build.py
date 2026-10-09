#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from smoke_tests import (
    run_control_subprocess_timeout_smoke_test,
    run_repository_install_smoke_test,
    run_repository_uninstall_smoke_test,
    run_installer_preflight_smoke_test,
    run_updater_status_smoke_test,
    run_control_module_smoke_test,
    run_control_runtime_globals_smoke_test,
    run_admin_path_routing_smoke_test,
    run_strata_preset_smoke_test,
    run_metrics_dashboard_smoke_test,
    run_power_runtime_smoke_test,
)

ROOT = Path(__file__).resolve().parents[2]
SMOKE_TESTS = {
    "source_runtime": "Compile checked-in control/build modules without generating files",
    "control_subprocess_timeout_smoke": "Require timeouts for control subprocess calls",
    "repository_install_smoke": "Install services from a checkout without package/git mutation",
    "repository_uninstall_smoke": "Remove service registrations while preserving runtime data",
    "installer_preflight_smoke": "Reject missing prerequisites before writing files",
    "updater_status_smoke": "Run updater module status and report checkout revision",
    "control_module_smoke": "Run HTTP, benchmark-worker, and web-assets source paths with isolated state",
    "control_runtime_globals_smoke": "Resolve global loads in assembled controller callables",
    "admin_path_routing_smoke": "Exercise canonical admin shell routes and relocated GET APIs",
    "metrics_dashboard_smoke": "Render the four Metrics sections with preserved inference charts",
    "power_runtime_smoke": "Verify persisted power restoration and inference power transitions",
    "strata_preset_smoke": "Verify Strata preset inventory, pinned install metadata, and isolated artifacts",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run source-tree validation; release installer and payload generation are retired."
    )
    parser.add_argument(
        "--smoke-tests", action="append", default=[],
        help="Select source_runtime, control_subprocess_timeout_smoke, control_module_smoke, admin_path_routing_smoke, control_runtime_globals_smoke, installer_preflight_smoke, repository_install_smoke, repository_uninstall_smoke, updater_status_smoke, metrics_dashboard_smoke, power_runtime_smoke, or strata_preset_smoke (comma-separated).",
    )
    parser.add_argument("--list-smoke-tests", action="store_true", help="List source/runtime smoke checks and exit.")
    args = parser.parse_args(argv)
    if args.list_smoke_tests:
        print("\n".join(f"{name} - {description}" for name, description in SMOKE_TESTS.items()))
        return 0
    selected = {token.strip() for group in args.smoke_tests for token in group.split(",") if token.strip()} or set(SMOKE_TESTS)
    unknown = selected - SMOKE_TESTS.keys()
    if unknown:
        parser.error("Unknown --smoke-tests value(s): " + ", ".join(sorted(unknown)))

    failures: list[str] = []
    if "source_runtime" in selected:
        try:
            for package in (ROOT / "src" / "control", ROOT / "src" / "build"):
                for path in sorted(package.rglob("*.py")):
                    compile(path.read_bytes(), str(path), "exec")
        except (OSError, SyntaxError) as exc:
            failures.append(f"Source compilation failed: {exc}")
        print("source_runtime: " + ("failed" if failures else "passed - source modules compiled in memory"))
    checks = {
        "control_subprocess_timeout_smoke": run_control_subprocess_timeout_smoke_test,
        "installer_preflight_smoke": lambda: run_installer_preflight_smoke_test(ROOT),
        "repository_install_smoke": lambda: run_repository_install_smoke_test(ROOT),
        "repository_uninstall_smoke": lambda: run_repository_uninstall_smoke_test(ROOT),
        "updater_status_smoke": lambda: run_updater_status_smoke_test(ROOT),
        "control_module_smoke": lambda: run_control_module_smoke_test(ROOT),
        "control_runtime_globals_smoke": lambda: run_control_runtime_globals_smoke_test(ROOT),
        "admin_path_routing_smoke": lambda: run_admin_path_routing_smoke_test(ROOT),
        "metrics_dashboard_smoke": lambda: run_metrics_dashboard_smoke_test(ROOT),
        "power_runtime_smoke": lambda: run_power_runtime_smoke_test(ROOT),
        "strata_preset_smoke": lambda: run_strata_preset_smoke_test(ROOT),
    }
    for name, check in checks.items():
        if name not in selected:
            continue
        ok, detail = check()
        print(f"{name}: {'passed' if ok else 'failed'} - {detail}")
        if not ok:
            failures.append(detail)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
