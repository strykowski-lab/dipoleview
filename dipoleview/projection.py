"""Mollweide projection and HEALPix pixel geometry utilities."""

import numpy as np
import healpy as hp


def mollweide(l_deg, b_deg):
    """Mollweide projection, fully vectorised. l increases LEFT."""
    l = np.where(np.asarray(l_deg, float) > 180.0,
                 np.asarray(l_deg, float) - 360.0,
                 np.asarray(l_deg, float))
    b = np.asarray(b_deg, float)
    lam = np.deg2rad(l)
    phi = np.deg2rad(b)
    theta = phi.copy()
    for _ in range(50):
        denom = np.where(np.abs(np.cos(theta)) < 1e-10, 1e-10,
                         2.0 + 2.0 * np.cos(2.0 * theta))
        delta = -(2.0 * theta + np.sin(2.0 * theta) - np.pi * np.sin(phi)) / denom
        theta += delta
        if np.all(np.abs(delta) < 1e-10):
            break
    return (-(2.0 * np.sqrt(2.0) / np.pi) * lam * np.cos(theta),
            np.sqrt(2.0) * np.sin(theta))


def pixel_boundaries(nside, npix, step=2):
    """Compute Mollweide-projected pixel boundary polygons.

    Parameters
    ----------
    nside : int
        HEALPix nside parameter.
    npix : int
        Number of pixels.
    step : int
        Number of intermediate points per edge (higher = smoother curves).
        Default 2 gives 8 vertices per pixel which handles the curved
        HEALPix pixel edges much better than 4 corners.

    Returns
    -------
    mx, my : ndarray of shape (npix, 4*step)
        Mollweide x, y coordinates of boundary vertices.
    wrap : ndarray of shape (npix,)
        Boolean mask for pixels that wrap around lon=0/360.
    """
    n_verts = 4 * step
    raw = hp.boundaries(nside, np.arange(npix), step=step)  # (npix, 3, 4*step)
    cx, cy, cz = raw[:, 0, :], raw[:, 1, :], raw[:, 2, :]
    phi_corn = np.degrees(np.arctan2(cy, cx)) % 360.0
    lat_corn = np.degrees(np.arcsin(np.clip(cz, -1.0, 1.0)))

    # Detect wrapping: if any pair of adjacent corners spans > 180 degrees
    # in longitude, the pixel wraps around the 0/360 boundary
    phi_diff = np.abs(np.diff(phi_corn, axis=1, append=phi_corn[:, :1]))
    wrap = np.any(phi_diff > 180.0, axis=1)

    mx, my = mollweide(phi_corn, lat_corn)  # (npix, n_verts)

    # Sort corners by angle from centroid to avoid self-intersecting quads
    cent_x = mx.mean(axis=1, keepdims=True)
    cent_y = my.mean(axis=1, keepdims=True)
    order = np.argsort(np.arctan2(my - cent_y, mx - cent_x), axis=1)
    mx = np.take_along_axis(mx, order, axis=1)
    my = np.take_along_axis(my, order, axis=1)

    return mx, my, wrap


def pixel_centres(nside, npix):
    """Return (lon, lat) in degrees for all pixel centres."""
    theta_c, phi_c = hp.pix2ang(nside, np.arange(npix))
    lon_c = np.degrees(phi_c)
    lat_c = 90.0 - np.degrees(theta_c)
    return lon_c, lat_c


def graticule_lines():
    """Generate Mollweide-projected graticule polylines.

    Returns
    -------
    list of str
        SVG polyline elements.
    """
    grat = []
    b_samp = np.linspace(-89.5, 89.5, 360)
    for l0 in range(0, 360, 60):
        gx, gy = mollweide(np.full_like(b_samp, l0), b_samp)
        pts = ' '.join(f'{x:.4f},{-y:.4f}' for x, y in zip(gx, gy))
        grat.append(
            f'<polyline points="{pts}" fill="none" stroke="#1c1c28" '
            f'stroke-width="0.004" pointer-events="none"/>'
        )
    l_samp = np.linspace(0.5, 359.5, 720)
    for b0 in (-60, -30, 0, 30, 60):
        gx, gy = mollweide(l_samp, np.full_like(l_samp, b0))
        pts = ' '.join(f'{x:.4f},{-y:.4f}' for x, y in zip(gx, gy))
        grat.append(
            f'<polyline points="{pts}" fill="none" stroke="#1c1c28" '
            f'stroke-width="0.004" pointer-events="none"/>'
        )
    return grat
