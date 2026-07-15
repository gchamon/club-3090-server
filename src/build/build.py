#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import build_support as support
from build_support import *
from smoke_tests import *


SMOKE_TEST_REGISTRY = [
    (1, "runtime_inventory_split_import_smoke", "Runtime inventory split import smoke"),
    (2, "changelog_icon_smoke", "Changelog icon metadata smoke"),
    (3, "control_subprocess_timeout_smoke", "Control subprocess timeout smoke"),
    (4, "ui_boot_smoke_source", "Source UI boot smoke"),
    (5, "ui_service_actions_smoke", "UI service actions smoke"),
    (6, "ui_boot_smoke_shipped", "Shipped UI boot smoke"),
    (7, "ui_ship_html_smoke", "Shipped HTML fixture smoke"),
    (8, "api_contract_smoke", "Control API contract smoke"),
    (9, "remote_update_metadata_smoke", "Remote update metadata smoke"),
    (10, "model_install_progress_smoke", "Model install progress smoke"),
    (11, "runtime_inventory_registry_smoke", "Runtime inventory registry smoke"),
    (12, "chat_state_race_smoke", "Chat state race smoke"),
    (13, "admin_auth_failure_cache_smoke", "Admin auth persistent-session smoke"),
    (14, "audit_log_filter_smoke", "Audit log filter smoke"),
    (15, "log_bootstrap_tail_smoke", "Log bootstrap tail smoke"),
    (16, "log_query_cli_smoke", "Log query CLI smoke"),
    (17, "debug_transfer_expansion_smoke", "Debug transfer expansion smoke"),
    (18, "storage_browser_chunk_smoke", "Storage browser chunk smoke"),
    (19, "docker_logrotate_refresh_smoke", "Docker logrotate refresh smoke"),
]
SMOKE_TEST_ID_TO_NAME = {str(test_id): name for test_id, name, _label in SMOKE_TEST_REGISTRY}
SMOKE_TEST_NAME_TO_ID = {name: test_id for test_id, name, _label in SMOKE_TEST_REGISTRY}
SMOKE_TEST_LABELS = {name: label for test_id, name, label in SMOKE_TEST_REGISTRY}


def smoke_test_list_text() -> str:
    return "\n".join(
        f"{test_id:02d} {name} - {label}"
        for test_id, name, label in SMOKE_TEST_REGISTRY
    )


