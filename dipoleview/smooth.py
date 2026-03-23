"""Mask-aware smoothing via cKDTree running average."""

import numpy as np
import healpy as hp
from scipy.spatial import cKDTree


def smooth_map(count_map, mask=None, steradians=1.0):
    """Compute a smoothed count map using a running average.

    Excludes masked pixels from the average so the user can see
    what their mask does to the running average.

    Parameters
    ----------
    count_map : ndarray
        Full HEALPix map (ring ordering).
    mask : ndarray of bool, optional
        True = keep, False = masked. If None, all pixels used.
    steradians : float
        Smoothing radius in steradians. Default 1.

    Returns
    -------
    smooth : ndarray
        Full-sky array with smoothed values for unmasked pixels,
        NaN for masked pixels.
    """
    counts = np.asarray(count_map, dtype=float).copy()
    nside = hp.npix2nside(len(counts))
    npix = len(counts)
    pos = np.array(hp.pix2vec(nside, np.arange(npix))).T

    radius = np.arccos(1 - steradians / (2 * np.pi))
    chord = 2 * np.sin(radius / 2)

    if mask is not None:
        unmasked = np.where(mask)[0]
    else:
        unmasked = np.arange(npix)

    is_unmasked = np.zeros(npix, dtype=bool)
    is_unmasked[unmasked] = True

    tree = cKDTree(pos)
    neighbors_list = tree.query_ball_point(pos[unmasked], chord, workers=-1)

    result = np.full(npix, np.nan)
    for j, nbrs in enumerate(neighbors_list):
        nbrs_arr = np.asarray(nbrs, dtype=int)
        valid = nbrs_arr[is_unmasked[nbrs_arr]]
        if len(valid) > 0:
            result[unmasked[j]] = counts[valid].mean()

    return result
