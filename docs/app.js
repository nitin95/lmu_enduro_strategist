const DEFAULTS = {
  race_hours: 6,
  lap_time_s: 105,
  ve_full_push: 0.039,
  N_tires: 100,
  MAX_STINTS_PER_SET: 2,
  DT_TIME: 32,
  chaos_factor: 0.01,
  // WET_RACE: false,
  // wet_ve: 0.043,
  fuel_to_ve: 1.25,
  n_simulations: 1000000,
  random_seed: 42,
};

const INPUT_DEFINITIONS = [
  { label: 'Race duration (h)', key: 'race_hours', type: 'number' },
  { label: 'Lap time (s)', key: 'lap_time_s', type: 'number' },
  { label: 'Full-push VE/lap', key: 've_full_push', type: 'number' },
  { label: 'Tyre sets available', key: 'N_tires', type: 'number' },
  { label: 'Max stints per tyre set', key: 'MAX_STINTS_PER_SET', type: 'number' },
  { label: 'Drive-through penalty (s)', key: 'DT_TIME', type: 'number' },
  { label: 'Chaos factor', key: 'chaos_factor', type: 'number' },
  // { label: 'Wet race', key: 'WET_RACE', type: 'checkbox' },
  // { label: 'Wet VE/lap', key: 'wet_ve', type: 'number' },
  { label: 'Fuel → VE conversion', key: 'fuel_to_ve', type: 'number' },
  { label: 'GA evaluation budget', key: 'n_simulations', type: 'number' },
  { label: 'Random seed', key: 'random_seed', type: 'number' },
];

const VE_COLORS = {
  'Full Push': '#4c72b0',
  '+1 lap save': '#22c55e',
  '+2 laps save': '#eab308',
  '+3 laps save': '#f97316',
  '+4 laps save': '#ef4444',
};

// ============================================================================
// Linear Interpolator (port from scipy.interp1d)
// ============================================================================
class LinearInterpolator {
  constructor(xArray, yArray) {
    this.x = Array.from(xArray).sort((a, b) => a - b);
    const indices = this.x.map((val, idx) => [val, idx]).sort((a, b) => a[0] - b[0]).map(x => x[1]);
    this.y = indices.map(i => yArray[i]);
    if (this.x.length < 2) {
      throw new Error('LinearInterpolator requires at least 2 points');
    }
  }

  interpolate(x) {
    if (x <= this.x[0]) {
      return this.y[0];
    }
    if (x >= this.x[this.x.length - 1]) {
      return this.y[this.y.length - 1];
    }
    let i = 0;
    while (i < this.x.length - 1 && this.x[i + 1] < x) {
      i++;
    }
    const x0 = this.x[i];
    const x1 = this.x[i + 1];
    const y0 = this.y[i];
    const y1 = this.y[i + 1];
    return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0);
  }
}

// ============================================================================
// XML Parsing Functions
// ============================================================================
function parseXMLFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const xmlText = e.target.result;
        const parser = new DOMParser();
        const xmlDoc = parser.parseFromString(xmlText, 'text/xml');
        if (xmlDoc.getElementsByTagName('parsererror').length > 0) {
          throw new Error('Invalid XML format');
        }
        const laps = extractLapsFromXML(xmlDoc);
        resolve(laps);
      } catch (error) {
        reject(error);
      }
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsText(file);
  });
}

function extractLapsFromXML(xmlDoc) {
  const laps = [];
  const trackVenue = xmlDoc.querySelector('TrackVenue')?.textContent || 'Unknown';
  const trackCourse = xmlDoc.querySelector('TrackCourse')?.textContent || '';
  const track = `${trackVenue}${trackCourse ? `(${trackCourse})` : ''}`;

  const sessionTypes = ['Practice', 'Practice1', 'Practice2', 'Qualify', 'Qualify1', 'Qualify2', 'Race', 'Warmup', 'Test'];
  
  for (const sessionTag of sessionTypes) {
    const sessionElems = xmlDoc.getElementsByTagName(sessionTag);
    for (const session of sessionElems) {
      const drivers = session.getElementsByTagName('Driver');
      for (const driverElem of drivers) {
        const driverName = driverElem.querySelector('Name')?.textContent || 'Unknown';
        const lapElems = driverElem.getElementsByTagName('Lap');
        for (const lapElem of lapElems) {
          const lapTimeStr = lapElem.textContent?.trim();
          const veUsedStr = lapElem.getAttribute('veUsed') || lapElem.getAttribute('ve_used');
          
          if (!lapTimeStr || lapTimeStr === '--.----') continue;
          
          const lapTime = parseFloat(lapTimeStr);
          const veUsed = parseFloat(veUsedStr);
          
          if (isNaN(lapTime) || isNaN(veUsed) || veUsed < 0) continue;
          
          laps.push({
            driver: driverName,
            lap_time: lapTime,
            ve_used: veUsed,
            track_venue: trackVenue,
            track_course: trackCourse,
            track: track,
            session_type: sessionTag,
          });
        }
      }
    }
  }
  
  return laps;
}

// ============================================================================
// Data Aggregation Functions
// ============================================================================
function extractUniqueTracks(lapRecords) {
  const trackSet = new Set();
  lapRecords.forEach(lap => {
    trackSet.add(lap.track);
  });
  return Array.from(trackSet).sort();
}

