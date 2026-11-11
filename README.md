# NeuroDrive

NeuroDrive is a final year project for real-time EEG-based anxiety monitoring.
It reads Muse headset data through an LSL stream, estimates anxiety from qEEG
band-power ratios, streams live metrics to a browser dashboard, and saves each
session as CSV for later analysis.

The project can also run without a headset using a simulation mode, which makes
testing and demonstrations possible when Muse hardware or a streaming backend is
not available.

## Current Architecture

NeuroDrive is currently a web-first Flask application.

```text
Muse Headband + muselsl (Muse 2) or OpenMuse (Muse S Athena)
        |
        v
Lab Streaming Layer (pylsl)
        |
        v
app.py / MuseStreamManager
        |
        +--> qEEG anxiety estimator in utils/anxiety_calculator.py
        +--> CSV session writer in data/
        +--> Socket.IO real-time events
                 |
                 v
          Browser dashboard
```

### Main Components

- `app.py` - main Flask + Socket.IO server for real Muse/LSL streaming.
- `START_NEURODRIVE.bat` - one-click Windows launcher for Muse 2 (muselsl), Muse S Athena (OpenMuse), or demo mode.
- `start.py` - interactive launcher for muselsl, OpenMuse, or simulation mode.
- `run.py` - quick launcher for the real headset server on port `5000`.
- `withouttheadband.py` - simulation server on port `5001`.
- `tools/start_muselsl.py` - starts muselsl for Muse 2 / legacy Muse, waits for the EEG stream, then runs the dashboard.
- `tools/start_stream.py` - starts OpenMuse for Muse S Athena, waits for the EEG stream, then runs the dashboard.
- `utils/anxiety_calculator.py` - qEEG band-ratio anxiety estimate logic.
- `templates/dashboard.html` - complete dashboard template with Socket.IO and charts.
- `templates/fypdashboard.html` - route target used by `app.py` and simulation mode.
- `index.html` - standalone/alternate Qt WebChannel dashboard experiment.
- `static.py` - routes for serving CSV data and artifact files.
- `data/` - generated session CSV files.
- `docs/` - setup guides, architecture notes, and EEG reference text.
- `artifacts/` - optional model metrics, reports, and generated assets.
- `backups/` and `old_docs/` - older versions kept for reference.

## Anxiety Estimation

The runtime does not treat an incoming anxiety channel as the final result.
Instead, it calculates a non-clinical heuristic estimate from EEG band powers:

- Theta/Beta ratio
- inverse Alpha/Sum ratio
- fast-wave dominance using beta, or gamma as a proxy when beta is unavailable
- slow-wave contribution from delta and theta

The result includes:

- `anxiety` score from `0` to `100`
- `anxiety_label`: `low`, `medium`, `high`, or `no signal`
- `anxiety_method`
- diagnostic ratios saved to CSV

Important: this is a research-aligned demo estimate, not a clinically validated
diagnostic model. Clinical-grade classification would require validated
preprocessing, artifact rejection, PSD extraction, and labelled psychological
ground truth.

## Requirements

On Python 3.12, install the full stack (including muselsl for Muse 2):

```bash
pip install -r requirements.txt
```

OpenMuse requires Python 3.12 or newer.

On Python 3.13/3.14, the full `requirements.txt` cannot be installed because
its pinned versions (for example `numpy==1.26.4`) have no wheels for those
versions. Use the Athena-only file instead:

```bash
pip install -r requirements-athena.txt
```

For Muse S Athena, install OpenMuse separately (required for both cases):

```bash
pip install https://github.com/DominiqueMakowski/OpenMuse/zipball/main
```

The Muse headset should be on, nearby, and not paired through Windows Bluetooth
settings. Run only one backend at a time (`muselsl` or `OpenMuse`).

On Windows, OpenMuse is installed into the per-user Python `Scripts` folder,
which is not on `PATH` by default. `start.py` and `tools/start_stream.py` now
look there automatically. If you run OpenMuse manually, either add
`%APPDATA%\Python\Python3XX\Scripts` to `PATH` or call the executable with its
full path.

## Running The Project

### One-Click Launcher (Windows)

Double-click `START_NEURODRIVE.bat` in the project root. On the first run it:

1. Finds Python 3.12+ (or downloads and installs Python 3.12.10 for the
   current user).
2. Creates a project-local `.venv`.
3. Installs the full requirements on Python 3.12 (Muse 2 + Athena), or the
   Athena-only set on Python 3.13/3.14.
4. Installs the tested OpenMuse 0.1.8 build from GitHub.
5. Starts `start.py`.

Internet access is required on the first run. Later runs reuse `.venv` and do
not download anything again. The `.venv` is machine-specific and can be large
(about 500 MB); when copying the project to another PC, you can delete `.venv`
first to keep the copy small. The launcher detects a broken/missing environment
and rebuilds it automatically.

If Python cannot be installed automatically or the network is unavailable, the
launcher prints the manual download link and tries an existing system Python as
a fallback. It cannot guarantee success on a machine with no internet access,
no permission to install software, or no writable disk space.

After setup, the same menu as `start.py` appears:

- `1` - Muse 2 / legacy Muse via muselsl (recommended for `Muse-2474`).
- `2` - Muse S Athena via OpenMuse.
- `3` - simulation mode without a headband.
- `4` - exit.

