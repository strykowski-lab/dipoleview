// =========================================================
// Data (injected by Python)
// =========================================================
const NPIX      = %%NPIX%%;
const PIX_LON   = %%PIX_LON%%;
const PIX_LAT   = %%PIX_LAT%%;
const PIX_RA    = %%PIX_RA%%;
const PIX_DEC   = %%PIX_DEC%%;
const PIX_GL    = %%PIX_GL%%;
const PIX_GB    = %%PIX_GB%%;
const PIX_FILL  = %%PIX_FILL%%;
const NAN_COLOR = '%%NAN_COLOR%%';
const MASK_FILL = '%%MASK_FILL%%';
const LON_NAME  = '%%LON_NAME%%';
const LAT_NAME  = '%%LAT_NAME%%';
const NSIDE     = %%NSIDE%%;
const NEIGHBOURS = %%NEIGHBOURS%%;
const LUT = %%LUT%%;
const ORIG_VMIN = %%VMIN%%;
const ORIG_VMAX = %%VMAX%%;
const FLUX_ENABLED = %%FLUX_ENABLED%%;

// Decode raw map values
function b64ToFloat32(b64) {
  const binary = atob(b64);
  const buf = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) buf[i] = binary.charCodeAt(i);
  return new Float32Array(buf.buffer);
}
const MAP_VALUES = b64ToFloat32('%%MAP_VALUES_B64%%');

// =========================================================
// Mutable state
// =========================================================
let currentFill    = PIX_FILL.slice();
let showSmooth     = false;
let smoothFill     = null;
let smoothVals     = null;  // raw averaged values from last computeSmooth()
let rawVmin        = ORIG_VMIN;
let rawVmax        = ORIG_VMAX;
let smoothVmin     = null;
let smoothVmax     = null;
let sliceMasks     = [];
let discMasks      = [];
let pixelMasks     = {};
let history        = [];
let future         = [];

// =========================================================
// DOM refs
// =========================================================
const svgEl      = document.getElementById('map-svg');
const pixLayer   = document.getElementById('pixels');
const hoverInfo  = document.getElementById('hover-info');
const selInfo    = document.getElementById('sel-info');
const undoBtn    = document.getElementById('undo-btn');
const redoBtn    = document.getElementById('redo-btn');
const smoothBtn  = document.getElementById('smooth-btn');
const refreshBtn = document.getElementById('refresh-btn');
const saveBtn    = document.getElementById('save-btn');
const loadBtn    = document.getElementById('load-btn');
const saveStatus = document.getElementById('save-status');
const zoomPctEl  = document.getElementById('zoom-pct');

const polyElems = new Array(NPIX).fill(null);
for (const el of pixLayer.querySelectorAll('polygon')) {
  polyElems[+el.dataset.idx] = el;
}

// Patch all coord-system-dependent UI text using the injected LON_NAME / LAT_NAME.
document.getElementById('copy-coord-btn').textContent = 'Copy ' + LON_NAME + ',' + LAT_NAME;
document.getElementById('disc-center-label').textContent = LON_NAME + ' ' + LAT_NAME;
document.getElementById('coord-search-inp').placeholder =
  LON_NAME + ' ' + LAT_NAME + '  (e.g. 120 \u221215)';

let hoveredIdx  = -1;
let selectedIdx = -1;
let dragDist    = 0;

// =========================================================
// Mask helpers
// =========================================================
function getMaskedSet() {
  const s = new Set(Object.keys(pixelMasks).map(Number));
  for (const sm of sliceMasks) for (const idx of sm.pixels) s.add(idx);
  for (const dm of discMasks)  for (const idx of dm.pixels) s.add(idx);
  return s;
}

function effectiveColor(i, maskedSet) {
  if (maskedSet.has(i)) return MASK_FILL;
  if (showSmooth && smoothFill) return smoothFill[i] || currentFill[i];
  return currentFill[i];
}

function updateSourceCount() {
  const masked = getMaskedSet();
  let total = 0;
  for (let i = 0; i < NPIX; i++) {
    if (masked.has(i)) continue;
    const v = MAP_VALUES[i];
    if (isFinite(v)) total += v;
  }
  const el = document.getElementById('source-count');
  if (el) el.textContent = Math.round(total).toLocaleString() + ' sources';
}

function hex2(n) { return n.toString(16).padStart(2, '0'); }

