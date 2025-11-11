const statusOutput = document.getElementById("status-output");
const uploadOutput = document.getElementById("upload-output");
const trainOutput = document.getElementById("train-output");
const predictOutput = document.getElementById("predict-output");
const bulkOutput = document.getElementById("bulk-output");
const bulkCsvOutput = document.getElementById("bulk-csv-output");
const catalogOutput = document.getElementById("catalog-output");
const latestModelOutput = document.getElementById("latest-model-output");

const STATUS_READY_TEXT = "Ready.";
statusOutput.textContent = STATUS_READY_TEXT;

function formatJSON(data) {
  try {
    return JSON.stringify(data, null, 2);
  } catch (err) {
    return String(data);
  }
}

async function callEndpoint(path, options = {}) {
  const url = `/api/gpt${path}`;
  statusOutput.textContent = `Calling ${url}...`;
  try {
    const res = await fetch(url, options);
    const isJSON = res.headers.get("content-type")?.includes("application/json");
    let payload = null;
    if (isJSON) {
      payload = await res.json();
    } else {
      payload = await res.text();
    }
    statusOutput.textContent = `${res.status} ${res.statusText || ""}`.trim();
    if (!res.ok) {
      const message = typeof payload === "string" ? payload : formatJSON(payload);
      throw new Error(message || `Request to ${url} failed`);
    }
    return payload;
  } catch (err) {
    statusOutput.textContent = `Request failed: ${err.message}`;
    throw err;
  }
}

async function refreshLatestModel() {
  latestModelOutput.textContent = "Checking for saved models...";
  try {
    const data = await callEndpoint("/models/latest");
    if (!data?.latest) {
      latestModelOutput.textContent = "No saved model found. Train one to enable predictions.";
      return;
    }
    latestModelOutput.textContent = `Latest model: ${data.latest}`;
  } catch (err) {
    latestModelOutput.textContent = `Unable to fetch model info: ${err.message}`;
  }
}

document.getElementById("btn-health").addEventListener("click", async () => {
  try {
    const data = await callEndpoint("/status");
    statusOutput.textContent += `\n${formatJSON(data)}`;
  } catch (_) {}
});

document.getElementById("btn-model-status").addEventListener("click", refreshLatestModel);

async function renderCatalog() {
  catalogOutput.textContent = "Loading catalog...";
  try {
    const data = await callEndpoint("/catalog");
    if (!data.ok) {
      catalogOutput.textContent = formatJSON(data);
      return;
    }

    const { players = [], teams = [], opps = [] } = data;
    catalogOutput.innerHTML = `
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Collection</th>
              <th>Total</th>
              <th>Sample</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Players</td>
              <td>${players.length}</td>
              <td>${players.slice(0, 15).join(", ") || "—"}</td>
            </tr>
            <tr>
              <td>Teams</td>
              <td>${teams.length}</td>
              <td>${teams.slice(0, 20).join(", ") || "—"}</td>
            </tr>
            <tr>
              <td>Opponents</td>
              <td>${opps.length}</td>
              <td>${opps.slice(0, 20).join(", ") || "—"}</td>
            </tr>
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    catalogOutput.textContent = `Catalog load failed: ${err.message}`;
  }
}

document.getElementById("btn-catalog").addEventListener("click", renderCatalog);

document.getElementById("form-upload").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.target);
  uploadOutput.textContent = "Uploading...";
  try {
    const data = await callEndpoint("/upload-etr", {
      method: "POST",
      body: formData,
    });
    uploadOutput.textContent = formatJSON(data);
    await renderCatalog();
  } catch (err) {
    uploadOutput.textContent = `Upload failed: ${err.message}`;
  }
});

document.getElementById("btn-train").addEventListener("click", async () => {
  trainOutput.textContent = "Training started...";
  try {
    const data = await callEndpoint("/train", { method: "POST" });
    trainOutput.textContent = formatJSON(data);
    await refreshLatestModel();
  } catch (err) {
    trainOutput.textContent = `Training failed: ${err.message}`;
  }
});

document.getElementById("form-predict").addEventListener("submit", async (event) => {
  event.preventDefault();
  const params = new URLSearchParams(new FormData(event.target));
  predictOutput.textContent = "Requesting prediction...";
  try {
    const data = await callEndpoint(`/predict?${params.toString()}`);
    predictOutput.textContent = formatJSON(data);
  } catch (err) {
    predictOutput.textContent = `Prediction failed: ${err.message}`;
  }
});

document.getElementById("btn-bulk-json").addEventListener("click", async () => {
  const payload = document.getElementById("bulk-json").value;
  if (!payload.trim()) {
    bulkOutput.textContent = "Please paste a JSON array first.";
    return;
  }
  let parsed;
  try {
    parsed = JSON.parse(payload);
  } catch (err) {
    bulkOutput.textContent = `Invalid JSON: ${err.message}`;
    return;
  }
  bulkOutput.textContent = "Sending bulk prediction request...";
  try {
    const data = await callEndpoint("/predict_bulk_json", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(parsed),
    });
    bulkOutput.textContent = formatJSON(data);
  } catch (err) {
    bulkOutput.textContent = `Bulk prediction failed: ${err.message}`;
  }
});

document.getElementById("form-bulk-csv").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.target);
  bulkCsvOutput.textContent = "Uploading CSV for predictions...";
  try {
    const data = await callEndpoint("/predict_bulk_csv", {
      method: "POST",
      body: formData,
    });
    bulkCsvOutput.textContent = formatJSON(data);
  } catch (err) {
    bulkCsvOutput.textContent = `Bulk CSV prediction failed: ${err.message}`;
  }
});

refreshLatestModel();
