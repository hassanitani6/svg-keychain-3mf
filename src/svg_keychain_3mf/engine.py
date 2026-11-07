#!/usr/bin/env python3
"""
SVG Keychain 3MF
Converts flat-colour SVGs (such as flag maps) into multi-colour 3D-printable
keychain, plaque and fridge-magnet 3MF files for Bambu Studio.

Workflow:
  1. Drop an SVG (e.g. a Wikipedia flag-map) into the app
  2. Each colour region in the SVG becomes a separate printed part
  3. Output is a BambuStudio-ready .3mf with extruder slots pre-assigned
"""

try:  # The desktop app needs Tk; the command line and the engine do not.
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, colorchooser
    _TkBase = tk.Tk
except ImportError as _tk_err:
    tk = ttk = filedialog = messagebox = colorchooser = None
    _TkBase = object
    _TK_IMPORT_ERROR = str(_tk_err)
import xml.etree.ElementTree as ET
import re
import os
import zipfile
import json
import io
import threading
from pathlib import Path

import math
import numpy as np
from svgpathtools import parse_path, Path as SvgPath
from shapely.geometry import Polygon, MultiPolygon, Point, box, LineString
from shapely.ops import unary_union
from shapely.affinity import translate, scale as shapely_scale
import trimesh

# ──────────────────────────────────────────────────────────────
# OPTIONAL: render-then-vectorize backend (cairosvg + OpenCV)
# Renders the SVG exactly as designed (correct paint order, clips, masks,
# overlapping strokes) and traces each colour to clean polygons — fixes flags
# the path-parser mangles (Union Jacks, crosses, coats of arms). If the libs
# aren't present we silently fall back to parse_svg.
# ──────────────────────────────────────────────────────────────
def _enable_cairo():
    """Point cairocffi at a real libcairo (macOS SIP strips DYLD_* from
    /usr/bin/python3, so the env-var route fails — patch find_library)."""
    import ctypes.util, os as _os
    candidates = [
        '/opt/homebrew/lib/libcairo.2.dylib',     # Apple-silicon Homebrew
        '/usr/local/lib/libcairo.2.dylib',         # Intel Homebrew
        _os.environ.get('SVG_KEYCHAIN_LIBCAIRO', ''),  # explicit override / bundled
    ]
    found = next((p for p in candidates if p and _os.path.exists(p)), None)
    if found:
        _orig = ctypes.util.find_library
        ctypes.util.find_library = (lambda name:
            found if (name and 'cairo' in name) else _orig(name))

try:
    _enable_cairo()
    import cairosvg as _cairosvg
    import cv2 as _cv2
    _RASTER_OK = True
except Exception as _raster_err:          # cairosvg/cv2 missing or libcairo absent
    _cairosvg = None
    _cv2 = None
    _RASTER_OK = False
    _RASTER_IMPORT_ERROR = str(_raster_err)


# ──────────────────────────────────────────────────────────────
# COLOUR HELPERS
# ──────────────────────────────────────────────────────────────

CSS_NAMED = {
    'aliceblue':'#f0f8ff','antiquewhite':'#faebd7','aqua':'#00ffff',
    'aquamarine':'#7fffd4','azure':'#f0ffff','beige':'#f5f5dc',
    'bisque':'#ffe4c4','black':'#000000','blue':'#0000ff',
    'brown':'#a52a2a','burlywood':'#deb887','cadetblue':'#5f9ea0',
    'chartreuse':'#7fff00','chocolate':'#d2691e','coral':'#ff7f50',
    'cornflowerblue':'#6495ed','cornsilk':'#fff8dc','crimson':'#dc143c',
    'cyan':'#00ffff','darkblue':'#00008b','darkcyan':'#008b8b',
    'darkgoldenrod':'#b8860b','darkgray':'#a9a9a9','darkgreen':'#006400',
    'darkkhaki':'#bdb76b','darkmagenta':'#8b008b','darkolivegreen':'#556b2f',
    'darkorange':'#ff8c00','darkorchid':'#9932cc','darkred':'#8b0000',
    'darksalmon':'#e9967a','darkseagreen':'#8fbc8f','darkslateblue':'#483d8b',
    'darkslategray':'#2f4f4f','darkturquoise':'#00ced1','darkviolet':'#9400d3',
    'deeppink':'#ff1493','deepskyblue':'#00bfff','dimgray':'#696969',
    'dodgerblue':'#1e90ff','firebrick':'#b22222','floralwhite':'#fffaf0',
    'forestgreen':'#228b22','fuchsia':'#ff00ff','gainsboro':'#dcdcdc',
    'ghostwhite':'#f8f8ff','gold':'#ffd700','goldenrod':'#daa520',
    'gray':'#808080','green':'#008000','greenyellow':'#adff2f',
    'grey':'#808080','honeydew':'#f0fff0','hotpink':'#ff69b4',
    'indianred':'#cd5c5c','indigo':'#4b0082','ivory':'#fffff0',
    'khaki':'#f0e68c','lavender':'#e6e6fa','lawngreen':'#7cfc00',
    'lemonchiffon':'#fffacd','lightblue':'#add8e6','lightcoral':'#f08080',
    'lightcyan':'#e0ffff','lightgray':'#d3d3d3','lightgreen':'#90ee90',
    'lightpink':'#ffb6c1','lightsalmon':'#ffa07a','lightseagreen':'#20b2aa',
    'lightskyblue':'#87cefa','lightslategray':'#778899','lightsteelblue':'#b0c4de',
    'lightyellow':'#ffffe0','lime':'#00ff00','limegreen':'#32cd32',
    'linen':'#faf0e6','magenta':'#ff00ff','maroon':'#800000',
    'mediumaquamarine':'#66cdaa','mediumblue':'#0000cd','mediumorchid':'#ba55d3',
    'mediumpurple':'#9370db','mediumseagreen':'#3cb371','mediumslateblue':'#7b68ee',
    'mediumspringgreen':'#00fa9a','mediumturquoise':'#48d1cc',
    'mediumvioletred':'#c71585','midnightblue':'#191970','mintcream':'#f5fffa',
    'mistyrose':'#ffe4e1','moccasin':'#ffe4b5','navajowhite':'#ffdead',
    'navy':'#000080','oldlace':'#fdf5e6','olive':'#808000',
    'olivedrab':'#6b8e23','orange':'#ffa500','orangered':'#ff4500',
    'orchid':'#da70d6','palegoldenrod':'#eee8aa','palegreen':'#98fb98',
    'paleturquoise':'#afeeee','palevioletred':'#db7093','papayawhip':'#ffefd5',
    'peachpuff':'#ffdab9','peru':'#cd853f','pink':'#ffc0cb',
    'plum':'#dda0dd','powderblue':'#b0e0e6','purple':'#800080',
    'red':'#ff0000','rosybrown':'#bc8f8f','royalblue':'#4169e1',
    'saddlebrown':'#8b4513','salmon':'#fa8072','sandybrown':'#f4a460',
    'seagreen':'#2e8b57','seashell':'#fff5ee','sienna':'#a0522d',
    'silver':'#c0c0c0','skyblue':'#87ceeb','slateblue':'#6a5acd',
    'slategray':'#708090','snow':'#fffafa','springgreen':'#00ff7f',
    'steelblue':'#4682b4','tan':'#d2b48c','teal':'#008080',
    'thistle':'#d8bfd8','tomato':'#ff6347','turquoise':'#40e0d0',
    'violet':'#ee82ee','wheat':'#f5deb3','white':'#ffffff',
    'whitesmoke':'#f5f5f5','yellow':'#ffff00','yellowgreen':'#9acd32',
}

def _approximate_color_name(hex_color):
    """Return a rough human-readable label for a hex color (for logging)."""
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return ''
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if max(r, g, b) < 40:
        return 'Black'
    if min(r, g, b) > 215:
        return 'White'
    if r > 180 and g < 80 and b < 80:
        return 'Red'
    if r < 80 and g < 80 and b > 180:
        return 'Blue'
    if r < 80 and g > 150 and b < 80:
        return 'Green'
    if r > 150 and g > 120 and b < 60:
        return 'Gold/Yellow'
    if r > 180 and g > 100 and b < 60:
        return 'Orange'
    if r < 80 and g > 130 and b > 130:
        return 'Teal'
    if r > 120 and g < 80 and b > 150:
        return 'Purple'
    return ''


def normalize_color(c):
    """Return lowercase #rrggbb string, or None for none/transparent."""
    if not c:
        return None
    c = c.strip().lower()
    if c in ('none', 'transparent', 'inherit', 'currentcolor', ''):
        return None
    if c in CSS_NAMED:
        return CSS_NAMED[c]
    if c.startswith('#'):
        h = c[1:]
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        if len(h) == 8:
            h = h[:6]
        if len(h) == 6:
            return '#' + h
    m = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', c)
    if m:
        return '#{:02x}{:02x}{:02x}'.format(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def get_element_fill(elem, parent_fill):
    """Resolve fill colour for an SVG element, inheriting from parent."""
    style = elem.get('style', '')
    m = re.search(r'(?:^|;)\s*fill\s*:\s*([^;]+)', style)
    if m:
        raw = m.group(1).strip()
        if raw.lower() == 'none':
            return None
        v = normalize_color(raw)
        if v is not None:
            return v
    raw = elem.get('fill')
    if raw is not None:
        if raw.lower() == 'none':
            return None
        v = normalize_color(raw)
        if v is not None:
            return v
    return parent_fill


# ──────────────────────────────────────────────────────────────
# SVG TRANSFORM HELPERS
# ──────────────────────────────────────────────────────────────

def _parse_svg_transform(t_str):
    """Parse an SVG transform attribute — handles chained transforms like translate(x,y)scale(s)."""
    if not t_str:
        return None
    t_str = t_str.strip()

    def _single(name, args_str):
        vals = [float(x) for x in re.split(r'[\s,]+', args_str.strip()) if x]
        if name == 'matrix' and len(vals) == 6:
            return vals
        if name == 'translate':
            tx = vals[0] if vals else 0.0
            ty = vals[1] if len(vals) > 1 else 0.0
            return [1.0, 0.0, 0.0, 1.0, tx, ty]
        if name == 'scale':
            sx = vals[0] if vals else 1.0
            sy = vals[1] if len(vals) > 1 else sx
            return [sx, 0.0, 0.0, sy, 0.0, 0.0]
        if name == 'rotate':
            a = math.radians(vals[0]) if vals else 0.0
            ca, sa = math.cos(a), math.sin(a)
            if len(vals) == 3:
                cx, cy = vals[1], vals[2]
                return [ca, sa, -sa, ca,
                        cx*(1-ca) + cy*sa,
                        cy*(1-ca) - cx*sa]
            return [ca, sa, -sa, ca, 0.0, 0.0]
        if name == 'skewX':
            return [1.0, 0.0, math.tan(math.radians(vals[0])), 1.0, 0.0, 0.0]
        if name == 'skewY':
            return [1.0, math.tan(math.radians(vals[0])), 0.0, 1.0, 0.0, 0.0]
        return None

    # Find all transform functions in document order and compose them left-to-right
    result = None
    for m in re.finditer(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)', t_str):
        tf = _single(m.group(1), m.group(2))
        if tf is not None:
            result = _compose_transforms(result, tf) if result is not None else tf
    return result


def _compose_transforms(parent, child):
    """Compose two 6-element SVG transforms: result = parent ∘ child."""
    if parent is None:
        return child
    if child is None:
        return parent
    a1, b1, c1, d1, e1, f1 = parent
    a2, b2, c2, d2, e2, f2 = child
    return [
        a1*a2 + c1*b2,  b1*a2 + d1*b2,
        a1*c2 + c1*d2,  b1*c2 + d1*d2,
        a1*e2 + c1*f2 + e1,  b1*e2 + d1*f2 + f1,
    ]


def _apply_transform(pts, tf):
    """Apply a 6-element SVG transform to an (N,2) numpy array (SVG coords)."""
    if tf is None:
        return pts
    a, b, c, d, e, f = tf
    x = pts[:, 0]; y = pts[:, 1]
    return np.column_stack([a*x + c*y + e, b*x + d*y + f])


# ──────────────────────────────────────────────────────────────
# SVG → SHAPELY POLYGONS
# ──────────────────────────────────────────────────────────────

def _sample_subpath(sp_str, density):
    """Sample one closed SVG sub-path. Returns (N,2) array in SVG coords (Y-down), or None."""
    sp_str = sp_str.rstrip()
    if not re.search(r'[Zz]\s*$', sp_str):
        sp_str += ' Z'
    try:
        path = parse_path(sp_str)
    except Exception:
        return None
    if not path:
        return None
    try:
        length = path.length()
    except Exception:
        length = 100.0
    if length < 0.5:
        return None
    n = max(20, min(1000, int(length * density)))
    pts = []
    for i in range(n):
        try:
            pt = path.point(i / n)
            pts.append((float(pt.real), float(pt.imag)))   # SVG coords, Y-down
        except Exception:
            pass
    return np.array(pts, dtype=float) if len(pts) >= 3 else None


def _split_path_into_subpath_points(full_path, density):
    """
    Split a svgpathtools Path into subpaths by detecting segment start/end gaps.
    Handles relative-m subpaths correctly (parse_path does the right thing).
    Returns a list of (N,2) numpy arrays in SVG coords (Y-down).
    """
    GAP_THRESHOLD = 0.5   # SVG user-units; a true subpath jump is >> this

    subpath_segs = []
    current = []
    prev_end = None

    for seg in full_path:
        if prev_end is not None and abs(seg.start - prev_end) > GAP_THRESHOLD:
            if current:
                subpath_segs.append(current)
            current = []
        current.append(seg)
        prev_end = seg.end

    if current:
        subpath_segs.append(current)

    result = []
    for segs in subpath_segs:
        sp = SvgPath(*segs)
        try:
            length = sp.length()
        except Exception:
            length = 100.0
        if length < 0.5:
            continue
        n = max(20, min(1000, int(length * density)))
        pts = []
        for i in range(n):
            try:
                pt = sp.point(i / n)
                pts.append((float(pt.real), float(pt.imag)))
            except Exception:
                pass
        if len(pts) >= 3:
            result.append(np.array(pts, dtype=float))

    return result


def _pts_to_shapely_polys(point_arrays):
    """
    Convert a list of (N,2) arrays into shapely Polygons.
    Sub-paths that are fully enclosed by a larger one become holes (handles
    letter counter-shapes, O rings, etc.). Uses full containment — not just
    centroid — so adjacent dots/diacritics are never misclassified as holes.
    """
    raw = []
    for pts in point_arrays:
        if pts is None or len(pts) < 3:
            continue
        try:
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty and poly.area > 1e-6:
                raw.append(poly)
        except Exception:
            pass
    if not raw:
        return []

    raw.sort(key=lambda p: p.area, reverse=True)
    used = set()
    result = []

    for i, outer in enumerate(raw):
        if i in used:
            continue
        holes = []
        for j, inner in enumerate(raw):
            if j <= i or j in used:
                continue
            try:
                # Two-step check: centroid must be inside, AND most of inner must
                # overlap outer (guards against concave neighbours mis-classified).
                if outer.contains(inner.centroid):
                    overlap = outer.intersection(inner).area / (inner.area + 1e-10)
                    if overlap > 0.5:
                        holes.append(list(inner.exterior.coords))
                        used.add(j)
            except Exception:
                pass
        try:
            if holes:
                candidate = Polygon(list(outer.exterior.coords), holes)
                if not candidate.is_valid:
                    candidate = candidate.buffer(0)
                result.append(candidate)
            else:
                result.append(outer)
        except Exception:
            result.append(outer)
        used.add(i)

    return [p for p in result if not p.is_empty and p.is_valid]


def _rect_to_pts(elem):
    """Convert a <rect> SVG element to a (5,2) corner array (SVG coords, Y-down)."""
    try:
        x = float(elem.get('x', 0) or 0)
        y = float(elem.get('y', 0) or 0)
        w = float(elem.get('width',  0) or 0)
        h = float(elem.get('height', 0) or 0)
    except (ValueError, TypeError):
        return None
    if w <= 0 or h <= 0:
        return None
    return np.array([[x, y], [x+w, y], [x+w, y+h], [x, y+h], [x, y]], dtype=float)


_RTV_CSS = {'white':'#ffffff','black':'#000000','red':'#ff0000','green':'#008000',
            'blue':'#0000ff','yellow':'#ffff00','gold':'#ffd700','navy':'#000080',
            'maroon':'#800000','silver':'#c0c0c0','gray':'#808080','grey':'#808080'}


def _rtv_declared_palette(svg_text):
    """Collect the SVG's intended colours from fill/stop-color/style hex + named."""
    hexes = set()
    for m in re.finditer(r'#([0-9a-fA-F]{6})\b', svg_text):
        hexes.add('#' + m.group(1).lower())
    for m in re.finditer(r'#([0-9a-fA-F]{3})\b', svg_text):
        h = m.group(1).lower()
        hexes.add('#' + h[0]*2 + h[1]*2 + h[2]*2)
    for m in re.finditer(r'fill\s*[:=]\s*["\']?\s*([a-zA-Z]+)', svg_text):
        nm = m.group(1).lower()
        if nm in _RTV_CSS:
            hexes.add(_RTV_CSS[nm])
    return sorted(hexes)


def _rtv_srgb2lab(rgb):
    with np.errstate(all='ignore'):
        a = np.clip(rgb, 0, 255) / 255.0
        a = np.where(a > 0.04045, ((a + 0.055) / 1.055) ** 2.4, a / 12.92)
        M = np.array([[0.4124, 0.3576, 0.1805],
                      [0.2126, 0.7152, 0.0722],
                      [0.0193, 0.1192, 0.9505]])
        xyz = (a @ M.T) / np.array([0.95047, 1.0, 1.08883])
        xyz = np.clip(xyz, 0, None)
        f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16/116)
        L = 116*f[..., 1] - 16
        A = 500*(f[..., 0] - f[..., 1])
        B = 200*(f[..., 1] - f[..., 2])
    return np.nan_to_num(np.stack([L, A, B], axis=-1))