function recomputeRawFill() {
  // Re-stretch currentFill across the visible (non-masked, non-NaN) range
  // so the full colormap is always used.
  const masked = getMaskedSet();
  let vmin = Infinity, vmax = -Infinity;
  for (let i = 0; i < NPIX; i++) {
    if (masked.has(i)) continue;
    const v = MAP_VALUES[i];
    if (!isFinite(v)) continue;
    if (v < vmin) vmin = v;
    if (v > vmax) vmax = v;
  }
  if (!isFinite(vmin)) { vmin = ORIG_VMIN; vmax = ORIG_VMAX; }
  const rng = vmax > vmin ? vmax - vmin : 1;
  for (let i = 0; i < NPIX; i++) {
    const v = MAP_VALUES[i];
    if (!isFinite(v)) { currentFill[i] = NAN_COLOR; continue; }
    const t = Math.min(255, Math.max(0, Math.round(255 * (v - vmin) / rng)));
    const [r, g, b] = LUT[t];
    currentFill[i] = '#' + hex2(r) + hex2(g) + hex2(b);
  }
  rawVmin = vmin;
  rawVmax = vmax;
}

function updateAllPolygons() {
  recomputeRawFill();
  const masked = getMaskedSet();
  for (let i = 0; i < NPIX; i++) {
    const el = polyElems[i];
    if (!el) continue;
    const c = effectiveColor(i, masked);
    el.setAttribute('fill', c);
    el.setAttribute('stroke', c);
  }
  // Update colorbar limits if the function exists (it's defined after this)
  if (typeof updateColorbar === 'function') updateColorbar();
  updateSourceCount();
}

// =========================================================
// Colorbar
// =========================================================
const cbarCanvas = document.getElementById('cbar-canvas');
const cbarMinEl  = document.getElementById('cbar-min');
const cbarMaxEl  = document.getElementById('cbar-max');

