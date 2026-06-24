let allDetections = [];

const freqLabels = {
  hour: 'Hourly',
  day: 'Daily',
  month: 'Monthly'
};

const SPECIES_COLORS = {
  'American Crow': '#1a1a1a',        // glossy black
  'Lesser Goldfinch': '#e8c64a',     // bright yellow-gold
  'House Finch': '#a13d4c',          // dusty rose-red (male's head/breast)
  'Song Sparrow': '#7a6248',         // streaky brown
  'Chipping Sparrow': '#a8763e',     // rufous cap, warm brown
  'Dark-eyed Junco': '#5c5c5c',      // slate gray
  'Evening Grosbeak': '#d4a72c',     // mustard yellow with black/white wings
  'Varied Thrush': '#d2691e',        // burnt orange
  'Canada Goose': '#4a3c2e'          // dark brown body
};
const DEFAULT_COLOR = '#4a90d9';

function getColor(species) {
  return SPECIES_COLORS[species] || DEFAULT_COLOR;
}

fetch('data/detections.json')
  .then(response => response.json())
  .then(data => {
    allDetections = data.map(d => ({
      species: d.species.commonName,
      timestamp: new Date(d.timestamp)
    }));

    populateSpeciesDropdown(allDetections);
    setDefaultDateRange(allDetections);
    renderView();
  });

function parseLocalDate(dateStr) {
  const [year, month, day] = dateStr.split('-').map(Number);
  return new Date(year, month - 1, day);  // month is 0-indexed in JS Date
}

function populateSpeciesDropdown(detections) {
  const counts = {};
  detections.forEach(d => {
    counts[d.species] = (counts[d.species] || 0) + 1;
  });

  const sortedSpecies = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);

  const select = document.getElementById('species-select');
  sortedSpecies.forEach(species => {
    const opt = document.createElement('option');
    opt.value = species;
    opt.textContent = `${species} (${counts[species]})`;
    select.appendChild(opt);
  });
}

function setDefaultDateRange(detections) {
  const timestamps = detections.map(d => d.timestamp);
  const minDate = new Date(Math.min(...timestamps));
  const maxDate = new Date(Math.max(...timestamps));

  document.getElementById('from-date').value = minDate.toISOString().split('T')[0];
  document.getElementById('to-date').value = maxDate.toISOString().split('T')[0];
}

