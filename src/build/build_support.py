#!/usr/bin/env python3
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


BUILD_DIR = Path(__file__).resolve().parent
SRC_DIR = BUILD_DIR.parent
ROOT = SRC_DIR.parent
CONTROL_SOURCE_DIR = SRC_DIR / "control"
WEB_SOURCE_DIR = SRC_DIR / "web"
VENDOR_SOURCE_DIR = BUILD_DIR / "vendor"
EXTENSIONS_SOURCE_DIR = ROOT / "extensions"
UPSTREAM_RUNTIME_DIR = ROOT / "club-3090"
UPSTREAM_RUNTIME_REPO_URL = os.environ.get("CLUB3090_UPSTREAM_REPO_URL", "https://github.com/noonghunna/club-3090.git")
LOGS_DIR = ROOT / "logs"
ARTIFACTS_DIR = ROOT / "artifacts"
SCRIPT_SOURCE_NAME = "base.sh"
SCRIPT_OUTPUT_NAME = "install-club3090-server.sh"
SCRIPT_SOURCE_PATH = BUILD_DIR / SCRIPT_SOURCE_NAME
SCRIPT_OUTPUT_PATH = ROOT / SCRIPT_OUTPUT_NAME
METADATA_FILE = ROOT / "metadata.json"
UPDATER_SOURCE_PATH = BUILD_DIR / "updater.py"
UPDATER_OUTPUT_PATH = ARTIFACTS_DIR / "updater.py"
CONTROL_OUTPUT_PATH = ARTIFACTS_DIR / "control.py"
WEB_HTML_OUTPUT_PATH = ARTIFACTS_DIR / "base.html"
WEB_CSS_OUTPUT_PATH = ARTIFACTS_DIR / "base.css"
WEB_JS_OUTPUT_PATH = ARTIFACTS_DIR / "base.js"
WEB_BUNDLE_HTML_OUTPUT_PATH = ARTIFACTS_DIR / "web-ui.bundle.html"
WEB_MIN_CSS_OUTPUT_PATH = ARTIFACTS_DIR / "web-ui.min.css"
WEB_MIN_JS_OUTPUT_PATH = ARTIFACTS_DIR / "web-ui.min.js"
WEB_SHIP_RAW_HTML_OUTPUT_PATH = ARTIFACTS_DIR / "web-ui.ship.raw.html"
WEB_SHIP_HTML_OUTPUT_PATH = ARTIFACTS_DIR / "web-ui.html"
WEB_BASE_HTML_PATH = WEB_SOURCE_DIR / "base.html"
WEB_BASE_CSS_PATH = WEB_SOURCE_DIR / "base.css"
CODE_SYNTAX_PATH = WEB_SOURCE_DIR / "code_syntax.json"
GPUTEMPS_SOURCE_PATH = VENDOR_SOURCE_DIR / "gputemps.c"
NVML_HEADER_PATH = VENDOR_SOURCE_DIR / "nvml.h"
FIXTURES_DIR = BUILD_DIR / "text-fixtures"
BUILD_REPORT_PATH = LOGS_DIR / "build-report.json"
BUILD_LAST_SUCCESS_PATH = LOGS_DIR / "build-last-success.json"
BUILD_LOG_PATH = LOGS_DIR / "build.log"
TEST_HTML_PATH = ARTIFACTS_DIR / "web-ui.test.html"
HIGHLIGHT_SUPPORTED_LANGUAGES_PATH = ROOT / "node_modules" / "highlight.js" / "SUPPORTED_LANGUAGES.md"
CONTROL_SOURCE_ORDER = [
    "shared.py",
    "chat.py",
    "runtime_inventory.py",
    "services_config.py",
    "mcp.py",
    "auth.py",
    "presets.py",
    "instances.py",
    "benchmarks.py",
    "scripts.py",
    "image_studio.py",
    "logs.py",
    "system.py",
    "proxy_chat.py",
    "http_server.py",
]
WEB_JS_SOURCE_ORDER = [
    "core.js",
    "log_cards.js",
    "charts.js",
    "state.js",
    "layout_users.js",
    "instances_presets.js",
    "runtime_state.js",
    "system.js",
    "logs.js",
    "app.js",
    "chat.js",
]
def _read_initial_build_identity() -> tuple[str, str]:
    script_path = SCRIPT_SOURCE_PATH
    fallback_script_version = f"{date.today().isoformat()}.v0.0.0"
    fallback_version = "0.0.0"
    try:
        source = script_path.read_text(encoding="utf-8")
    except Exception:
        return fallback_version, fallback_script_version
    match = re.search(r'^SCRIPT_VERSION="([^"]+)"$', source, flags=re.M)
    script_version = match.group(1).strip() if match else fallback_script_version
    version_match = re.search(r"v(\d+\.\d+\.\d+)\s*$", script_version)
    version = version_match.group(1) if version_match else fallback_version
    return version, script_version


VERSION, SCRIPT_VERSION = _read_initial_build_identity()
VERSION_TAG = f"v{VERSION}"
BACKUP_TAG = f"v{VERSION.replace('.', '')}"
AUTHORITATIVE_FILES = [
    SCRIPT_SOURCE_NAME,
    SCRIPT_OUTPUT_NAME,
    "build.py",
    "metadata.json",
    "package.json",
    "package-lock.json",
    "v07_CHECKLIST.MD",
]
GENERATED_ROOT_OUTPUTS = [
    "control.py",
    "updater.py",
    "web-ui.html",
    "web-ui.css",
    "web-ui.js",
    "web-ui.test.html",
]
DERIVED_ROOT_GLOBS = [
    "_tmp_*",
    "*.bundle.html",
    "*.min.css",
    "*.min.js",
    "*.ship.html",
    "*.ship.raw.html",
    "*.pyc",
    "__pycache__",
]
DEFAULT_TOOL_TIMEOUT_SECONDS = 45
MERMAID_LAB_EXPECTED_COUNTS = {
    "Mermaid flowchart": 9,
    "Mermaid sequence diagram": 6,
    "Mermaid class diagram": 4,
    "Mermaid state diagram": 4,
    "Mermaid gantt chart": 4,
    "Mermaid pie chart": 2,
    "Mermaid git graph": 2,
    "Mermaid journey diagram": 2,
    "Mermaid mindmap": 3,
    "Mermaid timeline": 2,
    "Mermaid quadrant chart": 2,
}


