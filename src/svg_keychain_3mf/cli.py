"""Command-line entry point.

    svg-keychain                      open the desktop app
    svg-keychain generate FILE.svg    build 3MF files without the app
    svg-keychain doctor               print a redacted environment report for bug reports
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import __version__

OUTPUTS = ("keychain", "plaque", "magnet")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="svg-keychain", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"svg-keychain-3mf {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("gui", help="open the desktop app (default)")

    g = sub.add_parser("generate", help="convert an SVG (or an existing 3MF) into 3MF files")
    g.add_argument("input", type=Path)
    g.add_argument("-o", "--out-dir", type=Path, help="folder for the 3MF files (default: next to the input)")
    g.add_argument("--outputs", default="keychain", help="comma list of keychain,plaque,magnet (default: keychain)")
    g.add_argument("--size", type=float, help="longest side in mm (default 60 keychain/magnet, 100 plaque)")
    g.add_argument("--thickness", type=float, default=5.0, help="mm (default 5)")
    g.add_argument("--hole", type=float, default=3.0, help="key-ring hole diameter in mm (default 3)")
    g.add_argument("--nozzle", type=float, default=0.4, choices=(0.2, 0.4), help="nozzle diameter in mm")
    g.add_argument("--min-area", type=float, default=1.0, help="drop colour pieces smaller than this many mm²")
    g.add_argument("--flat", action="store_true", help="same height for every colour (no stepped relief)")
    g.add_argument("--double-sided", action="store_true", help="keychain only: flag reads on both faces")
    g.add_argument("--base-colour", help="add a backing plate in this hex colour, e.g. '#0f4c81'")
    g.add_argument("--base-thickness", type=float, default=2.0)
    g.add_argument("--merge-threshold", type=int, default=15, help="merge colours closer than this (0-100 Lab distance)")
    g.add_argument("--path-parser", action="store_true",
                   help="skip the render-then-trace reader and use the plain SVG path parser")
    g.add_argument("-q", "--quiet", action="store_true")

    d = sub.add_parser("doctor", help="print an environment report to paste into a bug report")
    d.add_argument("--json", action="store_true", help="machine-readable output")
    return p


def _generate(args) -> int:
    from . import engine

    log = (lambda _m: None) if args.quiet else (lambda m: print(m, file=sys.stderr))
    src: Path = args.input
    if not src.is_file():
        print(f"error: {src} is not a file", file=sys.stderr)
        return 2
    wanted = [o.strip() for o in args.outputs.split(",") if o.strip()]
    unknown = sorted(set(wanted) - set(OUTPUTS))
    if unknown or not wanted:
        print(f"error: --outputs must be a comma list of {', '.join(OUTPUTS)}", file=sys.stderr)
        return 2
    if args.double_sided and wanted != ["keychain"]:
        print("error: --double-sided applies to keychains only; use --outputs keychain", file=sys.stderr)
        return 2
    if args.double_sided and (args.flat or args.thickness != 5.0):
        print("error: --double-sided keychains have a fixed thickness and relief; drop --flat/--thickness",
              file=sys.stderr)
        return 2
    for name in ("size", "thickness", "hole", "min_area", "base_thickness"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            print(f"error: --{name.replace('_', '-')} must be greater than 0", file=sys.stderr)
            return 2
    if args.base_colour and not re.fullmatch(r"#?[0-9A-Fa-f]{6}", args.base_colour):
        print("error: --base-colour must be a hex colour such as '#0f4c81'", file=sys.stderr)
        return 2
    if args.base_colour and not args.base_colour.startswith("#"):
        args.base_colour = "#" + args.base_colour

    import xml.etree.ElementTree as ET
    import zipfile
    try:
        if src.suffix.lower() == ".3mf":
            geoms, _vb = engine.parse_3mf(str(src), log=log)
        else:
            geoms, _vb = engine.parse_svg_auto(str(src), log=log, prefer_raster=not args.path_parser,
                                               nozzle_mm=args.nozzle, min_area_mm2=args.min_area)
    except (ValueError, ET.ParseError, zipfile.BadZipFile, KeyError) as e:
        print(f"error: could not read {src.name}: {e}", file=sys.stderr)
        return 1
    if not geoms:
        print("error: no coloured regions found. Paths need a fill colour; try flattening the SVG "
              "(e.g. Inkscape: Path → Object to Path) and save as plain SVG.", file=sys.stderr)
        return 1

    out_dir = args.out_dir or src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    for suf in ("_keychain", "_plaque", "_magnet"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
            break
    common = dict(min_area_mm2=args.min_area, base_colour=args.base_colour.lower() if args.base_colour else None,
                  base_thickness_mm=args.base_thickness, nozzle_mm=args.nozzle,
                  island_rel_threshold=0.01, color_merge_threshold=args.merge_threshold, log=log)

    written = []
    for kind in wanted:
        size = args.size or (100.0 if kind == "plaque" else 60.0)
        if kind == "keychain" and args.double_sided:
            meshes = engine.build_keychain_meshes_double_sided(geoms, max_size_mm=size,
                                                               hole_diameter_mm=args.hole, **common)
        elif kind == "keychain":
            meshes = engine.build_keychain_meshes(geoms, max_size_mm=size, thickness_mm=args.thickness,
                                                  hole_diameter_mm=args.hole,
                                                  stepped_heights=not args.flat, **common)
        elif kind == "plaque":
            meshes = engine.build_plaque_meshes(geoms, max_size_mm=size, thickness_mm=args.thickness,
                                                stepped_heights=not args.flat, **common)
        else:
            try:
                meshes = engine.build_magnet_meshes(geoms, max_size_mm=size, thickness_mm=args.thickness,
                                                    stepped_heights=not args.flat, **common)
            except ValueError as e:
                print(f"magnet skipped: {e}", file=sys.stderr)
                continue
        path = out_dir / f"{stem}_{kind}.3mf"
        engine.write_3mf(meshes, str(path), log=log)
        written.append(path)
        print(f"{path}\t{len(meshes)} colour parts")
    return 0 if written else 1


def _gui() -> int:
    from . import engine
    try:
        engine._run_app()
    except ImportError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        return _generate(args)
    if args.command == "doctor":
        from .doctor import run
        return run(as_json=args.json)
    return _gui()
