#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import build_support as support
from build_support import *
from smoke_tests import *


def cleanup_root_artifacts(report: BuildReport) -> None:
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


def compile_build_modules() -> None:
    for path in (
        BUILD_DIR / "build.py",
        BUILD_DIR / "build_support.py",
        BUILD_DIR / "smoke_tests.py",
        ROOT / "build.py",
    ):
        if path.exists():
            compile(read_text(path), str(path), "exec")


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
    write_text(backup_dir / f"install-club3090-server-{support.VERSION_TAG}.sh", built_script)
    write_text(backup_dir / SCRIPT_SOURCE_NAME, script_source)
    write_text(backup_dir / "control.py", control_source)
    write_text(backup_dir / "control.ship.py", built_control)
    write_text(backup_dir / "updater.py", updater_source)
    write_text(backup_dir / "web-ui.html", html_source)
    write_text(backup_dir / "web-ui.css", css_source)
    write_text(backup_dir / "web-ui.js", js_source)
    write_text(backup_dir / "code_syntax.json", read_text(CODE_SYNTAX_PATH))
    write_text(backup_dir / "web-ui.bundle.html", bundle_html)
    write_text(backup_dir / "web-ui.min.css", min_css)
    write_text(backup_dir / "web-ui.min.js", min_js)
    write_text(backup_dir / "web-ui.ship.raw.html", ship_raw_html)
    write_text(backup_dir / "web-ui.ship.html", ship_html)
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


def build_release(*, metadata: dict[str, str] | None = None, metadata_update_detail: str = "") -> int:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    metadata = metadata or load_build_metadata_inputs()
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

    change_log_latest_text = metadata["change_log_latest"]
    change_log_icons_text = metadata["change_log_icons"]
    club3090_version_text = metadata["club3090_version"]
    control_source = compose_control_source()
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

        flush_build_report(report, "running node syntax check for composed web-ui.js")
        source_js_ok, source_js_detail = validate_js_with_node(js_source, temp_dir, "web-ui.source.check.js")
        if not source_js_ok:
            report.add_test("node_js_syntax", "failed", source_js_detail or "node --check failed")
            flush_build_report(report, "build failed: node syntax check")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("node_js_syntax", "passed", "Composed web-ui.js passed node --check")

        flush_build_report(report, "running source UI smoke test")
        source_smoke_ok, source_smoke_detail = run_ui_smoke_test(bundled_js_source, temp_dir, "web-ui.source.smoke.cjs")
        if not source_smoke_ok:
            report.add_test("ui_boot_smoke_source", "failed", source_smoke_detail or "source UI smoke test failed")
            flush_build_report(report, "build failed: source UI smoke test")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("ui_boot_smoke_source", "passed", "Source UI booted successfully under the mocked DOM smoke test")

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
        built_control = inject_code_syntax_payload_into_control(control_source, code_syntax_gzip_base64)
        built_control = inject_html_payload_into_control(built_control, html_gzip_base64)
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

        flush_build_report(report, "running API contract smoke test")
        api_contract_ok, api_contract_detail = run_api_contract_smoke_test(temp_control, temp_dir, "control.api-contract.py")
        if not api_contract_ok:
            report.add_test("api_contract_smoke", "failed", api_contract_detail or "API contract smoke test failed")
            flush_build_report(report, "build failed: API contract smoke test")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("api_contract_smoke", "passed", api_contract_detail or "API contract smoke test passed")

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
            control_source=control_source,
            updater_text=updater_source,
            html_text=html_source,
            css_text=css_source,
            js_text=js_source,
            script_text=built_script,
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

        cleanup_root_artifacts(report)
        report.add_test("root_generated_cleanup", "passed", "Generated root bundle files were removed after the successful build, while web-ui.test.html was retained")
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
        required=True,
        help="User-facing release note bullet for this new version. Repeat for multiple bullets.",
    )
    parser.add_argument(
        "--iterative",
        action="store_true",
        help="Keep the current numeric version and advance only the optional letter suffix (for example v0.9.32 -> v0.9.32a). Without this switch, builds advance the numeric patch version (for example v0.9.32 -> v0.9.33).",
    )
    args = parser.parse_args(argv)
    metadata, metadata_update_detail = update_metadata_for_build(
        args.changes,
        iterative=bool(args.iterative),
    )
    configure_build_identity(metadata["version"], metadata["script_version"])
    return build_release(metadata=metadata, metadata_update_detail=metadata_update_detail)


if __name__ == "__main__":
    raise SystemExit(main())