function initColorbar() {
  const ctx = cbarCanvas.getContext('2d');
  const imgData = ctx.createImageData(256, 1);
  for (let i = 0; i < 256; i++) {
    const [r, g, b] = LUT[i];
    imgData.data[i * 4]     = r;
    imgData.data[i * 4 + 1] = g;
    imgData.data[i * 4 + 2] = b;
    imgData.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(imgData, 0, 0);
}

function updateColorbar() {
  // Show the range the pixel colormap is currently stretched across.
  // When smoothing is on, use the smoothed-map range; otherwise the raw range
  // that recomputeRawFill() last computed from the visible pixels.
  let vmin, vmax;
  if (showSmooth && smoothVmin !== null && smoothVmax !== null) {
    vmin = smoothVmin;
    vmax = smoothVmax;
  } else {
    vmin = rawVmin;
    vmax = rawVmax;
  }
  if (!isFinite(vmin)) { vmin = ORIG_VMIN; vmax = ORIG_VMAX; }
  cbarMinEl.textContent = vmin.toPrecision(4);
  cbarMaxEl.textContent = vmax.toPrecision(4);
}

initColorbar();
updateColorbar();
updateSourceCount();

// =========================================================
// Undo / redo
// =========================================================
function snapshotState() {
  const smSerial = sliceMasks.map(sm => ({expr: sm.expr, pixels: Array.from(sm.pixels)}));
  const dmSerial = discMasks.map(dm => ({
    center_lon: dm.center_lon, center_lat: dm.center_lat,
    radius_deg: dm.radius_deg, pixels: dm.pixels, label: dm.label,
  }));
  return JSON.stringify({sliceMasks: smSerial, discMasks: dmSerial, pixelMasks});
}

function saveSnapshot() {
  history.push(snapshotState());
  future = [];
  updateUndoRedoButtons();
}

function restoreSnapshot(snap) {
  const s    = JSON.parse(snap);
  sliceMasks = s.sliceMasks.map(sm => ({expr: sm.expr, pixels: sm.pixels}));
  discMasks  = (s.discMasks || []).map(dm => ({...dm}));
  pixelMasks = s.pixelMasks;
  updateAllPolygons();
  updateSliceList();
  updateDiscList();
  updateMaskTable();
}

function undo() {
  if (!history.length) return;
  future.push(snapshotState());
  restoreSnapshot(history.pop());
  updateUndoRedoButtons();
}

function redo() {
  if (!future.length) return;
  history.push(snapshotState());
  restoreSnapshot(future.pop());
  updateUndoRedoButtons();
}

function updateUndoRedoButtons() {
  undoBtn.disabled = !history.length;
  redoBtn.disabled = !future.length;
}

undoBtn.onclick = undo;
redoBtn.onclick = redo;

// Helper to select a pixel by index
function selectPixel(i) {
  if (selectedIdx !== -1 && polyElems[selectedIdx])
    polyElems[selectedIdx].classList.remove('selected');
  selectedIdx = i;
  if (polyElems[i]) polyElems[i].classList.add('selected');
  renderSelInfo();
}

document.addEventListener('keydown', e => {
  const tag = document.activeElement.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') return;

  if (e.key === 'z' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    if (e.shiftKey) redo(); else undo();
    return;
  }

  // Arrow key navigation (edge neighbours in Mollweide visual space)
  // HEALPix: [SW(0), W(1), NW(2), N(3), NE(4), E(5), SE(6), S(7)]
  // Mollweide screen: NW(2)=top-right, NE(4)=top-left, SW(0)=bot-right, SE(6)=bot-left
  const arrowMap = {
    'ArrowUp':    2,  // NW = visually top-right edge
    'ArrowLeft':  4,  // NE = visually top-left edge
    'ArrowRight': 0,  // SW = visually bottom-right edge
    'ArrowDown':  6,  // SE = visually bottom-left edge
  };
  if (arrowMap.hasOwnProperty(e.key) && selectedIdx !== -1) {
    e.preventDefault();
    const nbr = NEIGHBOURS[selectedIdx][arrowMap[e.key]];
    if (nbr >= 0 && nbr < NPIX) selectPixel(nbr);
    return;
  }

  // Enter to mask/unmask selected pixel
  if (e.key === 'Enter' && selectedIdx !== -1) {
    e.preventDefault();
    const i = selectedIdx;
    const masked = getMaskedSet();
    if (masked.has(i) && pixelMasks[i]) {
      saveSnapshot();
      delete pixelMasks[i];
      updateAllPolygons();
      updateMaskTable();
    } else if (!masked.has(i)) {
      saveSnapshot();
      pixelMasks[i] = true;
      updateAllPolygons();
      updateMaskTable();
    }
    return;
  }
});

// =========================================================
// Smooth toggle + refresh
// =========================================================
function updateSmoothBtn() {
  smoothBtn.textContent = showSmooth ? 'SMOOTH: ON' : 'SMOOTH: OFF';
  smoothBtn.classList.toggle('active', showSmooth);
}

smoothBtn.onclick = () => {
  showSmooth = !showSmooth;
  updateSmoothBtn();
  updateAllPolygons();
  renderSelInfo();
  if (hoveredIdx !== -1) {
    const el = polyElems[hoveredIdx];
    if (el) hoverInfo.textContent =
      LON_NAME + ': ' + PIX_LON[hoveredIdx].toFixed(2) + '\u00b0\u2002' +
      LAT_NAME + ': ' + PIX_LAT[hoveredIdx].toFixed(2) + '\u00b0\u2002' +
      'val: ' + pixelValStr(hoveredIdx);
  }
};
updateSmoothBtn();

refreshBtn.onclick = () => {
  if (!showSmooth) return;
  refreshBtn.disabled = true;
  refreshBtn.textContent = 'Computing...';
  setTimeout(() => {
    computeSmooth();
    updateAllPolygons();
    renderSelInfo();
    if (hoveredIdx !== -1) {
      const el = polyElems[hoveredIdx];
      if (el) hoverInfo.textContent =
        LON_NAME + ': ' + PIX_LON[hoveredIdx].toFixed(2) + '\u00b0\u2002' +
        LAT_NAME + ': ' + PIX_LAT[hoveredIdx].toFixed(2) + '\u00b0\u2002' +
        'val: ' + pixelValStr(hoveredIdx);
    }
    refreshBtn.disabled = false;
    refreshBtn.textContent = 'Refresh smooth';
  }, 50);
};

function computeSmooth() {
  // Exact translation of smooth_map() in smooth.py.
  //
  // Algorithm:
  //   1. Convert steradians -> angular radius -> chord distance.
  //   2. Build 3D unit vectors from PIX_LON/PIX_LAT (identical to
  //      hp.pix2vec output because lat = 90 - theta, lon = phi).
  //   3. For each unmasked pixel j, iterate over ALL pixels, keep those
  //      that are both (a) within chord distance and (b) unmasked, then
  //      average their MAP_VALUES — matching the cKDTree query_ball_point
  //      + is_unmasked filter in the Python code.
  //
  // This is O(N_unmasked * N_total) and slow for large maps, but gives
  // numerically identical results to the Python implementation.

  const srInput = document.getElementById('smooth-sr-inp');
  const steradians = Math.max(0.1, parseFloat(srInput.value) || 1.0);

  // radius = arccos(1 - steradians / (2*pi))
  // chord  = 2 * sin(radius / 2)
  const radius = Math.acos(1 - steradians / (2 * Math.PI));
  const chord  = 2 * Math.sin(radius / 2);
  const chord2 = chord * chord;

  const maskedSet = getMaskedSet();
  const isUnmasked = new Uint8Array(NPIX);
  for (let i = 0; i < NPIX; i++) {
    if (!maskedSet.has(i)) isUnmasked[i] = 1;
  }

  // 3D unit vectors from (lon, lat) degrees.
  // hp.pix2vec returns (sin(theta)*cos(phi), sin(theta)*sin(phi), cos(theta))
  // which equals (cos(lat)*cos(lon), cos(lat)*sin(lon), sin(lat)).
  const DEG2RAD = Math.PI / 180;
  const vx = new Float64Array(NPIX);
  const vy = new Float64Array(NPIX);
  const vz = new Float64Array(NPIX);
  for (let i = 0; i < NPIX; i++) {
    const lonR = PIX_LON[i] * DEG2RAD;
    const latR = PIX_LAT[i] * DEG2RAD;
    const cosLat = Math.cos(latR);
    vx[i] = cosLat * Math.cos(lonR);
    vy[i] = cosLat * Math.sin(lonR);
    vz[i] = Math.sin(latR);
  }

  // For each unmasked pixel j: collect all unmasked pixels within chord
  // distance (including j itself) and average MAP_VALUES.
  smoothVals = new Float64Array(NPIX).fill(NaN);
  const averageVals = smoothVals;
  for (let j = 0; j < NPIX; j++) {
    if (!isUnmasked[j]) continue;
    const xj = vx[j], yj = vy[j], zj = vz[j];
    let sum = 0, cnt = 0;
    for (let i = 0; i < NPIX; i++) {
      if (!isUnmasked[i]) continue;
      const dx = xj - vx[i], dy = yj - vy[i], dz = zj - vz[i];
      if (dx*dx + dy*dy + dz*dz <= chord2) {
        const v = MAP_VALUES[i];
        if (isFinite(v)) { sum += v; cnt++; }
      }
    }
    if (cnt > 0) averageVals[j] = sum / cnt;
  }

  smoothFill = new Array(NPIX);
  let vmin = Infinity, vmax = -Infinity;
  for (let i = 0; i < NPIX; i++) {
    if (isUnmasked[i] && isFinite(averageVals[i])) {
      if (averageVals[i] < vmin) vmin = averageVals[i];
      if (averageVals[i] > vmax) vmax = averageVals[i];
    }
  }
  const rng = vmax > vmin ? vmax - vmin : 1;
  for (let i = 0; i < NPIX; i++) {
    if (!isUnmasked[i]) { smoothFill[i] = MASK_FILL; continue; }
    if (!isFinite(averageVals[i])) { smoothFill[i] = NAN_COLOR; continue; }
    const t = Math.min(255, Math.max(0, Math.round(255 * (averageVals[i] - vmin) / rng)));
    const [r, g, b] = LUT[t];
    smoothFill[i] = '#' + hex2(r) + hex2(g) + hex2(b);
  }
  if (isFinite(vmin)) { smoothVmin = vmin; smoothVmax = vmax; }
  else { smoothVmin = null; smoothVmax = null; }
}

// Test: compare JS smooth results against the Python smooth_map endpoint.
// Call testSmooth() from the browser console to run a comparison.
function testSmooth() {
  const srInput = document.getElementById('smooth-sr-inp');
  const steradians = Math.max(0.1, parseFloat(srInput.value) || 1.0);
  const maskedSet = getMaskedSet();
  const maskedPixels = [];
  for (let i = 0; i < NPIX; i++) { if (maskedSet.has(i)) maskedPixels.push(i); }

  // Ensure JS smooth is computed with current mask/steradians
  computeSmooth();

  fetch('/smooth', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({masked_pixels: maskedPixels, steradians}),
  })
  .then(r => r.json())
  .then(data => {
    const pyVals = data.values;  // full-sky array, NaN for masked/invalid
    let maxAbsDiff = 0, nDiff = 0, nChecked = 0;
    for (let i = 0; i < NPIX; i++) {
      if (!maskedSet.has(i) && isFinite(pyVals[i]) && isFinite(MAP_VALUES[i])) {
        nChecked++;
        const jsDiff = Math.abs(smoothVals[i] - pyVals[i]);
        if (jsDiff > maxAbsDiff) maxAbsDiff = jsDiff;
        if (jsDiff > 1e-6) nDiff++;
      }
    }
    console.log(`smooth test: checked ${nChecked} pixels, max |diff| = ${maxAbsDiff.toExponential(3)}, n_diff(>1e-6) = ${nDiff}`);
    if (nDiff === 0) console.log('PASS: JS and Python smooth agree.');
    else console.warn('FAIL: discrepancies found.');
  })
  .catch(err => console.error('testSmooth failed:', err));
}