def _vet_svg(svg_text, palette, log):
    """Pre-flight gates on the SVG. Logs plain-English warnings for things that
    won't reproduce cleanly (embedded photos, gradients/filters, too many or no
    colours). Returns False only for a hard REJECT (unusable input); otherwise
    True (proceed, possibly with a flatten warning)."""
    low = svg_text.lower()
    if '<svg' not in low:
        log("  ⚠ Not a valid SVG (no <svg> root) — download the SVG source.")
        return False
    if re.search(r'<image\b', low) or 'data:image/' in low:
        log("  ⚠ This SVG embeds a photo (not vector shapes); colours can't be "
            "cleanly separated. Use a proper vector flag-map SVG.")
    if re.search(r'<(linear|radial)gradient\b', low):
        log("  ⚠ Gradient detected — it will be flattened to the nearest solid "
            "colours. Preview before printing.")
    if re.search(r'<filter\b', low):
        log("  ⚠ Blur/filter detected — can't be 3D-printed; it will be flattened.")
    n = len(palette)
    if n == 0:
        log("  ⚠ No declared colours found in the SVG.")
        return False
    if n > 16:
        log(f"  ⚠ {n} colours declared — more than 16 AMS slots. The smallest "
            "will be merged or dropped at the min-area step.")
    return True


