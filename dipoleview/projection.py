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


def pixel_boundaries(nside, npix, step=2, rot=None):
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
    rot : healpy.Rotator, optional
        If given, rotate each boundary vertex from the input coord system
        into the output system before Mollweide projection. Pixel values
        are not touched, so integer counts are preserved.

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
    if rot is not None:
        vec = np.stack([cx.ravel(), cy.ravel(), cz.ravel()], axis=0)
        vec = rot(vec)
        cx = vec[0].reshape(npix, n_verts)
        cy = vec[1].reshape(npix, n_verts)
        cz = vec[2].reshape(npix, n_verts)
    phi_corn = np.degrees(np.arctan2(cy, cx)) % 360.0
    lat_corn = np.degrees(np.arcsin(np.clip(cz, -1.0, 1.0)))

    # Project all corners. hp.boundaries returns vertices in order around
    # the pixel boundary, so no re-sorting is needed — sorting by angle
    # from centroid causes self-intersecting polygons near the poles.
    mx, my = mollweide(phi_corn, lat_corn)  # (npix, n_verts)

    # Detect wrapping pixels by checking the projected x-span.
    # Pixels that straddle the 0/360 OR the 180° seam will have corners
    # projected to opposite sides of the map, giving a huge x-span.
    # A normal pixel's x-span is at most a few times the typical pixel size.
    typical_size = 4.0 * np.sqrt(2.0) / np.sqrt(npix)  # rough pixel width
    x_span = mx.max(axis=1) - mx.min(axis=1)
    wrap = x_span > typical_size * 5.0

    return mx, my, wrap


def pixel_centres(nside, npix, rot=None):
    """Return (lon, lat) in degrees for all pixel centres.

    If ``rot`` is given, the centres are rotated from the input coord
    system to the output one without touching the underlying pixel values.
    """
    theta_c, phi_c = hp.pix2ang(nside, np.arange(npix))
    if rot is not None:
        theta_c, phi_c = rot(theta_c, phi_c)
    lon_c = np.degrees(phi_c) % 360.0
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