// =========================================================
// Hover / click
// =========================================================
pixLayer.addEventListener('mouseover', e => {
  const el = e.target.closest('polygon');
  if (!el) return;
  const i = +el.dataset.idx;
  if (hoveredIdx !== -1 && polyElems[hoveredIdx])
    polyElems[hoveredIdx].classList.remove('hovered');
  hoveredIdx = i;
  el.classList.add('hovered');
  hoverInfo.textContent =
    LON_NAME + ': ' + (+el.dataset.lon).toFixed(2) + '\u00b0\u2002' +
    LAT_NAME + ': ' + (+el.dataset.lat).toFixed(2) + '\u00b0\u2002' +
    'val: ' + pixelValStr(i);
});

pixLayer.addEventListener('mouseout', e => {
  const el = e.target.closest('polygon');
  if (!el) return;
  if (hoveredIdx !== -1 && polyElems[hoveredIdx])
    polyElems[hoveredIdx].classList.remove('hovered');
  hoveredIdx = -1;
  hoverInfo.textContent = '\u2014';
});

pixLayer.addEventListener('click', e => {
  if (dragDist > 5) return;
  // Always use the hovered pixel so click matches the black border
  const i = hoveredIdx;
  if (i < 0) return;

  const masked = getMaskedSet();

  if (masked.has(i)) {
    if (pixelMasks[i]) {
      saveSnapshot();
      delete pixelMasks[i];
      updateAllPolygons();
      updateMaskTable();
      if (selectedIdx === i) { selectedIdx = -1; renderSelInfo(); }
    }
  } else if (selectedIdx === i) {
    saveSnapshot();
    if (polyElems[i]) polyElems[i].classList.remove('selected');
    pixelMasks[i] = true;
    selectedIdx = -1;
    updateAllPolygons();
    renderSelInfo();
    updateMaskTable();
  } else {
    if (selectedIdx !== -1 && polyElems[selectedIdx])
      polyElems[selectedIdx].classList.remove('selected');
    selectedIdx = i;
    if (polyElems[i]) polyElems[i].classList.add('selected');
    renderSelInfo();
  }
});