def configure_build_identity(version: str, script_version: str) -> None:
    global VERSION, SCRIPT_VERSION, VERSION_TAG, BACKUP_TAG, AUTHORITATIVE_FILES
    normalized_version = str(version or "").strip()
    normalized_script_version = str(script_version or "").strip()
    VERSION = normalized_version
    SCRIPT_VERSION = normalized_script_version
    VERSION_TAG = f"v{VERSION}"
    BACKUP_TAG = f"v{VERSION.replace('.', '')}"
    AUTHORITATIVE_FILES = [
        SCRIPT_SOURCE_NAME,
        SCRIPT_OUTPUT_NAME,
        "build.py",
        "metadata.json",
        "package.json",
        "package-lock.json",
        "v07_CHECKLIST.MD",
    ]


def compose_split_source(base_dir: Path, names: list[str], *, comment_prefix: str, preserve_first_file: bool = False) -> str:
    parts: list[str] = []
    for index, name in enumerate(names):
        path = base_dir / name
        text = read_text(path).rstrip("\n")
        if preserve_first_file and index == 0:
            parts.append(text + "\n")
            continue
        parts.append(f"{comment_prefix} BEGIN {path.relative_to(ROOT).as_posix()}\n{text}\n{comment_prefix} END {path.relative_to(ROOT).as_posix()}\n")
    return "".join(parts)


def compose_control_source() -> str:
    return compose_split_source(CONTROL_SOURCE_DIR, CONTROL_SOURCE_ORDER, comment_prefix="#", preserve_first_file=True)


def compose_web_js_source() -> str:
    return compose_split_source(WEB_SOURCE_DIR, WEB_JS_SOURCE_ORDER, comment_prefix="//")


def sync_generated_root_sources(
    *,
    control_source: str,
    updater_text: str,
    html_text: str,
    css_text: str,
    js_text: str,
    script_text: str,
    bundle_html: str = "",
    min_css: str = "",
    min_js: str = "",
    ship_raw_html: str = "",
    ship_html: str = "",
) -> None:
    write_text(CONTROL_OUTPUT_PATH, control_source)
    write_text(UPDATER_OUTPUT_PATH, updater_text)
    write_text(WEB_HTML_OUTPUT_PATH, html_text)
    write_text(WEB_CSS_OUTPUT_PATH, css_text)
    write_text(WEB_JS_OUTPUT_PATH, js_text)
    if bundle_html:
        write_text(WEB_BUNDLE_HTML_OUTPUT_PATH, bundle_html)
    if min_css:
        write_text(WEB_MIN_CSS_OUTPUT_PATH, min_css)
    if min_js:
        write_text(WEB_MIN_JS_OUTPUT_PATH, min_js)
    if ship_raw_html:
        write_text(WEB_SHIP_RAW_HTML_OUTPUT_PATH, ship_raw_html)
    if ship_html:
        write_text(WEB_SHIP_HTML_OUTPUT_PATH, ship_html)
    write_text(SCRIPT_OUTPUT_PATH, script_text)


def load_build_metadata_inputs() -> dict[str, str]:
    raw_text = read_text(METADATA_FILE)
    payload = json.loads(raw_text)
    version = str(payload.get("version") or "").strip()
    release_date = str(payload.get("release_date") or "").strip()
    if not version or not release_date:
        raise ValueError("metadata.json must include non-empty version and release_date values")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date):
        raise ValueError("metadata.json release_date must use YYYY-MM-DD format")
    script_version = f"{release_date}.v{version}"
    return {
        "version": version,
        "release_date": release_date,
        "script_version": script_version,
        "change_log_latest": str(payload.get("change_log_latest") or "").strip(),
        "change_log_release": str(payload.get("change_log_release") or "").strip(),
        "change_log_icons": json.dumps(payload.get("change_log_icons") or {}, ensure_ascii=False, separators=(",", ":")),
        "club3090_version": json.dumps(payload.get("club3090_version") or {}, ensure_ascii=False, separators=(",", ":")),
        "hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "mtime": METADATA_FILE.stat().st_mtime,
    }


def expected_upstream_runtime_commit() -> str:
    try:
        payload = json.loads(read_text(METADATA_FILE))
    except Exception:
        return ""
    compat = payload.get("club3090_version") or {}
    if not isinstance(compat, dict):
        return ""
    commit = str(compat.get("commit") or "").strip()
    return commit if re.fullmatch(r"[0-9a-fA-F]{7,40}", commit) else ""


