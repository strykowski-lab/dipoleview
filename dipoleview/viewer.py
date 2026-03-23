"""Interactive HEALPix map viewer with mask editor.

Opens a self-contained HTML file in the browser.
  - Scroll / zoom buttons to zoom, drag to pan.
  - Hover -> black border + live coordinates top-right.
  - Click -> select pixel (red border). Click selected -> mask it.
  - Click masked pixel -> unmask.
  - Side panel: slice masks (MaskMaker syntax), pixel mask table.
  - Smooth toggle button (mask-aware running average, refreshed on demand).
  - Save/Load session buttons for persisting mask state.
  - Full undo/redo (Cmd/Ctrl+Z, Cmd/Ctrl+Shift+Z) + UI buttons.
"""

import base64
import json
import os
import tempfile
import webbrowser
from pathlib import Path

import numpy as np
import healpy as hp

_MASK_FILL = '#4a4060'
_TEMPLATES = Path(__file__).parent / 'templates'


def _load_template(name):
    return (_TEMPLATES / name).read_text()


def _encode_map_values(m):
    """Base64-encode raw map values as Float32 for client-side smoothing."""
    return base64.b64encode(np.asarray(m, dtype=np.float32).tobytes()).decode()


def view(healpix_map, coord='G', cmap='plasma', title='',
         session=None, outfile=None, browser=True):
    """Open an interactive HEALPix map viewer + mask editor in the browser.

    Parameters
    ----------
    healpix_map : array_like
        Full HEALPix count map (ring ordering).
    coord : str, optional
        Coordinate system: 'G' (galactic), 'C' (equatorial), 'E' (ecliptic).
        Default 'G'.
    cmap : str, optional
        Matplotlib colormap name. Default 'plasma'.
    title : str, optional
        Label shown top-left.
    session : str, optional
        Path to a previously saved session JSON file to restore on open.
    outfile : str, optional
        HTML output path. Defaults to a temp file.
    browser : bool, optional
        Open in the system browser. Default True.

    Returns
    -------
    str
        Path to the generated HTML file.
    """
    import matplotlib.cm as mcm
    import matplotlib.colors as mcolors
    from .projection import pixel_boundaries, pixel_centres, graticule_lines

    m = np.asarray(healpix_map, dtype=float)
    nside = hp.npix2nside(len(m))
    npix = len(m)

    coord_labels = {'G': ('l', 'b'), 'C': ('ra', 'dec'), 'E': ('lon', 'lat')}
    lon_name, lat_name = coord_labels.get(coord, ('lon', 'lat'))

    # ------------------------------------------------------------------
    # Colormap
    # ------------------------------------------------------------------
    valid = np.isfinite(m)
    vmin = float(np.nanmin(m[valid])) if valid.any() else 0.0
    vmax = float(np.nanmax(m[valid])) if valid.any() else 1.0
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap_fn = mcm.get_cmap(cmap)
    rgba = cmap_fn(norm(np.where(valid, m, vmin)))
    nan_color = '#2a2a2a'
    hex_colors = [
        '#{:02x}{:02x}{:02x}'.format(int(r * 255), int(g * 255), int(b_ * 255))
        if valid[i] else nan_color
        for i, (r, g, b_, _) in enumerate(rgba)
    ]

    # LUT: 256-entry colormap for JS smoothing
    lut_vals = cmap_fn(np.linspace(0, 1, 256))
    lut_json = json.dumps([[int(r * 255), int(g * 255), int(b_ * 255)]
                           for r, g, b_, _ in lut_vals])

    # ------------------------------------------------------------------
    # Pixel centres
    # ------------------------------------------------------------------
    lon_c, lat_c = pixel_centres(nside, npix)

    # ------------------------------------------------------------------
    # Pixel boundaries — step=2 for 8 vertices per pixel (fixes tessellation)
    # ------------------------------------------------------------------
    print(f'Computing pixel boundaries (nside={nside}, npix={npix})...')
    mx, my, wrap = pixel_boundaries(nside, npix, step=2)
    n_verts = mx.shape[1]

    # ------------------------------------------------------------------
    # SVG polygons
    # ------------------------------------------------------------------
    print('Building SVG...')
    polys = []
    for i in range(npix):
        if wrap[i]:
            continue
        pts = ' '.join(f'{mx[i, k]:.5f},{-my[i, k]:.5f}' for k in range(n_verts))
        color = hex_colors[i]
        polys.append(
            f'<polygon points="{pts}" fill="{color}" stroke="{color}" '
            f'data-idx="{i}" data-lon="{lon_c[i]:.2f}" data-lat="{lat_c[i]:.2f}"/>'
        )
    polygons_str = '\n    '.join(polys)

    # ------------------------------------------------------------------
    # Graticule
    # ------------------------------------------------------------------
    graticule_str = '\n    '.join(graticule_lines())

    # ------------------------------------------------------------------
    # SVG layout
    # ------------------------------------------------------------------
    W, H = 2.0 * np.sqrt(2.0), np.sqrt(2.0)
    pad = 0.10
    vb = f'{-W - pad:.4f} {-H - pad:.4f} {2 * (W + pad):.4f} {2 * (H + pad):.4f}'
    ellipse_str = (
        f'<ellipse cx="0" cy="0" rx="{W:.5f}" ry="{H:.5f}" '
        f'fill="none" stroke="#333" stroke-width="0.006" pointer-events="none"/>'
    )

    # ------------------------------------------------------------------
    # Pixel data for JS
    # ------------------------------------------------------------------
    pix_lon_js = '[' + ','.join(f'{v:.2f}' for v in lon_c) + ']'
    pix_lat_js = '[' + ','.join(f'{v:.2f}' for v in lat_c) + ']'
    pix_fill_js = '[' + ','.join(f'"{c}"' for c in hex_colors) + ']'
    map_values_b64 = _encode_map_values(m)

    # ------------------------------------------------------------------
    # Escape title
    # ------------------------------------------------------------------
    title_esc = (title.replace('&', '&amp;')
                      .replace('<', '&lt;')
                      .replace('>', '&gt;'))

    # ------------------------------------------------------------------
    # Load templates
    # ------------------------------------------------------------------
    css_str = _load_template('style.css')
    js_str = _load_template('viewer.js')
    html = _load_template('viewer.html')

    # ------------------------------------------------------------------
    # Handle session loading — inject restore code into JS
    # ------------------------------------------------------------------
    session_js = ''
    if session and os.path.isfile(session):
        with open(session) as f:
            session_data = f.read()
        session_js = f'''
// Auto-restore session
(function() {{
  try {{
    const session = {session_data};
    if (session.sliceMasks || session.pixelMasks) {{
      sliceMasks = (session.sliceMasks || []).map(sm => ({{
        expr: sm.expr, pixels: sm.pixels
      }}));
      pixelMasks = session.pixelMasks || {{}};
      updateAllPolygons();
      updateSliceList();
      updateMaskTable();
      saveStatus.textContent = 'Restored session';
    }}
  }} catch(e) {{ console.warn('Session restore failed:', e); }}
}})();
'''
    js_str = js_str + '\n' + session_js

    # ------------------------------------------------------------------
    # Assemble HTML
    # ------------------------------------------------------------------
    for key, val in [
        ('%%CSS%%', css_str),
        ('%%JS%%', js_str),
        ('%%TITLE%%', title_esc),
        ('%%VIEWBOX%%', vb),
        ('%%POLYGONS%%', polygons_str),
        ('%%GRATICULE%%', graticule_str),
        ('%%ELLIPSE%%', ellipse_str),
        ('%%LON_NAME%%', lon_name),
        ('%%LAT_NAME%%', lat_name),
        ('%%NPIX%%', str(npix)),
        ('%%NSIDE%%', str(nside)),
        ('%%PIX_LON%%', pix_lon_js),
        ('%%PIX_LAT%%', pix_lat_js),
        ('%%PIX_FILL%%', pix_fill_js),
        ('%%MAP_VALUES_B64%%', map_values_b64),
        ('%%LUT%%', lut_json),
        ('%%NAN_COLOR%%', nan_color),
        ('%%MASK_FILL%%', _MASK_FILL),
    ]:
        html = html.replace(key, val)

    if outfile is None:
        fd, outfile = tempfile.mkstemp(suffix='.html', prefix='healpix_viewer_')
        os.close(fd)
    with open(outfile, 'w') as fh:
        fh.write(html)

    print(f'Viewer saved -> {outfile}')
    if browser:
        webbrowser.open('file://' + os.path.abspath(outfile))
    return outfile
