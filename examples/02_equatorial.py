"""Example 2 — RACS-low1 in equatorial coordinates.

Loads the RACS-low1 catalogue via dipoletools and opens the viewer
in native equatorial (ICRS) coordinates — no conversion applied.

The viewer auto-detects the coordinate system from the MapMaker object,
so display coordinates and all masking tools (discs, search, copy) will
operate in ra, dec throughout.

Flux cuts are enabled because a MapMaker is passed directly.
"""

from dipoletools import MapMaker
from dipoleview import view

# Load catalogue — stays in native equatorial coords
mm = MapMaker('racs-low1')        # coords() returns 'C' by default

# Open viewer.  coord is auto-detected from mm.coords() -> 'C'
view(mm, title='RACS-low1  (equatorial)')