def parse_svg_raster(filepath, log=None, target_mm=60.0, min_area_mm2=1.0,
                     render_px=2600):
    """Render-then-vectorize SVG reader. Returns ({color_hex: MultiPolygon},
    (w_mm, h_mm)) — same contract as parse_svg. Renders the SVG with cairosvg
    (correct paint order / clips / masks / overlapping strokes), snaps each
    pixel to the SVG's declared palette in Lab space, then traces every colour
    region to clean shapely polygons. Raises if the raster backend is missing."""
    if log is None:
        log = print
    if not _RASTER_OK:
        raise RuntimeError("raster backend unavailable")

    import io as _io
    from PIL import Image as _Image
    from shapely.validation import make_valid as _make_valid

    svg_text = Path(filepath).read_text(encoding='utf-8', errors='replace')
    palette = _rtv_declared_palette(svg_text)
    if not palette:
        raise ValueError("no declared colours in SVG")
    if not _vet_svg(svg_text, palette, log):
        raise ValueError("SVG failed vetting gate")

    png = _cairosvg.svg2png(bytestring=svg_text.encode(), output_width=render_px)
    img = np.array(_Image.open(_io.BytesIO(png)).convert('RGBA'))
    rgb = img[..., :3].astype(np.float64)
    alpha = img[..., 3]
    H, W = alpha.shape
    transparent = alpha < 128
    rgb[transparent] = 255

    # Augment the declared palette with an undeclared colour that actually got
    # rendered — e.g. a shape with no fill that falls back to SVG's default BLACK
    # (Germany/Belgium black stripe). Detect pixels that fit NO declared colour
    # well (large Lab residual); if a significant block does, add the dominant
    # such colour so it isn't snapped onto an unrelated neighbour. Using the
    # residual (not a colour histogram) avoids splitting a colour into near-
    # duplicates from anti-aliasing/quantisation.
    decl_lab = _rtv_srgb2lab(
        np.array([[int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)] for h in palette],
                 dtype=np.float64))
    px_lab0 = _rtv_srgb2lab(rgb.reshape(-1, 3)).reshape(H, W, 3)
    resid = np.linalg.norm(px_lab0[:, :, None, :] - decl_lab[None, None, :, :], axis=3).min(axis=2)
    n_opaque = max(1, int((~transparent).sum()))
    for _ in range(4):                       # pick up a few undeclared colours if needed
        miss = (resid > 25.0) & (~transparent)
        if int(miss.sum()) < 0.03 * n_opaque:    # nothing significant left unrepresented
            break
        mr = rgb[miss]                        # dominant missing colour = mode of the misfit pixels
        q = (np.round(mr / 16.0) * 16.0)
        uq, ct = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
        col = np.clip(uq[int(np.argmax(ct))], 0, 255).astype(int)
        hexc = '#%02x%02x%02x' % (col[0], col[1], col[2])
        if hexc in palette:
            break
        palette.append(hexc)
        log(f"  Added undeclared rendered colour {hexc} "
            f"({100 * int(miss.sum()) / n_opaque:.0f}% of art)")
        clab = _rtv_srgb2lab(col[None, :].astype(np.float64))[0]
        resid = np.minimum(resid, np.linalg.norm(px_lab0 - clab[None, None, :], axis=2))

    pal_rgb = np.array([[int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)] for h in palette],
                       dtype=np.float64)
    pal_lab = _rtv_srgb2lab(pal_rgb)
    px_lab = _rtv_srgb2lab(rgb.reshape(-1, 3)).reshape(H, W, 3)
    dist = np.linalg.norm(px_lab[:, :, None, :] - pal_lab[None, None, :, :], axis=3)
    labels = np.argmin(dist, axis=2)

    longest_px = max(H, W)
    mm_per_px = target_mm / longest_px
    min_area_px = min_area_mm2 / (mm_per_px ** 2)

    geoms = {}
    for i, hexc in enumerate(palette):
        mask = ((labels == i) & (~transparent)).astype(np.uint8) * 255
        if mask.sum() == 0:
            continue
        mask = _cv2.morphologyEx(mask, _cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        cnts, hier = _cv2.findContours(mask, _cv2.RETR_CCOMP, _cv2.CHAIN_APPROX_SIMPLE)
        if hier is None:
            continue
        hier = hier[0]
        polys = []
        for ci, c in enumerate(cnts):
            if hier[ci][3] != -1 or _cv2.contourArea(c) < min_area_px:
                continue
            outer = _cv2.approxPolyDP(c, 0.0012 * _cv2.arcLength(c, True), True).reshape(-1, 2)
            if len(outer) < 3:
                continue
            holes = []
            ch = hier[ci][2]
            while ch != -1:
                hc = cnts[ch]
                if _cv2.contourArea(hc) >= min_area_px * 0.3:
                    he = _cv2.approxPolyDP(hc, 0.0012 * _cv2.arcLength(hc, True), True).reshape(-1, 2)
                    if len(he) >= 3:
                        holes.append(he)
                ch = hier[ch][0]
            try:
                p = Polygon(outer, holes)
                if not p.is_valid:
                    p = _make_valid(p)
                if p.area > 0:
                    polys.append(p)
            except Exception:
                pass
        if not polys:
            continue
        g = unary_union(polys)
        if g.geom_type not in ('Polygon', 'MultiPolygon'):
            pp = [q for q in getattr(g, 'geoms', [])
                  if q.geom_type in ('Polygon', 'MultiPolygon') and q.area > 0]
            if not pp:
                continue
            g = unary_union(pp)
        g = shapely_scale(g, mm_per_px, mm_per_px, origin=(0, 0))
        geoms[hexc] = g

    if not geoms:
        raise ValueError("raster vectorize produced no colour regions")
    minx, miny, maxx, maxy = unary_union(list(geoms.values())).bounds
    log(f"Raster reader: {len(geoms)} colours, "
        f"{sum(len(g.geoms) if isinstance(g, MultiPolygon) else 1 for g in geoms.values())} polygons")
    return geoms, (maxx - minx, maxy - miny)


def parse_svg_auto(filepath, log=None, prefer_raster=True, **kw):
    """Read an SVG into {colour: geometry}. Uses the render-then-vectorize
    backend when available (faithful on complex flags); falls back to the
    legacy path parser if it's unavailable or errors.

    Both readers emit Y-DOWN geometry (image/SVG convention: the flag's top is
    at low Y). We flip to Y-UP here so the flag's top is at high Y — that makes
    the ring hole (placed at max-Y by _find_hole_xy) land at the TOP of the
    design, so the keychain hangs the right way up, and the model is upright in
    BambuStudio (which is Y-up)."""
    if log is None:
        log = print
    # Detail threshold scales with the nozzle: a 0.2 mm nozzle resolves fine
    # emblems (Mexico's eagle, coats of arms), so keep small pieces; a 0.4 mm
    # nozzle can't print them, so the coarser default stays (other flags
    # unchanged). Falls back to the UI 'min island area' if passed explicitly.
    nozzle_mm = kw.get('nozzle_mm', 0.4)
    raster_min_area = 0.2 if nozzle_mm <= 0.25 else kw.get('min_area_mm2', 1.0)
    geoms = vb = None
    if prefer_raster and _RASTER_OK:
        try:
            geoms, vb = parse_svg_raster(filepath, log=log,
                                         target_mm=kw.get('target_mm', 60.0),
                                         min_area_mm2=raster_min_area)
        except Exception as e:
            log(f"Raster reader failed ({e}); falling back to path parser")
    if geoms is None:
        geoms, vb = parse_svg(filepath, log=log)
    # Flip Y-down → Y-up about a common axis so all zones stay aligned.
    flipped = {}
    for color, g in geoms.items():
        fg = shapely_scale(g, xfact=1.0, yfact=-1.0, origin=(0, 0))
        if not fg.is_empty:
            flipped[color] = fg
    return flipped, vb


def parse_svg(filepath, log=None):
    """
    Parse an SVG file, returning {color_hex: shapely_geometry} and (vb_w, vb_h).

    Handles:
      - <defs> skipped (not rendered)
      - <use xlink:href="#id"> resolved with transforms
      - <rect> elements (converted to corner polygons)
      - cumulative matrix/translate/scale transforms on <g>, <use>, <rect>
      - per-shape painter's algorithm (not per-colour) for correct Z-order
    """
    if log is None:
        log = print

    try:
        tree = ET.parse(filepath)
    except ET.ParseError:
        raise ValueError(
            "Not a valid SVG file — the file may be a PNG or other image format. "
            "Download the SVG source from Wikipedia (right-click the image → Save as SVG)."
        )
    root = tree.getroot()

    svgns = ''
    xlinkns = '{http://www.w3.org/1999/xlink}'
    if root.tag.startswith('{'):
        svgns = root.tag.split('}')[0] + '}'

    vb = root.get('viewBox', '').split()
    if len(vb) >= 4:
        vb_min_x, vb_min_y = float(vb[0]), float(vb[1])
        vb_w, vb_h = float(vb[2]), float(vb[3])
    else:
        vb_min_x, vb_min_y = 0.0, 0.0
        vb_w = float(re.sub(r'[^\d.]', '', root.get('width',  '500')) or '500')
        vb_h = float(re.sub(r'[^\d.]', '', root.get('height', '500')) or '500')
    vb_max_y = vb_min_y + vb_h

    log(f"SVG viewBox: {vb_w:.0f} × {vb_h:.0f} user-units")

    density = max(0.05, 200.0 / max(vb_w, vb_h))
    MIN_STROKE_SVG = max(vb_w, vb_h) / 120.0  # ≥ 0.5 mm at 60 mm scale
    vb_rect = box(vb_min_x, vb_min_y, vb_min_x + vb_w, vb_min_y + vb_h)

    id_map = {}
    for elem in root.iter():
        eid = elem.get('id')
        if eid:
            id_map[eid] = elem

    # Each entry: (z_index, color_hex, shapely_geometry)
    # z_index = document order position (higher = drawn on top in SVG)
    shapes = []
    path_total = [0]

    def _explicit_fill(elem):
        style = elem.get('style', '')
        m = re.search(r'(?:^|;)\s*fill\s*:\s*([^;]+)', style)
        if m:
            raw = m.group(1).strip().lower()
            if raw in ('none', 'transparent'):
                return 'none'
            v = normalize_color(raw)
            if v:
                return v
        raw = (elem.get('fill') or '').strip().lower()
        if raw in ('none', 'transparent'):
            return 'none'
        if raw:
            v = normalize_color(raw)
            if v:
                return v
        return None

    def _compute_clip_geom(cp_elem, tf, _depth=0):
        """Parse a <clipPath> or <mask> element and return its Shapely geometry."""
        if _depth > 8:
            return None
        geoms = []
        for child in cp_elem:
            ctag = (child.tag
                    .replace(svgns, '')
                    .replace('{http://www.w3.org/2000/svg}', ''))
            own_tf = _parse_svg_transform(child.get('transform', ''))
            c_tf = _compose_transforms(tf, own_tf)
            if ctag == 'path':
                d = child.get('d', '')
                if d:
                    try:
                        fp = parse_path(d)
                        pts_list = []
                        for pts in _split_path_into_subpath_points(fp, density):
                            if c_tf is not None:
                                pts = _apply_transform(pts, c_tf)
                            pts[:, 1] = vb_max_y - pts[:, 1]
                            pts_list.append(pts)
                        polys = _pts_to_shapely_polys(pts_list)
                        if polys:
                            geoms.append(unary_union(polys))
                    except Exception:
                        pass
            elif ctag == 'rect':
                pts = _rect_to_pts(child)
                if pts is not None:
                    if c_tf is not None:
                        pts = _apply_transform(pts, c_tf)
                    pts[:, 1] = vb_max_y - pts[:, 1]
                    polys = _pts_to_shapely_polys([pts])
                    if polys:
                        geoms.append(unary_union(polys))
            elif ctag == 'g':
                # Recurse into groups (e.g. Ukraine mask wraps paths in a <g>)
                inner = _compute_clip_geom(child, c_tf, _depth + 1)
                if inner is not None:
                    geoms.append(inner)
            elif ctag == 'use':
                # Resolve <use xlink:href="#id"> inside clipPath/mask (e.g. USA clip1x → #Canton)
                href = (child.get(f'{xlinkns}href') or child.get('href', '')).lstrip('#')
                ux = float(child.get('x') or 0)
                uy = float(child.get('y') or 0)
                if ux or uy:
                    c_tf = _compose_transforms(c_tf, [1, 0, 0, 1, ux, uy])
                ref = id_map.get(href)
                if ref is not None:
                    # Recurse treating the referenced element as a container
                    # so its type is handled (path/rect/g/use all work via the loop)
                    class _FakeContainer:
                        def __iter__(self_): return iter([ref])
                    inner = _compute_clip_geom(_FakeContainer(), c_tf, _depth + 1)
                    if inner is not None:
                        geoms.append(inner)
        if not geoms:
            return None
        try:
            result = unary_union(geoms).intersection(vb_rect)
            return result if not result.is_empty else None
        except Exception:
            try:
                result = unary_union([g.buffer(0) for g in geoms]).intersection(vb_rect)
                return result if not result.is_empty else None
            except Exception:
                log('clipPath geometry repair failed — clip disabled for this element')
                return None

    def _add_shape(z, color, pts_list, clip=None):
        """Union a list of point arrays into one shapely geometry and record it.
        Returns the recorded geometry, or None if nothing was added."""
        polys = _pts_to_shapely_polys(pts_list)
        if not polys:
            return None
        try:
            geom = unary_union(polys)
            if geom.is_empty:
                return None
            if clip is not None:
                try:
                    geom = geom.intersection(clip)
                except Exception:
                    try:
                        geom = geom.buffer(0).intersection(clip.buffer(0))
                    except Exception:
                        log(f'clip intersection failed for {color} — shape unclipped')
            geom = geom.intersection(vb_rect)
            if not geom.is_empty:
                shapes.append((z, color, geom))
                return geom
            return None
        except Exception:
            return None

    def _get_stroke_attrs(elem):
        """Return (stroke_color_hex_or_None, stroke_width_in_svg_units)."""
        style = elem.get('style', '')
        stroke_color = None
        m = re.search(r'(?:^|;)\s*stroke\s*:\s*([^;]+)', style)
        if m:
            raw = m.group(1).strip().lower()
            if raw not in ('none', 'transparent'):
                stroke_color = normalize_color(raw)
        else:
            raw = (elem.get('stroke') or '').strip().lower()
            if raw and raw not in ('none', 'transparent'):
                stroke_color = normalize_color(raw)
        if stroke_color is None:
            return (None, 1.0)
        stroke_width = 1.0
        m = re.search(r'(?:^|;)\s*stroke-width\s*:\s*([^;]+)', style)
        if m:
            try:
                stroke_width = float(re.sub(r'[^\d.]', '', m.group(1).strip()) or '1')
            except (ValueError, TypeError):
                pass
        else:
            sw = (elem.get('stroke-width') or '').strip()
            if sw:
                try:
                    stroke_width = float(re.sub(r'[^\d.]', '', sw) or '1')
                except (ValueError, TypeError):
                    pass
        return (stroke_color, stroke_width)

    def _build_stroke_geom(pts_list, half_w, clip=None, fill_poly=None):
        """Create a stroke polygon.

        fill_poly (if given): the already-computed fill polygon.  We derive the
        stroke as a ring — outer buffer minus inner buffer — so we never fill
        the interior of a closed path (which LineString.buffer would do).

        Without fill_poly (fill='none' paths): buffer the centerline linestring.
        """
        if fill_poly is not None and not fill_poly.is_empty:
            try:
                outer = fill_poly.buffer(half_w)
                inner = fill_poly.buffer(-half_w)
                result = outer.difference(inner)
                if clip is not None:
                    result = result.intersection(clip)
                result = result.intersection(vb_rect)
                return result if not result.is_empty else None
            except Exception:
                return None

        # fill='none' path — buffer the centerline
        geoms = []
        for pts in pts_list:
            if pts is None or len(pts) < 2:
                continue
            try:
                ls = LineString(pts)
                if ls.length > 0.5:
                    geoms.append(ls.buffer(half_w, cap_style=1, join_style=1))
            except Exception:
                pass
        if not geoms:
            return None
        try:
            result = unary_union(geoms)
            if clip is not None:
                result = result.intersection(clip)
            result = result.intersection(vb_rect)
            return result if not result.is_empty else None
        except Exception:
            return None

    def walk(elem, parent_fill, tf, active_clip=None, depth=0):
        if depth > 30:
            return

        local_tag = (elem.tag
                     .replace(svgns, '')
                     .replace('{http://www.w3.org/2000/svg}', ''))

        if local_tag == 'defs':
            return

        ef = _explicit_fill(elem)
        if ef == 'none':
            eff = None
        elif ef is not None:
            eff = ef
        else:
            eff = parent_fill

        own_tf = _parse_svg_transform(elem.get('transform', ''))
        if local_tag == 'use':
            ux = float(elem.get('x') or 0)
            uy = float(elem.get('y') or 0)
            if ux or uy:
                own_tf = _compose_transforms([1, 0, 0, 1, ux, uy], own_tf)
        child_tf = _compose_transforms(tf, own_tf)

        # Resolve clip-path / mask on this element and intersect with inherited clip.
        child_clip = active_clip
        for clip_attr_name in ('clip-path', 'mask'):
            attr_val = elem.get(clip_attr_name, '')
            if not attr_val:
                # also check style= string
                attr_val = re.search(
                    rf'(?:^|;)\s*{clip_attr_name}\s*:\s*([^;]+)', elem.get('style', '')
                )
                attr_val = attr_val.group(1).strip() if attr_val else ''
            if attr_val:
                m = re.search(r'url\(#([^)]+)\)', attr_val)
                if m:
                    ref_elem = id_map.get(m.group(1))
                    if ref_elem is not None:
                        new_clip = _compute_clip_geom(ref_elem, child_tf)
                        if new_clip is not None:
                            child_clip = (child_clip.intersection(new_clip)
                                          if child_clip is not None else new_clip)

        if local_tag == 'path':
            d = elem.get('d', '')
            fill_z   = path_total[0] * 2
            stroke_z = path_total[0] * 2 + 1
            pts_list = []
            if d:
                try:
                    full_path_obj = parse_path(d)
                except Exception:
                    full_path_obj = None
                if full_path_obj:
                    for pts in _split_path_into_subpath_points(full_path_obj, density):
                        if child_tf is not None:
                            pts = _apply_transform(pts, child_tf)
                        pts[:, 1] = vb_max_y - pts[:, 1]
                        pts_list.append(pts)
            if pts_list:
                if eff:
                    fill_geom = _add_shape(fill_z, eff, pts_list, child_clip)
                    # Exterior stroke ring for a differently-coloured stroke
                    sc, sw = _get_stroke_attrs(elem)
                    if sc and sc != eff and fill_geom is not None and not fill_geom.is_empty:
                        if child_tf is not None:
                            _sx = math.sqrt(child_tf[0]**2 + child_tf[1]**2)
                            _sy = math.sqrt(child_tf[2]**2 + child_tf[3]**2)
                            tf_scale = math.sqrt(_sx * _sy)
                            if tf_scale > 0:
                                sw *= tf_scale
                        half_w = max(sw, MIN_STROKE_SVG) / 2.0
                        try:
                            ring = fill_geom.buffer(half_w).difference(fill_geom)
                            if child_clip is not None:
                                ring = ring.intersection(child_clip)
                            ring = ring.intersection(vb_rect)
                            if not ring.is_empty:
                                shapes.append((stroke_z, sc, ring))
                        except Exception:
                            pass
                else:
                    # fill=none: convert stroke to a filled shape
                    sc, sw = _get_stroke_attrs(elem)
                    if sc:
                        # Scale stroke-width from local coords to root SVG coords
                        if child_tf is not None:
                            _sx = math.sqrt(child_tf[0]**2 + child_tf[1]**2)
                            _sy = math.sqrt(child_tf[2]**2 + child_tf[3]**2)
                            tf_scale = math.sqrt(_sx * _sy)
                            if tf_scale > 0:
                                sw *= tf_scale
                        sg = _build_stroke_geom(pts_list, max(sw, MIN_STROKE_SVG) / 2.0,
                                                child_clip)
                        if sg is not None:
                            shapes.append((stroke_z, sc, sg))
            path_total[0] += 1

        elif local_tag == 'rect':
            fill_z   = path_total[0] * 2
            stroke_z = path_total[0] * 2 + 1
            pts = _rect_to_pts(elem)
            if pts is not None:
                if child_tf is not None:
                    pts = _apply_transform(pts, child_tf)
                pts[:, 1] = vb_max_y - pts[:, 1]
                if eff:
                    fill_geom = _add_shape(fill_z, eff, [pts], child_clip)
                    sc, sw = _get_stroke_attrs(elem)
                    if sc and sc != eff and fill_geom is not None and not fill_geom.is_empty:
                        half_w = max(sw, MIN_STROKE_SVG) / 2.0
                        try:
                            ring = fill_geom.buffer(half_w).difference(fill_geom)
                            if child_clip is not None:
                                ring = ring.intersection(child_clip)
                            ring = ring.intersection(vb_rect)
                            if not ring.is_empty:
                                shapes.append((stroke_z, sc, ring))
                        except Exception:
                            pass
                else:
                    sc, sw = _get_stroke_attrs(elem)
                    if sc:
                        sg = _build_stroke_geom([pts], max(sw, MIN_STROKE_SVG) / 2.0,
                                                child_clip)
                        if sg is not None:
                            shapes.append((stroke_z, sc, sg))
            path_total[0] += 1

        elif local_tag == 'circle':
            fill_z   = path_total[0] * 2
            stroke_z = path_total[0] * 2 + 1
            try:
                cx = float(elem.get('cx', 0) or 0)
                cy = float(elem.get('cy', 0) or 0)
                r  = float(elem.get('r',  0) or 0)
            except (ValueError, TypeError):
                r = 0.0
            if r > 0:
                n = max(32, int(2 * math.pi * r * density))
                pts = np.array([(cx + r * math.cos(2 * math.pi * k / n),
                                 cy + r * math.sin(2 * math.pi * k / n))
                                for k in range(n)], dtype=float)
                if child_tf is not None:
                    pts = _apply_transform(pts, child_tf)
                pts[:, 1] = vb_max_y - pts[:, 1]
                if eff:
                    fill_geom = _add_shape(fill_z, eff, [pts], child_clip)
                    sc, sw = _get_stroke_attrs(elem)
                    if sc and sc != eff and fill_geom is not None and not fill_geom.is_empty:
                        half_w = max(sw, MIN_STROKE_SVG) / 2.0
                        try:
                            ring = fill_geom.buffer(half_w).difference(fill_geom)
                            if child_clip is not None:
                                ring = ring.intersection(child_clip)
                            ring = ring.intersection(vb_rect)
                            if not ring.is_empty:
                                shapes.append((stroke_z, sc, ring))
                        except Exception:
                            pass
                else:
                    sc, sw = _get_stroke_attrs(elem)
                    if sc:
                        sg = _build_stroke_geom([pts], max(sw, MIN_STROKE_SVG) / 2.0,
                                                child_clip)
                        if sg is not None:
                            shapes.append((stroke_z, sc, sg))
            path_total[0] += 1

        elif local_tag == 'ellipse':
            fill_z   = path_total[0] * 2
            stroke_z = path_total[0] * 2 + 1
            try:
                cx = float(elem.get('cx', 0) or 0)
                cy = float(elem.get('cy', 0) or 0)
                rx = float(elem.get('rx', 0) or 0)
                ry = float(elem.get('ry', 0) or 0)
            except (ValueError, TypeError):
                rx = ry = 0.0
            if rx > 0 and ry > 0:
                n = max(32, int(2 * math.pi * max(rx, ry) * density))
                pts = np.array([(cx + rx * math.cos(2 * math.pi * k / n),
                                 cy + ry * math.sin(2 * math.pi * k / n))
                                for k in range(n)], dtype=float)
                if child_tf is not None:
                    pts = _apply_transform(pts, child_tf)
                pts[:, 1] = vb_max_y - pts[:, 1]
                if eff:
                    fill_geom = _add_shape(fill_z, eff, [pts], child_clip)
                    sc, sw = _get_stroke_attrs(elem)
                    if sc and sc != eff and fill_geom is not None and not fill_geom.is_empty:
                        half_w = max(sw, MIN_STROKE_SVG) / 2.0
                        try:
                            ring = fill_geom.buffer(half_w).difference(fill_geom)
                            if child_clip is not None:
                                ring = ring.intersection(child_clip)
                            ring = ring.intersection(vb_rect)
                            if not ring.is_empty:
                                shapes.append((stroke_z, sc, ring))
                        except Exception:
                            pass
                else:
                    sc, sw = _get_stroke_attrs(elem)
                    if sc:
                        sg = _build_stroke_geom([pts], max(sw, MIN_STROKE_SVG) / 2.0,
                                                child_clip)
                        if sg is not None:
                            shapes.append((stroke_z, sc, sg))
            path_total[0] += 1

        elif local_tag in ('polygon', 'polyline'):
            fill_z   = path_total[0] * 2
            stroke_z = path_total[0] * 2 + 1
            pts_str = elem.get('points', '')
            if pts_str:
                try:
                    nums = [float(x) for x in re.split(r'[\s,]+', pts_str.strip()) if x]
                    if len(nums) >= 6:
                        pts = np.array(list(zip(nums[0::2], nums[1::2])), dtype=float)
                        if child_tf is not None:
                            pts = _apply_transform(pts, child_tf)
                        pts[:, 1] = vb_max_y - pts[:, 1]
                        if eff:
                            fill_geom = _add_shape(fill_z, eff, [pts], child_clip)
                            sc, sw = _get_stroke_attrs(elem)
                            if sc and sc != eff and fill_geom is not None and not fill_geom.is_empty:
                                half_w = max(sw, MIN_STROKE_SVG) / 2.0
                                try:
                                    ring = fill_geom.buffer(half_w).difference(fill_geom)
                                    if child_clip is not None:
                                        ring = ring.intersection(child_clip)
                                    ring = ring.intersection(vb_rect)
                                    if not ring.is_empty:
                                        shapes.append((stroke_z, sc, ring))
                                except Exception:
                                    pass
                        else:
                            sc, sw = _get_stroke_attrs(elem)
                            if sc:
                                sg = _build_stroke_geom([pts], max(sw, MIN_STROKE_SVG) / 2.0,
                                                        child_clip)
                                if sg is not None:
                                    shapes.append((stroke_z, sc, sg))
                except (ValueError, TypeError):
                    pass
            path_total[0] += 1

        elif local_tag == 'use':
            href = elem.get(f'{xlinkns}href') or elem.get('href', '')
            if href.startswith('#'):
                ref_elem = id_map.get(href[1:])
                if ref_elem is not None:
                    walk(ref_elem, eff, child_tf, child_clip, depth + 1)
                    # When the USE element itself has stroke attrs but fill=none,
                    # those attrs are not seen by walk() because eff is already None.
                    # Render the referenced path as an explicit stroke shape here.
                    if not eff:
                        use_sc, use_sw = _get_stroke_attrs(elem)
                        if use_sc:
                            ref_tag = (ref_elem.tag
                                       .replace(svgns, '')
                                       .replace('{http://www.w3.org/2000/svg}', ''))
                            if ref_tag == 'path':
                                d = ref_elem.get('d', '')
                                if d:
                                    try:
                                        fp = parse_path(d)
                                        use_pts = []
                                        for pts in _split_path_into_subpath_points(fp, density):
                                            if child_tf is not None:
                                                pts = _apply_transform(pts, child_tf)
                                            pts[:, 1] = vb_max_y - pts[:, 1]
                                            use_pts.append(pts)
                                        if use_pts:
                                            if child_tf is not None:
                                                _sx = math.sqrt(child_tf[0]**2 + child_tf[1]**2)
                                                _sy = math.sqrt(child_tf[2]**2 + child_tf[3]**2)
                                                _ts = math.sqrt(_sx * _sy)
                                                if _ts > 0:
                                                    use_sw *= _ts
                                            half_w = max(use_sw, MIN_STROKE_SVG) / 2.0
                                            stroke_z = path_total[0] * 2 + 1
                                            path_total[0] += 1
                                            sg = _build_stroke_geom(use_pts, half_w, child_clip)
                                            if sg is not None and not sg.is_empty:
                                                shapes.append((stroke_z, use_sc, sg))
                                    except Exception:
                                        pass

        else:
            for child in elem:
                walk(child, eff, child_tf, child_clip, depth + 1)

    walk(root, '#000000', None, None)
    log(f"Collected {len(shapes)} shapes from {path_total[0]} elements, "
        f"{len({c for _,c,_ in shapes})} colours")

    # ── Per-shape painter's algorithm ─────────────────────────
    # Process shapes highest-z first.  Each shape's visible area is what remains
    # after removing all already-claimed (higher-z) geometry.
    shapes.sort(key=lambda s: s[0], reverse=True)
    covered_all   = Polygon()   # union of all claimed geometry regardless of colour
    covered_by_c  = {}          # per-colour union — same-colour shapes stack without blocking each other
    color_visible = {}

    for _z, color, geom in shapes:
        try:
            # A shape can only be blocked by geometry of a *different* colour drawn on top.
            # Same-colour higher-z shapes (e.g. Australia's blue correction patches) should
            # not prevent lower-z same-colour shapes (the base blue field) from claiming area.
            other_covered = covered_all.difference(covered_by_c.get(color, Polygon()))
            visible = geom.difference(other_covered)
            if not visible.is_empty:
                color_visible.setdefault(color, []).append(visible)
            covered_by_c[color] = covered_by_c.get(color, Polygon()).union(geom)
            covered_all = covered_all.union(geom)
        except Exception:
            color_visible.setdefault(color, []).append(geom)

    color_geoms = {}
    for color, geom_list in color_visible.items():
        try:
            merged = unary_union(geom_list)
            if not merged.is_empty:
                color_geoms[color] = merged
        except Exception as e:
            log(f"  Warning merging {color}: {e}")

    log(f"Resulting colour zones: {len(color_geoms)}")
    return color_geoms, (vb_w, vb_h)


# ──────────────────────────────────────────────────────────────
# 3MF PARSER  (for importing existing keychains)
# ──────────────────────────────────────────────────────────────

def _fill_holes(geom):
    """Remove interior rings (e.g. a keychain ring-hole) from a polygon."""
    if isinstance(geom, Polygon):
        return Polygon(geom.exterior)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([Polygon(p.exterior) for p in geom.geoms])
    return geom


def parse_3mf(path, log=None):
    """Extract colour zones from a BambuStudio 3MF file.

    Works for files generated by this app and for Fusion-360-sourced models
    coloured in BambuStudio.  Returns (color_geoms, None) in the same format
    as parse_svg() so it feeds directly into the build pipeline.

    Parses the XML directly to avoid trimesh naming ambiguity.
    """
    if log is None:
        log = print

    NS = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'

    with zipfile.ZipFile(path) as zf:
        names_in_zip = zf.namelist()

        # ── extruder index → hex colour ─────────────────────────────────────
        color_by_extruder = {}
        if 'Metadata/project_settings.config' in names_in_zip:
            try:
                proj = json.loads(zf.read('Metadata/project_settings.config'))
                for i, c in enumerate(proj.get('filament_colour', [])):
                    color_by_extruder[i + 1] = c.upper()
            except Exception:
                pass

        # ── object id → extruder; per-part extruders; negative_part ids ────────
        extruder_by_id  = {}   # object-level extruder (fallback)
        part_exts_by_id = {}   # oid → [ext_for_part0, ext_for_part1, ...]
        negative_ids    = set()
        if 'Metadata/model_settings.config' in names_in_zip:
            try:
                cfg = ET.fromstring(zf.read('Metadata/model_settings.config'))
                for obj in cfg.findall('object'):
                    oid = obj.get('id', '')
                    if any(p.get('subtype') == 'negative_part'
                           for p in obj.findall('part')):
                        negative_ids.add(oid)
                        continue
                    obj_ext = 1
                    for m in obj.findall('metadata'):
                        if m.get('key') == 'extruder':
                            try:
                                obj_ext = int(m.get('value', 1))
                            except ValueError:
                                pass
                    extruder_by_id[oid] = obj_ext
                    parts = obj.findall('part')
                    if parts:
                        pexts = []
                        for p in parts:
                            if p.get('subtype') == 'negative_part':
                                pexts.append(None)
                                continue
                            pext = obj_ext
                            for pm in p.findall('metadata'):
                                if pm.get('key') == 'extruder' and pm.get('value'):
                                    try:
                                        pext = int(pm.get('value'))
                                    except ValueError:
                                        pass
                            pexts.append(pext)
                        part_exts_by_id[oid] = pexts
            except Exception:
                pass

        # ── parse mesh data from all .model files ────────────────────────────
        mesh_by_id = {}   # object_id_str → (verts float64, faces int32)
        comp_by_id = {}   # object_id_str → [(ref_id, transform_str), ...]

        model_files = sorted(n for n in names_in_zip if n.endswith('.model'))
        for mf in model_files:
            try:
                root = ET.fromstring(zf.read(mf))
                for obj in root.findall(f'.//{NS}object'):
                    oid = obj.get('id', '')
                    # Component reference (Ireland-style shared mesh)
                    comps_el = obj.find(f'{NS}components')
                    if comps_el is not None:
                        refs = [(c.get('objectid', ''), c.get('transform', ''))
                                for c in comps_el.findall(f'{NS}component')]
                        comp_by_id[oid] = refs
                        continue
                    mesh_el = obj.find(f'{NS}mesh')
                    if mesh_el is None:
                        continue
                    verts_el = mesh_el.find(f'{NS}vertices')
                    tris_el  = mesh_el.find(f'{NS}triangles')
                    if verts_el is None or tris_el is None:
                        continue
                    verts = np.array(
                        [[float(v.get('x', 0)), float(v.get('y', 0)),
                          float(v.get('z', 0))]
                         for v in verts_el.findall(f'{NS}vertex')],
                        dtype=np.float64)
                    faces = np.array(
                        [[int(t.get('v1', 0)), int(t.get('v2', 0)),
                          int(t.get('v3', 0))]
                         for t in tris_el.findall(f'{NS}triangle')],
                        dtype=np.int32)
                    if len(verts) > 0 and len(faces) > 0:
                        mesh_by_id[oid] = (verts, faces)
            except Exception as e:
                if log:
                    log(f"  Warning: could not parse {mf}: {e}")

        # ── get build items (top-level instances with extruder assignments) ──
        instances = []   # list of (object_id, transform_str)
        if '3D/3dmodel.model' in names_in_zip:
            try:
                root = ET.fromstring(zf.read('3D/3dmodel.model'))
                build_el = root.find(f'{NS}build')
                if build_el is not None:
                    for item in build_el.findall(f'{NS}item'):
                        instances.append((item.get('objectid', ''),
                                          item.get('transform', '')))
            except Exception:
                pass
        if not instances:
            instances = [(oid, '') for oid in extruder_by_id]

    # Deduplicate plate copies: group instances by their component signature.
    # A plate of N identical keychains → only process one representative.
    def _sig(inst_id):
        if inst_id in comp_by_id:
            return frozenset(ref for ref, _ in comp_by_id[inst_id]
                             if ref not in negative_ids)
        return inst_id

    seen_sigs      = set()
    dedup_instances = []
    for inst_id, inst_tf in instances:
        s = _sig(inst_id)
        if s not in seen_sigs:
            seen_sigs.add(s)
            dedup_instances.append((inst_id, inst_tf))

    log(f"3MF: {len(instances)} instance(s) → {len(dedup_instances)} unique shape(s), "
        f"{len(mesh_by_id)} mesh object(s)")

    def _apply_transform(verts, transform_str):
        if not transform_str:
            return verts
        try:
            vals = [float(x) for x in transform_str.split()]
            if len(vals) != 12:
                return verts
            mat = np.eye(4)
            mat[:3, 0] = vals[0:3]
            mat[:3, 1] = vals[3:6]
            mat[:3, 2] = vals[6:9]
            mat[:3, 3] = vals[9:12]
            ones = np.ones((len(verts), 1))
            return (mat @ np.hstack([verts, ones]).T).T[:, :3]
        except Exception:
            return verts

    def _footprint(verts, faces):
        """Return Shapely polygon(s) from the bottom (Z = min) cross-section.

        Vertices MUST already be in world/build-plate coordinates (inst_transform
        applied) so that Z is the print-height axis (thin dimension) and the XY
        plane is the build plate.  We section at Z = min_z and drop Z, which
        preserves the global XY positions — meaning all colour components from
        the same instance stay correctly aligned with each other.
        """
        min_z = float(verts[:, 2].min())
        mesh  = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        try:
            sec = mesh.section(plane_origin=[0, 0, min_z + 0.001],
                               plane_normal=[0, 0, 1])
            if sec is None:
                raise ValueError("no section")
            sv    = sec.vertices[:, :2]   # drop Z → global XY
            polys = []
            for ent in sec.entities:
                pts = sv[ent.points]
                if len(pts) < 3:
                    continue
                try:
                    poly = _fill_holes(Polygon(pts))
                    if not poly.is_empty and poly.area > 0.001:
                        polys.append(poly)
                except Exception:
                    pass
            if polys:
                return polys
        except Exception:
            pass
        # Fallback: convex hull of bottom-face XY vertices
        bottom = verts[verts[:, 2] < min_z + 0.1][:, :2]
        if len(bottom) >= 3:
            hull = Polygon(bottom).convex_hull
            if hull and not hull.is_empty:
                return [hull]
        return []

    # ── extract 2-D footprint per unique instance and assign colour ──────────
    # Apply inst_transform first so all components land in world Z-up space
    # (the build-plate frame BambuStudio uses).  That makes Z the thin axis
    # and ensures every colour zone shares the same XY coordinate system.
    color_polys = {}
    for inst_id, inst_transform in dedup_instances:
        if inst_id in negative_ids:
            continue

        if inst_id in comp_by_id:
            # Multi-component: each component can have its own extruder/colour.
            pexts   = [e for e in part_exts_by_id.get(inst_id, []) if e is not None]
            obj_ext = extruder_by_id.get(inst_id, 1)

            for comp_idx, (ref_id, comp_xf) in enumerate(comp_by_id[inst_id]):
                if ref_id in negative_ids:
                    continue
                ext   = pexts[comp_idx] if comp_idx < len(pexts) else obj_ext
                color = color_by_extruder.get(ext, '#000000')

                if ref_id not in mesh_by_id:
                    continue
                verts, faces = mesh_by_id[ref_id]
                if comp_xf:                                   # component → object local
                    verts = _apply_transform(verts, comp_xf)
                verts = _apply_transform(verts, inst_transform)  # object local → world
                polys = _footprint(verts, faces)
                if polys:
                    color_polys.setdefault(color, []).extend(polys)
        else:
            # Single mesh — use object-level extruder.
            extruder = extruder_by_id.get(inst_id, 1)
            color    = color_by_extruder.get(extruder, '#000000')
            if inst_id not in mesh_by_id:
                continue
            verts, faces = mesh_by_id[inst_id]
            verts = _apply_transform(verts, inst_transform)   # local → world
            polys = _footprint(verts, faces)
            if polys:
                color_polys.setdefault(color, []).extend(polys)

    if not color_polys:
        raise ValueError(
            "Could not extract colour regions from this 3MF.\n"
            "Make sure colour assignments are set in BambuStudio.")

    color_geoms = {}
    for color, polys in color_polys.items():
        try:
            merged = unary_union(polys)
            if not merged.is_empty:
                color_geoms[color] = merged
        except Exception:
            pass

    log(f"Extracted {len(color_geoms)} colour zone(s): {', '.join(color_geoms)}")
    return color_geoms, None


# ──────────────────────────────────────────────────────────────
# SHARED HEIGHT CONSTRAINTS
# ──────────────────────────────────────────────────────────────

_MIN_BASE = 3.0   # base layer (largest area) always ≥ this — shared double-sided flag body
_MAX_TOP  = 5.5   # tallest colour target ceiling (2.5 mm of stepping room)
_MIN_STEP = 0.4   # preferred height difference between adjacent colour levels (visual relief)
_MAX_STEP = 1.0   # maximum height difference between adjacent colour levels

# Keychain-specific (double-sided) "3D map relief": the flag reads on the flat
# BOTTOM face, and on the TOP each colour rises in its map shape to its own
# height — so the flag also reads on top as 3D relief. Each colour is extruded
# z=0 → its stepped height; largest-area (field) colour is the flat base (the
# sturdy bulk), smaller colours / emblems step up. Print with the per-object
# filament the .3mf assigns (NOT by-height) — colours share layers, which is fine.
_KC_FLAG_BASE = 4.0   # base height — largest-area (field) colour = the sturdy bulk (mm)
_KC_MAX_TOP   = 5.5   # tallest (smallest-area) colour = top of the relief (mm)
_KC_MAX_STEP  = 1.5   # cap the jump between adjacent colour levels (avoid fragile walls)
_MIN_POLY_MM2 = 0.1  # minimum area per individual polygon — sub-0.1 mm² pieces can't print on a 0.4 mm nozzle

_MAG_DIAM = 5.1   # magnet pocket diameter mm (includes print tolerance)

# Base layers are stored under this prefix so they always occupy a separate
# BambuStudio extruder slot, independent of any flag colour that shares the hex.
_BASE_PREFIX = '_base_'

def _display_colour(key):
    """Strip _BASE_PREFIX from a mesh-dict key to get the actual hex colour."""
    return key[len(_BASE_PREFIX):] if key.startswith(_BASE_PREFIX) else key


def _make_base_shape(combined_geom, padding=3.0, resolution=32):
    """Return a smooth base silhouette that traces the flag geometry outline.

    Uses morphological dilation (buffer): the base extends `padding` mm beyond
    the flag map in every direction.  Coastal details smaller than the buffer
    radius disappear into smooth curves; major peninsulas and bays are
    preserved.  The result is organic and shape-faithful, not a bounding box.
    """
    return combined_geom.buffer(padding, quad_segs=resolution)


def _resolve_far_islands(scaled, base_padding=3.0, log=None):
    """Remove islands too far from the mainland to sit naturally on a keychain.

    The base is a buffer of `base_padding` mm, so it automatically welds any
    components within 2×base_padding of each other — narrow straits read as
    water and the web is solid. Anything farther would only attach by a long,
    thin bridge that looks unnatural and snaps in a pocket, so we drop it rather
    than connect it. Keeps the whole base-connected cluster the mainland belongs
    to (so island chains across narrow water survive), removes the rest.
    Returns (new_scaled, None) — second value kept for call-site compatibility."""
    if log is None:
        log = print
    combined = unary_union(list(scaled.values()))
    comps = list(combined.geoms) if isinstance(combined, MultiPolygon) else [combined]
    if len(comps) <= 1:
        return scaled, None
    main = max(comps, key=lambda c: c.area)
    # The base merges everything its buffer touches; keep only the blob the
    # mainland sits in, drop islands that would need a fragile bridge.
    base = combined.buffer(base_padding)
    blobs = list(base.geoms) if isinstance(base, MultiPolygon) else [base]
    main_blob = next((b for b in blobs if b.intersects(main)), None)
    if main_blob is None:
        return scaled, None
    to_remove = [c for c in comps if c is not main and not main_blob.intersects(c)]
    if to_remove:
        cut = unary_union(to_remove)
        scaled = {col: g.difference(cut) for col, g in scaled.items()}
        scaled = {col: g for col, g in scaled.items() if not g.is_empty}
        log(f"  Removed {len(to_remove)} far island(s) "
            f"(too distant to connect naturally — bridge would be fragile)")
    return scaled, None


def _color_diff(h1, h2):
    """RGB Euclidean distance between two hex colours, normalised 0–1."""
    def parse(h):
        h = h.lstrip('#')
        return [int(h[i:i+2], 16) for i in (0, 2, 4)]
    c1, c2 = parse(h1), parse(h2)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2))) / (255 * math.sqrt(3))


