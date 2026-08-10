const $ = (id) => document.getElementById(id);
const headers = {"Content-Type": "application/json"};

async function updateReadings() {
  try {
    const response = await fetch("/api/readings", {cache: "no-store"});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    $("temperature").textContent = data.temperature_c.toFixed(1);
    $("humidity").textContent = data.humidity_percent.toFixed(1);
    $("moisture").textContent = data.soil_moisture_percent.toFixed(1);
    $("pump").textContent = data.pump_on ? "ON" : "OFF";
    await updateHistory();
  } catch (error) {
    $("message").textContent = "Reading error: " + error.message;
  }
}

function drawChart(id, values, color, suffix) {
  const canvas = $(id);
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth, 280);
  const height = Math.max(canvas.clientHeight, 180);
  canvas.width = width * ratio; canvas.height = height * ratio;
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  const pad = {left: 42, right: 14, top: 18, bottom: 28};
  const chartWidth = width - pad.left - pad.right;
  const chartHeight = height - pad.top - pad.bottom;
  if (!values.length) { ctx.fillStyle = "#5e746b"; ctx.fillText("Waiting for stored readings...", 18, 36); return; }
  let min = Math.min(...values), max = Math.max(...values);
  if (min === max) { min -= 1; max += 1; }
  const margin = (max - min) * 0.12; min -= margin; max += margin;
  ctx.strokeStyle = "#d7e2dd"; ctx.fillStyle = "#5e746b"; ctx.font = "12px system-ui";
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + chartHeight * i / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width-pad.right, y); ctx.stroke();
    ctx.fillText((max - (max-min)*i/4).toFixed(1), 3, y+4);
  }
  ctx.strokeStyle = color; ctx.lineWidth = 3; ctx.lineJoin = "round"; ctx.beginPath();
  values.forEach((value, index) => {
    const x = pad.left + chartWidth * (values.length === 1 ? 0.5 : index/(values.length-1));
    const y = pad.top + chartHeight * (1-(value-min)/(max-min));
    index ? ctx.lineTo(x,y) : ctx.moveTo(x,y);
  });
  ctx.stroke(); ctx.fillStyle = "#5e746b"; ctx.fillText("oldest", pad.left, height-8); ctx.fillText("latest", width-52, height-8);
  const latest = values[values.length-1];
  canvas.setAttribute("aria-label", `${id.replace("-chart", "")} history, latest ${latest.toFixed(1)} ${suffix}`);
}

async function updateHistory() {
  const response = await fetch("/api/history?limit=120", {cache: "no-store"});
  if (!response.ok) throw new Error(await response.text());
  const rows = (await response.json()).readings;
  const temperatures = rows.map(row => row.temperature_c);
  const humidities = rows.map(row => row.humidity_percent);
  const moistures = rows.map(row => row.soil_moisture_percent);
  drawChart("temperature-chart", temperatures, "#d45b3f", "degrees Celsius");
  drawChart("humidity-chart", humidities, "#3579b8", "percent relative humidity");
  drawChart("moisture-chart", moistures, "#2f8c61", "percent");
  $("temperature-trend").textContent = `${temperatures.length} points`;
  $("humidity-trend").textContent = `${humidities.length} points`;
  $("moisture-trend").textContent = `${moistures.length} points`;
}

async function loadCalibration() {
  try {
    const response = await fetch("/api/config/calibration", {cache: "no-store"});
    if (!response.ok) throw new Error(await response.text());
    const config = await response.json();
    $("dry-value").value = config.dry_value;
    $("wet-value").value = config.wet_value;
    $("calibration-message").textContent = "Saved calibration loaded from SQLite.";
    $("calibration-message").className = "form-message";
  } catch (error) {
    $("calibration-message").textContent = "Calibration error: " + error.message;
    $("calibration-message").className = "form-message error";
  }
}

$("calibration-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("save-calibration");
  const dryValue = Number($("dry-value").value);
  const wetValue = Number($("wet-value").value);
  if (!Number.isInteger(dryValue) || !Number.isInteger(wetValue) || dryValue === wetValue) {
    $("calibration-message").textContent = "Enter two different whole-number raw values.";
    $("calibration-message").className = "form-message error";
    return;
  }
  button.disabled = true;
  try {
    const response = await fetch("/api/config/calibration", {
      method: "PUT", headers, body: JSON.stringify({dry_value: dryValue, wet_value: wetValue})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Unable to save calibration");
    $("calibration-message").textContent = `Saved: dry ${data.dry_value}, wet ${data.wet_value}.`;
    $("calibration-message").className = "form-message success";
    await updateReadings();
  } catch (error) {
    $("calibration-message").textContent = error.message;
    $("calibration-message").className = "form-message error";
  } finally {
    button.disabled = false;
  }
});

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST", headers, body: body ? JSON.stringify(body) : undefined
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
}

$("manual-on").addEventListener("click", async () => {
  $("manual-on").disabled = true;
  try {
    const duration = Number($("duration").value);
    $("message").textContent = "Manual timed pump cycle running…";
    await post("/api/pump/timed", {duration});
    $("message").textContent = "Manual pump cycle completed and stopped safely.";
  } catch (error) {
    $("message").textContent = error.message;
  } finally {
    $("manual-on").disabled = false;
    updateReadings();
  }
});

$("off").addEventListener("click", async () => {
  try {
    await post("/api/pump/off");
    $("message").textContent = "Pump stop requested.";
    updateReadings();
  } catch (error) {
    $("message").textContent = error.message;
  }
});

updateReadings();
loadCalibration();
setInterval(updateReadings, 3000);
window.addEventListener("resize", updateHistory);
