// =========================================================
// Data (injected by Python)
// =========================================================
const NPIX      = %%NPIX%%;
const PIX_LON   = %%PIX_LON%%;
const PIX_LAT   = %%PIX_LAT%%;
const PIX_FILL  = %%PIX_FILL%%;
const NAN_COLOR = '%%NAN_COLOR%%';
const MASK_FILL = '%%MASK_FILL%%';
const LON_NAME  = '%%LON_NAME%%';
const LAT_NAME  = '%%LAT_NAME%%';
const NSIDE     = %%NSIDE%%;

// Base64-encoded Float32 raw map values for client-side smoothing
const MAP_VALUES_B64 = '%%MAP_VALUES_B64%%';

// Decode raw map values
function b64ToFloat32(b64) {
  const binary = atob(b64);
  const buf = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) buf[i] = binary.charCodeAt(i);
  return new Float32Array(buf.buffer);
}
const MAP_VALUES = b64ToFloat32(MAP_VALUES_B64);

// Colormap LUT (256 entries)
const LUT = %%LUT%%;

// =========================================================
// Mutable state
// =========================================================
let currentFill = PIX_FILL.slice();
let showSmooth  = false;
let smoothFill  = null;  // computed on refresh
let sliceMasks  = [];    // [{expr, pixels: []}]
let pixelMasks  = {};    // {idx: true}
let history     = [];
let future      = [];

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

// Index polygons by pixel index
const polyElems = new Array(NPIX).fill(null);
for (const el of pixLayer.querySelectorAll('polygon')) {
  polyElems[+el.dataset.idx] = el;
}

let hoveredIdx  = -1;
let selectedIdx = -1;
let dragDist    = 0;

// =========================================================
// Mask helpers
// =========================================================
function getMaskedSet() {
  const s = new Set(Object.keys(pixelMasks).map(Number));
  for (const sm of sliceMasks) {
    for (const idx of sm.pixels) s.add(idx);
  }
  return s;
}

function effectiveColor(i, maskedSet) {
  if (maskedSet.has(i)) return MASK_FILL;
  if (showSmooth && smoothFill) return smoothFill[i] || currentFill[i];
  return currentFill[i];
}

function updateAllPolygons() {
  const masked = getMaskedSet();
  for (let i = 0; i < NPIX; i++) {
    const el = polyElems[i];
    if (!el) continue;
    const c = effectiveColor(i, masked);
    el.setAttribute('fill', c);
    el.setAttribute('stroke', c);
  }
}

// =========================================================
// Undo / redo
// =========================================================
function snapshotState() {
  const smSerial = sliceMasks.map(sm => ({
    expr: sm.expr, pixels: Array.from(sm.pixels)
  }));
  return JSON.stringify({sliceMasks: smSerial, pixelMasks});
}

function saveSnapshot() {
  history.push(snapshotState());
  future = [];
  updateUndoRedoButtons();
}

