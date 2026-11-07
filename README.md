# svg-keychain-3mf

Turn a flat-colour SVG — a flag map, a logo, a simple badge — into a **multi-colour 3MF** you can open in
Bambu Studio and print with an AMS: every colour becomes its own part, already assigned to its own filament slot.

![Three synthetic examples: a stepped tricolour keychain, an emblem plaque and a map keychain](docs/demo.png)

## What it does

- Reads each fill colour in the SVG as a separate printable zone (strokes become zones too).
- Builds **keychains** (with a key-ring hole), **plaques** and **fridge magnets**. Magnets get hidden pockets for
  5 mm × 2 mm disc magnets: add a pause at Z = 2.46 mm in Bambu Studio, drop the magnets in, and resume.
- **Stepped relief** by default: each colour finishes at its own height so the design reads in 3D. `--flat` turns this off.
- **Double-sided keychains** (`--double-sided`) and an optional **backing plate** in a colour of your choice.
- Cleans up for printing: merges near-identical colours, removes specks and slivers too small for your nozzle
  (0.4 mm or 0.2 mm), and drops islands that are too far away to join the keychain as one piece.
- Writes a 3MF with one object per colour, extruders 1…N and the filament colours pre-filled.
- Can re-read a 3MF it produced to rebuild it as a different output (other Bambu Studio projects may work but are untested).
- Desktop app (Tkinter) and a command line. Works offline; no account, no telemetry.

## Install

Needs Python 3.10 or newer.

**One command** (with [pipx](https://pipx.pypa.io/)):

```bash
pipx install "svg-keychain-3mf[render] @ git+https://github.com/hassanitani6/svg-keychain-3mf"
svg-keychain doctor
```

**From a clone** (with [uv](https://docs.astral.sh/uv/)):

```bash
git clone https://github.com/hassanitani6/svg-keychain-3mf
cd svg-keychain-3mf
uv sync --extra render      # or: pip install ".[render]"
uv run svg-keychain doctor  # checks what is installed
```

The `render` extra adds a more faithful SVG reader (handles clipping, masks and overlapping shapes). It needs the
Cairo library on your system: `brew install cairo` on macOS, `sudo apt install libcairo2` on Debian/Ubuntu. Without it
the tool still works using its built-in path parser — `doctor` tells you which reader is active. On Windows,
expect the path parser unless you have installed Cairo yourself; the automated Windows tests use the path parser.

## Quick start

Desktop app:

```bash
uv run svg-keychain
```

Command line:

```bash
uv run svg-keychain generate examples/tricolour.svg --outputs keychain,plaque,magnet -o out/
# out/tricolour_keychain.3mf   3 colour parts
# out/tricolour_plaque.3mf     3 colour parts
# out/tricolour_magnet.3mf     3 colour parts
```

Open the 3MF in Bambu Studio. Check that each part is on the filament you want, slice, and print.

Useful options (`svg-keychain generate --help` for all):

| Option | Default | Meaning |
|---|---|---|
| `--size` | 60 (keychain, magnet), 100 (plaque) | Longest side in mm |
| `--thickness` | 5 | Total thickness in mm |
| `--hole` | 3 | Key-ring hole diameter in mm |
| `--nozzle` | 0.4 | 0.2 keeps finer detail |
| `--flat` | off | All colours the same height |
| `--double-sided` | off | Keychain reads on both faces |
| `--base-colour '#0f4c81'` | none | Adds a backing plate |
| `--path-parser` | off | Skip the Cairo reader |

## Examples

`examples/` holds three synthetic SVGs (public domain, CC0) used in the picture above and in the tests.

## Limitations

- **Flat colours only.** Gradients, embedded photos and filters are not converted. Text must be converted to paths
  first (Inkscape: *Path → Object to Path*).
- **Printer profile.** The project file is set up for a Bambu Lab A1 with a 0.4 mm nozzle and Bambu PLA Basic. On
  another printer, Bambu Studio may offer to switch profiles: accept, then check each part's filament slot.
- **Made for Bambu Studio.** The 3MF includes Bambu Studio project metadata (it identifies itself as a Bambu Studio
  project so colours and extruders load). Other slicers may open the geometry without the colour assignments; this
  has not been tested.
- **One-piece keychains.** Islands that cannot be joined to the main shape are dropped from keychains. Use a plaque
  with `--base-colour` if you need every island.
- Tested on macOS (Apple silicon) with Python 3.12. Linux and Windows run in CI but have not been tried by hand;
  the Cairo reader is the part most likely to need setup on Windows.
- Use designs you have the right to print. Many flag-map SVGs on Wikimedia Commons are public domain or
  CC-licensed — check each file's page.

## Troubleshooting

| Symptom | Try |
|---|---|
| `no coloured regions found` | The SVG has no fills. Convert strokes/text to paths and save as plain SVG. |
| `doctor` says *path parser only* | Install Cairo (see Install) or point `SVG_KEYCHAIN_LIBCAIRO` at `libcairo` directly. |
| Shapes overlap or colours look wrong | Remove `--path-parser`, or install the `render` extra. |
| `magnet skipped` | The design is too small or thin for magnet pockets; increase `--size`. |
| App window does not open on Linux | Install Tk: `sudo apt install python3-tk`. `svg-keychain generate` works without it. |
| The app closed unexpectedly | Details are saved to `svg-keychain-3mf_error.log` in your home folder (check it before attaching it to an issue). |

## Costs and privacy

The tool is free and runs entirely on your computer. It does not upload your designs, check for updates or collect
usage data, and it does not fetch images or files that an SVG links to (there is a test for this).

GitHub issues are public. The issue form asks for `svg-keychain doctor` output, which leaves out your user name and
home folder — check it before pasting. The maintainer may use an AI assistant (Anthropic's Claude) on their own
computer to help read a report; that only happens when they choose to run it, and email addresses, phone numbers,
home-folder paths and tokens are removed from the text first. Nothing runs automatically when you file an issue.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security problems: see [SECURITY.md](SECURITY.md).

## Licence

MIT — see [LICENSE](LICENSE). Bambu Lab and Bambu Studio are trademarks of their owner; this project is not
affiliated with or endorsed by them.
