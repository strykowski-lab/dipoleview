# dipoleview

Interactive HEALPix sky viewer and mask editor. Opens a self-contained HTML viewer in your browser for inspecting count maps and building pixel masks.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```python
from dipoleview import view

# Only a HEALPix count map is required
view(count_map)

# Optional arguments
view(count_map, cmap='viridis', coord='G', title='My Map')
view(count_map, session='previous_session.json')  # restore saved mask
```

### Viewer controls

- **Scroll** to zoom, **drag** to pan
- **Hover** a pixel to see coordinates (top-right)
- **Click** a pixel to select it (red border), click again to mask it
- **Click** a masked pixel to unmask it
- **Slice masks**: type an expression (e.g. `|b| < 10`, `60 < l < 120`, `dec < -40`) and press Apply
- **Undo/Redo**: Cmd+Z / Ctrl+Z and Cmd+Shift+Z / Ctrl+Shift+Z
- **SMOOTH toggle**: shows a mask-aware running average of the map
- **Refresh smooth**: recomputes the smooth using the current mask
- **Save session**: downloads the mask state as JSON
- **Load session**: restores a previously saved session from a JSON file

## Dependencies

- numpy
- healpy
- matplotlib
- scipy

## Examples

See `examples/01_viewer.py` for a complete example using [racs-dipole](https://github.com/your-org/racs-dipole) to build a count map.
