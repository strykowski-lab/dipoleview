"""Example: Interactive HEALPix viewer with dipoleview.

This example uses racs-dipole's MapMaker to build a count map,
then opens the interactive viewer for masking and inspection.

The viewer opens in your default browser at a local URL.
The Python process must stay alive while you use the viewer.
"""

import sys
sys.path.insert(0, '/Users/mali/repos/racs-dipole')

import numpy as np
from dipole import MapMaker
from dipoleview import view

# -------------------------------------------------------------------------
# 1. Build a count map using racs-dipole
# -------------------------------------------------------------------------
mm = MapMaker('racs-low1')
mm.coords('C', 'G')
mm.cut(label='flux', min=1500)
count_map = mm.map()

# -------------------------------------------------------------------------
# 2. Open the viewer — only the count map is required
# -------------------------------------------------------------------------
# Minimal usage:
path = view(count_map)

# -------------------------------------------------------------------------
# 3. Optional arguments
# -------------------------------------------------------------------------
# path = view(count_map, cmap='viridis')           # different colourmap
# path = view(count_map, title='RACS-Low1')        # title overlay
# path = view(count_map, coord='G')                # coordinate labels (default 'G')
# path = view(count_map, session='session.json')   # restore a saved mask session
# path = view(count_map, browser=False)             # don't auto-open browser

# -------------------------------------------------------------------------
# Usage notes
# -------------------------------------------------------------------------
# In the browser:
#   - Scroll to zoom, drag to pan.
#   - Hover a pixel -> coordinates shown top-right.
#   - Click a pixel -> select it (red border).
#   - Click the selected pixel again -> mask it (dark fill).
#   - Click a masked pixel -> unmask it.
#   - Slice masks: type an expression (e.g. "|b| < 10") and press Apply.
#   - Undo: Cmd+Z / Ctrl+Z. Redo: Cmd+Shift+Z / Ctrl+Shift+Z.
#   - "SMOOTH" toggle: shows mask-aware running average.
#   - "Refresh smooth": recomputes the smooth with current mask.
#   - "Save session": downloads the mask state as JSON.
#   - "Load session": restores a previously saved session.