def _coerce_to_polygon(g):
    """Fix invalid geometry and return only Polygon/MultiPolygon, or None.

    buffer(0) in Shapely 2.x can return a GeometryCollection whose .boundary
    is None, breaking downstream operations.  make_valid is more robust and
    still extracts polygon parts from any mixed-type result.
    """
    if g is None or g.is_empty:
        return None
    if g.is_valid and isinstance(g, (Polygon, MultiPolygon)):
        return g
    try:
        from shapely import make_valid
        g = make_valid(g)
    except Exception:
        g = g.buffer(0)
    if isinstance(g, (Polygon, MultiPolygon)):
        return g if not g.is_empty else None
    if hasattr(g, 'geoms'):
        polys = [sub for sub in g.geoms
                 if isinstance(sub, (Polygon, MultiPolygon)) and not sub.is_empty]
        if not polys:
            return None
        return unary_union(polys) if len(polys) > 1 else polys[0]
    return None


def _apply_relative_island_filter(scaled, rel_threshold, log):
    """Remove disconnected polygons smaller than rel_threshold × largest single polygon.

    Geographic-significance gate: offshore specks become water; named islands
    (Crete, Cozumel, Kyushu…) that are large enough relative to the main body survive.
    Only called when a base/water layer is active.
    """
    max_poly_area = 0.0
    for geom in scaled.values():
        polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
        for p in polys:
            if p.area > max_poly_area:
                max_poly_area = p.area

    if max_poly_area == 0:
        return scaled

    cutoff = rel_threshold * max_poly_area
    result = {}
    removed = 0
    for color, geom in scaled.items():
        if isinstance(geom, MultiPolygon):
            kept = [p for p in geom.geoms if p.area >= cutoff]
            removed += len(list(geom.geoms)) - len(kept)
            if not kept:
                continue
            result[color] = unary_union(kept) if len(kept) > 1 else kept[0]
        else:
            if geom.area >= cutoff:
                result[color] = geom
            else:
                removed += 1

    if removed:
        log(f"  Relative island filter ({rel_threshold * 100:.1f}% of main): "
            f"removed {removed} tiny piece(s)")
    return result


# ── Offshore-island printability gate (tunable) ───────────────
_ISLAND_MIN_AREA_MM2  = 1.0   # offshore island below this looks like a speck → remove
_ISLAND_MIN_WIDTH_MM  = 0.6   # offshore island thinner than this can't print cleanly → remove
_AUTO_BASE_COLOUR     = '#0f4c81'  # marine blue — colour of the auto-added water base


def _island_thresholds(nozzle_mm):
    """Printability-only island thresholds, scaled to the nozzle. A 0.2 mm
    nozzle prints finer features, so it keeps smaller real islands; a 0.4 mm
    nozzle needs them chunkier. Keeps every island the nozzle can actually
    print, removes only true sub-printable specks (geographic accuracy)."""
    if nozzle_mm <= 0.25:        # 0.2 mm nozzle — keep finer islands
        return 0.5, 0.35
    return _ISLAND_MIN_AREA_MM2, _ISLAND_MIN_WIDTH_MM   # 0.4 mm nozzle
_ISLAND_DETAIL_PAD_MM = 0.2   # tiny outward pad on the land footprint for numerical
                              # robustness (edge-adjacent detail); kept small so it does
                              # NOT reach offshore specks just past the coastline


def _piece_min_width(poly):
    """Approximate the narrowest dimension of a polygon via erosion (binary search).
    Returns the largest w such that poly.buffer(-w/2) is still non-empty — i.e. the
    diameter of the widest disc that fits inside the narrowest neck."""
    lo, hi = 0.0, 3.0
    if not poly.buffer(-hi / 2).is_empty:
        return hi
    for _ in range(18):
        mid = (lo + hi) / 2
        if poly.buffer(-mid / 2).is_empty:
            hi = mid
        else:
            lo = mid
    return lo


def _detail_min_width(nozzle_mm):
    """Smallest stroke a nozzle can render as a clean, legible feature.
    Below this, motto text / fine emblem strokes print as an illegible smudge."""
    return 0.40 if nozzle_mm <= 0.25 else 0.60


def _fill_tiny_holes(poly, hole_min_width_mm, hole_min_area_mm2):
    """Fill interior holes too small/thin to print as clean negative space — the
    letter counters punched into a motto band (Brazil's 'Ordem e Progresso'),
    pin-prick star holes, fine emblem gaps. Large structural cutouts (the rhombus
    in a flag field, the globe inside it) are kept. The keychain ring is drilled
    later, so it isn't present here and can't be filled by accident."""
    if not poly.interiors:
        return poly, 0
    keep_rings = []
    filled = 0
    for ring in poly.interiors:
        ip = Polygon(ring)
        if ip.area >= hole_min_area_mm2 and _piece_min_width(ip) >= hole_min_width_mm:
            keep_rings.append(ring)
        else:
            filled += 1
    if filled == 0:
        return poly, 0
    return Polygon(poly.exterior, keep_rings), filled


def _remove_unprintable_detail(scaled, min_width_mm, max_area_mm2=10.0, log=None):
    """Auto-omit sub-printable on-map detail so it doesn't print as a blur, while
    keeping the banner/emblem SHAPE. Two passes:
      1. Drop standalone pieces that are BOTH thinner than min_width_mm AND small
         (< max_area) — stray motto strokes, specks.
      2. Fill interior holes too small/thin to print cleanly — the letter counters
         cut into a motto band, star pin-holes — so the band stays a clean solid.
    Wide features and anything the nozzle can resolve are untouched."""
    if log is None:
        log = print
    hole_w = min_width_mm * 1.5          # a hole must be wider than a wall to print clean
    hole_a = max(2.0, max_area_mm2 * 0.2)
    removed = 0
    holes_filled = 0
    result = {}
    for color, geom in scaled.items():
        polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
        keep = []
        for p in polys:
            if p.area >= max_area_mm2 or _piece_min_width(p) >= min_width_mm:
                p2, f = _fill_tiny_holes(p, hole_w, hole_a)
                holes_filled += f
                keep.append(p2)
            else:
                removed += 1
        if keep:
            result[color] = unary_union(keep) if len(keep) > 1 else keep[0]
    if removed or holes_filled:
        log(f"  Auto-simplify: dropped {removed} sub-printable piece(s), "
            f"filled {holes_filled} sub-printable hole(s) "
            f"(< {min_width_mm:g} mm detail — would print illegibly)")
    return result if result else scaled


