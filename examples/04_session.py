"""Example 4 — restore a saved mask session.

After saving a session in the viewer (sidebar → Save session), a
*_metadata.json file is written alongside a *_mask.npy file.
Pass the metadata path as `session=` to restore all slice masks,
disc masks, and individually masked pixels from a previous run.

The coordinate system is determined by the MapMaker as usual; the
session file stores pixel indices so it is coordinate-system agnostic.
"""

from dipoletools import MapMaker
from dipoleview import view

SESSION = 'racs-low1_YYYYMMDD_HHMMSS_metadata.json'   # <- edit path

mm = MapMaker('racs-low1')
mm.coords('C', 'G')

view(mm,
     title='RACS-low1  (restored session)',
     session=SESSION)