// Returns the display value for pixel i: smoothed if smooth is on, raw otherwise.
function pixelVal(i) {
  if (showSmooth && smoothVals) return smoothVals[i];
  return MAP_VALUES[i];
}

function pixelValStr(i) {
  const v = pixelVal(i);
  if (!isFinite(v)) return 'nan';
  return (showSmooth && smoothVals) ? v.toFixed(2) : String(Math.round(v));
}

function renderSelInfo() {
  const copyBtn = document.getElementById('copy-coord-btn');
  if (selectedIdx === -1) {
    selInfo.textContent = '';
    copyBtn.style.display = 'none';
  } else {
    selInfo.textContent =
      '[sel] ' + LON_NAME + ': ' + PIX_LON[selectedIdx].toFixed(2) + '\u00b0  ' +
      LAT_NAME + ': ' + PIX_LAT[selectedIdx].toFixed(2) + '\u00b0  ' +
      'val: ' + pixelValStr(selectedIdx);
    copyBtn.style.display = '';
  }
}

// =========================================================
// Slice expression parser
// =========================================================
function parseSliceExpr(expr) {
  expr = expr.trim();
  const varArrays = {
    'ra': PIX_RA, 'dec': PIX_DEC,
    'l': PIX_GL, 'b': PIX_GB,
    'lon': PIX_LON, 'lat': PIX_LAT,
  };
  const allVars = ['dec', 'lat', 'lon', 'ra', 'b', 'l'];
  let varName = null;
  for (const v of allVars) {
    if (new RegExp('(?<![a-z])' + v + '(?![a-z])').test(expr)) {
      varName = v; break;
    }
  }
  if (!varName) return null;
  const values = varArrays[varName];

  let useAbs = false, cleanExpr = expr;
  if (expr.includes('|')) {
    useAbs = true;
    cleanExpr = expr.replace(/\|[^|]+\|/g, varName);
  }

  const ops = {
    '<': (a,b)=>a<b, '<=': (a,b)=>a<=b,
    '>': (a,b)=>a>b, '>=': (a,b)=>a>=b,
  };

  const two = cleanExpr.match(/^(-?[\d.]+)\s*([<>]=?)\s*\w+\s*([<>]=?)\s*(-?[\d.]+)$/);
  if (two) {
    const lv=parseFloat(two[1]), lop=two[2], rop=two[3], rv=parseFloat(two[4]);
    const result = [];
    for (let i=0;i<NPIX;i++) { const v=useAbs?Math.abs(values[i]):values[i]; if(ops[lop](lv,v)&&ops[rop](v,rv)) result.push(i); }
    return result;
  }
  const one_vf = cleanExpr.match(/^\w+\s*([<>]=?)\s*(-?[\d.]+)$/);
  if (one_vf) {
    const op=one_vf[1], num=parseFloat(one_vf[2]);
    const result = [];
    for (let i=0;i<NPIX;i++) { const v=useAbs?Math.abs(values[i]):values[i]; if(ops[op](v,num)) result.push(i); }
    return result;
  }
  const one_nf = cleanExpr.match(/^(-?[\d.]+)\s*([<>]=?)\s*\w+$/);
  if (one_nf) {
    const num=parseFloat(one_nf[1]), op=one_nf[2];
    const result = [];
    for (let i=0;i<NPIX;i++) { const v=useAbs?Math.abs(values[i]):values[i]; if(ops[op](num,v)) result.push(i); }
    return result;
  }
  return null;
}

function applySlice(expr) {
  const pixels = parseSliceExpr(expr);
  if (pixels === null) { alert('Could not parse: ' + expr); return; }
  saveSnapshot();
  sliceMasks.push({expr, pixels});
  updateAllPolygons();
  updateSliceList();
}