function getBucketKey(date, freq) {
  if (freq === 'hour') {
    return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ${pad(date.getHours())}:00`;
  } else if (freq === 'day') {
    return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
  } else {
    return `${date.getFullYear()}-${pad(date.getMonth()+1)}`;
  }
}

function pad(n) {
  return n.toString().padStart(2, '0');
}

function getSortedDays(detections) {
  const daySet = new Set(detections.map(d => getBucketKey(d.timestamp, 'day')));
  return Array.from(daySet).sort();
}

// ---- View switching ----

let trendFromDate = null;
let trendToDate = null;

function renderView() {
  const view = document.getElementById('view-select').value;
  const chartWrapper = document.getElementById('chart-wrapper');
  const deltaDisplay = document.getElementById('delta-display');
  const trendControls = document.getElementById('trend-only-controls');

  if (view === 'trend') {
    chartWrapper.style.display = 'block';
    deltaDisplay.style.display = 'none';
    trendControls.style.display = 'block';

    // Restore the Trend view's own date range, if we've saved one
    if (trendFromDate && trendToDate) {
      document.getElementById('from-date').value = trendFromDate;
      document.getElementById('to-date').value = trendToDate;
    }

    drawChart();
  } else if (view === 'today') {
    // Save whatever's currently in the date fields, in case it's the Trend range
    trendFromDate = document.getElementById('from-date').value;
    trendToDate = document.getElementById('to-date').value;

    chartWrapper.style.display = 'block';
    deltaDisplay.style.display = 'none';
    trendControls.style.display = 'none';

    const days = getSortedDays(allDetections);
    const mostRecent = days[days.length - 1];
    document.getElementById('from-date').value = mostRecent;
    document.getElementById('to-date').value = mostRecent;

    drawTodayChart();
  } else if (view === 'delta') {
    chartWrapper.style.display = 'none';
    deltaDisplay.style.display = 'block';
    trendControls.style.display = 'none';
    renderDelta();
  }
}

function refreshCurrentView() {
  const view = document.getElementById('view-select').value;
  if (view === 'trend') drawChart();
  else if (view === 'today') drawTodayChart();
  else if (view === 'delta') renderDelta();
}

// ---- Trend chart ----

function drawChart() {
  const species = document.getElementById('species-select').value;
  const freq = document.getElementById('freq-select').value;
  const fromDate = parseLocalDate(document.getElementById('from-date').value);
  const toDate = parseLocalDate(document.getElementById('to-date').value);
  toDate.setHours(23, 59, 59);

  const filtered = allDetections.filter(d => {
    const inRange = d.timestamp >= fromDate && d.timestamp <= toDate;
    const speciesMatch = species === '__all__' || d.species === species;
    return inRange && speciesMatch;
  });

  const buckets = {};
  filtered.forEach(d => {
    const key = getBucketKey(d.timestamp, freq);
    buckets[key] = (buckets[key] || 0) + 1;
  });

  const sortedKeys = Object.keys(buckets).sort();
  const xValues = sortedKeys;
  const yValues = sortedKeys.map(k => buckets[k]);

  const title = species === '__all__'
    ? `All species — ${freqLabels[freq]} detections`
    : `${species} — ${freqLabels[freq]} detections`;

  Plotly.newPlot('chart', [{
    x: xValues,
    y: yValues,
    type: 'bar'
  }], {
    title: title,
    xaxis: { title: freqLabels[freq] },
    yaxis: { title: 'Detections' },
    autosize: true,
    dragmode: false
  });

  window.dispatchEvent(new Event('resize'));
}

// ---- Today's Species (horizontal bar) ----

function drawTodayChart() {
  const fromDate = parseLocalDate(document.getElementById('from-date').value);
  const toDate = parseLocalDate(document.getElementById('to-date').value);
  toDate.setHours(23, 59, 59);

  const filtered = allDetections.filter(d => d.timestamp >= fromDate && d.timestamp <= toDate);

  const counts = {};
  filtered.forEach(d => {
    counts[d.species] = (counts[d.species] || 0) + 1;
  });

  const sorted = Object.entries(counts).sort((a, b) => a[1] - b[1]);

  Plotly.newPlot('chart', [{
    x: sorted.map(s => s[1]),
    y: sorted.map(s => s[0]),
    type: 'bar',
    orientation: 'h',
    marker: { color: sorted.map(s => getColor(s[0])) }
  }], {
    title: 'Species Detected',
    xaxis: { title: 'Detections' },
    autosize: true,
    dragmode: false,
    margin: { l: 150 }
  });

  window.dispatchEvent(new Event('resize'));
}

// ---- Yesterday vs Today delta ----

function renderDelta() {
  const days = getSortedDays(allDetections);
  const today = days[days.length - 1];
  const yesterday = days[days.length - 2];

  const el = document.getElementById('delta-display');

  if (!yesterday) {
    el.innerHTML = `<p>Not enough data yet to compare days.</p>`;
    return;
  }

  const speciesOnDay = (dayKey) => new Set(
    allDetections
      .filter(d => getBucketKey(d.timestamp, 'day') === dayKey)
      .map(d => d.species)
  );

  const todaySpecies = speciesOnDay(today);
  const yesterdaySpecies = speciesOnDay(yesterday);

  const newToday = [...todaySpecies].filter(s => !yesterdaySpecies.has(s));
  const missingToday = [...yesterdaySpecies].filter(s => !todaySpecies.has(s));

  let html = `<h2>${yesterday} → ${today}</h2>`;
  html += `<p><strong>New today:</strong> ${newToday.length ? newToday.join(', ') : 'none'}</p>`;
  html += `<p><strong>Missing today:</strong> ${missingToday.length ? missingToday.join(', ') : 'none'}</p>`;

  el.innerHTML = html;
}

// ---- Event listeners ----

document.getElementById('toggle-btn').addEventListener('click', () => {
  document.getElementById('controls').classList.toggle('open');
});

document.getElementById('view-select').addEventListener('change', renderView);

document.getElementById('species-select').addEventListener('change', refreshCurrentView);
document.getElementById('freq-select').addEventListener('change', refreshCurrentView);
document.getElementById('from-date').addEventListener('change', refreshCurrentView);
document.getElementById('to-date').addEventListener('change', refreshCurrentView);

window.addEventListener('orientationchange', () => {
  setTimeout(() => {
    Plotly.Plots.resize('chart');
  }, 200);
});

window.addEventListener('resize', () => {
  Plotly.Plots.resize('chart');
});