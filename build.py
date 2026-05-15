#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import argparse
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VERSION = "0.6.30"
SCRIPT_VERSION = f"{date.today().isoformat()}.v{VERSION}"
VERSION_TAG = f"v{VERSION}"
BACKUP_TAG = f"v{VERSION.replace('.', '')}"
AUTHORITATIVE_FILES = [
    "install-club3090-server.sh",
    "control.py",
    "web-ui.html",
    "web-ui.css",
    "web-ui.js",
    "build.py",
    "package.json",
    "package-lock.json",
    f"CHECKLIST_v{VERSION.replace('.', '')}.md",
]
FIXTURES_DIR = ROOT / "test-fixtures"
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
BUILD_REPORT_PATH = ROOT / "build-report.json"
BUILD_LOG_PATH = ROOT / "build.log"
DEFAULT_TOOL_TIMEOUT_SECONDS = 45
TEST_HTML_PATH = ROOT / "web-ui.test.html"


@dataclass
class BuildReport:
    version: str
    script_version: str
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


def flush_build_report(report: BuildReport, log_message: str = "") -> None:
    write_text(BUILD_REPORT_PATH, report.to_json() + "\n")
    if log_message:
        timestamp = date.today().isoformat()
        with BUILD_LOG_PATH.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"[{timestamp}] {log_message.rstrip()}\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


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


def read_vendor_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Vendor asset not found: {path}")
    return read_text(path)


def wrap_commonjs_module(source: str, global_name: str) -> str:
    return (
        f"var {global_name}=(function(){{\n"
        "var module={exports:{}};\n"
        "var exports=module.exports;\n"
        f"{source.rstrip()}\n"
        f"return module.exports&&module.exports.default?module.exports.default:module.exports;\n"
        "})();\n"
    )


def vendor_js_bundle() -> str:
    return ""


def vendor_css_bundle() -> str:
    parts = [
        read_vendor_text(
            ROOT
            / "node_modules"
            / "highlight.js"
            / "styles"
            / "atom-one-dark-reasonable.min.css"
        ),
    ]
    return "\n".join(part.strip() for part in parts if part.strip()) + "\n"


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