The launcher is local process automation only. It is not a CI/CD pipeline and
does not build, test, or deploy code to a remote service.

### Manual Launcher

After the one-click launcher has created `.venv`, use that environment:

```powershell
.\.venv\Scripts\python.exe start.py
```

Choose the same options: `1` muselsl, `2` OpenMuse, `3` simulation, `4` exit.

To use OpenMuse from a custom location, set `NEURODRIVE_OPENMUSE` to the full
path of `OpenMuse.exe`. The one-click launcher sets this automatically.

### Muse 2 / Legacy Muse (muselsl)

The one-click launcher uses the known MAC `00:55:DA:B8:24:74` for `Muse-2474`
by default. To target a different headset, set `NEURODRIVE_MUSE_ADDRESS` or
clear it and use `NEURODRIVE_MUSE_NAME`.

1. Confirm the device name or MAC address:

```bash
muselsl list
```

2. Start the stream using the exact device name:

```bash
muselsl stream --name Muse-2474 --model legacy
```

If the name is not found, use the MAC address from `muselsl list`:

```bash
muselsl stream --address 00:55:DA:B8:24:74 --model legacy
```

3. In another terminal, start the dashboard:

```bash
python app.py
```

Dashboard URL:

```text
http://localhost:5000
```

### Muse S Athena (OpenMuse)

If OpenMuse is already streaming LSL data:

```bash
python run.py
```

or:

```bash
python app.py
```

The dashboard uses the same URL: `http://localhost:5000`.

### Simulation Mode

```bash
python withouttheadband.py
```

Dashboard URL:

```text
http://localhost:5001
```

Simulation mode generates synthetic delta, theta, alpha, beta, gamma, and heart
rate values, then passes them through the same anxiety estimator used by the
real streaming path.

## API Endpoints

The real and simulation servers expose the same basic interface:

- `GET /` - dashboard page
- `GET /api/status` - current stream/session status
- `POST /api/start` - start streaming
- `POST /api/stop` - stop streaming and write CSV
- `GET /api/sessions` - list saved CSV sessions
- `GET /api/session/<filename>` - read a saved session, limited to recent rows
- `GET /data/<filename>` - download a CSV file
- `GET /artifacts/<path>` - serve generated artifact files

Socket.IO events:

- `status_update` - stream and session status messages
- `metrics_update` - live EEG, heart-rate, anxiety, and ratio payloads
- `connected` - emitted when a dashboard client connects

## Session Data

CSV files are written to `data/`. A new file is saved when you click
**Stop Session** in the dashboard or stop the server with `Ctrl+C`.

Real headset sessions use:

```text
data/neurodrive_session_YYYYMMDD_HHMMSS.csv
```

Simulation sessions use:

```text
data/neurodrive_simulation_YYYYMMDD_HHMMSS.csv
```

Each row includes sequence, timestamps, EEG bands, heart rate, anxiety score,
anxiety label, estimation method, diagnostic ratios, and stream name.

## Testing And Diagnostics

Run the streaming smoke test:

```bash
python test_streaming.py
```

Check whether `pylsl` can be imported:

```bash
python check_pylsl.py
```

Start only the muselsl helper:

```bash
python tools/start_muselsl.py
```

Start only the OpenMuse helper:

```bash
python tools/start_stream.py
```

## Additional Assets

The repository also keeps older root-level assets for reference:

- `VIVA_DEFENSE_PREP.md` - viva and presentation notes.
- `train_anxiety_model.py` - training script from the ML variant.
- `models/` - legacy model files (`anxiety_rf.pkl`, `scaler.pkl`).
- `guides/`, `references/`, `reports/` - older copies of the material now
  organized under `docs/` and `artifacts/`.
- `anxiety_calculator.py`, `fypdashboard.html`, `start_stream.py` - legacy
  root-level copies.

The active application uses `app.py`, `templates/`, `tools/`, and `utils/`.

## Notes For Developers

- `TARGET_HZ` is currently `20.0` in both real and simulation stream managers.
- `app.py` discovers Muse-like streams by name/type or EEG streams with at least four channels.
- Raw EEG streams are reduced to `TP9`, `AF7`, `AF8`, and `TP10` before band-power analysis; `Right AUX`/`AUX_*` channels are ignored.
- Heart rate stays `0` unless the stream provides a real heart-rate label. Muse 2 PPG is not consumed by the current single-stream manager.
- Muselsl defaults to `Muse-2474` at MAC `00:55:DA:B8:24:74` with `--model legacy`; override with `NEURODRIVE_MUSE_NAME`, `NEURODRIVE_MUSE_ADDRESS`, or `NEURODRIVE_MUSELSL_MODEL`. Set `NEURODRIVE_MUSE_ADDRESS=` (empty) to connect by name instead.
- OpenMuse uses `NEURODRIVE_ATHENA_ADDRESS`, defaulting to the Athena MAC in `tools/start_stream.py`.
- The Flask route `/` renders `templates/fypdashboard.html`, restored from
  `templates/dashboard.html`. `templates/fypdashboard_complex.html` is an
  alternate, more complex dashboard kept for reference.
- `index.html` is an alternate standalone interface that expects a Qt WebChannel bridge, so it is not the primary Flask dashboard.
- Older PyQt/backed-up versions are stored in `backups/` and should not be treated as the active architecture.
