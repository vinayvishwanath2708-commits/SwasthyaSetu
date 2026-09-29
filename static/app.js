/* ================================================================
   CareCost — app.js
   Mobile-first SPA logic: i18n, form, API calls, map, results
   ================================================================ */

'use strict';

// ── State ───────────────────────────────────────────────────────
let i18n = {};
let currentLang = 'en';
let isDark = false;
let procedures = [];
let selectedProcedureId = null;
let lastEstimate = null;
let map = null;
let markerGroup = null;

// ── Boot ────────────────────────────────────────────────────────
(async function init() {
  await loadI18n();
  await loadProcedures();
  applyI18n();
  setupProcedureSearch();
  // Restore dark preference
  if (localStorage.getItem('carecost-theme') === 'dark') toggleTheme();
})();

// ── i18n ────────────────────────────────────────────────────────
async function loadI18n() {
  try {
    const res = await fetch('/static/i18n.json');
    i18n = await res.json();
  } catch (e) {
    console.error('Failed to load i18n', e);
    i18n = { en: {} };
  }
}

function t(key) {
  return (i18n[currentLang] && i18n[currentLang][key]) || (i18n['en'] && i18n['en'][key]) || key;
}

function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll('[data-i18n-content]').forEach(el => {
    el.textContent = t(el.dataset.i18nContent);
  });
  // Update html lang
  document.documentElement.lang = currentLang;
}

window.setLang = function(lang) {
  currentLang = lang;
  ['en', 'te', 'hi'].forEach(l => {
    document.getElementById('lang-' + l).classList.toggle('active', l === lang);
  });
  applyI18n();
  // Re-render results if visible
  if (lastEstimate) renderResults(lastEstimate);
};

// ── Theme ────────────────────────────────────────────────────────
window.toggleTheme = function() {
  isDark = !isDark;
  document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
  const btn = document.getElementById('theme-toggle');
  btn.innerHTML = isDark
    ? '☀️ <span data-i18n="light_mode">' + t('light_mode') + '</span>'
    : '🌙 <span data-i18n="dark_mode">' + t('dark_mode') + '</span>';
  localStorage.setItem('carecost-theme', isDark ? 'dark' : 'light');
  // Update map tiles for dark mode
  if (map) {
    map.eachLayer(l => { if (l._url) map.removeLayer(l); });
    L.tileLayer(
      isDark
        ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
        : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      { maxZoom: 18, attribution: '© OpenStreetMap contributors' }
    ).addTo(map);
  }
};

// ── Procedures autocomplete ──────────────────────────────────────
async function loadProcedures() {
  try {
    const res = await fetch('/api/procedures');
    procedures = await res.json();
  } catch (e) {
    console.error('Failed to load procedures', e);
  }
}

function setupProcedureSearch() {
  const input = document.getElementById('procedure-search');
  const list = document.getElementById('procedure-list');
  let selectedIndex = -1;

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    selectedProcedureId = null;
    document.getElementById('selected-procedure-id').value = '';
    if (!q) { closeList(); return; }

    const matches = procedures.filter(p =>
      p.name.toLowerCase().includes(q) ||
      (p.keywords || '').toLowerCase().includes(q)
    );
    renderAutocomplete(matches);
  });

  input.addEventListener('keydown', e => {
    const items = list.querySelectorAll('.autocomplete-item');
    if (e.key === 'ArrowDown') {
      selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
      items.forEach((it, i) => it.classList.toggle('selected', i === selectedIndex));
      e.preventDefault();
    } else if (e.key === 'ArrowUp') {
      selectedIndex = Math.max(selectedIndex - 1, 0);
      items.forEach((it, i) => it.classList.toggle('selected', i === selectedIndex));
      e.preventDefault();
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      items[selectedIndex]?.click();
      e.preventDefault();
    } else if (e.key === 'Escape') {
      closeList();
    }
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.search-wrapper')) closeList();
  });

  function renderAutocomplete(matches) {
    list.innerHTML = '';
    selectedIndex = -1;
    if (!matches.length) { closeList(); return; }
    matches.forEach(p => {
      const li = document.createElement('li');
      li.className = 'autocomplete-item';
      li.setAttribute('role', 'option');
      li.setAttribute('id', 'opt-' + p.procedure_id);
      li.innerHTML = `<span>${p.name}</span><span class="cat">${p.category}</span>`;
      li.onclick = () => {
        input.value = p.name;
        selectedProcedureId = p.procedure_id;
        document.getElementById('selected-procedure-id').value = p.procedure_id;
        input.setAttribute('aria-expanded', 'false');
        closeList();
      };
      list.appendChild(li);
    });
    list.classList.add('open');
    input.setAttribute('aria-expanded', 'true');
  }

  function closeList() {
    list.classList.remove('open');
    input.setAttribute('aria-expanded', 'false');
  }
}