function extractDriversForTrack(lapRecords, track) {
  const driverMap = new Map();
  lapRecords
    .filter(lap => lap.track === track)
    .forEach(lap => {
      if (!driverMap.has(lap.driver)) {
        driverMap.set(lap.driver, 0);
      }
      driverMap.set(lap.driver, driverMap.get(lap.driver) + 1);
    });
  return Array.from(driverMap.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([driver, count]) => ({ driver, count }));
}

function extractTeamLaps(lapRecords, track, drivers) {
  const driverSet = new Set(drivers);
  return lapRecords
    .filter(lap => lap.track === track && driverSet.has(lap.driver))
    .map(lap => ({ ve_used: lap.ve_used, lap_time: lap.lap_time }));
}

function extractVeLaptimeRelationship(laps, minValidLaps = 3) {
  const groups = new Map();
  laps.forEach(lap => {
    const veRounded = Math.round(lap.ve_used * 10000) / 10000;
    if (!groups.has(veRounded)) {
      groups.set(veRounded, []);
    }
    groups.get(veRounded).push(lap.lap_time);
  });

  // Log diagnostic info
  console.log(`Total laps: ${laps.length}, Unique VE values: ${groups.size}`);
  const groupSizes = Array.from(groups.values()).map(v => v.length);
  console.log(`Group sizes: ${groupSizes.join(', ')}`);

  // Try with progressively more lenient criteria
  for (let minLaps of [minValidLaps, 2, 1]) {
    const aggregated = [];
    for (const [ve, laptimes] of groups.entries()) {
      if (laptimes.length >= minLaps) {
        const mean = laptimes.reduce((a, b) => a + b, 0) / laptimes.length;
        const std = Math.sqrt(
          laptimes.reduce((sq, val) => sq + Math.pow(val - mean, 2), 0) / laptimes.length
        );
        aggregated.push({ ve_used: ve, mean_laptime: mean, count: laptimes.length, std });
      }
    }

    if (aggregated.length >= 2) {
      console.log(`Aggregated data created with ${aggregated.length} groups (minLaps threshold: ${minLaps})`);
      return aggregated.sort((a, b) => a.ve_used - b.ve_used);
    }
  }

  console.error(`Failed to aggregate data: only ${groups.size} unique VE values found`);
  return null;
}

function createInterpolatorFromData(aggregatedData) {
  if (!aggregatedData || aggregatedData.length < 2) {
    return null;
  }
  const ve_array = aggregatedData.map(d => d.ve_used);
  const laptime_array = aggregatedData.map(d => d.mean_laptime);
  return new LinearInterpolator(ve_array, laptime_array);
}

const elements = {
  inputGrid: document.getElementById('inputGrid'),
  calculateButton: document.getElementById('calculateButton'),
  solverButton: document.getElementById('solverButton'),
  resetButton: document.getElementById('resetButton'),
  progressLabel: document.getElementById('progressLabel'),
  progressFill: document.getElementById('progressFill'),
  statRaceTime: document.getElementById('statRaceTime'),
  statLaps: document.getElementById('statLaps'),
  statVe: document.getElementById('statVe'),
  veTableBody: document.querySelector('#veTable tbody'),
  gridTableBody: document.querySelector('#gridTable tbody'),
  solverLog: document.getElementById('solverLog'),
  solverTableBody: document.querySelector('#solverTable tbody'),
  comparisonTableBody: document.querySelector('#comparisonTable tbody'),
  ganttCanvas: document.getElementById('ganttCanvas'),
  // Data tab elements
  xmlFileInput: document.getElementById('xmlFileInput'),
  dataStatusLabel: document.getElementById('dataStatusLabel'),
  trackDropdown: document.getElementById('trackDropdown'),
  driverSelect: document.getElementById('driverSelect'),
  selectedDriversList: document.getElementById('selectedDriversList'),
  buildInterpolatorBtn: document.getElementById('buildInterpolatorBtn'),
  clearDataBtn: document.getElementById('clearDataBtn'),
  modeIndicator: document.getElementById('modeIndicator'),
  raceTrackDropdown: document.getElementById('raceTrackDropdown'),
};

const state = {
  inputs: {},
  data: null,
  planA: null,
  planB: null,
  planC: null,
  worker: null,
  // Team data state
  xmlData: [],
  selectedTrack: null,
  selectedDrivers: [],
  interpolatorMode: 'hardcoded',
  currentInterpolator: null,
  teamInfo: null,
};

// Create default hardcoded interpolator
const HARDCODED_VE = [0.040, 0.039, 0.038, 0.037, 0.036];
const HARDCODED_LAPTIME = [74, 74.2, 74.5, 75, 75.5];
try {
  state.currentInterpolator = new LinearInterpolator(HARDCODED_VE, HARDCODED_LAPTIME);
} catch (e) {
  console.error('Failed to create hardcoded interpolator:', e);
}

function initInputs() {
  INPUT_DEFINITIONS.forEach(({ label, key, type }) => {
    const labelEl = document.createElement('label');
    labelEl.textContent = label;
    const input = document.createElement('input');
    input.type = type === 'checkbox' ? 'checkbox' : 'text';
    input.dataset.key = key;
    if (type === 'checkbox') {
      input.checked = DEFAULTS[key];
    } else {
      input.value = DEFAULTS[key];
      input.inputMode = 'decimal';
    }
    input.addEventListener('input', debounce(calculate, 280));
    labelEl.appendChild(input);
    elements.inputGrid.appendChild(labelEl);
    state.inputs[key] = input;
  });
}

