"""Mask-aware smoothing via cKDTree running average."""

import numpy as np
import healpy as hp
from scipy.spatial import cKDTree


def smooth_map(count_map, mask=None, steradians=1):
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
    numpy.ndarray
        Full-sky array with smoothed values for unmasked pixels,
        NaN for masked pixels.
    """

    counts = count_map
    nside = hp.npix2nside(len(counts))
    npix = len(counts)
    pos = np.array(hp.pix2vec(nside, np.arange(npix))).T

    radius = np.arccos(1 - steradians / (2 * np.pi))
    chord = 2 * np.sin(radius / 2)

    if mask is not None:
        unmasked_indices = np.where(mask)[0]
    else:
        unmasked_indices = np.arange(npix)

    is_unmasked = np.zeros(npix, dtype=bool)
    is_unmasked[unmasked_indices] = True

    tree = cKDTree(pos)
    neighbors_list = tree.query_ball_point(pos[unmasked_indices], chord,
                                            workers=-1)

    average_counts = np.zeros(len(unmasked_indices))
    for j, nbrs in enumerate(neighbors_list):
        nbrs_arr = np.asarray(nbrs, dtype=int)
        valid = nbrs_arr[is_unmasked[nbrs_arr]]
        if len(valid) > 0:
            average_counts[j] = counts[valid].mean()

    return average_counts