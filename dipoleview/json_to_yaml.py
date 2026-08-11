"""Convert a viewer session ``*_metadata.json`` into a readable mask YAML.

The JSON a viewer session writes is a full record of the editing session:
every cut and disc is stored together with the thousands of pixel indices
it happened to select at that resolution.  That is fine for reloading a
session, but it is unreadable, and it welds the mask to one nside.

``json_to_yaml`` strips it back to the recipe — the cuts, the discs, and
any pixels that were masked by hand — so anyone can rebuild the mask at
their own resolution with :func:`dipoleview.yaml_to_mask`.
"""

import json
import os
import re
from datetime import datetime, timezone

import numpy as np

from .yaml_to_mask import ANY, _PixelFrames, _cut_pixels, _disc_pixels

__all__ = ['json_to_yaml']

# Frames the viewer can pixelise a map in, and the names it labels the
# native longitude/latitude with in that frame.
_NATIVE_NAMES = {
    'galactic': ('l', 'b'),
    'equatorial': ('ra', 'dec'),
    'ecliptic': ('lon', 'lat'),
}
_ECLIPTIC_NAMES = ('elon', 'elat')

_PIXELS_PER_LINE = 12


def _session_masks(session):
    """Pixel indices the session masked, split by where they came from."""
    from_rules = set()
    for entry in session.get('sliceMasks') or []:
        from_rules.update(int(i) for i in entry.get('pixels', []))
    for entry in session.get('discMasks') or []:
        from_rules.update(int(i) for i in entry.get('pixels', []))
    by_hand = {int(index) for index, flagged in
               (session.get('pixelMasks') or {}).items() if flagged}
    return from_rules, by_hand


def _infer_coordinates(session, nside):
    """Work out which frame the map was pixelised in.

    Pixel indices only line up with a cut such as ``|b|<5`` if the pixel
    centres are read in the frame the map was actually binned in, so we
    replay every cut and disc in each candidate frame and keep whichever
    reproduces the stored indices best.
    """
    # Discs are recorded in the map's own frame, so they are replayed with
    # frame-relative lon/lat names that follow whichever frame is on trial.
    rules = [(_cut_pixels, entry['expr'],
              set(int(i) for i in entry.get('pixels', [])))
             for entry in session.get('sliceMasks') or []]
    rules += [(_disc_pixels, _disc_expression(entry, 'lon', 'lat'),
               set(int(i) for i in entry.get('pixels', [])))
              for entry in session.get('discMasks') or []]
    rules = [rule for rule in rules if rule[2]]

    labelled = _label_frame(session)
    if not rules:
        return labelled

    best, best_score = None, -1.0
    for frame in _NATIVE_NAMES:
        pixels = _PixelFrames(nside, 'RING', frame)
        score = 0.0
        for evaluate, expr, expected in rules:
            try:
                got = set(evaluate(expr, pixels).tolist())
            except ValueError:
                continue
            union = len(got | expected)
            score += len(got & expected) / union if union else 1.0
        if score > best_score:
            best, best_score = frame, score

    if labelled is not None and labelled != best:
        # The disc labels are written in the native frame, so they are the
        # more direct evidence — trust them and say so.
        print(f'  note: disc labels say {labelled}, pixel indices look like '
              f'{best}; going with {labelled}')
        return labelled
    return best


def _label_frame(session):
    """Frame implied by the disc labels, e.g. ``l=309.5 b=19.4 r=2.0°``."""
    for entry in session.get('discMasks') or []:
        label = str(entry.get('label', ''))
        for frame, (lon_name, _) in _NATIVE_NAMES.items():
            if label.startswith(lon_name + '='):
                return frame
    return None


def _disc_expression(entry, lon_name, lat_name):
    """Render one disc as ``l=309.5, b=19.4, r=2.0``."""
    return (f'{lon_name}={_number(entry["center_lon"])}, '
            f'{lat_name}={_number(entry["center_lat"])}, '
            f'r={_number(entry["radius_deg"])}')


def _number(value):
    """Format an angle exactly, keeping it readable and a decimal.

    ``repr`` is the shortest decimal that reads back as the same double, so
    a centre typed as 309.5 stays ``309.5`` and nothing is ever truncated.
    """
    text = repr(float(value))
    return text + '.0' if '.' not in text and 'e' not in text else text


def _rename_native(expr, coordinates):
    """Rewrite native ``lon``/``lat`` into a frame-explicit variable name.

    Cuts and discs stay in whatever coordinates they were written in, but
    ``lon``/``lat`` alone do not say which frame that is, so an ecliptic
    session gets its variables spelled out as ``elon``/``elat``.
    """
    if coordinates != 'ecliptic':
        return expr
    for native, explicit in zip(_NATIVE_NAMES['ecliptic'], _ECLIPTIC_NAMES):
        expr = re.sub(r'(?<![a-z])' + native + r'(?![a-z])', explicit, expr)
    return expr


def _quote(text):
    """YAML-safe double-quoted scalar."""
    return '"' + str(text).replace('\\', '\\\\').replace('"', '\\"') + '"'