function getInputValue(key) {
  const input = state.inputs[key];
  if (!input) return null;
  if (input.type === 'checkbox') {
    return input.checked;
  }
  const value = input.value.trim();
  return value === '' ? null : Number(value);
}

function getInputs() {
  const values = {};
  INPUT_DEFINITIONS.forEach(({ key, type }) => {
    let value = getInputValue(key);
    if (value === null || Number.isNaN(value)) {
      if (type === 'checkbox') {
        value = DEFAULTS[key];
      } else {
        value = DEFAULTS[key];
      }
    }
    if (key === 'n_simulations' || key === 'random_seed' || key === 'N_tires' || key === 'MAX_STINTS_PER_SET') {
      value = Math.floor(value);
    }
    values[key] = value;
  });
  values.race_time_s = values.race_hours * 3600;
  values.laps_approx = values.race_time_s / values.lap_time_s;
  return values;
}

function calculate() {
  const inputs = getInputs();
  state.data = inputs;
  calculateDerived(inputs);
  renderSummary(inputs);
  renderVeTable(inputs);
  renderGridTable(inputs);
  clearSolver();
  renderComparison();
}

function calculateDerived(d) {
  const lapsFp = Math.floor(1 / d.ve_full_push);
  const lapsFp1 = lapsFp + 1;
  const lapsFp2 = lapsFp1 + 1;
  const lapsFp3 = lapsFp2 + 1;
  const lapsFp4 = lapsFp3 + 1;
  // const lapsWet = d.WET_RACE ? Math.floor(1 / d.wet_ve) : lapsFp1;
  d.laps_fp = lapsFp;
  d.laps_fp1 = lapsFp1;
  d.laps_fp2 = lapsFp2;
  d.laps_fp3 = lapsFp3;
  d.laps_fp4 = lapsFp4;
  // d.laps_wet = lapsWet;
  d.ve_fp1 = 1 / lapsFp1;
  d.ve_fp2 = 1 / lapsFp2;
  d.ve_fp3 = 1 / lapsFp3;
  d.ve_fp4 = 1 / lapsFp4;
  d.fuel_fp = (d.ve_full_push / d.fuel_to_ve) * 100;
  d.fuel_fp1 = (d.ve_fp1 / d.fuel_to_ve) * 100;
  d.fuel_fp2 = (d.ve_fp2 / d.fuel_to_ve) * 100;
  d.fuel_fp3 = (d.ve_fp3 / d.fuel_to_ve) * 100;
  d.fuel_fp4 = (d.ve_fp4 / d.fuel_to_ve) * 100;
}

function renderSummary(d) {
  elements.statRaceTime.textContent = `${d.race_hours.toFixed(1)} h`;
  elements.statLaps.textContent = `${d.laps_approx.toFixed(1)}`;
  elements.statVe.textContent = `${(d.ve_full_push * 100).toFixed(2)}%`;
  // elements.statWetVe.textContent = `${(d.wet_ve * 100).toFixed(2)}%`;
}

function renderVeTable(d) {
  elements.veTableBody.innerHTML = '';
  const rows = [
    { label: 'Full Push', ve: d.ve_full_push * 100, laps: d.laps_fp, ve_val: d.ve_full_push, fuel: d.fuel_fp },
    { label: '+1 lap save', ve: d.ve_fp1 * 100, laps: d.laps_fp1, ve_val: d.ve_fp1, fuel: d.fuel_fp1 },
    { label: '+2 laps save', ve: d.ve_fp2 * 100, laps: d.laps_fp2, ve_val: d.ve_fp2, fuel: d.fuel_fp2 },
    { label: '+3 laps save', ve: d.ve_fp3 * 100, laps: d.laps_fp3, ve_val: d.ve_fp3, fuel: d.fuel_fp3 },
    { label: '+4 laps save', ve: d.ve_fp4 * 100, laps: d.laps_fp4, ve_val: d.ve_fp4, fuel: d.fuel_fp4 },
    // { label: 'Wet', ve: d.wet_ve * 100, laps: d.laps_wet, ve_val: d.wet_ve, fuel: null },
  ];
  rows.forEach(row => {
    const lt = state.currentInterpolator ? state.currentInterpolator.interpolate(row.ve_val) : d.lap_time_s;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${row.label}</td><td>${row.ve.toFixed(2)}%</td><td>${row.laps}</td><td>${lt.toFixed(2)}s</td><td>${row.fuel === null ? '—' : row.fuel.toFixed(2)}</td>`;
    elements.veTableBody.appendChild(tr);
  });
}

function renderGridTable(d) {
  elements.gridTableBody.innerHTML = '';
  const lapsOnPlan = Math.ceil(d.laps_approx);
  const scenarios = [
    { name: 'Negative 2', laps: lapsOnPlan - 2 },
    { name: 'Negative 1', laps: lapsOnPlan - 1 },
    { name: 'On Plan', laps: lapsOnPlan },
    { name: 'Positive 1', laps: lapsOnPlan + 1 },
    { name: 'Positive 2', laps: lapsOnPlan + 2 },
  ];
  scenarios.forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${item.name}</td><td>${item.laps}</td><td>${(item.laps / d.laps_fp1).toFixed(3)}</td><td>${(item.laps / d.laps_fp2).toFixed(3)}</td><td>${(item.laps / d.laps_fp3).toFixed(3)}</td><td>${(item.laps / d.laps_fp4).toFixed(3)}</td>`;
    elements.gridTableBody.appendChild(tr);
  });
}

