/**
 * server.js — Node/Express API layer over the existing Python pipeline.
 *
 * This does NOT reimplement any of the pandas/sklearn logic in JS. Each
 * route shells out to a thin Python script (api_runs.py, api_trends.py,
 * api_prediction.py) that imports your existing db.py / analyze.py /
 * trend_analysis.py / model.py directly and prints JSON to stdout.
 * That keeps one source of truth for the math — Node is just transport.
 *
 * Setup:
 *   npm install express
 *   (Python side: your existing venv with pandas/numpy/sklearn installed)
 *
 * Run:
 *   PYTHON_BIN=/path/to/venv/bin/python3 node server.js
 *   (defaults to ./venv/bin/python3 relative to this file if unset)
 *
 * Endpoints:
 *   GET /health
 *   GET /runs?page=1&per_page=50
 *   GET /trends/efficiency
 *   GET /prediction
 */
const express = require("express");
const { execFile } = require("child_process");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3001;

const PYTHON_BIN =
  process.env.PYTHON_BIN || path.join(__dirname, "venv", "bin", "python3");
const SCRIPT_DIR = __dirname;

/**
 * Runs a Python script in SCRIPT_DIR and parses its stdout as JSON.
 * Rejects with a readable error (using stderr if present) on any failure —
 * bad exit code, non-JSON stdout, or the process failing to start at all.
 */
function runPython(script, args = []) {
  return new Promise((resolve, reject) => {
    execFile(
      PYTHON_BIN,
      [path.join(SCRIPT_DIR, script), ...args],
      { cwd: SCRIPT_DIR, maxBuffer: 10 * 1024 * 1024, timeout: 30_000 },
      (err, stdout, stderr) => {
        if (err) {
          reject(new Error(stderr?.trim() || err.message));
          return;
        }
        try {
          resolve(JSON.parse(stdout));
        } catch (parseErr) {
          reject(
            new Error(
              `${script} did not return valid JSON: ${parseErr.message}\n${stdout}`
            )
          );
        }
      }
    );
  });
}

app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
  next();
});

// GET /health
app.get("/health", async (req, res) => {
  try {
    const data = await runPython("api_health.py");
    res.json(data);
  } catch (err) {
    console.error("GET /health failed:", err.message);
    res.status(500).json({ error: "Failed to check pipeline health", detail: err.message });
  }
});

// GET /runs?page=1&per_page=50
app.get("/runs", async (req, res) => {
  const page = Math.max(1, parseInt(req.query.page, 10) || 1);
  const perPage = Math.min(200, Math.max(1, parseInt(req.query.per_page, 10) || 50));

  try {
    const data = await runPython("api_runs.py", [String(page), String(perPage)]);
    res.json(data);
  } catch (err) {
    console.error("GET /runs failed:", err.message);
    res.status(500).json({ error: "Failed to load runs", detail: err.message });
  }
});

// GET /trends/efficiency
app.get("/trends/efficiency", async (req, res) => {
  try {
    const data = await runPython("api_trends.py");
    res.json(data);
  } catch (err) {
    console.error("GET /trends/efficiency failed:", err.message);
    res
      .status(500)
      .json({ error: "Failed to load efficiency trend", detail: err.message });
  }
});

// GET /prediction
app.get("/prediction", async (req, res) => {
  try {
    const data = await runPython("api_prediction.py");
    res.json(data);
  } catch (err) {
    console.error("GET /prediction failed:", err.message);
    res.status(500).json({ error: "Failed to compute prediction", detail: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`Marathon analytics API running on http://localhost:${PORT}`);
  console.log(`Using Python at: ${PYTHON_BIN}`);
});