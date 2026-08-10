const $ = (id) => document.getElementById(id);
const headers = {"Content-Type": "application/json"};
const apiKey = sessionStorage.getItem("iotApiKey") || prompt("Pump-control API key (leave blank in mock mode):") || "";
if (apiKey) {
  sessionStorage.setItem("iotApiKey", apiKey);
  headers["X-API-Key"] = apiKey;
}

async function updateReadings() {
  try {
    const response = await fetch("/api/readings", {cache: "no-store"});
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    $("temperature").textContent = data.temperature_c.toFixed(1);
    $("humidity").textContent = data.humidity_percent.toFixed(1);
    $("moisture").textContent = data.soil_moisture_percent.toFixed(1);
    $("pump").textContent = data.pump_on ? "ON" : "OFF";
  } catch (error) {
    $("message").textContent = "Reading error: " + error.message;
  }
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST", headers, body: body ? JSON.stringify(body) : undefined
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
}

$("run").addEventListener("click", async () => {
  $("run").disabled = true;
  try {
    const duration = Number($("duration").value);
    $("message").textContent = "Timed pump cycle running…";
    await post("/api/pump/timed", {duration});
    $("message").textContent = "Timed pump cycle completed safely.";
  } catch (error) {
    $("message").textContent = error.message;
  } finally {
    $("run").disabled = false;
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
setInterval(updateReadings, 3000);
