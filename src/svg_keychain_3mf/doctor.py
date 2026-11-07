"""`svg-keychain doctor`: an environment report for bug reports.

Collects only what helps reproduce a problem: tool and Python versions, OS family
and release, dependency versions, and whether the optional SVG renderer loads.
It never reads your SVGs, never uploads anything, and replaces your home folder
and user name with placeholders so the report is safe to paste publicly.
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import re
from importlib import metadata
from pathlib import Path

from . import __version__

PACKAGES = ("numpy", "shapely", "trimesh", "svgpathtools", "mapbox-earcut",
            "cairosvg", "cairocffi", "opencv-python-headless", "pillow")

_SECRETISH = re.compile(r"(?i)(token|secret|password|api[_-]?key)\s*[=:]\s*\S+")
# Any home folder, whoever it belongs to: /Users/x, /home/x, C:\Users\x (either slash).
_ANY_HOME = re.compile(r"(?i)(/Users/|/home/|\b[A-Z]:[\\/]+Users[\\/]+)[^/\\\s\"']+")


def _names_to_hide() -> set[str]:
    names = {Path.home().name}
    try:
        names.add(getpass.getuser())
    except (KeyError, OSError):
        pass  # no login name available (e.g. some containers); the home-folder rules still apply
    return {n for n in names if n}


def redact(text: str) -> str:
    home = str(Path.home())
    if home and home not in ("/", "\\"):
        text = re.sub(re.escape(home), "~", text, flags=re.I)
    text = _ANY_HOME.sub(lambda m: m.group(1) + "<user>", text)
    for name in _names_to_hide():
        text = re.sub(rf"(?i)(?<![\w]){re.escape(name)}(?![\w])", "<user>", text)
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<email>", text)
    return _SECRETISH.sub(r"\1=<redacted>", text)


def _redact_values(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redact_values(v) for k, v in value.items()}
    return value


def _pkg(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def collect() -> dict:
    report: dict = {
        "tool_version": __version__,
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "packages": {p: _pkg(p) for p in PACKAGES},
    }
    try:
        import tkinter  # noqa: F401
        report["gui_tkinter"] = "ok"
    except Exception as e:
        report["gui_tkinter"] = f"unavailable: {type(e).__name__}"
    try:
        from . import engine
        report["svg_reader"] = ("render-then-trace (cairosvg + OpenCV)" if engine._RASTER_OK
                                else "path parser only: " + getattr(engine, "_RASTER_IMPORT_ERROR", "unknown"))
    except Exception as e:
        report["svg_reader"] = f"engine failed to import: {type(e).__name__}: {e}"
    if os.environ.get("SVG_KEYCHAIN_LIBCAIRO"):
        report["SVG_KEYCHAIN_LIBCAIRO"] = os.environ["SVG_KEYCHAIN_LIBCAIRO"]
    return _redact_values(report)


def render_text(report: dict) -> str:
    lines = ["svg-keychain-3mf doctor report",
             "(review before sharing — it should contain no personal details)", ""]
    for k, v in report.items():
        if isinstance(v, dict):
            lines.append(f"{k}:")
            lines += [f"  {pk}: {pv}" for pk, pv in v.items()]
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def run(as_json: bool = False) -> int:
    report = collect()
    print(json.dumps(report, indent=2) if as_json else render_text(report))
    return 0
