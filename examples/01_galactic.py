"""Example 1 — RACS-low1 in galactic coordinates.

Loads the RACS-low1 catalogue via dipoletools, converts from equatorial
to galactic coordinates, and opens the interactive viewer.

The viewer auto-detects the coordinate system from the MapMaker object,
so display coordinates and all masking tools (discs, search, copy) will
operate in l, b throughout.

Flux cuts are enabled because a MapMaker is passed directly.
"""

from dipoletools import MapMaker
from dipoleview import view

# Load catalogue and convert to galactic coordinates
mm = MapMaker('racs-low1')
mm.coords('C', 'G')               # convert ICRS -> galactic

# Open viewer.  coord is auto-detected from mm.coords() -> 'G'
view(mm, title='RACS-low1  (galactic)')
