"""Example 5 — load a numpy array mask alongside the map.

Pass any boolean HEALPix array via `mask=` to pre-mask pixels when the
viewer opens. Convention matches the viewer's saved masks:
``True`` = keep, ``False`` = masked.

If `session=` is also given, the array mask is merged with the session
(union of masked pixels) while the session's slice/disc-mask metadata
is preserved.
"""

import numpy as np
import healpy as hp

from dipoletools import MapMaker
from dipoleview import view

mm = MapMaker('racs-low1')
mm.coords('C', 'G')

npix = len(np.asarray(mm.map))
nside = hp.npix2nside(npix)

# Build a simple example mask in the map's native pixelisation frame:
# hide a band near the equator of the storage frame.
# Convention: True = keep, False = masked.
_, lat = hp.pix2ang(nside, np.arange(npix), lonlat=True)
array_mask = np.abs(lat) > 10.0

# Optionally save it to disk and pass the path instead:
# np.save('plane_mask.npy', array_mask)
# view(mm, mask='plane_mask.npy', ...)

view(mm,
     title='RACS-low1  (with array mask)',
     mask=array_mask)

# To merge an array mask with a previously saved session, pass both:
# view(mm,
#      session='racs-low1_YYYYMMDD_HHMMSS_metadata.json',
#      mask=array_mask)