function updateSliceList() {
  const div = document.getElementById('slice-list');
  div.innerHTML = '';
  sliceMasks.forEach((sm, idx) => {
    const row = document.createElement('div');
    row.className = 'slice-row';
    const span = document.createElement('span');
    span.textContent = sm.expr;
    const btn = document.createElement('button');
    btn.textContent = '\u00d7';
    btn.className = 'remove-btn';
    btn.onclick = () => { saveSnapshot(); sliceMasks.splice(idx,1); updateAllPolygons(); updateSliceList(); };
    row.appendChild(span); row.appendChild(btn); div.appendChild(row);
  });
}

document.getElementById('apply-slice-btn').onclick = () => {
  const ta = document.getElementById('slice-input');
  const expr = ta.value.trim();
  if (expr) { applySlice(expr); ta.value = ''; }
};

document.getElementById('slice-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('apply-slice-btn').click();
  }
});

// =========================================================
// Disc masks
// =========================================================
function computeDiscPixels(center_lon, center_lat, radius_deg) {
  // Works in whatever native coord system PIX_LON/PIX_LAT are in.
  // Angular separation is coordinate-system independent.
  const DEG2RAD = Math.PI / 180;
  const cosRad  = Math.cos(radius_deg * DEG2RAD);
  const latR    = center_lat * DEG2RAD;
  const lonR    = center_lon * DEG2RAD;
  const cosLat  = Math.cos(latR);
  const cx = cosLat * Math.cos(lonR);
  const cy = cosLat * Math.sin(lonR);
  const cz = Math.sin(latR);
  const pixels = [];
  for (let i = 0; i < NPIX; i++) {
    const lonRi   = PIX_LON[i] * DEG2RAD;
    const latRi   = PIX_LAT[i] * DEG2RAD;
    const cosLatI = Math.cos(latRi);
    const dot = cx * cosLatI * Math.cos(lonRi)
              + cy * cosLatI * Math.sin(lonRi)
              + cz * Math.sin(latRi);
    if (dot >= cosRad) pixels.push(i);
  }
  return pixels;
}

function updateDiscList() {
  const div = document.getElementById('disc-list');
  div.innerHTML = '';
  discMasks.forEach((dm, idx) => {
    const row  = document.createElement('div');
    row.className = 'slice-row';
    const span = document.createElement('span');
    span.textContent = dm.label;
    const btn  = document.createElement('button');
    btn.textContent = '\u00d7';
    btn.className = 'remove-btn';
    btn.onclick = () => { saveSnapshot(); discMasks.splice(idx, 1); updateAllPolygons(); updateDiscList(); };
    row.appendChild(span); row.appendChild(btn); div.appendChild(row);
  });
}

document.getElementById('apply-disc-btn').onclick = () => {
  const centerInp = document.getElementById('disc-center-inp');
  const radiusInp = document.getElementById('disc-radius-inp');
  const parts = centerInp.value.trim().split(/\s+/);
  if (parts.length !== 2) {
    alert('Enter center as "' + LON_NAME + ' ' + LAT_NAME + '" (two numbers separated by a space)');
    return;
  }
  const center_lon = parseFloat(parts[0]);
  const center_lat = parseFloat(parts[1]);
  const radius_deg = parseFloat(radiusInp.value);
  if (!isFinite(center_lon) || !isFinite(center_lat)) {
    alert('Invalid ' + LON_NAME + ' ' + LAT_NAME + ' coordinates');
    return;
  }
  if (!isFinite(radius_deg) || radius_deg <= 0) {
    alert('Radius must be a positive number of degrees');
    return;
  }
  const pixels = computeDiscPixels(center_lon, center_lat, radius_deg);
  const label  = LON_NAME + '=' + center_lon.toFixed(1) + ' '
               + LAT_NAME + '=' + center_lat.toFixed(1) + ' r=' + radius_deg.toFixed(1) + '\u00b0';
  saveSnapshot();
  discMasks.push({center_lon, center_lat, radius_deg, pixels, label});
  updateAllPolygons();
  updateDiscList();
  centerInp.value = '';
  radiusInp.value = '';
};

['disc-center-inp', 'disc-radius-inp'].forEach(id => {
  document.getElementById(id).addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); document.getElementById('apply-disc-btn').click(); }
  });
});