def parse_smoke_test_selection(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    selected: set[str] = set()
    invalid: list[str] = []
    for raw_value in values:
        for token in str(raw_value or "").split(","):
            key = token.strip()
            if not key:
                continue
            if key.lower() in {"all", "*"}:
                return None
            if key in SMOKE_TEST_ID_TO_NAME:
                selected.add(SMOKE_TEST_ID_TO_NAME[key])
            elif key.lstrip("0") in SMOKE_TEST_ID_TO_NAME:
                selected.add(SMOKE_TEST_ID_TO_NAME[key.lstrip("0")])
            elif key in SMOKE_TEST_NAME_TO_ID:
                selected.add(key)
            else:
                invalid.append(key)
    if invalid:
        raise ValueError(
            "Unknown --smoke-tests value(s): "
            + ", ".join(invalid)
            + "\nAvailable smoke tests:\n"
            + smoke_test_list_text()
        )
    if not selected:
        raise ValueError("--smoke-tests was provided but no smoke test IDs were selected")
    return selected


class SmokeTestSelector:
    def __init__(self, selected: set[str] | None = None) -> None:
        self.selected = set(selected or []) if selected else None

    def limited(self) -> bool:
        return self.selected is not None

    def enabled(self, name: str) -> bool:
        return self.selected is None or name in self.selected

    def skip(self, report: BuildReport, name: str) -> bool:
        if self.enabled(name):
            return False
        test_id = SMOKE_TEST_NAME_TO_ID.get(name)
        id_text = f"#{test_id:02d} " if test_id is not None else ""
        report.add_test(name, "skipped", f"Skipped by --smoke-tests; {id_text}{SMOKE_TEST_LABELS.get(name, name)} was not selected")
        return True

    def selected_detail(self) -> str:
        if self.selected is None:
            return "all smoke tests enabled"
        rows = [
            f"#{SMOKE_TEST_NAME_TO_ID[name]:02d} {name}"
            for name in sorted(self.selected, key=lambda item: SMOKE_TEST_NAME_TO_ID.get(item, 9999))
        ]
        return "selected smoke tests: " + ", ".join(rows)


def cleanup_root_artifacts(report: BuildReport, *, remove_artifacts: bool = False) -> None:
    keep = {name.lower() for name in AUTHORITATIVE_FILES}
    generated = {name.lower() for name in GENERATED_ROOT_OUTPUTS}
    for name in GENERATED_ROOT_OUTPUTS:
        path = ROOT / name
        if not path.exists():
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            report.removed_root_artifacts.append(path.name)
        except Exception as exc:
            report.warn(f"cleanup skipped for {path.name}: {exc}")
    for pattern in DERIVED_ROOT_GLOBS:
        for path in ROOT.glob(pattern):
            if path.name.lower() in keep:
                continue
            if path.name.lower() in generated:
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                report.removed_root_artifacts.append(path.name)
            except Exception as exc:
                report.warn(f"cleanup skipped for {path.name}: {exc}")
    if remove_artifacts and ARTIFACTS_DIR.exists():
        try:
            shutil.rmtree(ARTIFACTS_DIR)
            report.removed_root_artifacts.append(ARTIFACTS_DIR.name)
        except Exception as exc:
            report.warn(f"cleanup skipped for {ARTIFACTS_DIR.name}: {exc}")


def compile_build_modules() -> None:
    for path in (
        BUILD_DIR / "build.py",
        BUILD_DIR / "build_support.py",
        BUILD_DIR / "smoke_tests.py",
        ROOT / "build.py",
    ):
        if path.exists():
            compile(read_text(path), str(path), "exec")


def upstream_checkout_dirs() -> list[Path]:
    checkouts = []
    for path in sorted(ROOT.iterdir(), key=lambda row: row.name.lower()):
        if path.is_dir() and path.name.startswith("club-3090"):
            checkouts.append(path)
    return checkouts


def validate_upstream_checkout_clean(report: BuildReport) -> bool:
    try:
        ensure_upstream_runtime_checkout()
    except Exception as exc:
        report.add_test("upstream_checkout_clean", "failed", str(exc))
        return False
    checkouts = [path for path in upstream_checkout_dirs() if (path / ".git").exists()]
    if not checkouts:
        report.add_test("upstream_checkout_clean", "skipped", "No club-3090 Git worktrees were found")
        return True
    dirty_files = []
    inspected = []
    for checkout in checkouts:
        inspected.append(checkout.name)
        for args in (
            ["git", "-C", str(checkout), "diff", "--name-only"],
            ["git", "-C", str(checkout), "diff", "--cached", "--name-only"],
            ["git", "-C", str(checkout), "ls-files", "--others", "--exclude-standard"],
        ):
            try:
                result = subprocess.run(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
            except Exception as exc:
                report.add_test("upstream_checkout_clean", "failed", f"could not inspect {checkout.name}: {exc}")
                return False
            if result.returncode != 0:
                detail = (result.stdout or f"git inspection failed for {checkout.name}").strip()[-1200:]
                report.add_test("upstream_checkout_clean", "failed", f"{checkout.name}: {detail}")
                return False
            dirty_files.extend(
                f"{checkout.name}/{str(line or '').strip()}"
                for line in str(result.stdout or "").splitlines()
                if str(line or "").strip()
            )
    dirty_files = sorted(set(dirty_files))
    if dirty_files:
        report.add_test(
            "upstream_checkout_clean",
            "failed",
            "Upstream checkout files are dirty; put compatibility adaptations in our control/installer layer instead: "
            + ", ".join(dirty_files[:30]),
        )
        return False
    report.add_test(
        "upstream_checkout_clean",
        "passed",
        "No tracked, staged, or untracked files in club-3090 upstream checkouts were modified: "
        + ", ".join(inspected),
    )
    return True


def backup_release_artifacts(
    report: BuildReport,
    *,
    script_source: str,
    control_source: str,
    updater_source: str,
    html_source: str,
    css_source: str,
    js_source: str,
    bundle_html: str,
    min_css: str,
    min_js: str,
    ship_raw_html: str,
    ship_html: str,
    built_control: str,
    built_script: str,
    test_html: str,
) -> None:
    backup_dir = ROOT / "backups" / f"backups_{support.BACKUP_TAG}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_artifacts_dir = backup_dir / ARTIFACTS_DIR.name
    backup_artifacts_dir.mkdir(parents=True, exist_ok=True)
    write_text(backup_dir / f"install-club3090-server-{support.VERSION_TAG}.sh", built_script)
    write_text(backup_dir / SCRIPT_SOURCE_NAME, script_source)
    write_text(backup_dir / "control.py", control_source)
    write_text(backup_artifacts_dir / "control.ship.py", built_control)
    write_text(backup_dir / "updater.py", updater_source)
    write_text(backup_dir / "web-ui.html", html_source)
    write_text(backup_dir / "web-ui.css", css_source)
    write_text(backup_dir / "web-ui.js", js_source)
    write_text(backup_dir / "code_syntax.json", read_text(CODE_SYNTAX_PATH))
    write_text(backup_dir / "web-ui.bundle.html", bundle_html)
    write_text(backup_dir / "web-ui.min.css", min_css)
    write_text(backup_dir / "web-ui.min.js", min_js)
    write_text(backup_artifacts_dir / "web-ui.ship.raw.html", ship_raw_html)
    write_text(backup_artifacts_dir / "web-ui.ship.html", ship_html)
    write_text(backup_dir / TEST_HTML_PATH.name, test_html)
    write_text(backup_dir / "build-report.json", json.dumps(report.__dict__, indent=2))

    for path in (
        ROOT / "package.json",
        ROOT / "package-lock.json",
        ROOT / "LICENSE",
        ROOT / "v07_PROGRESS_REPORT.MD",
        ROOT / "v07_CHECKLIST.MD",
    ):
        if path.exists():
            write_text(backup_dir / path.name, read_text(path))

    for source_dir in (CONTROL_SOURCE_DIR, WEB_SOURCE_DIR, BUILD_DIR):
        target_dir = backup_dir / source_dir.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(
            source_dir,
            target_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )


def build_release(
    *,
    metadata: dict[str, str] | None = None,
    metadata_update_detail: str = "",
    remove_artifacts: bool = False,
    smoke_test_selector: SmokeTestSelector | None = None,
) -> int:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    metadata = metadata or load_build_metadata_inputs()
    smoke_test_selector = smoke_test_selector or SmokeTestSelector()
    report = BuildReport(version=metadata["version"], script_version=metadata["script_version"])
    report.metadata_hash = str(metadata.get("hash") or "")
    report.metadata_mtime = float(metadata.get("mtime") or 0.0)
    report.change_log_latest_hash = hashlib.sha256(
        str(metadata.get("change_log_latest") or "").encode("utf-8")
    ).hexdigest()
    report.change_log_release_hash = hashlib.sha256(
        str(metadata.get("change_log_release") or "").encode("utf-8")
    ).hexdigest()
    write_text(BUILD_LOG_PATH, "")
    flush_build_report(report, f"build started for v{metadata['version']}")

    report.add_test(
        "metadata_update",
        "passed",
        metadata_update_detail or "metadata.json loaded for build",
    )
    if smoke_test_selector.limited():
        report.add_test(
            "smoke_test_selection",
            "passed",
            smoke_test_selector.selected_detail(),
        )
    if not validate_upstream_checkout_clean(report):
        flush_build_report(report, "build failed: upstream checkout has direct modifications")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1

    change_log_latest_text = metadata["change_log_latest"]
    change_log_icons_text = metadata["change_log_icons"]
    club3090_version_text = metadata["club3090_version"]
    control_source = compose_control_source()
    club3090_compat = json.loads(club3090_version_text or "{}")
    compat_marker = "SCRIPT_CLUB3090_COMPAT = {}"
    if control_source.count(compat_marker) != 1:
        report.add_test("control_compat_metadata", "failed", "control source compatibility marker is missing or duplicated")
        flush_build_report(report, "build failed: control compatibility metadata")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    control_source = control_source.replace(
        compat_marker,
        f"SCRIPT_CLUB3090_COMPAT = {club3090_compat!r}",
        1,
    )
    report.add_test("control_compat_metadata", "passed", "embedded tested Club-3090 compatibility metadata into control.py")
    updater_source = read_text(UPDATER_SOURCE_PATH)
    html_source = read_text(WEB_BASE_HTML_PATH)
    css_source = read_text(WEB_BASE_CSS_PATH)
    js_source = compose_web_js_source()
    script_source_raw = read_text(SCRIPT_SOURCE_PATH)
    try:
        script_source = inject_script_metadata(
            script_source_raw,
            script_version=metadata["script_version"],
            change_log_latest=change_log_latest_text,
            change_log_icons_json=change_log_icons_text,
            club3090_version_json=club3090_version_text,
        )
    except Exception as exc:
        report.add_test("script_metadata_injection", "failed", str(exc))
        flush_build_report(report, "build failed: script metadata injection")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("script_metadata_injection", "passed", "build.py injected script metadata into base.sh from the supplied build inputs")
    status_fixtures = load_status_fixtures()

    metadata_issues = validate_script_metadata(
        script_source,
        expected_version=metadata["version"],
        expected_script_version=metadata["script_version"],
        expected_change_log_latest=change_log_latest_text,
        expected_change_log_icons=change_log_icons_text,
        expected_club3090_version=club3090_version_text,
    )
    if metadata_issues:
        report.add_test("script_metadata_contract", "failed", "; ".join(metadata_issues))
        flush_build_report(report, "build failed: script metadata contract")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("script_metadata_contract", "passed", "base.sh/build.py metadata match the required build arguments")
    tailscale_ip_contract = (
        'emit_tailscale_ip_routes="true"' in script_source_raw
        and 'https://${tailscale_ip}:${ADMIN_PORT}' in script_source_raw
        and 'https://${tailscale_ip}:${PROXY_PORT}' in script_source_raw
        and 'tls ${TLS_CERT_FILE} ${TLS_KEY_FILE}' in script_source_raw
    )
    if not tailscale_ip_contract:
        report.add_test("tailscale_ip_tls_fallback", "failed", "base.sh is missing the direct Tailscale-IP self-signed HTTPS fallback routes")
        flush_build_report(report, "build failed: Tailscale-IP TLS fallback contract")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("tailscale_ip_tls_fallback", "passed", "Direct Tailscale-IP HTTPS routes retain the self-signed fallback certificate")

    report.warnings.extend(scan_duplicate_functions(WEB_JS_OUTPUT_PATH, js_source))
    report.warnings.extend(scan_potential_dead_code(js_source, html_source, css_source))
    duplicate_warnings = [warning for warning in report.warnings if "duplicate top-level" in warning]
    if duplicate_warnings:
        report.add_test("ui_duplicate_symbol_scan", "failed", "; ".join(duplicate_warnings))
        flush_build_report(report, "build failed during duplicate symbol scan")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("ui_duplicate_symbol_scan", "passed", "No duplicated top-level UI function symbols detected")
    report.add_test("dead_code_report", "passed", "No dead-code report warnings" if not report.warnings else "; ".join(report.warnings))
    description_issues = validate_model_score_description_source(js_source)
    if description_issues:
        report.add_test("model_score_description_source", "failed", "; ".join(description_issues))
        flush_build_report(report, "build failed during model score description source scan")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("model_score_description_source", "passed", "Model Score compliance descriptions include category-specific what/why/how text")
    flush_build_report(report, "completed static duplicate/dead-code scan")

    if 'HTML_GZIP_BASE64 = ""  # Injected by build.py for shipped outputs.\n' not in control_source:
        report.add_test("control_source_placeholder", "failed", "Generated control.py is missing the build-time HTML payload placeholder")
        flush_build_report(report, "build failed: control placeholder missing")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("control_source_placeholder", "passed", "Generated control.py keeps HTML as a compressed build-time placeholder")

    if 'CODE_SYNTAX_CONFIG_GZIP_BASE64 = ""  # Injected by build.py for shipped outputs.\n' not in control_source:
        report.add_test("control_code_syntax_placeholder", "failed", "Generated control.py is missing the code syntax payload placeholder")
        flush_build_report(report, "build failed: control code syntax placeholder missing")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("control_code_syntax_placeholder", "passed", "Generated control.py keeps the code syntax payload placeholder")

    if 'AI_STUDIO_EXTENSION_PAYLOAD_GZIP_BASE64 = ""  # Injected by build.py for shipped outputs.\n' not in control_source:
        report.add_test("control_ai_studio_extension_placeholder", "failed", "Generated control.py is missing the AI Studio extension payload placeholder")
        flush_build_report(report, "build failed: AI Studio extension placeholder missing")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("control_ai_studio_extension_placeholder", "passed", "Generated control.py keeps the AI Studio extension payload placeholder")

    if "/* injected by build.py from web-ui.css */" not in html_source or "// injected by build.py from web-ui.js" not in html_source:
        report.add_test("html_template_placeholders", "failed", "web/base.html is missing CSS/JS build placeholders")
        flush_build_report(report, "build failed: html placeholders missing")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("html_template_placeholders", "passed", "web/base.html keeps CSS/JS template placeholders")

    try:
        code_syntax_json = load_embedded_code_syntax_json()
        code_syntax_gzip_base64 = compress_code_syntax_json_to_gzip_base64(code_syntax_json)
    except Exception as exc:
        report.add_test("code_syntax_pack", "failed", str(exc))
        flush_build_report(report, "build failed: code syntax pack")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test(
        "code_syntax_pack",
        "passed",
        f"Packed code_syntax.json with {json.loads(code_syntax_json).get('language_alias_count', 0)} language aliases into {len(code_syntax_gzip_base64)} base64 chars",
    )
    try:
        source_code_syntax = json.loads(read_text(CODE_SYNTAX_PATH))
        embedded_code_syntax = json.loads(code_syntax_json)
        source_theme_tokens = dict((source_code_syntax.get("theme") or {}).get("tokens") or {})
        embedded_theme_tokens = dict((embedded_code_syntax.get("theme") or {}).get("tokens") or {})
        if source_theme_tokens != embedded_theme_tokens:
            raise ValueError("Embedded code_syntax theme tokens do not match web/code_syntax.json")
        source_aliases = {
            normalize_code_syntax_alias(key): str(value or "").strip()
            for key, value in dict(source_code_syntax.get("aliases") or {}).items()
            if normalize_code_syntax_alias(key) and str(value or "").strip()
        }
        for key, value in source_aliases.items():
            if embedded_code_syntax.get("aliases", {}).get(key) != value:
                raise ValueError(f"Embedded code_syntax alias {key!r} does not match web/code_syntax.json")
        required_array_keys = [
            "keywords",
            "storage",
            "types",
            "builtins",
            "constants",
            "literals",
            "function_declaration_keywords",
            "type_declaration_keywords",
            "namespace_declaration_keywords",
            "comment_patterns",
            "doc_comment_patterns",
            "preprocessor_patterns",
            "regex_patterns",
            "verbatim_string_patterns",
            "variable_patterns",
            "symbol_patterns",
            "macro_patterns",
            "operator_patterns",
            "class_patterns",
            "function_patterns",
            "builtin_patterns",
            "separator_patterns",
            "property_patterns",
            "parameter_patterns",
            "annotation_patterns",
            "decorator_patterns",
            "namespace_patterns",
            "tag_patterns",
            "attribute_patterns",
            "selector_patterns",
            "unit_patterns",
            "escape_patterns",
            "label_patterns",
            "inserted_patterns",
            "deleted_patterns",
            "meta_patterns",
        ]
        required_boolean_keys = ["case_insensitive", "character_literals", "regex_literals"]
        required_string_keys = ["annotation_token"]
        for family_name, family_definition in dict(source_code_syntax.get("families") or {}).items():
            if not isinstance(family_definition, dict):
                raise ValueError(f"code_syntax family {family_name!r} is not an object")
            for array_key in required_array_keys:
                if not isinstance(family_definition.get(array_key), list):
                    raise ValueError(
                        f"code_syntax family {family_name!r} is missing normalized array field {array_key!r}"
                    )
            for boolean_key in required_boolean_keys:
                if not isinstance(family_definition.get(boolean_key), bool):
                    raise ValueError(
                        f"code_syntax family {family_name!r} is missing normalized boolean field {boolean_key!r}"
                    )
            for string_key in required_string_keys:
                if not isinstance(family_definition.get(string_key), str):
                    raise ValueError(
                        f"code_syntax family {family_name!r} is missing normalized string field {string_key!r}"
                    )
    except Exception as exc:
        report.add_test("code_syntax_source_sync", "failed", str(exc))
        flush_build_report(report, "build failed: code syntax source sync")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test(
        "code_syntax_source_sync",
        "passed",
        f"Embedded code_syntax theme and configured aliases match {CODE_SYNTAX_PATH.relative_to(ROOT).as_posix()}",
    )

    bundled_css_source, bundled_js_source = compose_web_assets(css_source, js_source)
    bundle_html = inject_assets_into_html(html_source, bundled_css_source, bundled_js_source)

    with tempfile.TemporaryDirectory(prefix="club3090-build-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        temp_control = temp_dir / "control.ship.py"
        temp_script = temp_dir / SCRIPT_OUTPUT_NAME
        temp_bundle = temp_dir / "web-ui.bundle.html"
        temp_min_css = temp_dir / "web-ui.min.css"
        temp_min_js = temp_dir / "web-ui.min.js"
        temp_ship_raw = temp_dir / "web-ui.ship.raw.html"
        temp_ship = temp_dir / "web-ui.ship.html"

        write_text(temp_bundle, bundle_html)

        try:
            compile_build_modules()
            report.add_test("python_build_compile", "passed", "build modules compiled successfully")
        except Exception as exc:
            report.add_test("python_build_compile", "failed", str(exc))
            flush_build_report(report, "build failed: build module compilation")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1

        if not smoke_test_selector.skip(report, "runtime_inventory_split_import_smoke"):
            flush_build_report(report, "running runtime inventory split import smoke test")
            split_inventory_ok, split_inventory_detail = run_runtime_inventory_split_import_smoke_test(
                CONTROL_SOURCE_DIR / "runtime_inventory.py",
                CONTROL_SOURCE_DIR,
                temp_dir,
                "runtime-inventory.split-import.py",
            )
            if not split_inventory_ok:
                report.add_test("runtime_inventory_split_import_smoke", "failed", split_inventory_detail or "Runtime inventory split import smoke test failed")
                flush_build_report(report, "build failed: runtime inventory split import smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("runtime_inventory_split_import_smoke", "passed", split_inventory_detail or "Runtime inventory split import smoke test passed")

        if not smoke_test_selector.skip(report, "changelog_icon_smoke"):
            flush_build_report(report, "running changelog icon smoke test")
            changelog_icon_ok, changelog_icon_detail = run_changelog_change_icon_smoke_test()
            if not changelog_icon_ok:
                report.add_test("changelog_icon_smoke", "failed", changelog_icon_detail or "Changelog icon smoke test failed")
                flush_build_report(report, "build failed: changelog icon smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("changelog_icon_smoke", "passed", changelog_icon_detail or "Changelog icon smoke test passed")

        if not smoke_test_selector.skip(report, "control_subprocess_timeout_smoke"):
            flush_build_report(report, "running control subprocess timeout smoke test")
            subprocess_timeout_ok, subprocess_timeout_detail = run_control_subprocess_timeout_smoke_test()
            if not subprocess_timeout_ok:
                report.add_test("control_subprocess_timeout_smoke", "failed", subprocess_timeout_detail or "Control subprocess timeout smoke test failed")
                flush_build_report(report, "build failed: control subprocess timeout smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("control_subprocess_timeout_smoke", "passed", subprocess_timeout_detail or "Control subprocess timeout smoke test passed")

        flush_build_report(report, "running node syntax check for composed web-ui.js")
        source_js_ok, source_js_detail = validate_js_with_node(js_source, temp_dir, "web-ui.source.check.js")
        if not source_js_ok:
            report.add_test("node_js_syntax", "failed", source_js_detail or "node --check failed")
            flush_build_report(report, "build failed: node syntax check")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("node_js_syntax", "passed", "Composed web-ui.js passed node --check")

        if not smoke_test_selector.skip(report, "ui_boot_smoke_source"):
            flush_build_report(report, "running source UI smoke test")
            source_smoke_ok, source_smoke_detail = run_ui_smoke_test(bundled_js_source, temp_dir, "web-ui.source.smoke.cjs")
            if not source_smoke_ok:
                report.add_test("ui_boot_smoke_source", "failed", source_smoke_detail or "source UI smoke test failed")
                flush_build_report(report, "build failed: source UI smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("ui_boot_smoke_source", "passed", "Source UI booted successfully under the mocked DOM smoke test")

        if not smoke_test_selector.skip(report, "ui_service_actions_smoke"):
            flush_build_report(report, "running UI service action smoke test")
            service_smoke_ok, service_smoke_detail = run_ui_service_actions_smoke_test(
                bundled_js_source,
                temp_dir,
                "web-ui.service-actions.smoke.cjs",
            )
            if not service_smoke_ok:
                report.add_test("ui_service_actions_smoke", "failed", service_smoke_detail or "UI service action smoke test failed")
                flush_build_report(report, "build failed: UI service action smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("ui_service_actions_smoke", "passed", service_smoke_detail or "UI service action smoke test passed")

        flush_build_report(report, "running clean-css minification")
        try:
            min_css, css_minifier_detail = minify_css_with_clean_css(bundled_css_source, temp_dir)
        except Exception as exc:
            report.add_test("clean_css_minify", "failed", str(exc))
            flush_build_report(report, "build failed: clean-css minification")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("clean_css_minify", "passed", css_minifier_detail)
        write_text(temp_min_css, min_css)

        flush_build_report(report, "running terser minification")
        try:
            min_js, minifier_detail = minify_js_with_terser(bundled_js_source, temp_dir)
        except Exception as exc:
            report.add_test("terser_minify", "failed", str(exc))
            flush_build_report(report, "build failed: terser minification")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("terser_minify", "passed", minifier_detail)

        flush_build_report(report, "running shipped JS syntax check")
        shipped_ok, shipped_detail = validate_js_with_node(min_js, temp_dir, "web-ui.shipped.check.js")
        if not shipped_ok:
            report.add_test("node_js_shipped_syntax", "failed", shipped_detail or "shipped JS validation failed")
            flush_build_report(report, "build failed: shipped JS syntax check")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("node_js_shipped_syntax", "passed", "Terser-minified shipped JS passed node --check")

        if not smoke_test_selector.skip(report, "ui_boot_smoke_shipped"):
            flush_build_report(report, "running shipped JS smoke test")
            shipped_smoke_ok, shipped_smoke_detail = run_ui_smoke_test(min_js, temp_dir, "web-ui.shipped.smoke.cjs")
            if not shipped_smoke_ok:
                report.add_test("ui_boot_smoke_shipped", "failed", shipped_smoke_detail or "shipped UI smoke test failed")
                flush_build_report(report, "build failed: shipped JS smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("ui_boot_smoke_shipped", "passed", "Shipped UI booted successfully under the mocked DOM smoke test")

        ship_raw_html = inject_assets_into_html(html_source, min_css, min_js)
        ship_html = minify_html(ship_raw_html)
        fixture_results = []
        if not smoke_test_selector.skip(report, "ui_ship_html_smoke"):
            flush_build_report(report, f"running shipped HTML smoke tests for {len(status_fixtures)} fixtures")
            for index, (fixture_name, payload) in enumerate(status_fixtures, start=1):
                ok, detail = run_shipped_html_smoke_test(ship_html, payload, fixture_name, temp_dir, f"web-ui.ship-html-{index}.cjs")
                fixture_results.append((fixture_name, ok, detail))
                if not ok:
                    report.add_test("ui_ship_html_smoke", "failed", detail or f"Shipped HTML smoke failed for {fixture_name}")
                    flush_build_report(report, f"build failed: shipped HTML smoke test for {fixture_name}")
                    print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                    return 1
            report.add_test(
                "ui_ship_html_smoke",
                "passed",
                ", ".join(name for name, _, _ in fixture_results) if fixture_results else "No fixtures found",
            )

        html_gzip_base64 = compress_html_to_gzip_base64(ship_html)
        report.add_test(
            "admin_html_pack",
            "passed",
            f"Packed shipped admin HTML from {len(ship_html.encode('utf-8'))} bytes into {len(html_gzip_base64)} base64 chars",
        )
        try:
            gputemps_vendor_gzip_base64 = compress_gputemps_vendor_payload_to_gzip_base64()
        except Exception as exc:
            report.add_test("gputemps_vendor_pack", "failed", str(exc))
            flush_build_report(report, "build failed: gputemps vendor pack")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test(
            "gputemps_vendor_pack",
            "passed",
            f"Packed vendored gputemps.c and nvml.h into {len(gputemps_vendor_gzip_base64)} base64 chars",
        )
        try:
            ai_studio_extension_gzip_base64 = compress_ai_studio_extensions_payload_to_gzip_base64()
        except Exception as exc:
            report.add_test("ai_studio_extension_pack", "failed", str(exc))
            flush_build_report(report, "build failed: AI Studio extension pack")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test(
            "ai_studio_extension_pack",
            "passed",
            f"Packed AI Studio ComfyUI preview extension into {len(ai_studio_extension_gzip_base64)} base64 chars",
        )
        built_control = inject_code_syntax_payload_into_control(control_source, code_syntax_gzip_base64)
        built_control = inject_html_payload_into_control(built_control, html_gzip_base64)
        built_control = inject_ai_studio_extensions_payload_into_control(built_control, ai_studio_extension_gzip_base64)
        script_source = inject_gputemps_vendor_payload_into_script(script_source, gputemps_vendor_gzip_base64)
        built_script = inject_control_into_script(script_source, built_control)
        built_script = inject_updater_into_script(built_script, updater_source)
        report.add_test(
            "embedded_python_payload_pack",
            "passed",
            f"Packed control.py from {len(built_control.encode('utf-8'))} bytes into {len(compress_text_to_gzip_base64(built_control))} base64 chars and updater.py from {len(updater_source.encode('utf-8'))} bytes into {len(compress_text_to_gzip_base64(updater_source))} base64 chars",
        )
        write_text(temp_control, built_control)
        write_text(temp_script, built_script)
        write_text(temp_min_js, min_js)
        write_text(temp_ship_raw, ship_raw_html)
        write_text(temp_ship, ship_html)

        try:
            compile(built_control, str(temp_control), "exec")
            report.add_test("python_control_compile", "passed", "Injected control.py compiled successfully")
        except Exception as exc:
            report.add_test("python_control_compile", "failed", str(exc))
            flush_build_report(report, "build failed: control.py compilation")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1

        if not smoke_test_selector.skip(report, "api_contract_smoke"):
            flush_build_report(report, "running API contract smoke test")
            api_contract_ok, api_contract_detail = run_api_contract_smoke_test(temp_control, temp_dir, "control.api-contract.py")
            if not api_contract_ok:
                report.add_test("api_contract_smoke", "failed", api_contract_detail or "API contract smoke test failed")
                flush_build_report(report, "build failed: API contract smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("api_contract_smoke", "passed", api_contract_detail or "API contract smoke test passed")

        if not smoke_test_selector.skip(report, "remote_update_metadata_smoke"):
            flush_build_report(report, "running remote update metadata smoke test")
            remote_update_smoke_ok, remote_update_smoke_detail = run_remote_update_metadata_smoke_test(
                temp_control,
                temp_dir,
                "control.remote-update-metadata.py",
            )
            if not remote_update_smoke_ok:
                report.add_test("remote_update_metadata_smoke", "failed", remote_update_smoke_detail or "Remote update metadata smoke test failed")
                flush_build_report(report, "build failed: remote update metadata smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("remote_update_metadata_smoke", "passed", remote_update_smoke_detail or "Remote update metadata smoke test passed")

        if not smoke_test_selector.skip(report, "model_install_progress_smoke"):
            flush_build_report(report, "running model install progress smoke test")
            model_install_smoke_ok, model_install_smoke_detail = run_model_install_progress_smoke_test(
                temp_control,
                temp_dir,
                "control.model-install-progress.py",
            )
            if not model_install_smoke_ok:
                report.add_test("model_install_progress_smoke", "failed", model_install_smoke_detail or "Model install progress smoke test failed")
                flush_build_report(report, "build failed: model install progress smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("model_install_progress_smoke", "passed", model_install_smoke_detail or "Model install progress smoke test passed")

        if not smoke_test_selector.skip(report, "runtime_inventory_registry_smoke"):
            flush_build_report(report, "running runtime inventory registry smoke test")
            inventory_registry_ok, inventory_registry_detail = run_runtime_inventory_registry_smoke_test(
                temp_control,
                temp_dir,
                ROOT,
                "control.runtime-inventory-registry.py",
            )
            if not inventory_registry_ok:
                report.add_test("runtime_inventory_registry_smoke", "failed", inventory_registry_detail or "Runtime inventory registry smoke test failed")
                flush_build_report(report, "build failed: runtime inventory registry smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("runtime_inventory_registry_smoke", "passed", inventory_registry_detail or "Runtime inventory registry smoke test passed")

        if not smoke_test_selector.skip(report, "chat_state_race_smoke"):
            flush_build_report(report, "running chat state race smoke test")
            chat_race_ok, chat_race_detail = run_chat_state_race_smoke_test(
                temp_control,
                temp_dir,
                "control.chat-state-race.py",
            )
            if not chat_race_ok:
                report.add_test("chat_state_race_smoke", "failed", chat_race_detail or "Chat state race smoke test failed")
                flush_build_report(report, "build failed: chat state race smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("chat_state_race_smoke", "passed", chat_race_detail or "Chat state race smoke test passed")

        if not smoke_test_selector.skip(report, "admin_auth_failure_cache_smoke"):
            flush_build_report(report, "running admin auth failure cache smoke test")
            admin_auth_cache_ok, admin_auth_cache_detail = run_admin_auth_failure_cache_smoke_test(
                temp_control,
                temp_dir,
                "control.admin-auth-failure-cache.py",
            )
            if not admin_auth_cache_ok:
                report.add_test("admin_auth_failure_cache_smoke", "failed", admin_auth_cache_detail or "Admin auth failure cache smoke test failed")
                flush_build_report(report, "build failed: admin auth failure cache smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("admin_auth_failure_cache_smoke", "passed", admin_auth_cache_detail or "Admin auth failure cache smoke test passed")

        if not smoke_test_selector.skip(report, "audit_log_filter_smoke"):
            flush_build_report(report, "running audit log filter smoke test")
            audit_filter_ok, audit_filter_detail = run_audit_log_filter_smoke_test(
                temp_control,
                temp_dir,
                "control.audit-log-filter.py",
            )
            if not audit_filter_ok:
                report.add_test("audit_log_filter_smoke", "failed", audit_filter_detail or "Audit log filter smoke test failed")
                flush_build_report(report, "build failed: audit log filter smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("audit_log_filter_smoke", "passed", audit_filter_detail or "Audit log filter smoke test passed")

        if not smoke_test_selector.skip(report, "log_bootstrap_tail_smoke"):
            flush_build_report(report, "running log bootstrap tail smoke test")
            log_tail_ok, log_tail_detail = run_log_bootstrap_tail_smoke_test(
                temp_control,
                temp_dir,
                "control.log-bootstrap-tail.py",
            )
            if not log_tail_ok:
                report.add_test("log_bootstrap_tail_smoke", "failed", log_tail_detail or "Log bootstrap tail smoke test failed")
                flush_build_report(report, "build failed: log bootstrap tail smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("log_bootstrap_tail_smoke", "passed", log_tail_detail or "Log bootstrap tail smoke test passed")

        if not smoke_test_selector.skip(report, "log_query_cli_smoke"):
            flush_build_report(report, "running log query CLI smoke test")
            log_query_ok, log_query_detail = run_log_query_cli_smoke_test(
                temp_control,
                temp_dir,
                "control.log-query-cli.py",
            )
            if not log_query_ok:
                report.add_test("log_query_cli_smoke", "failed", log_query_detail or "Log query CLI smoke test failed")
                flush_build_report(report, "build failed: log query CLI smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("log_query_cli_smoke", "passed", log_query_detail or "Log query CLI smoke test passed")

        if not smoke_test_selector.skip(report, "debug_transfer_expansion_smoke"):
            flush_build_report(report, "running debug transfer expansion smoke test")
            debug_transfer_ok, debug_transfer_detail = run_debug_transfer_expansion_smoke_test(
                temp_control,
                temp_dir,
                "control.debug-transfer-expansion.py",
            )
            if not debug_transfer_ok:
                report.add_test("debug_transfer_expansion_smoke", "failed", debug_transfer_detail or "Debug transfer expansion smoke test failed")
                flush_build_report(report, "build failed: debug transfer expansion smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("debug_transfer_expansion_smoke", "passed", debug_transfer_detail or "Debug transfer expansion smoke test passed")

        if not smoke_test_selector.skip(report, "storage_browser_chunk_smoke"):
            flush_build_report(report, "running storage browser chunk smoke test")
            storage_chunk_ok, storage_chunk_detail = run_storage_browser_chunk_smoke_test(
                temp_control,
                temp_dir,
                "control.storage-browser-chunk.py",
            )
            if not storage_chunk_ok:
                report.add_test("storage_browser_chunk_smoke", "failed", storage_chunk_detail or "Storage browser chunk smoke test failed")
                flush_build_report(report, "build failed: storage browser chunk smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("storage_browser_chunk_smoke", "passed", storage_chunk_detail or "Storage browser chunk smoke test passed")

        if not smoke_test_selector.skip(report, "docker_logrotate_refresh_smoke"):
            flush_build_report(report, "running docker logrotate refresh smoke test")
            logrotate_ok, logrotate_detail = run_docker_logrotate_refresh_smoke_test(
                temp_control,
                temp_dir,
                "control.docker-logrotate.py",
            )
            if not logrotate_ok:
                report.add_test("docker_logrotate_refresh_smoke", "failed", logrotate_detail or "Docker logrotate refresh smoke test failed")
                flush_build_report(report, "build failed: docker logrotate refresh smoke test")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("docker_logrotate_refresh_smoke", "passed", logrotate_detail or "Docker logrotate refresh smoke test passed")

        script_embedded = extract_embedded_control(built_script)
        if script_embedded != built_control.rstrip("\n"):
            detail = "Embedded control block does not exactly match built control.py"
            report.add_test("embedded_control_match", "failed", detail)
            flush_build_report(report, "build failed: embedded control mismatch")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("embedded_control_match", "passed", "Embedded control block matches built control.py")

        missing_flow_items = validate_flow_branches(built_script)
        if missing_flow_items:
            detail = "Missing flow markers: " + ", ".join(missing_flow_items)
            report.add_test("installer_flow_scan", "failed", detail)
            flush_build_report(report, "build failed: installer flow scan")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("installer_flow_scan", "passed", "Install/update/migrate flow markers detected")

        installer_contract_issues = validate_installer_control_contract(built_script, built_control)
        if installer_contract_issues:
            detail = "; ".join(installer_contract_issues)
            report.add_test("installer_control_contract", "failed", detail)
            flush_build_report(report, "build failed: installer control contract mismatch")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("installer_control_contract", "passed", "Installer validator matches control.py functions")

        flush_build_report(report, "running bash syntax check")
        bash_path = Path(r"C:\Program Files\Git\bin\bash.exe")
        if bash_path.exists():
            bash_check = run_command([str(bash_path), "-lc", f"bash -n {SCRIPT_OUTPUT_NAME}"], temp_dir)
            if bash_check.returncode != 0:
                detail = (bash_check.stderr or bash_check.stdout or "bash -n failed").strip()
                report.add_test("bash_script_syntax", "failed", detail)
                flush_build_report(report, "build failed: bash syntax check")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("bash_script_syntax", "passed", f"{SCRIPT_OUTPUT_NAME} passed bash -n")
        else:
            report.warn("Git Bash was not found locally; bash syntax validation was skipped")
            report.add_test("bash_script_syntax", "skipped", "Git Bash not found")

        if "\r" in built_script or "\r" in built_control or "\r" in js_source:
            detail = "CRLF detected in built outputs"
            report.add_test("lf_line_endings", "failed", detail)
            flush_build_report(report, "build failed: LF line ending check")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("lf_line_endings", "passed", "Built outputs use LF line endings only")

        sync_generated_root_sources(
            control_source=built_control,
            updater_text=updater_source,
            html_text=html_source,
            css_text=css_source,
            js_text=js_source,
            script_text=built_script,
            bundle_html=bundle_html,
            min_css=min_css,
            min_js=min_js,
            ship_raw_html=ship_raw_html,
            ship_html=ship_html,
        )

        flush_build_report(report, "generating test HTML artifact")
        try:
            test_html, test_html_detail = generate_test_html_artifact()
        except Exception as exc:
            report.add_test("test_html_artifact", "failed", str(exc))
            flush_build_report(report, "build failed: test HTML artifact generation")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("test_html_artifact", "passed", test_html_detail or "test html smoke ok")

        expected_artifacts = [
            CONTROL_OUTPUT_PATH,
            UPDATER_OUTPUT_PATH,
            WEB_HTML_OUTPUT_PATH,
            WEB_CSS_OUTPUT_PATH,
            WEB_JS_OUTPUT_PATH,
            WEB_BUNDLE_HTML_OUTPUT_PATH,
            WEB_MIN_CSS_OUTPUT_PATH,
            WEB_MIN_JS_OUTPUT_PATH,
            WEB_SHIP_RAW_HTML_OUTPUT_PATH,
            WEB_SHIP_HTML_OUTPUT_PATH,
            TEST_HTML_PATH,
        ]
        missing_artifacts = [
            path.relative_to(ROOT).as_posix()
            for path in expected_artifacts
            if not path.exists() or (path.is_file() and path.stat().st_size <= 0)
        ]
        if missing_artifacts:
            detail = "Missing generated artifact(s): " + ", ".join(missing_artifacts)
            report.add_test("artifact_folder_outputs", "failed", detail)
            flush_build_report(report, "build failed: artifact folder outputs")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test(
            "artifact_folder_outputs",
            "passed",
            "Generated control, base assets, minified web UI, and test HTML were written under artifacts/",
        )

        backup_release_artifacts(
            report,
            script_source=script_source,
            control_source=control_source,
            updater_source=updater_source,
            html_source=html_source,
            css_source=css_source,
            js_source=js_source,
            bundle_html=bundle_html,
            min_css=min_css,
            min_js=min_js,
            ship_raw_html=ship_raw_html,
            ship_html=ship_html,
            built_control=built_control,
            built_script=built_script,
            test_html=test_html,
        )
        backup_artifacts_dir = ROOT / "backups" / f"backups_{support.BACKUP_TAG}" / ARTIFACTS_DIR.name
        misplaced_backup_ship_artifacts = [
            path.name
            for path in (
                backup_artifacts_dir.parent / "control.ship.py",
                backup_artifacts_dir.parent / "web-ui.ship.raw.html",
                backup_artifacts_dir.parent / "web-ui.ship.html",
            )
            if path.exists()
        ]
        missing_backup_ship_artifacts = [
            path.name
            for path in (
                backup_artifacts_dir / "control.ship.py",
                backup_artifacts_dir / "web-ui.ship.raw.html",
                backup_artifacts_dir / "web-ui.ship.html",
            )
            if not path.exists() or path.stat().st_size <= 0
        ]
        if misplaced_backup_ship_artifacts or missing_backup_ship_artifacts:
            detail_parts = []
            if misplaced_backup_ship_artifacts:
                detail_parts.append("misplaced at backup root: " + ", ".join(misplaced_backup_ship_artifacts))
            if missing_backup_ship_artifacts:
                detail_parts.append("missing from backup artifacts/: " + ", ".join(missing_backup_ship_artifacts))
            detail = "; ".join(detail_parts)
            report.add_test("backup_ship_artifact_layout", "failed", detail)
            flush_build_report(report, "build failed: backup ship artifact layout")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test(
            "backup_ship_artifact_layout",
            "passed",
            "Shipped control and web artifacts were retained under the release backup artifacts/ folder",
        )

        cleanup_root_artifacts(report, remove_artifacts=remove_artifacts)
        cleanup_detail = (
            "Generated root bundle files were removed after the successful build, and the artifacts folder was removed by --remove-artifacts"
            if remove_artifacts
            else "Generated root bundle files were removed after the successful build; release artifacts were retained under artifacts/"
        )
        report.add_test("root_generated_cleanup", "passed", cleanup_detail)
        write_text(BUILD_LAST_SUCCESS_PATH, report.to_json() + "\n")

    flush_build_report(report, "build completed successfully")
    print(json.dumps(report.__dict__, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Club-3090 release artifacts and automatically bump metadata.json for the new version.",
    )
    parser.add_argument(
        "--change",
        "--changes",
        dest="changes",
        action="append",
        nargs="+",
        help="User-facing release note bullet for this new version. Repeat for multiple bullets, or pass multiple entries after --changes.",
    )
    parser.add_argument(
        "--smoke-tests",
        dest="smoke_tests",
        action="append",
        default=[],
        help="Run only the selected smoke test IDs or names, comma-separated. Use --list-smoke-tests to see IDs. Intended for targeted iteration only; omit for full release validation.",
    )
    parser.add_argument(
        "--list-smoke-tests",
        action="store_true",
        help="Print numeric smoke test IDs and exit without building.",
    )
    parser.add_argument(
        "--iterative",
        action="store_true",
        help="Keep the current numeric version and advance only the optional letter suffix (for example v0.9.32 -> v0.9.32a). Without this switch, builds advance the numeric patch version (for example v0.9.32 -> v0.9.33).",
    )
    parser.add_argument(
        "--version",
        dest="target_version",
        default="",
        help="Build exactly this version instead of applying the default patch bump. Cannot be combined with --iterative.",
    )
    parser.add_argument(
        "--remove-artifacts",
        action="store_true",
        help="Delete the generated artifacts/ folder after a successful build. By default the folder is retained for inspection.",
    )
    args = parser.parse_args(argv)
    if args.list_smoke_tests:
        print(smoke_test_list_text())
        return 0
    if not args.changes:
        parser.error("--change/--changes is required unless --list-smoke-tests is used")
    try:
        selected_smoke_tests = parse_smoke_test_selection(args.smoke_tests)
    except ValueError as exc:
        parser.error(str(exc))
    smoke_test_selector = SmokeTestSelector(selected_smoke_tests)
    original_metadata_text = support.read_text(support.METADATA_FILE)
    try:
        change_entries = [entry for group in (args.changes or []) for entry in group]
        metadata, metadata_update_detail = update_metadata_for_build(
            change_entries,
            iterative=bool(args.iterative),
            target_version=str(args.target_version or "").strip(),
        )
        configure_build_identity(metadata["version"], metadata["script_version"])
        result = build_release(
            metadata=metadata,
            metadata_update_detail=metadata_update_detail,
            remove_artifacts=bool(args.remove_artifacts),
            smoke_test_selector=smoke_test_selector,
        )
    except Exception:
        support.write_text(support.METADATA_FILE, original_metadata_text)
        raise
    if result != 0:
        support.write_text(support.METADATA_FILE, original_metadata_text)
        print("metadata.json restored because the build did not complete successfully")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
