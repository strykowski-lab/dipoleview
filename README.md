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
from dipoletools import MapMaker
from dipoleview import view

mm = MapMaker('racs-low1')
mm.coords('C', 'G')       # convert to galactic
view(mm)                  # coord auto-detected from MapMaker
```

Or with a plain count map:

```python
import numpy as np
from dipoleview import view

count_map = np.load('my_map.npy')
view(count_map, coord='G', title='My map')
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
| `coord` | `str` | Coordinate system: `'G'` (galactic), `'C'` (equatorial), `'E'` (ecliptic). Ignored when a `MapMaker` is passed (coordinate is read from `MapMaker.coords()`). Default `'G'`. |
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

---

## Examples

| Script | Description |
|--------|-------------|
| `examples/01_galactic.py` | RACS-low1 via MapMaker, galactic coordinates (C → G) |
| `examples/02_equatorial.py` | RACS-low1 via MapMaker, native equatorial coordinates |
| `examples/03_countmap.py` | Plain numpy count map, no flux-cut controls |
| `examples/04_session.py` | Restore a previously saved mask session |

---

## License

MIT