def _filter_printable_islands(scaled, min_area_mm2=_ISLAND_MIN_AREA_MM2,
                              min_width_mm=_ISLAND_MIN_WIDTH_MM, log=None):
    """Remove tiny OFFSHORE islands that print as ugly specks, while protecting
    on-map flag detail (text, stars, crescents, coats of arms) AND real islands.

    Discriminator = footprint containment against the LAND. The map silhouette
    (union of all colours) is split into connected components. Every component
    that itself clears the area+width thresholds is "land" and is always kept
    (the mainland and every real island — Japan's four islands, NZ's two, the
    larger Aegean isles). The union of all land footprints, padded outward, is
    the protected region: any small component whose interior point lands inside
    it is flag detail sitting on the map (Saudi shahada, Chile's canton star,
    Brazil's stars) and is kept. A small component OUTSIDE all land footprints is
    a genuine offshore speck and is removed. Runs only when there is more than
    one silhouette component, so continental flags are untouched.
    """
    if log is None:
        log = print
    if not scaled:
        return scaled

    sil = unary_union(list(scaled.values()))
    comps = list(sil.geoms) if isinstance(sil, MultiPolygon) else [sil]
    if len(comps) <= 1:
        return scaled

    def _is_land(c):
        return c.area >= min_area_mm2 and _piece_min_width(c) >= min_width_mm

    land = [c for c in comps if _is_land(c)]
    if not land:                                   # nothing clears the bar — keep largest as land
        land = [max(comps, key=lambda c: c.area)]

    land_set = set(id(c) for c in land)
    try:
        footprint = unary_union([Polygon(c.exterior) for c in land]).buffer(_ISLAND_DETAIL_PAD_MM)
    except Exception:
        footprint = unary_union(land).buffer(_ISLAND_DETAIL_PAD_MM)

    removable = []
    for c in comps:
        if id(c) in land_set:
            continue                               # real landmass / island → keep
        if footprint.contains(c.representative_point()):
            continue                               # flag detail on the map → keep
        removable.append(c)                        # small + offshore → remove

    if not removable:
        return scaled

    cut = unary_union(removable)
    result = {}
    for color, geom in scaled.items():
        g = geom.difference(cut)
        if not g.is_empty:
            result[color] = g
    log(f"  Island filter: removed {len(removable)} tiny offshore piece(s) "
        f"(< {min_area_mm2:g} mm² or < {min_width_mm:g} mm wide); on-map flag detail kept")
    return result if result else scaled


def merge_similar_colors(color_geoms, threshold=15, log=None):
    """Merge colour zones whose RGB Euclidean distance is ≤ threshold (0–255 scale).

    Useful for coats-of-arms SVGs (e.g. Ecuador) where auto-tracing creates dozens
    of near-identical orange/yellow shades.  Returns a new dict with fewer zones;
    the canonical key for each cluster is the member with the largest total area.
    threshold=0 disables merging entirely.
    """
    if log is None:
        log = print
    if threshold <= 0 or len(color_geoms) <= 1:
        return color_geoms

    def _rgb(h):
        h = h.lstrip('#')
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _dist(a, b):
        ra, ga, ba = _rgb(a)
        rb, gb, bb = _rgb(b)
        return math.sqrt((ra-rb)**2 + (ga-gb)**2 + (ba-bb)**2)

    colors = sorted(color_geoms.keys(), key=lambda c: color_geoms[c].area, reverse=True)
    assigned = set()
    clusters = []
    for c in colors:
        if c in assigned:
            continue
        cluster = [c]
        assigned.add(c)
        for other in colors:
            if other not in assigned and _dist(c, other) <= threshold:
                cluster.append(other)
                assigned.add(other)
        clusters.append(cluster)

    if len(clusters) == len(colors):
        return color_geoms

    result = {}
    for cluster in clusters:
        canonical = cluster[0]  # already sorted largest-area first
        if len(cluster) == 1:
            result[canonical] = color_geoms[canonical]
        else:
            merged = unary_union([color_geoms[c] for c in cluster])
            result[canonical] = merged
            log(f"  Colour merge: {canonical} ← {' + '.join(cluster[1:])} "
                f"(Δ_max={max(_dist(canonical, o) for o in cluster[1:]):.0f})")

    if len(result) < len(color_geoms):
        log(f"  Merged {len(color_geoms)} → {len(result)} colour zones (threshold={threshold})")
    return result


def _compute_stepped_heights(area_order, log, layer_mm=0.12,
                             min_base=None, max_top=None, max_step=None):
    """Give every colour a DISTINCT top height — never two on the same level — so
    a height-based filament assignment needs only one swap per colour (fewer
    colour changes, faster print). The first colour in `area_order` gets min_base
    (lowest), the last gets up toward max_top (tallest); pass the colours sorted
    so the result matches the look you want (largest-area last → field is the
    tall body, terraced relief down to the small colours). Every colour mesh
    starts at z=0, so the bottom band is shared and multi-coloured: that shared
    region (0 → min_base) IS the double-sided flag face. Keeping min_base thin
    (≈1 mm) limits the multicolour zone to a few layers.

    Heights stay inside [min_base, max_top] when the colours fit. With many
    colours the step shrinks toward a printable floor (≥ 2 layers) rather than
    collapsing two colours onto one height; if even that overflows the cap it
    says so, since keychain thickness is limited."""
    if min_base is None:
        min_base = _MIN_BASE
    if max_top is None:
        max_top = _MAX_TOP
    if max_step is None:
        max_step = _MAX_STEP
    n = len(area_order)
    if n == 1:
        return {area_order[0]: min_base}

    available = max_top - min_base
    floor_step = max(2.0 * layer_mm, 0.12)   # ≥2 print layers so the slicer can split colours cleanly
    even_step = available / (n - 1)

    if even_step >= _MIN_STEP:
        # Room to spare — weight steps by colour difference so visually distant
        # neighbours get more physical separation. Floored at _MIN_STEP, capped
        # at max_step. (A large max_step lets the steps fill the full range so
        # the tallest colour actually reaches max_top.)
        diffs = [_color_diff(area_order[i], area_order[i + 1]) for i in range(n - 1)]
        total_diff = sum(diffs) or 1.0
        steps = [min(max(d / total_diff * available, _MIN_STEP), max_step) for d in diffs]
        total = sum(steps)
        if total > available:   # flooring at _MIN_STEP overshot — scale back the slack
            reducible = [(i, s - _MIN_STEP) for i, s in enumerate(steps) if s > _MIN_STEP]
            surplus = sum(a for _, a in reducible)
            if surplus > 0:
                excess = total - available
                for i, a in reducible:
                    steps[i] -= excess * (a / surplus)
        elif total < available:   # caps left slack — stretch up so the body reaches max_top
            headroom = [(i, max_step - s) for i, s in enumerate(steps) if s < max_step]
            slack = sum(a for _, a in headroom)
            if slack > 0:
                deficit = available - total
                for i, a in headroom:
                    steps[i] += deficit * (a / slack)
    else:
        # Too many colours to give each _MIN_STEP — use a uniform step so every
        # colour still lands on its own height. Shrink to the printable floor if
        # needed (and warn if that pushes past the thickness cap).
        step = max(even_step, floor_step)
        steps = [step] * (n - 1)
        if step > even_step:
            top = min_base + step * (n - 1)
            log(f"  Note: {n} colours — stepping at the {step:.2f} mm printable floor; "
                f"tallest reaches {top:.2f} mm (over the {max_top:.1f} mm target, but each "
                f"colour stays on its own layer).")

    heights = [min_base]
    for s in steps:
        heights.append(round(heights[-1] + s, 3))

    color_heights = {c: heights[i] for i, c in enumerate(area_order)}
    log("Stepped heights (every colour distinct):")
    for c in area_order:
        log(f"  {c}: {color_heights[c]:.2f} mm")
    return color_heights
_MAG_H    = 2.1   # magnet pocket depth mm
_MAG_BACK = 0.36  # solid back wall before pocket (3 × 0.12 mm layers)

# Double-sided keychain geometry constants
_DS_SHELL_H = 0.60   # coloured shell thickness each side (5 × 0.12 mm layers)
_DS_TOTAL_H = 4.0    # overall flat height — same for all colour zones
_DS_MID_COL = '#ffffff'  # neutral white middle core

# ──────────────────────────────────────────────────────────────
# 3-D KEYCHAIN BUILDER
# ──────────────────────────────────────────────────────────────

def _find_hole_xy(combined, hole_r):
    """Return (x, y) for the ring hole.

    Scans down from the top in 0.5 mm steps, trying the bounding-box centre X
    and several nearby X positions at each row.  The first (x, y) where a circle
    of radius (hole_r + 1 mm) fits entirely inside the shape is returned.
    Searches the top 35 % of the shape height; falls back to a relaxed margin
    (hole_r + 0.5) to handle fragmented zones like Colombia or narrow tips like
    Cameroon, ensuring the hole always lands inside solid geometry.
    """
    minx, miny, maxx, maxy = combined.bounds
    span_x = maxx - minx
    span_y = maxy - miny
    cx     = (minx + maxx) / 2
    margin = hole_r + 1.0
    margin_relaxed = hole_r + 0.5
    max_depth = span_y * 0.35

    x_offsets = [0, -0.10, 0.10, -0.20, 0.20, -0.30, 0.30, -0.40, 0.40]
    x_candidates = [cx + o * span_x for o in x_offsets]

    def _scan(m):
        cy = maxy - m
        while cy >= maxy - max_depth:
            for x in x_candidates:
                if minx + m <= x <= maxx - m:
                    try:
                        if combined.contains(Point(x, cy).buffer(m)):
                            return (x, cy)
                    except Exception:
                        pass
            cy -= 0.5
        return None

    result = _scan(margin) or _scan(margin_relaxed)
    if result:
        return result

    # Last resort: grid-sample the top strip for any valid interior point
    top_strip = combined.intersection(box(minx, maxy - max_depth, maxx, maxy))
    if not top_strip.is_empty:
        best = (None, maxy - max_depth)
        for ty in [maxy - margin_relaxed,
                   maxy - max_depth * 0.33,
                   maxy - max_depth * 0.66,
                   maxy - max_depth]:
            for tx in x_candidates:
                if not (minx + margin_relaxed <= tx <= maxx - margin_relaxed):
                    continue
                try:
                    if combined.contains(Point(tx, ty).buffer(margin_relaxed)):
                        if best[0] is None or ty > best[1]:
                            best = (tx, ty)
                except Exception:
                    pass
        if best[0] is not None:
            return best
        fcx = top_strip.centroid.x
        fcy = max(maxy - max_depth, maxy - margin_relaxed)
        return (fcx, fcy)

    return (cx, max(maxy - max_depth, maxy - margin_relaxed))


def _extrude_double_sided(geom, total_h=_DS_TOTAL_H, shell_h=_DS_SHELL_H):
    """Extrude two thin coloured shells — bottom (0→shell_h) and top (total_h-shell_h→total_h).

    The caller adds one combined mid-fill mesh separately so all colour zones share
    the same neutral core without overlap between extruder assignments.
    """
    bottom = _extrude(geom, shell_h)
    top    = _extrude(geom, shell_h)
    if top is not None:
        top.apply_translation([0, 0, total_h - shell_h])
    parts = [m for m in (bottom, top) if m is not None]
    return trimesh.util.concatenate(parts) if parts else None


def _extrude(geom, height):
    """Extrude a Polygon or MultiPolygon upward by height mm."""
    if isinstance(geom, Polygon):
        if geom.is_empty or geom.area < 0.01:
            return None
        try:
            return trimesh.creation.extrude_polygon(geom, height)
        except Exception:
            return None
    if isinstance(geom, MultiPolygon):
        parts = []
        for poly in geom.geoms:
            if not poly.is_empty and poly.area >= 0.01:
                try:
                    parts.append(trimesh.creation.extrude_polygon(poly, height))
                except Exception:
                    pass
        if parts:
            return trimesh.util.concatenate(parts)
    return None


def _find_magnet_positions(combined, mag_r, clearance=0.5):
    """Return ((lx,ly),(rx,ry)) for two magnet pockets inside the shape.

    Tries two layouts, both scanning the actual shape (not bounding box):
      1. Side-by-side  — left/right at ~1/3 and 2/3 of the row width.
         Works for wide shapes (Egypt, Canada, France, …).
      2. Top-and-bottom — one near top, one near bottom, centred horizontally.
         Works for tall/narrow shapes (Palestine, Italy, …).
    Falls back to a tighter clearance if the first pass fails, then retries on
    the convex hull (avoids coastline inlets blocking clearance checks), then
    uses a single centred pocket as a last resort.
    """

    def _search_two(shape):
        """Try side-by-side and top-and-bottom within `shape`. Returns pair or None."""
        boundary = shape.boundary
        minx, miny, maxx, maxy = shape.bounds
        total_h = maxy - miny
        total_w = maxx - minx

        def _side_by_side(margin):
            for y_frac in [0.50, 0.45, 0.55, 0.40, 0.60, 0.35, 0.65, 0.30, 0.70,
                           0.25, 0.75, 0.20, 0.80]:
                y   = miny + total_h * y_frac
                row = shape.intersection(
                    box(minx - 1, y - 0.05, maxx + 1, y + 0.05))
                if row.is_empty:
                    continue
                lx_min, _, rx_max, _ = row.bounds
                row_w = rx_max - lx_min
                if row_w < 4 * margin:
                    continue
                for x_frac in [1/3, 0.28, 0.38, 0.22, 0.42, 0.18, 0.46, 0.14, 0.48]:
                    lx = lx_min + row_w * x_frac
                    rx = rx_max - row_w * x_frac
                    if lx >= rx - 2 * margin:
                        continue
                    lp, rp = Point(lx, y), Point(rx, y)
                    if (shape.contains(lp) and shape.contains(rp) and
                            boundary.distance(lp) >= margin and
                            boundary.distance(rp) >= margin):
                        return (lx, y), (rx, y)
            return None

        def _top_and_bottom(margin):
            valid = []
            for y_frac in np.arange(0.10, 0.91, 0.04):
                y = miny + total_h * float(y_frac)
                for dx in [0.0, 0.08, -0.08, 0.15, -0.15, 0.22, -0.22]:
                    x = (minx + maxx) / 2 + total_w * dx
                    p = Point(x, y)
                    if shape.contains(p) and boundary.distance(p) >= margin:
                        valid.append((y_frac, x, y))
                        break
            if len(valid) < 2:
                return None
            lo = min(valid, key=lambda t: t[0])
            hi = max(valid, key=lambda t: t[0])
            if hi[0] - lo[0] < 0.15:
                return None
            cx = (minx + maxx) / 2
            for dx in [0.0, 0.08, -0.08, 0.15, -0.15, 0.22, -0.22, 0.28, -0.28]:
                x = cx + total_w * dx
                lp, hp = Point(x, lo[2]), Point(x, hi[2])
                if (shape.contains(lp) and shape.contains(hp) and
                        boundary.distance(lp) >= margin and
                        boundary.distance(hp) >= margin):
                    return (x, lo[2]), (x, hi[2])
            return (lo[1], lo[2]), (hi[1], hi[2])

        aspect = total_h / total_w if total_w > 0 else 1.0
        for margin in (mag_r + clearance, mag_r + 0.3):
            if aspect >= 1.2:
                r = _top_and_bottom(margin) or _side_by_side(margin)
            else:
                r = _side_by_side(margin) or _top_and_bottom(margin)
            if r:
                return r
        return None

    # First try on the actual shape.
    r = _search_two(combined)
    if r:
        return r

    # Retry on the convex hull — jagged coastlines and inlets can fail the
    # boundary-clearance check even when the interior is large enough.
    hull = combined.convex_hull
    r = _search_two(hull)
    if r:
        return r

    # Single-magnet fallback.
    print('  Shape too narrow for two magnet pockets — using single centred pocket')
    _hull = hull
    _h_minx, _h_miny, _h_maxx, _h_maxy = _hull.bounds
    _h_cx = (_h_minx + _h_maxx) / 2
    _h_w  = _h_maxx - _h_minx
    _h_h  = _h_maxy - _h_miny
    for fy_frac in [0.50, 0.40, 0.60, 0.35, 0.65, 0.30, 0.70]:
        fy = _h_miny + _h_h * fy_frac
        for dx in [0.0, 0.08, -0.08, 0.15, -0.15, 0.22, -0.22, 0.30, -0.30, 0.38, -0.38]:
            fx = _h_cx + _h_w * dx
            try:
                p = Point(fx, fy)
                if _hull.contains(p) and _hull.boundary.distance(p) >= mag_r + 0.3:
                    return (fx, fy), (fx, fy)  # duplicate = single pocket via unary_union
            except Exception:
                pass

    raise ValueError(
        "Could not place magnet pockets inside the flag shape — "
        "try a larger size or a simpler flag.")


def _extrude_with_pockets(geom, height, pockets_2d, z_lo, z_hi):
    """Extrude geom with cylindrical pockets cut between z_lo and z_hi.

    Splits the extrusion into three segments:
      Z=0      → z_lo  : solid back wall
      z_lo     → z_hi  : holed section (magnets inserted here mid-print)
      z_hi     → height: solid seal that hides the magnets
    """
    parts = []

    if z_lo > 0:
        m = _extrude(geom, z_lo)
        if m is not None:
            parts.append(m)

    geom_holed = geom
    for p in pockets_2d:
        geom_holed = geom_holed.difference(p)
    if not geom_holed.is_empty:
        m = _extrude(geom_holed, z_hi - z_lo)
        if m is not None:
            m.apply_translation([0, 0, z_lo])
            parts.append(m)

    if height > z_hi:
        m = _extrude(geom, height - z_hi)
        if m is not None:
            m.apply_translation([0, 0, z_hi])
            parts.append(m)

    return trimesh.util.concatenate(parts) if parts else None