function clearSolver() {
  elements.solverLog.textContent = 'Solver output will appear here once you run the GA.';
  elements.solverTableBody.innerHTML = '';
  elements.comparisonTableBody.innerHTML = '';
  setProgress(0, 'Idle');
  state.planA = null;
  state.planB = null;
  state.planC = null;
  drawGanttChart();
}

function setProgress(percent, label) {
  elements.progressFill.style.width = `${percent}%`;
  elements.progressLabel.textContent = label;
}

function appendSolverLog(text) {
  const line = document.createElement('div');
  line.textContent = text;
  elements.solverLog.appendChild(line);
  elements.solverLog.scrollTop = elements.solverLog.scrollHeight;
}

function switchTab(panelId) {
  document.querySelectorAll('.tab-button').forEach(button => {
    button.classList.toggle('active', button.dataset.panel === panelId);
  });
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === panelId);
  });
}

// ============================================================================
// Team Data Event Handlers
// ============================================================================
async function handleXMLUpload(event) {
  const files = Array.from(event.target.files);
  if (files.length === 0) return;

  try {
    for (const file of files) {
      const laps = await parseXMLFile(file);
      state.xmlData = state.xmlData.concat(laps);
    }
    updateDataStatus();
    updateTrackDropdowns();
  } catch (error) {
    alert(`Error loading XML: ${error.message}`);
  }
}

function updateDataStatus() {
  if (state.xmlData.length === 0) {
    elements.dataStatusLabel.textContent = 'No data loaded';
    elements.buildInterpolatorBtn.disabled = true;
    elements.trackDropdown.disabled = true;
    return;
  }
  elements.dataStatusLabel.textContent = `Loaded: ${state.xmlData.length} laps from ${new Set(state.xmlData.map(l => l.track)).size} tracks`;
  elements.trackDropdown.disabled = false;
}

function updateTrackDropdowns() {
  const tracks = extractUniqueTracks(state.xmlData);
  
  // Update data tab track dropdown
  elements.trackDropdown.innerHTML = tracks.map(t => `<option value="${t}">${t}</option>`).join('');
  if (tracks.length > 0 && !state.selectedTrack) {
    state.selectedTrack = tracks[0];
    elements.trackDropdown.value = state.selectedTrack;
  }
  
  // Update race parameters track dropdown
  const currentTracks = [{ label: 'Hardcoded (no data)', value: null }, ...tracks.map(t => ({ label: t, value: t }))];
  const currentValue = elements.raceTrackDropdown.value;
  elements.raceTrackDropdown.innerHTML = currentTracks.map(t => `<option value="${t.value || ''}">${t.label}</option>`).join('');
  
  if (state.selectedTrack) {
    elements.raceTrackDropdown.value = state.selectedTrack;
  }
  
  updateDriverDropdown();
}

function updateDriverDropdown() {
  if (!state.selectedTrack) {
    elements.driverSelect.innerHTML = '<option>No track selected</option>';
    elements.driverSelect.disabled = true;
    return;
  }

  const drivers = extractDriversForTrack(state.xmlData, state.selectedTrack);
  elements.driverSelect.innerHTML = drivers
    .map(d => `<option value="${d.driver}">${d.driver} (${d.count} laps)</option>`)
    .join('');
  elements.driverSelect.disabled = drivers.length === 0;
}

function handleTrackChange(event) {
  state.selectedTrack = event.target.value;
  elements.raceTrackDropdown.value = state.selectedTrack || '';
  state.selectedDrivers = [];
  updateDriverDropdown();
  updateSelectedDriversList();
  elements.buildInterpolatorBtn.disabled = true;
}

function handleRaceTrackChange(event) {
  const newTrack = event.target.value || null;
  if (newTrack !== state.selectedTrack) {
    state.selectedTrack = newTrack;
    elements.trackDropdown.value = newTrack || '';
    state.selectedDrivers = [];
    updateDriverDropdown();
    updateSelectedDriversList();
    elements.buildInterpolatorBtn.disabled = true;
  }
}

function handleDriverSelection(event) {
  const selected = Array.from(event.target.selectedOptions).map(o => o.value);
  
  // Enforce max 6 drivers
  if (selected.length > 6) {
    alert('Maximum 6 drivers allowed per team');
    event.target.value = Array.from(event.target.options)
      .filter(o => state.selectedDrivers.includes(o.value))
      .map(o => o.value);
    return;
  }
  
  state.selectedDrivers = selected;
  updateSelectedDriversList();
  elements.buildInterpolatorBtn.disabled = selected.length === 0;
}

