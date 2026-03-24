"""Example 3 — plain HEALPix count map (no MapMaker).

Demonstrates passing a bare numpy count map to the viewer instead of
a MapMaker object.  Use this when you have a pre-built map and do not
need live flux-cut controls.

The coordinate system must be declared explicitly via the `coord`
argument ('G' = galactic, 'C' = equatorial, 'E' = ecliptic).
Flux-cut controls are greyed out in this mode.
"""

import numpy as np
from dipoletools import MapMaker
from dipoleview import view

# -----------------------------------------------------------------
# Option A: extract the count map from a MapMaker and pass the array
# -----------------------------------------------------------------
mm = MapMaker('racs-low1')
mm.coords('C', 'G')
count_map = mm.map()               # numpy array, ring-ordered HEALPix

view(count_map,
     coord='G',                    # must be specified explicitly
     title='RACS-low1  (count map, galactic)',
     cmap='plasma')

# -----------------------------------------------------------------
# Option B: load a pre-saved .npy map
# -----------------------------------------------------------------
# count_map = np.load('my_map.npy')
# view(count_map, coord='G', title='My map')
