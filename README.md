# dipoleview

**dipoleview** is an interactive HEALPix sky viewer and mask editor that opens a self-contained browser interface for inspecting source-count maps and building pixel masks.  It integrates directly with [dipoletools](https://github.com/strykowski-lab/dipoletools) for live flux-cut controls, or accepts any ring-ordered HEALPix array as a plain numpy array.

---

## Installation

```bash
git clone https://github.com/strykowski-lab/dipoleview.git
cd dipoleview
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

To run the examples you will also need dipoletools:

```bash
git clone https://github.com/strykowski-lab/dipoletools.git
pip install -e /path/to/dipoletools
```

---

## Quick start

```python
import numpy as np
from dipoleview import view

count_map = np.load('my_map.npy')
view(count_map, coord='G', title='My map')

# Rotate from equatorial to galactic on the way in (matches healpy's
# mollview(coord=[...]) convention). NaN / hp.UNSEEN pixels are
# treated as initially masked.
view(count_map, coord=['C', 'G'])
```

Or with a dipoletools `MapMaker` (enables live flux-cut controls):

```python
from dipoletools import MapMaker
from dipoleview import view

mm = MapMaker('racs-low1')
mm.coords('C', 'G')       # convert to galactic
view(mm)                  # coord auto-detected from MapMaker
```

---

## API

```python
view(source, coord='G', cmap='plasma', title='',
     session=None, save_dir=None, outfile=None, browser=True)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `source` | `MapMaker` or `array_like` | A dipoletools `MapMaker` object, or any ring-ordered HEALPix array. Passing a `MapMaker` enables live flux cuts and auto-detects the coordinate system. |
| `coord` | `str` or `list` | Coordinate system: `'G'` (galactic), `'C'` (equatorial), `'E'` (ecliptic). For a plain count map, a two-element list like `['C', 'G']` rotates the map from the input frame to the display frame (matching healpy's `mollview(coord=[...])` convention). Ignored when a `MapMaker` is passed (coordinate is read from `MapMaker.coords()`). Default `'G'`. |
| `cmap` | `str` | Matplotlib colormap name. Default `'plasma'`. |
| `title` | `str` | Label shown in the top-left of the map. |
| `session` | `str` | Path to a `*_metadata.json` file saved by a previous session, to restore all masks on open. |
| `save_dir` | `str` | Directory where session files are saved. Defaults to the current working directory. |
| `outfile` | `str` | Path for the generated HTML file. Defaults to a temp file. |
| `browser` | `bool` | Open in the system browser automatically. Default `True`. |

The function starts a local HTTP server and blocks until interrupted (`Ctrl+C`).

---

## Viewer controls

### Map navigation

| Action | Effect |
|--------|--------|
| Scroll | Zoom in / out centred on the cursor |
| Drag | Pan the map |
| `+` / `−` buttons | Zoom in / out by a fixed step |
| `⊙` button | Reset zoom to full-sky view |
| Zoom % box | Type a percentage and press Enter to jump to that zoom level |

### Pixel interaction

| Action | Effect |
|--------|--------|
| Hover pixel | Shows native coordinates and pixel value top-right |
| Click pixel | Select it (red border); value shown below coordinates |
| Click selected pixel | Mask it (dark fill); removed from source count |
| Click masked pixel | Unmask it |
| Arrow keys | Move selection to adjacent pixel (when a pixel is selected) |
| Enter | Toggle mask on the selected pixel |
| **Copy** button | Copies the selected pixel's coordinates as `"lon lat"` to the clipboard |

### Go to (coordinate search)

Type coordinates in the native system (`l b` for galactic, `ra dec` for equatorial) and press **Go** or Enter to jump directly to the containing pixel.

### Source count

The total source count (sum of `MAP_VALUES` over all unmasked pixels) is displayed above the colourbar and updates in real time as pixels are masked, slices are applied, or flux cuts are changed.

### Flux cut *(requires MapMaker)*

Enter minimum and/or maximum flux values and press **Apply cut** to re-bin the catalogue with those thresholds.  The map and source count update immediately.

### Smooth

| Control | Effect |
|---------|--------|
| **SMOOTH: OFF/ON** | Toggle the mask-aware smoothed view |
| `sr` input | Smoothing scale in steradians |
| **Refresh smooth** | Recompute the smooth with the current mask and scale |

The smooth is a running average over all unmasked pixels within the specified solid angle (exact match of `smooth_map` in `smooth.py`).  Pixel values shown on hover/selection reflect the smoothed values when the smooth is active.

### Slice masks

Type an inequality expression and press **Apply** (or Enter).  Any variable understood by the expression parser can be used:

| Variable | Meaning |
|----------|---------|
| `l`, `b` | Galactic longitude / latitude |
| `ra`, `dec` | Right ascension / declination |
| `lon`, `lat` | Native display coordinates |

Examples: `|b| < 10`, `60 < ra < 80`, `dec < -40`, `l > 300`

Each applied slice appears as a removable row.

### Disc masks

Enter a centre in native coordinates (`lon lat`, space-separated) and a radius in degrees, then press **Apply disc** or Enter.  All pixels within the disc are masked.  Each disc appears as a removable row (e.g. `l=120.0 b=-15.0 r=5.0°`).

### Masked pixels

A scrollable table of individually click-masked pixels with coordinates.  Each entry has a remove button to unmask it.

### Undo / Redo

`Cmd+Z` / `Ctrl+Z` and `Cmd+Shift+Z` / `Ctrl+Shift+Z` step through the full mask history (slice masks, disc masks, individual pixel masks).

### Save / Load session

- **Save session** writes a `*_metadata.json` and `*_mask.npy` to `save_dir`.
- **Load session** restores all slice masks, disc masks, and individually masked pixels from a previously saved `*_metadata.json`.

To publish a mask rather than reload it, convert the `*_metadata.json` to a readable
YAML recipe — see [Portable masks](#portable-masks) below.

---

## Portable masks

A saved session's `*_metadata.json` lists every masked pixel index, which makes it
unreadable and ties the mask to one nside.  `json_to_yaml` boils it down to the
recipe — the cuts, the discs, and any pixels masked by hand — as a YAML file that
anyone can read, edit, cite, or rebuild at their own resolution.

```python
from dipoleview import json_to_yaml, yaml_to_mask

json_to_yaml('racs-low3_20260420_184651_metadata.json', 'racs-low3.yaml')

mask = yaml_to_mask('racs-low3.yaml')          # bool array: True = keep
mask = yaml_to_mask('racs-low3.yaml', nside=256, coordinates='equatorial')
```

The YAML is the whole mask:

```yaml
coordinates: ANY
nside: ANY
ordering: ANY

cuts:
  - "|b|<5"
  - "dec>48.9"

discs:
  - "l=309.5, b=19.4, r=4.1"
  - "l=76.1, b=5.7, r=5.1"

pixels: []
```

| Field | Meaning |
|-------|---------|
| `coordinates` | Frame the map is pixelised in: `galactic`, `equatorial` (`celestial`), `ecliptic`, or `ANY`. |
| `nside` | HEALPix nside, or `ANY`. |
| `ordering` | `RING` or `NESTED`, or `ANY`. |
| `cuts` | Inequalities in `l`, `b`, `ra`, `dec`, `elon`, `elat` (or `lon`/`lat` for the pixelisation frame). Pixels **satisfying** a cut are masked out, so `\|b\|<5` removes the galactic plane. |
| `discs` | `l=309.5, b=19.4, r=4.1` — centre and radius in degrees. Every pixel centre inside is masked out. |
| `pixels` | Extra pixel indices masked by hand, i.e. ones no cut or disc accounts for. |

Cuts and discs are written in whatever frame they were drawn in, and name that frame
themselves, so `yaml_to_mask` converts them to the pixelisation frame for you — `|b|<5`
removes the galactic plane whether you rebuild the mask in galactic, equatorial or
ecliptic coordinates.

That is why `coordinates`, `nside` and `ordering` are normally `ANY`: a mask made only
of cuts and discs is a region of sky, not a set of pixels, so you can rebuild it however
suits your analysis (defaults: `equatorial`, `nside=64`, `RING`).  The exception is
`pixels`, whose raw indices only mean something for one particular pixelisation.  As
soon as that list is non-empty the three fields are pinned to the values the mask was
built at, and passing a conflicting argument raises `ValueError` rather than quietly
returning the wrong sky.

### Sending a mask to someone else

`yaml_to_mask` lives in a single self-contained file with no dipoleview imports.  Send a
collaborator the `.yaml` plus a copy of `dipoleview/yaml_to_mask.py`, and they can
rebuild the mask with only `numpy`, `healpy`, `astropy` and `pyyaml` installed:

```python
from yaml_to_mask import yaml_to_mask
mask = yaml_to_mask('racs-low3.yaml')
```

or straight from the command line:

```bash
python yaml_to_mask.py racs-low3.yaml -o racs-low3_mask.npy
```

### API

```python
json_to_yaml(json_path, yaml_path)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `json_path` | `str` | A `*_metadata.json` saved by the viewer. |
| `yaml_path` | `str` | Where to write the `.yaml`. |

Everything else — including which frame the map was pixelised in — is worked out from
the session.  Cuts and discs are recomputed as it converts, so any pixel the recipe
misses is written into `pixels` and the YAML reproduces the original mask.

```python
yaml_to_mask(path, coordinates=None, nside=None, ordering=None)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | `str` | The `.yaml` mask description. |
| `coordinates` | `str` | `'galactic'`, `'equatorial'` (`'celestial'`), `'ecliptic'`. Only when the file says `ANY`. Default `'equatorial'`. |
| `nside` | `int` | HEALPix nside. Only when the file says `ANY`. Default `64`. |
| `ordering` | `str` | `'RING'` or `'NESTED'`. Only when the file says `ANY`. Default `'RING'`. |

Returns a boolean array of length `12 * nside²`, `True` = keep and `False` = masked out,
matching the convention of the viewer's `*_mask.npy` files.

> **Note.** Sessions saved before August 2026 were built by a viewer that evaluated cuts
> and discs against pixel coordinates rounded to two decimal places, so a pixel sitting
> within ~0.005° (18 arcsec) of a cut or disc edge could be left on the wrong side of it.
> The viewer now writes those coordinates at full precision, and rebuilt masks reproduce
> a current session's `*_mask.npy` byte for byte.  Converting an older session, the
> recipe may claim a handful of edge pixels the session missed — `json_to_yaml` prints a
> note whenever that happens, and regenerating the session's `*_mask.npy` from the YAML
> resolves it.

---

## Examples

| Script | Description |
|--------|-------------|
| `examples/01_galactic.py` | RACS-low1 via MapMaker, galactic coordinates (C → G) |
| `examples/02_equatorial.py` | RACS-low1 via MapMaker, native equatorial coordinates |
| `examples/03_countmap.py` | Plain numpy count map, no flux-cut controls |
| `examples/04_session.py` | Restore a previously saved mask session |
| `examples/05_array_mask.py` | Load a numpy boolean mask alongside the map |
| `examples/06_yaml_mask.py` | Publish a mask as YAML and rebuild it at any nside/frame |

---

## Citation

If you use `dipoleview` in your research, please include a footnote to the repository:

> [https://github.com/strykowski-lab/dipoleview](https://github.com/strykowski-lab/dipoleview)

BibTeX:

```bibtex
@software{dipoleview,
  author       = {Land-Strykowski, Mali},
  title        = {dipoleview: Interactive HEALPix sky viewer and mask editor},
  url          = {https://github.com/strykowski-lab/dipoleview},
  version      = {0.1.0},
  year         = {2026},
}
```

---

## License

MIT