def _build_mesh_with_satellites(geom, h, sat_h, stepped_heights, hole, log, color,
                                 pocket_fn=None):
    """Extrude the whole colour at a single height h.

    Every colour occupies exactly ONE height so a height-based filament
    assignment needs just one swap per colour (fewer colour changes). Small
    detail polygons (e.g. the USA stars) stay at the colour's own height rather
    than being elevated to a shared level: on a double-sided keychain they
    already read on the bottom face, and a shared elevated height would land
    several colours on the same top level. (`sat_h` is kept in the signature for
    call-site compatibility but no longer used.)

    pocket_fn: optional callable(geom, height) → mesh, used for magnet-pocket zones.
    """
    mesh = pocket_fn(geom, h) if pocket_fn is not None else _extrude(geom, h)
    if mesh is not None:
        log(f"  {color}: {h:.2f} mm, {len(mesh.vertices):,} verts, {len(mesh.faces):,} tris")
    return mesh


def build_keychain_meshes(color_geoms, max_size_mm=60.0, thickness_mm=5.0,
                          hole_diameter_mm=3.0, min_area_mm2=0.5,
                          stepped_heights=True, base_colour=None,
                          base_thickness_mm=2.0, nozzle_mm=0.4,
                          base_gap_only=True,
                          island_rel_threshold=0.01, color_merge_threshold=15,
                          log=None):
    """
    Scale, filter islands, punch a ring hole, and extrude each colour zone.
    With stepped_heights=True, each colour is extruded to a different height
    (largest area = shortest base, smallest area = tallest detail) so the
    print has a stepped 3-D relief and uses less filament on background layers.
    Returns {color_hex: trimesh.Trimesh}
    """
    if log is None:
        log = print

    if not color_geoms:
        raise ValueError("No colour regions found in SVG")

    color_geoms = merge_similar_colors(color_geoms, threshold=color_merge_threshold, log=log)

    combined_raw = unary_union(list(color_geoms.values()))
    if combined_raw.is_empty:
        raise ValueError("All geometries are empty")

    minx, miny, maxx, maxy = combined_raw.bounds
    raw_w = maxx - minx
    raw_h = maxy - miny
    if raw_w == 0 or raw_h == 0:
        raise ValueError("Degenerate bounding box")

    scale_f = max_size_mm / max(raw_w, raw_h)
    log(f"SVG span: {raw_w:.1f} × {raw_h:.1f} → ×{scale_f:.5f} → max {max_size_mm} mm")

    DEGENERATE_MM2 = 0.005  # floor for sub-pixel bezier artifacts

    scaled = {}
    for color, geom in color_geoms.items():
        g = translate(geom, -minx, -miny)
        g = shapely_scale(g, xfact=scale_f, yfact=scale_f, origin=(0, 0))

        g = _coerce_to_polygon(g)
        if g is None or g.is_empty:
            continue
        if isinstance(g, MultiPolygon):
            sorted_polys = sorted(
                [_coerce_to_polygon(p) for p in g.geoms],
                key=lambda p: p.area if p else 0, reverse=True
            )
            sorted_polys = [p for p in sorted_polys if p is not None and not p.is_empty]
            if not sorted_polys:
                continue
            # Flag-stripe detection: if the largest piece is 100× the second-largest,
            # this is a dominant stripe with scattered coat-of-arms fragments.
            # Apply the zone-total threshold to secondaries so tiny scatter pieces
            # don't appear as floating blobs in BambuStudio.
            if len(sorted_polys) >= 2 and sorted_polys[0].area > 100 * sorted_polys[1].area:
                secondary_min = max(DEGENERATE_MM2, min_area_mm2)
                kept = [sorted_polys[0]] + [p for p in sorted_polys[1:] if p.area >= secondary_min]
            else:
                per_poly_min = max(DEGENERATE_MM2, _MIN_POLY_MM2)
                kept = [p for p in sorted_polys if p.area >= per_poly_min]
            if not kept:
                continue
            g = unary_union(kept) if len(kept) > 1 else kept[0]
        elif isinstance(g, Polygon) and g.area < DEGENERATE_MM2:
            continue

        # Drop whole colour zones whose remaining area is still too small
        if g.area < min_area_mm2:
            continue

        if not g.is_empty:
            scaled[color] = g

    if not scaled:
        raise ValueError("No geometry left after minimum-area filter — try lowering Min island area")

    _isl_a, _isl_w = _island_thresholds(nozzle_mm)
    scaled = _filter_printable_islands(scaled, min_area_mm2=_isl_a, min_width_mm=_isl_w, log=log)

    # Remove islands too far to connect naturally — the base welds nearby pieces
    # across narrow water; anything beyond that is dropped (no fragile bridges).
    scaled, _ = _resolve_far_islands(scaled, base_padding=3.0, log=log)

    # Auto-omit detail too fine to print legibly (motto text, tiny strokes).
    scaled = _remove_unprintable_detail(scaled, _detail_min_width(nozzle_mm), log=log)

    if base_colour and island_rel_threshold > 0:
        scaled = _apply_relative_island_filter(scaled, island_rel_threshold, log)
        if not scaled:
            raise ValueError("All geometry removed by relative island filter — try lowering the threshold")

    # Auto-detect: add a base only for genuine geographic islands — i.e. pieces
    # that are both large enough (≥ 0.5 % of the main body) AND physically
    # separated from it (gap ≥ 0.2 mm at print scale).  This rejects flag-stripe
    # SVGs where stripes nearly-touch (gap ≈ 0 mm) while accepting real island
    # nations like Japan, Canada, New Zealand, and France (Corsica).
    if not base_colour:
        combined_check = unary_union(list(scaled.values()))
        if isinstance(combined_check, MultiPolygon):
            _polys = sorted(combined_check.geoms, key=lambda g: g.area, reverse=True)
            _main = _polys[0]
            _islands = [p for p in _polys[1:]
                        if p.area >= _main.area * 0.005
                        and _main.distance(p) >= 0.2]
            if _islands:
                base_colour = _AUTO_BASE_COLOUR   # marine blue (water)
                log(f"  Auto island base: {len(_islands) + 1} disconnected parts → "
                    f"adding marine-blue base ({base_colour})")

    log(f"After island filter: {len(scaled)} colour zones")

    # 3D map relief: each colour rises in its own map region to a distinct stepped
    # height. Largest-area (field) colour is the flat base (sturdy bulk); smaller
    # colours / emblems step UP — so the flag reads flat on the bottom and as 3D
    # relief on top. Print per-object (colours share layers).
    area_order = sorted(scaled.keys(), key=lambda c: scaled[c].area, reverse=True)  # largest first = base
    if stepped_heights and len(scaled) > 1:
        color_heights = _compute_stepped_heights(
            area_order, log, layer_mm=(0.08 if nozzle_mm <= 0.25 else 0.12),
            min_base=_KC_FLAG_BASE, max_top=_KC_MAX_TOP, max_step=_KC_MAX_STEP)
    else:
        color_heights = {c: _KC_FLAG_BASE for c in scaled}

    combined_scaled = unary_union(list(scaled.values()))
    hole_r = hole_diameter_mm / 2

    # Search the ring hole in the base silhouette (near the edge, not buried).
    if base_colour:
        base_rect = _make_base_shape(combined_scaled)
        _hole_search = base_rect
    else:
        base_rect = None
        _hole_search = combined_scaled

    hx, hy = _find_hole_xy(_hole_search, hole_r)
    hole   = Point(hx, hy).buffer(hole_r, quad_segs=32)

    # Verify hole doesn't split any colour zone by severing a thin neck.
    # (Hole is in the base border area when base is present, so this rarely fires.)
    for _attempt in range(3):
        _splits_zone = False
        for _c, _g in scaled.items():
            _after = _g.difference(hole)
            _before_n = len(list(_g.geoms)) if isinstance(_g, MultiPolygon) else 1
            _after_n  = len([p for p in (_after.geoms if isinstance(_after, MultiPolygon) else [_after])
                             if hasattr(p, 'area') and p.area > _MIN_POLY_MM2])
            if _after_n > _before_n:
                _splits_zone = True
                break
        if not _splits_zone:
            break
        log(f"  Hole at ({hx:.1f},{hy:.1f}) splits a zone — retrying deeper")
        hx, hy = _find_hole_xy(
            _hole_search.difference(Point(hx, hy).buffer(hole_r + 2.0)),
            hole_r
        )
        hole = Point(hx, hy).buffer(hole_r, quad_segs=32)

    log(f"Ring hole at ({hx:.1f}, {hy:.1f}) mm, ⌀{hole_diameter_mm} mm")

    sat_h = _MAX_TOP + _MIN_STEP   # detail polygons rise above tallest normal layer

    meshes = {}
    for color, geom in scaled.items():
        geom_cut = geom.difference(hole)
        if geom_cut.is_empty:
            continue
        h = color_heights.get(color, _KC_FLAG_BASE)
        mesh = _build_mesh_with_satellites(geom_cut, h, sat_h, stepped_heights, hole, log, color)
        if mesh is not None:
            meshes[color] = mesh

    if not meshes:
        raise ValueError("Extrusion produced no meshes")

    if base_colour:
        base_geom = base_rect.difference(hole)
        if base_gap_only:
            # Double-sided: fill ONLY the water gaps (everything in the padded
            # base shape that isn't a flag colour). This connects disconnected
            # islands without laying a slab under the map, so the flag stays
            # visible on the bottom face. Sit it flush with the flag face so the
            # bottom (first) layer is one solid multicolour plane (no empty/gappy
            # initial layer), and the water reads level with the shortest colour.
            base_geom = base_geom.difference(combined_scaled)
            base_h = _KC_FLAG_BASE
        else:
            base_h = base_thickness_mm
        # The water-gap polygon has a ragged coastline; clean off zero-width
        # slivers so the extrusion is watertight (a non-watertight base slices
        # with holes in the first layer).
        base_geom = _coerce_to_polygon(base_geom.buffer(0))
        base_mesh = _extrude(base_geom, base_h) if base_geom is not None else None
        if base_mesh is not None and not base_mesh.is_empty:
            base_key = _BASE_PREFIX + base_colour
            log(f"  Base layer ({base_colour}): {base_h:.2f} mm"
                + ("  (gap-only connector)" if base_gap_only else ""))
            meshes = {base_key: base_mesh, **meshes}

    return meshes


def build_keychain_meshes_double_sided(
        color_geoms, max_size_mm=60.0,
        hole_diameter_mm=3.0, min_area_mm2=0.5,
        base_colour=None, base_thickness_mm=2.0, nozzle_mm=0.4,
        island_rel_threshold=0.01,
        color_merge_threshold=15,
        shell_h=_DS_SHELL_H, total_h=_DS_TOTAL_H, mid_colour=_DS_MID_COL,
        log=None):
    """Double-sided keychain via colour = structure stepping.

    Each colour region is its own mesh extruded from z=0 to its own stepped
    height. At z=0 every region is present, so the full flag reads on the BOTTOM
    face; the differing heights give a 3D relief on the TOP face. No MMU paint
    and no neutral core — this is the cheapest, cleanest way to get both faces
    (matches the user's Palestine double-sided technique; "Option B" from the
    3D-printing research). total_h sets the tallest step; base/island handling,
    hole placement and nozzle-scaled island filtering all come from the stepped
    single-sided builder this delegates to.

    Returns {color_hex: trimesh.Trimesh}
    """
    if log is None:
        log = print

    # Double-sided is achieved by colour=structure stepping (3D-print research
    # "Option B"): each colour region is its own mesh from z=0 — so the flag
    # reads on the BOTTOM face — up to its own stepped height, giving the 3D
    # relief on the TOP face. No MMU paint, no neutral core (those waste filament
    # and band on stepped walls). The stepped single-sided builder already
    # produces exactly this, so delegate to it.
    log("Double-sided (colour = structure, stepped): flag on the bottom face, relief on top")
    return build_keychain_meshes(
        color_geoms,
        max_size_mm=max_size_mm,
        thickness_mm=total_h,
        hole_diameter_mm=hole_diameter_mm,
        min_area_mm2=min_area_mm2,
        stepped_heights=True,
        base_colour=base_colour,
        base_thickness_mm=base_thickness_mm,
        nozzle_mm=nozzle_mm,
        base_gap_only=True,        # keep the flag visible on the bottom face
        island_rel_threshold=island_rel_threshold,
        color_merge_threshold=color_merge_threshold,
        log=log,
    )


# ──────────────────────────────────────────────────────────────
# 3-D PLAQUE BUILDER
# ──────────────────────────────────────────────────────────────

def build_plaque_meshes(color_geoms, max_size_mm=100.0, thickness_mm=5.0,
                        min_area_mm2=0.5, stepped_heights=True, base_colour=None,
                        base_thickness_mm=2.0, nozzle_mm=0.4,
                        island_rel_threshold=0.01, color_merge_threshold=15,
                        log=None):
    """
    Like build_keychain_meshes but larger and without a keychain hole.

    Returns {color_hex: trimesh.Trimesh}
    """
    if log is None:
        log = print

    if not color_geoms:
        raise ValueError("No colour regions found in SVG")

    color_geoms = merge_similar_colors(color_geoms, threshold=color_merge_threshold, log=log)

    combined_raw = unary_union(list(color_geoms.values()))
    if combined_raw.is_empty:
        raise ValueError("All geometries are empty")

    minx, miny, maxx, maxy = combined_raw.bounds
    raw_w = maxx - minx
    raw_h = maxy - miny
    if raw_w == 0 or raw_h == 0:
        raise ValueError("Degenerate bounding box")

    scale_f = max_size_mm / max(raw_w, raw_h)
    log(f"SVG span: {raw_w:.1f} × {raw_h:.1f} → ×{scale_f:.5f} → max {max_size_mm} mm")

    DEGENERATE_MM2 = 0.005  # floor for sub-pixel bezier artifacts

    scaled = {}
    for color, geom in color_geoms.items():
        g = translate(geom, -minx, -miny)
        g = shapely_scale(g, xfact=scale_f, yfact=scale_f, origin=(0, 0))

        g = _coerce_to_polygon(g)
        if g is None or g.is_empty:
            continue
        if isinstance(g, MultiPolygon):
            per_poly_min = max(DEGENERATE_MM2, _MIN_POLY_MM2)
            kept = [_coerce_to_polygon(p) for p in g.geoms if p.area >= per_poly_min]
            kept = [p for p in kept if p is not None and not p.is_empty]
            if not kept:
                continue
            g = unary_union(kept) if len(kept) > 1 else kept[0]
        elif isinstance(g, Polygon) and g.area < DEGENERATE_MM2:
            continue

        if g.area < min_area_mm2:
            continue

        if not g.is_empty:
            scaled[color] = g

    if not scaled:
        raise ValueError("No geometry left after minimum-area filter — try lowering Min island area")

    _isl_a, _isl_w = _island_thresholds(nozzle_mm)
    scaled = _filter_printable_islands(scaled, min_area_mm2=_isl_a, min_width_mm=_isl_w, log=log)

    if base_colour and island_rel_threshold > 0:
        scaled = _apply_relative_island_filter(scaled, island_rel_threshold, log)
        if not scaled:
            raise ValueError("All geometry removed by relative island filter — try lowering the threshold")

    log(f"After island filter: {len(scaled)} colour zones")

    # Stepped heights (colour-diff weighted)
    area_order = sorted(scaled.keys(), key=lambda c: scaled[c].area, reverse=True)
    if stepped_heights and len(scaled) > 1:
        color_heights = _compute_stepped_heights(
            area_order, log, layer_mm=(0.08 if nozzle_mm <= 0.25 else 0.12))
    else:
        color_heights = {c: thickness_mm for c in scaled}

    combined_scaled = unary_union(list(scaled.values()))

    sat_h = _MAX_TOP + _MIN_STEP

    meshes = {}
    for color, geom in scaled.items():
        if geom.is_empty:
            continue
        h = color_heights.get(color, thickness_mm)
        mesh = _build_mesh_with_satellites(geom, h, sat_h, stepped_heights, None, log, color)
        if mesh is not None:
            meshes[color] = mesh

    if not meshes:
        raise ValueError("Extrusion produced no meshes")

    if base_colour:
        base_h = base_thickness_mm
        base_mesh = _extrude(_make_base_shape(combined_scaled), base_h)
        if base_mesh is not None:
            base_key = _BASE_PREFIX + base_colour
            log(f"  Base layer ({base_colour}): {base_h:.2f} mm")
            meshes = {base_key: base_mesh, **meshes}

    return meshes


# ──────────────────────────────────────────────────────────────
# 3-D FRIDGE-MAGNET BUILDER
# ──────────────────────────────────────────────────────────────

