let allDetections = [];

const freqLabels = {
  hour: 'Hourly',
  day: 'Daily',
  month: 'Monthly'
};

fetch('data/detections.json')
  .then(response => response.json())
  .then(data => {
    allDetections = data.map(d => ({
      species: d.species.commonName,
      timestamp: new Date(d.timestamp)
    }));

    populateSpeciesDropdown(allDetections);
    setDefaultDateRange(allDetections);
    drawChart();
  });

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

function drawChart() {
  const species = document.getElementById('species-select').value;
  const freq = document.getElementById('freq-select').value;
  const fromDate = new Date(document.getElementById('from-date').value);
  const toDate = new Date(document.getElementById('to-date').value);
  toDate.setHours(23, 59, 59);  // include the full "to" day

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

document.getElementById('species-select').addEventListener('change', drawChart);
document.getElementById('freq-select').addEventListener('change', drawChart);
document.getElementById('from-date').addEventListener('change', drawChart);
document.getElementById('to-date').addEventListener('change', drawChart);