function updateSelectedDriversList() {
  if (state.selectedDrivers.length === 0) {
    elements.selectedDriversList.innerHTML = '<p style="margin: 0; color: var(--text-muted);">No drivers selected</p>';
    return;
  }

  const teamLaps = extractTeamLaps(state.xmlData, state.selectedTrack, state.selectedDrivers);
  const veRange = teamLaps.length > 0 
    ? `${Math.min(...teamLaps.map(l => l.ve_used)).toFixed(4)} - ${Math.max(...teamLaps.map(l => l.ve_used)).toFixed(4)}`
    : 'N/A';

  let html = `<div style="margin-bottom: 8px;"><strong>Team:</strong> ${state.selectedDrivers.join(', ')}</div>`;
  html += `<div style="margin-bottom: 8px;"><strong>Total laps:</strong> ${teamLaps.length}</div>`;
  html += `<div><strong>VE range:</strong> ${veRange}</div>`;
  
  elements.selectedDriversList.innerHTML = html;
}

function buildTeamInterpolator() {
  if (state.selectedDrivers.length === 0) {
    alert('Select at least one driver');
    return;
  }

  const teamLaps = extractTeamLaps(state.xmlData, state.selectedTrack, state.selectedDrivers);
  if (teamLaps.length < 10) {
    alert(`Insufficient data: ${teamLaps.length} laps (need at least 10)`);
    return;
  }

  const aggregatedData = extractVeLaptimeRelationship(teamLaps);
  if (!aggregatedData) {
    alert(
      `Unable to build interpolator: your ${teamLaps.length} laps don't have enough distinct VE values or grouping. ` +
      `Check the browser console for diagnostic details.`
    );
    return;
  }

  const newInterpolator = createInterpolatorFromData(aggregatedData);
  if (!newInterpolator) {
    alert('Failed to create interpolator from team data');
    return;
  }

  state.currentInterpolator = newInterpolator;
  state.interpolatorMode = 'team-data';
  state.teamInfo = {
    track: state.selectedTrack,
    drivers: state.selectedDrivers,
    lapCount: teamLaps.length,
    aggregatedData: aggregatedData,
  };

  saveToLocalStorage();
  updateModeIndicator();
  calculate();
}

function clearAllData() {
  state.xmlData = [];
  state.selectedTrack = null;
  state.selectedDrivers = [];
  state.currentInterpolator = new LinearInterpolator(HARDCODED_VE, HARDCODED_LAPTIME);
  state.interpolatorMode = 'hardcoded';
  state.teamInfo = null;
  
  elements.xmlFileInput.value = '';
  elements.trackDropdown.innerHTML = '<option>No data loaded</option>';
  elements.trackDropdown.disabled = true;
  elements.driverSelect.innerHTML = '<option>No drivers available</option>';
  elements.driverSelect.disabled = true;
  elements.selectedDriversList.innerHTML = '<p style="margin: 0; color: var(--text-muted);">No drivers selected</p>';
  elements.buildInterpolatorBtn.disabled = true;
  elements.raceTrackDropdown.innerHTML = '<option value="">Hardcoded (no data)</option>';
  
  updateDataStatus();
  updateModeIndicator();
  clearLocalStorage();
  calculate();
}

function updateModeIndicator() {
  if (state.interpolatorMode === 'hardcoded') {
    elements.modeIndicator.textContent = '📊 Using: Hardcoded defaults';
    elements.modeIndicator.style.color = 'var(--text-muted)';
  } else {
    const drivers = state.teamInfo.drivers.slice(0, 2).join(', ') + (state.teamInfo.drivers.length > 2 ? ` +${state.teamInfo.drivers.length - 2}` : '');
    elements.modeIndicator.textContent = `📊 Using: Team Data (${drivers})`;
    elements.modeIndicator.style.color = '#22c55e';
  }
}

function saveToLocalStorage() {
  if (state.teamInfo) {
    const data = {
      mode: 'team-data',
      track: state.teamInfo.track,
      drivers: state.teamInfo.drivers,
      ve_array: state.teamInfo.aggregatedData.map(d => d.ve_used),
      laptime_array: state.teamInfo.aggregatedData.map(d => d.mean_laptime),
      timestamp: new Date().toISOString(),
    };
    localStorage.setItem('lmu_team_interpolator', JSON.stringify(data));
  }
}

function loadFromLocalStorage() {
  try {
    const stored = localStorage.getItem('lmu_team_interpolator');
    if (!stored) return;

    const data = JSON.parse(stored);
    if (data.mode !== 'team-data' || !data.ve_array || !data.laptime_array) {
      return;
    }

    const interp = new LinearInterpolator(data.ve_array, data.laptime_array);
    state.currentInterpolator = interp;
    state.interpolatorMode = 'team-data';
    state.teamInfo = {
      track: data.track,
      drivers: data.drivers,
      lapCount: 0,
      aggregatedData: data.ve_array.map((ve, i) => ({
        ve_used: ve,
        mean_laptime: data.laptime_array[i],
      })),
    };
    updateModeIndicator();
  } catch (error) {
    console.warn('Failed to load stored interpolator:', error);
  }
}

function clearLocalStorage() {
  localStorage.removeItem('lmu_team_interpolator');
}

