"""Interactive HEALPix map viewer with mask editor.

Opens a self-contained HTML file in the browser.
A lightweight background server handles save/load to the working directory.
"""

import base64
import json
import os
import tempfile
import threading
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import numpy as np
import healpy as hp

_MASK_FILL = '#4a4060'
_TEMPLATES = Path(__file__).parent / 'templates'
_server_state = {}


def _load_template(name):
    return (_TEMPLATES / name).read_text()


def _encode_map_values(m):
    return base64.b64encode(np.asarray(m, dtype=np.float32).tobytes()).decode()


def _recolor(m, cmap_name, nan_color='#2a2a2a'):
    """Recompute hex colors and vmin/vmax for a map array."""
    import matplotlib.cm as mcm
    import matplotlib.colors as mcolors

    m = np.asarray(m, dtype=float)
    valid = np.isfinite(m)
    vmin = float(np.nanmin(m[valid])) if valid.any() else 0.0
    vmax = float(np.nanmax(m[valid])) if valid.any() else 1.0
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap_fn = mcm.get_cmap(cmap_name)
    rgba = cmap_fn(norm(np.where(valid, m, vmin)))
    hex_colors = [
        '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b_*255))
        if valid[i] else nan_color
        for i, (r, g, b_, _) in enumerate(rgba)
    ]
    return hex_colors, vmin, vmax


def _get_label(source, mapmaker):
    """Determine save-file label from the source."""
    if mapmaker is None:
        return 'countmap'

    # Shorthand name (e.g. 'racs-low1', 'nvss')
    if getattr(mapmaker, '_shorthand_name', None):
        return mapmaker._shorthand_name

    # User-given custom catalogue name (not the default 'original')
    if hasattr(mapmaker, '_catalogue_order') and mapmaker._catalogue_order:
        cat_name = mapmaker._catalogue_order[0]
        if cat_name != 'original':
            return cat_name

    return 'countmap'


class _ViewerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            html = _server_state.get('html', '')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)

        if self.path == '/save':
            try:
                data = json.loads(body)
                save_dir = _server_state.get('save_dir', '.')
                label = _server_state.get('label', 'countmap')
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')

                meta_path = os.path.join(save_dir, f'{label}_{ts}_metadata.json')
                with open(meta_path, 'w') as f:
                    json.dump(data['session'], f, indent=2)

                npix = _server_state.get('npix', 0)
                mask_arr = np.ones(npix, dtype=bool)
                for idx in data.get('masked_pixels', []):
                    if 0 <= idx < npix:
                        mask_arr[idx] = False
                mask_path = os.path.join(save_dir, f'{label}_{ts}_mask.npy')
                np.save(mask_path, mask_arr)

                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                result = {'metadata': os.path.basename(meta_path),
                          'mask': os.path.basename(mask_path)}
                self.wfile.write(json.dumps(result).encode())
                print(f'  Saved: {meta_path}')
                print(f'  Saved: {mask_path}')
            except Exception as e:
                self.send_response(500)
                self._cors()
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif self.path == '/list-sessions':
            try:
                save_dir = _server_state.get('save_dir', '.')
                files = sorted([
                    f for f in os.listdir(save_dir)
                    if f.endswith('_metadata.json')
                ], reverse=True)
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(files).encode())
            except Exception as e:
                self.send_response(500)
                self._cors()
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif self.path == '/load':
            try:
                data = json.loads(body)
                filename = data.get('path', '')
                save_dir = _server_state.get('save_dir', '.')
                filepath = os.path.join(save_dir, filename)
                if not os.path.isfile(filepath):
                    self.send_response(404)
                    self._cors()
                    self.end_headers()
                    self.wfile.write(b'File not found')
                    return
                with open(filepath) as f:
                    session = json.load(f)
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(session).encode())
            except Exception as e:
                self.send_response(500)
                self._cors()
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif self.path == '/smooth':
            try:
                from .smooth import smooth_map
                data = json.loads(body)
                steradians = float(data.get('steradians', 1.0))
                masked_pixels = set(data.get('masked_pixels', []))

                npix = _server_state.get('npix', 0)
                count_map = _server_state.get('count_map')
                if count_map is None:
                    self.send_response(400)
                    self._cors()
                    self.end_headers()
                    self.wfile.write(b'No map data available')
                    return

                mask = np.ones(npix, dtype=bool)
                for idx in masked_pixels:
                    if 0 <= idx < npix:
                        mask[idx] = False

                unmasked_indices = np.where(mask)[0]
                average_counts = smooth_map(count_map, mask=mask,
                                            steradians=steradians)

                # Build full-sky result: NaN for masked pixels.
                values = np.full(npix, float('nan'))
                values[unmasked_indices] = average_counts

                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                # JSON doesn't support NaN — use null, JS will get null
                result = {'values': [None if not np.isfinite(v) else float(v)
                                     for v in values]}
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self._cors()
                self.end_headers()
                self.wfile.write(str(e).encode())

        elif self.path == '/flux-cut':
            try:
                mm = _server_state.get('mapmaker')
                if mm is None:
                    self.send_response(400)
                    self._cors()
                    self.end_headers()
                    self.wfile.write(b'No MapMaker available')
                    return

                data = json.loads(body)
                fmin = data.get('min')  # None if not provided
                fmax = data.get('max')
                print(f'  Flux cut: min={fmin}, max={fmax}')

                # Restore to full catalogue, then apply the new cut
                mm.restore()
                cat_name = mm._catalogue_order[0]
                n_before = len(mm._catalogues[cat_name])
                print(f'  After restore: {n_before} sources')

                mm.cut('flux', min=fmin, max=fmax)
                n_after = len(mm._catalogues[cat_name])
                print(f'  After cut: {n_after} sources')

                new_map = np.asarray(mm.map, dtype=float)
                print(f'  New map range: {np.nanmin(new_map):.2f} - {np.nanmax(new_map):.2f}, total counts: {np.nansum(new_map):.0f}')

                cmap_name = _server_state.get('cmap', 'plasma')
                hex_colors, vmin, vmax = _recolor(new_map, cmap_name)
                values_b64 = _encode_map_values(new_map)

                result = {
                    'colors': hex_colors,
                    'values_b64': values_b64,
                    'vmin': vmin,
                    'vmax': vmax,
                }
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self._cors()
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()


