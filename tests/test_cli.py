import getpass
import json
import subprocess
import sys
from pathlib import Path

from svg_keychain_3mf import doctor

FIXTURES = Path(__file__).parent / "fixtures"


def run(*args, env=None):
    # errors="replace": on Windows the tool's piped output is not UTF-8.
    return subprocess.run([sys.executable, "-m", "svg_keychain_3mf", *args], env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)


def test_generate_writes_requested_files(tmp_path):
    r = run("generate", str(FIXTURES / "tricolour.svg"), "-o", str(tmp_path),
            "--outputs", "keychain,plaque", "--path-parser", "-q")
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in tmp_path.glob("*.3mf")) == ["tricolour_keychain.3mf", "tricolour_plaque.3mf"]


def test_unpainted_svg_fails_with_advice(tmp_path):
    r = run("generate", str(FIXTURES / "no-fills.svg"), "-o", str(tmp_path), "-q")
    assert r.returncode == 1 and "no coloured regions" in r.stderr
    assert not list(tmp_path.glob("*.3mf"))


def test_broken_svg_fails_cleanly(tmp_path):
    r = run("generate", str(FIXTURES / "truncated.svg"), "-o", str(tmp_path), "-q")
    assert r.returncode == 1
    assert "could not read" in r.stderr and "Traceback" not in r.stderr


def test_rejects_unknown_output_type(tmp_path):
    r = run("generate", str(FIXTURES / "tricolour.svg"), "--outputs", "mug")
    assert r.returncode == 2


def test_doctor_report_has_no_home_path_or_user():
    r = run("doctor", "--json")
    assert r.returncode == 0
    report = json.loads(r.stdout)
    assert {"tool_version", "python", "os", "packages", "svg_reader"} <= set(report)
    assert str(Path.home()) not in r.stdout
    user = getpass.getuser()
    if len(user) >= 3:
        assert user not in r.stdout


def test_redact_scrubs_paths_emails_and_secrets():
    home = str(Path.home())
    text = f"{home}/designs/x.svg owner=someone@example.com API_KEY=abc123 token: xyz"
    out = doctor.redact(text)
    assert home not in out and "someone@example.com" not in out
    assert "abc123" not in out and "xyz" not in out
    assert out.startswith("~/designs/x.svg")


def test_invalid_numbers_and_colours_are_rejected(tmp_path):
    src = str(FIXTURES / "tricolour.svg")
    for bad in (["--size", "0"], ["--hole", "-1"], ["--base-colour", "blue"]):
        assert run("generate", src, "-o", str(tmp_path), *bad).returncode == 2, bad
    assert run("generate", src, "--double-sided", "--flat").returncode == 2


def test_generate_works_without_tk(tmp_path):
    code = ("import sys, builtins; real = builtins.__import__\n"
            "def no_tk(name, *a, **k):\n"
            "    if name.startswith('tkinter'): raise ImportError('No module named tkinter')\n"
            "    return real(name, *a, **k)\n"
            "builtins.__import__ = no_tk\n"
            "from svg_keychain_3mf.cli import main\n"
            f"sys.exit(main(['generate', {str(FIXTURES / 'tricolour.svg')!r}, '-o', {str(tmp_path)!r}, '-q', '--path-parser']))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stderr


def test_doctor_hides_unusual_home_paths(monkeypatch, tmp_path):
    fake_home = tmp_path / "Zoë Ångström"
    monkeypatch.setattr(doctor.Path, "home", lambda: fake_home)
    monkeypatch.setenv("SVG_KEYCHAIN_LIBCAIRO", str(fake_home / "lib" / "libcairo.2.dylib"))
    text = json.dumps(doctor.collect(), ensure_ascii=False) + doctor.redact(
        r"C:\Users\Roberto\AppData\x.dll /home/someone/lib /Users/Other/x ZOË ÅNGSTRÖM")
    for leak in ("Zoë", "Roberto", "someone", "Other", "ZOË"):
        assert leak not in text, leak


def test_non_latin_file_name_with_windows_style_output(tmp_path):
    import os
    import shutil
    src = tmp_path / "علم.svg"
    shutil.copy(FIXTURES / "tricolour.svg", src)
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    r = run("generate", str(src), "-o", str(tmp_path / "out"), "-q", "--path-parser", env=env)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "out" / "علم_keychain.3mf").exists()
