import xml.etree.ElementTree as ET
import zipfile

import pytest
from shapely.geometry import Polygon

from svg_keychain_3mf import engine
from conftest import footprint, union_footprint

QUIET = dict(log=lambda _m: None)
READERS = [pytest.param(False, id="path-parser"),
           pytest.param(True, id="render-then-trace",
                        marks=pytest.mark.skipif(not engine._RASTER_OK, reason="cairosvg/OpenCV not installed"))]


def holes_of(geom):
    return [h for poly in getattr(geom, "geoms", [geom]) for h in poly.interiors]


@pytest.mark.parametrize("raster", READERS)
def test_reads_each_fill_colour_as_a_zone(fixture_svg, raster):
    geoms, _ = engine.parse_svg_auto(fixture_svg("tricolour.svg"), prefer_raster=raster, **QUIET)
    assert sorted(geoms) == ["#00838f", "#6a1b9a", "#ffffff"]


def test_unpainted_svg_gives_no_zones(fixture_svg):
    geoms, _ = engine.parse_svg_auto(fixture_svg("no-fills.svg"), prefer_raster=False, **QUIET)
    assert geoms == {}


@pytest.mark.parametrize("raster", READERS)
def test_keychain_is_printable(fixture_svg, raster):
    geoms, _ = engine.parse_svg_auto(fixture_svg("tricolour.svg"), prefer_raster=raster, **QUIET)
    meshes = engine.build_keychain_meshes(geoms, max_size_mm=60.0, **QUIET)

    assert len(meshes) == 3
    for m in meshes.values():
        assert m.is_watertight and m.volume > 0
    lo = [min(m.bounds[0][i] for m in meshes.values()) for i in (0, 1)]
    hi = [max(m.bounds[1][i] for m in meshes.values()) for i in (0, 1)]
    assert max(hi[0] - lo[0], hi[1] - lo[1]) == pytest.approx(60.0, abs=0.5)

    tops = {round(m.bounds[1][2], 2) for m in meshes.values()}
    assert len(tops) == 3, "stepped relief: every colour should end at its own height"


def test_flat_option_gives_one_height(fixture_svg):
    geoms, _ = engine.parse_svg_auto(fixture_svg("tricolour.svg"), prefer_raster=False, **QUIET)
    meshes = engine.build_keychain_meshes(geoms, stepped_heights=False, thickness_mm=4.0, **QUIET)
    assert {round(m.bounds[1][2], 2) for m in meshes.values()} == {4.0}


def test_keychain_has_a_ring_hole_and_plaque_does_not(fixture_svg):
    geoms, _ = engine.parse_svg_auto(fixture_svg("tricolour.svg"), prefer_raster=False, **QUIET)
    key = union_footprint(engine.build_keychain_meshes(geoms, hole_diameter_mm=3.0, **QUIET))
    plaque = union_footprint(engine.build_plaque_meshes(geoms, **QUIET))

    holes = holes_of(key)
    assert holes, "expected a key-ring hole through the keychain"
    assert Polygon(holes[0]).area == pytest.approx(3.14159 * 1.5 ** 2, rel=0.25)
    assert not holes_of(plaque)


def test_unprintable_specks_are_dropped(fixture_svg):
    geoms, _ = engine.parse_svg_auto(fixture_svg("island-map.svg"), prefer_raster=False, **QUIET)
    meshes = engine.build_keychain_meshes(geoms, max_size_mm=60.0, min_area_mm2=1.0, **QUIET)
    for colour, m in meshes.items():
        fp = footprint(m)
        for piece in getattr(fp, "geoms", [fp]):
            assert piece.area >= 1.0, f"{colour} kept a {piece.area:.2f} mm² speck"


def test_nested_ring_keeps_its_hole(fixture_svg):
    geoms, _ = engine.parse_svg_auto(fixture_svg("emblem.svg"), prefer_raster=False, **QUIET)
    meshes = engine.build_plaque_meshes(geoms, **QUIET)
    assert holes_of(footprint(meshes["#f2c300"]))


def test_double_sided_keychain_builds(fixture_svg):
    geoms, _ = engine.parse_svg_auto(fixture_svg("tricolour.svg"), prefer_raster=False, **QUIET)
    meshes = engine.build_keychain_meshes_double_sided(geoms, **QUIET)
    assert meshes and all(m.is_watertight for m in meshes.values())


def test_3mf_has_one_object_and_extruder_per_colour(fixture_svg, tmp_path):
    geoms, _ = engine.parse_svg_auto(fixture_svg("emblem.svg"), prefer_raster=False, **QUIET)
    meshes = engine.build_keychain_meshes(geoms, **QUIET)
    out = tmp_path / "emblem.3mf"
    engine.write_3mf(meshes, str(out), **QUIET)

    with zipfile.ZipFile(out) as z:
        assert {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"} <= set(z.namelist())
        model = ET.fromstring(z.read("3D/3dmodel.model"))
        settings = ET.fromstring(z.read("Metadata/model_settings.config"))
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    assert len(model.findall(".//m:resources/m:object", ns)) >= len(meshes)
    extruders = [md.get("value") for obj in settings.findall("object")
                 for md in obj.findall("metadata") if md.get("key") == "extruder"]
    assert sorted(extruders) == [str(i) for i in range(1, len(meshes) + 1)]


def test_3mf_round_trip_keeps_colours(fixture_svg, tmp_path):
    geoms, _ = engine.parse_svg_auto(fixture_svg("tricolour.svg"), prefer_raster=False, **QUIET)
    out = tmp_path / "t.3mf"
    engine.write_3mf(engine.build_keychain_meshes(geoms, **QUIET), str(out), **QUIET)
    again, _ = engine.parse_3mf(str(out), **QUIET)
    assert len(again) == 3


def test_reveal_never_uses_a_shell(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("subprocess.Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    nasty = tmp_path / 'a"; touch pwned; echo ".3mf'
    cmd = engine.reveal_in_file_manager(nasty)
    assert isinstance(calls[0][0], list) and calls[0][1].get("shell") is not True
    assert str(nasty) in cmd or str(nasty.parent) in cmd
    assert not (tmp_path / "pwned").exists()


@pytest.mark.parametrize("raster", READERS)
def test_svg_links_to_the_internet_are_never_fetched(fixture_svg, raster, monkeypatch):
    import socket
    import urllib.request
    attempts = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: attempts.append(a) or (_ for _ in ()).throw(OSError))
    monkeypatch.setattr(socket.socket, "connect", lambda self, addr: attempts.append(addr) or (_ for _ in ()).throw(OSError))
    geoms, _ = engine.parse_svg_auto(fixture_svg("external-refs.svg"), prefer_raster=raster, **QUIET)
    assert attempts == []
    assert sorted(geoms) == ["#ff0000"]
