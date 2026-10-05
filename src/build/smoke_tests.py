from __future__ import annotations

import ast
import os
import subprocess
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
        for relative in ("scripts/switch.sh", "scripts/setup.sh"):
            (upstream / relative).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        unit_dir = temp / "units"
        env_file = temp / "etc" / "club3090-server.env"
        state_dir = temp / "state"
        systemctl_log = temp / "systemctl.log"
        forbidden_log = temp / "forbidden-mutations.log"
        mutation_wrapper = '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CLUB3090_TEST_MUTATION_LOG"\nexit 99\n'
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
        if "ExecStart=/usr/bin/python3 -m control.runtime" not in control_unit:
            return False, "control service does not execute the repository runtime module"
        if f"CLUB3090_DIR={upstream}" not in control_unit:
            return False, "control service upstream checkout path is incorrect"
        if "/opt/club3090-control/control.py" in control_unit or "CONTROL_PAYLOAD" in control_unit:
            return False, "control service references an installed/embedded application payload"
        if f"CLUB3090_CONTROL_DIR={state_dir}" not in control_unit:
            return False, "control service runtime-data path is incorrect"
        benchmark_unit = (unit_dir / "club3090-benchmarks.service").read_text(encoding="utf-8")
        if f"WorkingDirectory={root}/src" not in benchmark_unit or "ExecStart=/usr/bin/python3 -m control.runtime --benchmark-worker" not in benchmark_unit:
            return False, "benchmark service does not execute from the source checkout"
        updater_unit = (unit_dir / "club3090-updater.service").read_text(encoding="utf-8")
        if f"WorkingDirectory={root}/src" not in updater_unit or f"ExecStart=/usr/bin/python3 {root}/src/build/updater.py" not in updater_unit:
            return False, "updater service does not execute from the source checkout"
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
