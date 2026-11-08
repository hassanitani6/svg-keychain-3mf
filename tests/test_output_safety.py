"""The tool must never silently replace a file: not the input, and not an earlier output."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from svg_keychain_3mf import engine

FIXTURES = Path(__file__).parent / "fixtures"
QUIET = dict(log=lambda _m: None)


def run(*args):
    return subprocess.run([sys.executable, "-m", "svg_keychain_3mf", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)


def make_3mf(folder: Path, name: str) -> Path:
    """A real 3MF made by the tool from the synthetic tricolour flag."""
    r = run("generate", str(FIXTURES / "tricolour.svg"), "-o", str(folder), "--path-parser", "-q")
    assert r.returncode == 0, r.stderr
    made = folder / "tricolour_keychain.3mf"
    return made if made.name == name else made.rename(folder / name)


def test_refuses_to_replace_its_own_3mf_input(tmp_path):
    src = make_3mf(tmp_path, "b_keychain.3mf")
    before = src.read_bytes()
    for extra in ([], ["--overwrite"]):
        r = run("generate", str(src), "--outputs", "keychain", "--path-parser", "-q", *extra)
        assert r.returncode == 2, r.stderr
        assert "replace the input" in r.stderr and "Traceback" not in r.stderr
        assert src.read_bytes() == before


def test_refuses_existing_output_without_overwrite(tmp_path):
    existing = tmp_path / "tricolour_keychain.3mf"
    existing.write_bytes(b"hand-edited in the slicer")
    r = run("generate", str(FIXTURES / "tricolour.svg"), "-o", str(tmp_path), "--path-parser", "-q")
    assert r.returncode == 2
    assert "already exists" in r.stderr and "--overwrite" in r.stderr
    assert existing.read_bytes() == b"hand-edited in the slicer"


def test_nothing_is_written_when_any_output_exists(tmp_path):
    (tmp_path / "tricolour_plaque.3mf").write_bytes(b"keep")
    r = run("generate", str(FIXTURES / "tricolour.svg"), "-o", str(tmp_path), "--outputs", "keychain,plaque",
            "--path-parser", "-q")
    assert r.returncode == 2
    assert not (tmp_path / "tricolour_keychain.3mf").exists()


def test_overwrite_replaces_an_earlier_output(tmp_path):
    existing = tmp_path / "tricolour_keychain.3mf"
    existing.write_bytes(b"old")
    r = run("generate", str(FIXTURES / "tricolour.svg"), "-o", str(tmp_path), "--path-parser", "-q", "--overwrite")
    assert r.returncode == 0, r.stderr
    assert zipfile.is_zipfile(existing)
    assert not list(tmp_path.glob("*.part"))


def test_hardlink_to_the_input_is_refused_even_with_overwrite(tmp_path):
    src = tmp_path / "in" / "flag.svg"
    src.parent.mkdir()
    shutil.copy(FIXTURES / "tricolour.svg", src)
    out = tmp_path / "out"
    out.mkdir()
    try:
        os.link(src, out / "flag_keychain.3mf")
    except OSError:
        pytest.skip("this file system has no hard links")
    r = run("generate", str(src), "-o", str(out), "--path-parser", "-q", "--overwrite")
    assert r.returncode == 2 and "replace the input" in r.stderr
    assert src.read_bytes() == (FIXTURES / "tricolour.svg").read_bytes()


def test_name_differing_only_in_case_is_the_input_on_case_insensitive_disks(tmp_path):
    src = make_3mf(tmp_path, "c_keychain.3MF")
    if not (tmp_path / "c_keychain.3mf").exists():
        pytest.skip("case-sensitive file system: the two names are different files")
    before = src.read_bytes()
    r = run("generate", str(src), "--path-parser", "-q", "--overwrite")
    assert r.returncode == 2 and "replace the input" in r.stderr
    assert src.read_bytes() == before


def test_a_crash_while_writing_keeps_the_old_file_and_leaves_no_part_file(tmp_path, fixture_svg, monkeypatch):
    geoms, _ = engine.parse_svg_auto(fixture_svg("tricolour.svg"), prefer_raster=False, **QUIET)
    meshes = engine.build_keychain_meshes(geoms, max_size_mm=60.0, **QUIET)
    dest = tmp_path / "flag_keychain.3mf"
    dest.write_bytes(b"previous good file")
    real = zipfile.ZipFile.writestr
    calls = {"n": 0}

    def failing(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk full")
        return real(self, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "writestr", failing)
    with pytest.raises(OSError):
        engine.write_3mf(meshes, str(dest), **QUIET)
    assert dest.read_bytes() == b"previous good file"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["flag_keychain.3mf"]


def test_out_dir_that_is_a_file_gives_a_clean_error(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    r = run("generate", str(FIXTURES / "tricolour.svg"), "-o", str(blocker), "--path-parser", "-q")
    assert r.returncode == 1
    assert "error:" in r.stderr and "Traceback" not in r.stderr


def test_oversized_3mf_member_is_rejected(tmp_path, monkeypatch):
    src = make_3mf(tmp_path, "big_keychain.3mf")
    monkeypatch.setattr(engine, "MAX_3MF_MEMBER_BYTES", 100)
    with pytest.raises(ValueError, match="too large"):
        engine.parse_3mf(str(src), **QUIET)


def test_oversized_svg_is_rejected(fixture_svg, monkeypatch):
    monkeypatch.setattr(engine, "MAX_SVG_BYTES", 100)
    with pytest.raises(ValueError, match="too large"):
        engine.parse_svg_auto(fixture_svg("tricolour.svg"), prefer_raster=False, **QUIET)


def test_deeply_nested_svg_fails_cleanly(tmp_path):
    deep = tmp_path / "deep.svg"
    deep.write_text('<svg xmlns="http://www.w3.org/2000/svg">' + "<g>" * 50000 + "</g>" * 50000 + "</svg>",
                    encoding="utf-8")
    r = run("generate", str(deep), "-o", str(tmp_path), "--path-parser", "-q")
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