function validScenarioFor(stintLaps, d) {
  const maxFp = d.laps_fp;
  if (stintLaps <= maxFp) {
    const lt = state.currentInterpolator ? state.currentInterpolator.interpolate(d.ve_full_push) : d.lap_time_s;
    return { label: 'Full Push', ve: d.ve_full_push, lt: lt, maxLaps: maxFp };
  }
  const table = [
    { label: '+1 lap save', ve: d.ve_fp1, lt: state.currentInterpolator ? state.currentInterpolator.interpolate(d.ve_fp1) : d.lap_time_s * 1.01, maxLaps: d.laps_fp1 },
    { label: '+2 laps save', ve: d.ve_fp2, lt: state.currentInterpolator ? state.currentInterpolator.interpolate(d.ve_fp2) : d.lap_time_s * 1.02, maxLaps: d.laps_fp2 },
    { label: '+3 laps save', ve: d.ve_fp3, lt: state.currentInterpolator ? state.currentInterpolator.interpolate(d.ve_fp3) : d.lap_time_s * 1.03, maxLaps: d.laps_fp3 },
    { label: '+4 laps save', ve: d.ve_fp4, lt: state.currentInterpolator ? state.currentInterpolator.interpolate(d.ve_fp4) : d.lap_time_s * 1.04, maxLaps: d.laps_fp4 },
  ];
  return table.find(item => stintLaps <= item.maxLaps) || null;
}

function refuelTime(veRefill, isTyreChange, d) {
  if (isTyreChange) {
    return veRefill * 0.4 + 22.0 + d.DT_TIME;
  }
  return veRefill * 0.4 + d.DT_TIME;
}

function evaluateStrategy(stopLaps, d) {
  let totalPit = 0;
  let elapsedDrive = 0;
  let prev = 0;
  let nTireStints = 0;
  for (const stop of stopLaps) {
    const stintLaps = stop - prev;
    nTireStints += 1;
    const isTyreChange = nTireStints > d.MAX_STINTS_PER_SET;
    const scenario = validScenarioFor(stintLaps, d);
    if (!scenario) return null;
    if (stintLaps < (1 / d.ve_full_push) * 0.7 || stintLaps * scenario.ve > 1.02) return null;
    const fuelL = stintLaps * scenario.ve * 100;
    totalPit += refuelTime(fuelL, isTyreChange, d);
    elapsedDrive += stintLaps * scenario.lt * (1 + d.chaos_factor);
    prev = stop;
  }
  const remaining = d.race_time_s - elapsedDrive - totalPit;
  if (remaining <= 0) return null;
  const finalLaps = remaining / (d.lap_time_s * (1 + d.chaos_factor));
  if (finalLaps < (1 / d.ve_full_push) * 0.7 || finalLaps * d.ve_full_push > 1.02) return null;
  const totalLaps = (stopLaps.length ? stopLaps[stopLaps.length - 1] : 0) + finalLaps;
  const finalFuelL = Math.ceil(Math.ceil(finalLaps) * d.ve_full_push * 100);
  return {
    stop_laps: stopLaps,
    n_stops: stopLaps.length,
    total_pit_time: totalPit,
    final_laps: finalLaps,
    total_laps: totalLaps,
    final_fuel_l: finalFuelL,
  };
}

function computePlanA(d) {
  const lapsFp = d.laps_fp;
  const lt = state.currentInterpolator ? state.currentInterpolator.interpolate(d.ve_full_push) : d.lap_time_s;
  const ve = d.ve_full_push;
  const chaos = d.chaos_factor;
  const raceTime = d.race_time_s;
  const fuelPerStint = lapsFp * ve * 100;
  const stopLaps = [];
  let totalDrive = 0;
  let totalPit = 0;
  let currentLap = 0;
  let nTireStints = 0;
  while (true) {
    nTireStints += 1;
    const isTyreChange = nTireStints > d.MAX_STINTS_PER_SET;
    const stintDrive = lapsFp * lt * (1 + chaos);
    const pit = refuelTime(fuelPerStint, isTyreChange, d);
    if (totalDrive + stintDrive + totalPit + pit >= raceTime) break;
    totalDrive += stintDrive;
    totalPit += pit;
    currentLap += lapsFp;
    stopLaps.push(currentLap);
  }
  const remaining = raceTime - totalDrive - totalPit;
  if (remaining <= 0) return null;
  const finalLaps = remaining / (lt * (1 + chaos));
  const totalLaps = currentLap + finalLaps;
  const finalFuelL = Math.ceil(Math.ceil(finalLaps) * ve * 100);
  return {
    stop_laps: stopLaps,
    n_stops: stopLaps.length,
    total_pit_time: totalPit,
    final_laps: finalLaps,
    total_laps: totalLaps,
    final_fuel_l: finalFuelL,
  };
}

function createWorker() {
  if (typeof Worker === 'undefined') {
    throw new Error('Web Workers are not supported in this browser.');
  }
  const source = document.getElementById('ga-worker').textContent;
  if (!source) {
    throw new Error('Worker source not found.');
  }
  const blob = new Blob([source], { type: 'text/javascript' });
  const url = URL.createObjectURL(blob);
  const worker = new Worker(url);
  worker._blobUrl = url;
  return worker;
}

function setSolverButtons(enabled) {
  elements.solverButton.disabled = !enabled;
  elements.calculateButton.disabled = !enabled;
}