def inject_html_into_control(control_source: str, shipped_html: str) -> str:
    replacement = f"HTML = {json.dumps(shipped_html, ensure_ascii=False)}\n"
    updated, count = re.subn(
        r'^HTML = ""\s+# Injected by build\.py for shipped outputs\.\n',
        lambda _: replacement,
        control_source,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise ValueError("Could not find the HTML injection placeholder in control.py")
    return updated


def inject_control_into_script(script_source: str, control_text: str) -> str:
    updated, count = re.subn(r'^SCRIPT_VERSION="[^"]+"$', f'SCRIPT_VERSION="{SCRIPT_VERSION}"', script_source, count=1, flags=re.M)
    if count != 1:
        raise ValueError("Could not find SCRIPT_VERSION line in install-club3090-server.sh")
    start_marker = "\"${SUDO[@]}\" tee \"${CONTROL_PY}\" >/dev/null <<'PYCTRL'\n"
    end_marker = "\nPYCTRL\n"
    start = updated.find(start_marker)
    if start < 0:
        raise ValueError("Could not find embedded control start marker in install-club3090-server.sh")
    content_start = start + len(start_marker)
    end = updated.find(end_marker, content_start)
    if end < 0:
        raise ValueError("Could not find embedded control end marker in install-club3090-server.sh")
    return updated[:content_start] + control_text.rstrip("\n") + end_marker + updated[end + len(end_marker):]


def validate_flow_branches(script_text: str) -> list[str]:
    required = [
        'ACTION="install"',
        '--update',
        '--migrate',
        'if [[ "${ACTION}" == "update" || "${ACTION}" == "migrate" ]]',
        'if [[ "${ACTION}" == "migrate" ]]',
        'migrate_repo_checkout',
        'log_step "Writing embedded control backend to ${CONTROL_PY}"',
    ]
    missing = [item for item in required if item not in script_text]
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
        raise RuntimeError("Local clean-css-cli install was not found at node_modules/clean-css-cli/bin/cleancss")
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
        raise RuntimeError("Local terser install was not found at node_modules/terser/dist/bundle.min.js")
    write_text(source_path, js_text)
    runner = """const fs = require('fs');
const terser = require(process.argv[4]);
(async () => {
  const input = fs.readFileSync(process.argv[2], 'utf8');
  const result = await terser.minify(input, {
    compress: true,
    mangle: false,
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


def ui_smoke_harness(js_text: str) -> str:
    payload = json.dumps(js_text, ensure_ascii=False)
    return f"""const vm = require("vm");
const code = {payload};
const elements = new Map();
function makeClassList() {{
  return {{
    add() {{}},
    remove() {{}},
    toggle() {{}},
    contains() {{ return false; }},
  }};
}}
function makeElement(id = "") {{
  return {{
    id,
    value: "",
    textContent: "",
    innerHTML: "",
    checked: true,
    disabled: false,
    scrollTop: 0,
    scrollHeight: 100,
    clientHeight: 100,
    width: 300,
    height: 150,
    clientWidth: 300,
    className: "",
    dataset: {{}},
    style: {{}},
    children: [],
    firstChild: null,
    lastChild: null,
    parentNode: null,
    classList: makeClassList(),
    appendChild(child) {{
      child.parentNode = this;
      this.children.push(child);
      this.firstChild = this.firstChild || child;
      this.lastChild = child;
      return child;
    }},
    insertBefore(child) {{
      child.parentNode = this;
      this.children.push(child);
      this.firstChild = this.firstChild || child;
      this.lastChild = child;
      return child;
    }},
    insertAdjacentElement(_pos, child) {{
      return this.appendChild(child);
    }},
    querySelector(selector) {{
      return getElement(selector);
    }},
    querySelectorAll() {{
      return [];
    }},
    addEventListener() {{}},
    removeEventListener() {{}},
    focus() {{}},
    select() {{}},
    setSelectionRange() {{}},
    setAttribute() {{}},
    removeAttribute() {{}},
    remove() {{}},
    getContext() {{
      return {{
        clearRect() {{}},
        fillText() {{}},
        beginPath() {{}},
        moveTo() {{}},
        lineTo() {{}},
        stroke() {{}},
        fillStyle: "",
        font: "",
        strokeStyle: "",
        lineWidth: 0,
      }};
    }},
  }};
}}
function getElement(id) {{
  const key = String(id || "");
  if (!elements.has(key)) elements.set(key, makeElement(key));
  return elements.get(key);
}}
const document = {{
  body: getElement("body"),
  createElement(tag) {{ return makeElement(tag); }},
  getElementById(id) {{ return getElement(id); }},
  querySelector(selector) {{ return getElement(selector); }},
  querySelectorAll() {{ return []; }},
  addEventListener() {{}},
  execCommand() {{ return true; }},
}};
const statusPayload = {{
  metrics: {{}},
  power: {{}},
  gpus: [],
  users: [],
  groups: [],
  server_config: {{}},
  instances: [],
  presets: {{ defaults: [], custom: [] }},
  ui_config: {{}},
  series: [],
  system: {{ cpu: {{ cores: [] }}, memory: null, disks: [], network: {{}}, info: {{}} }},
  models: [],
  variants: [],
  instance_runtime_metrics: {{}},
  running_runtimes: [],
  containers: [],
  active_modes: [],
  gpu_count: 0,
}};
const context = {{
  console,
  document,
  navigator: {{ clipboard: {{ writeText: async () => {{}} }} }},
  localStorage: {{ getItem() {{ return null; }}, setItem() {{}}, removeItem() {{}} }},
  EventSource: function EventSource(url) {{
    this.url = url;
    this.addEventListener = () => {{}};
    this.close = () => {{}};
  }},
  fetch: async (url) => {{
    if (String(url).startsWith("/admin/status")) {{
      return {{
        ok: true,
        status: 200,
        async json() {{ return statusPayload; }},
        async text() {{ return JSON.stringify(statusPayload); }},
      }};
    }}
    return {{
      ok: true,
      status: 200,
      async json() {{ return {{ ok: true, users: [], groups: [], server_config: {{}}, presets: {{ defaults: [], custom: [] }} }}; }},
      async text() {{ return "{{\\"ok\\":true}}"; }},
    }};
  }},
  setInterval() {{ return 1; }},
  clearInterval() {{}},
  setTimeout(fn) {{ if (typeof fn === "function") fn(); return 1; }},
  clearTimeout() {{}},
  alert() {{}},
  confirm() {{ return false; }},
  prompt() {{ return null; }},
  devicePixelRatio: 1,
  URLSearchParams,
  Date,
}};
context.window = {{
  document,
  navigator: context.navigator,
  localStorage: context.localStorage,
  fetch: context.fetch,
  setTimeout: context.setTimeout,
  clearTimeout: context.clearTimeout,
  setInterval: context.setInterval,
  clearInterval: context.clearInterval,
  addEventListener() {{}},
}};
let asyncFailure = null;
process.on("unhandledRejection", (error) => {{
  asyncFailure = error;
}});
process.on("uncaughtException", (error) => {{
  asyncFailure = error;
}});
(async () => {{
  vm.createContext(context);
  vm.runInContext(code, context, {{ filename: "web-ui.js" }});
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
  if (asyncFailure) throw asyncFailure;
  if (typeof context.tab !== "function") throw new Error("tab() was not initialized");
  if (typeof context.refreshStatus !== "function") throw new Error("refreshStatus() was not initialized");
  console.log("ui smoke ok");
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""


def test_html_bootstrap(fixtures: list[tuple[str, dict]]) -> str:
    fixture_map = {name: payload for name, payload in fixtures}
    fixture_json = json.dumps(fixture_map, ensure_ascii=False)
    markdown_showcase = """# Markdown Showcase

This seeded test-only conversation exercises the local parser surface an AI agent is likely to emit: **bold**, *italic*, ***bold italic***, __strong underscores__, _safe emphasis_, ~~deleted text~~, ==highlighted text==, `inline code`, <kbd>Ctrl</kbd> + <kbd>K</kbd>, and escaped punctuation like \\*literal stars\\*, \\[literal brackets\\], and \\$literal dollars\\$.

Mixed inline stress: before _safe emphasis_ after, before <kbd>Enter</kbd> after, `literal *stars*`, **bold with `code` inside**, and [inline link after emphasis](https://example.com/inline).

## Links, Emails, And Media

- External link with confirmation modal: [OpenAI](https://openai.com)
- Internal link without modal: [Status panel](/admin)
- Autolink: https://example.com/docs?query=club-3090.
- Email autolink: ops@example.com
- Broken image should become a static note: ![broken fixture image](https://example.invalid/missing-image.png)
- Reference-style link: [Club 3090 repo][club-repo]
- Collapsed reference link: [Docs][]
- Bare www link: www.example.com/path

[club-repo]: https://github.com/noonghunna/club-3090
[docs]: https://example.com/reference-docs

## Lists

1. Ordered parent
   - Nested unordered child
     - Deeper child
   1. Nested ordered child
2. Task list
   - [x] Completed item
   - [ ] Pending item with `code`
3. Definition-ish text
   Term
   : Definition text should remain readable even if rendered as paragraph continuation.

## Definition Lists

Another Term
: First definition
: Second definition with **strong text** and [a reference][club-repo].

## Blockquotes

> A quoted answer can contain **formatting**.
> - Nested quote list item
> - Another item with $E = mc^2$
> > Nested quote level two with [an internal link](/admin#chat)

## Tables

| Feature | Status | Notes |
|:--|:--:|--:|
| Links | pass | modal |
| Tables | pass | aligned |
| Math | pass | 123 |
| Escapes | pass | \\| pipe |
| Inline | **bold** | `code` and [link](/admin) |
| Math | $x_i^2$ | $\\frac{1}{2}$ |

## Math

Inline math should stay readable: $2 + 2 = 4$, $E = mc^2$, $x_i^2$, $\\frac{a}{b}$, and $\\sqrt{x^2 + y^2}$.
More math: $\\alpha + \\beta \\leq \\gamma$, $\\lim_{x\\to 0} \\frac{\\sin x}{x} = 1$, and $a_{n+1} = a_n + d$.

$$
\\int_0^1 x^2 dx = \\frac{1}{3}
$$

$$
\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}
$$

$$
\\prod_{k=1}^{n} k = n!
$$

## Code

```python
def greet(name: str) -> str:
    return f"hello {name}"

print(greet("club-3090"))
```

~~~bash
set -euo pipefail
printf '%s\\n' "escaped code fences work"
~~~

    indented_code = {"kept": True}

## HTML Safety

Raw tags like <script>alert("nope")</script> should be escaped, while supported Markdown continues below.

---

Final paragraph after a rule.
"""
    markdown_showcase_json = json.dumps(markdown_showcase, ensure_ascii=False).replace("</", "<\\/")
    preferred_fixture = next(
        (
            name
            for name, payload in fixtures
            if any(
                row and row.get("running")
                for row in (
                    payload.get("running_runtimes")
                    if isinstance(payload.get("running_runtimes"), list)
                    else payload.get("instances", [])
                )
            )
        ),
        fixtures[0][0] if fixtures else "empty",
    )
    default_payload = fixtures[0][1] if fixtures else {
        "vllm_service": "active",
        "control_service": "active",
        "console_service": "active",
        "metrics": {},
        "power": {},
        "gpus": [],
        "users": [],
        "groups": [],
        "server_config": {},
        "instances": [],
        "presets": {"defaults": [], "custom": []},
        "ui_config": {},
        "series": [],
        "system": {"cpu": {"cores": []}, "memory": None, "disks": [], "network": {}, "info": {}},
        "models": [],
        "variants": [],
        "instance_runtime_metrics": {},
        "running_runtimes": [],
        "containers": [],
        "active_modes": [],
        "gpu_count": 0,
    }
    default_json = json.dumps(default_payload, ensure_ascii=False)
    return f"""
(function () {{
  const FIXTURES = {fixture_json};
  const EMPTY_FIXTURE = {default_json};
  const DEFAULT_FIXTURE = {json.dumps(preferred_fixture, ensure_ascii=False)};
  const MARKDOWN_SHOWCASE = {markdown_showcase_json};
  const state = {{
    fixture: DEFAULT_FIXTURE,
    status: JSON.parse(JSON.stringify(FIXTURES[DEFAULT_FIXTURE] || EMPTY_FIXTURE)),
    latencyMs: 30,
  }};
  function clone(value) {{
    return JSON.parse(JSON.stringify(value));
  }}
  function fixtureNames() {{
    return Object.keys(FIXTURES).sort();
  }}
  function currentStatus() {{
    const status = clone(state.status || EMPTY_FIXTURE);
    const rows = Array.isArray(status.running_runtimes) && status.running_runtimes.length
      ? status.running_runtimes
      : Array.isArray(status.instances)
        ? status.instances.filter((row) => row && row.running)
        : [];
    const runtime = rows[0];
    if (runtime) {{
      runtime.display_name = runtime.display_name || 'Global Dual';
      runtime.mode = runtime.mode || 'vllm/dual-dflash';
      runtime.container = runtime.container || 'vllm-qwen36-27b-dual-dflash';
      runtime.model_id = runtime.model_id || 'vllm-qwen36-27b-dual-dflash';
      runtime.served_model_name = runtime.served_model_name || 'vllm-qwen36-27b-dual-dflash';
      runtime.gpu_indices = Array.isArray(runtime.gpu_indices) && runtime.gpu_indices.length ? runtime.gpu_indices : [0, 1];
      runtime.last_latency_s = runtime.last_latency_s ?? 0.009;
      runtime.last_ttft_s = runtime.last_ttft_s ?? 2.722;
      runtime.last_tokens_per_second = runtime.last_tokens_per_second ?? 32.2;
      runtime.max_tokens_per_second = runtime.max_tokens_per_second ?? 81.2;
      runtime.gpu_kv_cache_usage_pct = runtime.gpu_kv_cache_usage_pct ?? 6.2;
      runtime.ctx_size_tokens = runtime.ctx_size_tokens ?? 185000;
      runtime.speculative = runtime.speculative || {{}};
      runtime.speculative.drafted_tokens = runtime.speculative.drafted_tokens ?? 5;
      runtime.speculative.accept_rate_pct = runtime.speculative.accept_rate_pct ?? 62.6;
      runtime.speculative.accepted_tokens = runtime.speculative.accepted_tokens ?? 166;
      runtime.speculative.draft_tokens = runtime.speculative.draft_tokens ?? 265;
      runtime.speculative.mean_acceptance_length = runtime.speculative.mean_acceptance_length ?? 4.13;
      runtime.prompt_tps = runtime.prompt_tps ?? 5.7;
      runtime.generation_tps = runtime.generation_tps ?? 22;
      runtime.prefix_cache_hit_rate_pct = runtime.prefix_cache_hit_rate_pct ?? 0;
      runtime.last_input_tokens = runtime.last_input_tokens ?? 0;
      runtime.last_output_tokens = runtime.last_output_tokens ?? 0;
      runtime.last_total_tokens = runtime.last_total_tokens ?? 0;
      runtime.last_tool_calls = runtime.last_tool_calls ?? 0;
      runtime.last_status = runtime.last_status ?? 404;
      runtime.last_path = runtime.last_path ?? '';
      runtime.last_request_at = runtime.last_request_at || new Date().toISOString();
    }}
    return status;
  }}
  function setFixture(name) {{
    const nextName = String(name || "").trim();
    state.fixture = FIXTURES[nextName] ? nextName : DEFAULT_FIXTURE;
    state.status = clone(FIXTURES[state.fixture] || EMPTY_FIXTURE);
  }}
  function responseFrom(body, ok = true, status = 200) {{
    const payload = clone(body);
    return {{
      ok,
      status,
      async json() {{ return clone(payload); }},
      async text() {{ return JSON.stringify(payload); }},
    }};
  }}
  function buildStreamResponse(text, reasoning = '') {{
    const payload = [
      'event: status\\ndata: ' + JSON.stringify({{ message: 'Generating message...' }}) + '\\n\\n',
      reasoning
        ? 'event: reasoning\\ndata: ' + JSON.stringify({{ text: reasoning }}) + '\\n\\n'
        : '',
      'event: delta\\ndata: ' + JSON.stringify({{ text }}) + '\\n\\n',
      'event: done\\ndata: ' + JSON.stringify({{ message: '' }}) + '\\n\\n',
    ].join('');
    const payloadBytes = new Uint8Array(Array.from(payload, (char) => char.charCodeAt(0)));
    return {{
      ok: true,
      status: 200,
      body: {{
        getReader() {{
          let consumed = false;
          return {{
            async read() {{
              if (consumed) return {{ value: undefined, done: true }};
              consumed = true;
              return {{ value: payloadBytes, done: false }};
            }},
          }};
        }},
      }},
    }};
  }}
  function inferRuntime(status) {{
    const rows = Array.isArray(status.running_runtimes) && status.running_runtimes.length
      ? status.running_runtimes
      : Array.isArray(status.instances)
        ? status.instances.filter((row) => row && row.running)
        : [];
    return rows[0] || null;
  }}
  function mountLab() {{
    const panel = document.createElement('div');
    panel.id = 'club3090TestLab';
    panel.innerHTML = `
      <style>
        #club3090TestLab {{
          position: fixed;
          right: 14px;
          bottom: 14px;
          z-index: 9999;
          width: min(360px, calc(100vw - 24px));
          padding: 12px;
          border: 1px solid #29405a;
          border-radius: 14px;
          background: rgba(9, 15, 24, 0.96);
          box-shadow: 0 18px 50px rgba(0, 0, 0, 0.42);
          color: #e8eef7;
          font: 12px/1.4 system-ui, -apple-system, Segoe UI, Arial, sans-serif;
          backdrop-filter: blur(10px);
        }}
        #club3090TestLab .lab-title {{
          margin: 0 0 8px;
          font-size: 13px;
          font-weight: 800;
        }}
        #club3090TestLab .lab-grid {{
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
        }}
        #club3090TestLab label {{
          display: flex;
          flex-direction: column;
          gap: 4px;
          color: #9dafc3;
        }}
        #club3090TestLab select,
        #club3090TestLab button,
        #club3090TestLab textarea {{
          background: #081018;
          color: #eef4ff;
          border: 1px solid #2c3a4f;
          border-radius: 9px;
          padding: 8px;
          font: inherit;
        }}
        #club3090TestLab select {{
          appearance: none;
          -webkit-appearance: none;
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='m6 9 6 6 6-6' fill='none' stroke='%239dafc3' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
          background-position: calc(100% - 14px) 50%;
          background-repeat: no-repeat;
          background-size: 12px 12px;
          padding-right: 32px;
        }}
        #club3090TestLab textarea {{
          min-height: 84px;
          resize: vertical;
          grid-column: 1 / -1;
        }}
        #club3090TestLab .lab-actions {{
          display: flex;
          gap: 8px;
          margin-top: 8px;
        }}
        #club3090TestLab .lab-note {{
          margin-top: 8px;
          color: #9dafc3;
        }}
      </style>
      <div class="lab-title">Club-3090 Local UI Lab</div>
      <div class="lab-grid">
        <label>Fixture
          <select id="club3090FixtureSelect"></select>
        </label>
        <label>Latency (ms)
          <select id="club3090LatencySelect">
            <option value="0">0</option>
            <option value="30" selected>30</option>
            <option value="120">120</option>
            <option value="350">350</option>
          </select>
        </label>
        <label style="grid-column: 1 / -1;">Status Override (JSON)
          <textarea id="club3090FixtureEditor" spellcheck="false"></textarea>
        </label>
      </div>
      <div class="lab-actions">
        <button id="club3090FixtureApply" type="button">Apply JSON</button>
        <button id="club3090FixtureReset" type="button">Reset Fixture</button>
        <button id="club3090OpenChat" type="button">Open Chat</button>
      </div>
      <div class="lab-note">This file mocks the admin API locally so you can switch tabs, open modals, test chat UI, and spot layout regressions on Windows.</div>
    `;
    document.body.appendChild(panel);
    const fixtureSelect = panel.querySelector('#club3090FixtureSelect');
    const latencySelect = panel.querySelector('#club3090LatencySelect');
    const editor = panel.querySelector('#club3090FixtureEditor');
    const refreshEditor = () => {{
      editor.value = JSON.stringify(state.status, null, 2);
    }};
    fixtureSelect.innerHTML = fixtureNames()
      .map((name) => `<option value="${{name}}" ${{name === state.fixture ? 'selected' : ''}}>${{name}}</option>`)
      .join('');
    fixtureSelect.addEventListener('change', async () => {{
      setFixture(fixtureSelect.value);
      refreshEditor();
      if (typeof window.refreshStatus === 'function') await window.refreshStatus({{ force: true }});
    }});
    latencySelect.addEventListener('change', () => {{
      state.latencyMs = Math.max(0, Number(latencySelect.value || 0) || 0);
    }});
    panel.querySelector('#club3090FixtureApply').addEventListener('click', async () => {{
      try {{
        state.status = JSON.parse(editor.value || '{{}}');
        if (typeof window.refreshStatus === 'function') await window.refreshStatus({{ force: true }});
      }} catch (error) {{
        window.alert('Invalid JSON override: ' + String(error));
      }}
    }});
    panel.querySelector('#club3090FixtureReset').addEventListener('click', async () => {{
      setFixture(fixtureSelect.value);
      refreshEditor();
      if (typeof window.refreshStatus === 'function') await window.refreshStatus({{ force: true }});
    }});
    panel.querySelector('#club3090OpenChat').addEventListener('click', () => {{
      if (typeof window.openChatTab === 'function') window.openChatTab();
    }});
    refreshEditor();
  }}
  const originalFetch = window.fetch ? window.fetch.bind(window) : null;
  window.__club3090TestLab = {{
    get fixture() {{ return state.fixture; }},
    get status() {{ return currentStatus(); }},
    setFixture,
    refresh: async () => {{
      if (typeof window.refreshStatus === 'function') await window.refreshStatus({{ force: true }});
    }},
  }};
  window.fetch = async (url, options = {{}}) => {{
    const requestUrl = String(url || '');
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    await wait(state.latencyMs);
    if (requestUrl.startsWith('/admin/status')) {{
      return responseFrom(currentStatus());
    }}
    if (requestUrl === '/admin/chat-stream') {{
      const runtime = inferRuntime(state.status) || {{}};
      const runtimeLabel = runtime.display_name || runtime.id || runtime.instance_id || 'mock runtime';
      return buildStreamResponse(`Test HTML response from ${{runtimeLabel}}.`, 'Mock reasoning stream.');
    }}
    if (requestUrl === '/admin/chat') {{
      return responseFrom({{
        ok: true,
        response: {{
          choices: [
            {{
              message: {{
                content: JSON.stringify({{
                  title: 'Test HTML conversation',
                  summary: 'Local browser test conversation generated from the standalone HTML harness.',
                }}),
              }},
            }},
          ],
        }},
      }});
    }}
    if (requestUrl.startsWith('/admin/chat-state')) {{
      return responseFrom({{
        ok: true,
        state: {{
          activeConversationId: 'vision-test',
          conversations: [
            {{
              id: 'markdown-showcase',
              title: 'Markdown Showcase',
              folder: 'Test HTML',
              updatedAt: 1710000000000,
              lastUsedAt: 1710000000000,
              messagesLoaded: false,
            }},
            {{
              id: 'vision-test',
              title: 'Vision Test',
              folder: 'Test HTML',
              updatedAt: 1710000001000,
              lastUsedAt: 1710000001000,
              messagesLoaded: false,
            }},
          ],
          promptTemplates: [],
        }},
      }});
    }}
    if (requestUrl.startsWith('/admin/chat-conversation')) {{
      const parsedUrl = new URL(requestUrl, 'file:///');
      const conversationId = String(parsedUrl.searchParams.get('conversation_id') || parsedUrl.searchParams.get('id') || '');
      if (conversationId === 'vision-test') await wait(80);
      if (conversationId === 'markdown-showcase') await wait(10);
      const detailMap = {{
        'markdown-showcase': {{
          id: 'markdown-showcase',
          title: 'Markdown Showcase',
          folder: 'Test HTML',
          presetId: '',
          apiPresetName: '',
          messages: [
            {{
              role: 'user',
              text: 'Render the supported Markdown examples so the local parser can be inspected at a glance.',
            }},
            {{
              role: 'assistant',
              text: MARKDOWN_SHOWCASE,
              reasoningText: 'This test-only seed validates Markdown rendering without changing shipped server state.',
              thinkingDurationMs: 1420,
              thinkingDone: true,
              thinkingExpanded: false,
              modelLabel: 'Test HTML fixture',
            }},
          ],
          attachments: [],
          params: {{}},
          systemPrompt: '',
          statsCollapsed: false,
          messagesLoaded: true,
        }},
        'vision-test': {{
          id: 'vision-test',
          title: 'Vision Test',
          folder: 'Test HTML',
          presetId: '',
          apiPresetName: '',
          messages: [
            {{
              role: 'user',
              text: 'Describe what is visible in the uploaded image.',
            }},
            {{
              role: 'assistant',
              text: 'Vision test conversation loaded successfully.',
              reasoningText: 'Mocked conversation detail for concurrency regression coverage.',
              thinkingDurationMs: 980,
              thinkingDone: true,
              thinkingExpanded: false,
              modelLabel: 'Test HTML fixture',
            }},
          ],
          attachments: [],
          params: {{}},
          systemPrompt: '',
          statsCollapsed: false,
          messagesLoaded: true,
        }},
      }};
      return responseFrom({{
        ok: true,
        revision: 7,
        conversation: detailMap[conversationId] || {{
          id: conversationId || 'missing',
          title: 'Missing',
          folder: '',
          messages: [],
          attachments: [],
          params: {{}},
          systemPrompt: '',
          statsCollapsed: false,
          messagesLoaded: true,
        }},
      }});
    }}
    if (requestUrl === '/admin/chat-attachments') {{
      return responseFrom({{
        ok: true,
        attachment: {{
          id: 'fixture-image',
          kind: 'image',
          name: 'fixture.png',
          mime: 'image/png',
          source: 'file',
          url: '/admin/chat-attachments/fixture-image',
        }},
      }});
    }}
    if (requestUrl === '/admin/mcp') {{
      return responseFrom({{ ok: true, servers: [] }});
    }}
    if (/^\\/admin\\//.test(requestUrl)) {{
      return responseFrom({{
        ok: true,
        changed: false,
        users: [],
        groups: [],
        server_config: {{}},
        presets: {{ defaults: [], custom: [] }},
      }});
    }}
    if (originalFetch) return originalFetch(url, options);
    throw new Error('Unhandled request in test HTML: ' + requestUrl);
  }};
  window.EventSource = function EventSource(url) {{
    this.url = url;
    this.addEventListener = () => {{}};
    this.close = () => {{}};
  }};
  window.alert = window.alert || function alert(message) {{ console.log(String(message || '')); }};
  window.confirm = window.confirm || function confirm() {{ return true; }};
  window.prompt = window.prompt || function prompt(_message, fallback = '') {{ return fallback || ''; }};
  window.matchMedia = window.matchMedia || function matchMedia() {{
    return {{ matches: false, addListener() {{}}, removeListener() {{}}, addEventListener() {{}}, removeEventListener() {{}} }};
  }};
  window.navigator.clipboard = window.navigator.clipboard || {{ writeText: async () => {{}} }};
  window.TextDecoder = window.TextDecoder || class TextDecoder {{
    decode(value) {{
      if (!value) return '';
      return Array.from(value, (byte) => String.fromCharCode(byte)).join('');
    }}
  }};
  window.addEventListener('DOMContentLoaded', () => {{
    mountLab();
    if (typeof window.refreshStatus === 'function') {{
      window.refreshStatus({{ force: true }}).catch(() => {{}});
    }}
  }});
}})();
"""


def build_test_html(html_source: str, css_source: str, js_source: str, fixtures: list[tuple[str, dict]]) -> str:
    bootstrap = test_html_bootstrap(fixtures)
    bundled = inject_assets_into_html(html_source, css_source, bootstrap + "\n" + js_source)
    return bundled.replace("__SCRIPT_VERSION__", SCRIPT_VERSION)


def shipped_html_smoke_harness(html_text: str, status_payload: dict, fixture_name: str) -> str:
    html_payload = json.dumps(html_text, ensure_ascii=False)
    status_json = json.dumps(status_payload, ensure_ascii=False)
    fixture_label = json.dumps(fixture_name, ensure_ascii=False)
    return f"""const {{ JSDOM }} = require(process.argv[2]);
const html = {html_payload};
const statusPayload = {status_json};
const fixtureName = {fixture_label};
let asyncFailure = null;
process.on("unhandledRejection", (error) => {{
  asyncFailure = error;
}});
process.on("uncaughtException", (error) => {{
  asyncFailure = error;
}});
(async () => {{
  const dom = new JSDOM(html, {{
    url: "http://127.0.0.1:8008/admin",
    runScripts: "dangerously",
    resources: "usable",
    pretendToBeVisual: true,
    beforeParse(window) {{
      window.fetch = async (url) => {{
        if (String(url).startsWith("/admin/status")) {{
          return {{
            ok: true,
            status: 200,
            async json() {{ return statusPayload; }},
            async text() {{ return JSON.stringify(statusPayload); }},
          }};
        }}
        return {{
          ok: true,
          status: 200,
          async json() {{ return {{ ok: true, changed: false, users: [], groups: [], server_config: {{}}, presets: {{ defaults: [], custom: [] }} }}; }},
          async text() {{ return "{{\\"ok\\":true}}"; }},
        }};
      }};
      window.EventSource = function EventSource(url) {{
        this.url = url;
        this.addEventListener = () => {{}};
        this.close = () => {{}};
      }};
      window.setInterval = () => 1;
      window.clearInterval = () => {{}};
      window.setTimeout = (fn) => {{ if (typeof fn === "function") fn(); return 1; }};
      window.clearTimeout = () => {{}};
      window.alert = () => {{}};
      window.confirm = () => false;
      window.prompt = () => null;
      window.matchMedia = () => ({{ matches: false, addListener() {{}}, removeListener() {{}}, addEventListener() {{}}, removeEventListener() {{}} }});
      window.navigator.clipboard = {{ writeText: async () => {{}} }};
    }},
  }});
  await new Promise((resolve) => setTimeout(resolve, 80));
  if (asyncFailure) throw asyncFailure;
  const {{ window }} = dom;
  const summary = window.document.getElementById("summary");
  if (!summary || !summary.textContent || summary.textContent.includes("no container") && !String(statusPayload.container || "").includes("no container")) {{
    throw new Error(`summary did not render for fixture ${{fixtureName}}`);
  }}
  const gpuCards = window.document.getElementById("gpuCards");
  if (Array.isArray(statusPayload.gpus) && statusPayload.gpus.length && (!gpuCards || !gpuCards.textContent.includes("GPU 0"))) {{
    throw new Error(`GPU cards did not render for fixture ${{fixtureName}}`);
  }}
  const generationHost = window.document.getElementById("generationStatsContent");
  const hasStartedRuntime = Array.isArray(statusPayload.running_runtimes) && statusPayload.running_runtimes.some((row) =>
    row && [row.last_status, row.last_latency_s, row.last_ttft_s, row.last_tokens_per_second, row.last_total_tokens, row.last_output_tokens, row.last_request_at, row.prompt_tps, row.generation_tps, row.gpu_kv_cache_usage_pct]
      .some((value) => value !== null && value !== undefined && value !== "" && value !== 0)
  );
  if (hasStartedRuntime && (!generationHost || generationHost.textContent.includes("waiting for inference"))) {{
    throw new Error(`Generation stats did not render for fixture ${{fixtureName}}`);
  }}
  if (typeof window.refreshStatus !== "function" || typeof window.tab !== "function") {{
    throw new Error(`UI globals missing for fixture ${{fixtureName}}`);
  }}
  window.close();
  console.log(`html smoke ok: ${{fixtureName}}`);
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""


def run_shipped_html_smoke_test(html_text: str, status_payload: dict, fixture_name: str, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, shipped_html_smoke_harness(html_text, status_payload, fixture_name))
    jsdom_entry = (ROOT / "node_modules" / "jsdom" / "lib" / "api.js").resolve()
    if not jsdom_entry.exists():
        raise RuntimeError("Local jsdom install was not found at node_modules/jsdom/lib/api.js")
    result = run_command(["node", str(script_path), str(jsdom_entry)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def test_html_smoke_harness(html_text: str) -> str:
    html_payload = json.dumps(html_text, ensure_ascii=False)
    return f"""const {{ JSDOM }} = require(process.argv[2]);
const html = {html_payload};
let asyncFailure = null;
process.on("unhandledRejection", (error) => {{
  asyncFailure = error;
}});
process.on("uncaughtException", (error) => {{
  asyncFailure = error;
}});
(async () => {{
  const dom = new JSDOM(html, {{
    url: "file:///C:/club3090/web-ui.test.html",
    runScripts: "dangerously",
    resources: "usable",
    pretendToBeVisual: true,
    beforeParse(window) {{
      window.HTMLCanvasElement.prototype.getContext = () => ({{
        clearRect() {{}},
        fillRect() {{}},
        beginPath() {{}},
        moveTo() {{}},
        lineTo() {{}},
        stroke() {{}},
        fillText() {{}},
        measureText() {{ return {{ width: 0 }}; }},
      }});
      window.setInterval = window.setInterval || ((fn) => {{ if (typeof fn === "function") fn(); return 1; }});
      window.clearInterval = window.clearInterval || (() => {{}});
      window.matchMedia = window.matchMedia || (() => ({{ matches: false, addListener() {{}}, removeListener() {{}}, addEventListener() {{}}, removeEventListener() {{}} }}));
      window.navigator.clipboard = window.navigator.clipboard || {{ writeText: async () => {{}} }};
      window.TextDecoder = window.TextDecoder || class TextDecoder {{
        decode(value) {{
          if (!value) return "";
          return Array.from(value, (byte) => String.fromCharCode(byte)).join("");
        }}
      }};
    }},
  }});
  await new Promise((resolve) => setTimeout(resolve, 120));
  if (asyncFailure) throw asyncFailure;
  const {{ window }} = dom;
  if (!window.__club3090TestLab) throw new Error("test lab bootstrap did not initialize");
  const fixtureSelect = window.document.getElementById("club3090FixtureSelect");
  const fixtureEditor = window.document.getElementById("club3090FixtureEditor");
  if (!fixtureSelect || !fixtureEditor) throw new Error("test lab controls are missing");
  if (!fixtureSelect.options.length) throw new Error("fixture selector is empty");
  const preferredOption = Array.from(fixtureSelect.options).find((option) => /multi-runtime/i.test(option.value)) || fixtureSelect.options[0];
  fixtureSelect.value = preferredOption.value;
  fixtureSelect.dispatchEvent(new window.Event("change", {{ bubbles: true }}));
  await new Promise((resolve) => setTimeout(resolve, 40));
  const tabs = Array.from(window.document.querySelectorAll(".tab"));
  if (tabs.length < 3) throw new Error("top-level tabs did not render");
  const logsButton = tabs.find((button) => /logs/i.test(button.textContent || ""));
  if (!logsButton) throw new Error("logs tab button was not found");
  logsButton.click();
  const chatButton = window.document.getElementById("chatLaunchBtn");
  if (!chatButton) throw new Error("chat launcher button missing");
  chatButton.click();
  await new Promise((resolve) => setTimeout(resolve, 40));
  const chatPane = window.document.getElementById("chat");
  if (!chatPane || !chatPane.classList.contains("active")) {{
    throw new Error("chat tab did not activate");
  }}
  const conversationSelect = window.document.getElementById("chatConversationSelect");
  if (!conversationSelect) throw new Error("conversation selector missing");
  conversationSelect.value = "markdown-showcase";
  if (typeof window.selectChatConversation === "function") {{
    window.selectChatConversation("markdown-showcase");
  }} else {{
    conversationSelect.dispatchEvent(new window.Event("change", {{ bubbles: true }}));
  }}
  let transcriptAfterSwitch = null;
  for (let attempt = 0; attempt < 20; attempt += 1) {{
    await new Promise((resolve) => setTimeout(resolve, 60));
    transcriptAfterSwitch = window.document.getElementById("chatTranscript");
    if (transcriptAfterSwitch && /Markdown Showcase/.test(transcriptAfterSwitch.textContent || "")) break;
  }}
  if (!transcriptAfterSwitch || !/Markdown Showcase/.test(transcriptAfterSwitch.textContent || "")) {{
    throw new Error("chat transcript did not finish loading the switched conversation");
  }}
  if (typeof window.openConversationEditorModal !== "function" || typeof window.openChatSettingsModal !== "function") {{
    throw new Error("chat modal functions are missing");
  }}
  window.openConversationEditorModal();
  if (window.document.getElementById("chatConversationModal")?.classList.contains("hidden")) {{
    throw new Error("conversation modal did not open");
  }}
  window.closeConversationEditorModal();
  window.openChatSettingsModal();
  if (window.document.getElementById("chatSettingsModal")?.classList.contains("hidden")) {{
    throw new Error("chat settings modal did not open");
  }}
  window.closeChatSettingsModal();
  const input = window.document.getElementById("chatInput");
  if (!input) throw new Error("chat input missing");
  input.value = "hello from test html";
  if (typeof window.handleChatInputChange === "function") window.handleChatInputChange();
  await window.sendChatMessage();
  await new Promise((resolve) => setTimeout(resolve, 60));
  const transcript = window.document.getElementById("chatTranscript");
  if (!transcript || !/Test HTML response/.test(transcript.textContent || "")) {{
    throw new Error("chat transcript did not receive mocked stream output");
  }}
  if (!transcript.querySelector(".chat-thinking-card")) {{
    throw new Error("chat transcript did not render the mocked thinking summary");
  }}
  const brand = window.document.querySelector(".brand");
  if (!brand || /__SCRIPT_VERSION__/.test(brand.textContent || "")) {{
    throw new Error("script version placeholder was not replaced");
  }}
  window.close();
  console.log("test html smoke ok");
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""


def run_test_html_smoke_test(html_text: str, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, test_html_smoke_harness(html_text))
    jsdom_entry = (ROOT / "node_modules" / "jsdom" / "lib" / "api.js").resolve()
    if not jsdom_entry.exists():
        raise RuntimeError("Local jsdom install was not found at node_modules/jsdom/lib/api.js")
    result = run_command(["node", str(script_path), str(jsdom_entry)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def api_contract_smoke_harness() -> str:
    return """import importlib.util
import os
import pathlib
import sys
import time

control_path = pathlib.Path(sys.argv[1])
temp_root = pathlib.Path(sys.argv[2]) / "api-contract"
temp_root.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("club3090_control_contract", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

module.CONTROL_DIR = str(temp_root)
module.UI_CONFIG_FILE = str(temp_root / "ui_config.json")
module.CUSTOM_PRESETS_FILE = str(temp_root / "custom_presets.json")
module.INSTANCES_CONFIG_FILE = str(temp_root / "instances.json")
module.SERVER_CONFIG_FILE = str(temp_root / "server_config.json")
module.USERS_FILE = str(temp_root / "users.json")
module.GROUPS_FILE = str(temp_root / "groups.json")
module.RUNTIME_INVENTORY_FILE = str(temp_root / "runtime_inventory.json")

cfg, changed = module.write_ui_config({"active_tab": "logs", "show_global_logs": False})
assert changed is True and cfg["active_tab"] == "logs" and cfg["show_global_logs"] is False
cfg2, changed2 = module.write_ui_config({"active_tab": "logs", "show_global_logs": False})
assert changed2 is False and cfg2 == cfg

server_before = module.read_server_config()
server_after = module.write_server_config({"selected_preset_model": "fixture-model", "gpu_pairing_enabled": False})
server_after_repeat = module.write_server_config({"selected_preset_model": "fixture-model", "gpu_pairing_enabled": False})
assert server_after["selected_preset_model"] == "fixture-model"
assert server_after_repeat == server_after
assert pathlib.Path(module.SERVER_CONFIG_FILE).exists()

custom = {"sample": {"description": "fixture", "params": {"temperature": 0.7}}}
module.write_custom_presets(custom)
custom_mtime = pathlib.Path(module.CUSTOM_PRESETS_FILE).stat().st_mtime_ns
time.sleep(0.01)
module.write_custom_presets(custom)
assert pathlib.Path(module.CUSTOM_PRESETS_FILE).stat().st_mtime_ns == custom_mtime

rows = [{"id": "GPU0", "kind": "single", "gpu_index": 0, "mode": "vllm/default", "enabled": True, "port": 8200}]
module.load_runtime_inventory = lambda force=False, rebuild_if_missing=True: {"models": [], "variants": []}
module.detect_gpu_count_runtime = lambda : 1
module.resolve_variant_spec = lambda selector: {"kind": "single", "selector": selector}
module.default_single_mode_selector = lambda : "vllm/default"
module.default_dual_mode_selector = lambda : "vllm/dual"
module.write_instances_config(rows)
inst_mtime = pathlib.Path(module.INSTANCES_CONFIG_FILE).stat().st_mtime_ns
time.sleep(0.01)
module.write_instances_config(rows)
assert pathlib.Path(module.INSTANCES_CONFIG_FILE).stat().st_mtime_ns == inst_mtime

module.status_snapshot_cache = {"ok": True, "instances": [], "server_config": {}}
module.status_snapshot_updated_at = time.time()
snapshot = module.get_status_snapshot(force=False)
assert snapshot["ok"] is True and "server_config" in snapshot and "instances" in snapshot

print("api contract ok")
"""


def run_api_contract_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, api_contract_smoke_harness())
    result = run_command([sys.executable, str(script_path), str(control_path), str(cwd)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def chat_state_race_smoke_harness() -> str:
    return """import importlib.util
import json
import os
import pathlib
import shutil
import sys
import tempfile

control_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("club3090_control_chat_race", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

temp_root = pathlib.Path(tempfile.mkdtemp(prefix="club3090-chat-race-"))
try:
    module.CONTROL_DIR = str(temp_root)
    module.CHAT_CONVERSATIONS_DIR = str(temp_root / "conversations")
    module.CHAT_STATE_FILE = str(temp_root / "conversations" / "state.json")
    module.CHAT_ATTACHMENTS_DIR = str(temp_root / "conversations" / "attachments")
    os.makedirs(module.CHAT_ATTACHMENTS_DIR, exist_ok=True)

    pathlib.Path(module._chat_attachment_blob_path("used")).write_bytes(b"used")
    pathlib.Path(module._chat_attachment_blob_path("orphan")).write_bytes(b"orphan")
    pathlib.Path(module._chat_attachment_meta_path("used")).write_text(
        json.dumps({"id": "used", "mime": "image/png"}),
        encoding="utf-8",
    )
    pathlib.Path(module._chat_attachment_meta_path("orphan")).write_text(
        json.dumps({"id": "orphan", "mime": "image/png"}),
        encoding="utf-8",
    )

    state = module.write_chat_state(
        {
            "revision": 1,
            "activeConversationId": "c1",
            "conversations": [
                {
                    "id": "c1",
                    "title": "Conversation One",
                    "messages": [],
                    "attachments": [
                        {
                            "id": "used",
                            "kind": "image",
                            "url": "/admin/chat-attachments/used",
                        }
                    ],
                }
            ],
            "promptTemplates": [],
        }
    )
    assert state["revision"] == 1
    assert pathlib.Path(module._chat_attachment_blob_path("used")).exists()
    assert not pathlib.Path(module._chat_attachment_blob_path("orphan")).exists()

    stale = module.write_chat_state(
        {
            "revision": 1,
            "activeConversationId": "",
            "conversations": [],
            "promptTemplates": [],
        }
    )
    assert len(stale.get("conversations") or []) == 1

    deleted = module.delete_chat_conversation("c1")
    assert deleted["ok"] is True
    assert deleted["state"]["revision"] == 2
    assert deleted["state"]["conversations"] == []
    assert not pathlib.Path(module._chat_attachment_blob_path("used")).exists()

    replay = module.write_chat_state(
        {
            "revision": 1,
            "activeConversationId": "c1",
            "conversations": [
                {
                    "id": "c1",
                    "title": "Stale Replay",
                    "messages": [],
                    "attachments": [],
                }
            ],
            "promptTemplates": [],
        }
    )
    assert replay["revision"] == 2
    assert replay["conversations"] == []
    print("chat state race smoke ok")
finally:
    shutil.rmtree(temp_root, ignore_errors=True)
"""


def run_chat_state_race_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, chat_state_race_smoke_harness())
    result = run_command([sys.executable, str(script_path), str(control_path)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def log_bootstrap_tail_smoke_harness() -> str:
    return """import importlib.util
import pathlib
import sys

control_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("club3090_control_log_tail", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

seen = {}

def fake_run(args, **kwargs):
    seen["args"] = list(args)
    seen["timeout"] = kwargs.get("timeout")
    class Result:
        stdout = "2026-05-14T20:51:12Z first line\\n2026-05-14T20:51:13Z second line\\n"
    return Result()

watcher = module.RuntimeLogWatcher.__new__(module.RuntimeLogWatcher)
watcher.container_name = "demo-container"
watcher._set_status = lambda status: seen.setdefault("status", status)
watcher._append_line = lambda line, timestamp="": seen.setdefault("lines", []).append((timestamp, line))

original_run = module.subprocess.run
original_tail = module.LOG_INITIAL_TAIL_LINES
try:
    module.subprocess.run = fake_run
    module.LOG_INITIAL_TAIL_LINES = 250
    last_timestamp, last_line = watcher._load_initial_snapshot()
finally:
    module.subprocess.run = original_run
    module.LOG_INITIAL_TAIL_LINES = original_tail

assert seen["args"][:3] == ["docker", "logs", "--timestamps"], seen
assert "--tail" in seen["args"], seen
assert "250" in seen["args"], seen
assert seen["args"][-1] == "demo-container", seen
assert seen["timeout"] is not None and float(seen["timeout"]) <= 20, seen
assert last_timestamp == "2026-05-14T20:51:13Z", (last_timestamp, last_line)
assert last_line == "second line", (last_timestamp, last_line)
assert len(seen.get("lines") or []) == 2, seen
print("log bootstrap tail smoke ok")
"""


def run_log_bootstrap_tail_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, log_bootstrap_tail_smoke_harness())
    result = run_command([sys.executable, str(script_path), str(control_path)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def log_query_cli_smoke_harness() -> str:
    return """import contextlib
import importlib.util
import io
import pathlib
import shutil
import sys
import tempfile

control_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("club3090_control_log_query", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

temp_root = pathlib.Path(tempfile.mkdtemp(prefix="club3090-log-query-"))
try:
    audit_path = temp_root / "audit.log"
    audit_path.write_text(
        "\\n".join(
            [
                "2026-05-14 info boot ok",
                "2026-05-14 error status snapshot fallback: demo",
                "2026-05-14 warn reconnecting logs",
            ]
        ) + "\\n",
        encoding="utf-8",
    )
    module.AUDIT_LOG_FILE = str(audit_path)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
      module.emit_cli_log_query(module.AUDIT_LOG_FILE, ["--tail", "5", "--match", "fallback"])
    text = output.getvalue()
    assert "status snapshot fallback" in text, text
    assert "reconnecting logs" not in text, text
    print("log query cli smoke ok")
finally:
    shutil.rmtree(temp_root, ignore_errors=True)
"""


def run_log_query_cli_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, log_query_cli_smoke_harness())
    result = run_command([sys.executable, str(script_path), str(control_path)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def docker_logrotate_refresh_smoke_harness() -> str:
    return """import importlib.util
import pathlib
import shutil
import sys
import tempfile

control_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("club3090_control_logrotate", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

temp_root = pathlib.Path(tempfile.mkdtemp(prefix="club3090-logrotate-"))
try:
    target = temp_root / "club3090-docker-containers"
    module.DOCKER_LOGROTATE_FILE = str(target)
    module.managed_docker_log_paths = lambda: ["/var/lib/docker/containers/a/a-json.log", "/var/lib/docker/containers/b/b-json.log"]
    ok = module.refresh_docker_logrotate_config()
    assert ok is True
    text = target.read_text(encoding="utf-8")
    assert "rotate 7" in text, text
    assert "copytruncate" in text, text
    assert "/var/lib/docker/containers/a/a-json.log" in text, text
    print("docker logrotate refresh smoke ok")
finally:
    shutil.rmtree(temp_root, ignore_errors=True)
"""


def run_docker_logrotate_refresh_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, docker_logrotate_refresh_smoke_harness())
    result = run_command([sys.executable, str(script_path), str(control_path)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def ui_service_actions_smoke_harness(js_text: str) -> str:
    payload = json.dumps(js_text, ensure_ascii=False)
    return f"""const vm = require("vm");
const code = {payload};
const elements = new Map();
function makeClassList() {{
  return {{
    add() {{}},
    remove() {{}},
    toggle() {{}},
    contains() {{ return false; }},
  }};
}}
function makeElement(id = "") {{
  return {{
    id,
    value: "",
    textContent: "",
    innerHTML: "",
    checked: true,
    disabled: false,
    scrollTop: 0,
    scrollHeight: 100,
    clientHeight: 100,
    width: 300,
    height: 150,
    clientWidth: 300,
    className: "",
    dataset: {{}},
    style: {{}},
    children: [],
    classList: makeClassList(),
    appendChild(child) {{ this.children.push(child); return child; }},
    insertBefore(child) {{ this.children.push(child); return child; }},
    insertAdjacentElement(_pos, child) {{ this.children.push(child); return child; }},
    querySelector(selector) {{ return getElement(selector); }},
    querySelectorAll() {{ return []; }},
    addEventListener() {{}},
    removeEventListener() {{}},
    focus() {{}},
    select() {{}},
    setSelectionRange() {{}},
    setAttribute() {{}},
    removeAttribute() {{}},
    remove() {{}},
    getContext() {{
      return {{
        clearRect() {{}},
        fillText() {{}},
        beginPath() {{}},
        moveTo() {{}},
        lineTo() {{}},
        stroke() {{}},
      }};
    }},
  }};
}}
function getElement(id) {{
  const key = String(id || "");
  if (!elements.has(key)) elements.set(key, makeElement(key));
  return elements.get(key);
}}
const document = {{
  body: getElement("body"),
  createElement(tag) {{ return makeElement(tag); }},
  getElementById(id) {{ return getElement(id); }},
  querySelector(selector) {{ return getElement(selector); }},
  querySelectorAll() {{ return []; }},
  addEventListener() {{}},
  execCommand() {{ return true; }},
}};
const context = {{
  console,
  document,
  navigator: {{ clipboard: {{ writeText: async () => {{}} }} }},
  localStorage: {{ getItem() {{ return null; }}, setItem() {{}}, removeItem() {{}} }},
  EventSource: function EventSource() {{
    this.addEventListener = () => {{}};
    this.close = () => {{}};
  }},
  fetch: async (url) => {{
    if (String(url).startsWith("/admin/status")) {{
      return {{
        ok: true,
        status: 200,
        async json() {{ return {{ metrics: {{}}, power: {{}}, gpus: [], users: [], groups: [], server_config: {{}}, instances: [], presets: {{ defaults: [], custom: [] }}, ui_config: {{}}, series: [], system: {{ cpu: {{ cores: [] }}, memory: null, disks: [], network: {{}}, info: {{}} }}, models: [], variants: [], instance_runtime_metrics: {{}}, running_runtimes: [], containers: [], active_modes: [], gpu_count: 0, upstream_services: [] }}; }},
        async text() {{ return "{{\\"ok\\":true}}"; }},
      }};
    }}
    return {{
      ok: true,
      status: 200,
      async json() {{ return {{ ok: true }}; }},
      async text() {{ return "{{\\"ok\\":true}}"; }},
    }};
  }},
  setInterval() {{ return 1; }},
  clearInterval() {{}},
  setTimeout(fn) {{ if (typeof fn === "function") fn(); return 1; }},
  clearTimeout() {{}},
  alert() {{}},
  confirm() {{ return false; }},
  prompt() {{ return null; }},
  devicePixelRatio: 1,
  URLSearchParams,
  Date,
}};
context.window = {{
  document,
  navigator: context.navigator,
  localStorage: context.localStorage,
  fetch: context.fetch,
  setTimeout: context.setTimeout,
  clearTimeout: context.clearTimeout,
  setInterval: context.setInterval,
  clearInterval: context.clearInterval,
  addEventListener() {{}},
}};
vm.createContext(context);
vm.runInContext(code, context, {{ filename: "web-ui.js" }});

if (typeof context.renderServiceCards !== "function") throw new Error("renderServiceCards() missing");
const startingHtml = context.renderServiceCards(
  [{{
    id: "searxng",
    display_name: "SearXNG",
    status: "running",
    health_status: "unreachable",
    stateClass: "warn",
    detail: "port 8088",
    ready: false,
  }}],
  {{ showActions: true }},
);
if (!startingHtml.includes(">Start<")) throw new Error("starting service should show Start");
if (startingHtml.includes(">Restart<")) throw new Error("starting service should not show Restart");
if (startingHtml.includes(">Stop<")) throw new Error("starting service should not show Stop");

const readyHtml = context.renderServiceCards(
  [{{
    id: "searxng",
    display_name: "SearXNG",
    status: "running",
    health_status: "healthy",
    stateClass: "ok",
    detail: "port 8088",
    ready: true,
  }}],
  {{ showActions: true }},
);
if (!readyHtml.includes(">Restart<")) throw new Error("ready service should show Restart");
if (!readyHtml.includes(">Stop<")) throw new Error("ready service should show Stop");
if (readyHtml.includes(">Start<")) throw new Error("ready service should not show Start");

console.log("ui service action smoke ok");
"""


def run_ui_service_actions_smoke_test(js_text: str, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, ui_service_actions_smoke_harness(js_text))
    result = run_command(["node", str(script_path)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def load_status_fixtures() -> list[tuple[str, dict]]:
    fixtures: list[tuple[str, dict]] = []
    if not FIXTURES_DIR.exists():
        return fixtures
    for path in sorted(FIXTURES_DIR.glob("status-*.json")):
        try:
            fixtures.append((path.stem, json.loads(read_text(path))))
        except Exception:
            continue
    return fixtures


def scan_potential_dead_code(js_source: str, html_source: str, css_source: str) -> list[str]:
    warnings: list[str] = []
    function_names = sorted(set(re.findall(r"(?m)^function\s+([A-Za-z_]\w*)\s*\(", js_source) + re.findall(r"(?m)^([A-Za-z_]\w*)\s*=\s*function\b", js_source)))
    html_hook_names = set(re.findall(r"""(?:onclick|onchange|oninput)="\s*([A-Za-z_]\w*)\s*\(""", html_source))
    text_hits = {name: len(re.findall(rf"\b{name}\b", js_source)) for name in function_names}
    unused = [name for name in function_names if text_hits.get(name, 0) <= 1 and name not in html_hook_names and not name.startswith("render")]
    if unused:
        warnings.append("Potentially unused JS functions: " + ", ".join(unused[:12]) + (" ..." if len(unused) > 12 else ""))
    selector_counts: dict[str, int] = {}
    for selector in re.findall(r"(?m)^([^{@][^{]+?)\s*\{", css_source):
        key = " ".join(selector.split())
        selector_counts[key] = selector_counts.get(key, 0) + 1
    duplicates = sorted(key for key, count in selector_counts.items() if count > 1)
    if duplicates:
        warnings.append("Duplicate CSS selectors detected: " + ", ".join(duplicates[:8]) + (" ..." if len(duplicates) > 8 else ""))
    return warnings


def run_ui_smoke_test(js_text: str, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, ui_smoke_harness(js_text))
    result = run_command(["node", str(script_path)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def cleanup_root_artifacts(report: BuildReport) -> None:
    keep = {name.lower() for name in AUTHORITATIVE_FILES}
    for pattern in DERIVED_ROOT_GLOBS:
        for path in ROOT.glob(pattern):
            if path.name.lower() in keep:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            report.removed_root_artifacts.append(path.name)


def build_release() -> int:
    report = BuildReport(version=VERSION, script_version=SCRIPT_VERSION)
    write_text(BUILD_LOG_PATH, "")
    flush_build_report(report, f"build started for v{VERSION}")

    control_source = read_text(ROOT / "control.py")
    html_source = read_text(ROOT / "web-ui.html")
    css_source = read_text(ROOT / "web-ui.css")
    js_source = read_text(ROOT / "web-ui.js")
    script_source = read_text(ROOT / "install-club3090-server.sh")
    status_fixtures = load_status_fixtures()

    report.warnings.extend(scan_duplicate_functions(ROOT / "web-ui.js", js_source))
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

    if 'HTML = ""  # Injected by build.py for shipped outputs.\n' not in control_source:
        report.add_test("control_source_placeholder", "failed", "control.py is missing the build-time HTML placeholder")
        flush_build_report(report, "build failed: control placeholder missing")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("control_source_placeholder", "passed", "control.py keeps HTML as a build-time placeholder")

    if "/* injected by build.py from web-ui.css */" not in html_source or "// injected by build.py from web-ui.js" not in html_source:
        report.add_test("html_template_placeholders", "failed", "web-ui.html is missing CSS/JS build placeholders")
        flush_build_report(report, "build failed: html placeholders missing")
        print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
        return 1
    report.add_test("html_template_placeholders", "passed", "web-ui.html keeps CSS/JS template placeholders")

    bundled_css_source, bundled_js_source = compose_web_assets(css_source, js_source)
    bundle_html = inject_assets_into_html(html_source, bundled_css_source, bundled_js_source)

    with tempfile.TemporaryDirectory(prefix="club3090-build-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        temp_control = temp_dir / "control.ship.py"
        temp_script = temp_dir / "install-club3090-server.sh"
        temp_bundle = temp_dir / "web-ui.bundle.html"
        temp_min_css = temp_dir / "web-ui.min.css"
        temp_min_js = temp_dir / "web-ui.min.js"
        temp_ship_raw = temp_dir / "web-ui.ship.raw.html"
        temp_ship = temp_dir / "web-ui.ship.html"

        write_text(temp_bundle, bundle_html)

        try:
            compile(read_text(ROOT / "build.py"), str(ROOT / "build.py"), "exec")
            report.add_test("python_build_compile", "passed", "build.py compiled successfully")
        except Exception as exc:
            report.add_test("python_build_compile", "failed", str(exc))
            flush_build_report(report, "build failed: build.py compilation")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1

        flush_build_report(report, "running node syntax check for web-ui.js")
        node_check = run_command(["node", "--check", str(ROOT / "web-ui.js")], ROOT)
        if node_check.returncode != 0:
            detail = (node_check.stderr or node_check.stdout or "node --check failed").strip()
            report.add_test("node_js_syntax", "failed", detail)
            flush_build_report(report, "build failed: node syntax check")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("node_js_syntax", "passed", "web-ui.js passed node --check")

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
        built_control = inject_html_into_control(control_source, ship_html)
        built_script = inject_control_into_script(script_source, built_control)
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
            bash_check = run_command([str(bash_path), "-lc", "bash -n install-club3090-server.sh"], temp_dir)
            if bash_check.returncode != 0:
                detail = (bash_check.stderr or bash_check.stdout or "bash -n failed").strip()
                report.add_test("bash_script_syntax", "failed", detail)
                flush_build_report(report, "build failed: bash syntax check")
                print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
                return 1
            report.add_test("bash_script_syntax", "passed", "install-club3090-server.sh passed bash -n")
        else:
            report.warn("Git Bash was not found locally; bash syntax validation was skipped")
            report.add_test("bash_script_syntax", "skipped", "Git Bash not found")

        if "\r" in built_script or "\r" in built_control:
            detail = "CRLF detected in built outputs"
            report.add_test("lf_line_endings", "failed", detail)
            flush_build_report(report, "build failed: LF line ending check")
            print(json.dumps(report.__dict__, indent=2), file=sys.stderr)
            return 1
        report.add_test("lf_line_endings", "passed", "Built outputs use LF line endings only")

        write_text(ROOT / "install-club3090-server.sh", built_script)

        backup_dir = ROOT / "Backups" / f"Backups_{BACKUP_TAG}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        write_text(backup_dir / f"install-club3090-server-{VERSION_TAG}.sh", built_script)
        write_text(backup_dir / "control.py", control_source)
        write_text(backup_dir / "control.ship.py", built_control)
        write_text(backup_dir / "web-ui.html", html_source)
        write_text(backup_dir / "web-ui.css", css_source)
        write_text(backup_dir / "web-ui.js", js_source)
        write_text(backup_dir / "web-ui.bundle.html", bundle_html)
        write_text(backup_dir / "web-ui.min.css", min_css)
        write_text(backup_dir / "web-ui.min.js", min_js)
        write_text(backup_dir / "web-ui.ship.raw.html", ship_raw_html)
        write_text(backup_dir / "web-ui.ship.html", ship_html)
        write_text(backup_dir / "build.py", read_text(ROOT / "build.py"))
        for package_file in ("package.json", "package-lock.json"):
            package_path = ROOT / package_file
            if package_path.exists():
                write_text(backup_dir / package_file, read_text(package_path))
        if FIXTURES_DIR.exists():
            fixtures_backup = backup_dir / FIXTURES_DIR.name
            fixtures_backup.mkdir(parents=True, exist_ok=True)
            for fixture in FIXTURES_DIR.glob("*.json"):
                write_text(fixtures_backup / fixture.name, read_text(fixture))
        for checklist in ROOT.glob("CHECKLIST_*.md"):
            write_text(backup_dir / checklist.name, read_text(checklist))

        cleanup_root_artifacts(report)
        write_text(backup_dir / "build-report.json", json.dumps(report.__dict__, indent=2))

    flush_build_report(report, "build completed successfully")
    print(json.dumps(report.__dict__, indent=2))
    return 0


def build_test_html_mode() -> int:
    html_source = read_text(ROOT / "web-ui.html")
    css_source = read_text(ROOT / "web-ui.css")
    js_source = read_text(ROOT / "web-ui.js")
    fixtures = load_status_fixtures()

    if "/* injected by build.py from web-ui.css */" not in html_source or "// injected by build.py from web-ui.js" not in html_source:
        print("web-ui.html is missing CSS/JS build placeholders", file=sys.stderr)
        return 1

    test_html = build_test_html(html_source, css_source, js_source, fixtures)
    write_text(TEST_HTML_PATH, test_html)

    with tempfile.TemporaryDirectory(prefix="club3090-test-html-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        node_check = run_command(["node", "--check", str(ROOT / "web-ui.js")], ROOT)
        if node_check.returncode != 0:
            detail = (node_check.stderr or node_check.stdout or "node --check failed").strip()
            print(detail, file=sys.stderr)
            return 1
        ok, detail = run_test_html_smoke_test(test_html, temp_dir, "web-ui.test-html.smoke.cjs")
        if not ok:
            print(detail or "test HTML smoke test failed", file=sys.stderr)
            return 1
        service_ok, service_detail = run_ui_service_actions_smoke_test(
            js_source,
            temp_dir,
            "web-ui.test-html.service-actions.smoke.cjs",
        )
        if not service_ok:
            print(service_detail or "UI service action smoke test failed", file=sys.stderr)
            return 1
        compile(read_text(ROOT / "build.py"), str(ROOT / "build.py"), "exec")

    print(json.dumps({
        "mode": "test-html",
        "version": VERSION,
        "script_version": SCRIPT_VERSION,
        "output": str(TEST_HTML_PATH),
        "fixtures": [name for name, _ in fixtures],
        "validation": "passed",
        "detail": detail or service_detail or "test html smoke ok",
    }, indent=2))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Club-3090 control artifacts")
    parser.add_argument(
        "--test-html",
        action="store_true",
        help="Generate a fully self-contained local web UI test page with mocked admin API fixtures.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.test_html:
        return build_test_html_mode()
    return build_release()


if __name__ == "__main__":
    raise SystemExit(main())