def build_magnet_meshes(color_geoms, max_size_mm=60.0, thickness_mm=5.0,
                        min_area_mm2=1.0, stepped_heights=True, base_colour=None,
                        base_thickness_mm=2.0, nozzle_mm=0.4,
                        island_rel_threshold=0.01, color_merge_threshold=15,
                        log=None):
    """Like build_keychain_meshes but without a ring hole and with two
    cylindrical pockets for hidden disc magnets.  If the shape is too flat
    for two pockets, a single centred pocket is used instead.

    Pockets: 5.1 mm dia × 2.1 mm deep, starting 0.36 mm from the back face.
    Pause the print at Z = 2.46 mm, insert magnets, resume to seal.
    Returns {color_hex: trimesh.Trimesh}
    """
    if log is None:
        log = print

    if not color_geoms:
        raise ValueError("No colour regions found")

    color_geoms = merge_similar_colors(color_geoms, threshold=color_merge_threshold, log=log)

    combined_raw = unary_union(list(color_geoms.values()))
    if combined_raw.is_empty:
        raise ValueError("All geometries are empty")

    minx, miny, maxx, maxy = combined_raw.bounds
    raw_w = maxx - minx
    raw_h = maxy - miny
    if raw_w == 0 or raw_h == 0:
        raise ValueError("Degenerate bounding box")

    scale_f = max_size_mm / max(raw_w, raw_h)
    log(f"Span: {raw_w:.1f} × {raw_h:.1f} → ×{scale_f:.5f} → max {max_size_mm} mm")

    DEGENERATE_MM2 = 0.005  # floor for sub-pixel bezier artifacts
    scaled = {}
    for color, geom in color_geoms.items():
        g = translate(geom, -minx, -miny)
        g = shapely_scale(g, xfact=scale_f, yfact=scale_f, origin=(0, 0))
        g = _coerce_to_polygon(g)
        if g is None or g.is_empty:
            continue
        if isinstance(g, MultiPolygon):
            per_poly_min = max(DEGENERATE_MM2, _MIN_POLY_MM2)
            kept = [_coerce_to_polygon(p) for p in g.geoms if p.area >= per_poly_min]
            kept = [p for p in kept if p is not None and not p.is_empty]
            if not kept:
                continue
            g = unary_union(kept) if len(kept) > 1 else kept[0]
        elif isinstance(g, Polygon) and g.area < DEGENERATE_MM2:
            continue
        if g.area < min_area_mm2:
            continue
        if not g.is_empty:
            scaled[color] = g

    if not scaled:
        raise ValueError("No geometry left after minimum-area filter")

    _isl_a, _isl_w = _island_thresholds(nozzle_mm)
    scaled = _filter_printable_islands(scaled, min_area_mm2=_isl_a, min_width_mm=_isl_w, log=log)

    if base_colour and island_rel_threshold > 0:
        scaled = _apply_relative_island_filter(scaled, island_rel_threshold, log)
        if not scaled:
            raise ValueError("All geometry removed by relative island filter — try lowering the threshold")

    log(f"After island filter: {len(scaled)} colour zones")

    area_order = sorted(scaled.keys(), key=lambda c: scaled[c].area, reverse=True)
    if stepped_heights and len(scaled) > 1:
        color_heights = _compute_stepped_heights(
            area_order, log, layer_mm=(0.08 if nozzle_mm <= 0.25 else 0.12))
    else:
        color_heights = {c: thickness_mm for c in scaled}

    combined_scaled = unary_union(list(scaled.values()))
    mag_r = _MAG_DIAM / 2

    # When a base is requested, compute its geometry now so that magnet
    # placement runs on the full convex base rectangle rather than the
    # jagged map outline — this guarantees two pockets fit (e.g. Canada).
    if base_colour:
        base_rect = _make_base_shape(combined_scaled)
        placement_geom = base_rect
    else:
        base_rect = None
        placement_geom = combined_scaled

    (lx, ly), (rx, ry) = _find_magnet_positions(placement_geom, mag_r)
    pockets_2d   = [Point(lx, ly).buffer(mag_r), Point(rx, ry).buffer(mag_r)]
    pocket_union = unary_union(pockets_2d)
    z_lo = _MAG_BACK
    z_hi = _MAG_BACK + _MAG_H
    log(f"Magnet pockets at ({lx:.1f}, {ly:.1f}) and ({rx:.1f}, {ry:.1f}) mm")
    log(f"Pocket Z range: {z_lo:.2f} → {z_hi:.2f} mm  "
        f"(pause at {z_hi:.2f} mm to insert magnets)")

    sat_h = _MAX_TOP + _MIN_STEP

    meshes = {}
    for color, geom in scaled.items():
        h = color_heights.get(color, thickness_mm)
        if geom.intersects(pocket_union):
            # Magnet pockets: extrude main body with pockets, satellites without
            mesh = _build_mesh_with_satellites(
                geom, h, sat_h, stepped_heights, None, log, color,
                pocket_fn=lambda g, hh: _extrude_with_pockets(g, hh, pockets_2d, z_lo, z_hi)
                    if g.intersects(pocket_union) else _extrude(g, hh))
        else:
            mesh = _build_mesh_with_satellites(geom, h, sat_h, stepped_heights, None, log, color)
        if mesh is not None:
            meshes[color] = mesh

    if not meshes:
        raise ValueError("Extrusion produced no meshes")

    if base_colour:
        base_h = base_thickness_mm
        if base_colour not in meshes:
            base_mesh = _extrude_with_pockets(base_rect, base_h, pockets_2d, z_lo, z_hi)
            if base_mesh is not None:
                base_key = _BASE_PREFIX + base_colour
                log(f"  Base layer ({base_colour}): {base_h:.2f} mm")
                meshes = {base_key: base_mesh, **meshes}

    return meshes


# ──────────────────────────────────────────────────────────────
# 3MF WRITER
# ──────────────────────────────────────────────────────────────