function runSolver() {
  if (state.worker) {
    state.worker.terminate();
    URL.revokeObjectURL(state.worker._blobUrl);
  }
  setSolverButtons(false);
  elements.solverTableBody.innerHTML = '';
  elements.solverLog.textContent = '';
  setProgress(0, 'Starting solver…');
  const data = state.data || getInputs();
  let worker;
  try {
    worker = createWorker();
  } catch (error) {
    appendSolverLog(`Worker failed to start: ${error.message}`);
    appendSolverLog('Worker support may be blocked in this browser or environment.');
    setProgress(0, 'Worker unavailable');
    setSolverButtons(true);
    return;
  }
  state.worker = worker;
  appendSolverLog('Solver worker created. Running in background thread.');
  worker.addEventListener('message', event => {
    const payload = event.data;
    if (!payload) return;
    if (payload.type === 'log') {
      appendSolverLog(payload.msg);
    }
    if (payload.type === 'progress') {
      setProgress(Math.round((payload.gen / payload.total) * 100), `Plan ${payload.planLabel}: ${payload.gen}/${payload.total}, best ${payload.best}`);
    }
    if (payload.type === 'result') {
      appendSolverLog('Solver finished. Rendering results.');
      state.planA = payload.planA;
      state.planB = payload.planB;
      state.planC = payload.planC;
      renderSolverResult(payload.planA, 'Plan A — Full Push Benchmark');
      if (payload.planB) renderSolverResult(payload.planB, 'Plan B — Best GA');
      if (payload.planC) renderSolverResult(payload.planC, 'Plan C — One Fewer Stop GA');
      renderComparison();
      switchTab('comparisonPanel');
      setProgress(100, 'Solver complete');
      setSolverButtons(true);
      worker.terminate();
      URL.revokeObjectURL(worker._blobUrl);
      state.worker = null;
    }
    if (payload.type === 'error') {
      appendSolverLog(`Error: ${payload.msg}`);
      setProgress(0, 'Solver error');
      setSolverButtons(true);
      worker.terminate();
      URL.revokeObjectURL(worker._blobUrl);
      state.worker = null;
    }
  });
  worker.onerror = event => {
    appendSolverLog(`Worker error: ${event.message} (${event.filename}:${event.lineno})`);
    setProgress(0, 'Worker error');
    setSolverButtons(true);
    worker.terminate();
    URL.revokeObjectURL(worker._blobUrl);
    state.worker = null;
  };
  worker.onmessageerror = event => {
    appendSolverLog('Worker message error.');
    setProgress(0, 'Worker message error');
    setSolverButtons(true);
    worker.terminate();
    URL.revokeObjectURL(worker._blobUrl);
    state.worker = null;
  };
  worker.postMessage({ type: 'run', payload: data });
}