// =========================================================
// Coordinate search
// =========================================================
document.getElementById('coord-search-btn').onclick = () => {
  const val   = document.getElementById('coord-search-inp').value.trim();
  const parts = val.split(/\s+/);
  if (parts.length !== 2) {
    alert('Enter coords as "' + LON_NAME + ' ' + LAT_NAME + '"');
    return;
  }
  const lon = parseFloat(parts[0]);
  const lat = parseFloat(parts[1]);
  if (!isFinite(lon) || !isFinite(lat)) { alert('Invalid coordinates'); return; }

  // Find the pixel whose centre is closest to (lon, lat) in the native coord system.
  const DEG2RAD = Math.PI / 180;
  const cosLat = Math.cos(lat * DEG2RAD);
  const qx = cosLat * Math.cos(lon * DEG2RAD);
  const qy = cosLat * Math.sin(lon * DEG2RAD);
  const qz = Math.sin(lat * DEG2RAD);
  let bestDot = -Infinity, bestIdx = 0;
  for (let i = 0; i < NPIX; i++) {
    const lonRi   = PIX_LON[i] * DEG2RAD;
    const latRi   = PIX_LAT[i] * DEG2RAD;
    const cosLatI = Math.cos(latRi);
    const dot = qx * cosLatI * Math.cos(lonRi)
              + qy * cosLatI * Math.sin(lonRi)
              + qz * Math.sin(latRi);
    if (dot > bestDot) { bestDot = dot; bestIdx = i; }
  }
  selectPixel(bestIdx);
};

document.getElementById('coord-search-inp').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); document.getElementById('coord-search-btn').click(); }
});

// =========================================================
// Copy l,b for selected pixel
// =========================================================
document.getElementById('copy-coord-btn').onclick = () => {
  if (selectedIdx === -1) return;
  const text = PIX_LON[selectedIdx].toFixed(2) + ' ' + PIX_LAT[selectedIdx].toFixed(2);
  navigator.clipboard.writeText(text).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta);
  });
};

// =========================================================
// Pixel mask table
// =========================================================
function updateMaskTable() {
  const div = document.getElementById('pixel-table');
  div.innerHTML = '';
  const keys = Object.keys(pixelMasks).map(Number).sort((a,b)=>a-b);
  if (!keys.length) {
    const note = document.createElement('div');
    note.style.cssText = 'color:#555;font-size:11px;padding:2px 0';
    note.textContent = 'No masked pixels';
    div.appendChild(note);
    return;
  }
  keys.forEach(i => {
    const row = document.createElement('div');
    row.className = 'mask-row';
    const span = document.createElement('span');
    span.textContent = LON_NAME+'='+PIX_LON[i].toFixed(1)+'\u00b0 '+LAT_NAME+'='+PIX_LAT[i].toFixed(1)+'\u00b0';
    const btn = document.createElement('button');
    btn.textContent = '\u00d7';
    btn.className = 'remove-btn';
    btn.onclick = () => {
      saveSnapshot(); delete pixelMasks[i];
      updateAllPolygons();
      updateMaskTable();
    };
    row.appendChild(span); row.appendChild(btn); div.appendChild(row);
  });
}
updateMaskTable();

// =========================================================
// Flux cut (server-side via MapMaker)
// =========================================================
const fluxMinInp = document.getElementById('flux-min-inp');
const fluxMaxInp = document.getElementById('flux-max-inp');
const redrawBtn  = document.getElementById('redraw-btn');

if (!FLUX_ENABLED) {
  fluxMinInp.disabled = true;
  fluxMaxInp.disabled = true;
  redrawBtn.disabled = true;
  redrawBtn.classList.add('flux-disabled');
  redrawBtn.title = 'Pass a MapMaker object to view() to enable flux cuts';
} else {
  redrawBtn.onclick = () => {
    const minVal = fluxMinInp.value.trim();
    const maxVal = fluxMaxInp.value.trim();
    const fMin = minVal === '' ? null : parseFloat(minVal);
    const fMax = maxVal === '' ? null : parseFloat(maxVal);

    if (fMin !== null && isNaN(fMin)) return;
    if (fMax !== null && isNaN(fMax)) return;

    redrawBtn.disabled = true;
    redrawBtn.textContent = 'Computing...';

    fetch('/flux-cut', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({min: fMin, max: fMax}),
    })
    .then(r => {
      if (!r.ok) return r.text().then(t => { throw new Error(t); });
      return r.json();
    })
    .then(data => {
      for (let i = 0; i < NPIX; i++) {
        currentFill[i] = data.colors[i];
        PIX_FILL[i] = data.colors[i];
      }
      const newVals = b64ToFloat32(data.values_b64);
      for (let i = 0; i < NPIX; i++) MAP_VALUES[i] = newVals[i];

      if (showSmooth) { showSmooth = false; updateSmoothBtn(); }
      updateAllPolygons();
      redrawBtn.disabled = false;
      redrawBtn.textContent = 'Apply cut';
    })
    .catch(err => {
      console.error('Flux cut failed:', err);
      alert('Flux cut failed: ' + err.message);
      redrawBtn.disabled = false;
      redrawBtn.textContent = 'Apply cut';
    });
  };
}