def write_3mf(color_meshes, output_path, log=None):
    """
    Write a BambuStudio-native 3MF.

    Produces the exact file structure BambuStudio creates itself:
    - Application metadata = BambuStudio-02.03.00.70  (removes "not created here" warning)
    - slice_info.config with X-BBL-Client-Type: slicer
    - model_settings.config with <part>, <plate>, and <assemble> sections
    - project_settings.config with 12-slot filament_colour array pre-loaded
      with the actual flag hex colours so BambuStudio shows them immediately
    """
    import datetime
    if log is None:
        log = print

    colors = list(color_meshes.keys())
    n = len(colors)
    log(f"Writing 3MF: {n} colour zones → {Path(output_path).name}")

    SLOTS = max(12, n)
    if n > 16:
        log(f'Warning: {n} colours exceed 16 AMS slots — BambuStudio shows all parts '
            f'but only 16 can be physically loaded at once')
    slot_colors = [_display_colour(c).upper() for c in colors] + ['#FFFFFF'] * (SLOTS - n)
    today = datetime.date.today().isoformat()

    def _flist(v):
        return [v] * SLOTS

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:

        # ── [Content_Types].xml ──────────────────────────────────
        zf.writestr('[Content_Types].xml', (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
            ' <Default Extension="png" ContentType="image/png"/>\n'
            ' <Default Extension="gcode" ContentType="text/x.gcode"/>\n'
            '</Types>'
        ))

        # ── _rels/.rels ──────────────────────────────────────────
        zf.writestr('_rels/.rels', (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            ' <Relationship Target="/3D/3dmodel.model" Id="rel-1"'
            ' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            '</Relationships>'
        ))

        # ── 3D/3dmodel.model ─────────────────────────────────────
        buf = io.StringIO()
        buf.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        buf.write(
            '<model unit="millimeter" xml:lang="en-US"'
            ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
            ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
            ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
            ' requiredextensions="p">\n'
        )
        buf.write(f' <metadata name="Application">BambuStudio-02.03.00.70</metadata>\n')
        buf.write(f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n')
        buf.write(f' <metadata name="CreationDate">{today}</metadata>\n')
        buf.write(' <resources>\n')
        for i, color in enumerate(colors):
            oid  = i + 1
            mesh = color_meshes[color]
            buf.write(f'  <object id="{oid}" p:UUID="{oid:08d}-61cb-4c03-9d28-80fed5dfa1dc" type="model">\n')
            buf.write('   <mesh>\n    <vertices>\n')
            for v in mesh.vertices:
                buf.write(f'     <vertex x="{v[0]:.5f}" y="{v[1]:.5f}" z="{v[2]:.5f}"/>\n')
            buf.write('    </vertices>\n    <triangles>\n')
            for f in mesh.faces:
                buf.write(f'     <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>\n')
            buf.write('    </triangles>\n   </mesh>\n  </object>\n')
        buf.write(' </resources>\n <build>\n')
        for i in range(n):
            buf.write(f'  <item objectid="{i+1}" transform="1 0 0 0 1 0 0 0 1 0 0 0" printable="1"/>\n')
        buf.write(' </build>\n</model>')
        zf.writestr('3D/3dmodel.model', buf.getvalue())

        # ── Metadata/slice_info.config ───────────────────────────
        zf.writestr('Metadata/slice_info.config', (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<config>\n'
            '  <header>\n'
            '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
            '    <header_item key="X-BBL-Client-Version" value="02.03.00.70"/>\n'
            '  </header>\n'
            '</config>'
        ))

        # ── Metadata/model_settings.config ───────────────────────
        fmaps = ' '.join([str(i + 1) for i in range(n)])
        cfg = ['<?xml version="1.0" encoding="UTF-8"?>\n<config>']
        for i, color in enumerate(colors):
            oid  = i + 1
            mesh = color_meshes[color]
            fc   = len(mesh.faces)
            dc   = _display_colour(color)
            name = f'Zone_{dc.lstrip("#")}'
            cfg.append(
                f'  <object id="{oid}">\n'
                f'    <metadata key="name" value="{name}"/>\n'
                f'    <metadata key="extruder" value="{oid}"/>\n'
                f'    <metadata face_count="{fc}"/>\n'
                f'    <part id="{oid}" subtype="normal_part">\n'
                f'      <metadata key="name" value="{name}"/>\n'
                f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                f'      <metadata key="source_file" value="{name}.stl"/>\n'
                f'      <metadata key="source_object_id" value="{i}"/>\n'
                f'      <metadata key="source_volume_id" value="0"/>\n'
                f'      <metadata key="source_offset_x" value="0"/>\n'
                f'      <metadata key="source_offset_y" value="0"/>\n'
                f'      <metadata key="source_offset_z" value="0"/>\n'
                f'      <mesh_stat face_count="{fc}" edges_fixed="0" degenerate_facets="0"'
                f' facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
                f'    </part>\n'
                f'  </object>'
            )
        cfg.append(
            f'  <plate>\n'
            f'    <metadata key="plater_id" value="1"/>\n'
            f'    <metadata key="plater_name" value=""/>\n'
            f'    <metadata key="locked" value="false"/>\n'
            f'    <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
            f'    <metadata key="filament_maps" value="{fmaps}"/>'
        )
        for i in range(n):
            cfg.append(
                f'    <model_instance>\n'
                f'      <metadata key="object_id" value="{i+1}"/>\n'
                f'      <metadata key="instance_id" value="0"/>\n'
                f'      <metadata key="identify_id" value="{i+1}"/>\n'
                f'    </model_instance>'
            )
        cfg.append('  </plate>')
        cfg.append('  <assemble>')
        for i in range(n):
            cfg.append(
                f'   <assemble_item object_id="{i+1}" instance_id="0"'
                f' transform="1 0 0 0 1 0 0 0 1 0 0 0" offset="0 0 0" />'
            )
        cfg.append('  </assemble>\n</config>')
        zf.writestr('Metadata/model_settings.config', '\n'.join(cfg))

        # ── Metadata/project_settings.config ─────────────────────
        project = {
            "layer_height":                      "0.12",
            "initial_layer_print_height":        "0.10",
            "nozzle_diameter":                   ["0.4"],
            "single_extruder_multi_material":    1,
            "filament_colour":                   slot_colors,
            "filament_multi_colour":             slot_colors,
            "filament_type":                     _flist("PLA"),
            "filament_settings_id":              _flist("Bambu PLA Basic @BBL A1"),
            "filament_ids":                      _flist("GFA00"),
            "filament_vendor":                   _flist("Bambu Lab"),
            "filament_density":                  _flist("1.26"),
            "filament_diameter":                 _flist("1.75"),
            "filament_flow_ratio":               _flist("0.98"),
            "filament_max_volumetric_speed":     _flist("21"),
            "filament_is_support":               _flist("0"),
            "filament_soluble":                  _flist("0"),
            "filament_map":                      _flist("1"),
            "filament_map_mode":                 "Auto For Flush",
            "filament_printable":                _flist("1"),
            "filament_self_index":               [str(i + 1) for i in range(SLOTS)],
            "filament_long_retractions_when_cut":    _flist("1"),
            "filament_retraction_distances_when_cut": _flist("18"),
            "filament_minimal_purge_on_wipe_tower":  _flist("15"),
            "filament_prime_volume":             _flist("30"),
            "nozzle_temperature":                _flist("220"),
            "nozzle_temperature_initial_layer":  _flist("220"),
            "nozzle_temperature_range_high":     _flist("240"),
            "nozzle_temperature_range_low":      _flist("190"),
            "wall_loops":                        "3",
            "top_shell_layers":                  "7",
            "bottom_shell_layers":               "5",
            "sparse_infill_density":             "15%",
            "wall_filament":                     1,
            "sparse_infill_filament":            1,
            "solid_infill_filament":             1,
            "support_filament":                  0,
            "support_interface_filament":        0,
            "print_extruder_id":                 ["1"],
        }
        zf.writestr('Metadata/project_settings.config', json.dumps(project, indent=2))

    log(f"Saved: {output_path}")
    log("\nFilament guide — load these colours in Bambu Studio:")
    for i, color in enumerate(colors):
        dc = _display_colour(color)
        name = _approximate_color_name(dc)
        suffix = f"  ({name})" if name else ''
        log(f"  Extruder {i + 1}:  {dc.upper()}{suffix}")
    log("  Colours are pre-loaded in the 3MF — open it in Bambu Studio and they appear automatically.")


# ──────────────────────────────────────────────────────────────
# GUI APPLICATION
# ──────────────────────────────────────────────────────────────

def reveal_in_file_manager(path):
    """Show a generated file in the OS file manager. Arguments are passed as a
    list (never through a shell) so file names with quotes cannot run commands."""
    import subprocess, sys as _sys
    path = str(path)
    if _sys.platform == 'darwin':
        cmd = ['open', '-R', path]
    elif _sys.platform.startswith('win'):
        cmd = ['explorer', '/select,', path]
    else:
        cmd = ['xdg-open', str(Path(path).parent)]
    try:
        subprocess.Popen(cmd)
    except OSError:
        return None
    return cmd


class App(_TkBase):
    def __init__(self):
        super().__init__()
        self.title("SVG Keychain 3MF")
        self._build_ui()
        # Force window to center of screen at a fixed size
        self.update_idletasks()
        w, h = 460, 680
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f'{w}x{h}+{x}+{y}')
        # Bring to front on macOS
        self.lift()
        self.attributes('-topmost', True)
        self.after(200, lambda: self.attributes('-topmost', False))
        self.focus_force()
        # Attempt Tk drag-and-drop (needs tkdnd package; silently skipped if absent)
        try:
            self.tk.call('package', 'require', 'tkdnd')
            self._svg_entry.drop_target_register('DND_Files')  # type: ignore
            self._svg_entry.dnd_bind('<<Drop>>', self._on_drop)  # type: ignore
        except Exception:
            pass

    def _build_ui(self):
        BG    = '#1e1e1e'
        FG    = '#e0e0e0'
        ENTRY = '#2d2d2d'
        BTN   = '#2a6fdb'
        BTNF  = '#ffffff'

        self.configure(bg=BG)
        main = tk.Frame(self, bg=BG, padx=20, pady=16)
        main.pack(fill='both', expand=True)

        tk.Label(main, text="SVG Keychain 3MF",
                 font=('Helvetica', 20, 'bold'), bg=BG, fg=FG).pack()
        tk.Label(main, text="SVG  →  Bambu Studio 3MF",
                 font=('Helvetica', 11), fg='#888', bg=BG).pack(pady=(2, 14))

        # SVG file picker
        tk.Label(main, text="SVG file:", anchor='w', bg=BG, fg=FG,
                 font=('Helvetica', 12)).pack(fill='x')
        self._svg_var = tk.StringVar()
        self._svg_entry = tk.Entry(main, textvariable=self._svg_var,
                                   font=('Helvetica', 11), relief='flat', bd=1,
                                   bg=ENTRY, fg=FG, insertbackground=FG,
                                   highlightbackground='#444', highlightthickness=1)
        self._svg_entry.pack(fill='x', ipady=4, pady=(3, 6))
        tk.Button(main, text="Browse for SVG file…",
                  font=('Helvetica', 13, 'bold'),
                  bg=BTN, fg=BTNF, activebackground='#1a5fcc', activeforeground=BTNF,
                  relief='flat', cursor='hand2', pady=8,
                  command=self._browse).pack(fill='x', pady=(0, 16))

        # Settings box
        sf = tk.LabelFrame(main, text=" Settings ", bg=BG, fg=FG,
                           font=('Helvetica', 11, 'bold'), pady=6, padx=10)
        sf.pack(fill='x', pady=(0, 12))

        self._keychain_size   = tk.DoubleVar(value=60.0)
        self._plaque_size     = tk.DoubleVar(value=100.0)
        self._magnet_size     = tk.DoubleVar(value=60.0)
        self._thickness       = tk.DoubleVar(value=5.0)
        self._hole_diam       = tk.DoubleVar(value=3.0)
        self._min_area        = tk.DoubleVar(value=1.0)
        self._nozzle          = tk.DoubleVar(value=0.4)   # 0.4 simple / 0.2 detailed
        self._stepped_heights      = tk.BooleanVar(value=True)
        self._base_layer           = tk.BooleanVar(value=False)
        self._base_colour          = tk.StringVar(value='#0f4c81')   # marine blue
        self._base_thickness       = tk.DoubleVar(value=2.0)
        self._island_rel_threshold = tk.DoubleVar(value=1.0)
        self._gen_keychain         = tk.BooleanVar(value=True)
        self._gen_plaque           = tk.BooleanVar(value=True)
        self._gen_magnet           = tk.BooleanVar(value=True)
        self._double_sided         = tk.BooleanVar(value=False)
        self._color_merge_thresh   = tk.DoubleVar(value=15.0)

        def spinrow(label, var, from_, to, row, incr=0.5):
            lbl = tk.Label(sf, text=label, anchor='e', bg=BG, fg=FG,
                           font=('Helvetica', 11))
            lbl.grid(row=row, column=0, sticky='e', padx=(0, 6), pady=3)
            spn = tk.Spinbox(sf, textvariable=var, from_=from_, to=to,
                             increment=incr, width=8, font=('Helvetica', 11),
                             bg=ENTRY, fg=FG, buttonbackground='#3c3c3c',
                             insertbackground=FG, disabledforeground='#666',
                             disabledbackground=ENTRY)
            spn.grid(row=row, column=1, sticky='w', pady=3)
            return lbl, spn

        self._kc_widgets  = spinrow("Keychain size (mm):",    self._keychain_size, 20,  200, 0)
        self._pl_widgets  = spinrow("Plaque size (mm):",      self._plaque_size,   20,  400, 1)
        self._mag_widgets = spinrow("Fridge magnet size (mm):", self._magnet_size, 20,  200, 2)
        spinrow("Thickness (mm):",        self._thickness,     1.0, 10.0, 3)
        spinrow("Hole diameter (mm):",    self._hole_diam,     1.0, 8.0,  4)
        spinrow("Min island area (mm²):", self._min_area,      0.5, 100.0, 5)

        tk.Checkbutton(sf, text="Stepped heights (3D relief, saves filament)",
                       variable=self._stepped_heights, bg=BG, fg=FG,
                       selectcolor=ENTRY, activebackground=BG, activeforeground=FG,
                       font=('Helvetica', 11), anchor='w'
                       ).grid(row=6, column=0, columnspan=2, sticky='w', pady=(4, 2))

        # Base layer row
        base_row = tk.Frame(sf, bg=BG)
        base_row.grid(row=7, column=0, columnspan=2, sticky='w', pady=(2, 0))
        tk.Checkbutton(base_row, text="Base/water layer:", variable=self._base_layer,
                       bg=BG, fg=FG, selectcolor=ENTRY,
                       activebackground=BG, activeforeground=FG,
                       font=('Helvetica', 11),
                       command=self._on_toggle_base_layer).pack(side='left')
        self._base_colour_btn = tk.Button(
            base_row, text=f"  {self._base_colour.get()}  ",
            bg=self._base_colour.get(), fg='white',
            font=('Helvetica', 10), relief='flat', padx=4,
            state='disabled', command=self._pick_base_colour)
        self._base_colour_btn.pack(side='left', padx=(6, 0))
        tk.Label(base_row, text="thick:", bg=BG, fg=FG,
                 font=('Helvetica', 10)).pack(side='left', padx=(10, 2))
        self._base_thick_spn = tk.Spinbox(
            base_row, textvariable=self._base_thickness,
            from_=0.5, to=10.0, increment=0.5, width=4,
            font=('Helvetica', 10), bg=ENTRY, fg=FG,
            buttonbackground='#3c3c3c', insertbackground=FG,
            disabledforeground='#666', disabledbackground=ENTRY,
            state='disabled')
        self._base_thick_spn.pack(side='left')
        tk.Label(base_row, text="mm", bg=BG, fg=FG,
                 font=('Helvetica', 10)).pack(side='left', padx=(2, 0))

        self._island_rel_widgets = spinrow(
            "Min island size (% of main):", self._island_rel_threshold,
            0.1, 20.0, 8, incr=0.5)
        for w in self._island_rel_widgets:
            w.config(state='disabled')

        gen_row = tk.Frame(sf, bg=BG)
        gen_row.grid(row=9, column=0, columnspan=2, sticky='w', pady=(2, 0))
        tk.Label(gen_row, text="Generate:", bg=BG, fg=FG,
                 font=('Helvetica', 11)).pack(side='left', padx=(0, 6))
        tk.Checkbutton(gen_row, text="Keychain",     variable=self._gen_keychain,
                       bg=BG, fg=FG, selectcolor=ENTRY,
                       activebackground=BG, activeforeground=FG,
                       font=('Helvetica', 11),
                       command=self._on_toggle_outputs).pack(side='left', padx=(0, 4))
        tk.Checkbutton(gen_row, text="Plaque",       variable=self._gen_plaque,
                       bg=BG, fg=FG, selectcolor=ENTRY,
                       activebackground=BG, activeforeground=FG,
                       font=('Helvetica', 11),
                       command=self._on_toggle_outputs).pack(side='left', padx=(0, 4))
        tk.Checkbutton(gen_row, text="Fridge Magnet", variable=self._gen_magnet,
                       bg=BG, fg=FG, selectcolor=ENTRY,
                       activebackground=BG, activeforeground=FG,
                       font=('Helvetica', 11),
                       command=self._on_toggle_outputs).pack(side='left')

        self._on_toggle_outputs()

        # Double-sided row
        ds_row = tk.Frame(sf, bg=BG)
        ds_row.grid(row=10, column=0, columnspan=2, sticky='w', pady=(2, 0))
        tk.Checkbutton(ds_row, text="Double-sided keychain",
                       variable=self._double_sided,
                       bg=BG, fg=FG, selectcolor=ENTRY,
                       activebackground=BG, activeforeground=FG,
                       font=('Helvetica', 11)).pack(side='left', padx=(0, 8))

        # Colour-merge threshold row
        spinrow("Colour merge threshold (0=off):", self._color_merge_thresh, 0, 50, 11, incr=5)

        # Nozzle row — drives the printable feature/island thresholds
        nozzle_row = tk.Frame(sf, bg=BG)
        nozzle_row.grid(row=12, column=0, columnspan=2, sticky='w', pady=(4, 0))
        tk.Label(nozzle_row, text="Nozzle:", bg=BG, fg=FG,
                 font=('Helvetica', 11)).pack(side='left', padx=(0, 6))
        self._nozzle_label = tk.StringVar(value='0.4 mm (simple shapes)')
        def _set_nozzle(choice):
            self._nozzle.set(0.2 if choice.startswith('0.2') else 0.4)
            self._nozzle_label.set(choice)
        om = tk.OptionMenu(nozzle_row, self._nozzle_label,
                           '0.4 mm (simple shapes)', '0.2 mm (fine detail / islands)',
                           command=_set_nozzle)
        om.config(bg=ENTRY, fg=FG, activebackground='#3c3c3c', activeforeground=FG,
                  highlightthickness=0, font=('Helvetica', 10), width=22)
        om['menu'].config(bg=ENTRY, fg=FG)
        om.pack(side='left')

        # Generate button
        self._gen_btn = tk.Button(
            main, text="▶  Generate 3MF",
            font=('Helvetica', 14, 'bold'),
            bg='#27ae60', fg='white',
            activebackground='#1e8449', activeforeground='white',
            disabledforeground='#aaa',
            relief='flat', cursor='hand2', pady=10,
            command=self._generate)
        self._gen_btn.pack(fill='x', pady=(0, 10))

        # Log output
        tk.Label(main, text="Output:", anchor='w', bg=BG, fg=FG,
                 font=('Helvetica', 11)).pack(fill='x')
        log_frame = tk.Frame(main, bg=BG)
        log_frame.pack(fill='both', expand=True, pady=(3, 0))
        self._log_box = tk.Text(log_frame, height=12, state='disabled',
                                font=('Courier', 11), bg='#141414', fg='#d4d4d4',
                                relief='flat', bd=0, wrap='word')
        self._log_box.pack(side='left', fill='both', expand=True)
        sb = tk.Scrollbar(log_frame, command=self._log_box.yview,
                          bg='#3c3c3c', troughcolor='#2d2d2d',
                          activebackground='#555555')
        sb.pack(side='right', fill='y')
        self._log_box.config(yscrollcommand=sb.set)

    def _on_toggle_outputs(self):
        for w in self._kc_widgets:
            w.config(state='normal' if self._gen_keychain.get() else 'disabled')
        for w in self._pl_widgets:
            w.config(state='normal' if self._gen_plaque.get() else 'disabled')
        for w in self._mag_widgets:
            w.config(state='normal' if self._gen_magnet.get() else 'disabled')

    def _on_toggle_base_layer(self):
        on = self._base_layer.get()
        self._base_colour_btn.config(state='normal' if on else 'disabled')
        self._base_thick_spn.config(state='normal' if on else 'disabled')
        for w in self._island_rel_widgets:
            w.config(state='normal' if on else 'disabled')

    def _pick_base_colour(self):
        result = colorchooser.askcolor(
            color=self._base_colour.get(),
            title="Pick water/base colour",
            parent=self)
        if result and result[1]:
            hex_col = result[1].lower()
            self._base_colour.set(hex_col)
            self._base_colour_btn.config(bg=hex_col, text=f'  {hex_col}  ')

    def _on_drop(self, event):
        path = event.data.strip('{}')
        if path.lower().endswith(('.svg', '.3mf')):
            self._svg_var.set(path)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select a flag-map SVG or 3MF",
            filetypes=[("Supported files", "*.svg *.3mf"),
                       ("SVG files", "*.svg"),
                       ("3MF files", "*.3mf"),
                       ("All files", "*.*")])
        if path:
            self._svg_var.set(path)

    def _log(self, msg):
        self._log_box.config(state='normal')
        self._log_box.insert('end', msg + '\n')
        self._log_box.see('end')
        self._log_box.config(state='disabled')
        self.update_idletasks()

    def _generate(self):
        svg_path = self._svg_var.get().strip()
        if not svg_path or not Path(svg_path).is_file():
            messagebox.showerror("No file", "Please select an SVG file first.")
            return
        self._gen_btn.config(state='disabled')
        self._log_box.config(state='normal')
        self._log_box.delete('1.0', 'end')
        self._log_box.config(state='disabled')
        self._log(f"Starting: {Path(svg_path).name}\n")
        threading.Thread(target=self._worker, args=(svg_path,), daemon=True).start()


    def _worker(self, input_path):
        try:
            # ── Parse input (SVG or 3MF) ─────────────────────────────────────
            ext = Path(input_path).suffix.lower()
            if ext == '.3mf':
                self._log("Parsing 3MF colour zones…")
                color_geoms, _vb = parse_3mf(input_path, log=self._log)
            else:
                if _RASTER_OK:
                    self._log("Reading SVG (render-then-vectorize)…")
                else:
                    self._log("Reading SVG (path parser; install cairosvg for higher fidelity)…")
                color_geoms, _vb = parse_svg_auto(
                    input_path, log=self._log,
                    nozzle_mm=self._nozzle.get(),
                    min_area_mm2=self._min_area.get())

            if not color_geoms:
                self._log("\nNo coloured regions detected.")
                if ext != '.3mf':
                    self._log("Tips:")
                    self._log("  • Use a Wikipedia 'flag map' SVG")
                    self._log("  • Make sure paths have fill= attributes")
                    self._log("  • Try flattening the SVG in Inkscape first")
                return

            self._log("\nColour zones detected:")
            for c, g in color_geoms.items():
                self._log(f"  {c}  (area {g.area:.0f} units²)")

            if not any([self._gen_keychain.get(),
                        self._gen_plaque.get(),
                        self._gen_magnet.get()]):
                self._log("\nERROR: Select at least one output type to generate.")
                return

            # Strip existing variant suffixes so 3MF inputs don't double-suffix
            stem = Path(input_path).stem
            for suf in ('_keychain', '_plaque', '_magnet'):
                if stem.endswith(suf):
                    stem = stem[: -len(suf)]
                    break

            generated = []

            # ── Keychain ─────────────────────────────────────────────────────
            base_colour      = self._base_colour.get().lower() if self._base_layer.get() else None
            base_thick       = self._base_thickness.get()
            island_rel       = self._island_rel_threshold.get() / 100.0
            merge_thresh     = int(self._color_merge_thresh.get())
            nozzle           = self._nozzle.get()

            if self._gen_keychain.get():
                if self._double_sided.get():
                    self._log("\nBuilding double-sided keychain meshes…")
                    km = build_keychain_meshes_double_sided(
                        color_geoms,
                        max_size_mm            = self._keychain_size.get(),
                        hole_diameter_mm       = self._hole_diam.get(),
                        min_area_mm2           = self._min_area.get(),
                        base_colour            = base_colour,
                        base_thickness_mm      = base_thick,
                        nozzle_mm              = nozzle,
                        island_rel_threshold   = island_rel,
                        color_merge_threshold  = merge_thresh,
                        log                    = self._log,
                    )
                else:
                    self._log("\nBuilding keychain meshes…")
                    km = build_keychain_meshes(
                        color_geoms,
                        max_size_mm            = self._keychain_size.get(),
                        thickness_mm           = self._thickness.get(),
                        hole_diameter_mm       = self._hole_diam.get(),
                        min_area_mm2           = self._min_area.get(),
                        stepped_heights        = self._stepped_heights.get(),
                        base_colour            = base_colour,
                        base_thickness_mm      = base_thick,
                        nozzle_mm              = nozzle,
                        island_rel_threshold   = island_rel,
                        color_merge_threshold  = merge_thresh,
                        log                    = self._log,
                    )
                kp = Path(input_path).parent / f"{stem}_keychain.3mf"
                self._log("\nWriting keychain 3MF…")
                write_3mf(km, str(kp), log=self._log)
                generated.append((kp, len(km), "Keychain"))

            # ── Plaque ───────────────────────────────────────────────────────
            if self._gen_plaque.get():
                self._log("\nBuilding plaque meshes…")
                pm = build_plaque_meshes(
                    color_geoms,
                    max_size_mm            = self._plaque_size.get(),
                    thickness_mm           = self._thickness.get(),
                    min_area_mm2           = self._min_area.get(),
                    stepped_heights        = self._stepped_heights.get(),
                    base_colour            = base_colour,
                    base_thickness_mm      = base_thick,
                    nozzle_mm              = nozzle,
                    island_rel_threshold   = island_rel,
                    color_merge_threshold  = merge_thresh,
                    log                    = self._log,
                )
                pp = Path(input_path).parent / f"{stem}_plaque.3mf"
                self._log("\nWriting plaque 3MF…")
                write_3mf(pm, str(pp), log=self._log)
                generated.append((pp, len(pm), "Plaque"))

            # ── Fridge Magnet ────────────────────────────────────────────────
            if self._gen_magnet.get():
                self._log("\nBuilding fridge magnet meshes…")
                try:
                    mm = build_magnet_meshes(
                        color_geoms,
                        max_size_mm            = self._magnet_size.get(),
                        thickness_mm           = self._thickness.get(),
                        min_area_mm2           = self._min_area.get(),
                        stepped_heights        = self._stepped_heights.get(),
                        base_colour            = base_colour,
                        base_thickness_mm      = base_thick,
                        nozzle_mm              = nozzle,
                        island_rel_threshold   = island_rel,
                        color_merge_threshold  = merge_thresh,
                        log                    = self._log,
                    )
                    mp = Path(input_path).parent / f"{stem}_magnet.3mf"
                    self._log("\nWriting fridge magnet 3MF…")
                    write_3mf(mm, str(mp), log=self._log)
                    generated.append((mp, len(mm), "Fridge Magnet"))
                except ValueError as e:
                    self._log(f"\n[Fridge Magnet skipped] {e}")

            if not generated:
                return

            self._log(f"\n✓  Done!  {len(generated)} file(s) generated:")
            for path, n, label in generated:
                self._log(f"   {label} → {path.name}  ({n} colour parts)")
            self._log("\nOpen any file in BambuStudio — filament colours load automatically.")
            if reveal_in_file_manager(generated[0][0]) is None:
                self._log("(Could not open the file manager — files are in the same folder as the input.)")

        except Exception as exc:
            import traceback
            self._log(f"\nERROR: {exc}")
            self._log(traceback.format_exc())
        finally:
            self.after(0, lambda: self._gen_btn.config(state='normal'))


def _run_app():
    """Launch the GUI. A crash is shown in a dialog and saved to
    ~/svg-keychain-3mf_error.log, because a windowed launch has no terminal to print to."""
    if tk is None:
        raise ImportError(f"the desktop app needs Tk ({_TK_IMPORT_ERROR}); "
                          "install it (e.g. `sudo apt install python3-tk`) or use `svg-keychain generate`")
    try:
        App().mainloop()
    except Exception:
        import traceback, datetime
        tb = traceback.format_exc()
        try:
            logp = Path.home() / 'svg-keychain-3mf_error.log'
            logp.write_text(f"{datetime.datetime.now()}\n\n{tb}\n")
        except Exception:
            logp = None
        try:
            from tkinter import messagebox as _mb, Tk as _Tk
            _r = _Tk(); _r.withdraw()
            _mb.showerror(
                "SVG Keychain 3MF — error",
                "The app hit an error and must close.\n\n"
                + (f"Details saved to:\n{logp}\n\n" if logp else "")
                + tb[-800:])
        except Exception:
            print(tb)
        raise


if __name__ == '__main__':
    _run_app()