function renderSolverResult(result, label) {
  if (!result) return;
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${label}</td><td>${result.n_stops}</td><td>${result.total_laps.toFixed(2)}</td><td>${result.total_pit_time.toFixed(0)}s</td><td>${result.final_fuel_l}%</td>`;
  elements.solverTableBody.appendChild(tr);
  const detailTr = document.createElement('tr');
  detailTr.className = 'solver-table-details';
  const detailTd = document.createElement('td');
  detailTd.colSpan = 5;
  detailTd.textContent = `Stops: [${result.stop_laps.join(', ')}], final stint ~${result.final_laps.toFixed(1)} laps.`;
  detailTr.appendChild(detailTd);
  elements.solverTableBody.appendChild(detailTr);
}

function renderComparison() {
  elements.comparisonTableBody.innerHTML = '';
  const plans = [
    { label: 'Plan A', result: state.planA },
    { label: 'Plan B', result: state.planB },
    { label: 'Plan C', result: state.planC },
  ];
  const metrics = [
    { label: 'Stops', get: r => (r ? r.n_stops : 'N/A') },
    { label: 'Total Laps', get: r => (r ? r.total_laps.toFixed(2) : 'N/A') },
    { label: 'Total Pit Time (s)', get: r => (r ? `${r.total_pit_time.toFixed(0)}` : 'N/A') },
    { label: 'Final Stint Fuel (%)', get: r => (r ? `${r.final_fuel_l}` : 'N/A') },
  ];
  metrics.forEach(metric => {
    const tr = document.createElement('tr');
    const values = plans.map(plan => metric.get(plan.result));
    tr.innerHTML = `<td>${metric.label}</td><td>${values[0]}</td><td>${values[1]}</td><td>${values[2]}</td>`;
    elements.comparisonTableBody.appendChild(tr);
  });
  drawGanttChart();
}

function computeStintSegments(result, d) {
  const segments = [];
  let clock = 0;
  let prev = 0;
  let nTireStints = 0;
  for (let i = 0; i < result.stop_laps.length; i += 1) {
    const stopLap = result.stop_laps[i];
    const stintLaps = stopLap - prev;
    nTireStints += 1;
    const isTyreChange = nTireStints > d.MAX_STINTS_PER_SET;
    const scenario = validScenarioFor(stintLaps, d);
    if (!scenario) break;
    const driveS = stintLaps * scenario.lt * (1 + d.chaos_factor);
    const pitS = refuelTime(stintLaps * scenario.ve * 100, isTyreChange, d);
    segments.push({ type: 'stint', start_s: clock, end_s: clock + driveS, ve_label: scenario.label, stint_num: i + 1 });
    clock += driveS;
    segments.push({ type: 'pit', start_s: clock, end_s: clock + pitS });
    clock += pitS;
    prev = stopLap;
  }
  const finalLaps = result.final_laps;
  const scenario = validScenarioFor(finalLaps, d);
  if (scenario) {
    const driveS = finalLaps * scenario.lt * (1 + d.chaos_factor);
    segments.push({ type: 'stint', start_s: clock, end_s: clock + driveS, ve_label: scenario.label, stint_num: result.stop_laps.length + 1 });
  }
  return segments;
}

function drawGanttChart() {
  const canvas = elements.ganttCanvas;
  const ctx = canvas.getContext('2d');
  const d = state.data;
  const width = canvas.clientWidth * window.devicePixelRatio;
  const height = canvas.clientHeight * window.devicePixelRatio;
  canvas.width = width;
  canvas.height = height;
  ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
  const cw = canvas.clientWidth;
  const ch = canvas.clientHeight;
  ctx.clearRect(0, 0, cw, ch);
  ctx.fillStyle = 'rgba(255,255,255,0.04)';
  ctx.fillRect(0, 0, cw, ch);
  if (!d) return;
  const plans = [
    { label: 'Plan A', result: state.planA },
    { label: 'Plan B', result: state.planB },
    { label: 'Plan C', result: state.planC },
  ];
  const marginLeft = 96;
  const marginRight = 24;
  const marginTop = 36;
  const chartHeight = ch - marginTop - 60;
  const rowHeight = (chartHeight - 20) / plans.length;
  const raceMinutes = d.race_time_s / 60;
  ctx.font = '13px Inter, sans-serif';
  ctx.fillStyle = 'rgba(255,255,255,0.7)';
  ctx.fillText('Race timeline (minutes)', marginLeft, 18);
  const contentWidth = cw - marginLeft - marginRight;
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  for (let x = 0; x <= raceMinutes; x += 30) {
    const xpos = marginLeft + (x / raceMinutes) * contentWidth;
    ctx.beginPath();
    ctx.moveTo(xpos, marginTop);
    ctx.lineTo(xpos, marginTop + chartHeight);
    ctx.stroke();
    ctx.fillStyle = 'rgba(255,255,255,0.45)';
    ctx.fillText(`${x}`, xpos + 2, marginTop + chartHeight + 18);
  }
  plans.forEach((plan, index) => {
    const y = marginTop + index * rowHeight + 10;
    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.fillText(plan.label, 12, y + rowHeight / 2 + 3);
    if (!plan.result) {
      ctx.fillStyle = 'rgba(204,204,204,0.35)';
      ctx.fillRect(marginLeft, y, contentWidth, rowHeight * 0.5);
      ctx.fillStyle = 'rgba(255,255,255,0.65)';
      ctx.fillText('N/A', marginLeft + contentWidth / 2 - 12, y + rowHeight / 2 + 4);
      return;
    }
    const segments = computeStintSegments(plan.result, d);
    segments.forEach(seg => {
      const segX = marginLeft + (seg.start_s / 60 / raceMinutes) * contentWidth;
      const segW = ((seg.end_s - seg.start_s) / 60 / raceMinutes) * contentWidth;
      if (seg.type === 'pit') {
        ctx.fillStyle = '#374151';
        ctx.fillRect(segX, y + rowHeight * 0.38, segW, rowHeight * 0.24);
      } else {
        ctx.fillStyle = VE_COLORS[seg.ve_label] || '#888';
        ctx.fillRect(segX, y, segW, rowHeight * 0.6);
        if (segW > 48) {
          ctx.fillStyle = '#ffffff';
          ctx.font = '600 11px Inter, sans-serif';
          ctx.fillText(`${seg.stint_num}`, segX + segW / 2 - 6, y + rowHeight * 0.36 + 3);
        }
      }
    });
  });
  const legendKeys = Object.keys(VE_COLORS);
  legendKeys.push('Pit stop');
  legendKeys.forEach((key, index) => {
    const x = marginLeft + (index % 3) * 148;
    const y = ch - 26 - Math.floor(index / 3) * 22;
    ctx.fillStyle = key === 'Pit stop' ? '#374151' : VE_COLORS[key];
    ctx.fillRect(x, y - 10, 32, 10);
    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.fillText(key, x + 40, y - 1);
  });
}

function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = window.setTimeout(() => fn(...args), delay);
  };
}

function attachEventHandlers() {
  document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', () => switchTab(button.dataset.panel));
  });
  elements.calculateButton.addEventListener('click', calculate);
  elements.solverButton.addEventListener('click', runSolver);
  elements.resetButton.addEventListener('click', () => {
    INPUT_DEFINITIONS.forEach(({ key, type }) => {
      const input = state.inputs[key];
      if (type === 'checkbox') {
        input.checked = DEFAULTS[key];
      } else {
        input.value = DEFAULTS[key];
      }
    });
    calculate();
  });
  
  // XML file upload handler
  elements.xmlFileInput.addEventListener('change', handleXMLUpload);
  
  // Track dropdown handlers
  elements.trackDropdown.addEventListener('change', handleTrackChange);
  elements.raceTrackDropdown.addEventListener('change', handleRaceTrackChange);
  
  // Driver select handler
  elements.driverSelect.addEventListener('change', handleDriverSelection);
  
  // Build interpolator button
  elements.buildInterpolatorBtn.addEventListener('click', buildTeamInterpolator);
  
  // Clear data button
  elements.clearDataBtn.addEventListener('click', clearAllData);
  
  window.addEventListener('resize', debounce(drawGanttChart, 200));
}

function init() {
  initInputs();
  loadFromLocalStorage();
  attachEventHandlers();
  calculate();
}

init();