// ── Voice input ──────────────────────────────────────────────────
window.startVoice = function() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert('Voice input is not supported in your browser. Try Chrome on Android.');
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = currentLang === 'hi' ? 'hi-IN' : currentLang === 'te' ? 'te-IN' : 'en-IN';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  const btn = document.getElementById('mic-btn');
  btn.classList.add('listening');

  recognition.onresult = e => {
    const transcript = e.results[0][0].transcript;
    const input = document.getElementById('procedure-search');
    input.value = transcript;
    input.dispatchEvent(new Event('input'));
    btn.classList.remove('listening');
  };
  recognition.onerror = () => btn.classList.remove('listening');
  recognition.onend = () => btn.classList.remove('listening');
  recognition.start();
};

// ── Geolocation ──────────────────────────────────────────────────
window.getLocation = function() {
  const status = document.getElementById('location-status');
  if (!navigator.geolocation) { status.textContent = 'Geolocation not supported'; return; }

  status.textContent = '📡 Locating…';
  navigator.geolocation.getCurrentPosition(
    pos => {
      document.getElementById('user-lat').value = pos.coords.latitude;
      document.getElementById('user-lng').value = pos.coords.longitude;
      status.textContent = `✅ ${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)}`;
    },
    err => {
      status.textContent = '⚠️ Could not get location — using city centre';
    }
  );
};

// ── Form submission ──────────────────────────────────────────────
window.submitEstimate = async function() {
  clearError();
  const procedureId = selectedProcedureId;
  const city = document.getElementById('city-select').value;
  const hasSchemeCard = document.getElementById('scheme-card').checked;
  const insuranceCover = parseFloat(document.getElementById('insurance-cover').value) || 0;
  const userLat = parseFloat(document.getElementById('user-lat').value) || null;
  const userLng = parseFloat(document.getElementById('user-lng').value) || null;

  if (!procedureId) { showError(t('error_select_procedure')); return; }
  if (!city) { showError(t('error_select_city')); return; }

  const btn = document.getElementById('estimate-btn');
  btn.disabled = true;
  btn.classList.add('loading');

  try {
    const res = await fetch('/api/estimate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        procedure_id: procedureId,
        city,
        has_scheme_card: hasSchemeCard,
        insurance_cover_left: insuranceCover,
        user_lat: userLat,
        user_lng: userLng,
      }),
    });
    const data = await res.json();
    if (data.error) { showError(data.error); return; }
    lastEstimate = { ...data, city, procedureId };
    renderResults(data);
    showResults();
  } catch (e) {
    showError('Network error. Please check your connection and try again.');
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
  }
};

// ── Results renderer ─────────────────────────────────────────────
function renderResults(data) {
  renderCostRange(data.cost_range, data.is_demo);
  renderBestOption(data.best_option, data.savings_vs_expensive);
  renderMap(data.hospitals, data.best_option);
  renderHospitalCards(data.hospitals);
  renderAssumptions(data.assumptions);
}

function renderCostRange(cr, isDemo) {
  if (!cr || !cr.overall_low) return;
  const low = cr.overall_low;
  const high = cr.overall_high;
  const mid = cr.overall_mid;

  document.getElementById('overall-range-text').textContent =
    `₹${fmt(low)} – ₹${fmt(high)}`;
  document.getElementById('range-sub-text').textContent =
    `Government to corporate hospitals, city tier ${cr.city_tier || '—'}`;

  // Position mid marker
  const pct = ((mid - low) / (high - low)) * 100;
  document.getElementById('mid-marker').style.left = `${pct.toFixed(1)}%`;

  // Demo badge
  document.getElementById('demo-badge-range').style.display = isDemo ? 'inline-flex' : 'none';
}