function restoreSnapshot(snap) {
  const s    = JSON.parse(snap);
  sliceMasks = s.sliceMasks.map(sm => ({expr: sm.expr, pixels: sm.pixels}));
  pixelMasks = s.pixelMasks;
  updateAllPolygons();
  updateSliceList();
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

document.addEventListener('keydown', e => {
  if (e.key === 'z' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    if (e.shiftKey) redo(); else undo();
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
};

updateSmoothBtn();

// Refresh: recompute smooth using current mask
refreshBtn.onclick = () => {
  if (!showSmooth) return;
  refreshBtn.disabled = true;
  refreshBtn.textContent = 'Computing...';
  // Use setTimeout to let the UI update before blocking
  setTimeout(() => {
    computeSmooth();
    updateAllPolygons();
    refreshBtn.disabled = false;
    refreshBtn.textContent = 'Refresh smooth';
  }, 50);
};

function computeSmooth() {
  // Client-side running average using pixel neighbours
  // This is a simplified version: for each unmasked pixel, average
  // the values of unmasked neighbours within a fixed angular radius.
  const maskedSet = getMaskedSet();
  const steradians = 1.0;
  const radius = Math.acos(1 - steradians / (2 * Math.PI));

  // Convert pixel positions to unit vectors
  const vecs = new Array(NPIX);
  for (let i = 0; i < NPIX; i++) {
    const lon = PIX_LON[i] * Math.PI / 180;
    const lat = PIX_LAT[i] * Math.PI / 180;
    const cosLat = Math.cos(lat);
    vecs[i] = [cosLat * Math.cos(lon), cosLat * Math.sin(lon), Math.sin(lat)];
  }

  const cosRadius = Math.cos(radius);
  smoothFill = new Array(NPIX);

  // Build list of unmasked pixels for efficiency
  const unmasked = [];
  for (let i = 0; i < NPIX; i++) {
    if (!maskedSet.has(i)) unmasked.push(i);
  }
  const isUnmasked = new Uint8Array(NPIX);
  for (const i of unmasked) isUnmasked[i] = 1;

  // Compute valid range for LUT mapping
  let vmin = Infinity, vmax = -Infinity;
  for (const i of unmasked) {
    const v = MAP_VALUES[i];
    if (isFinite(v)) {
      if (v < vmin) vmin = v;
      if (v > vmax) vmax = v;
    }
  }
  const rng = vmax > vmin ? vmax - vmin : 1;

  function hx(n) { return n.toString(16).padStart(2, '0'); }

  for (const i of unmasked) {
    const vi = vecs[i];
    let sum = 0, cnt = 0;
    for (const j of unmasked) {
      const vj = vecs[j];
      const dot = vi[0]*vj[0] + vi[1]*vj[1] + vi[2]*vj[2];
      if (dot >= cosRadius) {
        const v = MAP_VALUES[j];
        if (isFinite(v)) { sum += v; cnt++; }
      }
    }
    if (cnt > 0) {
      const avg = sum / cnt;
      const t = Math.min(255, Math.max(0, Math.round(255 * (avg - vmin) / rng)));
      const [r, g, b] = LUT[t];
      smoothFill[i] = '#' + hx(r) + hx(g) + hx(b);
    } else {
      smoothFill[i] = NAN_COLOR;
    }
  }

  // Masked pixels keep mask color (handled by effectiveColor)
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
    LAT_NAME + ': ' + (+el.dataset.lat).toFixed(2) + '\u00b0';
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
  const el = e.target.closest('polygon');
  if (!el) return;
  const i = +el.dataset.idx;
  const masked = getMaskedSet();

  if (masked.has(i)) {
    if (pixelMasks[i]) {
      saveSnapshot();
      delete pixelMasks[i];
      const c = effectiveColor(i, getMaskedSet());
      el.setAttribute('fill', c); el.setAttribute('stroke', c);
      updateMaskTable();
      if (selectedIdx === i) { selectedIdx = -1; renderSelInfo(); }
    }
  } else if (selectedIdx === i) {
    saveSnapshot();
    el.classList.remove('selected');
    pixelMasks[i] = true;
    el.setAttribute('fill', MASK_FILL); el.setAttribute('stroke', MASK_FILL);
    selectedIdx = -1;
    renderSelInfo();
    updateMaskTable();
  } else {
    if (selectedIdx !== -1 && polyElems[selectedIdx])
      polyElems[selectedIdx].classList.remove('selected');
    selectedIdx = i;
    el.classList.add('selected');
    renderSelInfo();
  }
});

function renderSelInfo() {
  if (selectedIdx === -1) {
    selInfo.textContent = '';
  } else {
    selInfo.textContent =
      '[sel] ' + LON_NAME + ': ' + PIX_LON[selectedIdx].toFixed(2) + '\u00b0  ' +
      LAT_NAME + ': ' + PIX_LAT[selectedIdx].toFixed(2) + '\u00b0';
  }
}

// =========================================================
// Slice expression parser
// =========================================================
function parseSliceExpr(expr) {
  expr = expr.trim();
  const latVars = ['dec', 'lat', 'b'];
  const lonVars = ['lon', 'ra', 'l'];
  let varName = null, isLat = false;
  for (const v of [...latVars, ...lonVars]) {
    if (new RegExp('(?<![a-z])' + v + '(?![a-z])').test(expr)) {
      varName = v;
      isLat   = latVars.includes(v);
      break;
    }
  }
  if (!varName) return null;

  const values = isLat ? PIX_LAT : PIX_LON;

  let useAbs    = false;
  let cleanExpr = expr;
  if (expr.includes('|')) {
    useAbs    = true;
    cleanExpr = expr.replace(/\|[^|]+\|/g, varName);
  }

  const ops = {
    '<':  (a, b) => a <  b,
    '<=': (a, b) => a <= b,
    '>':  (a, b) => a >  b,
    '>=': (a, b) => a >= b,
  };

  const two = cleanExpr.match(
    /^(-?[\d.]+)\s*([<>]=?)\s*\w+\s*([<>]=?)\s*(-?[\d.]+)$/
  );
  if (two) {
    const lv = parseFloat(two[1]), lop = two[2], rop = two[3], rv = parseFloat(two[4]);
    const result = [];
    for (let i = 0; i < NPIX; i++) {
      const v = useAbs ? Math.abs(values[i]) : values[i];
      if (ops[lop](lv, v) && ops[rop](v, rv)) result.push(i);
    }
    return result;
  }

  const one_vf = cleanExpr.match(/^\w+\s*([<>]=?)\s*(-?[\d.]+)$/);
  if (one_vf) {
    const op = one_vf[1], num = parseFloat(one_vf[2]);
    const result = [];
    for (let i = 0; i < NPIX; i++) {
      const v = useAbs ? Math.abs(values[i]) : values[i];
      if (ops[op](v, num)) result.push(i);
    }
    return result;
  }

  const one_nf = cleanExpr.match(/^(-?[\d.]+)\s*([<>]=?)\s*\w+$/);
  if (one_nf) {
    const num = parseFloat(one_nf[1]), op = one_nf[2];
    const result = [];
    for (let i = 0; i < NPIX; i++) {
      const v = useAbs ? Math.abs(values[i]) : values[i];
      if (ops[op](num, v)) result.push(i);
    }
    return result;
  }

  return null;
}

function applySlice(expr) {
  const pixels = parseSliceExpr(expr);
  if (pixels === null) {
    alert('Could not parse: ' + expr);
    return;
  }
  saveSnapshot();
  sliceMasks.push({expr, pixels});
  updateAllPolygons();
  updateSliceList();
}

function updateSliceList() {
  const div = document.getElementById('slice-list');
  div.innerHTML = '';
  sliceMasks.forEach((sm, idx) => {
    const row  = document.createElement('div');
    row.className = 'slice-row';
    const span = document.createElement('span');
    span.textContent = sm.expr;
    const btn  = document.createElement('button');
    btn.textContent = '\u00d7';
    btn.className   = 'remove-btn';
    btn.onclick = () => {
      saveSnapshot();
      sliceMasks.splice(idx, 1);
      updateAllPolygons();
      updateSliceList();
    };
    row.appendChild(span);
    row.appendChild(btn);
    div.appendChild(row);
  });
}

document.getElementById('apply-slice-btn').onclick = () => {
  const ta   = document.getElementById('slice-input');
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
// Pixel mask table
// =========================================================
function updateMaskTable() {
  const div  = document.getElementById('pixel-table');
  div.innerHTML = '';
  const keys = Object.keys(pixelMasks).map(Number).sort((a, b) => a - b);
  if (!keys.length) {
    const note = document.createElement('div');
    note.style.cssText = 'color:#555;font-size:11px;padding:2px 0';
    note.textContent = 'No masked pixels';
    div.appendChild(note);
    return;
  }
  keys.forEach(i => {
    const row  = document.createElement('div');
    row.className = 'mask-row';
    const span = document.createElement('span');
    span.textContent =
      LON_NAME + '=' + PIX_LON[i].toFixed(1) + '\u00b0 ' +
      LAT_NAME + '=' + PIX_LAT[i].toFixed(1) + '\u00b0';
    const btn = document.createElement('button');
    btn.textContent = '\u00d7';
    btn.className   = 'remove-btn';
    btn.onclick = () => {
      saveSnapshot();
      delete pixelMasks[i];
      const c = effectiveColor(i, getMaskedSet());
      if (polyElems[i]) {
        polyElems[i].setAttribute('fill', c);
        polyElems[i].setAttribute('stroke', c);
      }
      updateMaskTable();
    };
    row.appendChild(span);
    row.appendChild(btn);
    div.appendChild(row);
  });
}

updateMaskTable();

// =========================================================
// Save / Load session
// =========================================================
saveBtn.onclick = () => {
  const session = {
    nside: NSIDE,
    npix: NPIX,
    sliceMasks: sliceMasks.map(sm => ({expr: sm.expr, pixels: Array.from(sm.pixels)})),
    pixelMasks: pixelMasks,
    timestamp: new Date().toISOString(),
  };
  const json = JSON.stringify(session, null, 2);
  const blob = new Blob([json], {type: 'application/json'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  const ts   = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  a.href     = url;
  a.download = 'healpix_mask_' + ts + '_session.json';
  a.click();
  URL.revokeObjectURL(url);
  saveStatus.textContent = 'Saved: ' + a.download;

  // Also generate and download the boolean mask as a JSON array
  const maskArr = new Array(NPIX).fill(true);
  const maskedSet = getMaskedSet();
  for (const idx of maskedSet) maskArr[idx] = false;
  const maskBlob = new Blob([JSON.stringify(maskArr)], {type: 'application/json'});
  const maskUrl  = URL.createObjectURL(maskBlob);
  const a2       = document.createElement('a');
  a2.href        = maskUrl;
  a2.download    = 'healpix_mask_' + ts + '.json';
  a2.click();
  URL.revokeObjectURL(maskUrl);
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
          alert('Invalid session file.');
          return;
        }
        // Save current state as backup
        saveSnapshot();
        // Restore
        sliceMasks = (session.sliceMasks || []).map(sm => ({
          expr: sm.expr, pixels: sm.pixels
        }));
        pixelMasks = session.pixelMasks || {};
        updateAllPolygons();
        updateSliceList();
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
// Zoom / pan
// =========================================================
const initVBStr = '%%VIEWBOX%%';
const [ivx, ivy, ivw, ivh] = initVBStr.split(' ').map(parseFloat);
let vb = {x: ivx, y: ivy, w: ivw, h: ivh};

function applyVB() {
  svgEl.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
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
  const rect   = svgEl.getBoundingClientRect();
  const cx     = vb.x + (e.clientX - rect.left) / rect.width  * vb.w;
  const cy     = vb.y + (e.clientY - rect.top)  / rect.height * vb.h;
  zoomAt(e.deltaY > 0 ? 1.15 : 1 / 1.15, cx, cy);
}, {passive: false});

let dragging = false, dragStart = null;

svgEl.addEventListener('mousedown', e => {
  if (e.button !== 0) return;
  dragging  = true;
  dragDist  = 0;
  dragStart = {x: e.clientX, y: e.clientY, vb: {...vb}};
});

window.addEventListener('mousemove', e => {
  if (!dragging) return;
  const dx  = e.clientX - dragStart.x;
  const dy  = e.clientY - dragStart.y;
  dragDist  = Math.sqrt(dx * dx + dy * dy);
  const rect = svgEl.getBoundingClientRect();
  vb = {
    ...dragStart.vb,
    x: dragStart.vb.x - dx / rect.width  * dragStart.vb.w,
    y: dragStart.vb.y - dy / rect.height * dragStart.vb.h,
  };
  applyVB();
});

window.addEventListener('mouseup', () => { dragging = false; });

document.getElementById('zoom-in').onclick = () => {
  zoomAt(1 / 1.3, vb.x + vb.w / 2, vb.y + vb.h / 2);
};
document.getElementById('zoom-out').onclick = () => {
  zoomAt(1.3, vb.x + vb.w / 2, vb.y + vb.h / 2);
};
document.getElementById('zoom-reset').onclick = () => {
  vb = {x: ivx, y: ivy, w: ivw, h: ivh};
  applyVB();
};
