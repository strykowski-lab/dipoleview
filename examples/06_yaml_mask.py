"""Example 6 — publish a mask as YAML, and rebuild it anywhere.

A saved session's *_metadata.json records every masked pixel index, which
makes it unreadable and welds the mask to one nside. `json_to_yaml` boils
it down to the recipe — the cuts, the discs, and any pixels masked by hand
— in a file anyone can read, edit and cite.

To hand the mask to someone else, send them two files: the .yaml, and a
copy of dipoleview/yaml_to_mask.py. That script is self-contained, so they
can rebuild the mask without installing dipoleview:

    from yaml_to_mask import yaml_to_mask
    mask = yaml_to_mask('racs-low3.yaml')
"""

import healpy as hp
import numpy as np

from dipoleview import json_to_yaml, yaml_to_mask

SESSION = 'racs-low3_YYYYMMDD_HHMMSS_metadata.json'   # <- edit path
MASK_YAML = 'racs-low3.yaml'


# 1. Session JSON -> YAML. No other arguments: everything the YAML needs
#    is worked out from the session, including which frame the map was
#    pixelised in.
json_to_yaml(SESSION, MASK_YAML)


# 2. YAML -> boolean array. True = keep, False = masked out.
mask = yaml_to_mask(MASK_YAML)
print(f'{mask.sum()} of {mask.size} pixels kept')


# 3. A mask built only from cuts and discs is not tied to a pixelisation,
#    so the YAML leaves coordinates/nside/ordering as ANY and you can
#    rebuild it however you like. Cuts and discs name their own frame
#    (`|b|<5` is galactic wherever the map is binned), so they are
#    converted for you.
#
#    Masks that also list hand-masked pixels are the exception: raw pixel
#    indices only mean something for one pixelisation, so the YAML pins
#    all three fields down and refuses to be rebuilt any other way.
try:
    fine = yaml_to_mask(MASK_YAML, nside=256, coordinates='equatorial')
    area = (~fine).sum() * hp.nside2pixarea(256, degrees=True)
    print(f'nside=256, equatorial: {area:.0f} sq.deg masked')

    nested = yaml_to_mask(MASK_YAML, ordering='NESTED')
    print('NESTED covers the same sky as RING: '
          f'{np.array_equal(hp.reorder(nested, n2r=True), mask)}')
except ValueError as error:
    print(f'fixed by the file: {error}')


# 5. The result is an ordinary boolean HEALPix mask — save it, or open it
#    back up in the viewer.
np.save('racs-low3_mask.npy', mask)

# from dipoleview import view
# view(count_map, mask=mask, title='RACS-low3')