function renderBestOption(best, savings) {
  if (!best) { document.getElementById('best-option-card').style.display = 'none'; return; }
  document.getElementById('best-option-card').style.display = '';
  document.getElementById('best-hospital-name').textContent = best.name;
  document.getElementById('best-oop-amount').textContent = '₹' + fmt(best.out_of_pocket);

  // Stacked bar
  const total = best.estimated_price || 1;
  const schemePct = (best.scheme_covered / total) * 100;
  const insPct = (best.insurance_covered / total) * 100;
  const oopPct = Math.max(0, 100 - schemePct - insPct);

  const barScheme = document.getElementById('bar-scheme');
  const barIns = document.getElementById('bar-insurance');
  const barOop = document.getElementById('bar-oop');

  barScheme.style.width = schemePct + '%';
  barScheme.textContent = schemePct > 8 ? t('scheme_covers') : '';
  barIns.style.width = insPct + '%';
  barIns.textContent = insPct > 8 ? t('insurance_covers') : '';
  barOop.style.width = oopPct + '%';
  barOop.textContent = oopPct > 8 ? t('you_pay') : '';

  // Savings
  const sp = document.getElementById('savings-pill');
  if (savings > 0) {
    sp.style.display = 'inline-flex';
    document.getElementById('savings-text').textContent =
      `${t('savings_label')}: ₹${fmt(savings)}`;
  } else {
    sp.style.display = 'none';
  }
}