def _start_server(html, save_dir, npix, label='countmap',
                  mapmaker=None, cmap='plasma', count_map=None):
    _server_state['html'] = html
    _server_state['save_dir'] = save_dir
    _server_state['npix'] = npix
    _server_state['label'] = label
    _server_state['mapmaker'] = mapmaker
    _server_state['cmap'] = cmap
    _server_state['count_map'] = count_map
    server = HTTPServer(('127.0.0.1', 0), _ViewerHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return port


def view(source, coord='G', cmap='plasma', title='',
         session=None, decimals=0,
         save_dir=None, outfile=None, browser=True):
    """Open an interactive HEALPix map viewer + mask editor in the browser.

    Parameters
    ----------
    source : array_like or MapMaker
        A HEALPix count map (ring ordering), or a MapMaker instance.
        If a MapMaker is passed, flux cuts are enabled in the UI.
        For a plain count map, NaN and ``hp.UNSEEN`` pixels are treated
        as initially masked.
    coord : str or list of str, optional
        Coordinate system: 'G' (galactic), 'C' (equatorial), 'E' (ecliptic).
        For a plain count map, a two-element list like ``['C', 'G']``
        rotates the map from the first frame to the second (matching
        healpy's ``mollview(coord=[...])`` convention).
    cmap : str, optional
        Matplotlib colormap name. Default 'plasma'.
    title : str, optional
        Label shown top-left.
    session : str, optional
        Path to a saved _metadata.json to restore on open.
    decimals : int, optional
        Number of decimal places shown in the ``val: X`` hover/select
        readout. Default 0 (integer display).
    save_dir : str, optional
        Directory for saved files. Defaults to cwd.
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

    # Detect MapMaker vs plain array
    mapmaker = None
    if hasattr(source, 'cut') and hasattr(source, 'restore') and hasattr(source, 'map'):
        mapmaker = source
        healpix_map = np.asarray(source.map, dtype=float)
        # Pull coord from MapMaker if available, overriding the caller's default.
        if callable(getattr(mapmaker, 'coords', None)):
            try:
                coord = mapmaker.coords()
            except Exception:
                pass
    else:
        healpix_map = np.asarray(source, dtype=float)

    m = healpix_map
    nside = hp.npix2nside(len(m))
    npix = len(m)

    # For plain count maps: support coord=[in, out] rotation, and treat
    # NaN / UNSEEN pixels as initially masked.
    initial_masked = []
    if mapmaker is None:
        if isinstance(coord, (list, tuple)):
            if len(coord) != 2:
                raise ValueError("coord list must have exactly two elements, e.g. ['C', 'G']")
            coord_in, coord_out = coord
            if coord_in != coord_out:
                rot = hp.Rotator(coord=[coord_in, coord_out])
                m = rot.rotate_map_pixel(m)
            coord = coord_out

        bad = ~np.isfinite(m) | np.isclose(m, hp.UNSEEN)
        if bad.any():
            m = np.where(bad, np.nan, m)
            initial_masked = np.flatnonzero(bad).tolist()

    if save_dir is None:
        save_dir = os.getcwd()
    save_dir = os.path.abspath(save_dir)

    label = _get_label(source, mapmaker)

    coord_labels = {'G': ('l', 'b'), 'C': ('ra', 'dec'), 'E': ('lon', 'lat')}
    lon_name, lat_name = coord_labels.get(coord, ('lon', 'lat'))

    # Colormap
    valid = np.isfinite(m)
    vmin = float(np.nanmin(m[valid])) if valid.any() else 0.0
    vmax = float(np.nanmax(m[valid])) if valid.any() else 1.0
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap_fn = mcm.get_cmap(cmap)
    rgba = cmap_fn(norm(np.where(valid, m, vmin)))
    nan_color = '#2a2a2a'
    hex_colors = [
        '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b_*255))
        if valid[i] else nan_color
        for i, (r, g, b_, _) in enumerate(rgba)
    ]

    lut_vals = cmap_fn(np.linspace(0, 1, 256))
    lut_json = json.dumps([[int(r*255), int(g*255), int(b_*255)]
                           for r, g, b_, _ in lut_vals])

    # Pixel centres
    lon_c, lat_c = pixel_centres(nside, npix)

    # Pixel boundaries
    print(f'Computing pixel boundaries (nside={nside}, npix={npix})...')
    mx, my, wrap = pixel_boundaries(nside, npix, step=2)
    n_verts = mx.shape[1]

    # SVG polygons
    print('Building SVG...')
    polys = []
    for i in range(npix):
        if wrap[i]:
            continue
        pts = ' '.join(f'{mx[i,k]:.5f},{-my[i,k]:.5f}' for k in range(n_verts))
        color = hex_colors[i]
        polys.append(
            f'<polygon points="{pts}" fill="{color}" stroke="{color}" '
            f'data-idx="{i}" data-lon="{lon_c[i]:.2f}" data-lat="{lat_c[i]:.2f}"/>'
        )
    polygons_str = '\n    '.join(polys)

    # Graticule + layout
    graticule_str = '\n    '.join(graticule_lines())
    W, H = 2.0 * np.sqrt(2.0), np.sqrt(2.0)
    pad = 0.10
    vb_str = f'{-W-pad:.4f} {-H-pad:.4f} {2*(W+pad):.4f} {2*(H+pad):.4f}'
    ellipse_str = (
        f'<ellipse cx="0" cy="0" rx="{W:.5f}" ry="{H:.5f}" '
        f'fill="none" stroke="#333" stroke-width="0.006" pointer-events="none"/>'
    )

    # Pixel data for JS
    pix_lon_js = '[' + ','.join(f'{v:.2f}' for v in lon_c) + ']'
    pix_lat_js = '[' + ','.join(f'{v:.2f}' for v in lat_c) + ']'
    pix_fill_js = '[' + ','.join(f'"{c}"' for c in hex_colors) + ']'
    map_values_b64 = _encode_map_values(m)

    # Coordinate conversions
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    if coord == 'G':
        sky = SkyCoord(l=lon_c*u.deg, b=lat_c*u.deg, frame='galactic')
        pix_ra_js = '[' + ','.join(f'{v:.2f}' for v in sky.icrs.ra.deg) + ']'
        pix_dec_js = '[' + ','.join(f'{v:.2f}' for v in sky.icrs.dec.deg) + ']'
        pix_gl_js, pix_gb_js = pix_lon_js, pix_lat_js
    elif coord == 'C':
        sky = SkyCoord(ra=lon_c*u.deg, dec=lat_c*u.deg, frame='icrs')
        pix_ra_js, pix_dec_js = pix_lon_js, pix_lat_js
        pix_gl_js = '[' + ','.join(f'{v:.2f}' for v in sky.galactic.l.deg) + ']'
        pix_gb_js = '[' + ','.join(f'{v:.2f}' for v in sky.galactic.b.deg) + ']'
    else:
        pix_ra_js, pix_dec_js = pix_lon_js, pix_lat_js
        pix_gl_js, pix_gb_js = pix_lon_js, pix_lat_js

    # HEALPix neighbours
    print('Computing pixel neighbours...')
    all_nbrs = hp.get_all_neighbours(nside, np.arange(npix)).T
    nbrs_json = json.dumps(all_nbrs.tolist())

    # Escape title
    title_esc = (title.replace('&', '&amp;')
                      .replace('<', '&lt;')
                      .replace('>', '&gt;'))

    # Load templates
    css_str = _load_template('style.css')
    js_str = _load_template('viewer.js')
    html = _load_template('viewer.html')

    # Session restore
    session_js = ''
    if session and os.path.isfile(session):
        with open(session) as f:
            session_data = f.read()
        session_js = f'''
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
    initial_mask_js = ''
    if initial_masked:
        initial_mask_js = f'''
(function() {{
  try {{
    const initial = {json.dumps(initial_masked)};
    for (const i of initial) pixelMasks[i] = true;
    updateAllPolygons();
    updateMaskTable();
  }} catch(e) {{ console.warn('Initial mask init failed:', e); }}
}})();
'''
    js_str = js_str + '\n' + initial_mask_js + '\n' + session_js

    # Port placeholder — filled after server starts
    # We use a two-pass approach: build HTML with placeholder, start server,
    # then replace the port placeholder.
    for key, val in [
        ('%%CSS%%', css_str),
        ('%%JS%%', js_str),
        ('%%TITLE%%', title_esc),
        ('%%VIEWBOX%%', vb_str),
        ('%%POLYGONS%%', polygons_str),
        ('%%GRATICULE%%', graticule_str),
        ('%%ELLIPSE%%', ellipse_str),
        ('%%LON_NAME%%', lon_name),
        ('%%LAT_NAME%%', lat_name),
        ('%%NPIX%%', str(npix)),
        ('%%NSIDE%%', str(nside)),
        ('%%PIX_LON%%', pix_lon_js),
        ('%%PIX_LAT%%', pix_lat_js),
        ('%%PIX_RA%%', pix_ra_js),
        ('%%PIX_DEC%%', pix_dec_js),
        ('%%PIX_GL%%', pix_gl_js),
        ('%%PIX_GB%%', pix_gb_js),
        ('%%PIX_FILL%%', pix_fill_js),
        ('%%MAP_VALUES_B64%%', map_values_b64),
        ('%%NEIGHBOURS%%', nbrs_json),
        ('%%LUT%%', lut_json),
        ('%%NAN_COLOR%%', nan_color),
        ('%%MASK_FILL%%', _MASK_FILL),
        ('%%VMIN%%', f'{vmin:.6g}'),
        ('%%VMAX%%', f'{vmax:.6g}'),
        ('%%FLUX_ENABLED%%', 'true' if mapmaker is not None else 'false'),
        ('%%VAL_DECIMALS%%', str(int(decimals))),
    ]:
        html = html.replace(key, val)

    # Start server (serves the HTML and handles API calls)
    port = _start_server(html, save_dir, npix,
                         label=label, mapmaker=mapmaker, cmap=cmap,
                         count_map=m)

    # Also write to file for reference
    if outfile is None:
        fd, outfile = tempfile.mkstemp(suffix='.html', prefix='healpix_viewer_')
        os.close(fd)
    with open(outfile, 'w') as fh:
        fh.write(html)

    url = f'http://127.0.0.1:{port}/'
    print(f'Viewer saved -> {outfile}')
    print(f'Server on port {port}, saves to: {save_dir}')
    print(f'Opening: {url}')
    if browser:
        webbrowser.open(url)

    # Keep the server alive until the user interrupts
    print('Press Ctrl+C to stop the server.')
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print('\nServer stopped.')

    return outfile
