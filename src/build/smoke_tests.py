from __future__ import annotations

import ast
import json
import os
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROL_SOURCE_DIR = ROOT / "src" / "control"


def run_control_subprocess_timeout_smoke_test() -> tuple[bool, str]:
    watched = {"run", "check_call", "check_output"}
    offenders: list[str] = []
    for path in sorted(CONTROL_SOURCE_DIR.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            return False, f"Could not parse {path.relative_to(ROOT)}: {exc}"
        subprocess_aliases = {"subprocess"}
        direct_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "subprocess":
                        subprocess_aliases.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                for alias in node.names:
                    if alias.name in watched:
                        direct_names.add(alias.asname or alias.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = ""
            if isinstance(node.func, ast.Attribute) and node.func.attr in watched:
                if isinstance(node.func.value, ast.Name) and node.func.value.id in subprocess_aliases:
                    called = f"{node.func.value.id}.{node.func.attr}"
            elif isinstance(node.func, ast.Name) and node.func.id in direct_names:
                called = node.func.id
            if called and not any(keyword.arg == "timeout" for keyword in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {called} missing timeout=")
    if offenders:
        return False, "\n".join(offenders)
    return True, "control subprocess timeout smoke ok"


def run_repository_install_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-repo-install-") as temp_raw:
        temp = Path(temp_raw)
        bin_dir = temp / "bin"
        bin_dir.mkdir()
        upstream = temp / "upstream"
        (upstream / "scripts").mkdir(parents=True)
        (upstream / "models").mkdir()
        real_git = shutil.which("git")
        if not real_git:
            return False, "git executable required for isolated upstream fixture"
        subprocess.run([real_git, "-C", str(upstream), "init", "--quiet"], check=True, timeout=10)
        unit_dir = temp / "units"
        env_file = temp / "etc" / "club3090-server.env"
        state_dir = temp / "state"
        systemctl_log = temp / "systemctl.log"
        forbidden_log = temp / "forbidden-mutations.log"
        for relative in ("scripts/switch.sh", "scripts/setup.sh", "scripts/preflight.sh", "scripts/launch.sh"):
            script = upstream / relative
            if relative == "scripts/setup.sh":
                script.write_text('#!/bin/sh\nprintf "%s\\n%s\\n%s\\n%s\\n%s\\n" "$PWD" "$#" "$1" "${MODEL_DIR:-}" "${WEIGHTS:-}|${WITH_DFLASH_DRAFT:-}" >> "$CLUB3090_TEST_SETUP_LOG"\nexit 0\n', encoding="utf-8")
            else:
                script.write_text('#!/bin/sh\nprintf "%s\\n" "upstream script invoked: $0" >> "$CLUB3090_TEST_MUTATION_LOG"\nexit 99\n', encoding="utf-8")
            script.chmod(0o755)
        mutation_wrapper = '#!/bin/sh\nif [ "$1" = "-C" ] && [ "$3" = "rev-parse" ]; then if [ -n "${CLUB3090_TEST_SERVER_DIR:-}" ] && [ "$2" = "$CLUB3090_TEST_SERVER_DIR" ]; then printf "%s\\n" "$2"; exit 0; fi; exec "$CLUB3090_TEST_REAL_GIT" "$@"; fi\nprintf "%s\\n" "$*" >> "$CLUB3090_TEST_MUTATION_LOG"\nexit 99\n'
        wrappers = {
            "sudo": '#!/bin/sh\nexec "$@"\n',
            "systemctl": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CLUB3090_TEST_SYSTEMCTL_LOG"\nif [ "$1" = "is-active" ] && [ "${CLUB3090_TEST_HEALTH_DELAY:-}" = "1" ]; then marker="${CLUB3090_TEST_SYSTEMCTL_LOG}.$3"; if [ ! -e "$marker" ]; then : > "$marker"; exit 1; fi; fi\nexit 0\n',
            "docker": '#!/bin/sh\nif [ "$1 $2 $3" = "compose version" ]; then exit 0; fi\nexit 0\n',
            "git": mutation_wrapper,
            "apt": mutation_wrapper,
            "apt-get": mutation_wrapper,
            "pacman": mutation_wrapper,
            "yay": mutation_wrapper,
            "paru": mutation_wrapper,
            "pip": mutation_wrapper,
            "pip3": mutation_wrapper,
            "curl": '#!/bin/sh\nexit 0\n',
            "openssl": '#!/bin/sh\nexit 0\n',
            "pamtester": '#!/bin/sh\nexit 0\n',
        }
        for name, content in wrappers.items():
            wrapper = bin_dir / name
            wrapper.write_text(content, encoding="utf-8")
            wrapper.chmod(0o755)
        env = dict(os.environ)
        env.update(
            PATH=f"{bin_dir}:{Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
            CLUB3090_DIR=str(upstream),
            CLUB3090_CONTROL_DIR=str(state_dir),
            CLUB3090_SERVER_ENV_FILE=str(env_file),
            CLUB3090_SYSTEMD_UNIT_DIR=str(unit_dir),
            CLUB3090_TEST_SYSTEMCTL_LOG=str(systemctl_log),
            CLUB3090_TEST_MUTATION_LOG=str(forbidden_log),
            CLUB3090_TEST_SETUP_LOG=str(temp / "upstream-setup.log"),
            CLUB3090_TEST_REAL_GIT=real_git,
        )
        for key in ("CLUB3090_ADMIN_PORT", "CLUB3090_PROXY_PORT", "CLUB3090_ADMIN_BIND_HOST", "CLUB3090_PROXY_BIND_HOST", "DEFAULT_MODE", "CLUB3090_ENABLE_EXTRA_TEMPS"):
            env.pop(key, None)
        result = subprocess.run(
            [str(root / "install.sh")], cwd=str(root), env=env,
            capture_output=True, text=True, check=False, timeout=60,
        )
        if result.returncode:
            return False, result.stderr.strip() or result.stdout.strip() or "install.sh failed"
        if (temp / "upstream-setup.log").exists():
            return False, "installer unexpectedly invoked upstream model setup without a selector"
        for name in ("nvidia-smi", "sha256sum", "hf"):
            wrapper = bin_dir / name
            wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            wrapper.chmod(0o755)
        setup_env = dict(env)
        setup_env.update(
            CLUB3090_SETUP_MODEL="qwen3.6-27b",
            MODEL_DIR="/models/test",
            WEIGHTS="4bit",
            WITH_DFLASH_DRAFT="1",
            CLUB3090_TEST_HEALTH_DELAY="1",
        )
        setup_result = subprocess.run(
            [str(root / "install.sh")], cwd=str(root), env=setup_env,
            capture_output=True, text=True, check=False, timeout=60,
        )
        if setup_result.returncode:
            return False, setup_result.stderr.strip() or "selected-model installer run failed"
        installer_output = setup_result.stdout + setup_result.stderr
        for message in (
            "[install] Checking host dependencies",
            "[install] Running upstream model setup for qwen3.6-27b",
            "[install] Upstream model setup completed",
            "[install] Rendering systemd service units",
            "[install] Starting services; systemd may wait for startup",
            "[install] Installation complete",
            "[install] Checking service health with systemd (up to 60s)",
            "[install] Healthy: all managed services report active",
            "[install] Waiting for active services:",
        ):
            if message not in installer_output:
                return False, f"installer omitted progress message {message!r}"
        setup_lines = (temp / "upstream-setup.log").read_text(encoding="utf-8").splitlines()
        if setup_lines != [str(upstream), "1", "qwen3.6-27b", "/models/test", "4bit|1"]:
            return False, f"upstream setup did not receive expected checkout, model, and environment: {setup_lines!r}"
        control_unit_path = unit_dir / "club3090-control.service"
        if not control_unit_path.is_file():
            return False, "installer did not write the control service"
        control_unit = control_unit_path.read_text(encoding="utf-8")
        if f"WorkingDirectory={root}/src" not in control_unit:
            return False, "control service WorkingDirectory does not point at the checkout"
        if "ExecStart=/usr/bin/python3 -m control.http_server" not in control_unit:
            return False, "control service does not execute the direct HTTP server module"
        if f"EnvironmentFile=-{env_file}" not in control_unit:
            return False, "control service omits its configured environment file"
        benchmark_unit = (unit_dir / "club3090-benchmarks.service").read_text(encoding="utf-8")
        if f"WorkingDirectory={root}/src" not in benchmark_unit or "ExecStart=/usr/bin/python3 -m control.http_server --benchmark-worker" not in benchmark_unit:
            return False, "benchmark service does not execute the source-tree worker module"
        updater_unit = (unit_dir / "club3090-updater.service").read_text(encoding="utf-8")
        if f"WorkingDirectory={root}/src" not in updater_unit or "ExecStart=/usr/bin/python3 -m build.updater" not in updater_unit:
            return False, "updater service does not execute its package module"
        for unit_name, helper_name in (
            ("club3090-headless-x.service", "prepare-headless-x.sh"),
            ("club3090-console-log.service", "follow-vllm-log.sh"),
            ("club3090-vllm.service", "start-vllm-last-mode.sh"),
            ("club3090-cert-refresh.service", "refresh-ip-certificate.sh"),
        ):
            unit_text = (unit_dir / unit_name).read_text(encoding="utf-8")
            if f"ExecStart={root}/scripts/club3090-server/{helper_name}" not in unit_text:
                return False, f"{unit_name} does not execute its checkout-owned helper"
            if f"EnvironmentFile=-{env_file}" not in unit_text:
                return False, f"{unit_name} omits its configured environment file"
        vllm_unit = (unit_dir / "club3090-vllm.service").read_text(encoding="utf-8")
        if "ConditionKernelCommandLine=" in vllm_unit:
            return False, "vLLM unit retains a boot-mode condition"
        if "Wants=network-online.target club3090-control.service" not in vllm_unit or "After=docker.service network-online.target club3090-control.service" not in vllm_unit:
            return False, "vLLM unit does not order itself after and pull in the control service"
        if any(path.suffix in {".py", ".sh", ".html", ".css", ".js", ".c", ".h"} for path in state_dir.rglob("*") if path.is_file()):
            return False, "installer copied application source files into mutable runtime state"
        if not env_file.is_file():
            return False, "service configuration file was not written"
        config_text = env_file.read_text(encoding="utf-8")
        for expected in (
            f"CLUB3090_SERVER_DIR={root}",
            f"CLUB3090_DIR={upstream}",
            f"CLUB3090_CONTROL_DIR={state_dir}",
            "CLUB3090_ADMIN_PORT=8008",
            "CLUB3090_PROXY_PORT=8009",
            "CLUB3090_ADMIN_BIND_HOST=0.0.0.0",
            "CLUB3090_PROXY_BIND_HOST=0.0.0.0",
        ):
            if expected not in config_text:
                return False, f"service configuration omits {expected}"
        env_file.write_text(config_text + "OPERATOR_CUSTOM=preserve\\n", encoding="utf-8")
        override_env = dict(env)
        override_env.update(CLUB3090_ADMIN_PORT="8101", DEFAULT_MODE="vllm/default")
        rerun = subprocess.run(
            [str(root / "install.sh")], cwd=str(root), env=override_env,
            capture_output=True, text=True, check=False, timeout=60,
        )
        if rerun.returncode:
            return False, rerun.stderr.strip() or "idempotent installer rerun failed"
        config_text = env_file.read_text(encoding="utf-8")
        if "CLUB3090_ADMIN_PORT=8101" not in config_text or "DEFAULT_MODE=vllm/default" not in config_text or "OPERATOR_CUSTOM=preserve" not in config_text:
            return False, "installer did not apply supplied overrides while preserving operator settings"
        rerun = subprocess.run(
            [str(root / "install.sh")], cwd=str(root), env=env,
            capture_output=True, text=True, check=False, timeout=60,
        )
        if rerun.returncode:
            return False, rerun.stderr.strip() or "installer rerun without overrides failed"
        if "CLUB3090_ADMIN_PORT=8101" not in env_file.read_text(encoding="utf-8"):
            return False, "installer overwrote a configured port without an override"
        if forbidden_log.exists():
            return False, "installer invoked a package manager or mutated repository state"
        systemctl_calls = systemctl_log.read_text(encoding="utf-8")
        expected_enable = "enable club3090-control.service club3090-benchmarks.service club3090-updater.service club3090-vllm.service"
        if expected_enable not in systemctl_calls:
            return False, "installer did not enable the expected repository-native services"
        expected_stop = "stop club3090-control.service club3090-updater.service club3090-vllm.service"
        expected_start = "start club3090-control.service club3090-updater.service club3090-vllm.service"
        if expected_stop not in systemctl_calls or expected_start not in systemctl_calls:
            return False, "installer did not stop and start the deployment services"
        if not systemctl_calls.index(expected_enable) < systemctl_calls.index(expected_stop) < systemctl_calls.index(expected_start):
            return False, "installer did not stop and restart deployment services after enabling units"
        for service in ("club3090-control.service", "club3090-updater.service", "club3090-vllm.service"):
            health_check = f"is-active --quiet {service}"
            if health_check not in systemctl_calls or systemctl_calls.index(health_check) < systemctl_calls.index(expected_start):
                return False, f"installer did not check health for {service} after starting services"
        prior_systemctl_calls = systemctl_log.read_text(encoding="utf-8")
        updater_env = dict(env)
        updater_env["CLUB3090_RUNNING_FROM_UPDATER"] = "1"
        updater_run = subprocess.run(
            [str(root / "install.sh")], cwd=str(root), env=updater_env,
            capture_output=True, text=True, check=False, timeout=60,
        )
        if updater_run.returncode:
            return False, updater_run.stderr.strip() or "updater-owned installer run failed"
        updater_calls = systemctl_log.read_text(encoding="utf-8")[len(prior_systemctl_calls):]
        if "stop club3090-control.service club3090-vllm.service" not in updater_calls:
            return False, "updater-owned install did not restart control and vLLM services"
        if "stop club3090-control.service club3090-updater.service club3090-vllm.service" in updater_calls:
            return False, "updater-owned install stopped its own updater service"
        if "start club3090-control.service club3090-vllm.service" not in updater_calls:
            return False, "updater-owned install did not restart control and vLLM services"
        if "is-active --quiet club3090-updater.service" not in updater_calls:
            return False, "updater-owned install did not health-check the still-running updater service"
        dotenv_root = temp / "dotenv-server"
        dotenv_root.mkdir()
        shutil.copy2(root / "install.sh", dotenv_root / "install.sh")
        for name in ("src", "scripts", "systemd"):
            (dotenv_root / name).symlink_to(root / name, target_is_directory=True)
        dotenv_root.joinpath(".env").write_text(f"CLUB3090_DIR={upstream}\n", encoding="utf-8")
        dotenv_env_file = temp / "dotenv-etc" / "club3090-server.env"
        dotenv_env = dict(env)
        dotenv_env.pop("CLUB3090_DIR", None)
        dotenv_env.update(
            CLUB3090_CONTROL_DIR=str(temp / "dotenv-state"),
            CLUB3090_SERVER_ENV_FILE=str(dotenv_env_file),
            CLUB3090_SYSTEMD_UNIT_DIR=str(temp / "dotenv-units"),
            CLUB3090_TEST_SERVER_DIR=str(dotenv_root),
        )
        dotenv_result = subprocess.run(
            [str(dotenv_root / "install.sh")], cwd=str(dotenv_root), env=dotenv_env,
            capture_output=True, text=True, check=False, timeout=60,
        )
        if dotenv_result.returncode:
            return False, dotenv_result.stderr.strip() or "installer did not accept the repository .env upstream path"
        if f"CLUB3090_DIR={upstream}" not in dotenv_env_file.read_text(encoding="utf-8"):
            return False, "installer did not persist CLUB3090_DIR from the repository .env file"
        return True, "installer honors repository .env upstream path and updater-owned service lifecycle"


def run_repository_uninstall_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-repo-uninstall-") as temp_raw:
        temp = Path(temp_raw)
        bin_dir = temp / "bin"
        bin_dir.mkdir()
        unit_dir = temp / "units"
        unit_dir.mkdir()
        env_file = temp / "etc" / "club3090-server.env"
        env_file.parent.mkdir()
        env_file.write_text("CLUB3090_ADMIN_PORT=8008\n", encoding="utf-8")
        state_dir = temp / "state"
        state_dir.mkdir()
        sentinel = state_dir / "keep.json"
        sentinel.write_text("{}", encoding="utf-8")
        units = (
            "club3090-control.service",
            "club3090-benchmarks.service",
            "club3090-updater.service",
            "club3090-headless-x.service",
            "club3090-console-log.service",
            "club3090-vllm.service",
            "club3090-cert-refresh.service",
            "club3090-cert-refresh.timer",
        )
        for unit in units:
            (unit_dir / unit).write_text("[Unit]\n", encoding="utf-8")
        calls = temp / "systemctl.log"
        wrappers = {
            "sudo": '#!/bin/sh\nexec "$@"\n',
            "systemctl": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CLUB3090_TEST_SYSTEMCTL_LOG"\nexit 0\n',
        }
        for name, content in wrappers.items():
            wrapper = bin_dir / name
            wrapper.write_text(content, encoding="utf-8")
            wrapper.chmod(0o755)
        env = dict(os.environ)
        env.update(
            PATH=f"{bin_dir}:{os.environ.get('PATH', '')}",
            CLUB3090_SERVER_ENV_FILE=str(env_file),
            CLUB3090_SYSTEMD_UNIT_DIR=str(unit_dir),
            CLUB3090_TEST_SYSTEMCTL_LOG=str(calls),
        )
        result = subprocess.run(
            [str(root / "uninstall.sh")], cwd=str(root), env=env,
            capture_output=True, text=True, check=False, timeout=60,
        )
        if result.returncode:
            return False, result.stderr.strip() or result.stdout.strip() or "uninstall.sh failed"
        if env_file.exists() or any((unit_dir / unit).exists() for unit in units):
            return False, "uninstaller left registered services or configuration behind"
        if not sentinel.is_file():
            return False, "uninstaller removed mutable runtime data"
        uninstaller_output = result.stdout + result.stderr
        for message in (
            "[uninstall] Checking systemctl and privilege requirements",
            "[uninstall] Stopping and disabling Club-3090 Server services",
            f"[uninstall] Removing service configuration {env_file}",
            "[uninstall] Reloading systemd unit definitions",
            "[uninstall] Uninstallation complete",
        ):
            if message not in uninstaller_output:
                return False, f"uninstaller omitted progress message {message!r}"
        systemctl_calls = calls.read_text(encoding="utf-8")
        for unit in units:
            if f"disable --now {unit}" not in systemctl_calls:
                return False, f"uninstaller did not stop/disable {unit}"
        if "club3090-caddy.service" in systemctl_calls:
            return False, "uninstaller attempted to stop/disable the operator-managed Caddy unit"
        return True, "uninstaller removed service registration and configuration while preserving runtime data"
def run_installer_preflight_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-installer-preflight-") as temp_raw:
        temp = Path(temp_raw)
        bin_dir = temp / "bin"
        bin_dir.mkdir()
        unit_dir = temp / "units"
        wrappers = {
            "sudo": '#!/bin/sh\nexit 0\n',
            "systemctl": '#!/bin/sh\nexit 0\n',
            "git": '#!/bin/sh\nexit 0\n',
            "curl": '#!/bin/sh\nexit 0\n',
            "openssl": '#!/bin/sh\nexit 0\n',
            "docker": '#!/bin/sh\nexit 0\n',
        }
        for name, content in wrappers.items():
            wrapper = bin_dir / name
            wrapper.write_text(content, encoding="utf-8")
            wrapper.chmod(0o755)
        for name, target in (
            ("python3", sys.executable),
            ("bash", shutil.which("bash") or "/bin/bash"),
        ):
            (bin_dir / name).symlink_to(target)
        env = dict(os.environ)
        env.update(
            PATH=f"{bin_dir}:{Path(sys.executable).parent}",
            CLUB3090_SYSTEMD_UNIT_DIR=str(unit_dir),
            CLUB3090_SERVER_ENV_FILE=str(temp / "etc" / "club3090-server.env"),
        )
        result = subprocess.run(
            [str(root / "install.sh")], cwd=str(root), env=env,
            capture_output=True, text=True, check=False, timeout=30,
        )
        if result.returncode == 0 or "pamtester" not in result.stderr:
            return False, "installer did not report the missing pamtester prerequisite"
        if unit_dir.exists():
            return False, "installer wrote a unit directory before prerequisite checks passed"
        for name in ("pamtester", "nvidia-smi", "sha256sum"):
            wrapper = bin_dir / name
            wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            wrapper.chmod(0o755)
        missing_hf_env = dict(env)
        marker = temp / "upstream-setup.log"
        missing_hf_env.update(
            CLUB3090_SETUP_MODEL="qwen3.6-27b",
            CLUB3090_CONTROL_DIR=str(temp / "model-state"),
            CLUB3090_SERVER_ENV_FILE=str(temp / "model-etc" / "club3090-server.env"),
            CLUB3090_SYSTEMD_UNIT_DIR=str(temp / "model-units"),
            CLUB3090_TEST_SETUP_LOG=str(marker),
        )
        missing_hf = subprocess.run(
            [str(root / "install.sh")], cwd=str(root), env=missing_hf_env,
            capture_output=True, text=True, check=False, timeout=30,
        )
        if missing_hf.returncode == 0 or "Hugging Face CLI" not in missing_hf.stderr:
            return False, "selected-model preflight did not report missing Hugging Face CLI"
        if any(path.exists() for path in (
            Path(missing_hf_env["CLUB3090_CONTROL_DIR"]),
            Path(missing_hf_env["CLUB3090_SERVER_ENV_FILE"]).parent,
            Path(missing_hf_env["CLUB3090_SYSTEMD_UNIT_DIR"]),
            marker,
        )):
            return False, "selected-model dependency failure wrote state, service registration, or invoked upstream setup"
        return True, "installer reports missing prerequisites before filesystem writes"

def run_control_runtime_globals_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-control-globals-") as temp_raw:
        temp = Path(temp_raw)
        env = dict(os.environ)
        env.update(
            CLUB3090_CONTROL_DIR=str(temp / "state"),
            CLUB3090_DIR=str(temp / "upstream"),
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=str(root / "src"),
        )
        audit = r"""
import builtins, dis, json, types
import control

functions = {}
def add(name, value):
    if isinstance(value, types.FunctionType):
        functions.setdefault(id(value), (name, value))
def inspect_class(prefix, cls):
    for name, value in vars(cls).items():
        qualified = prefix + "." + name
        if isinstance(value, (staticmethod, classmethod)):
            add(qualified, value.__func__)
        elif isinstance(value, property):
            for suffix, fn in (("getter", value.fget), ("setter", value.fset), ("deleter", value.fdel)):
                if fn is not None:
                    add(qualified + "." + suffix, fn)
        else:
            add(qualified, value)
for name, value in vars(control).items():
    if isinstance(value, type):
        inspect_class("control." + name, value)
    else:
        add("control." + name, value)
failures = set()
for qualified, fn in functions.values():
    pending, seen = [fn.__code__], set()
    while pending:
        code = pending.pop()
        if id(code) in seen:
            continue
        seen.add(id(code))
        for instruction in dis.get_instructions(code):
            if instruction.opname == "LOAD_GLOBAL":
                name = instruction.argval
                if name not in fn.__globals__ and not hasattr(builtins, name):
                    failures.add(f"{qualified}: {name}")
        pending.extend(value for value in code.co_consts if isinstance(value, types.CodeType))
result = sorted(failures)
print(json.dumps(result))
raise SystemExit(bool(result))
"""
        check_env = dict(env)
        check_env["CLUB3090_CONTROL_DIR"] = str(temp / "model-update-state")
        check = subprocess.run(
            [
                sys.executable, "-c",
                "import control.shared as shared; events=[]; shared.append_audit_text_line=events.append; "
                "shared.refresh_status_snapshot=lambda: None; "
                "summary=shared.run_model_update_check('smoke', {'variants': []}); "
                "assert isinstance(summary, dict); "
                "assert not any('_repo_subprocess_env' in str(event) or 'NameError' in str(event) for event in events); "
                "print('model update checker passed')",
            ],
            cwd=str(root / "src"), env=check_env, capture_output=True,
            text=True, check=False, timeout=30,
        )
        if check.returncode:
            return False, check.stderr.strip() or "scheduled model-update check failed"
        result = subprocess.run(
            [sys.executable, "-c", audit],
            cwd=str(root / "src"), env=env, capture_output=True,
            text=True, check=False, timeout=60,
        )
        try:
            failures = json.loads(result.stdout)
        except ValueError as exc:
            diagnostic = result.stderr.strip() or result.stdout.strip() or str(exc)
            return False, f"control runtime global audit emitted malformed JSON: {diagnostic}"
        if not isinstance(failures, list) or any(not isinstance(item, str) for item in failures):
            return False, f"control runtime global audit emitted invalid JSON payload: {result.stdout.strip()}"
        if result.returncode or failures:
            details = "\n".join(failures) or result.stderr.strip() or result.stdout.strip()
            return False, f"unresolved control globals:\n{details}"
        return True, "assembled control globals resolve and the scheduled model-update check completes"


def run_control_module_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-control-module-") as temp_raw:
        temp = Path(temp_raw)
        state_dir = temp / "state"
        upstream = temp / "upstream"
        upstream.mkdir()
        env = dict(os.environ)
        env.update(
            CLUB3090_CONTROL_DIR=str(state_dir),
            CLUB3090_DIR=str(upstream),
            CLUB3090_ADMIN_AUTH_DENIAL_LOG_WINDOW_SECONDS="7",
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=str(root / "src"),
        )
        compose_rel = "models/qwen3.8-27b/llama-cpp/compose/single/iq4xs/base.yml"
        compose_path = upstream / compose_rel
        compose_path.parent.mkdir(parents=True)
        compose_path.write_text(
            "# Profile (at-a-glance):\n"
            "#   Model: Qwen 3.8 27B\n"
            "#   Topology: Single GPU\n"
            "#   Status: 🧪 Experimental\n"
            "services:\n"
            "  qwen38-upstream:\n"
            "    image: llama.cpp\n"
            "    ports:\n"
            "      - \"8020:8080\"\n"
            "    command: -m /models/qwen38.gguf\n",
            encoding="utf-8",
        )
        registry_path = upstream / "scripts/lib/profiles/compose_registry.py"
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(
            "COMPOSE_REGISTRY = {\n"
            "    'llamacpp/qwen38-upstream-single': {\n"
            "        'model': 'qwen3.8-27b', 'engine': 'llama-cpp-local',\n"
            f"        'compose_path': {compose_rel!r}, 'tp': 1, 'default_port': 8020,\n"
            "    },\n"
            "}\n",
            encoding="utf-8",
        )
        inventory = subprocess.run(
            [sys.executable, "-m", "control.http_server", "--rebuild-inventory"],
            cwd=str(root / "src"), env=env, capture_output=True,
            text=True, check=False, timeout=30,
        )
        if inventory.returncode:
            return False, inventory.stderr.strip() or "control inventory module command failed"
        try:
            payload = json.loads(inventory.stdout)
        except ValueError as exc:
            return False, f"control inventory output was not JSON: {exc}"
        if payload.get("ok") is not True or not (state_dir / "runtime_inventory.json").is_file():
            return False, "control module did not rebuild inventory under CLUB3090_CONTROL_DIR"
        rebuilt_inventory = json.loads((state_dir / "runtime_inventory.json").read_text(encoding="utf-8"))
        qwen_models = [row for row in rebuilt_inventory.get("models", []) if row.get("model_id") == "qwen3.8-27b"]
        qwen_rows = [row for row in rebuilt_inventory.get("variants", []) if row.get("model_id") == "qwen3.8-27b"]
        selectors = {row.get("selector") or row.get("upstream_tag") for row in qwen_rows}
        origins = {row.get("inventory_origin") for row in qwen_rows}
        required_qwen_selectors = {
            "llamacpp/qwen38-upstream-single",
            "llamacpp/qwen38-27b-orcarouter-uncensored-single-iq4xs",
            "llamacpp/qwen38-27b-hauhaucs-aggressive-single-iq4xs",
        }
        if len(qwen_models) != 1 or not required_qwen_selectors.issubset(selectors) or "control_catalog" not in origins:
            return False, f"upstream and control Qwen 3.8 catalog rows did not merge: models={len(qwen_models)} selectors={sorted(selectors)} origins={sorted(origins)}"
        worker = subprocess.run(
            [sys.executable, "-m", "control.http_server", "--benchmark-worker"],
            cwd=str(root / "src"), env=env, capture_output=True,
            text=True, check=False, timeout=30,
        )
        if worker.returncode:
            return False, worker.stderr.strip() or "idle benchmark worker module command failed"
        assets = subprocess.run(
            [
                sys.executable, "-c",
                "import control; assert control.ADMIN_AUTH_DENIAL_LOG_WINDOW_SECONDS == 7; "
                "control.admin_auth_denial_state.clear(); control.admin_auth_denial_state[('stale','/old')] = 1.0; "
                "control.time.time=lambda: 1000.0; "
                "assert control.should_log_admin_auth_denial('192.0.2.1','/admin'); "
                "assert not control.should_log_admin_auth_denial('192.0.2.1','/admin'); "
                "assert ('stale','/old') not in control.admin_auth_denial_state; "
                "control._shared.DEBUG_LOGS=True; events=[]; control._shared.log_audit=lambda event, **kwargs: events.append(event); "
                "exec(\"with control.suppress_chat_debug_audit():\\n control.debug_audit('chat_test')\"); "
                "assert not events; control.debug_audit('chat_test'); assert events == ['debug_chat_test']; "
                "control.docker_log_path_cache.clear(); calls=[]; "
                "control.subprocess.check_output=lambda *args, **kwargs: (calls.append(args), '/var/lib/docker/containers/test/test-json.log')[1]; "
                "assert control._docker_log_path('test-container') == '/var/lib/docker/containers/test/test-json.log'; "
                "assert control._docker_log_path('test-container') == '/var/lib/docker/containers/test/test-json.log'; "
                "assert len(calls) == 1; "
                "assert control.admin_session_ok({'Cookie': ''}, '127.0.0.1') is False; "
                "token=control.create_admin_session('127.0.0.1'); "
                "assert control.admin_session_ok({'Cookie': f'{control.ADMIN_SESSION_COOKIE_NAME}={token}'}, '127.0.0.1'); "
                "exec(\"class _Stop(Exception): pass\\n"
                "control.refresh_docker_logrotate_config=lambda: None\\n"
                "def _stop(delay): raise _Stop(delay)\\n"
                "control.time.sleep=_stop\\n"
                "try:\\n control.docker_logrotate_refresher()\\n"
                "except _Stop as stopped:\\n assert stopped.args[0] >= 300\\n"
                "else:\\n raise AssertionError('logrotate refresher returned')\"); "
                "control.startup_time=1000.0; "
                "warming=control.build_status_stale_overlay_snapshot({}, 'status snapshot is warming up'); "
                "assert isinstance(warming['control_started_at'], int) and warming['uptime_seconds'] >= 0 and isinstance(warming['metrics'], dict); "
                "error=control.build_status_error_snapshot('smoke failure'); "
                "assert isinstance(error['control_started_at'], int) and error['uptime_seconds'] >= 0 and isinstance(error['metrics'], dict) and error['status_error'] == 'smoke failure'; "
                "control.admin_stream_registry.clear(); "
                "import control.http_server as server; handler=object.__new__(server.AdminHandler); handler.headers={'X-Forwarded-For':'192.0.2.8','User-Agent':'smoke'}; handler.client_address=('127.0.0.1',1234); "
                "key,first=handler.begin_admin_stream('status'); replacement_key,second=handler.begin_admin_stream('status'); "
                "assert key == replacement_key and first.is_set() and control.admin_stream_registry[key] is second; "
                "handler.end_admin_stream(key,first); assert control.admin_stream_registry[key] is second; "
                "handler.end_admin_stream(key,second); assert key not in control.admin_stream_registry; control.admin_stream_registry.clear(); "
                "html=control.get_admin_html_template(); "
                "assert 'renderAIStudioLaneActions' in html; "
                "assert 'Start this inference runtime automatically at boot' in html; "
                "assert 'toggle_enabled' in html; print(len(html))",
            ],
            cwd=str(root / "src"), env=env, capture_output=True,
            text=True, check=False, timeout=30,
        )
        if assets.returncode or not assets.stdout.strip().isdigit():
            return False, assets.stderr.strip() or "source web assets did not render through the package runtime"
        if (root / "runtime_inventory.json").exists():
            return False, "control module wrote runtime inventory outside the selected state directory"
        return True, "control, benchmark-worker, and web assets execute from source modules with isolated state"

def run_admin_path_routing_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-admin-path-routing-") as temp_raw:
        temp = Path(temp_raw)
        control_dir = temp / "control"
        upstream_dir = temp / "upstream"
        control_dir.mkdir()
        upstream_dir.mkdir()
        env = dict(os.environ)
        env.update(
            CLUB3090_CONTROL_DIR=str(control_dir),
            CLUB3090_DIR=str(upstream_dir),
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=str(root / "src"),
        )
        code = r'''
import email.message
import io
import json
import threading
import control.http_server as server

def invoke(path):
    handler = object.__new__(server.AdminHandler)
    handler.path = path
    handler.command = "GET"
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.close_connection = False
    handler.wfile = io.BytesIO()
    handler.rfile = io.BytesIO()
    handler.headers = email.message.Message()
    handler.client_address = ("127.0.0.1", 12345)
    handler._headers_buffer = []
    handler.require_auth = lambda: True
    server.AdminHandler.do_GET(handler)
    response = handler.wfile.getvalue()
    head, separator, body = response.partition(b"\r\n\r\n")
    assert separator, f"response headers missing for {path}"
    lines = head.decode("latin1").split("\r\n")
    headers = {
        name.lower(): value
        for name, value in (line.split(": ", 1) for line in lines[1:] if ": " in line)
    }
    return lines[0], headers, body

shell_paths = (
    "/admin",
    "/admin/system",
    "/admin/ai-studio",
    "/admin/benchmarks",
    "/admin/metrics",
    "/admin/users",
    "/admin/scripts",
    "/admin/logs",
    "/admin/chat",
)
for path in shell_paths:
    status, headers, body = invoke(path)
    assert status == "HTTP/1.1 200 OK", (path, status)
    assert headers.get("content-type", "").startswith("text/html"), (path, headers)
    assert headers.get("cache-control") == "no-store, no-cache, must-revalidate", (path, headers)
    assert b'<section id="overview"' in body, f"{path} did not serve the admin shell"

status, _, _ = invoke("/admin/not-a-tab")
assert status.startswith("HTTP/1.1 404"), status
status, headers, body = invoke("/admin/benchmarks/status?live=1")
benchmark_payload = json.loads(body)
assert status == "HTTP/1.1 200 OK" and headers.get("content-type", "").startswith("application/json"), (status, headers)
assert benchmark_payload.get("ok") is True and isinstance(benchmark_payload.get("benchmarks"), dict), benchmark_payload

status, _, body = invoke("/admin/scripts/list?include_internal=1")
scripts_payload = json.loads(body)
assert status == "HTTP/1.1 200 OK" and scripts_payload.get("ok") is True, (status, scripts_payload)
assert isinstance(scripts_payload.get("scripts"), list) and isinstance(scripts_payload.get("job"), dict), scripts_payload

status, _, body = invoke("/admin/users/list")
users_payload = json.loads(body)
assert status == "HTTP/1.1 200 OK" and users_payload.get("ok") is True, (status, users_payload)
assert isinstance(users_payload.get("users"), list) and isinstance(users_payload.get("groups"), list), users_payload

real_begin_stream = server.AdminHandler.begin_admin_stream
def begin_stopped_stream(handler, label):
    key, stop_event = real_begin_stream(handler, label)
    stop_event.set()
    return key, stop_event
server.AdminHandler.begin_admin_stream = begin_stopped_stream
status, headers, _ = invoke("/admin/log-stream?source=benchmarks&tail=17")
assert status == "HTTP/1.1 200 OK" and headers.get("content-type") == "text/event-stream", (status, headers)
status, headers, body = invoke("/admin/logs?source=benchmarks")
assert status == "HTTP/1.1 200 OK" and headers.get("content-type", "").startswith("text/html"), (status, headers)
assert b'<section id="overview"' in body
print("canonical admin paths and relocated GET APIs passed")
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(root / "src"),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
        if result.returncode:
            return False, result.stderr.strip() or result.stdout.strip() or "admin path routing smoke failed"
        return True, result.stdout.strip() or "admin path routing smoke passed"


def run_updater_status_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-updater-status-") as temp_raw:
        temp = Path(temp_raw)
        state_dir = temp / "state"
        env = dict(os.environ)
        env.update(
            CLUB3090_CONTROL_DIR=str(state_dir),
            CLUB3090_SERVER_DIR=str(root),
            PYTHONDONTWRITEBYTECODE="1",
        )
        result = subprocess.run(
            [sys.executable, "-m", "build.updater", "--status"],
            cwd=str(root / "src"), env=env, capture_output=True,
            text=True, check=False, timeout=15,
        )
        if result.returncode:
            return False, result.stderr.strip() or "updater module status command failed"
        try:
            status = json.loads(result.stdout)
        except ValueError as exc:
            return False, f"updater status output was not JSON: {exc}"
        expected = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        revision = expected.stdout.strip() if expected.returncode == 0 else ""
        if not revision or status.get("repository_revision") != revision:
            return False, "updater did not report the checked-out Git revision"
        instructions = str(status.get("update_instructions") or "")
        if "System Update" not in instructions or "tracking branches" not in instructions or "git pull" in instructions:
            return False, "updater status did not describe the clean-tracking System Update"
        if status.get("automatic_updates") is not False or state_dir.exists():
            return False, "updater status enabled automatic updates or wrote mutable state"
        server_dir = temp / "server"
        upstream_dir = temp / "upstream"
        bin_dir = temp / "bin"
        for directory in (server_dir, upstream_dir, bin_dir):
            directory.mkdir()
        (server_dir / "src").mkdir()
        trace = temp / "system-update.trace"
        git_wrapper = bin_dir / "git"
        git_wrapper.write_text(
            "#!/bin/sh\n"
            "printf 'git %s\\n' \"$*\" >> \"$CLUB3090_TEST_TRACE\"\n"
            "repo=$2; shift 2\n"
            "case \"$1\" in\n"
            "  rev-parse) if [ \"$2\" = \"--show-toplevel\" ]; then "
            "if [ \"$CLUB3090_TEST_DUBIOUS\" = \"$repo\" ]; then printf 'fatal: detected dubious ownership\\n' >&2; exit 1; fi; "
            "printf '%s\\n' \"$repo\"; "
            "elif [ \"$CLUB3090_TEST_DIRTY\" = \"$repo\" ] && [ \"$2\" = \"--abbrev-ref\" ]; then exit 1; "
            "else printf 'origin/main\\n'; fi ;;\n"
            "  status) if [ \"$CLUB3090_TEST_DIRTY\" = \"$repo\" ]; then printf ' M file\\n'; fi ;;\n"
            "  fetch|merge) : ;;\n"
            "esac\n"
            "exit 0\n",
            encoding="utf-8",
        )
        git_wrapper.chmod(0o755)
        runuser_wrapper = bin_dir / "runuser"
        runuser_wrapper.write_text(
            "#!/bin/sh\n"
            "printf 'runuser %s\\n' \"$*\" >> \"$CLUB3090_TEST_TRACE\"\n"
            "[ \"$1\" = \"--user\" ] || exit 2\n"
            "shift 2\n"
            "[ \"$1\" = \"--\" ] || exit 2\n"
            "shift\n"
            "exec \"$@\"\n",
            encoding="utf-8",
        )
        runuser_wrapper.chmod(0o755)
        python_wrapper = bin_dir / "python3"
        python_wrapper.write_text(
            "#!/bin/sh\nprintf 'python %s\\n' \"$*\" >> \"$CLUB3090_TEST_TRACE\"\nexit 0\n",
            encoding="utf-8",
        )
        python_wrapper.chmod(0o755)
        bash_wrapper = bin_dir / "bash"
        bash_wrapper.write_text(
            "#!/bin/sh\nprintf 'install %s\\n' \"$*\" >> \"$CLUB3090_TEST_TRACE\"\nexit 0\n",
            encoding="utf-8",
        )
        bash_wrapper.chmod(0o755)
        command_env = dict(env)
        command_env.update(
            CLUB3090_SERVER_DIR=str(server_dir),
            CLUB3090_DIR=str(upstream_dir),
            CLUB3090_CONTROL_DIR=str(temp / "update-state"),
            CLUB3090_TEST_TRACE=str(trace),
            PATH=f"{bin_dir}:{os.environ.get('PATH', '')}",
            PYTHONPATH=str(root / "src"),
        )
        build = subprocess.run(
            [
                sys.executable, "-c",
                "import json; from build.updater import build_update_command; "
                "print(json.dumps(build_update_command('update', 'club3090')))",
            ],
            cwd=str(root / "src"), env=command_env, capture_output=True,
            text=True, check=False, timeout=15,
        )
        if build.returncode:
            return False, build.stderr.strip() or "System Update command construction failed"
        _scope, _label, command, _source = json.loads(build.stdout)
        clean = subprocess.run(
            ["/bin/bash", "-c", command], cwd=str(root), env=command_env,
            capture_output=True, text=True, check=False, timeout=15,
        )
        if clean.returncode:
            return False, clean.stderr.strip() or "clean tracking-checkout System Update command failed"
        trace_lines = trace.read_text(encoding="utf-8").splitlines()
        milestones = [
            f"git -C {server_dir} fetch --prune origin",
            f"git -C {server_dir} merge --ff-only @{{u}}",
            f"git -C {upstream_dir} fetch --prune origin",
            f"git -C {upstream_dir} merge --ff-only @{{u}}",
            "python -m control.http_server --rebuild-inventory",
            f"install {server_dir}/install.sh",
        ]
        positions = [next((index for index, line in enumerate(trace_lines) if milestone in line), -1) for milestone in milestones]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            return False, f"System Update stages did not run in order: {trace_lines!r}"
        for repo in (server_dir, upstream_dir):
            repo_uid = os.stat(repo).st_uid
            passwd = subprocess.run(
                ["getent", "passwd", str(repo_uid)],
                capture_output=True, text=True, check=False, timeout=5,
            )
            if passwd.returncode or not passwd.stdout.strip():
                return False, f"no passwd entry for fixture owner uid {repo_uid}"
            repo_user = passwd.stdout.split(":", 1)[0]
            if not any(
                line.startswith(f"runuser --user {repo_user} -- env HOME=")
                and f"git -C {repo}" in line
                for line in trace_lines
            ):
                return False, f"System Update did not run Git as worktree owner {repo_user} (uid {repo_uid}): {trace_lines!r}"
        trace.write_text("", encoding="utf-8")
        dirty_env = dict(command_env)
        dirty_env["CLUB3090_TEST_DIRTY"] = str(upstream_dir)
        dirty = subprocess.run(
            ["/bin/bash", "-c", command], cwd=str(root), env=dirty_env,
            capture_output=True, text=True, check=False, timeout=15,
        )
        dirty_lines = trace.read_text(encoding="utf-8").splitlines()
        if dirty.returncode == 0 or "local changes" not in dirty.stderr or any(" fetch " in line or " merge " in line for line in dirty_lines):
            return False, f"System Update did not stop before mutating a dirty checkout: rc={dirty.returncode} stderr={dirty.stderr!r} trace={dirty_lines!r}"
        trace.write_text("", encoding="utf-8")
        dubious_env = dict(command_env)
        dubious_env["CLUB3090_TEST_DUBIOUS"] = str(server_dir)
        dubious = subprocess.run(
            ["/bin/bash", "-c", command], cwd=str(root), env=dubious_env,
            capture_output=True, text=True, check=False, timeout=15,
        )
        dubious_lines = trace.read_text(encoding="utf-8").splitlines()
        if dubious.returncode == 0 or "detected dubious ownership" not in dubious.stderr or any(" fetch " in line or " merge " in line for line in dubious_lines):
            return False, f"System Update hid a Git ownership failure or mutated before preflight: rc={dubious.returncode} stderr={dubious.stderr!r} trace={dubious_lines!r}"
        return True, "updater runs Git as checkout owner and guards clean, dirty, and ownership failures"

def run_strata_preset_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-strata-preset-") as temp_raw:
        temp = Path(temp_raw)
        state_dir = temp / "state"
        upstream = temp / "upstream"
        upstream.mkdir()
        env = dict(os.environ)
        env.update(
            CLUB3090_CONTROL_DIR=str(state_dir),
            CLUB3090_DIR=str(upstream),
            CLUB3090_SERVER_DIR=str(root),
            PYTHONPATH=str(root / "src"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        rebuild = subprocess.run(
            [sys.executable, "-m", "control.http_server", "--rebuild-inventory"],
            cwd=str(root / "src"), env=env, capture_output=True,
            text=True, check=False, timeout=30,
        )
        if rebuild.returncode:
            return False, rebuild.stderr.strip() or "Strata inventory rebuild failed"
        inventory_path = state_dir / "runtime_inventory.json"
        if not inventory_path.is_file():
            return False, "Strata inventory rebuild did not write isolated inventory"
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return False, f"Strata inventory was not valid JSON: {exc}"
        expected = {
            "strata/qwen3.8-flash-next-q2-0": ("Q2_0", 37.6, "qwen"),
            "strata/qwen3.8-flash-next-iq2-xs": ("IQ2_XS", 39.2, "qwen"),
            "strata/qwen3.8-flash-next-iq3-xxs": ("IQ3_XXS", 47.0, "qwen"),
            "strata/qwen3.8-flash-next-iq3-s": ("IQ3_S", 54.8, "qwen"),
            "strata/qwen3.8-flash-next-coder-iq1-m": ("IQ1_M", None, "coder"),
            "strata/swift-1-5-iq2-xs": ("IQ2_XS", None, "swift"),
            "strata/swift-1-5-iq3-xxs": ("IQ3_XXS", None, "swift"),
            "strata/unsloth-ud-iq4-xs": ("UD-IQ4_XS", None, "unsloth"),
            "strata/unsloth-ud-q4-k-xl": ("UD-Q4_K_XL", None, "unsloth"),
            "strata/orcarouter-qwen3.8-flash-next-uncensored-iq3-xxs": ("IQ3_XXS", None, "orca"),
        }
        rows = {
            row.get("selector") or row.get("upstream_tag"): row
            for row in inventory.get("variants", [])
            if (row.get("selector") or row.get("upstream_tag")) in expected
        }
        if set(rows) != set(expected):
            return False, f"Strata inventory selectors differ: {sorted(rows)}"
        compose_paths, data_paths = set(), set()
        for selector, (model_token, guidance, family) in expected.items():
            row = rows[selector]
            compose = Path(row.get("compose_abs_path") or row.get("compose_path") or "")
            data = Path(row.get("strata_data_path") or row.get("data_path") or "")
            compose_paths.add(str(compose))
            data_paths.add(str(data))
            if row.get("strata_model_token") != model_token:
                return False, f"{selector} has wrong Strata MODEL token"
            expected_model_id = "qwen3.8-flash-next" if family != "orca" else "orcarouter-qwen3.8-flash-next-uncensored-iq3_xxs"
            if (
                row.get("model_id") != expected_model_id
                or row.get("engine") != "strata"
                or row.get("engine_display") != "Strata"
                or row.get("profile_engine_id") != "strata"
                or row.get("strata_family") != family
                or row.get("topology") != "single"
                or row.get("requires_min_gpu_count") != 1
                or row.get("requires_sm") != "75+"
            ):
                return False, f"{selector} lost its Strata model, family, engine, topology, or hardware identity"
            if guidance is not None and float(row.get("recommended_combined_memory_gb") or 0) != guidance:
                return False, f"{selector} lost advisory combined-memory guidance"
            if model_token in {"UD-Q4_K_XL", "IQ3_XXS"} and (family == "orca" or family == "unsloth"):
                if row.get("status_kind") != "experimental" or row.get("install_state") not in {"requires_download", "ready"}:
                    return False, f"{selector} must remain installable with its experimental state"
            if family == "coder" and (row.get("download_size_gb") != 58.4 or row.get("recommended_system_memory_gb") != 32):
                return False, f"{selector} lost its Coder advisory sizing"
            if family == "unsloth" and model_token == "UD-IQ4_XS":
                if row.get("download_size_gb") != 93.7 or row.get("recommended_system_memory_gb") != 48 or row.get("recommended_resident_memory_gb") != 59.5 or not row.get("requires_nvme"):
                    return False, f"{selector} lost its UD-IQ4_XS advisory sizing"
            if family == "unsloth" and model_token == "UD-Q4_K_XL":
                if row.get("download_size_gb") != 111.3 or row.get("recommended_system_memory_gb") != 48 or row.get("recommended_resident_memory_gb") != 77 or not row.get("requires_nvme"):
                    return False, f"{selector} lost its UD-Q4_K_XL advisory sizing"
            if family == "orca" and (row.get("strata_install_mode") != "orca" or row.get("download_size_gb") != 85.2):
                return False, f"{selector} lost its distinct Orca install contract"
            if row.get("hardware_blocked") not in (False, None):
                return False, f"{selector} was unexpectedly hardware-blocked in the inventory fixture"
            if not compose.is_file() or not data.is_dir():
                return False, f"{selector} does not have its isolated Compose/data paths"
            compose_text = compose.read_text(encoding="utf-8")
            if (
                f"FAMILY: {family}" not in compose_text
                or f"MODEL: {model_token}" not in compose_text
                or "${PORT}:8080" not in compose_text
                or 'PORT: "8080"' not in compose_text
                or "/data" not in compose_text
                or "memlock:" not in compose_text
                or "driver: nvidia" not in compose_text
                or 'API_KEY: "${STRATA_API_KEY}"' not in compose_text
                or "start_period: 600s" not in compose_text
            ):
                return False, f"{selector} Compose contract is incomplete"
        if len(compose_paths) != len(expected) or len(data_paths) != len(expected):
            return False, "Strata selectors do not have distinct Compose and data directories"
        source_paths = {row.get("strata_source_path") for row in rows.values()}
        images = {row.get("strata_image") for row in rows.values()}
        commits = {row.get("strata_commit") for row in rows.values()}
        expected_source = str(state_dir / "builtin-models" / "strata" / "source")
        if source_paths != {expected_source} or images != {"club3090-strata:v0.1.40.1"}:
            return False, "Strata variants do not share the pinned source and image contract"
        evaluator = r'''
import json
import os
from unittest.mock import patch
import control
system = control

expected = set(json.loads(os.environ["STRATA_SMOKE_EXPECTED"]))
rows = {
    row.get("selector") or row.get("upstream_tag"): row
    for row in json.loads(os.environ["STRATA_SMOKE_ROWS"])
}

def evaluate(*, host="Linux", docker="/usr/bin/docker", nvidia="/usr/bin/nvidia-smi",
             runtime=True, cdi=False, gpu_output="0, 8.6, 580.1", gpu_rc=0, assigned=None):
    def run_cmd(command, timeout=None):
        if any("DiscoveredDevices" in argument for argument in command):
            devices = [{"Source": "cdi", "ID": "nvidia.com/gpu=0"}] if cdi else []
            return (0, json.dumps(devices))
        if "info" in command:
            return (0, json.dumps({"nvidia": {}} if runtime else {"runc": {}}))
        return (gpu_rc, gpu_output)
    with patch.object(system.platform, "system", return_value=host), \
         patch.object(system.shutil, "which",
                      side_effect=lambda name: docker if name == "docker" else nvidia), \
         patch.object(system, "run_cmd", side_effect=run_cmd):
        return system.evaluate_strata_hardware(assigned)

def blocked(result, phrase):
    assert result["hardware_blocked"] is True, result
    assert phrase.lower() in result["hardware_block_reason"].lower(), result

blocked(evaluate(host="Darwin"), "Linux")
blocked(evaluate(docker=None), "Docker")
blocked(evaluate(runtime=False), "neither the NVIDIA runtime nor")
assert evaluate(runtime=False, cdi=True)["hardware_blocked"] is False, evaluate(runtime=False, cdi=True)
blocked(evaluate(nvidia=None), "nvidia-smi")
blocked(evaluate(gpu_rc=1, gpu_output=""), "nvidia-smi")
blocked(evaluate(gpu_output="0, 8.6, 579.99"), "580")
blocked(evaluate(gpu_output="0, 9.9, 580.1"), "compute capability")

# The table evaluates all visible GPUs; a selected instance evaluates only
# its assigned GPU, even when another visible GPU is compatible.
mixed = "0, 9.9, 580.1\n1, 8.9, 580.1"
assert evaluate(gpu_output=mixed)["hardware_blocked"] is False
blocked(evaluate(gpu_output=mixed, assigned=[0]), "compute capability")
assert evaluate(gpu_output=mixed, assigned=[1])["hardware_blocked"] is False
assert evaluate(gpu_output=mixed, assigned=[0, 1])["hardware_blocked"] is False

# Every supported architecture is accepted, and enrichment returns independent
# row copies while preserving the install projection and all four selectors.
for capability in ("7.5", "8.0", "8.6", "8.9", "12.0"):
    assert evaluate(gpu_output=f"0, {capability}, 580.1")["hardware_blocked"] is False
source_rows = []
for index, row in enumerate(rows.values()):
    enriched_source = dict(row)
    enriched_source["install_state"] = f"state-{index}"
    enriched_source["install_reason"] = f"reason-{index}"
    source_rows.append(enriched_source)
with patch.object(system, "evaluate_strata_hardware",
                  return_value={"hardware_blocked": True, "hardware_block_reason": "fixture blocked"}):
    enriched = system.enrich_strata_hardware_rows(source_rows)
assert len(enriched) == len(expected), len(enriched)
assert {row.get("selector") or row.get("upstream_tag") for row in enriched} == set(expected)
for index, (original, result) in enumerate(zip(source_rows, enriched)):
    assert result is not original
    assert original.get("hardware_blocked") is not True
    assert result["hardware_blocked"] is True
    assert result["hardware_block_reason"] == "fixture blocked"
    assert result["install_state"] == original["install_state"] == f"state-{index}"
    assert result["install_reason"] == original["install_reason"] == f"reason-{index}"
control.load_runtime_inventory(force=True)
for selector, row in rows.items():
    for operation in (
        lambda selector=selector: control.preset_resource_delete_plan(selector),
        lambda selector=selector: control.preset_cache_delete_plan(selector),
        lambda selector=selector: control.start_model_update_job(variant_id=selector),
        lambda path=row["strata_data_path"]: control.delete_model_resource_paths([path]),
    ):
        try:
            operation()
        except ValueError as exc:
            assert "Strata" in str(exc), exc
        else:
            raise AssertionError(f"generic resource action was allowed for {selector}")

blocked_row = next(iter(rows.values()))
instance = {"id": "GPU0", "kind": "single", "gpu_index": 0, "gpu_indices": [0],
            "mode": blocked_row["selector"], "port": 19450}
with patch.object(control, "instance_variant_spec", return_value=blocked_row), \
     patch.object(control, "evaluate_strata_hardware",
                  return_value={"hardware_blocked": True, "hardware_block_reason": "fixture incompatible"}), \
     patch.object(control, "ensure_variant_install_ready", side_effect=AssertionError("install preflight ran")), \
     patch.object(control, "preflight_instance_docker_images", side_effect=AssertionError("image preflight ran")):
    try:
        control._instance_launch(instance)
    except RuntimeError as exc:
        assert "fixture incompatible" in str(exc), exc
    else:
        raise AssertionError("hardware-blocked Strata assignment launched")

with patch.object(control, "instance_variant_spec", return_value=blocked_row), \
     patch.object(control, "resolve_variant_launch_env", return_value={}):
    artifact_paths = control.write_instance_artifacts(instance)
env_text = open(artifact_paths["env"], encoding="utf-8").read()
override_text = open(artifact_paths["override"], encoding="utf-8").read()
assert "GPU=0" in env_text and "STRATA_API_KEY=" in env_text
assert all(name not in env_text + override_text for name in
           ("VLLM_CACHE_ROOT", "TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR"))
assert os.stat(artifact_paths["env"]).st_mode & 0o777 == 0o600
assert os.stat(artifact_paths["override"]).st_mode & 0o777 == 0o600
orca_row = next(row for row in rows.values() if row.get("strata_install_mode") == "orca")
orca_instance = {"id": "ORCA0", "kind": "single", "gpu_index": 0, "gpu_indices": [0],
                 "mode": orca_row["selector"], "port": 19451}
with patch.object(control, "instance_variant_spec", return_value=orca_row), \
     patch.object(control, "resolve_variant_launch_env", return_value={}):
    orca_paths = control.write_instance_artifacts(orca_instance)
orca_override = open(orca_paths["override"], encoding="utf-8").read()
assert "serve.server" in orca_override and "/data/config/strata-orca-iq3_xxs.json" in orca_override
assert "entrypoint: !override" in orca_override and "VLLM_CACHE_ROOT" not in orca_override
selector = blocked_row["selector"]
proxy_instance = {"id": "GPU0", "mode": selector, "gpu_index": 0,
                  "gpu_indices": [0], "port": 19450}
for path in (f"/v1/{selector}/models", f"/{selector}/models"):
    upstream, parsed_selector, _cap = control.parse_preset_path(path)
    assert parsed_selector == selector and upstream == "/v1/models", (path, upstream, parsed_selector)
with patch.object(control, "resolve_variant_spec", return_value=blocked_row), \
     patch.object(control, "visible_instances", return_value=[proxy_instance]), \
     patch.object(control, "instance_running", return_value=True), \
     patch.object(control, "instance_runtime_port", return_value=19450), \
     patch.object(control, "instance_runtime_container_name", return_value="club3090-gpu0"), \
     patch.object(control, "strata_runtime_ready", return_value=True), \
     patch.object(control, "vllm_container_names", side_effect=AssertionError("global vLLM lookup ran")):
    target, target_spec = control.proxy_running_target_for_selector(selector)
    assert target and target["id"] == "GPU0" and target_spec["engine"] == "strata"
with patch.object(control, "resolve_variant_spec", return_value=blocked_row), \
     patch.object(control, "visible_instances", return_value=[proxy_instance]), \
     patch.object(control, "instance_running", return_value=True), \
     patch.object(control, "instance_runtime_port", return_value=19450), \
     patch.object(control, "instance_runtime_container_name", return_value="club3090-gpu0"), \
     patch.object(control, "strata_runtime_ready", return_value=False):
    target, _target_spec = control.proxy_running_target_for_selector(selector)
    assert target is None, target
import tempfile
import control.shared as shared
orca_data = os.path.join(control.CONTROL_DIR, "builtin-models", "orca-smoke")
orca_variant = {"strata_data_path": orca_data, "strata_source_path": os.path.join(control.CONTROL_DIR, "builtin-models", "strata", "source"), "strata_image": "club3090-strata:v0.1.40.1"}
with patch.object(shared, "_run_hf_download_step", side_effect=AssertionError("download ran without token")):
    try:
        control._prepare_strata_orca("job", "[model-install orca]", orca_variant, {})
    except RuntimeError as exc:
        assert "authorized" in str(exc) and "gated repository" in str(exc), exc
    else:
        raise AssertionError("Orca install accepted missing HF token")
assert not os.path.exists(orca_data)
def fake_orca_download(_job, _prefix, step, _env):
    assert step["repo_ids"] == ["orcarouter/Qwen3.8-Flash-Next-Uncensored-GGUF"]
    for name in step["filenames"]:
        with open(os.path.join(step["local_dir"], name), "wb") as handle:
            handle.write(b"fixture shard")
class FakeProcess:
    def wait(self):
        return 0
def fake_orca_docker(argv, **_kwargs):
    command = argv[-1]
    assert "tools/iq_pack.py" in command and "--compat-bf16" in command
    assert "tools/mtp_fetch.py fetch --out /data/mtp" in command
    assert "tools/mtp_pack.py --src /data/mtp --experts q2_0 --out /data/mtp/mtp-q2_0.gguf" in command
    assert "tools/mtp_rt.py --gguf /data/mtp/mtp-q2_0.gguf --out /data/mtp/rt" in command
    assert "cp /opt/strata/data/draft_vocab.bin /data/mtp/rt/draft_vocab.bin" in command
    for relative in ("packs/orca-iq3_xxs/tokenizer", "packs/orca-iq3_xxs/index.txt",
                     "packs/orca-iq3_xxs/dense.bin", "packs/orca-iq3_xxs/native_experts.txt",
                     "mtp/mtp-q2_0.gguf", "mtp/rt/draft_vocab.bin"):
        target = os.path.join(orca_data, relative)
        if relative.endswith("/tokenizer"):
            os.makedirs(target, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(b"prepared")
    return FakeProcess()
with patch.object(shared, "_run_hf_download_step", side_effect=fake_orca_download), \
     patch.object(shared.subprocess, "Popen", side_effect=fake_orca_docker), \
     patch.object(shared, "_stream_process_output_to_audit"):
    control._prepare_strata_orca("job", "[model-install orca]", orca_variant, {"HF_TOKEN": "fixture-secret"})
orca_config = open(os.path.join(orca_data, "config", "strata-orca-iq3_xxs.json"), encoding="utf-8").read()
assert "orcarouter-qwen3.8-flash-next-uncensored-iq3_xxs" in orca_config
assert "fixture-secret" not in orca_config and "api_key" not in orca_config.lower()
import io
import threading
log_dir = tempfile.mkdtemp(prefix="strata-log-fixture-")
shared.CONTROL_DIR = log_dir
shared.AUDIT_LOG_FILE = os.path.join(log_dir, "audit.log")
shared.DEBUG_LOG_FILE = os.path.join(log_dir, "debug.log")
shared.append_audit_text_line("audit one\naudit two")
shared.append_debug_text_chunk("chunk one\nchunk two\n")
shared.append_debug_text_line("debug complete")
shared._stream_process_output_to_audit(type("Output", (), {"stdout": io.BytesIO(b"compiler warning one\ncompiler warning two\n")})(), "[model-install fixture]")
audit_entries = open(shared.AUDIT_LOG_FILE, encoding="utf-8").read().splitlines()
debug_entries = open(shared.DEBUG_LOG_FILE, encoding="utf-8").read().splitlines()
stamp_pattern = __import__("re").compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")
assert all(stamp_pattern.match(line) and not stamp_pattern.match(line[20:]) for line in audit_entries + debug_entries)
assert any("[model-install fixture] compiler warning one" in line for line in audit_entries)
import control.logs as runtime_logs
runtime_logs.LOG_BOOTSTRAP_MARKER = "fixture-bootstrap-marker"
watcher = object.__new__(runtime_logs.RuntimeLogWatcher)
watcher.container_name = "fixture"
watcher.cond = threading.Condition()
watcher.bootstrap_lines = []
watcher.bootstrap_done = False
watcher.tail_lines = __import__("collections").deque()
watcher.tail_bytes = 0
watcher.events = __import__("collections").deque(maxlen=10)
watcher.last_timestamp = ""
watcher.last_line = ""
watcher.seq = 0
watcher.status_message = ""
watcher._append_line("compiler warning", timestamp="2026-10-06T10:11:12.000000000Z")
assert watcher.bootstrap_lines == ["2026-10-06T10:11:12.000000000Z compiler warning"]
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
api_key = control.ensure_strata_api_key()
class ReadyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        authorized = self.path == "/v1/models" and self.headers.get("Authorization") == f"Bearer {api_key}"
        status = 200 if self.path == "/health" or authorized else 401
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b"{}")
    def log_message(self, *args):
        pass
server = ThreadingHTTPServer(("127.0.0.1", 0), ReadyHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    root_url = f"http://127.0.0.1:{server.server_port}/"
    assert system.strata_runtime_ready("fixture", root_url)
    with patch.object(control, "ensure_strata_api_key", return_value="invalid"):
        assert not system.strata_runtime_ready("fixture", root_url)
finally:
    server.shutdown()
'''
        evaluator_env = dict(env)
        evaluator_env["STRATA_SMOKE_EXPECTED"] = json.dumps(sorted(expected))
        evaluator_env["STRATA_SMOKE_ROWS"] = json.dumps(list(rows.values()))
        evaluator_run = subprocess.run(
            [sys.executable, "-c", evaluator],
            cwd=str(root / "src"), env=evaluator_env, capture_output=True,
            text=True, check=False, timeout=30,
        )
        if evaluator_run.returncode:
            return False, f"Strata hardware evaluator smoke failed: {evaluator_run.stderr.strip() or evaluator_run.stdout.strip()}"
        return True, "ten Strata variants preserve selector/token/family metadata, advisory fit details, Orca preparation, timestamped logs, and hardware evaluator behavior"