def ensure_upstream_runtime_checkout() -> Path:
    target = UPSTREAM_RUNTIME_DIR
    commit = expected_upstream_runtime_commit()
    if not target.exists():
        result = subprocess.run(
            ["git", "clone", UPSTREAM_RUNTIME_REPO_URL, str(target)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=600,
        )
        if result.returncode != 0:
            detail = (result.stdout or "git clone failed").strip()[-2000:]
            raise RuntimeError(f"Could not clone upstream club-3090 checkout from {UPSTREAM_RUNTIME_REPO_URL}: {detail}")
    if not (target / ".git").exists():
        raise RuntimeError(f"{target.relative_to(ROOT)} exists but is not a Git checkout")
    if commit:
        current = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        current_head = str(current.stdout or "").strip()
        if current.returncode != 0:
            detail = (current.stdout or "git rev-parse failed").strip()[-1200:]
            raise RuntimeError(f"Could not inspect upstream club-3090 checkout: {detail}")
        if not current_head.lower().startswith(commit.lower()):
            fetch = subprocess.run(
                ["git", "-C", str(target), "fetch", "--tags", "origin"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=600,
            )
            if fetch.returncode != 0:
                detail = (fetch.stdout or "git fetch failed").strip()[-2000:]
                raise RuntimeError(f"Could not fetch upstream club-3090 commit {commit}: {detail}")
            checkout = subprocess.run(
                ["git", "-C", str(target), "checkout", "--detach", commit],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=120,
            )
            if checkout.returncode != 0:
                detail = (checkout.stdout or "git checkout failed").strip()[-2000:]
                raise RuntimeError(f"Could not check out upstream club-3090 commit {commit}: {detail}")
    return target


def bump_version_suffix(suffix: str) -> str:
    value = str(suffix or "").strip().lower()
    if not value:
        return "a"
    carry = 1
    chars = list(value)
    for index in range(len(chars) - 1, -1, -1):
        if carry <= 0:
            break
        current = ord(chars[index]) - ord("a") + carry
        chars[index] = chr(ord("a") + (current % 26))
        carry = 1 if current >= 26 else 0
    if carry:
        chars.insert(0, "a")
    return "".join(chars)


def bump_patch_version(version: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)([a-z]*)", str(version or "").strip())
    if not match:
        raise ValueError(f"metadata.json version must use major.minor.patch with an optional letter suffix, got {version!r}")
    major, minor, patch = (int(part) for part in match.groups()[:3])
    return f"{major}.{minor}.{patch + 1}"


def bump_iterative_version(version: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)([a-z]*)", str(version or "").strip())
    if not match:
        raise ValueError(f"metadata.json version must use major.minor.patch with an optional letter suffix, got {version!r}")
    major, minor, patch = (int(part) for part in match.groups()[:3])
    suffix = match.group(4) or ""
    return f"{major}.{minor}.{patch}{bump_version_suffix(suffix)}"


def base_release_version(version: str) -> str:
    match = re.fullmatch(r"(\d+\.\d+\.\d+)[a-z]*", str(version or "").strip())
    return match.group(1) if match else str(version or "").strip()


def split_release_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_version = ""
    current_lines: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if re.fullmatch(r"v\d+\.\d+\.\d+[a-z]*", stripped):
            if current_version or current_lines:
                sections.append((current_version, "\n".join(current_lines).strip()))
            current_version = stripped
            current_lines = []
            continue
        current_lines.append(line)
    if current_version or current_lines:
        sections.append((current_version, "\n".join(current_lines).strip()))
    return [(version, body) for version, body in sections if version or body]


def normalize_release_change_entries(changes: list[str]) -> list[str]:
    entries: list[str] = []
    for raw in changes or []:
        text = sanitize_metadata_text(raw)
        if not text:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            entries.append(line if line.startswith("• ") else f"• {line}")
    if not entries:
        raise ValueError("At least one non-empty release change entry is required.")
    return entries


def dedupe_release_change_entries(entries: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in entries or []:
        text = sanitize_metadata_text(raw)
        if not text:
            continue
        key = re.sub(r"\s+", " ", text.strip())
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def dedupe_release_change_text(text: str) -> str:
    lines = sanitize_metadata_text(text).splitlines()
    entries: list[str] = []
    passthrough: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("• "):
            entries.append(stripped)
        elif stripped:
            passthrough.append(stripped)
    deduped_entries = dedupe_release_change_entries(entries)
    return "\n".join([*passthrough, *deduped_entries]).strip()


def update_metadata_for_build(
    changes: list[str],
    *,
    iterative: bool = False,
    release_date: str | None = None,
    target_version: str | None = None,
) -> tuple[dict[str, str], str]:
    raw_text = read_text(METADATA_FILE)
    payload = json.loads(raw_text)
    current_version = str(payload.get("version") or "").strip()
    current_latest = dedupe_release_change_text(payload.get("change_log_latest") or "")
    current_release = sanitize_metadata_text(payload.get("change_log_release") or "")
    requested_version = str(target_version or "").strip()
    if requested_version:
        if iterative:
            raise ValueError("--version cannot be combined with --iterative")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-z]*)?", requested_version):
            raise ValueError("target version must use major.minor.patch with an optional letter suffix")
        next_version = requested_version
    else:
        next_version = bump_iterative_version(current_version) if iterative else bump_patch_version(current_version)
    current_base_version = base_release_version(current_version)
    next_base_version = base_release_version(next_version)
    next_release_date = str(release_date or date.today().isoformat()).strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", next_release_date):
        raise ValueError("release_date must use YYYY-MM-DD format")
    normalized_change_entries = normalize_release_change_entries(changes)
    icon_issues = validate_changelog_icons(
        "\n".join(normalized_change_entries),
        payload.get("change_log_icons") or {},
        "--change",
    )
    if icon_issues:
        raise ValueError("; ".join(icon_issues))
    change_entries = dedupe_release_change_entries(normalized_change_entries)
    release_sections = split_release_sections(current_release)
    carried_latest_entries = [current_latest] if current_latest and current_base_version == next_base_version else []
    remaining_release_sections: list[tuple[str, str]] = []
    for section_version, section_body in release_sections:
        section_base = base_release_version(section_version.lstrip("v"))
        if section_base == next_base_version:
            if section_body:
                carried_latest_entries.append(dedupe_release_change_text(section_body))
            continue
        remaining_release_sections.append((section_version, section_body))
    next_latest = dedupe_release_change_text("\n".join(
        part
        for part in [*carried_latest_entries, "\n".join(change_entries)]
        if str(part or "").strip()
    ))
    release_sections: list[str] = []
    if current_latest and current_base_version != next_base_version:
        release_sections.append(f"v{base_release_version(current_version)}\n\n{current_latest}")
    release_sections.extend(
        f"{version}\n\n{body}" if body else version
        for version, body in remaining_release_sections
    )
    payload["version"] = next_version
    payload["release_date"] = next_release_date
    payload["change_log_latest"] = next_latest
    payload["change_log_release"] = "\n\n".join(section for section in release_sections if section.strip())
    write_text(METADATA_FILE, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    build_mode = "explicit version override" if requested_version else ("iterative letter suffix" if iterative else "patch version bump")
    entry_count = len(normalized_change_entries)
    detail = f"metadata.json updated automatically from v{current_version} to v{next_version} using {entry_count} supplied change entr{'y' if entry_count == 1 else 'ies'} via {build_mode}"
    return load_build_metadata_inputs(), detail


def load_previous_success_report() -> dict:
    try:
        payload = json.loads(read_text(BUILD_LAST_SUCCESS_PATH))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def validate_metadata_was_updated(metadata: dict[str, str]) -> list[str]:
    previous = load_previous_success_report()
    if not previous:
        return []
    previous_hash = str(previous.get("metadata_hash") or "").strip()
    previous_mtime = float(previous.get("metadata_mtime") or 0.0)
    previous_version = str(previous.get("version") or "").strip()
    previous_script_version = str(previous.get("script_version") or "").strip()
    previous_change_log_latest_hash = str(previous.get("change_log_latest_hash") or "").strip()
    previous_change_log_release_hash = str(previous.get("change_log_release_hash") or "").strip()
    current_hash = str(metadata.get("hash") or "").strip()
    current_mtime = float(metadata.get("mtime") or 0.0)
    current_version = str(metadata.get("version") or "").strip()
    current_script_version = str(metadata.get("script_version") or "").strip()
    current_change_log_latest = str(metadata.get("change_log_latest") or "").strip()
    current_change_log_release = str(metadata.get("change_log_release") or "").strip()
    current_change_log_latest_hash = hashlib.sha256(
        current_change_log_latest.encode("utf-8")
    ).hexdigest()
    current_change_log_release_hash = hashlib.sha256(
        current_change_log_release.encode("utf-8")
    ).hexdigest()
    issues: list[str] = []
    if previous_version and current_version and current_version == previous_version:
        issues.append(
            f"version was not bumped since the last successful build (still {current_version})"
        )
    if (
        previous_script_version
        and current_script_version
        and current_script_version == previous_script_version
    ):
        issues.append(
            f"script_version was not bumped since the last successful build (still {current_script_version})"
        )
    if previous_hash and current_hash == previous_hash:
        issues.append("metadata.json has not changed since the last successful build")
    if previous_mtime and current_mtime and current_mtime <= previous_mtime:
        issues.append("metadata.json modification time is not newer than the last successful build")
    if not current_change_log_latest:
        issues.append("change_log_latest is empty; write this release's notes before building")
    if previous_change_log_latest_hash and current_change_log_latest_hash == previous_change_log_latest_hash:
        issues.append("change_log_latest was not updated since the last successful build")
    if previous_version and current_version and current_version != previous_version:
        if not current_change_log_release:
            issues.append("change_log_release is empty; preserve prior release notes before building")
        elif (
            previous_change_log_release_hash
            and current_change_log_release_hash == previous_change_log_release_hash
        ):
            issues.append("change_log_release was not updated after the version bump")
    return issues


@dataclass
class BuildReport:
    version: str
    script_version: str
    metadata_hash: str = ""
    metadata_mtime: float = 0.0
    change_log_latest_hash: str = ""
    change_log_release_hash: str = ""
    warnings: list[str] = field(default_factory=list)
    smoke_tests: list[dict[str, str]] = field(default_factory=list)
    removed_root_artifacts: list[str] = field(default_factory=list)

    def add_test(self, name: str, status: str, detail: str = "") -> None:
        self.smoke_tests.append({"name": name, "status": status, "detail": detail})

    def warn(self, detail: str) -> None:
        if detail not in self.warnings:
            self.warnings.append(detail)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def parse_script_multiline_constant(script_text: str, name: str) -> str:
    match = re.search(
        rf"{re.escape(name)}=\$\(cat <<'EOF_[A-Z0-9_]+'\n(.*?)\nEOF_[A-Z0-9_]+\n\)",
        script_text,
        flags=re.S,
    )
    return match.group(1).strip() if match else ""


def parse_script_singleline_constant(script_text: str, name: str) -> str:
    match = re.search(rf'^{re.escape(name)}="([^"]*)"$', script_text, flags=re.M)
    if match:
        return match.group(1).strip()
    match = re.search(rf"^{re.escape(name)}='([^']*)'$", script_text, flags=re.M)
    return match.group(1).strip() if match else ""


def bash_single_quote(value: str) -> str:
    return "'" + str(value or "").replace("'", "'\"'\"'") + "'"


CHANGELOG_ICON_SEQUENCE_RE = r"(?:🟢|🐞|🔴|🔒|⚡|🖥️|🛠️|🧪|🔄|📝|🧰|🧩|⚙️)"


def sanitize_metadata_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"(?:\|\||\\n)\s*•\s*", "\n• ", text)
    text = re.sub(rf"(?:\|\||\\n)\s*(?={CHANGELOG_ICON_SEQUENCE_RE})", "\n• ", text)
    text = re.sub(rf"\n\s*(?={CHANGELOG_ICON_SEQUENCE_RE})", "\n• ", text)
    return text.strip()


def inject_script_metadata(
    script_source: str,
    *,
    script_version: str,
    change_log_latest: str,
    change_log_icons_json: str,
    club3090_version_json: str,
) -> str:
    updated, count = re.subn(
        r'^SCRIPT_VERSION="[^"]*"$',
        f'SCRIPT_VERSION="{script_version}"',
        script_source,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise ValueError("Could not inject SCRIPT_VERSION into base.sh")
    return updated


def validate_changelog_icons(change_log_text: str, icons: dict[str, str], field_name: str) -> list[str]:
    issues: list[str] = []
    text = str(change_log_text or "").strip()
    if not text or text == "No major changes since last release":
        return issues
    allowed_icons = {str(value).strip() for value in (icons or {}).values() if str(value).strip()}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("• "):
            body = stripped[2:].strip()
        else:
            continue
        if not body:
            continue
        icon = body.split(" ", 1)[0].strip()
        if icon not in allowed_icons:
            issues.append(f"{field_name} contains a bullet with icon {icon!r} that is not declared in CHANGE_LOG_ICONS")
    return issues


def validate_script_metadata(
    script_source: str,
    *,
    expected_version: str,
    expected_script_version: str,
    expected_change_log_latest: str,
    expected_change_log_icons: str,
    expected_club3090_version: str,
) -> list[str]:
    issues: list[str] = []
    actual_version = parse_script_singleline_constant(script_source, "SCRIPT_VERSION")
    if VERSION != expected_version:
        issues.append(f"build.py VERSION is {VERSION!r}, expected {expected_version!r}")
    if SCRIPT_VERSION != expected_script_version:
        issues.append(f"build.py SCRIPT_VERSION is {SCRIPT_VERSION!r}, expected {expected_script_version!r}")
    if actual_version != expected_script_version:
        issues.append("base.sh SCRIPT_VERSION does not match the required --script-version value")
    for name in ("CHANGE_LOG_LATEST", "CHANGE_LOG_RELEASE", "CHANGE_LOG_ICONS", "CLUB_3090_VERSION"):
        if re.search(rf"(?m)^{re.escape(name)}=", script_source):
            issues.append(f"base.sh must not embed {name}; release metadata must come from GitHub metadata.json")
    return issues


def flush_build_report(report: BuildReport, log_message: str = "") -> None:
    write_text(BUILD_REPORT_PATH, report.to_json() + "\n")
    if log_message:
        timestamp = date.today().isoformat()
        with BUILD_LOG_PATH.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"[{timestamp}] {log_message.rstrip()}\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def normalize_code_syntax_alias(value: str) -> str:
    return re.sub(r"[^\w#+.-]+", "", str(value or "").strip().lower())


def parse_highlight_supported_languages(markdown_text: str) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    for line in str(markdown_text or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        columns = [part.strip() for part in stripped.strip("|").split("|")]
        if len(columns) < 3 or columns[0] in {"Language", ":-----------------------"}:
            continue
        language_name = str(columns[0] or "").strip()
        if not language_name:
            continue
        aliases = [
            normalize_code_syntax_alias(alias)
            for alias in re.split(r"\s*,\s*", str(columns[1] or "").strip())
            if normalize_code_syntax_alias(alias)
        ]
        rows.append((language_name, aliases))
    return rows


def fallback_highlight_supported_languages() -> list[tuple[str, list[str]]]:
    rows = """
1C Enterprise|1c
4D|4d
ABNF|abnf
Access logs|accesslog
Ada|ada
AngelScript|angelscript,asc
Apache|apache,apacheconf
AppleScript|applescript,osascript
Arcade|arcade
Arduino|arduino,ino
ARM Assembly|armasm,arm
AsciiDoc|asciidoc,adoc
AspectJ|aspectj
AutoHotkey|autohotkey,ahk
AutoIt|autoit
AVR Assembly|avrasm
Awk|awk,mawk,nawk,gawk
Bash|bash,sh,zsh,shell
Basic|basic
BNF|bnf
Brainfuck|brainfuck,bf
C|c,h
C#|csharp,cs
C++|cpp,c,cc,c++,h,hpp,hxx
C/AL|cal
Cache Object Script|cos,cls
CMake|cmake,cmake.in
Coq|coq
CSP|csp
CSS|css
D|d
Dart|dart
Delphi|delphi,dpr,dfm,pas,pascal
Diff|diff,patch
Django|django,jinja
DNS Zone|dns,zone,bind
Dockerfile|dockerfile,docker
DOS|dos,bat,cmd
DSConfig|dsconfig
DTS|dts
Dust|dust,dst
EBNF|ebnf
Elixir|elixir,ex,exs
Elm|elm
ERB|erb
Erlang|erlang,erl
Excel|excel,xls,xlsx
FIX|fix
Flix|flix
Fortran|fortran,f90,f95
F#|fsharp,fs,fsx
G-Code|gcode,nc
Gams|gams,gms
GAUSS|gauss,gss
Gherkin|gherkin,feature
GLSL|glsl,vert,frag
GML|gml
Go|go,golang
Golo|golo
Gradle|gradle
GraphQL|graphql,gql
Groovy|groovy
HTML/XML|xml,html,xhtml,rss,atom,xjb,xsd,xsl,plist,svg
HTTP|http,https
Haml|haml
Handlebars|handlebars,hbs,html.hbs,html.handlebars
Haskell|haskell,hs
Haxe|haxe,hx
Hy|hy,hylang
Ini|ini,toml,properties,conf,cfg,dosini,env,dotenv
Inform7|inform7,i7
IRPF90|irpf90
JSON|json,jsonc,json5
Java|java,jsp
JavaScript|javascript,js,jsx,mjs,cjs
Julia|julia,jl
Kotlin|kotlin,kt,kts
LaTeX|latex,tex
Leaf|leaf
Less|less
Lisp|lisp,cl,el,clojure,clj,edn,scheme,scm,racket
LiveCode Server|livecodeserver
LiveScript|livescript,ls
LLVM IR|llvm
Lua|lua
Makefile|makefile,mk,mak
Markdown|markdown,md,mkdown,mkd
Mathematica|mathematica,mma,wl
Matlab|matlab
Maxima|maxima
MEL|mel
Mercury|mercury
MIPS Assembly|mipsasm,mips
Mizar|mizar
Mojolicious|mojolicious
Monkey|monkey
Moonscript|moonscript,moon
N1QL|n1ql
NestedText|nestedtext,nt
Nginx|nginx,nginxconf
Nim|nim
Nix|nix
NSIS|nsis
Objective-C|objectivec,obj-c,objc,mm
OCaml|ocaml,ml
OpenSCAD|openscad,scad
Oxygene|oxygene
Parser3|parser3
Perl|perl,pl,pm
PF|pf,pf.conf
PHP|php,php3,php4,php5,php6,php7,php8,php-template
Pony|pony
PowerShell|powershell,ps,ps1,pwsh
Processing|processing
Profile|profile
Prolog|prolog
Protocol Buffers|protobuf,proto
Puppet|puppet,pp
PureBASIC|purebasic,pb,pbi
Python|python,py,gyp,ipython
Q|q,k,kdb
QML|qml
R|r
ReasonML|reasonml,re
RenderMan RIB|rib
RenderMan RSL|rsl
Roboconf|roboconf,graph,instances
RouterOS|routeros,mikrotik
Ruby|ruby,rb,gemspec,podspec,thor,irb
Rust|rust,rs
SAS|sas
Scala|scala
Scheme|scheme,scm
Scilab|scilab,sci
SCSS|scss
Shell Session|shellsession,console
Smali|smali
Smalltalk|smalltalk,st
SML|sml,ml
SQF|sqf
SQL|sql,postgres,postgresql,pgsql,mysql,sqlite,plsql
Stan|stan,stanfuncs
Stata|stata
STEP Part 21|step,p21,step21
Stylus|stylus,styl
SubUnit|subunit
Swift|swift
Tagger Script|taggerscript
TAP|tap
Tcl|tcl,tk
Thrift|thrift
TP|tp
Twig|twig,craftcms
TypeScript|typescript,ts,tsx,mts,cts
VB.NET|vbnet,vb
VBScript|vbscript,vbs
VHDL|vhdl
Vim Script|vim
WebAssembly|wasm
Wren|wren
X86 Assembly|x86asm,asm,nasm
XL|xl,tao
XQuery|xquery,xq,xqm,xqy
YAML|yaml,yml
Zephir|zephir,zep
""".strip()
    parsed: list[tuple[str, list[str]]] = []
    for raw in rows.splitlines():
        name, _, aliases_text = raw.partition("|")
        aliases = [
            normalize_code_syntax_alias(alias)
            for alias in aliases_text.split(",")
            if normalize_code_syntax_alias(alias)
        ]
        parsed.append((name.strip(), aliases))
    return parsed


def guess_code_syntax_family(language_name: str, aliases: list[str], configured_aliases: dict[str, str]) -> str:
    candidates = [normalize_code_syntax_alias(language_name), *[normalize_code_syntax_alias(alias) for alias in aliases]]
    for candidate in candidates:
        if candidate and candidate in configured_aliases:
            return str(configured_aliases[candidate] or "clike")
    joined = " ".join(candidate for candidate in candidates if candidate)
    if any(token in joined for token in ("diff", "patch")):
        return "diff"
    if any(token in joined for token in ("graphql", "gql")):
        return "graphql"
    if any(token in joined for token in ("powershell", "pwsh", "ps1")):
        return "powershell"
    if any(token in joined for token in ("typescript", "tsx", "dts", "mts", "cts")):
        return "typescript"
    if any(token in joined for token in ("javascript", "jsx", "mjs", "cjs", "ecmascript", "node")):
        return "javascript"
    if any(token in joined for token in ("rust",)):
        return "rust"
    if any(token in joined for token in ("golang",)) or " go " in f" {joined} ":
        return "go"
    if any(token in joined for token in ("java", "gradle", "jar")):
        return "java"
    if any(token in joined for token in ("csharp", "dotnet")) or " cs " in f" {joined} ":
        return "csharp"
    if any(token in joined for token in ("kotlin", "kts")):
        return "kotlin"
    if any(token in joined for token in ("swift",)):
        return "swift"
    if any(token in joined for token in ("php", "phtml")):
        return "php"
    if any(token in joined for token in ("ruby", "gemspec")) or " rb " in f" {joined} ":
        return "ruby"
    if any(token in joined for token in ("perl",)) or " pl " in f" {joined} " or " pm " in f" {joined} ":
        return "perl"
    if any(token in joined for token in ("lua",)):
        return "lua"
    if any(token in joined for token in ("rscript",)) or joined in {"r"}:
        return "r"
    if any(token in joined for token in ("html", "xml", "svg", "xhtml", "rss", "atom", "handlebars", "twig", "django", "jinja", "mdx", "astro", "vue", "svelte")):
        return "markup"
    if any(token in joined for token in ("json", "yaml", "toml", "ini", "dotenv", "env", "config", "conf", "properties", "nginx", "apache", "dns", "zone", "codeowners", "robots", "nestedtext")):
        return "data"
    if any(token in joined for token in ("css", "scss", "sass", "less", "stylus", "styl")):
        return "styles"
    if any(token in joined for token in ("sql", "plsql", "postgres", "pgsql", "mysql", "sqlite", "db2", "n1ql")):
        return "sql"
    if any(token in joined for token in ("shell", "bash", "zsh", "fish", "dos", "cmd", "bat", "docker", "makefile", "cmake", "awk", "curl")):
        return "shell"
    if any(token in joined for token in ("vb", "basic", "pascal", "delphi", "qbasic", "freebasic")):
        return "basic"
    if any(token in joined for token in ("lisp", "clojure", "scheme", "racket", "elisp", "hy")):
        return "lisp"
    if any(token in joined for token in ("python", "julia")):
        return "python"
    return "clike"


def load_embedded_code_syntax_json() -> str:
    base_config = json.loads(read_text(CODE_SYNTAX_PATH))
    aliases = {
        normalize_code_syntax_alias(key): str(value or "").strip()
        for key, value in dict(base_config.get("aliases") or {}).items()
        if normalize_code_syntax_alias(key) and str(value or "").strip()
    }
    if HIGHLIGHT_SUPPORTED_LANGUAGES_PATH.exists():
        supported_rows = parse_highlight_supported_languages(read_text(HIGHLIGHT_SUPPORTED_LANGUAGES_PATH))
    else:
        supported_rows = fallback_highlight_supported_languages()
    for language_name, language_aliases in supported_rows:
        family = guess_code_syntax_family(language_name, language_aliases, aliases)
        canonical = normalize_code_syntax_alias(language_name)
        if canonical and canonical not in aliases:
            aliases[canonical] = family
        for alias in language_aliases:
            if alias and alias not in aliases:
                aliases[alias] = family
    base_config["aliases"] = dict(sorted(aliases.items()))
    base_config["language_alias_count"] = len(base_config["aliases"])
    if base_config["language_alias_count"] < 300:
        raise ValueError(
            f"Embedded code_syntax coverage is too small ({base_config['language_alias_count']} aliases); expected at least 300"
        )
    return json.dumps(base_config, ensure_ascii=False, indent=2)


def compress_code_syntax_json_to_gzip_base64(code_syntax_json: str) -> str:
    return compress_text_to_gzip_base64(code_syntax_json)


def compress_ai_studio_extensions_payload_to_gzip_base64() -> str:
    root = EXTENSIONS_SOURCE_DIR / "comfyui-club3090-preview"
    payload: dict[str, str] = {}
    if root.is_dir():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            rel = path.relative_to(EXTENSIONS_SOURCE_DIR).as_posix()
            if ".." in rel.split("/"):
                raise ValueError(f"Invalid AI Studio extension path: {rel}")
            payload[rel] = read_text(path)
    else:
        payload = {
            "comfyui-club3090-preview/__init__.py": (
                'WEB_DIRECTORY = "./js"\n'
                "NODE_CLASS_MAPPINGS = {}\n"
                "NODE_DISPLAY_NAME_MAPPINGS = {}\n"
            ),
            "comfyui-club3090-preview/js/club3090-preview.js": (
                "import { app } from '../../../scripts/app.js';\n"
                "app.registerExtension({ name: 'club3090.workflow_preview' });\n"
            ),
        }
    required = {
        "comfyui-club3090-preview/__init__.py",
        "comfyui-club3090-preview/js/club3090-preview.js",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"AI Studio extension payload missing required file(s): {', '.join(missing)}")
    return compress_text_to_gzip_base64(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def compress_html_to_gzip_base64(html_text: str) -> str:
    return compress_text_to_gzip_base64(html_text)


def compress_text_to_gzip_base64(text: str) -> str:
    compressed = gzip.compress(str(text or "").encode("utf-8"), compresslevel=9)
    return base64.b64encode(compressed).decode("ascii")


def decompress_gzip_base64_text(payload: str) -> str:
    raw = gzip.decompress(base64.b64decode(str(payload or "").encode("ascii")))
    return raw.decode("utf-8")


def compress_gputemps_vendor_payload_to_gzip_base64() -> str:
    source = read_text(GPUTEMPS_SOURCE_PATH)
    header = read_text(NVML_HEADER_PATH)
    if "NVIDIA Management Library" not in header:
        raise ValueError("Vendored nvml.h does not look like the NVIDIA NVML header")
    if "nvmlDeviceGetTemperature" not in source:
        raise ValueError("Vendored gputemps.c does not look like the expected helper source")
    payload = json.dumps(
        {
            "gputemps.c": source,
            "nvml.h": header,
        },
        separators=(",", ":"),
    )
    return compress_text_to_gzip_base64(payload)


def compressed_python_writer_block(
    *,
    target_var: str,
    heredoc_name: str,
    payload_name: str,
    text: str,
) -> str:
    payload = compress_text_to_gzip_base64(text.rstrip("\n") + "\n")
    return (
        f"\"${{SUDO[@]}}\" \"${{PYTHON_BIN}}\" - \"${{{target_var}}}\" <<'{heredoc_name}'\n"
        "import base64\n"
        "import gzip\n"
        "import pathlib\n"
        "import sys\n"
        "\n"
        f"{payload_name} = \"{payload}\"\n"
        "path = pathlib.Path(sys.argv[1])\n"
        f"path.write_bytes(gzip.decompress(base64.b64decode({payload_name}.encode(\"ascii\"))))\n"
        f"{heredoc_name}\n"
    )


def inject_code_syntax_config(js_source: str, code_syntax_json: str) -> str:
    replacement = f"const CODE_SYNTAX_CONFIG = {code_syntax_json}; // injected by build.py from code_syntax.json"
    updated, count = re.subn(
        r"^const CODE_SYNTAX_CONFIG = null; // injected by build\.py from code_syntax\.json$",
        lambda _match: replacement,
        js_source,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise ValueError("Could not inject CODE_SYNTAX_CONFIG into web-ui.js")
    return updated


def inject_code_syntax_payload_into_control(control_source: str, code_syntax_gzip_base64: str) -> str:
    replacement = f'CODE_SYNTAX_CONFIG_GZIP_BASE64 = {json.dumps(str(code_syntax_gzip_base64 or ""))}\n'
    updated, count = re.subn(
        r'^CODE_SYNTAX_CONFIG_GZIP_BASE64 = ""\s+# Injected by build\.py for shipped outputs\.\n',
        lambda _: replacement,
        control_source,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise ValueError("Could not find the code syntax payload placeholder in control.py")
    return updated


def inject_ai_studio_extensions_payload_into_control(control_source: str, payload_gzip_base64: str) -> str:
    replacement = f'AI_STUDIO_EXTENSION_PAYLOAD_GZIP_BASE64 = {json.dumps(str(payload_gzip_base64 or ""))}\n'
    updated, count = re.subn(
        r'^AI_STUDIO_EXTENSION_PAYLOAD_GZIP_BASE64 = ""\s+# Injected by build\.py for shipped outputs\.\n',
        lambda _: replacement,
        control_source,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise ValueError("Could not find the AI Studio extension payload placeholder in control.py")
    return updated


def minify_css(css: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,>+~])\s*", r"\1", css)
    css = re.sub(r";}", "}", css)
    return css.strip()


def minify_html(html: str) -> str:
    parts: list[str] = []
    token_re = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>)", re.I | re.S)
    last = 0
    for match in token_re.finditer(html):
        chunk = html[last:match.start()]
        chunk = re.sub(r">\s+<", "><", chunk)
        chunk = re.sub(r"\s+", " ", chunk)
        parts.append(chunk.strip())
        parts.append(match.group(1).strip())
        last = match.end()
    tail = html[last:]
    tail = re.sub(r">\s+<", "><", tail)
    tail = re.sub(r"\s+", " ", tail)
    parts.append(tail.strip())
    return "".join(part for part in parts if part)


def vendor_js_bundle() -> str:
    return ""


def vendor_css_bundle() -> str:
    return ""


def compose_web_assets(css_source: str, js_source: str) -> tuple[str, str]:
    css = (vendor_css_bundle() + "\n" + css_source.lstrip()).strip() + "\n"
    js = (vendor_js_bundle() + "\n" + js_source.lstrip()).strip() + "\n"
    return css, js


def inject_assets_into_html(html_source: str, css: str, js: str) -> str:
    html_source, css_count = re.subn(r"<style>.*?</style>", lambda _: f"<style>{css}</style>", html_source, count=1, flags=re.S)
    if css_count != 1:
        raise ValueError("Expected exactly one <style> block in web-ui.html")
    html_source, js_count = re.subn(r"<script>.*?</script>", lambda _: f"<script>{js}</script>", html_source, count=1, flags=re.S)
    if js_count != 1:
        raise ValueError("Expected exactly one <script> block in web-ui.html")
    return html_source


def inject_html_payload_into_control(control_source: str, html_gzip_base64: str) -> str:
    replacement = f'HTML_GZIP_BASE64 = {json.dumps(str(html_gzip_base64 or ""))}\n'
    updated, count = re.subn(
        r'^HTML_GZIP_BASE64 = ""\s+# Injected by build\.py for shipped outputs\.\n',
        lambda _: replacement,
        control_source,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise ValueError("Could not find the HTML payload injection placeholder in control.py")
    return updated


def inject_gputemps_vendor_payload_into_script(script_source: str, payload_gzip_base64: str) -> str:
    replacement = f'GPUTEMPS_VENDOR_PAYLOAD_BASE64={json.dumps(str(payload_gzip_base64 or ""))}\n'
    updated, count = re.subn(
        r'^GPUTEMPS_VENDOR_PAYLOAD_BASE64=""\s+# Injected by build\.py for shipped outputs\.\n',
        lambda _: replacement,
        script_source,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise ValueError("Could not find the gputemps vendor payload placeholder in base.sh")
    return updated


def inject_control_into_script(script_source: str, control_text: str) -> str:
    updated, count = re.subn(r'^SCRIPT_VERSION="[^"]+"$', f'SCRIPT_VERSION="{SCRIPT_VERSION}"', script_source, count=1, flags=re.M)
    if count != 1:
        raise ValueError(f"Could not find SCRIPT_VERSION line in {SCRIPT_SOURCE_NAME}")
    start_marker = "\"${SUDO[@]}\" tee \"${CONTROL_PY}\" >/dev/null <<'PYCTRL'\n"
    end_marker = "\nPYCTRL\n"
    start = updated.find(start_marker)
    if start < 0:
        raise ValueError(f"Could not find embedded control start marker in {SCRIPT_SOURCE_NAME}")
    content_start = start + len(start_marker)
    end = updated.find(end_marker, content_start)
    if end < 0:
        raise ValueError(f"Could not find embedded control end marker in {SCRIPT_SOURCE_NAME}")
    unpacker = compressed_python_writer_block(
        target_var="CONTROL_PY",
        heredoc_name="PYCTRL",
        payload_name="CONTROL_PAYLOAD",
        text=control_text,
    )
    return updated[:start] + unpacker + updated[end + len(end_marker):]


def inject_updater_into_script(script_source: str, updater_text: str) -> str:
    start_marker = "\"${SUDO[@]}\" tee \"${UPDATER_PY}\" >/dev/null <<'PYUPDATER'\n"
    end_marker = "\nPYUPDATER\n"
    start = script_source.find(start_marker)
    if start < 0:
        raise ValueError(f"Could not find embedded updater start marker in {SCRIPT_SOURCE_NAME}")
    content_start = start + len(start_marker)
    end = script_source.find(end_marker, content_start)
    if end < 0:
        raise ValueError(f"Could not find embedded updater end marker in {SCRIPT_SOURCE_NAME}")
    unpacker = compressed_python_writer_block(
        target_var="UPDATER_PY",
        heredoc_name="PYUPDATER",
        payload_name="UPDATER_PAYLOAD",
        text=updater_text,
    )
    return script_source[:start] + unpacker + script_source[end + len(end_marker):]


def validate_flow_branches(script_text: str) -> list[str]:
    required = [
        'ACTION="install"',
        '--update',
        '--migrate',
        'if [[ "${ACTION}" == "update" || "${ACTION}" == "migrate" ]]',
        'if [[ "${ACTION}" == "migrate" ]]',
        'migrate_repo_checkout',
        'migrate_custom_presets_cli',
        'log_step "Writing embedded control backend to ${CONTROL_PY}"',
        'ufw status numbered',
        'systemctl is-active --quiet club3090-caddy.service',
        'CONTROL_HTTP_READY_TIMEOUT_SECONDS:-60',
        'wait_for_control_http "${CONTROL_ADMIN_BIND_PORT}" "${control_wait_seconds}"',
        'Caddy obtains and renews ts.net certificates directly from tailscaled.',
        'get_certificate tailscale',
        'emit_fallback_routes="false"',
        'Environment=XDG_DATA_HOME=${CONTROL_DIR}/caddy-data',
        'EXISTING_CONTROL_ADMIN_BIND_PORT',
        'club3090-cert-refresh.timer',
        'OnUnitActiveSec=1d',
        '--webroot-path "${ACME_WEBROOT}"',
        'temporary NAT-PMP TCP/80 lease opened',
        'ExecReload=$(command -v caddy) reload',
        'admin 127.0.0.1:2019',
        'default_sni %s',
    ]
    missing = [item for item in required if item not in script_text]
    if "admin off" in script_text:
        missing.append("Caddy reload support requires its loopback-only admin API")
    if "tailscale cert --cert-file" in script_text:
        missing.append("Tailscale HTTPS must use Caddy's auto-renewing certificate manager")
    return missing


def validate_installer_control_contract(script_text: str, control_text: str) -> list[str]:
    match = re.search(r'required = \{([^}]+)\}', script_text)
    if not match:
        return ["installer validator required-set not found"]
    required_names = {
        item.strip().strip('"').strip("'")
        for item in match.group(1).split(",")
        if item.strip()
    }
    control_funcs = set(re.findall(r"(?m)^def\s+([A-Za-z_]\w*)\s*\(", control_text))
    missing = sorted(name for name in required_names if name not in control_funcs)
    return [f"installer validator references missing control function '{name}'" for name in missing]


def extract_embedded_control(script_text: str) -> str:
    packed_match = re.search(
        r'"?\$\{SUDO\[@\]\}"?\s+"?\$\{PYTHON_BIN\}"?\s+-\s+"?\$\{CONTROL_PY\}"?\s+<<\'PYCTRL\'\n(.*?)\nPYCTRL\n',
        script_text,
        flags=re.S,
    )
    if packed_match:
        payload_match = re.search(
            r'CONTROL_PAYLOAD\s*=\s*(?:"""\n(.*?)\n"""|"([A-Za-z0-9+/=]+)")',
            packed_match.group(1),
            flags=re.S,
        )
        if not payload_match:
            raise ValueError("Compressed embedded control payload not found")
        return decompress_gzip_base64_text(payload_match.group(1) or payload_match.group(2)).rstrip("\n")
    marker = "\"${SUDO[@]}\" tee \"${CONTROL_PY}\" >/dev/null <<'PYCTRL'\n"
    end_marker = "\nPYCTRL\n"
    start = script_text.find(marker)
    if start < 0:
        raise ValueError("Embedded control start marker not found")
    content_start = start + len(marker)
    end = script_text.find(end_marker, content_start)
    if end < 0:
        raise ValueError("Embedded control end marker not found")
    return script_text[content_start:end]


def scan_duplicate_functions(path: Path, source: str) -> list[str]:
    counts: dict[str, int] = {}
    for name in re.findall(r"(?m)^function\s+([A-Za-z_]\w*)\s*\(", source):
        counts[name] = counts.get(name, 0) + 1
    for name in re.findall(r"(?m)^([A-Za-z_]\w*)\s*=\s*function\b", source):
        counts[name] = counts.get(name, 0) + 1
    return [f"{path.name}: duplicate top-level function symbol '{name}' ({count} definitions)" for name, count in sorted(counts.items()) if count > 1]


def run_command(args: list[str], cwd: Path, timeout_seconds: int = DEFAULT_TOOL_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "")
        return subprocess.CompletedProcess(
            args=args,
            returncode=124,
            stdout=stdout,
            stderr=(stderr + f"\nTimed out after {timeout_seconds}s").strip(),
        )


def minify_css_with_clean_css(css_text: str, cwd: Path) -> tuple[str, str]:
    source_path = cwd / "web-ui.cleancss.source.css"
    out_path = cwd / "web-ui.cleancss.min.css"
    cli_path = (ROOT / "node_modules" / "clean-css-cli" / "bin" / "cleancss").resolve()
    if not cli_path.exists():
        return minify_css(css_text), "internal CSS minifier fallback; clean-css-cli was not installed"
    write_text(source_path, css_text)
    result = run_command(["node", str(cli_path), "-O1", "-o", str(out_path), str(source_path)], cwd)
    try:
        source_path.unlink(missing_ok=True)
    except Exception:
        pass
    if result.returncode != 0:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        detail = (result.stderr or result.stdout or "clean-css minify failed").strip()
        raise RuntimeError(detail)
    minified = read_text(out_path)
    try:
        out_path.unlink(missing_ok=True)
    except Exception:
        pass
    return minified.strip(), "clean-css-cli"


def validate_js_with_node(js_text: str, cwd: Path, filename: str = "web-ui.check.js") -> tuple[bool, str]:
    temp_path = cwd / filename
    write_text(temp_path, js_text)
    result = run_command(["node", "--check", str(temp_path)], cwd)
    try:
        temp_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def minify_js_with_terser(js_text: str, cwd: Path) -> tuple[str, str]:
    source_path = cwd / "web-ui.terser.source.js"
    out_path = cwd / "web-ui.terser.min.js"
    runner_path = cwd / "web-ui.terser.runner.cjs"
    terser_entry = (ROOT / "node_modules" / "terser" / "dist" / "bundle.min.js").resolve()
    if not terser_entry.exists():
        return js_text.strip(), "unminified JavaScript fallback; terser was not installed"
    write_text(source_path, js_text)
    runner = """const fs = require('fs');
const terser = require(process.argv[4]);
(async () => {
  const input = fs.readFileSync(process.argv[2], 'utf8');
  const result = await terser.minify(input, {
    compress: true,
    mangle: true,
    ecma: 2020,
    format: { comments: false },
  });
  if (!result || typeof result.code !== 'string' || !result.code.trim()) {
    throw new Error(result && result.error ? String(result.error) : 'terser produced empty output');
  }
  fs.writeFileSync(process.argv[3], result.code, 'utf8');
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
"""
    write_text(runner_path, runner)
    result = run_command(["node", str(runner_path), str(source_path), str(out_path), str(terser_entry)], cwd)
    try:
        runner_path.unlink(missing_ok=True)
        source_path.unlink(missing_ok=True)
    except Exception:
        pass
    if result.returncode != 0:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        detail = (result.stderr or result.stdout or "terser minify failed").strip()
        raise RuntimeError(detail)
    minified = read_text(out_path)
    try:
        out_path.unlink(missing_ok=True)
    except Exception:
        pass
    return minified, "terser"