function renderMap(hospitals, best) {
  const centre = hospitals.length > 0
    ? [hospitals[0].lat, hospitals[0].lng]
    : [17.385, 78.4867];

  // Init or reset map
  if (!map) {
    map = L.map('map', { zoomControl: true }).setView(centre, 12);
    L.tileLayer(
      isDark
        ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
        : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      { maxZoom: 18, attribution: '© OpenStreetMap contributors' }
    ).addTo(map);
    markerGroup = L.layerGroup().addTo(map);
  } else {
    markerGroup.clearLayers();
  }

  const typeColors = { government: '#22c55e', trust: '#3b82f6', private: '#f59e0b', corporate: '#ec4899' };

  hospitals.forEach((h, i) => {
    const color = typeColors[h.type] || '#6366f1';
    const isBest = best && h.hospital_id === best.hospital_id;
    const size = isBest ? 14 : 10;

    const icon = L.divIcon({
      className: '',
      html: `<div style="
        width:${size}px;height:${size}px;border-radius:50%;
        background:${color};border:2.5px solid #fff;
        box-shadow:0 2px 6px rgba(0,0,0,.35);
        ${isBest ? 'outline:3px solid ' + color + ';outline-offset:2px;' : ''}
      "></div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });

    const marker = L.marker([h.lat, h.lng], { icon });
    marker.bindPopup(`
      <strong>${h.name}</strong><br/>
      ${capitalize(h.type)} · ${h.distance_km} km<br/>
      <b>Est. price:</b> ₹${fmt(h.estimated_price)}<br/>
      <b>${t('you_pay')}:</b> ₹${fmt(h.out_of_pocket)}
      ${h.is_demo ? '<br/><small>⚠️ Demo data</small>' : ''}
    `);
    markerGroup.addLayer(marker);
  });

  // Fit bounds
  if (hospitals.length > 0) {
    const latLngs = hospitals.map(h => [h.lat, h.lng]);
    map.fitBounds(L.latLngBounds(latLngs).pad(0.15));
  }

  // Force resize after reveal
  setTimeout(() => map.invalidateSize(), 300);
}

function renderHospitalCards(hospitals) {
  const container = document.getElementById('hospital-list');
  if (!hospitals.length) {
    container.innerHTML = `<p style="color:var(--text-muted);text-align:center;">${t('no_hospitals')}</p>`;
    return;
  }

  const typeColors = { government: 'government', trust: 'trust', private: 'private', corporate: 'corporate' };

  container.innerHTML = hospitals.map((h, i) => {
    const isBest = i === 0;
    const tags = buildTagsHTML(h);
    return `
      <div class="hospital-card ${isBest ? 'best-card' : ''}" role="article" aria-label="${h.name}">
        <div class="hosp-name-row">
          <span class="rank-badge" aria-label="Rank ${i + 1}">${i + 1}</span>
          <span class="hosp-name">${h.name}</span>
          <span class="hosp-type-badge type-${typeColors[h.type] || 'private'}">${capitalize(h.type)}</span>
        </div>
        <div class="hosp-price-row">
          <div class="price-item">
            <div class="value">₹${fmt(h.estimated_price)}</div>
            <div>${t('col_est_price')}</div>
          </div>
          ${h.scheme_covered > 0 ? `
          <div class="price-item">
            <div class="value" style="color:var(--brand-success);">−₹${fmt(h.scheme_covered)}</div>
            <div>${t('col_scheme')}</div>
          </div>` : ''}
          ${h.insurance_covered > 0 ? `
          <div class="price-item">
            <div class="value" style="color:var(--brand-accent);">−₹${fmt(h.insurance_covered)}</div>
            <div>${t('col_insurance')}</div>
          </div>` : ''}
          <div class="price-item oop">
            <div class="value">₹${fmt(h.out_of_pocket)}</div>
            <div>${t('col_you_pay')}</div>
          </div>
          <div class="price-item">
            <div class="value">${h.distance_km} km</div>
            <div>${t('col_distance')}</div>
          </div>
        </div>
        <div class="hosp-tags">${tags}</div>
      </div>
    `;
  }).join('');
}

function buildTagsHTML(h) {
  const tags = [];
  if (h.tags && h.tags.includes('scheme_hospital')) {
    tags.push(`<span class="tag tag-scheme">🏛️ ${t('tag_scheme')}</span>`);
  }
  if (h.cashless_insurance) {
    tags.push(`<span class="tag tag-cashless">💳 ${t('tag_cashless')}</span>`);
  }
  if (h.nabh) {
    tags.push(`<span class="tag tag-nabh">⭐ ${t('tag_nabh')}</span>`);
  }
  tags.push(`<span class="tag tag-distance">📍 ${h.distance_km} km</span>`);
  if (h.is_demo) {
    tags.push(`<span class="tag tag-demo">⚠️ ${t('tag_demo')}</span>`);
  }
  return tags.join('');
}

function renderAssumptions(assumptions) {
  const list = document.getElementById('assumptions-list');
  list.innerHTML = (assumptions || []).map(a => `<li>${a}</li>`).join('');
}

// ── Quote validator ──────────────────────────────────────────────
window.validateQuote = async function() {
  const amount = parseFloat(document.getElementById('quote-amount').value);
  if (!lastEstimate || !lastEstimate.procedureId) {
    alert(t('error_select_procedure'));
    return;
  }
  if (!amount || amount <= 0) return;

  const btn = document.getElementById('validate-btn');
  btn.disabled = true;

  try {
    const res = await fetch('/api/validate-quote', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        procedure_id: lastEstimate.procedureId,
        city: lastEstimate.city,
        quote_amount: amount,
      }),
    });
    const data = await res.json();
    renderVerdict(data);
  } catch (e) {
    console.error(e);
  } finally {
    btn.disabled = false;
  }
};

function renderVerdict(data) {
  const box = document.getElementById('verdict-box');
  const verdictKey = 'verdict_' + data.verdict;
  const verdictLabel = t(verdictKey);

  const verdictIcons = {
    below_range: '🔵',
    fair: '✅',
    above_range: '⚠️',
    far_above: '🚨',
    unknown: 'ℹ️',
  };

  box.innerHTML = `
    <div class="verdict-box verdict-${data.verdict}" role="status">
      <div class="verdict-title">${verdictIcons[data.verdict] || 'ℹ️'} ${verdictLabel}</div>
      ${data.range_low ? `<div style="font-size:.82rem;color:var(--text-muted);margin-bottom:.4rem;">
        Range: ₹${fmt(data.range_low)} – ₹${fmt(data.range_high)}
      </div>` : ''}
      <div class="verdict-text">${data.suggestion}</div>
    </div>
  `;
}

// ── UI helpers ───────────────────────────────────────────────────
function showResults() {
  document.getElementById('form-section').style.display = 'none';
  document.getElementById('results-section').style.display = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

window.showForm = function() {
  document.getElementById('results-section').style.display = 'none';
  document.getElementById('form-section').style.display = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

function showError(msg) {
  const el = document.getElementById('form-error');
  el.innerHTML = `<div class="alert alert-error">${msg}</div>`;
  el.style.display = '';
}

function clearError() {
  const el = document.getElementById('form-error');
  el.style.display = 'none';
  el.innerHTML = '';
}

function fmt(n) {
  if (n == null || isNaN(n)) return '0';
  return Number(n).toLocaleString('en-IN');
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}