// =========================================================
// Save / Load session (via server)
// =========================================================
saveBtn.onclick = () => {
  const session = {
    nside: NSIDE,
    npix: NPIX,
    sliceMasks: sliceMasks.map(sm => ({expr: sm.expr, pixels: Array.from(sm.pixels)})),
    discMasks:  discMasks.map(dm => ({
      center_lon: dm.center_lon, center_lat: dm.center_lat,
      radius_deg: dm.radius_deg, pixels: dm.pixels, label: dm.label,
    })),
    pixelMasks: pixelMasks,
    timestamp: new Date().toISOString(),
  };
  const maskedSet = getMaskedSet();
  const maskedPixels = [];
  for (let i = 0; i < NPIX; i++) { if (maskedSet.has(i)) maskedPixels.push(i); }

  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving...';

  fetch('/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session, masked_pixels: maskedPixels}),
  })
  .then(r => { if (!r.ok) throw new Error('Save failed'); return r.json(); })
  .then(data => {
    saveStatus.textContent = 'Saved: ' + data.metadata;
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save session';
  })
  .catch(err => {
    saveStatus.textContent = 'Save failed: ' + err.message;
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save session';
  });
};

loadBtn.onclick = () => {
  const input = document.createElement('input');
  input.type  = 'file';
  input.accept = '.json';
  input.onchange = (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const session = JSON.parse(e.target.result);
        if (!session.sliceMasks && !session.pixelMasks) {
          alert('Invalid session file. Use a *_metadata.json file.');
          return;
        }
        saveSnapshot();
        sliceMasks = (session.sliceMasks || []).map(sm => ({expr: sm.expr, pixels: sm.pixels}));
        discMasks  = (session.discMasks  || []).map(dm => ({...dm}));
        pixelMasks = session.pixelMasks || {};
        updateAllPolygons();
        updateSliceList();
        updateDiscList();
        updateMaskTable();
        saveStatus.textContent = 'Loaded: ' + file.name;
      } catch (err) {
        alert('Error loading session: ' + err.message);
      }
    };
    reader.readAsText(file);
  };
  input.click();
};

// =========================================================
// Zoom / pan with zoom % display
// =========================================================
const initVBStr = '%%VIEWBOX%%';
const [ivx, ivy, ivw, ivh] = initVBStr.split(' ').map(parseFloat);
let vb = {x: ivx, y: ivy, w: ivw, h: ivh};

function getZoomPct() {
  return Math.round(ivw / vb.w * 100);
}

function updateZoomDisplay() {
  zoomPctEl.value = getZoomPct() + '%';
}

function applyVB() {
  svgEl.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  updateZoomDisplay();
}

function zoomAt(factor, cx, cy) {
  vb = {
    x: cx - (cx - vb.x) * factor,
    y: cy - (cy - vb.y) * factor,
    w: vb.w * factor,
    h: vb.h * factor,
  };
  applyVB();
}

svgEl.addEventListener('wheel', e => {
  e.preventDefault();
  const rect = svgEl.getBoundingClientRect();
  const cx = vb.x + (e.clientX - rect.left) / rect.width * vb.w;
  const cy = vb.y + (e.clientY - rect.top) / rect.height * vb.h;
  zoomAt(e.deltaY > 0 ? 1.15 : 1 / 1.15, cx, cy);
}, {passive: false});

let dragging = false, dragStart = null;

svgEl.addEventListener('mousedown', e => {
  if (e.button !== 0) return;
  dragging = true;
  dragDist = 0;
  dragStart = {x: e.clientX, y: e.clientY, vb: {...vb}};
});

window.addEventListener('mousemove', e => {
  if (!dragging) return;
  const dx = e.clientX - dragStart.x;
  const dy = e.clientY - dragStart.y;
  dragDist = Math.sqrt(dx * dx + dy * dy);
  const rect = svgEl.getBoundingClientRect();
  vb = {
    ...dragStart.vb,
    x: dragStart.vb.x - dx / rect.width * dragStart.vb.w,
    y: dragStart.vb.y - dy / rect.height * dragStart.vb.h,
  };
  applyVB();
});

window.addEventListener('mouseup', () => { dragging = false; });

document.getElementById('zoom-in').onclick = () => {
  zoomAt(1/1.3, vb.x + vb.w/2, vb.y + vb.h/2);
};
document.getElementById('zoom-out').onclick = () => {
  zoomAt(1.3, vb.x + vb.w/2, vb.y + vb.h/2);
};
document.getElementById('zoom-reset').onclick = () => {
  vb = {x: ivx, y: ivy, w: ivw, h: ivh};
  applyVB();
};

// Manual zoom % entry
zoomPctEl.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const pct = parseInt(zoomPctEl.value);
    if (isNaN(pct) || pct <= 0) { updateZoomDisplay(); return; }
    const newW = ivw * 100 / pct;
    const newH = ivh * 100 / pct;
    const cx = vb.x + vb.w / 2;
    const cy = vb.y + vb.h / 2;
    vb = { x: cx - newW/2, y: cy - newH/2, w: newW, h: newH };
    applyVB();
  }
});
zoomPctEl.addEventListener('blur', updateZoomDisplay);

updateZoomDisplay();
