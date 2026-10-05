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
        for relative in ("scripts/switch.sh", "scripts/setup.sh"):
            script = upstream / relative
            script.write_text('#!/bin/sh\nprintf "%s\\n" "upstream script invoked: $0" >> "$CLUB3090_TEST_MUTATION_LOG"\nexit 99\n', encoding="utf-8")
            script.chmod(0o755)
        mutation_wrapper = '#!/bin/sh\nif [ "$1" = "-C" ] && [ "$3" = "rev-parse" ]; then exec "$CLUB3090_TEST_REAL_GIT" "$@"; fi\nprintf "%s\\n" "$*" >> "$CLUB3090_TEST_MUTATION_LOG"\nexit 99\n'
        wrappers = {
            "sudo": '#!/bin/sh\nexec "$@"\n',
            "systemctl": '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CLUB3090_TEST_SYSTEMCTL_LOG"\nexit 0\n',
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
            CLUB3090_TEST_REAL_GIT=real_git,
        )
        result = subprocess.run(
            [str(root / "install.sh")], cwd=str(root), env=env,
            capture_output=True, text=True, check=False, timeout=60,
        )
        if result.returncode:
            return False, result.stderr.strip() or result.stdout.strip() or "install.sh failed"
        control_unit_path = unit_dir / "club3090-control.service"
        if not control_unit_path.is_file():
            return False, "installer did not write the control service"
        control_unit = control_unit_path.read_text(encoding="utf-8")
        if f"WorkingDirectory={root}/src" not in control_unit:
            return False, "control service WorkingDirectory does not point at the checkout"
        if "ExecStart=/usr/bin/python3 -m control.http_server" not in control_unit:
            return False, "control service does not execute the direct HTTP server module"
        if "EnvironmentFile=-/etc/club3090-server.env" not in control_unit:
            return False, "control service omits its environment file"
        if f"CLUB3090_DIR={upstream}" not in control_unit:
            return False, "control service upstream checkout path is incorrect"
        if "/opt/club3090-control/control.py" in control_unit or "CONTROL_PAYLOAD" in control_unit:
            return False, "control service references an installed/embedded application payload"
        if f"CLUB3090_CONTROL_DIR={state_dir}" not in control_unit:
            return False, "control service runtime-data path is incorrect"
        benchmark_unit = (unit_dir / "club3090-benchmarks.service").read_text(encoding="utf-8")
        if f"WorkingDirectory={root}/src" not in benchmark_unit or "ExecStart=/usr/bin/python3 -m control.http_server --benchmark-worker" not in benchmark_unit:
            return False, "benchmark service does not execute the source-tree worker module"
        updater_unit = (unit_dir / "club3090-updater.service").read_text(encoding="utf-8")
        if f"WorkingDirectory={root}/src" not in updater_unit or "ExecStart=/usr/bin/python3 -m build.updater" not in updater_unit:
            return False, "updater service does not execute its package module"
        if not env_file.is_file() or "CLUB3090_ADMIN_PORT=8008" not in env_file.read_text(encoding="utf-8"):
            return False, "default service configuration was not written"
        if forbidden_log.exists():
            return False, "installer invoked a package manager or mutated repository state"
        systemctl_calls = systemctl_log.read_text(encoding="utf-8")
        expected_enable = "enable club3090-control.service club3090-benchmarks.service club3090-updater.service"
        if expected_enable not in systemctl_calls:
            return False, "installer did not enable the expected repository-native services"
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
                "import control; html=control.get_admin_html_template(); "
                "assert 'renderAIStudioLaneActions' in html; print(len(html))",
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
