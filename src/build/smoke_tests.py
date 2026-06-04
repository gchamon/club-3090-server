import json
import sys
import tempfile

from build_support import *


def ui_smoke_harness(js_text: str) -> str:
    payload = json.dumps(js_text, ensure_ascii=False)
    code_syntax_payload = json.dumps(load_embedded_code_syntax_json(), ensure_ascii=False)
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
    if (String(url).startsWith("/admin/code-syntax")) {{
      return {{
        ok: true,
        status: 200,
        async json() {{ return JSON.parse({code_syntax_payload}); }},
        async text() {{ return {code_syntax_payload}; }},
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
  if (code.includes("systemUtilityRow")) throw new Error("legacy systemUtilityRow layout shim should not be present");
  if (typeof context.tab !== "function") throw new Error("tab() was not initialized");
  if (typeof context.refreshStatus !== "function") throw new Error("refreshStatus() was not initialized");
  const updateStatus = {{
    ...statusPayload,
    remote_update: {{
      update_available: true,
      script_version: "2026-05-19.v0.6.108",
      commit_sha: "abc123",
    }},
    self_update: {{
      active: true,
      scope: "controller",
      stream_url: "/admin/update-stream?token=test-token&tail=4000",
      status_url: "/admin/update-status?token=test-token",
      summary: "running",
    }},
  }};
  context.__updateStatus = updateStatus;
  vm.runInContext("ensureV414Layout(); lastStatus = __updateStatus; renderUpdateNotices(__updateStatus); renderLogSourcePanel();", context);
  if (String(getElement("updateNoticeHost").innerHTML || "").includes("update-notice-bar-green")) {{
    throw new Error("update notice banner should hide the green update header while a self-update is active");
  }}
  if (!String(getElement("logSourcePanel").innerHTML || "").includes("disabled")) {{
    throw new Error("log source controls should render disabled while a self-update is active");
  }}
  vm.runInContext("currentLogSource = 'update'; renderLogSourcePanel(); setCurrentLogSource('audit');", context);
  if (vm.runInContext("currentLogSource", context) !== "update") {{
    throw new Error("log source switching should stay pinned to update logs while a self-update is active");
  }}
  vm.runInContext("updateMonitor.active = false; reconcileUpdateUiFromStatus(__updateStatus);", context);
  if (!vm.runInContext("updateMonitor.active", context)) {{
    throw new Error("self-update state from status should resume the update monitor after a reload");
  }}
  const selectorStatus = {{
    ...statusPayload,
    runtime_inventory: {{
      models: [
        {{ model_id: "qwen3.6-27b", display_name: "Qwen3.6-27B", installed_state: "ready" }},
        {{ model_id: "custom-fixture", display_name: "Fixture Custom", installed_state: "ready", source_kind: "custom", custom_model: true }},
      ],
      variants: [],
      profile_likes: [{{ key: "vllm/minimal", model_id: "qwen3.6-27b", model_display_name: "Qwen3.6-27B", tp: 1 }}],
    }},
    models: [
      {{ model_id: "qwen3.6-27b", display_name: "Qwen3.6-27B", installed_state: "ready" }},
      {{ model_id: "custom-fixture", display_name: "Fixture Custom", installed_state: "ready", source_kind: "custom", custom_model: true }},
    ],
    variants: [],
  }};
  context.__selectorStatus = selectorStatus;
  vm.runInContext("lastStatus = __selectorStatus; ensureDynamicPresetLayout(); renderPresetModelSelector();", context);
  const selectorHtml = String(getElement("presetModelSelector").innerHTML || "");
  if (!selectorHtml.includes("custom-model-trigger") || !selectorHtml.includes("Custom Model")) {{
    throw new Error("preset model selector should include the custom model trigger");
  }}
  if (!selectorHtml.includes("Fixture Custom")) {{
    throw new Error("preset model selector should render custom model tabs");
  }}
  const presetStatus = {{
    ...statusPayload,
    gpu_count: 2,
    instances: [
      {{ id: "GPU0", kind: "single", gpu_indices: [0], running: false, booting: false, mode: "" }},
      {{ id: "GPU1", kind: "single", gpu_indices: [1], running: true, booting: false, mode: "ik-llama/iq4ks-mtp" }},
    ],
    running_runtimes: [
      {{
        id: "GPU1",
        instance_id: "GPU1",
        selector: "ik-llama/iq4ks-mtp",
        mode: "ik-llama/iq4ks-mtp",
        running: true,
        booting: false,
        gpu_indices: [1],
        display_name: "GPU 1",
      }},
    ],
    variants: [
      {{
        upstream_tag: "ik-llama/iq4ks-mtp",
        variant_id: "iq4ks-mtp",
        model_id: "qwen3.6-27b",
        scope_kind: "single",
        install_state: "ready",
        best_for: "Fast reasoning",
        engine: "ik-llama",
        engine_display: "ik-llama",
        drafter: "",
        kv_format: "q4_0",
        max_model_len: 131072,
      }},
      {{
        upstream_tag: "vllm/qwen-a3b-preview-single",
        variant_id: "qwen-a3b-preview-single",
        model_id: "qwen3.6-35b-a3b",
        scope_kind: "single",
        install_state: "requires_download",
        best_for: "Large MoE",
        engine: "vllm",
        engine_display: "vllm",
        install_command: "hf download Intel/Qwen3.6-35B-A3B-int4-mixed-AutoRound --local-dir /models/target",
      }},
    ],
  }};
  context.__presetStatus = presetStatus;
  vm.runInContext("selectedScope = 'GPU0'; lastStatus = __presetStatus;", context);
  const runningCardHtml = String(vm.runInContext("renderVariantCard(lastStatus.variants[0])", context) || "");
  if (!runningCardHtml.includes(">Stop<")) {{
    throw new Error("model preset card should render Stop when the preset is already running on another scope");
  }}
  const downloadCardHtml = String(vm.runInContext("renderVariantCard(lastStatus.variants[1])", context) || "");
  if (!downloadCardHtml.includes('title=\"Download source: Intel/Qwen3.6-35B-A3B-int4-mixed-AutoRound\"')) {{
    throw new Error("download preset card should expose the Hugging Face repo in the button tooltip");
  }}
  console.log("ui smoke ok");
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""


def test_html_bootstrap(fixtures: list[tuple[str, dict]], code_syntax_json: str) -> str:
    fixture_map = {name: payload for name, payload in fixtures}
    fixture_json = json.dumps(fixture_map, ensure_ascii=False)
    code_syntax_payload = json.dumps(code_syntax_json or "{}", ensure_ascii=False)
    markdown_showcase = """# Markdown Showcase

This seeded test-only conversation exercises the local parser surface an AI agent is likely to emit: **bold**, *italic*, ***bold italic***, __strong underscores__, _safe emphasis_, ~~deleted text~~, ==highlighted text==, `inline code`, <kbd>Ctrl</kbd> + <kbd>K</kbd>, and escaped punctuation like \\*literal stars\\*, \\[literal brackets\\], and \\$literal dollars\\$.

Mixed inline stress: before _safe emphasis_ after, before <kbd>Enter</kbd> after, `literal *stars*`, **bold with `code` inside**, and [inline link after emphasis](https://example.com/inline).

### Practical Copy

Release note summary:
- API compatibility: **stable**
- Backend refresh: _pending rollout_
- Safety review: ==needs sign-off==
- Escaped literal: \\`not code\\`

Support response template:
> Thanks for reporting this.
> We reproduced it on the local fixture and narrowed it to the Markdown renderer.

## Links, Emails, And Media

- External link with confirmation modal: [OpenAI](https://openai.com)
- Internal link without modal: [Status panel](/admin)
- Autolink: https://example.com/docs?query=club-3090.
- Email autolink: ops@example.com
- Broken image should become a static note: ![broken fixture image](https://example.invalid/missing-image.png)
- Reference-style link: [Club 3090 repo][club-repo]
- Collapsed reference link: [Docs][]
- Bare www link: www.example.com/path
- Link with punctuation after it: [Admin logs](https://example.com/logs), then continue the sentence.
- Fragment link: [Jump to chat stats](/admin#chat)
- Mail-style inline text: Reach us at support@example.com or ops@example.com.

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

- Workflow checklist
  - [x] Parse headings
  - [x] Render links
  - [ ] Review edge cases
  - [ ] Ship after DOM verification

- Mixed content item with **bold**, `code`, [link](/admin), and ==highlight==.

## Definition Lists

Another Term
: First definition
: Second definition with **strong text** and [a reference][club-repo].

Glossary: A compact inline definition form.

## Blockquotes

> A quoted answer can contain **formatting**.
> - Nested quote list item
> - Another item with $E = mc^2$
> > Nested quote level two with [an internal link](/admin#chat)

> [!NOTE]
> This is a note for the user.
>
> It spans multiple lines.

> [!WARNING]
> The local parser should not trust raw HTML.
>
> It should preserve the text while blocking unsafe execution.

<details>
<summary>Click to expand</summary>
This content is hidden by default.
</details>

<details>
<summary>Deployment checklist</summary>

1. Pull the latest split sources
2. Rebuild the integrated installer
3. Open the local test fixture
4. Verify the rendered DOM before shipping

</details>

## Tables

| Feature | Status | Notes |
|:--|:--:|--:|
| Links | pass | modal |
| Tables | pass | aligned |
| Math | pass | 123 |
| Escapes | pass | \\| pipe |
| Inline | **bold** | `code` and [link](/admin) |
| Math | $x_i^2$ | $\\frac{1}{2}$ |

| Workflow | owner | expected outcome |
|:--|:--|:--|
| install | admin | service online |
| update | maintainer | no data loss |
| verify | QA | DOM matches fixture |

## Math

Inline math should stay readable: $2 + 2 = 4$, $E = mc^2$, $x_i^2$, $\\frac{a}{b}$, and $\\sqrt{x^2 + y^2}$.
More math: $\\alpha + \\beta \\leq \\gamma$, $\\lim_{x\\to 0} \\frac{\\sin x}{x} = 1$, and $a_{n+1} = a_n + d$.

Bracket math should also render: \\(\\left(\\frac{a}{b}\\right)\\), \\(\\forall x \\in \\mathbbR, \\exists y \\in \\mathbbZ\\), and \\(\\vecF = m \\veca\\).

More parser edge cases: \\(\\binomnk\\), \\(\\tbinomnk\\), \\(\\dbinomnk\\), \\(\\xleftarrow\\), \\(\\xrightarrow\\), \\(\\longrightarrow\\), \\(\\braket{\\psi}\\), \\(\\inneruv\\), \\(\\mathrmV\\), \\(\\colorred + \\colorblue = \\colorgreen\\), \\(\\aleph + \\beth + \\gimel + \\daleth\\), \\(\\hbar = \\frac{h}{2\\pi}\\), \\(\\hslash = \\hbar\\), \\(\\ell^2(\\mathbbR)\\), \\(\\Im z + \\Re z\\), and \\(\\dots + \\cdots + \\ldots + \\vdots + \\ddots\\).

\\[
\\begin{aligned}
f(x) &= ax^2 + bx + c \\\\
f'(x) &= 2ax + b
\\end{aligned}
\\]

\\[
\\begin{pmatrix}
a & b \\\\
c & d
\\end{pmatrix}
= ad - bc
\\]

\\[
\\begin{smallmatrix}
1 & 0 \\\\
0 & 1
\\end{smallmatrix}
\\qquad
\\sum_{\\begin{subarray}{l}
i \\in \\Lambda \\\\
0 < j < n
\\end{subarray}} x_{ij}
\\]

\\[
f(x)=\\begin{cases}
x^2 & \\textif x < 0 \\\\
x & \\textif x \\ge 0
\\end{cases}
\\]

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

```json
{
  "mode": "verify",
  "fixture": "markdown-showcase",
  "expect_mermaid_blocks": 6
}
```

```html
<!DOCTYPE html>
<html>
  <head>
    <title>Test Page</title>
  </head>
  <body>
    <h1>Hello</h1>
  </body>
</html>
```

```diff
- old renderer guessed layout
+ new renderer measures content and timeline spans
```

## Mermaid

```mermaid
graph TD
  A[Start] --> B{Is it?}
  B -- Yes --> C[OK]
  B -- No --> D[Do something]
  C --> E[End]
  D --> E
```

```mermaid
sequenceDiagram
  participant Alice
  participant Bob
  Alice->>Bob: Hello Bob, how are you?
  Bob->>Alice: I am good thanks!
```

```mermaid
classDiagram
  Animal <|-- Duck
  Animal <|-- Fish
  Animal <|-- Zebra
  Animal : +int age
  Animal : +String gender
  Animal: +isMammal()
  Animal: +mate()
  class Duck{
    +String beakColor
    +swim()
    +quack()
  }
```

```mermaid
stateDiagram-v2
    [*] --> Still
    Still --> Moving
    Moving --> Still
    Moving --> Crash
    Crash --> [*]
```

```mermaid
gantt
    dateFormat  YYYY-MM-DD
    title Adding GANTT diagram functionality to mermaid
    section A section
    Completed task            :done,    des1, 2014-01-06,2014-01-08
    Active task               :active,  des2, 2014-01-09, 3d
    Future task               :         des3, 2014-01-12, 5d
```

```mermaid
pie
    title Languages
    "Python" : 45
    "JavaScript" : 30
    "Java" : 15
    "C++" : 10
```

## HTML Safety

Raw tags like <script>alert("nope")</script> should be escaped, while supported Markdown continues below.

Inline raw HTML should stay harmless too: <div class="unsafe">this should render as text, not DOM</div>.

---

Final paragraph after a rule.
"""
    mermaid_lab_cases = [
        ("Flowcharts", "Decision Gate", """graph TD
  Start[Request arrives] --> Decide{Auth valid?}
  Decide -- Yes --> Route[Route request]
  Decide -- No --> Reject[Reject request]
  Route --> Done[Done]
  Reject --> Done"""),
        ("Flowcharts", "Service Router", """graph LR
  Client[Client] --> Proxy[Proxy]
  Proxy --> Text[Text runtime]
  Proxy --> Vision[Vision runtime]
  Text --> Logs[Logs]
  Vision --> Logs"""),
        ("Flowcharts", "Incident Triage", """flowchart TD
  Alert([Alert]) --> Verify{Real issue?}
  Verify -- No --> Noise[Close as noise]
  Verify -- Yes --> Owner[Page owner]
  Owner --> Fix([Mitigate])
  Noise --> End([Archive])
  Fix --> End"""),
        ("Flowcharts", "Release Pipeline", """graph TD
  Code[Code] --> Build(Build)
  Build --> Test{Tests green?}
  Test -- Yes --> Ship[Ship]
  Test -- No --> Patch[Patch]
  Patch --> Build"""),
        ("Flowcharts", "Fan Out Fan In", """graph TD
  Input[Input] --> Parse[Parse]
  Parse --> A[Task A]
  Parse --> B[Task B]
  Parse --> C[Task C]
  A --> Merge[Merge]
  B --> Merge
  C --> Merge
  Merge --> Reply[Reply]"""),
        ("Flowcharts", "Retry Loop", """graph TD
  Queue[Queued job] --> Run[Run job]
  Run --> Result{Success?}
  Result -- Retry --> Wait[Backoff]
  Wait --> Run
  Result -- Failed --> Dead[Dead letter]
  Result -- Success --> Store[Store output]"""),
        ("Flowcharts", "Team Ownership Map", """graph TD
  Product[Product] --> API[API]
  Product --> UI[UI]
  API --> Auth[Auth]
  API --> Inference[Inference]
  UI --> Chat[Chat]
  UI --> Metrics[Metrics]"""),
        ("Flowcharts", "Deployment Topology", """graph TD
  User[User] --> Caddy[Caddy]
  Caddy --> Admin[Admin UI]
  Caddy --> Proxy[Model proxy]
  Proxy --> GPU0[GPU0 container]
  Proxy --> GPU1[GPU1 container]
  Admin --> State[State files]"""),
        ("Sequence Diagrams", "Basic Request Reply", """sequenceDiagram
  participant User
  participant Proxy
  participant Runtime
  User->>Proxy: POST /v1/chat/completions
  Proxy->>Runtime: Forward request
  Runtime->>Proxy: Stream tokens
  Proxy->>User: Stream response"""),
        ("Sequence Diagrams", "Auth Flow", """sequenceDiagram
  participant Client
  participant Gateway
  participant Auth
  participant Runtime
  Client->>Gateway: Request
  Gateway->>Auth: Validate key
  Auth->>Gateway: OK
  Gateway->>Runtime: Forward
  Runtime->>Gateway: Tokens
  Gateway->>Client: Response"""),
        ("Sequence Diagrams", "Tool Call Handoff", """sequenceDiagram
  participant User
  participant Model
  participant Tool
  participant Model2
  User->>Model: Ask for report
  Model->>Tool: Fetch logs
  Tool->>Model2: Return payload
  Model2->>User: Summarized answer"""),
        ("Sequence Diagrams", "Webhook Ack", """sequenceDiagram
  participant Worker
  participant Queue
  participant Webhook
  Worker->>Queue: Poll
  Queue->>Worker: Job
  Worker->>Webhook: POST result
  Webhook->>Worker: 200 OK"""),
        ("Sequence Diagrams", "Support Escalation", """sequenceDiagram
  participant User
  participant Agent
  participant Lead
  participant Ops
  User->>Agent: Report bug
  Agent->>Lead: Escalate
  Lead->>Ops: Request logs
  Ops->>Lead: Findings
  Lead->>User: Resolution"""),
        ("Class Diagrams", "Domain Model", """classDiagram
  Service <|-- ChatService
  Service <|-- MetricsService
  Service : +String id
  Service : +start()
  Service : +stop()
  class ChatService{
    +stream()
    +cancel()
  }
  class MetricsService{
    +collect()
  }"""),
        ("Class Diagrams", "Worker Interfaces", """classDiagram
  Worker <|-- DownloadWorker
  Worker <|-- BuildWorker
  Worker : +queue()
  Worker : +run()
  class DownloadWorker{
    +fetchModel()
  }
  class BuildWorker{
    +bundleAssets()
  }"""),
        ("Class Diagrams", "API Resources", """classDiagram
  Resource <|-- Conversation
  Resource <|-- RuntimeSnapshot
  Resource : +String id
  class Conversation{
    +title
    +messages
  }
  class RuntimeSnapshot{
    +mode
    +gpuIndices
  }"""),
        ("State Diagrams", "Motion Loop", """stateDiagram-v2
  [*] --> Still
  Still --> Moving
  Moving --> Still
  Moving --> Crash
  Crash --> [*]"""),
        ("State Diagrams", "Approval Workflow", """stateDiagram-v2
  [*] --> Draft
  Draft --> Review
  Review --> Approved
  Review --> Draft
  Approved --> Published
  Published --> [*]"""),
        ("State Diagrams", "Job Recovery", """stateDiagram-v2
  [*] --> Pending
  Pending --> Running
  Running --> Failed
  Failed --> Pending
  Running --> Complete
  Complete --> [*]"""),
        ("Gantt Charts", "Feature Rollout", """gantt
  dateFormat  YYYY-MM-DD
  title Feature rollout
  section Planning
  Scope review       :done, p1, 2026-01-05, 2026-01-07
  Stakeholder signoff:done, p2, 2026-01-08, 2d
  section Delivery
  Backend changes    :active, d1, 2026-01-10, 4d
  UI verification    :d2, 2026-01-14, 3d"""),
        ("Gantt Charts", "Migration Window", """gantt
  dateFormat  YYYY-MM-DD
  title Migration window
  section Prep
  Snapshot data      :done, m1, 2026-02-01, 1d
  Dry run            :done, m2, 2026-02-02, 2d
  section Cutover
  Freeze writes      :active, m3, 2026-02-04, 1d
  Replay backlog     :m4, 2026-02-05, 2d"""),
        ("Gantt Charts", "Multi Section Launch", """gantt
  dateFormat  YYYY-MM-DD
  title Multi section launch
  section Infra
  Provision nodes    :done, a1, 2026-03-01, 2d
  section App
  Build images       :active, a2, 2026-03-03, 3d
  Smoke tests        :a3, 2026-03-06, 2d
  section Launch
  Flip traffic       :a4, 2026-03-08, 1d"""),
        ("Pie Charts", "Language Share", """pie
  title Languages
  "Python" : 45
  "JavaScript" : 30
  "Java" : 15
  "C++" : 10"""),
        ("Pie Charts", "Traffic Split", """pie
  title Traffic split
  "Chat" : 52
  "Embeddings" : 18
  "Image" : 12
  "Admin" : 9
  "Other" : 9"""),
        ("Git Graphs", "Feature Merge", """gitGraph
  commit
  commit
  branch feature
  checkout feature
  commit
  commit
  checkout main
  merge feature
  commit"""),
        ("Git Graphs", "Hotfix Release", """gitGraph
  commit
  branch release
  checkout release
  commit
  checkout main
  branch hotfix
  checkout hotfix
  commit
  checkout main
  merge hotfix"""),
        ("Journey Maps", "User Onboarding", """journey
  title User onboarding
  section Discover
  Visit landing page: 4:
  Read docs: 3:
  section Activate
  Create API key: 5:
  Send first request: 5:"""),
        ("Journey Maps", "Incident Response", """journey
  title Incident response
  section Detect
  Notice alert: 3:
  section Respond
  Check dashboards: 4:
  Restart runtime: 2:
  section Recover
  Confirm stability: 5:"""),
        ("Mindmaps", "Product Strategy", """mindmap
root((Product strategy))
  Reliability
    Health checks
    Recovery plans
  Usability
    Admin panel
    Chat tooling
  Performance
    Throughput
    Startup time"""),
        ("Mindmaps", "Failure Analysis", """mindmap
root((Failure analysis))
  Inputs
    Prompt size
    Tool output
  Runtime
    KV cache
    GPU memory
  Output
    Latency
    Token rate"""),
        ("Timelines", "Release Milestones", """timeline
  title Release milestones
  2024: Initial control UI
  2025: Chat integration
  2026: Mermaid fixture lab"""),
        ("Timelines", "Migration Plan", """timeline
  title Migration plan
  Week 1: Inventory models
  Week 2: Build new configs
  Week 3: Run test fixture
  Week 4: Cut over traffic"""),
        ("Quadrant Charts", "Backlog Prioritization", """quadrantChart
  title Backlog prioritization
  x-axis Low effort --> High effort
  y-axis Low impact --> High impact
  quadrant-1 Strategic
  quadrant-2 Quick wins
  quadrant-3 Nice to have
  quadrant-4 Expensive bets
  Auth cleanup: [0.25, 0.82]
  New dashboard: [0.65, 0.74]
  Tool presets: [0.38, 0.44]
  Kernel tuning: [0.81, 0.52]"""),
        ("Quadrant Charts", "Model Tradeoffs", """quadrantChart
  title Model tradeoffs
  x-axis Cheap --> Expensive
  y-axis Weak quality --> Strong quality
  quadrant-1 Premium
  quadrant-2 Sweet spot
  quadrant-3 Budget
  quadrant-4 Specialized
  Small instruct: [0.18, 0.42]
  Mid coding: [0.46, 0.73]
  Large reasoning: [0.82, 0.91]
  Vision agent: [0.66, 0.64]"""),
        ("Flowcharts", "Support Decision Tree", """graph TD
  Ticket[Ticket] --> Scope{Scope known?}
  Scope -- Yes --> Owner[Assign owner]
  Scope -- No --> Ask[Ask clarifying questions]
  Ask --> Owner
  Owner --> Close[Close loop]"""),
        ("Sequence Diagrams", "Cache Warmup", """sequenceDiagram
  participant Scheduler
  participant Runtime
  participant Cache
  Scheduler->>Runtime: Start runtime
  Runtime->>Cache: Preload weights
  Cache->>Runtime: Warm cache
  Runtime->>Scheduler: Ready"""),
        ("Class Diagrams", "Storage Records", """classDiagram
  Record <|-- ConversationRecord
  Record <|-- ExportRecord
  Record : +timestamp
  class ConversationRecord{
    +messages
    +folder
  }
  class ExportRecord{
    +format
    +path
  }"""),
        ("State Diagrams", "Maintenance Window", """stateDiagram-v2
  [*] --> Idle
  Idle --> Draining
  Draining --> Offline
  Offline --> Recovering
  Recovering --> Idle
  Recovering --> Offline"""),
        ("Gantt Charts", "Patch Release", """gantt
  dateFormat  YYYY-MM-DD
  title Patch release
  section Validation
  Reproduce issue    :done, r1, 2026-04-01, 1d
  Fix renderer       :active, r2, 2026-04-02, 2d
  Verify DOM         :r3, 2026-04-04, 1d"""),
        ("Mindmaps", "Operator Checklist", """mindmap
root((Operator checklist))
  Services
    Proxy
    Admin
    Console
  Health
    GPU temp
    Disk space
  Recovery
    Restart
    Rollback"""),
    ]
    mermaid_lab_lines = [
        "# Mermaid Lab",
        "",
        "This seeded test-only conversation focuses exclusively on Mermaid coverage for the hand-rolled renderer.",
        "",
        f"Total Mermaid cases: {len(mermaid_lab_cases)}",
        "",
        "The cases below are intentionally practical and cover simple through moderately complex flows for every Mermaid family currently supported by the local parser.",
    ]
    current_mermaid_category = None
    for category, title, diagram in mermaid_lab_cases:
        if category != current_mermaid_category:
            mermaid_lab_lines.extend(["", f"## {category}"])
            current_mermaid_category = category
        mermaid_lab_lines.extend(["", f"### {title}", "", "```mermaid", diagram.strip(), "```"])
    mermaid_lab_showcase = "\n".join(mermaid_lab_lines).strip() + "\n"
    markdown_showcase_json = json.dumps(markdown_showcase, ensure_ascii=False).replace("</", "<\\/")
    mermaid_lab_showcase_json = json.dumps(mermaid_lab_showcase, ensure_ascii=False).replace("</", "<\\/")
    mermaid_lab_expected_counts_json = json.dumps(MERMAID_LAB_EXPECTED_COUNTS, ensure_ascii=False)
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
  const MERMAID_LAB_SHOWCASE = {mermaid_lab_showcase_json};
  const MERMAID_LAB_EXPECTED = {mermaid_lab_expected_counts_json};
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
    rows.forEach((runtime, index) => {{
      if (!runtime) return;
      runtime.id = 'fixture-' + (index === 0 ? 'a' : 'b');
      runtime.instance_id = runtime.id;
      runtime.selector = 'mode-' + (index === 0 ? 'a' : 'b');
      runtime.display_name = 'Fixture Runtime ' + (index === 0 ? 'A' : 'B');
      runtime.mode = runtime.selector;
      runtime.container = 'fixture-' + (index === 0 ? 'a' : 'b') + '-container';
      runtime.model_id = 'fixture-model-' + (index === 0 ? 'a' : 'b');
      runtime.served_model_name = runtime.model_id;
      runtime.gpu_indices = [index];
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
    }});
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
  function buildStreamResponse(text, reasoning = '', options = {{}}) {{
    const chunkSize = Math.max(24, Number(options.chunkSize || 72) || 72);
    const reasoningChunkSize = Math.max(12, Number(options.reasoningChunkSize || 40) || 40);
    const delayMs = Math.max(0, Number(options.delayMs || 5) || 0);
    const chunks = [];
    const pushEvent = (eventName, payload) => {{
      if (payload === null || payload === undefined || payload === '') return;
      chunks.push(
        new Uint8Array(
          Array.from(
            `event: ${{eventName}}\\ndata: ${{JSON.stringify(payload)}}\\n\\n`,
            (char) => char.charCodeAt(0),
          ),
        ),
      );
    }};
    const sliceText = (value, size) => {{
      const parts = [];
      const source = String(value || '');
      for (let index = 0; index < source.length; index += size) {{
        parts.push(source.slice(index, index + size));
      }}
      return parts;
    }};
    pushEvent('status', {{ message: 'Generating message...' }});
    sliceText(reasoning, reasoningChunkSize).forEach((part) =>
      pushEvent('reasoning', {{ text: part }}),
    );
    sliceText(text, chunkSize).forEach((part) =>
      pushEvent('delta', {{ text: part }}),
    );
    pushEvent('done', {{ message: '' }});
    return {{
      ok: true,
      status: 200,
      body: {{
        getReader() {{
          let index = 0;
          return {{
            async read() {{
              if (index >= chunks.length) return {{ value: undefined, done: true }};
              if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
              return {{ value: chunks[index++], done: false }};
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
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Club-3090 Local UI Lab');
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
        #club3090TestLab .lab-head {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
          margin: 0 0 8px;
          cursor: move;
          user-select: none;
        }}
        #club3090TestLab .lab-title {{
          margin: 0;
          font-size: 13px;
          font-weight: 800;
        }}
        #club3090TestLab .lab-head-actions {{
          display: flex;
          align-items: center;
          gap: 8px;
          flex: 0 0 auto;
        }}
        #club3090TestLab .lab-head-btn {{
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          padding: 0;
          border: 0;
          background: transparent;
          color: #9dafc3;
          cursor: pointer;
          border-radius: 0;
          box-shadow: none;
        }}
        #club3090TestLab .lab-head-btn:hover,
        #club3090TestLab .lab-head-btn:focus-visible {{
          color: #eef4ff;
          outline: none;
        }}
        #club3090TestLab .lab-head-btn svg {{
          width: 18px;
          height: 18px;
          stroke: currentColor;
          stroke-width: 2;
          stroke-linecap: round;
          stroke-linejoin: round;
          fill: none;
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
      <div class="lab-head" id="club3090LabDragHandle">
        <div class="lab-title">Club-3090 Local UI Lab</div>
        <div class="lab-head-actions">
          <button class="lab-head-btn" id="club3090LabDetach" type="button" title="Detach test lab" aria-label="Detach test lab">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M14 5h5v5m0-5-7 7" />
              <path d="M10 7H7a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-3" />
            </svg>
          </button>
        </div>
      </div>
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
    const snapshotLabState = () => ({{
      fixture: state.fixture,
      latencyMs: state.latencyMs,
      statusText: JSON.stringify(state.status, null, 2),
    }});
    const popupMarkup = () => {{
      const snap = snapshotLabState();
      return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Club-3090 Local UI Lab</title>
    <style>
      :root {{ color-scheme: dark; }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        padding: 12px;
        background: #0b0f14;
        color: #e8eef7;
        font: 12px/1.4 system-ui, -apple-system, Segoe UI, Arial, sans-serif;
      }}
      .lab-shell {{
        width: 100%;
        min-height: calc(100vh - 24px);
        padding: 12px;
        border: 1px solid #29405a;
        border-radius: 14px;
        background: rgba(9, 15, 24, 0.96);
        box-shadow: 0 18px 50px rgba(0, 0, 0, 0.42);
      }}
      .lab-head {{ display:flex; align-items:center; justify-content:space-between; gap:8px; margin:0 0 8px; }}
      .lab-title {{ margin:0; font-size:13px; font-weight:800; }}
      .lab-head-btn {{ display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; padding:0; border:0; background:transparent; color:#9dafc3; cursor:pointer; }}
      .lab-head-btn:hover, .lab-head-btn:focus-visible {{ color:#eef4ff; outline:none; }}
      .lab-head-btn svg {{ width:18px; height:18px; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; fill:none; }}
      .lab-grid {{ display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; }}
      label {{ display:flex; flex-direction:column; gap:4px; color:#9dafc3; }}
      select, button, textarea {{
        background:#081018;
        color:#eef4ff;
        border:1px solid #2c3a4f;
        border-radius:9px;
        padding:8px;
        font:inherit;
      }}
      select {{
        appearance:none;
        -webkit-appearance:none;
        background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='m6 9 6 6 6-6' fill='none' stroke='%239dafc3' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
        background-position:calc(100% - 14px) 50%;
        background-repeat:no-repeat;
        background-size:12px 12px;
        padding-right:32px;
      }}
      textarea {{ min-height:84px; resize:vertical; grid-column:1 / -1; }}
      .lab-actions {{ display:flex; gap:8px; margin-top:8px; }}
      .lab-note {{ margin-top:8px; color:#9dafc3; }}
    </style>
  </head>
  <body>
    <div class="lab-shell">
      <div class="lab-head">
        <div class="lab-title">Club-3090 Local UI Lab</div>
        <button class="lab-head-btn" id="club3090PopupAttach" type="button" title="Reattach test lab" aria-label="Reattach test lab">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M10 19H5v-5m0 5 7-7" />
            <path d="M14 17h3a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v3" />
          </svg>
        </button>
      </div>
      <div class="lab-grid">
        <label>Fixture
          <select id="club3090PopupFixtureSelect"></select>
        </label>
        <label>Latency (ms)
          <select id="club3090PopupLatencySelect">
            <option value="0">0</option>
            <option value="30">30</option>
            <option value="120">120</option>
            <option value="350">350</option>
          </select>
        </label>
        <label style="grid-column: 1 / -1;">Status Override (JSON)
          <textarea id="club3090PopupFixtureEditor" spellcheck="false"></textarea>
        </label>
      </div>
      <div class="lab-actions">
        <button id="club3090PopupFixtureApply" type="button">Apply JSON</button>
        <button id="club3090PopupFixtureReset" type="button">Reset Fixture</button>
        <button id="club3090PopupOpenChat" type="button">Open Chat</button>
      </div>
      <div class="lab-note">This file mocks the admin API locally so you can switch tabs, open modals, test chat UI, and spot layout regressions on Windows.</div>
    </div>
    <script>
      (() => {{
        const api = window.opener && window.opener.__club3090TestLab;
        if (!api) return;
        const fixtureSelect = document.getElementById('club3090PopupFixtureSelect');
        const latencySelect = document.getElementById('club3090PopupLatencySelect');
        const editor = document.getElementById('club3090PopupFixtureEditor');
        const sync = () => {{
          const snap = api.getSnapshot();
          fixtureSelect.innerHTML = api.fixtureNames().map((name) => '<option value="' + name + '" ' + (name === snap.fixture ? 'selected' : '') + '>' + name + '</option>').join('');
          fixtureSelect.value = snap.fixture;
          latencySelect.value = String(snap.latencyMs);
          editor.value = snap.statusText;
        }};
        fixtureSelect.addEventListener('change', async () => {{
          api.setFixture(fixtureSelect.value);
          sync();
          await api.refresh();
        }});
        latencySelect.addEventListener('change', () => {{
          api.setLatency(latencySelect.value);
        }});
        document.getElementById('club3090PopupFixtureApply').addEventListener('click', async () => {{
          try {{
            api.applyStatusText(editor.value || '{{}}');
            await api.refresh();
          }} catch (error) {{
            window.alert('Invalid JSON override: ' + String(error));
          }}
        }});
        document.getElementById('club3090PopupFixtureReset').addEventListener('click', async () => {{
          api.setFixture(fixtureSelect.value);
          sync();
          await api.refresh();
        }});
        document.getElementById('club3090PopupOpenChat').addEventListener('click', () => {{
          if (typeof api.openChat === 'function') api.openChat();
        }});
        document.getElementById('club3090PopupAttach').addEventListener('click', () => {{
          if (typeof api.reattach === 'function') api.reattach();
          window.close();
        }});
        window.addEventListener('beforeunload', () => {{
          if (typeof api.popupClosed === 'function') api.popupClosed();
        }});
        sync();
      }})();
    <\\/script>
  </body>
</html>`;
    }};
    let detachedLabWindow = null;
    const fixtureSelect = panel.querySelector('#club3090FixtureSelect');
    const latencySelect = panel.querySelector('#club3090LatencySelect');
    const editor = panel.querySelector('#club3090FixtureEditor');
    const refreshEditor = () => {{
      editor.value = JSON.stringify(state.status, null, 2);
    }};
    const syncMainControls = () => {{
      fixtureSelect.innerHTML = fixtureNames()
        .map((name) => `<option value="${{name}}" ${{name === state.fixture ? 'selected' : ''}}>${{name}}</option>`)
        .join('');
      fixtureSelect.value = state.fixture;
      latencySelect.value = String(state.latencyMs);
      refreshEditor();
    }};
    const syncDetachedWindow = () => {{
      if (!detachedLabWindow || detachedLabWindow.closed) return;
      try {{
        detachedLabWindow.document.open();
        detachedLabWindow.document.write(popupMarkup());
        detachedLabWindow.document.close();
      }} catch (error) {{}}
    }};
    const reattachLab = () => {{
      panel.style.display = '';
      if (detachedLabWindow && !detachedLabWindow.closed) {{
        try {{
          detachedLabWindow.close();
        }} catch (error) {{}}
      }}
      detachedLabWindow = null;
    }};
    const popupClosed = () => {{
      detachedLabWindow = null;
      panel.style.display = '';
    }};
    const detachLab = () => {{
      try {{
        detachedLabWindow = window.open('', 'club3090-test-lab', 'popup=yes,width=420,height=520,resizable=yes,scrollbars=yes');
      }} catch (error) {{
        detachedLabWindow = null;
      }}
      if (!detachedLabWindow) return;
      panel.style.display = 'none';
      syncDetachedWindow();
    }};
    const dragHandle = panel.querySelector('#club3090LabDragHandle');
    let dragSession = null;
    const finishDrag = () => {{
      dragSession = null;
      document.body.classList.remove('resize-active');
    }};
    const moveDrag = (event) => {{
      if (!dragSession) return;
      const nextLeft = Math.max(8, dragSession.startLeft + (Number(event.clientX || 0) - dragSession.startX));
      const nextTop = Math.max(8, dragSession.startTop + (Number(event.clientY || 0) - dragSession.startY));
      panel.style.left = `${{Math.round(nextLeft)}}px`;
      panel.style.top = `${{Math.round(nextTop)}}px`;
      panel.style.right = 'auto';
      panel.style.bottom = 'auto';
    }};
    dragHandle.addEventListener('pointerdown', (event) => {{
      if (event.target && typeof event.target.closest === 'function' && event.target.closest('button, select, textarea, input, label')) return;
      dragSession = {{
        startX: Number(event.clientX || 0),
        startY: Number(event.clientY || 0),
        startLeft: panel.getBoundingClientRect().left,
        startTop: panel.getBoundingClientRect().top,
      }};
      dragHandle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    }});
    window.addEventListener('pointermove', moveDrag);
    window.addEventListener('pointerup', finishDrag);
    window.addEventListener('pointercancel', finishDrag);
    panel.querySelector('#club3090LabDetach').addEventListener('click', detachLab);
    fixtureSelect.addEventListener('change', async () => {{
      setFixture(fixtureSelect.value);
      syncMainControls();
      syncDetachedWindow();
      if (typeof window.refreshStatus === 'function') await window.refreshStatus({{ force: true }});
    }});
    latencySelect.addEventListener('change', () => {{
      state.latencyMs = Math.max(0, Number(latencySelect.value || 0) || 0);
      syncDetachedWindow();
    }});
    panel.querySelector('#club3090FixtureApply').addEventListener('click', async () => {{
      try {{
        state.status = JSON.parse(editor.value || '{{}}');
        syncDetachedWindow();
        if (typeof window.refreshStatus === 'function') await window.refreshStatus({{ force: true }});
      }} catch (error) {{
        window.alert('Invalid JSON override: ' + String(error));
      }}
    }});
    panel.querySelector('#club3090FixtureReset').addEventListener('click', async () => {{
      setFixture(fixtureSelect.value);
      syncMainControls();
      syncDetachedWindow();
      if (typeof window.refreshStatus === 'function') await window.refreshStatus({{ force: true }});
    }});
    panel.querySelector('#club3090OpenChat').addEventListener('click', () => {{
      if (typeof window.openChatTab === 'function') window.openChatTab();
    }});
    syncMainControls();
    window.__club3090TestLab = {{
      get fixture() {{ return state.fixture; }},
      get status() {{ return currentStatus(); }},
      setFixture,
      fixtureNames,
      getSnapshot: snapshotLabState,
      setLatency(value) {{
        state.latencyMs = Math.max(0, Number(value || 0) || 0);
      }},
      applyStatusText(text) {{
        state.status = JSON.parse(text || '{{}}');
      }},
      refresh: async () => {{
        if (typeof window.refreshStatus === 'function') await window.refreshStatus({{ force: true }});
      }},
      openChat() {{
        if (typeof window.openChatTab === 'function') window.openChatTab();
      }},
      reattach: reattachLab,
      popupClosed,
    }};
  }}
  const originalFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = async (url, options = {{}}) => {{
    const requestUrl = String(url || '');
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    await wait(state.latencyMs);
    if (requestUrl.startsWith('/admin/status')) {{
      return responseFrom(currentStatus());
    }}
    if (requestUrl.startsWith('/admin/code-syntax')) {{
      return responseFrom(JSON.parse({code_syntax_payload}));
    }}
    if (requestUrl === '/admin/chat-stream') {{
      const runtime = inferRuntime(state.status) || {{}};
      const runtimeLabel = runtime.display_name || runtime.id || runtime.instance_id || 'mock runtime';
      return buildStreamResponse(
        `# Test HTML response from ${{runtimeLabel}}\\n\\n${{MARKDOWN_SHOWCASE}}\\n\\n## Streaming Stress\\n\\n- Fibonacci in Python\\n- Fibonacci in Rust\\n- Fibonacci in Go\\n\\n\\`\\`\\`python\\ndef fib(n):\\n    a, b = 0, 1\\n    values = []\\n    for _ in range(n):\\n        values.append(a)\\n        a, b = b, a + b\\n    return values\\n\\`\\`\\`\\n\\n| Runtime | Status |\\n| --- | --- |\\n| mock | streaming |\\n| markdown | preserved |`,
        'Mock reasoning stream. Planning a long markdown response and streaming it in many small chunks so the transcript path is exercised under load.',
        {{ chunkSize: 48, reasoningChunkSize: 28, delayMs: 6 }},
      );
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
              id: 'mermaid-lab',
              title: 'Mermaid Lab',
              folder: 'Test HTML',
              updatedAt: 1710000000500,
              lastUsedAt: 1710000000500,
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
      if (conversationId === 'mermaid-lab') await wait(20);
      const detailMap = {{
        'markdown-showcase': {{
          id: 'markdown-showcase',
          title: 'Markdown Showcase',
          folder: 'Test HTML',
          presetId: 'fixture-a::mode-a',
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
          lastInputTokens: 111,
          lastOutputTokens: 222,
          lastTotalTokens: 333,
          lastPromptTokensPerSecond: 44.4,
          lastTokensPerSecond: 55.5,
          lastTokensPerSecondPeak: 66.6,
          lastLatencySeconds: 0.777,
          lastTtftSeconds: 0.123,
          lastToolCalls: 1,
          lastStatus: 200,
          lastRequestPath: '/admin/chat-stream',
          lastRuntimeRequestAt: 1710000002000,
          runtimeSnapshot: {{
            id: 'fixture-a',
            instance_id: 'fixture-a',
            selector: 'mode-a',
            mode: 'mode-a',
            display_name: 'Fixture Runtime A',
            container: 'fixture-a-container',
            served_model_name: 'fixture-model-a',
            model_id: 'fixture-model-a',
            gpu_indices: [0],
            port: 8101,
          }},
          statsCollapsed: false,
          messagesLoaded: true,
        }},
        'mermaid-lab': {{
          id: 'mermaid-lab',
          title: 'Mermaid Lab',
          folder: 'Test HTML',
          presetId: 'fixture-a::mode-a',
          apiPresetName: '',
          messages: [
            {{
              role: 'user',
              text: 'Render a Mermaid-only lab that exercises every supported diagram family from simple to practical examples.',
            }},
            {{
              role: 'assistant',
              text: MERMAID_LAB_SHOWCASE,
              reasoningText: 'This fixture focuses exclusively on Mermaid markdown so the lightweight renderer can be verified aggressively before shipping.',
              thinkingDurationMs: 1680,
              thinkingDone: true,
              thinkingExpanded: false,
              modelLabel: 'Test HTML fixture',
            }},
          ],
          attachments: [],
          params: {{}},
          systemPrompt: '',
          lastInputTokens: 444,
          lastOutputTokens: 888,
          lastTotalTokens: 1332,
          lastPromptTokensPerSecond: 52.1,
          lastTokensPerSecond: 61.3,
          lastTokensPerSecondPeak: 74.2,
          lastLatencySeconds: 0.931,
          lastTtftSeconds: 0.155,
          lastToolCalls: 0,
          lastStatus: 200,
          lastRequestPath: '/admin/chat-stream',
          lastRuntimeRequestAt: 1710000002500,
          runtimeSnapshot: {{
            id: 'fixture-a',
            instance_id: 'fixture-a',
            selector: 'mode-a',
            mode: 'mode-a',
            display_name: 'Fixture Runtime A',
            container: 'fixture-a-container',
            served_model_name: 'fixture-model-a',
            model_id: 'fixture-model-a',
            gpu_indices: [0],
            port: 8101,
          }},
          statsCollapsed: false,
          messagesLoaded: true,
        }},
        'vision-test': {{
          id: 'vision-test',
          title: 'Vision Test',
          folder: 'Test HTML',
          presetId: 'fixture-b::mode-b',
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
          lastInputTokens: 9,
          lastOutputTokens: 8,
          lastTotalTokens: 17,
          lastPromptTokensPerSecond: 7.7,
          lastTokensPerSecond: 6.6,
          lastTokensPerSecondPeak: 9.9,
          lastLatencySeconds: 1.234,
          lastTtftSeconds: 0.456,
          lastToolCalls: 0,
          lastStatus: 201,
          lastRequestPath: '/admin/chat-stream',
          lastRuntimeRequestAt: 1710000003000,
          runtimeSnapshot: {{
            id: 'fixture-b',
            instance_id: 'fixture-b',
            selector: 'mode-b',
            mode: 'mode-b',
            display_name: 'Fixture Runtime B',
            container: 'fixture-b-container',
            served_model_name: 'fixture-model-b',
            model_id: 'fixture-model-b',
            gpu_indices: [1],
            port: 8102,
          }},
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
    if (requestUrl.startsWith('/admin/')) {{
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


def build_test_html(
    html_source: str,
    css_source: str,
    js_source: str,
    fixtures: list[tuple[str, dict]],
    script_version: str,
) -> str:
    bootstrap = test_html_bootstrap(fixtures, load_embedded_code_syntax_json())
    bundled = inject_assets_into_html(html_source, css_source, bootstrap + "\n" + js_source)
    return bundled.replace("__SCRIPT_VERSION__", str(script_version or "").strip())


def generate_test_html_artifact() -> tuple[str, str]:
    html_source = read_text(WEB_BASE_HTML_PATH)
    css_source = read_text(WEB_BASE_CSS_PATH)
    js_source = compose_web_js_source()
    metadata = load_build_metadata_inputs()
    change_log_latest_text = metadata["change_log_latest"]
    change_log_icons_text = metadata["change_log_icons"]
    club3090_version_text = metadata["club3090_version"]
    script_source = inject_script_metadata(
        read_text(SCRIPT_SOURCE_PATH),
        script_version=metadata["script_version"],
        change_log_latest=change_log_latest_text,
        change_log_icons_json=change_log_icons_text,
        club3090_version_json=club3090_version_text,
    )
    fixtures = load_status_fixtures()
    metadata_issues = validate_script_metadata(
        script_source,
        expected_version=metadata["version"],
        expected_script_version=metadata["script_version"],
        expected_change_log_latest=change_log_latest_text,
        expected_change_log_icons=change_log_icons_text,
        expected_club3090_version=club3090_version_text,
    )
    if metadata_issues:
        raise ValueError("; ".join(metadata_issues))
    if "/* injected by build.py from web-ui.css */" not in html_source or "// injected by build.py from web-ui.js" not in html_source:
        raise ValueError("web-ui.html is missing CSS/JS build placeholders")
    test_html = build_test_html(
        html_source,
        css_source,
        js_source,
        fixtures,
        metadata["script_version"],
    )
    write_text(TEST_HTML_PATH, test_html)
    with tempfile.TemporaryDirectory(prefix="club3090-test-html-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        shipped_ok, shipped_detail = validate_js_with_node(js_source, temp_dir, "web-ui.test-html.check.js")
        if not shipped_ok:
            raise ValueError(shipped_detail or "node --check failed")
        ok, detail = run_test_html_smoke_test(test_html, temp_dir, "web-ui.test-html.smoke.cjs")
        if not ok:
            raise ValueError(detail or "test HTML smoke test failed")
        service_ok, service_detail = run_ui_service_actions_smoke_test(
            js_source,
            temp_dir,
            "web-ui.test-html.service-actions.smoke.cjs",
        )
        if not service_ok:
            raise ValueError(service_detail or "UI service action smoke test failed")
        compile(read_text(BUILD_DIR / "build.py"), str(BUILD_DIR / "build.py"), "exec")
    return test_html, detail or service_detail or "test html smoke ok"


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
    code_syntax_payload = json.dumps(load_embedded_code_syntax_json(), ensure_ascii=False)
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
      window.fetch = async (url) => {{
        if (String(url).startsWith("/admin/code-syntax")) {{
          return {{
            ok: true,
            status: 200,
            async json() {{ return JSON.parse({code_syntax_payload}); }},
            async text() {{ return {code_syntax_payload}; }},
          }};
        }}
        return {{
          ok: true,
          status: 200,
          async json() {{ return {{ ok: true }}; }},
          async text() {{ return "{{\\"ok\\":true}}"; }},
        }};
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
  const chatAutoscrollToggle = window.document.getElementById("chatAutoscroll");
  if (!chatAutoscrollToggle || !chatAutoscrollToggle.checked) {{
    throw new Error("chat transcript auto-scroll toggle should render and default to enabled");
  }}
  if (!transcriptAfterSwitch.classList.contains("chat-transcript-autofollow")) {{
    throw new Error("chat transcript should enable CSS auto-follow while the toggle is on");
  }}
  if (!transcriptAfterSwitch.querySelector(".chat-transcript-anchor")) {{
    throw new Error("chat transcript bottom anchor missing");
  }}
  const priorFetchForRecoveredStop = window.fetch;
  let recoveredStopBody = null;
  window.fetch = async (url, options = {{}}) => {{
    if (url === "/admin/chat-stop") {{
      recoveredStopBody = JSON.parse(String(options.body || "{{}}"));
      return {{
        ok: true,
        json: async () => ({{ ok: true, stream: {{ status: "aborted" }} }}),
      }};
    }}
    return priorFetchForRecoveredStop(url, options);
  }};
  const recoveredConversation = window.activeChatConversation?.();
  if (!recoveredConversation?.id) {{
    throw new Error("active chat conversation missing before recovered stop test");
  }}
  recoveredConversation.generationActive = true;
  window.stopChatGeneration();
  await new Promise((resolve) => setTimeout(resolve, 30));
  window.fetch = priorFetchForRecoveredStop;
  recoveredConversation.generationActive = false;
  if (!recoveredStopBody || recoveredStopBody.conversation_id !== recoveredConversation.id) {{
    throw new Error("recovered stop should call /admin/chat-stop with the active conversation id");
  }}
  chatAutoscrollToggle.click();
  await new Promise((resolve) => setTimeout(resolve, 30));
  if (transcriptAfterSwitch.classList.contains("chat-transcript-autofollow")) {{
    throw new Error("chat transcript CSS auto-follow class should clear when disabled");
  }}
  chatAutoscrollToggle.click();
  await new Promise((resolve) => setTimeout(resolve, 30));
  if (!transcriptAfterSwitch.classList.contains("chat-transcript-autofollow")) {{
    throw new Error("chat transcript CSS auto-follow class should restore when re-enabled");
  }}
  const lastShowcaseTurn = Array.from(transcriptAfterSwitch.querySelectorAll(".chat-turn")).pop();
  const showcaseBody = lastShowcaseTurn?.querySelector(".chat-message.chat-assistant .chat-message-body");
  if (!showcaseBody) {{
    throw new Error("markdown showcase message body did not render");
  }}
  if (typeof window.loadCodeSyntaxConfig === "function") {{
    await window.loadCodeSyntaxConfig({{ force: true }});
  }}
  if (typeof window.highlightCodeElement === "function") {{
    const transcriptCodeNodes = Array.from(showcaseBody.querySelectorAll("pre.chat-code code"));
    await Promise.all(transcriptCodeNodes.map((node) => window.highlightCodeElement(node)));
  }}
  const domExpectations = [
    [showcaseBody.querySelectorAll("h1, h2, h3").length >= 6, "expected multiple rendered headings"],
    [showcaseBody.querySelectorAll("blockquote").length >= 3, "expected rendered blockquotes"],
    [showcaseBody.querySelectorAll("details").length >= 2, "expected rendered details blocks"],
    [showcaseBody.querySelectorAll("table").length >= 2, "expected rendered tables"],
    [showcaseBody.querySelectorAll("pre code").length >= 4, "expected multiple fenced code blocks"],
    [showcaseBody.querySelectorAll(".chat-mermaid-block").length >= 6, "expected mermaid showcase blocks"],
    [showcaseBody.querySelectorAll(".chat-broken-media-note, img[alt='broken fixture image']").length >= 1, "expected broken image media fixture"],
    [showcaseBody.querySelectorAll(".chat-math, .chat-math-block").length >= 6, "expected inline and block math rendering"],
    [/Deployment checklist/.test(showcaseBody.textContent || ""), "expected expanded practical fixture copy"],
    [/this should render as text, not DOM/.test(showcaseBody.textContent || ""), "expected escaped raw HTML text"],
  ];
  for (const [passed, message] of domExpectations) {{
    if (!passed) throw new Error(message);
  }}
  let highlightedCode = showcaseBody.querySelector("pre.chat-code code .chat-syntax-token");
  for (let attempt = 0; attempt < 20 && !highlightedCode; attempt += 1) {{
    await new Promise((resolve) => setTimeout(resolve, 40));
    highlightedCode = showcaseBody.querySelector("pre.chat-code code .chat-syntax-token");
  }}
  if (!highlightedCode) {{
    throw new Error("expected asynchronous syntax highlighting tokens inside fenced code blocks");
  }}
  const renderedHtmlBlock = Array.from(showcaseBody.querySelectorAll("pre.chat-code code")).find((node) =>
    /<!DOCTYPE html>/.test(node.textContent || '')
  );
  if (!renderedHtmlBlock) {{
    throw new Error("expected rendered HTML code block fixture");
  }}
  if (!/<!DOCTYPE html>/.test(renderedHtmlBlock.textContent || '') || /&lt;|&gt;/.test(renderedHtmlBlock.textContent || '')) {{
    throw new Error("rendered HTML code block should show literal angle brackets instead of escaped entities");
  }}
  if (/&amp;lt;|&amp;gt;/.test(renderedHtmlBlock.innerHTML || '')) {{
    throw new Error("rendered HTML code block contains double-escaped angle bracket entities");
  }}
  const syntaxProbe = window.document.createElement("code");
  syntaxProbe.innerHTML = window.renderSyntaxHighlightedHtml('int main() {{ std::cout << 1 << \" x\"; }}', 'cpp', await window.loadCodeSyntaxConfig());
  if (!/std::cout << 1 << \" x\";/.test(syntaxProbe.textContent || '')) {{
    throw new Error("syntax highlighter escaped plain code characters instead of rendering them literally");
  }}
  if (syntaxProbe.querySelectorAll('.chat-syntax-operator').length < 2 || syntaxProbe.querySelectorAll('.chat-syntax-separator').length < 4) {{
    throw new Error("c-style syntax highlighting did not mark expected operators and marker characters");
  }}
  const pythonProbe = window.document.createElement("code");
  pythonProbe.innerHTML = window.renderSyntaxHighlightedHtml('value = arr[i] + delta * 2 if flag and not done else 0', 'python', await window.loadCodeSyntaxConfig());
  if (pythonProbe.querySelectorAll('.chat-syntax-operator').length < 3 || pythonProbe.querySelectorAll('.chat-syntax-separator').length < 2) {{
    throw new Error("python syntax highlighting did not mark expected operators and marker characters");
  }}
  const pascalProbe = window.document.createElement("code");
  pascalProbe.innerHTML = window.renderSyntaxHighlightedHtml('if (a + b) * c >= 10 then result := items[i] <> 0;', 'pascal', await window.loadCodeSyntaxConfig());
  if (pascalProbe.querySelectorAll('.chat-syntax-operator').length < 5 || pascalProbe.querySelectorAll('.chat-syntax-separator').length < 5) {{
    throw new Error("pascal/basic syntax highlighting did not mark expected operators and marker characters");
  }}
  const sqlProbe = window.document.createElement("code");
  sqlProbe.innerHTML = window.renderSyntaxHighlightedHtml('SELECT id, name FROM users WHERE id >= 10 AND active = true;', 'sql', await window.loadCodeSyntaxConfig());
  if (sqlProbe.querySelectorAll('.chat-syntax-keyword').length < 4) {{
    throw new Error("sql syntax highlighting did not mark expected keywords");
  }}
  if (sqlProbe.querySelectorAll('.chat-syntax-operator').length < 2) {{
    throw new Error("sql syntax highlighting did not mark expected operators");
  }}
  const jsProbe = window.document.createElement("code");
  jsProbe.innerHTML = window.renderSyntaxHighlightedHtml('const answer = /ab+c/i.test(\"abc\") && Math.max(1, 2);', 'javascript', await window.loadCodeSyntaxConfig());
  if (jsProbe.querySelectorAll('.chat-syntax-regex').length < 1) {{
    throw new Error("javascript syntax highlighting did not mark regex literals");
  }}
  if (jsProbe.querySelectorAll('.chat-syntax-builtin, .chat-syntax-function').length < 2) {{
    throw new Error("javascript syntax highlighting did not mark builtins or function calls");
  }}
  const cssProbe = window.document.createElement("code");
  cssProbe.innerHTML = window.renderSyntaxHighlightedHtml('.card:hover {{ color: #fff; transform: translateX(2px); }}', 'css', await window.loadCodeSyntaxConfig());
  if (cssProbe.querySelectorAll('.chat-syntax-selector').length < 1 || cssProbe.querySelectorAll('.chat-syntax-property').length < 2) {{
    throw new Error("css syntax highlighting did not mark selectors and properties");
  }}
  if (cssProbe.querySelectorAll('.chat-syntax-constant, .chat-syntax-unit').length < 2) {{
    throw new Error("css syntax highlighting did not mark color or unit tokens");
  }}
  const markupConfig = await window.loadCodeSyntaxConfig();
  const rootSyntaxTag = String(window.document.documentElement.style.getPropertyValue('--chat-syntax-tag') || '').trim().toLowerCase();
  const rootSyntaxKeyword = String(window.document.documentElement.style.getPropertyValue('--chat-syntax-keyword') || '').trim().toLowerCase();
  const rootSyntaxOperator = String(window.document.documentElement.style.getPropertyValue('--chat-syntax-operator') || '').trim().toLowerCase();
  if (rootSyntaxTag !== String(markupConfig?.theme?.tokens?.tag || '').trim().toLowerCase()) {{
    throw new Error("applied syntax tag CSS variable does not match the loaded code_syntax theme");
  }}
  if (rootSyntaxKeyword !== String(markupConfig?.theme?.tokens?.keyword || '').trim().toLowerCase()) {{
    throw new Error("applied syntax keyword CSS variable does not match the loaded code_syntax theme");
  }}
  if (rootSyntaxOperator !== String(markupConfig?.theme?.tokens?.operator || '').trim().toLowerCase()) {{
    throw new Error("applied syntax operator CSS variable does not match the loaded code_syntax theme");
  }}
  window.applyCodeSyntaxTheme({{ theme: {{ tokens: {{ tag: '#123456', keyword: '#abcdef', operator: '#654321' }} }} }});
  if (String(window.document.documentElement.style.getPropertyValue('--chat-syntax-tag') || '').trim().toLowerCase() !== '#123456') {{
    throw new Error("syntax theme reapply did not update the tag CSS variable");
  }}
  if (String(window.document.documentElement.style.getPropertyValue('--chat-syntax-keyword') || '').trim().toLowerCase() !== '#abcdef') {{
    throw new Error("syntax theme reapply did not update the keyword CSS variable");
  }}
  if (String(window.document.documentElement.style.getPropertyValue('--chat-syntax-operator') || '').trim().toLowerCase() !== '#654321') {{
    throw new Error("syntax theme reapply did not update the operator CSS variable");
  }}
  window.applyCodeSyntaxTheme({{ theme: {{ tokens: {{ keyword: '#fedcba' }} }} }});
  if (String(window.document.documentElement.style.getPropertyValue('--chat-syntax-tag') || '').trim()) {{
    throw new Error("syntax theme reapply should clear stale CSS variables for removed tokens");
  }}
  if (String(window.document.documentElement.style.getPropertyValue('--chat-syntax-operator') || '').trim()) {{
    throw new Error("syntax theme reapply should clear stale operator CSS variables for removed tokens");
  }}
  if (String(window.document.documentElement.style.getPropertyValue('--chat-syntax-keyword') || '').trim().toLowerCase() !== '#fedcba') {{
    throw new Error("syntax theme reapply should keep updated CSS variables for surviving tokens");
  }}
  window.applyCodeSyntaxTheme(markupConfig);
  const syntaxConfigA = JSON.parse(JSON.stringify(markupConfig || {{}}));
  syntaxConfigA.theme = syntaxConfigA.theme || {{}};
  syntaxConfigA.theme.tokens = {{
    ...(syntaxConfigA.theme.tokens || {{}}),
    keyword: '#111213',
  }};
  syntaxConfigA.families = syntaxConfigA.families || {{}};
  syntaxConfigA.families.javascript = syntaxConfigA.families.javascript || {{}};
  syntaxConfigA.families.javascript.keywords = Array.from(
    new Set([...(syntaxConfigA.families.javascript.keywords || []), 'const']),
  );
  const syntaxConfigB = JSON.parse(JSON.stringify(syntaxConfigA));
  syntaxConfigB.theme.tokens.keyword = '#212223';
  syntaxConfigB.families.javascript.keywords = (syntaxConfigB.families.javascript.keywords || []).filter(
    (token) => token !== 'const',
  );
  const priorFetchForSyntaxReload = window.fetch;
  let syntaxReloadFetchCount = 0;
  window.fetch = async (...fetchArgs) => {{
    const [resource] = fetchArgs;
    if (String(resource || '').includes('/admin/code-syntax')) {{
      const payload = syntaxReloadFetchCount === 0 ? syntaxConfigA : syntaxConfigB;
      syntaxReloadFetchCount += 1;
      return {{
        ok: true,
        json: async () => JSON.parse(JSON.stringify(payload)),
      }};
    }}
    return priorFetchForSyntaxReload(...fetchArgs);
  }};
  try {{
    await window.loadCodeSyntaxConfig({{ force: true }});
    const retroSyntaxHost = window.document.createElement('div');
    retroSyntaxHost.innerHTML = '<pre class="chat-code"><code data-code-block="1" data-code-lang="javascript">const answer = 1;</code></pre>';
    window.document.body.appendChild(retroSyntaxHost);
    const retroSyntaxNode = retroSyntaxHost.querySelector('code');
    await window.highlightCodeElement(retroSyntaxNode);
    if (retroSyntaxNode.querySelectorAll('.chat-syntax-keyword').length < 1) {{
      throw new Error("initial syntax reload fixture did not highlight javascript keywords");
    }}
    if (String(window.document.documentElement.style.getPropertyValue('--chat-syntax-keyword') || '').trim().toLowerCase() !== '#111213') {{
      throw new Error("forced code_syntax reload did not apply the fetched keyword color");
    }}
    await window.loadCodeSyntaxConfig({{ force: true }});
    await new Promise((resolve) => setTimeout(resolve, 120));
    if (retroSyntaxNode.querySelectorAll('.chat-syntax-keyword').length !== 0) {{
      throw new Error("existing highlighted code block did not rerender after code_syntax keyword changes");
    }}
    if (String(window.document.documentElement.style.getPropertyValue('--chat-syntax-keyword') || '').trim().toLowerCase() !== '#212223') {{
      throw new Error("second code_syntax reload did not update the fetched keyword color");
    }}
    retroSyntaxHost.remove();
  }} finally {{
    window.fetch = priorFetchForSyntaxReload;
    await window.loadCodeSyntaxConfig({{ force: true }});
  }}
  const streamingMarkdownHtml = String(
    window.renderChatMessageMarkdownHtml(
      {{ role: 'assistant', __streamingMarkdownState: null }},
      '**bold** and `code` still streaming',
      {{ streaming: true }},
    ) || '',
  );
  if (!/chat-live-preview/.test(streamingMarkdownHtml)) {{
    throw new Error("streaming markdown should render through the live preview lane while a reply is still open");
  }}
  const finalizedMarkdownHtml = String(
    window.renderChatMessageMarkdownHtml(
      {{ role: 'assistant' }},
      '**bold** and `code` finished',
      {{ streaming: false }},
    ) || '',
  );
  if (!/<strong>bold<\\/strong>/.test(finalizedMarkdownHtml) || !/<code>code<\\/code>/.test(finalizedMarkdownHtml)) {{
    throw new Error("finalized markdown should still render through the full markdown formatter");
  }}
  const latencyConversation = window.createChatConversation({{
    id: 'latency-check',
    title: 'Latency Check',
    messages: [{{ role: 'user', text: 'hi' }}, {{ role: 'assistant', text: 'hello', modelLabel: 'Fixture Runtime A' }}],
    runtimeSnapshot: {{}},
    messagesLoaded: true,
  }});
  window.updateConversationRuntimeMetrics(
    latencyConversation,
    latencyConversation.runtimeSnapshot,
    {{
      usage: {{ input_tokens: 4, output_tokens: 2, tokens: 6 }},
      ttft_s: 0.245,
      generation_tps: 18.5,
      status: 200,
      path: '/admin/chat-stream',
    }},
    {{ streaming: true, persist: false }},
  );
  if (latencyConversation.lastLatencySeconds !== undefined) {{
    throw new Error("streaming chat metrics should not publish a made-up latency before the request finishes");
  }}
  if (latencyConversation.lastTtftSeconds !== 0.245) {{
    throw new Error("streaming chat metrics should still surface TTFT while the reply is in progress");
  }}
  window.updateConversationRuntimeMetrics(
    latencyConversation,
    latencyConversation.runtimeSnapshot,
    {{
      usage: {{ input_tokens: 4, output_tokens: 2, tokens: 6 }},
      ttft_s: 0.245,
      latency_s: 1.337,
      generation_tps: 18.5,
      status: 200,
      path: '/admin/chat-stream',
    }},
    {{ streaming: false, persist: false }},
  );
  if (latencyConversation.lastLatencySeconds !== 1.337) {{
    throw new Error("completed chat metrics should publish the final end-to-end latency");
  }}
  const userMeta = String(window.renderChatMessageMeta({{ role: 'user', inputTokensEstimate: 5, inputTokensApprox: true }}) || '');
  if (!/input: 5 tokens/.test(userMeta) || /~input/.test(userMeta)) {{
    throw new Error("user chat message meta should use colon labels without the approximate tilde prefix");
  }}
  const assistantMeta = String(window.renderChatMessageMeta({{ role: 'assistant', outputTokens: 169, ttftSeconds: 0.364, tokensPerSecond: 77.87 }}) || '');
  if (!/output: 169 tokens/.test(assistantMeta) || !/TTFT: 0.364s/.test(assistantMeta) || !/tk\\/s: 77.87/.test(assistantMeta)) {{
    throw new Error("assistant chat message meta should use colon labels for output, TTFT, and throughput");
  }}
  const markupProbe = window.document.createElement("code");
  markupProbe.innerHTML = window.renderSyntaxHighlightedHtml('<!DOCTYPE html>\\n<div class=\"card\" data-id=\"1\">ok</div>', 'html', markupConfig);
  if (!/<!DOCTYPE html>\\s*<div class=\"card\" data-id=\"1\">ok<\\/div>/.test(markupProbe.textContent || '')) {{
    throw new Error("markup syntax highlighting should preserve literal markup characters in rendered text");
  }}
  if (/&lt;|&gt;/.test(markupProbe.textContent || '') || /&amp;lt;|&amp;gt;/.test(markupProbe.innerHTML || '')) {{
    throw new Error("markup syntax highlighting should not surface escaped angle bracket entities");
  }}
  if (markupProbe.querySelectorAll('.chat-syntax-tag').length < 2 || markupProbe.querySelectorAll('.chat-syntax-attribute').length < 2) {{
    throw new Error("markup syntax highlighting did not mark tags and attributes");
  }}
  if (String(markupConfig?.theme?.tokens?.tag || '').toLowerCase() === String(markupConfig?.theme?.foreground || '').toLowerCase()) {{
    throw new Error("markup syntax theme should give tags a distinct color from plain code text");
  }}
  if (String(markupConfig?.theme?.tokens?.attribute || '').toLowerCase() === String(markupConfig?.theme?.foreground || '').toLowerCase()) {{
    throw new Error("markup syntax theme should give attributes a distinct color from plain code text");
  }}
  const psProbe = window.document.createElement("code");
  psProbe.innerHTML = window.renderSyntaxHighlightedHtml('Get-ChildItem $env:TEMP | Where-Object {{ $_.Length -gt 10 }}', 'powershell', await window.loadCodeSyntaxConfig());
  if (psProbe.querySelectorAll('.chat-syntax-builtin').length < 2 || psProbe.querySelectorAll('.chat-syntax-variable, .chat-syntax-parameter').length < 2) {{
    throw new Error("powershell syntax highlighting did not mark cmdlets and variables");
  }}
  const liveInlineProbe = window.document.createElement("div");
  liveInlineProbe.innerHTML = window.renderStreamingMarkdownLiveHtml("Use `[1,2,3,4,5,6]` during streaming.");
  if (!liveInlineProbe.querySelector(".chat-live-preview") || liveInlineProbe.querySelectorAll("code").length < 1 || !/\\[1,2,3,4,5,6\\]/.test(liveInlineProbe.textContent || "")) {{
    throw new Error("streaming markdown preview should render inline code in the live lane");
  }}
  const liveFenceProbe = window.document.createElement("div");
  liveFenceProbe.innerHTML = window.renderStreamingMarkdownLiveHtml("```python\\nfor i in range(3):\\n    print(i)");
  const liveFenceCode = liveFenceProbe.querySelector("pre.chat-code code");
  if (!liveFenceCode || !/for i in range\\(3\\):\\n    print\\(i\\)/.test(liveFenceCode.textContent || "")) {{
    throw new Error("streaming markdown preview should preserve multiline code content while an open fence is still streaming");
  }}
  if (/```/.test(liveFenceProbe.textContent || "")) {{
    throw new Error("streaming markdown preview should hide the raw fence markers once a code block preview is active");
  }}
  const brokenBoldProbe = window.document.createElement("div");
  brokenBoldProbe.innerHTML = window.renderStreamingMarkdownLiveHtml("**31. Herbert Hoover (1929-1933)");
  if (!brokenBoldProbe.querySelector("strong") || /\\*\\*/.test(brokenBoldProbe.textContent || "")) {{
    throw new Error("streaming markdown preview should auto-close unfinished strong markers");
  }}
  if (window.normalizeSoftWrappedMarkdown("3\\n. Ruby") !== "3. Ruby") {{
    throw new Error("soft-wrap markdown normalization should repair split ordered-list markers without adding an extra space");
  }}
  if (window.normalizeSoftWrappedMarkdown("**3\\n. Ruby") !== "**3. Ruby") {{
    throw new Error("soft-wrap markdown normalization should repair split ordered-list markers inside an open strong span");
  }}
  const splitOrderedBlockProbe = window.document.createElement("div");
  splitOrderedBlockProbe.innerHTML = window.markdownToHtml("1. Python\\n2\\n. **Java**\\n3. Ruby");
  if (splitOrderedBlockProbe.querySelectorAll("ol > li").length !== 3 || !splitOrderedBlockProbe.querySelector("ol > li strong") || /2\\s+\\.\\s+/.test(splitOrderedBlockProbe.textContent || "")) {{
    throw new Error("full markdown renderer should parse split ordered-list markers as list items");
  }}
  const liveSplitOrderedProbe = window.document.createElement("div");
  liveSplitOrderedProbe.innerHTML = window.renderStreamingMarkdownLiveHtml("3\\n. **Ruby**");
  if (!liveSplitOrderedProbe.querySelector("ol > li strong") || liveSplitOrderedProbe.querySelector("ol")?.getAttribute("start") !== "3" || /3\\s+\\.\\s+/.test(liveSplitOrderedProbe.textContent || "")) {{
    throw new Error("streaming markdown preview should render split ordered-list markers as rich list items");
  }}
  const liveSplitUnorderedProbe = window.document.createElement("div");
  liveSplitUnorderedProbe.innerHTML = window.renderStreamingMarkdownLiveHtml("-\\n*Ruby*");
  if (!liveSplitUnorderedProbe.querySelector("ul > li em") || /^-\\s/.test((liveSplitUnorderedProbe.textContent || "").trim())) {{
    throw new Error("streaming markdown preview should render split unordered-list markers as rich list items");
  }}
  if (window.findChatStreamingMarkdownStableBoundary("2. Java") !== 0) {{
    throw new Error("streaming markdown split normalization should not sever an ordered-list marker from its text");
  }}
  if (window.findChatStreamingMarkdownStableBoundary("**The\\nActual Core Roster (No Fluff)**") !== 0) {{
    throw new Error("streaming markdown split normalization should not sever a multi-line strong span");
  }}
  if (window.findChatStreamingMarkdownStableBoundary("*Fate/stay night\\n& Fate/Zero*") !== 0) {{
    throw new Error("streaming markdown split normalization should not sever a multi-line emphasis span");
  }}
  if (window.findChatStreamingMarkdownStableBoundary("Use `core\\nroster` carefully") !== 0) {{
    throw new Error("streaming markdown split normalization should not sever a multi-line inline-code span");
  }}
  if (window.findChatStreamingMarkdownStableBoundary("Visit [Club\\n3090](https://example.com)") !== 0) {{
    throw new Error("streaming markdown split normalization should not sever a multi-line link label");
  }}
  if (window.findChatStreamingMarkdownStableBoundary("Check ~~Fate\\nroute~~ notes") !== 0) {{
    throw new Error("streaming markdown split normalization should not sever a multi-line strikethrough span");
  }}
  const contextUsageProbe = window.deriveRuntimeContextUsage({{
    last_total_tokens: 321,
    total_tokens: 999,
    last_input_tokens: 111,
    last_output_tokens: 210,
    ctx_size_tokens: 4096,
  }});
  if (contextUsageProbe.usedTokens !== 321 || contextUsageProbe.ctxSize !== 4096) {{
    throw new Error(`context usage should prefer last-request totals over cumulative totals: ${{JSON.stringify(contextUsageProbe)}}`);
  }}
  const kvFallbackProbe = String(
    window.formatLastStatusCard({{
      last_latency_s: 2.5,
      last_ttft_s: 0.4,
      last_total_tokens: 321,
      ctx_size_tokens: 4096,
      last_generation_tps: 33.3,
      last_prompt_tps: 44.4,
    }}, {{}}) || '',
  );
  if (!/KV: 0%/.test(kvFallbackProbe) || !/context: 321 \\/ 4,096/.test(kvFallbackProbe)) {{
    throw new Error("runtime stats fallback should show KV 0% and request-scoped context usage");
  }}
  window.setCurrentLogSource("audit");
  window.logCacheEntry("audit").text = "";
  window.logCacheEntry("audit").loaded = true;
  window.logCacheEntry("debug").text = "";
  window.logCacheEntry("debug").loaded = true;
  const originalFetch = window.fetch;
  window.fetch = async () => ({{
    ok: true,
    text: async () => JSON.stringify({{ ok: true, result: {{ status: "ok", values: [1, 2, 3] }} }}),
  }});
  try {{
    await window.post("/admin/test", {{ probe: true }}, "smoke request");
  }} finally {{
    window.fetch = originalFetch;
  }}
  const auditUiText = window.logCacheEntry("audit").text || "";
  const debugUiText = window.logCacheEntry("debug").text || "";
  if (!/request sent: smoke request/.test(auditUiText) || !/request finished: smoke request/.test(auditUiText)) {{
    throw new Error("audit ui log did not keep the short request lifecycle lines");
  }}
  if (/----- admin result -----/.test(auditUiText)) {{
    throw new Error("audit ui log still received the large admin result payload");
  }}
  if (!/----- admin result -----/.test(debugUiText) || !/"values": \\[\\s*1,\\s*2,\\s*3\\s*\\]/m.test(debugUiText)) {{
    throw new Error("debug ui log did not receive the detailed admin result payload");
  }}
  const originalRuntimeTrackingItems = window.runtimeTrackingItems;
  window.runtimeTrackingItems = () => [
    {{ id: "GLOBAL", instance_id: "GLOBAL", running: true, mode: "vllm/dual-dflash", gpu_indices: [0, 1] }},
    {{ id: "PAIR0_1", instance_id: "PAIR0_1", running: true, mode: "vllm/dual-dflash", gpu_indices: [0, 1] }},
  ];
  window.eval("selectedLogInstanceId = ''; currentLogSource = 'docker';");
  window.setScope("GLOBAL", false);
  window.renderLogInstanceSelector();
  const dockerOptionRows = Array.from(window.document.getElementById("logInstanceSelect")?.options || []).map((option) => [option.value, option.textContent || ""]);
  window.runtimeTrackingItems = originalRuntimeTrackingItems;
  const dockerOptionValues = dockerOptionRows.map((row) => row[0]);
  const dockerPairLabel = dockerOptionRows.find((row) => row[0] === "PAIR0_1")?.[1] || "";
  if (dockerOptionValues.includes("GLOBAL") || !dockerOptionValues.includes("PAIR0_1") || !/\\(Global\\)/.test(dockerPairLabel)) {{
    throw new Error(`docker log selector did not split global dual runtime into labeled concrete scopes: ${{JSON.stringify(dockerOptionRows)}}`);
  }}
  if (showcaseBody.querySelector(".unsafe")) {{
    throw new Error("unsafe raw HTML was not escaped in the showcase conversation");
  }}
  const statsTitleAfterFirstSwitch = window.document.getElementById("chatStatsTitle");
  const statsAfterFirstSwitch = window.document.getElementById("chatRuntimeStats");
  if (!statsTitleAfterFirstSwitch || !/Fixture Runtime A/.test(statsTitleAfterFirstSwitch.textContent || "") || !statsAfterFirstSwitch || !/input: 111/.test(statsAfterFirstSwitch.textContent || "")) {{
    throw new Error("chat stats did not restore the first conversation snapshot");
  }}
  conversationSelect.value = "vision-test";
  if (typeof window.selectChatConversation === "function") {{
    window.selectChatConversation("vision-test");
  }} else {{
    conversationSelect.dispatchEvent(new window.Event("change", {{ bubbles: true }}));
  }}
  for (let attempt = 0; attempt < 20; attempt += 1) {{
    await new Promise((resolve) => setTimeout(resolve, 60));
    const visionTitle = window.document.getElementById("chatStatsTitle");
    if (visionTitle && /Fixture Runtime B/.test(visionTitle.textContent || "")) break;
  }}
  const statsTitleAfterSecondSwitch = window.document.getElementById("chatStatsTitle");
  const statsAfterSecondSwitch = window.document.getElementById("chatRuntimeStats");
  if (!statsTitleAfterSecondSwitch || !/Fixture Runtime B/.test(statsTitleAfterSecondSwitch.textContent || "") || !statsAfterSecondSwitch || !/input: 9/.test(statsAfterSecondSwitch.textContent || "")) {{
    throw new Error("chat stats did not switch to the second conversation snapshot");
  }}
  conversationSelect.value = "markdown-showcase";
  if (typeof window.selectChatConversation === "function") {{
    window.selectChatConversation("markdown-showcase");
  }} else {{
    conversationSelect.dispatchEvent(new window.Event("change", {{ bubbles: true }}));
  }}
  for (let attempt = 0; attempt < 20; attempt += 1) {{
    await new Promise((resolve) => setTimeout(resolve, 60));
    const restoredTitle = window.document.getElementById("chatStatsTitle");
    if (restoredTitle && /Fixture Runtime A/.test(restoredTitle.textContent || "")) break;
  }}
  const statsTitleAfterRestore = window.document.getElementById("chatStatsTitle");
  const statsAfterRestore = window.document.getElementById("chatRuntimeStats");
  if (!statsTitleAfterRestore || !/Fixture Runtime A/.test(statsTitleAfterRestore.textContent || "") || !statsAfterRestore || !/input: 111/.test(statsAfterRestore.textContent || "")) {{
    throw new Error("chat stats did not restore after switching back to the first conversation");
  }}
  const transcriptRootBeforeRefresh = transcriptAfterSwitch.firstElementChild;
  await window.refreshStatus();
  await new Promise((resolve) => setTimeout(resolve, 40));
  if (transcriptAfterSwitch.firstElementChild !== transcriptRootBeforeRefresh) {{
    throw new Error("status refresh unexpectedly rebuilt the chat transcript DOM");
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
  input.value = "Generate Fibonacci in every language and generate text with all kinds of different markdown styles in one reply.";
  if (typeof window.handleChatInputChange === "function") window.handleChatInputChange();
  const transcript = window.document.getElementById("chatTranscript");
  if (!transcript) throw new Error("chat transcript missing");
  transcript.style.height = "240px";
  transcript.style.maxHeight = "240px";
  transcript.scrollTop = Math.max(0, transcript.scrollHeight - transcript.clientHeight);
  const sendPromise = window.sendChatMessage();
  await new Promise((resolve) => setTimeout(resolve, 80));
  const transcriptRootDuringStream = transcript.firstElementChild;
  const assistantShellDuringStream = Array.from(transcript.querySelectorAll(".chat-turn"))
    .pop()
    ?.querySelector(".chat-message.chat-assistant");
  if (!assistantShellDuringStream) {{
    throw new Error("stream did not create the active assistant shell");
  }}
  if (!assistantShellDuringStream.querySelector(".chat-message-markdown-stable") || !assistantShellDuringStream.querySelector(".chat-message-markdown-live")) {{
    throw new Error("streaming markdown hosts were not created");
  }}
  let observedScrollableStreamingFrame = false;
  let maxStreamingBottomDelta = 0;
  let lastStreamingBottomDelta = 0;
  const streamGrowthDeadline = Date.now() + 1200;
  while (Date.now() < streamGrowthDeadline && !/Markdown Showcase|Test HTML response/.test(assistantShellDuringStream.textContent || "")) {{
    await new Promise((resolve) => setTimeout(resolve, 40));
    const bottomDelta = Math.max(
      0,
      transcript.scrollHeight - (transcript.scrollTop + transcript.clientHeight),
    );
    if (transcript.scrollHeight > transcript.clientHeight + 24) {{
      observedScrollableStreamingFrame = true;
      maxStreamingBottomDelta = Math.max(maxStreamingBottomDelta, bottomDelta);
      lastStreamingBottomDelta = bottomDelta;
    }}
  }}
  if (transcript.firstElementChild !== transcriptRootDuringStream) {{
    throw new Error("stream update unexpectedly rebuilt the transcript root while streaming");
  }}
  const assistantShellAfterIncrement = Array.from(transcript.querySelectorAll(".chat-turn"))
    .pop()
    ?.querySelector(".chat-message.chat-assistant");
  if (assistantShellAfterIncrement !== assistantShellDuringStream) {{
    throw new Error("stream update unexpectedly rebuilt the active assistant shell");
  }}
  if (!/Markdown Showcase|Test HTML response/.test(assistantShellDuringStream.textContent || "")) {{
    throw new Error("streaming assistant content did not grow while the stream was active");
  }}
  if (observedScrollableStreamingFrame && (lastStreamingBottomDelta < 4 || lastStreamingBottomDelta > 40)) {{
    throw new Error(`chat transcript did not hold the live tail inside the streaming follow band (bottom delta ${{lastStreamingBottomDelta}}px)`);
  }}
  await sendPromise;
  await new Promise((resolve) => setTimeout(resolve, 60));
  if (!transcript || !/Test HTML response/.test(transcript.textContent || "")) {{
    throw new Error("chat transcript did not receive mocked stream output");
  }}
  const finalBottomDelta = Math.max(
    0,
    transcript.scrollHeight - (transcript.scrollTop + transcript.clientHeight),
  );
  if (finalBottomDelta > 4) {{
    throw new Error(`chat transcript should settle to the very bottom after streaming completes (bottom delta ${{finalBottomDelta}}px)`);
  }}
  if (!transcript.querySelector(".chat-thinking-card")) {{
    throw new Error("chat transcript did not render the mocked thinking summary");
  }}
  conversationSelect.value = "mermaid-lab";
  if (typeof window.selectChatConversation === "function") {{
    window.selectChatConversation("mermaid-lab");
  }} else {{
    conversationSelect.dispatchEvent(new window.Event("change", {{ bubbles: true }}));
  }}
  let mermaidTranscript = null;
  for (let attempt = 0; attempt < 30; attempt += 1) {{
    await new Promise((resolve) => setTimeout(resolve, 60));
    mermaidTranscript = window.document.getElementById("chatTranscript");
    if (mermaidTranscript && /Mermaid Lab/.test(mermaidTranscript.textContent || "")) break;
  }}
  if (!mermaidTranscript || !/Mermaid Lab/.test(mermaidTranscript.textContent || "")) {{
    throw new Error("mermaid lab conversation did not finish loading");
  }}
  if (Math.abs(Number(mermaidTranscript.scrollTop || 0)) > 4) {{
    throw new Error(`conversation switching should not auto-scroll the next transcript outside active generation (scrollTop ${{mermaidTranscript.scrollTop}})`);
  }}
  const lastMermaidTurn = Array.from(mermaidTranscript.querySelectorAll(".chat-turn")).pop();
  const mermaidBody = lastMermaidTurn?.querySelector(".chat-message.chat-assistant .chat-message-body");
  if (!mermaidBody) {{
    throw new Error("mermaid lab assistant body did not render");
  }}
  const mermaidBlocks = Array.from(mermaidBody.querySelectorAll(".chat-mermaid-block"));
  const mermaidLabExpected = {json.dumps(MERMAID_LAB_EXPECTED_COUNTS, ensure_ascii=False)};
  const expectedMermaidBlockCount = Object.values(mermaidLabExpected).reduce((sum, value) => sum + Number(value || 0), 0);
  if (mermaidBlocks.length !== expectedMermaidBlockCount || mermaidBlocks.length < 30) {{
    throw new Error(`mermaid lab block count mismatch: expected ${{expectedMermaidBlockCount}}, saw ${{mermaidBlocks.length}}`);
  }}
  if (mermaidBody.querySelectorAll(".chat-mermaid-block pre.chat-code").length) {{
    throw new Error("at least one mermaid lab block fell back to raw code instead of SVG");
  }}
  const renderedMermaidSvgs = Array.from(mermaidBody.querySelectorAll(".chat-mermaid-block svg.chat-mermaid-svg"));
  if (renderedMermaidSvgs.length !== mermaidBlocks.length) {{
    throw new Error("not every mermaid lab block produced an SVG");
  }}
  const mermaidAriaCounts = Object.create(null);
  const parseViewBox = (svg) =>
    String(svg.getAttribute("viewBox") || "")
      .trim()
      .split(/\\s+/)
      .map((part) => Number(part));
  renderedMermaidSvgs.forEach((svg) => {{
    const label = String(svg.getAttribute("aria-label") || "unknown");
    mermaidAriaCounts[label] = (mermaidAriaCounts[label] || 0) + 1;
    const parts = parseViewBox(svg);
    if (parts.length !== 4 || parts.some((value) => !Number.isFinite(value))) {{
      throw new Error(`invalid mermaid viewBox for ${{label}}`);
    }}
    if (parts[2] < 120 || parts[3] < 80) {{
      throw new Error(`mermaid SVG too small for ${{label}}: ${{parts.join(" ")}}`);
    }}
    if (parts[2] > 3200 || parts[3] > 2400) {{
      throw new Error(`mermaid SVG runaway geometry for ${{label}}: ${{parts.join(" ")}}`);
    }}
  }});
  for (const [label, expectedCount] of Object.entries(mermaidLabExpected)) {{
    if ((mermaidAriaCounts[label] || 0) !== expectedCount) {{
      throw new Error(`expected ${{expectedCount}} mermaid SVGs for ${{label}}, saw ${{mermaidAriaCounts[label] || 0}}`);
    }}
  }}
  const stateDiagrams = Array.from(mermaidBody.querySelectorAll("svg[aria-label='Mermaid state diagram']"));
  if (!stateDiagrams.length || !stateDiagrams.every((svg) => {{
    const parts = parseViewBox(svg);
    return parts[2] <= 1800 && parts[3] <= 700;
  }})) {{
    throw new Error("state diagram geometry exceeded sane bounds");
  }}
  const ganttCharts = Array.from(mermaidBody.querySelectorAll("svg[aria-label='Mermaid gantt chart']"));
  if (!ganttCharts.length || !ganttCharts.every((svg) => {{
    const parts = parseViewBox(svg);
    return /YYYY-MM-DD/.test(svg.textContent || "") && parts[2] <= 1800 && parts[3] <= 700;
  }})) {{
    throw new Error("gantt chart geometry or header text failed validation");
  }}
  if (mermaidBody.querySelectorAll("h2").length < 10 || mermaidBody.querySelectorAll("h3").length < expectedMermaidBlockCount) {{
    throw new Error("mermaid lab headings did not render as expected");
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
module.CUSTOM_MODELS_FILE = str(temp_root / "custom_models.json")
module.CUSTOM_MODELS_DIR = str(temp_root / "custom-models")
module.INSTANCES_CONFIG_FILE = str(temp_root / "instances.json")
module.SERVER_CONFIG_FILE = str(temp_root / "server_config.json")
module.USERS_FILE = str(temp_root / "users.json")
module.GROUPS_FILE = str(temp_root / "groups.json")
module.RUNTIME_INVENTORY_FILE = str(temp_root / "runtime_inventory.json")
module.GENERATED_COMPOSE_OVERRIDES_DIR = str(temp_root / "compose-overrides")

cfg, changed = module.write_ui_config({"active_tab": "logs", "show_global_logs": False})
assert changed is True and cfg["active_tab"] == "logs" and cfg["show_global_logs"] is False
cfg2, changed2 = module.write_ui_config({"active_tab": "logs", "show_global_logs": False})
assert changed2 is False and cfg2 == cfg

server_before = module.read_server_config()
server_after = module.write_server_config({"selected_preset_model": "fixture-model"})
server_after_repeat = module.write_server_config({"selected_preset_model": "fixture-model"})
assert server_after["selected_preset_model"] == "fixture-model"
assert server_after_repeat == server_after
assert pathlib.Path(module.SERVER_CONFIG_FILE).exists()

custom = {"sample": {"description": "fixture", "params": {"temperature": 0.7}}}
module.write_custom_presets(custom)
custom_mtime = pathlib.Path(module.CUSTOM_PRESETS_FILE).stat().st_mtime_ns
time.sleep(0.01)
module.write_custom_presets(custom)
assert pathlib.Path(module.CUSTOM_PRESETS_FILE).stat().st_mtime_ns == custom_mtime

custom_models = [
    {
        "id": "fixture-custom",
        "selector": "custom/fixture-custom",
        "slug": "org/fixture-model",
        "model_id": "custom-fixture-custom",
        "display_name": "Fixture Custom",
        "profile_like": "vllm/minimal",
        "compose_path": str(temp_root / "custom-models" / "fixture-custom" / "docker-compose.yml"),
    }
]
module.write_custom_model_registry(custom_models)
loaded_custom_models = module.read_custom_model_registry()
assert len(loaded_custom_models) == 1
assert loaded_custom_models[0]["selector"] == "custom/fixture-custom"
missing_rel_row = {
    "id": "legacy-custom",
    "selector": "custom/legacy-custom",
    "slug": "org/legacy-model",
    "model_id": "custom-legacy-custom",
    "display_name": "Legacy Custom",
    "profile_like": "vllm/minimal",
    "compose_path": str(temp_root / "custom-models" / "legacy-custom" / "docker-compose.yml"),
}
module.write_custom_model_registry(loaded_custom_models + [missing_rel_row])
legacy_rows = module.read_custom_model_registry()
assert any(str(row.get("compose_path") or "").endswith("legacy-custom" + os.sep + "docker-compose.yml") for row in legacy_rows), legacy_rows

variant = {
    "selector": "vllm/dual",
    "engine_family": "vllm",
    "service_name": "fixture-vllm",
    "compose_project_dir_abs_path": str(temp_root / "repo" / "models" / "qwen3.6-27b" / "vllm" / "compose"),
}
cache_root = module.variant_persistent_cache_host_root(variant)
assert cache_root.endswith(f"qwen3.6-27b{os.sep}vllm{os.sep}cache")
override_path = module.refresh_variant_cache_override(variant)
override_text = pathlib.Path(override_path).read_text(encoding="utf-8")
assert "TRITON_CACHE_DIR" in override_text and "VLLM_CACHE_ROOT" in override_text
warmup_guard = module.maybe_warmup_variant_runtime({"engine_family": "vllm", "served_model_name": "fixture-model"}, "")
assert warmup_guard.get("skipped") is True and warmup_guard.get("reason") == "missing-ready-url"
missing_model_dir_spec = {
    "compose_project_dir_abs_path": str(temp_root / "repo" / "models" / "qwen3.6-27b" / "vllm" / "compose" / "single" / "autoround-int4"),
}
module._load_repo_env_map = lambda : {"MODEL_DIR": "../../../../../../external-models"}
assert module._resolve_variant_model_dir_root(missing_model_dir_spec) == str(temp_root / "repo" / "external-models")
assert module._resolve_variant_model_dir_root({"host_model_dir": str(temp_root / "custom-host-models")}) == str(temp_root / "custom-host-models")
assert module._path_is_within(str(temp_root / "repo"), str(temp_root / "repo" / "models" / "x")) is True
assert module._path_is_within(str(temp_root / "repo"), str(temp_root / "repo-shadow" / "models" / "x")) is False

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

fixture_spec = {
    "selector": "ik-llama/iq4ks-two-stage",
    "variant_id": "fixture-ik-llama",
    "model_id": "qwen3.6-27b",
    "service_name": "ik-llama-qwen36-27b-two-stage",
    "compose_abs_path": str(temp_root / "repo" / "models" / "qwen3.6-27b" / "ik-llama" / "compose" / "single" / "iq4ks-two-stage.yml"),
    "compose_project_dir_abs_path": str(temp_root / "repo" / "models" / "qwen3.6-27b" / "ik-llama" / "compose"),
}
module.resolve_variant_spec = lambda selector: dict(fixture_spec) if selector == "ik-llama/iq4ks-two-stage" else {"kind": "single", "selector": selector}
module.resolve_variant_launch_env = lambda spec: {}
module._load_repo_env_map = lambda : {"HF_TOKEN": "fixture-token"}
module._resolve_variant_model_dir_root = lambda spec: str(temp_root / "models-cache")
runtime_root = temp_root / "repo" / "models" / "qwen3.6-27b" / "vllm"
(runtime_root / "patches" / "genesis" / "vllm" / "_genesis").mkdir(parents=True, exist_ok=True)
(runtime_root / "patches" / "local").mkdir(parents=True, exist_ok=True)
(runtime_root / "patches" / "vllm-pr35936-required-fallback" / "vllm" / "entrypoints" / "openai" / "chat_completion").mkdir(parents=True, exist_ok=True)
(runtime_root / "patches" / "vllm-pr35936-required-fallback" / "vllm" / "entrypoints" / "openai" / "engine").mkdir(parents=True, exist_ok=True)
(runtime_root / "patches" / "vllm-pr41800-truncate-prompt-tokens").mkdir(parents=True, exist_ok=True)
(runtime_root / "patches" / "froggeric-chat-template").mkdir(parents=True, exist_ok=True)
(runtime_root / "patches" / "local" / "qwen3coder_tool_parser_deferred_commit.py").write_text("print('ok')", encoding="utf-8")
(runtime_root / "patches" / "vllm-pr35936-required-fallback" / "vllm" / "entrypoints" / "openai" / "chat_completion" / "serving.py").write_text("# serving", encoding="utf-8")
(runtime_root / "patches" / "vllm-pr35936-required-fallback" / "vllm" / "entrypoints" / "openai" / "engine" / "serving.py").write_text("# engine", encoding="utf-8")
(runtime_root / "patches" / "vllm-pr35936-required-fallback" / "install.sh").write_text("#!/usr/bin/env bash", encoding="utf-8")
(runtime_root / "patches" / "vllm-pr41800-truncate-prompt-tokens" / "install.sh").write_text("#!/usr/bin/env bash", encoding="utf-8")
(runtime_root / "patches" / "froggeric-chat-template" / "chat_template.jinja").write_text("template", encoding="utf-8")
assert module.variant_runtime_root_dir({
    "compose_abs_path": str(runtime_root / "compose" / "single" / "autoround-int4" / "tools-text.yml"),
    "compose_project_dir_abs_path": str(runtime_root / "compose" / "single" / "autoround-int4"),
}) == str(runtime_root)
assert module.variant_persistent_cache_host_root({
    "engine_family": "vllm",
    "compose_abs_path": str(runtime_root / "compose" / "single" / "autoround-int4" / "tools-text.yml"),
    "compose_project_dir_abs_path": str(runtime_root / "compose" / "single" / "autoround-int4"),
}) == str(runtime_root / "cache")
patch_targets = module.instance_patch_bind_overrides({
    "compose_abs_path": str(runtime_root / "compose" / "single" / "autoround-int4" / "tools-text.yml"),
    "compose_project_dir_abs_path": str(runtime_root / "compose" / "single" / "autoround-int4"),
})
assert any(pathlib.Path(source) == runtime_root / "patches" / "froggeric-chat-template" / "chat_template.jinja" for source, _target in patch_targets), patch_targets
gpu1_instance = {
    "id": "GPU1",
    "kind": "single",
    "gpu_indices": [1],
    "gpu_index": 1,
    "mode": "ik-llama/iq4ks-two-stage",
    "enabled": True,
    "port": 8201,
}
paths = module.write_instance_artifacts(gpu1_instance)
env_text = pathlib.Path(paths["env"]).read_text(encoding="utf-8")
override_text = pathlib.Path(paths["override"]).read_text(encoding="utf-8")
assert "ESTATE_GPUS=1" in env_text, env_text
assert "CUDA_VISIBLE_DEVICES=1" in env_text, env_text
assert "NVIDIA_VISIBLE_DEVICES=1" in env_text, env_text
assert 'ESTATE_GPUS: "1"' in override_text, override_text
assert 'CUDA_VISIBLE_DEVICES: "0"' in override_text, override_text
assert 'NVIDIA_VISIBLE_DEVICES: "0"' in override_text, override_text
module._probe_host_gpus = lambda timeout=8: [
    {"index": 0, "memory_total_mib": 24576, "memory_free_mib": 24000, "compute_cap": "8.6"},
    {"index": 1, "memory_total_mib": 28672, "memory_free_mib": 28000, "compute_cap": "8.6"},
]
guard_env = module._apply_variant_hardware_guard(
    {"selector": "ik-llama/iq4ks-two-stage", "scope_kind": "single", "requires_min_vram_gb": 20},
    {},
)
assert guard_env["ESTATE_GPUS"] == "1", guard_env
assert guard_env["CUDA_VISIBLE_DEVICES"] == "0", guard_env
assert guard_env["NVIDIA_VISIBLE_DEVICES"] == "0", guard_env

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


def remote_update_metadata_smoke_harness() -> str:
    return """import importlib.util
import json
import pathlib
import sys

control_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("club3090_control_remote_update_smoke", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

module.SCRIPT_VERSION = "2026-05-31.v0.9.12"
module.resolve_remote_update_commit = lambda timeout=12: "3d1fb7cd41c39c568c7eff0c7afd63087fb7aabc"

large_release = "v0.9.12\\n\\n" + "\\n\\n".join(
    f"v0.9.{index}\\n\\n• 🐞 Regression entry {index} keeps the changelog payload intentionally large for smoke coverage."
    for index in range(11, -1, -1)
)
while len(large_release.encode("utf-8")) <= 52000:
    large_release += "\\n\\n• 🛠️ Padding entry to keep remote metadata above the legacy truncation threshold."

payload = json.dumps(
    {
        "version": "0.9.13",
        "release_date": "2026-06-01",
        "change_log_latest": "• 🐞 Fixed oversized remote metadata parsing so update banners still light up after larger release histories.",
        "change_log_release": large_release,
        "change_log_icons": {"fix": "🐞", "build_pipeline_improvement": "🛠️"},
        "club3090_version": {"release": "v0.8.6-1-ga74398d", "commit": "a74398d64f1748be0febccc727dc908b25e792fd"},
    },
    ensure_ascii=False,
)
assert len(payload.encode("utf-8")) > 52000, len(payload.encode("utf-8"))

module.fetch_remote_update_metadata_text = lambda commit_sha, timeout=12: (
    payload,
    "smoke",
    f"https://example.invalid/{commit_sha}/metadata.json",
)

result = module.fetch_remote_script_metadata(force=True)
assert result.get("error") in {"", None}, result
assert result.get("script_version") == "2026-06-01.v0.9.13", result
assert result.get("update_available") is True, result
assert "Regression entry" in str(result.get("change_log_release") or ""), result
print("remote update metadata smoke ok")
"""


def run_remote_update_metadata_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, remote_update_metadata_smoke_harness())
    result = run_command([sys.executable, str(script_path), str(control_path)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def model_install_progress_smoke_harness() -> str:
    return """import importlib.util
import pathlib
import shutil
import sys
import tempfile

control_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("club3090_control_model_install_smoke", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

temp_root = pathlib.Path(tempfile.mkdtemp(prefix="club3090-model-install-smoke-"))
try:
    partial_dir = temp_root / "models-cache" / "qwen3.6-27b-gguf" / "unsloth-q5ks"
    partial_dir.mkdir(parents=True, exist_ok=True)
    (partial_dir / ".partial-download").write_bytes(b"x" * 4096)

    direct_step = {
        "repo_ids": ["unsloth/Qwen3.6-27B-GGUF"],
        "filenames": ["Qwen3.6-27B-Q5_K_S.gguf"],
        "local_dir": str(partial_dir),
    }
    loaded_bytes = module._hf_download_step_loaded_bytes(direct_step, {}, 8192)
    assert loaded_bytes >= 4096, loaded_bytes

    variant = {
        "model_id": "qwen3.6-27b",
        "weights_variant": "autoround-int4",
        "model_path": "/root/.cache/huggingface/qwen3.6-27b-autoround-int4",
        "draft_model_path": "/root/.cache/huggingface/qwen3.6-27b-dflash",
        "mmproj_path": "",
        "host_model_dir": str(temp_root / "models-cache"),
    }
    module._weight_recipe_from_subpath = lambda subpath: {
        "WEIGHT_REPO": "z-lab/Qwen3.6-27B-DFlash",
        "WEIGHT_FILES": "",
        "WEIGHT_SUBDIR": "qwen3.6-27b-dflash",
    } if str(subpath or "").strip() == "qwen3.6-27b-dflash" else {}
    module._weight_recipe_from_model_variant = lambda model_id, weights_variant: {
        "WEIGHT_REPO": "Qwen/Qwen3.6-27B-Instruct-AWQ",
        "WEIGHT_FILES": "",
        "WEIGHT_SUBDIR": "qwen3.6-27b-autoround-int4",
    } if str(model_id or "").strip() == "qwen3.6-27b" and str(weights_variant or "").strip() == "autoround-int4" else {}
    module._recipe_subdir_host_path = lambda model_dir_root, recipe: str(pathlib.Path(model_dir_root) / str((recipe or {}).get("WEIGHT_SUBDIR") or ""))
    plan = module._monitor_plan_from_variant_install(
        variant,
        "WEIGHT_KEY=qwen3.6-27b:autoround-int4 WITH_DFLASH_DRAFT=1 bash scripts/setup.sh qwen3.6-27b",
    )
    assert plan, plan
    repos = {repo for step in plan for repo in (step.get("repo_ids") or [])}
    assert "z-lab/Qwen3.6-27B-DFlash" in repos, repos
    assert any("qwen3.6-27b-dflash" in str(step.get("local_dir") or "") for step in plan), plan

    direct_plan = module._parse_simple_hf_download_plan(
        'hf download unsloth/Qwen3.6-27B-GGUF Qwen3.6-27B-Q5_K_S.gguf --local-dir "/models/target"'
    )
    assert len(direct_plan) == 1, direct_plan
    parsed_setup = module._parse_setup_install_command(
        "WITH_DFLASH_DRAFT=1 bash scripts/setup.sh qwen3.6-27b"
    )
    assert parsed_setup and parsed_setup["model_id"] == "qwen3.6-27b", parsed_setup
    assert parsed_setup["env_map"].get("WITH_DFLASH_DRAFT") == "1", parsed_setup
    skip_command = module._setup_install_command_with_skip_model(parsed_setup)
    assert "SKIP_MODEL=1" in skip_command, skip_command
    assert "WITH_DFLASH_DRAFT=1" in skip_command, skip_command
    assert skip_command.endswith("bash scripts/setup.sh qwen3.6-27b"), skip_command
    print("model install progress smoke ok")
finally:
    shutil.rmtree(temp_root, ignore_errors=True)
"""


def run_model_install_progress_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, model_install_progress_smoke_harness())
    result = run_command([sys.executable, str(script_path), str(control_path)], cwd)
    try:
        script_path.unlink(missing_ok=True)
    except Exception:
        pass
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def runtime_inventory_registry_smoke_harness() -> str:
    return """import importlib.util
import pathlib
import shutil
import tempfile
import sys

control_path = pathlib.Path(sys.argv[1])
workspace_root = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("club3090_control_inventory_smoke", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

temp_root = pathlib.Path(tempfile.mkdtemp(prefix="club3090-inventory-smoke-"))
try:
    module.CONTROL_DIR = str(temp_root)
    module.UI_CONFIG_FILE = str(temp_root / "ui_config.json")
    module.CUSTOM_PRESETS_FILE = str(temp_root / "custom_presets.json")
    module.CUSTOM_MODELS_FILE = str(temp_root / "custom_models.json")
    module.CUSTOM_MODELS_DIR = str(temp_root / "custom-models")
    module.INSTANCES_CONFIG_FILE = str(temp_root / "instances.json")
    module.SERVER_CONFIG_FILE = str(temp_root / "server_config.json")
    module.USERS_FILE = str(temp_root / "users.json")
    module.GROUPS_FILE = str(temp_root / "groups.json")
    module.RUNTIME_INVENTORY_FILE = str(temp_root / "runtime_inventory.json")
    module.GENERATED_COMPOSE_OVERRIDES_DIR = str(temp_root / "compose-overrides")
    module.ACTIVE_MODE_FILE = str(temp_root / "active_mode")
    module.LAST_GOOD_MODE_FILE = str(temp_root / "last_good_mode")
    module.CLUB3090_DIR = str(workspace_root / "club-3090")
    custom_compose_dir = temp_root / "custom-models" / "legacy-custom"
    custom_compose_dir.mkdir(parents=True, exist_ok=True)
    (custom_compose_dir / "docker-compose.yml").write_text(
        "services:\\n  vllm-legacy-custom:\\n    container_name: legacy-custom\\n",
        encoding="utf-8",
    )
    module.write_custom_model_registry(
        [
            {
                "id": "legacy-custom",
                "selector": "custom/legacy-custom",
                "slug": "org/legacy-model",
                "model_id": "custom-legacy-custom",
                "display_name": "Legacy Custom",
                "profile_like": "vllm/minimal",
                "compose_path": str(custom_compose_dir / "docker-compose.yml"),
            }
        ]
    )

    inventory = module.rebuild_runtime_inventory()
    by_tag = {
        str(row.get("upstream_tag") or ""): row
        for row in (inventory.get("variants") or [])
        if str(row.get("upstream_tag") or "").strip()
    }

    llama_cpp = by_tag["llamacpp/mtp"]
    assert llama_cpp["compose_rel_path"].endswith("models/qwen3.6-27b/llama-cpp/compose/single/unsloth-q4km/mtp.yml"), llama_cpp
    llama_cpp_command = str(llama_cpp.get("install_command") or "")
    assert llama_cpp_command.startswith("hf download unsloth/Qwen3.6-27B-MTP-GGUF "), llama_cpp_command
    assert "bash scripts/setup.sh" not in llama_cpp_command, llama_cpp_command

    iq4ks = by_tag["ik-llama/iq4ks-mtp"]
    assert iq4ks["compose_rel_path"].endswith("models/qwen3.6-27b/ik-llama/compose/single/ubergarm-iq4ks/mtp.yml"), iq4ks
    iq4ks_command = str(iq4ks.get("install_command") or "")
    assert iq4ks_command.startswith("hf download ubergarm/Qwen3.6-27B-GGUF "), iq4ks_command
    assert "bash scripts/setup.sh" not in iq4ks_command, iq4ks_command
    assert str(iq4ks.get("engine_display") or "") == "ik-llama", iq4ks

    prism_vision = by_tag["ik-llama/prism-pro-dq-dual-vision"]
    prism_command = str(prism_vision.get("install_command") or "")
    assert prism_command.startswith("hf download Ex0bit/Qwen3.6-27B-PRISM-PRO-DQ "), prism_command
    assert "bash scripts/setup.sh" not in prism_command, prism_command
    assert "mmproj-F16.gguf" in prism_command, prism_command

    gemma_a4b = by_tag["vllm/gemma-a4b-awq-mtp"]
    gemma_command = str(gemma_a4b.get("install_command") or "")
    assert "WEIGHTS=awq" in gemma_command and "WITH_ASSISTANT_DRAFT=1" in gemma_command, gemma_command

    qwen_a3b = by_tag["vllm/qwen-a3b-preview-single"]
    qwen_a3b_command = str(qwen_a3b.get("install_command") or "")
    assert "Intel/Qwen3.6-35B-A3B-int4-mixed-AutoRound" in qwen_a3b_command, qwen_a3b_command
    assert "bash scripts/setup.sh qwen3.6-35b-a3b" not in qwen_a3b_command, qwen_a3b_command

    apex_fit = by_tag["ik-llama/apex-fit-q8q4"]
    apex_fit_command = str(apex_fit.get("install_command") or "")
    assert apex_fit_command.startswith("hf download mudler/Qwen3.6-35B-A3B-APEX-MTP-GGUF "), apex_fit_command
    assert "bash scripts/setup.sh" not in apex_fit_command, apex_fit_command

    sglang_single = next(
        row
        for row in (inventory.get("variants") or [])
        if str(row.get("compose_rel_path") or "").endswith("models/qwen3.6-27b/sglang/compose/single/autoround-int4/eagle3-experimental.yml")
    )
    assert str(sglang_single.get("model_path") or "") == "/models/target", sglang_single
    assert str(sglang_single.get("draft_model_path") or "") == "/models/drafter", sglang_single

    synthetic_model_root = temp_root / "models-cache"
    (synthetic_model_root / "qwen3.6-27b-autoround-int4").mkdir(parents=True, exist_ok=True)
    (synthetic_model_root / "qwen3.6-27b-dflash").mkdir(parents=True, exist_ok=True)
    (synthetic_model_root / "qwen3.6-27b-autoround-int4" / "weights.safetensors").write_bytes(b"base")
    (synthetic_model_root / "qwen3.6-27b-dflash" / "draft.safetensors").write_bytes(b"draft")
    synthetic_plan = module.variant_resource_plan_from_row(
        {
            "selector": "vllm/dual",
            "host_model_dir": str(synthetic_model_root),
            "model_path": "/root/.cache/huggingface/qwen3.6-27b-autoround-int4",
            "draft_model_path": "/root/.cache/huggingface/qwen3.6-27b-dflash",
            "mmproj_path": "",
        }
    )
    assert int(synthetic_plan.get("resource_size_bytes") or 0) >= 9, synthetic_plan
    assert len(synthetic_plan.get("resources") or []) == 2, synthetic_plan
    assert all(str(item.get("identity_key") or "").strip() for item in (synthetic_plan.get("resources") or [])), synthetic_plan

    assert llama_cpp["selector"] == "llamacpp/mtp", llama_cpp
    assert iq4ks["selector"] == "ik-llama/iq4ks-mtp", iq4ks
    assert qwen_a3b["selector"] == "vllm/qwen-a3b-preview-single", qwen_a3b
    legacy_custom = next(row for row in (inventory.get("variants") or []) if row.get("upstream_tag") == "custom/legacy-custom")
    assert legacy_custom["compose_rel_path"].endswith("custom-models/legacy-custom/docker-compose.yml"), legacy_custom
    assert by_tag["vllm/dual"]["nvlink_mode"] == "capable", by_tag["vllm/dual"]
    assert by_tag["vllm/gemma-int8"]["nvlink_mode"] == "capable", by_tag["vllm/gemma-int8"]

    assert module.default_dual_mode_selector() in {"vllm/dual-dflash", "vllm/dual"}
    assert module.variant_engine_family({"selector": "ik-llama/iq4ks-mtp"}) == "llamacpp"
    print("runtime inventory registry smoke ok")
finally:
    shutil.rmtree(temp_root, ignore_errors=True)
"""


def run_runtime_inventory_registry_smoke_test(control_path: Path, cwd: Path, workspace_root: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, runtime_inventory_registry_smoke_harness())
    result = run_command([sys.executable, str(script_path), str(control_path), str(workspace_root)], cwd)
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
                    "presetId": "GPU1::ik-llama/apex-mtp-compact",
                    "runtimeSnapshot": {
                        "id": "GPU1",
                        "selector": "ik-llama/apex-mtp-compact",
                        "mode": "ik-llama/apex-mtp-compact",
                    },
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
    titles = module.read_chat_state_titles()
    assert titles["conversations"][0]["presetId"] == "GPU1::ik-llama/apex-mtp-compact"
    assert titles["conversations"][0]["runtimeSnapshot"]["mode"] == "ik-llama/apex-mtp-compact"
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


def audit_log_filter_smoke_harness() -> str:
    return """import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile

control_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("club3090_control_audit_filter", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

temp_root = pathlib.Path(tempfile.mkdtemp(prefix="club3090-audit-filter-"))
try:
    audit_path = temp_root / "audit.log"
    debug_path = temp_root / "debug.log"
    module.AUDIT_LOG_FILE = str(audit_path)
    module.DEBUG_LOG_FILE = str(debug_path)
    module.audit_rate_limit_state.clear()
    module.log_audit("admin_auth_denied", client="127.0.0.1", path="/admin")
    module.log_audit("admin_power", action="stop_container", instance="GLOBAL", result_summary="ok")
    audit_text = audit_path.read_text(encoding="utf-8") if audit_path.exists() else ""
    debug_lines = [json.loads(line) for line in debug_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert "Admin auth denied" not in audit_text, audit_text
    assert "Admin power" in audit_text, audit_text
    assert any(str(row.get("event")) == "admin_auth_denied" for row in debug_lines), debug_lines
    assert any(str(row.get("event")) == "admin_power" for row in debug_lines), debug_lines
    print("audit log filter smoke ok")
finally:
    shutil.rmtree(temp_root, ignore_errors=True)
"""


def run_audit_log_filter_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, audit_log_filter_smoke_harness())
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


def debug_transfer_expansion_smoke_harness() -> str:
    return """import importlib.util
import os
import pathlib
import sys
import tempfile

control_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("club3090_control_debug_transfer", control_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory(prefix="club3090-debug-transfer-") as root:
    os.makedirs(os.path.join(root, "sub"), exist_ok=True)
    pathlib.Path(root, "a.sh").write_text("echo a\\n", encoding="utf-8")
    pathlib.Path(root, "sub", "b.sh").write_text("echo b\\n", encoding="utf-8")
    pathlib.Path(root, "sub", "c.txt").write_text("echo c\\n", encoding="utf-8")

    recursive_rows = module._expand_debug_transfer_download_entry(os.path.join(root, "*.sh"), root)
    assert [row["archive_path"] for row in recursive_rows] == ["a.sh", "sub/b.sh"], recursive_rows

    non_recursive_rows = module._expand_debug_transfer_download_entry(os.path.join(root, "*.sh") + ":", root)
    assert [row["archive_path"] for row in non_recursive_rows] == ["a.sh"], non_recursive_rows

    directory_rows = module._expand_debug_transfer_download_entry(root, root)
    assert sorted(row["archive_path"] for row in directory_rows) == ["a.sh", "sub/b.sh", "sub/c.txt"], directory_rows

    plan = module.build_debug_transfer_plan("download", [os.path.join(root, "*.sh")])
    assert plan.get("archive_forced") is True, plan

print("debug transfer expansion smoke ok")
"""


def run_debug_transfer_expansion_smoke_test(control_path: Path, cwd: Path, filename: str) -> tuple[bool, str]:
    script_path = cwd / filename
    write_text(script_path, debug_transfer_expansion_smoke_harness())
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

const exitedHtml = context.renderServiceCards(
  [{{
    id: "searxng",
    display_name: "SearXNG",
    status: "exited",
    health_status: "exited (code 137)",
    stateClass: "status-exited",
    detail: "port 8088",
    ready: false,
  }}],
  {{ showActions: true }},
);
if (!exitedHtml.includes(">exited<")) throw new Error("exited service should show exited badge");
if (!exitedHtml.includes("Status: exited (code 137)")) throw new Error("exited service should show exited detail");

context.lastStatus = {{
  users: [],
  groups: [],
  server_config: {{}},
  presets: {{ defaults: [], custom: [] }},
}};
context.ensureUsersUi();
context.applyDirectoryPayload({{
  users: [{{
    name: "alice",
    enabled: true,
    effective_allowed_targets: ["*"],
    groups: [],
    has_api_key: true,
    api_key_available: true,
    usage: {{
      window_5h: {{ requests: 0, score: 0, input_tokens: 0, output_tokens: 0, tool_calls: 0, thinking_seconds: 0 }},
      window_week: {{ requests: 0, score: 0, input_tokens: 0, output_tokens: 0, tool_calls: 0, thinking_seconds: 0 }},
    }},
    limits: {{}},
    effective_limits: {{}},
  }}],
  groups: [],
  server_config: {{}},
}});
if (!getElement("usersGrid").innerHTML.includes("alice")) throw new Error("directory payload should render saved users immediately");

context.applyPresetCatalogPayload({{
  defaults: [],
  custom: [{{
    name: "live_audit_ok",
    endpoint: "/v1/live_audit_ok",
    endpoint_alt: "/live_audit_ok",
    locked: false,
    params: {{}},
    description: "temporary",
  }}],
}});
if (!getElement("apiPresetGrid").innerHTML.includes("/v1/live_audit_ok")) throw new Error("preset payload should render custom preset immediately");
context.applyPresetCatalogPayload({{ defaults: [], custom: [] }});
if (getElement("apiPresetGrid").innerHTML.includes("/v1/live_audit_ok")) throw new Error("preset payload should remove deleted custom presets immediately");

if (typeof context.promptBenchmarkRun !== "function") throw new Error("promptBenchmarkRun() missing");
if (typeof context.promptRebenchRun !== "function") throw new Error("promptRebenchRun() missing");
if (typeof context.promptFreeGpuResources !== "function") throw new Error("promptFreeGpuResources() missing");
const taskCalls = [];
let presetModalConfig = null;
let choiceModalConfig = null;
const auditMessages = [];
context.post = async (url, body) => {{
  taskCalls.push({{ url, body }});
  return {{ ok: true }};
}};
context.setAuditMsg = (message) => {{
  auditMessages.push(String(message || ""));
}};
context.openPresetActionModal = (config) => {{
  presetModalConfig = config;
}};
context.openActionChoiceModal = (config) => {{
  choiceModalConfig = config;
}};
context.selectedAdminTaskTargetRuntime = () => ({{
  id: "GPU1",
  instance_id: "GPU1",
  running: true,
}});
context.selectedAdminTaskTargetLabel = () => "GPU 1";
context.renderGpuCards([{{
  index: 0,
  name: "RTX 3090",
  mem_free_mib: 1024,
  mem_used_mib: 1024,
  mem_total_mib: 2048,
  power_w: 120,
  power_limit_w: 350,
  fan_pct: 100,
  util_pct: 0,
}}]);
if (!getElement("gpuCards").innerHTML.includes("promptFreeGpuResources(0)")) {{
  throw new Error("GPU cards should expose the free-resources action");
}}
context.promptBenchmarkRun();
if (!presetModalConfig || !String(presetModalConfig.body || "").includes("GPU 1")) {{
  throw new Error("benchmark modal should mention the scoped runtime");
}}
Promise.resolve(presetModalConfig.onConfirm()).then(async () => {{
  if (!taskCalls.length || taskCalls[0].url !== "/admin/benchmark" || taskCalls[0].body.instance_id !== "GPU1") {{
    throw new Error("benchmark action should post the selected instance_id");
  }}
  context.promptRebenchRun();
  if (!choiceModalConfig || !Array.isArray(choiceModalConfig.choices) || choiceModalConfig.choices.length !== 2) {{
    throw new Error("rebench modal should expose both runtime and full choices");
  }}
  await choiceModalConfig.choices[0].onClick();
  await choiceModalConfig.choices[1].onClick();
  const rebenchCalls = taskCalls.filter((row) => row.url === "/admin/rebench");
  if (rebenchCalls.length !== 2) throw new Error("rebench should issue both variant requests during smoke");
  if (rebenchCalls[0].body.variant !== "runtime" || rebenchCalls[1].body.variant !== "full") {{
    throw new Error("rebench variants should target runtime and full respectively");
  }}
  if (!auditMessages.some((message) => message.includes("GPU 1"))) {{
    throw new Error("scoped admin tasks should report the selected runtime in the audit banner");
  }}
  context.promptFreeGpuResources(0);
  if (!presetModalConfig || !String(presetModalConfig.body || "").includes("GPU 0")) {{
    throw new Error("GPU free modal should mention the selected GPU");
  }}
  await presetModalConfig.onConfirm();
  const freeCalls = taskCalls.filter((row) => row.url === "/admin/power" && row.body.action === "free_gpu");
  if (!freeCalls.length || Number(freeCalls[0].body.gpu_index) !== 0) {{
    throw new Error("GPU free action should post free_gpu with the selected index");
  }}
  console.log("ui service action smoke ok");
}}).catch((error) => {{
  console.error(error);
  process.exitCode = 1;
}});
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
    for fixture in sorted(FIXTURES_DIR.glob("*.json")):
        try:
            payload = json.loads(read_text(fixture))
        except Exception:
            continue
        if isinstance(payload, dict):
            fixtures.append((fixture.stem, payload))
    return fixtures


def scan_potential_dead_code(js_source: str, html_source: str, css_source: str) -> list[str]:
    warnings: list[str] = []
    if "gpuPairingEnabled" in js_source:
        warnings.append("Legacy GPU pairing toggle identifiers still appear in the composed UI source")
    if "legacyGlobalDualScope" in js_source:
        warnings.append("legacyGlobalDualScope still appears in the composed UI source")
    if "systemUtilityRow" in js_source:
        warnings.append("Legacy systemUtilityRow layout shim still appears in the composed UI source")
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