def _format_pixels(indices):
    """A comma-separated flow sequence, wrapped over lines to stay readable."""
    if not indices:
        return 'pixels: []\n'
    lines = ['pixels: [']
    for start in range(0, len(indices), _PIXELS_PER_LINE):
        chunk = indices[start:start + _PIXELS_PER_LINE]
        tail = ',' if start + _PIXELS_PER_LINE < len(indices) else ''
        lines.append('  ' + ', '.join(str(i) for i in chunk) + tail)
    lines.append(']')
    return '\n'.join(lines) + '\n'


def json_to_yaml(json_path, yaml_path):
    """Write a mask YAML describing the mask in a viewer session JSON.

    Parameters
    ----------
    json_path : str
        A ``*_metadata.json`` saved by the dipoleview viewer.
    yaml_path : str
        Where to write the ``.yaml`` description.

    Returns
    -------
    str
        The path written.

    Notes
    -----
    ``coordinates``, ``nside`` and ``ordering`` are only pinned down when
    the mask lists individual pixels, because pixel indices are the one
    ingredient that is tied to a particular pixelisation.  A mask built
    purely from cuts and discs is left as ``ANY`` on all three, so it can
    be rebuilt at any resolution in any frame.
    """
    with open(json_path) as stream:
        session = json.load(stream)

    nside = int(session['nside'])
    coordinates = _infer_coordinates(session, nside) or 'equatorial'
    lon_name, lat_name = _NATIVE_NAMES[coordinates]

    cuts = [_rename_native(entry['expr'].strip(), coordinates)
            for entry in session.get('sliceMasks') or []]
    discs = [_rename_native(_disc_expression(entry, lon_name, lat_name),
                            coordinates)
             for entry in session.get('discMasks') or []]

    # Which pixels the cuts and discs account for on their own.  Recomputing
    # rather than trusting the stored index lists means the leftovers below
    # also absorb any pixel the browser and this code disagree about, so the
    # YAML rebuilds the original mask exactly.
    pixels = _PixelFrames(nside, 'RING', coordinates)
    reproduced = np.zeros(pixels.npix, dtype=bool)
    for expr in cuts:
        reproduced[_cut_pixels(expr, pixels)] = True
    for expr in discs:
        reproduced[_disc_pixels(expr, pixels)] = True

    from_rules, by_hand = _session_masks(session)
    original = np.zeros(pixels.npix, dtype=bool)
    original[sorted(from_rules | by_hand)] = True

    extra = sorted(np.flatnonzero(original & ~reproduced).tolist())
    overshoot = int((reproduced & ~original).sum())

    fixed = bool(extra)
    header = [
        '# HEALPix mask, written by dipoleview.',
        f'# Source: {os.path.basename(json_path)}',
        f'# Written: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}',
        '#',
        '# Rebuild it with yaml_to_mask.py:',
        '#     mask = yaml_to_mask("' + os.path.basename(yaml_path) + '")',
        '# giving a boolean array, True = keep, False = masked out.',
        '#',
        '# Pixels matching any cut, or falling inside any disc, are masked',
        '# out. Angles are degrees; cuts and discs name their own frame, so',
        '# they hold whatever frame the map itself is pixelised in.',
    ]
    if fixed:
        header += [
            '#',
            '# This mask lists individual pixels that no cut or disc accounts',
            '# for, so coordinates, nside and ordering are fixed below and',
            '# cannot be overridden.',
        ]
    else:
        header += [
            '#',
            '# Every masked pixel follows from the cuts and discs, so this',
            '# mask can be rebuilt at any nside, ordering and pixelisation',
            '# frame you like.',
        ]

    lines = header + ['']
    lines.append(f'coordinates: {coordinates if fixed else ANY}')
    lines.append(f'nside: {nside if fixed else ANY}')
    lines.append(f'ordering: {"RING" if fixed else ANY}')
    lines.append('')

    lines.append('cuts:' if cuts else 'cuts: []')
    lines += [f'  - {_quote(cut)}' for cut in cuts]
    lines.append('')

    lines.append('discs:' if discs else 'discs: []')
    lines += [f'  - {_quote(disc)}' for disc in discs]
    lines.append('')

    text = '\n'.join(lines) + '\n' + _format_pixels(extra)
    with open(yaml_path, 'w') as stream:
        stream.write(text)

    print(f'{os.path.basename(json_path)} -> {yaml_path}')
    print(f'  pixelised in {coordinates} at nside={nside}'
          + ('' if fixed else ' (recorded as ANY — no hand-masked pixels)'))
    print(f'  {len(cuts)} cuts, {len(discs)} discs, {len(extra)} extra pixels; '
          f'{int(original.sum())} pixels masked of {pixels.npix}')
    if overshoot:
        # The viewer compares against pixel coordinates rounded to 2 decimal
        # places, so a pixel sitting within ~0.005 deg of a cut or disc edge
        # can fall on the other side of it here.
        print(f'  note: {overshoot} pixel(s) sit right on a cut or disc edge '
              f'and are masked here but were not in the session')
    return yaml_path
