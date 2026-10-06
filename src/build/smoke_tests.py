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
        mutation_wrapper = '#!/bin/sh\nif [ "$1" = "-C" ] && [ "$3" = "rev-parse" ]; then exec "$CLUB3090_TEST_REAL_GIT" "$@"; fi\nprintf "%s\\n" "$*" >> "$CLUB3090_TEST_MUTATION_LOG"\nexit 99\n'
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
            "[install] Starting control, updater, and inference services",
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
        return True, "installer registered source-tree services without package-manager or git mutation"


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
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=str(root / "src"),
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
                "import control; assert control.admin_session_ok({'Cookie': ''}, '127.0.0.1') is False; "
                "token=control.create_admin_session('127.0.0.1'); "
                "assert control.admin_session_ok({'Cookie': f'{control.ADMIN_SESSION_COOKIE_NAME}={token}'}, '127.0.0.1'); "
                "assert not control.admin_session_ok({'Cookie': f'{control.ADMIN_SESSION_COOKIE_NAME}={token}'}, '10.0.0.2'); "
                "exec(\"class _Stop(Exception): pass\\n"
                "control.refresh_docker_logrotate_config=lambda: None\\n"
                "def _stop(delay): raise _Stop(delay)\\n"
                "control.time.sleep=_stop\\n"
                "try:\\n control.docker_logrotate_refresher()\\n"
                "except _Stop as stopped:\\n assert stopped.args[0] >= 300\\n"
                "else:\\n raise AssertionError('logrotate refresher returned')\"); "
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
def run_updater_status_smoke_test(root: Path) -> tuple[bool, str]:
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="club3090-updater-status-") as temp_raw:
        state_dir = Path(temp_raw) / "state"
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
        if "git pull" not in status.get("update_instructions", "") or "sudo ./install.sh" not in status.get("update_instructions", ""):
            return False, "updater did not direct operators to update the checkout and reinstall services"
        if status.get("automatic_updates") is not False or state_dir.exists():
            return False, "updater status enabled automatic updates or wrote mutable state"
        return True, "updater module reports checkout revision and manual update instructions"
