"""Load the control source fragments from this checkout and start the service."""

from pathlib import Path

CONTROL_SOURCE_ORDER = (
    "shared.py",
    "qwen38_catalog.py",
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
)


_SOURCE_DIR = Path(__file__).resolve().parent
_namespace = globals()
for _source_name in CONTROL_SOURCE_ORDER:
    _source_path = _SOURCE_DIR / _source_name
    if not _source_path.is_file():
        raise RuntimeError(f"Required control source is missing: {_source_path}")
    _namespace["__file__"] = str(_source_path)
    exec(compile(_source_path.read_bytes(), str(_source_path), "exec"), _namespace)
_namespace["__file__"] = str(Path(__file__).resolve())

main()
