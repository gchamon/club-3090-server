"""Source-tree runtime namespace shared by the control modules."""

from pathlib import Path as _Path
_PACKAGE_FILE = _Path(__file__).resolve()

_SOURCE_DIR = _Path(__file__).resolve().parent
_SOURCE_ORDER = (
    "qwen38_catalog.py",
    "strata_catalog.py",
    "chat.py",
    "services_config.py",
    "runtime_inventory.py",
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
)

from . import shared as _shared

globals().update({name: value for name, value in vars(_shared).items() if not name.startswith("__")})
for _source_name in _SOURCE_ORDER:
    _source_path = _SOURCE_DIR / _source_name
    if not _source_path.is_file():
        raise RuntimeError(f"Required control source is missing: {_source_path}")
    globals()["__file__"] = str(_source_path)
    exec(compile(_source_path.read_bytes(), str(_source_path), "exec"), globals())
_shared.__dict__.update({name: value for name, value in globals().items() if not name.startswith("__")})
globals()["__file__"] = str(_PACKAGE_FILE)
