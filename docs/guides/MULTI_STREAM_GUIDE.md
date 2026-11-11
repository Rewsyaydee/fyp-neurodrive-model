# NeuroDrive Multi-Stream CSV Export & Real-Time Synchronization

## Overview
This feature enables simultaneous acquisition of **5 sensor streams** from your Muse headband and related OpenMuse interfaces, synchronized to a common timestamp grid, and logged to CSV files for offline analysis.

## Sensor Streams Automatically Detected

| Stream | Channels | Sample Rate | LSL Type |
|--------|----------|-------------|----------|
| **EEG** | AF7, AF8, TP9, TP10 (4 channels) | 256 Hz | `EEG` |
| **fNIRS** | Frontal cortex hemodynamics | 64 Hz | `NIRS` or `fNIRS` |
| **PPG** | IR, NIR, Red (3 channels) | 64 Hz | `PPG` |
| **Accelerometer** | X, Y, Z (3 channels) | 52 Hz | `IMU-ACC` or `Accelerometer` |
| **Gyroscope** | X, Y, Z (3 channels) | 52 Hz | `IMU-GYRO` or `Gyroscope` |

## CSV Output Format

**Filename:** `neurodrive_session_YYYYMMDD_HHMM.csv`  
**Location:** `data/` folder

**Columns:**
```
Timestamp, EEG_AF7, EEG_AF8, EEG_TP9, EEG_TP10, fNIRS_O2, 
PPG_IR, PPG_NIR, PPG_Red, ACC_X, ACC_Y, ACC_Z, GYRO_X, GYRO_Y, GYRO_Z,
QUAT_W, QUAT_X, QUAT_Y, QUAT_Z, EULER_PITCH, EULER_YAW, EULER_ROLL
```

**Example Row:**
```
1712575234.123456, -45.2, 32.1, 28.5, -30.1, 0.0025, 1024, 1050, 990, 0.05, -0.02, 9.81, 0.001, -0.0005, 0.0, 0.9982, -0.0141, 0.0587, 0.0030, 1.82, 6.74, -1.58
```

## How It Works

### 1. **Time Synchronization**
- EEG (256 Hz) is the primary clock
- Other streams are aligned to EEG's timestamp via a rolling window (±0.1 seconds)
- Missing sensors in a window produce NULL values in CSV
- Handles jitter and rate differences gracefully

### 2. **Threading Architecture**
- `MultiStreamWorker` thread discovers and opens all LSL streams
- Per-stream buffers hold timestamped samples
- `SyncBuffer` aligns samples and emits synchronized tuples
- Main thread receives synced data via PyQt signals

### 3. **Live Dashboard ("Multi-Stream" Tab)**
Access via: **Main Window → Multi-Stream Tab**

**Three Real-Time Graphs:**
- **Graph 1:** EEG Frontal Lobe (AF7 [cyan] + AF8 [orange]) → nodding, attention
- **Graph 2:** PPG Waveform (IR green) → heart rate variability, cardiac trace
- **Graph 3:** Head Movement (ACC Z-axis [red]) → drowsiness, nodding detection

**Stream Health Stats:** Live sample counts per stream (bottom of tab)

### 4. **IMU Sensor Fusion for 3D Orientation**
- MultiStreamWorker now computes fused orientation in its worker thread using a Mahony AHRS filter.
- Inputs: synchronized ACC and GYRO samples plus timestamp delta.
- Outputs:
   - Quaternion orientation: `orientation_quat = [w, x, y, z]`
   - Euler orientation: `orientation_euler = [pitch, yaw, roll]` degrees
- These values are emitted in the `synced_data_signal` payload and logged to CSV.
- Dashboard 3D tracking consumes fused orientation when available and falls back to raw ACC/GYRO mapping if fusion is missing.

### 5. **Yaw Drift and Recenter**
- Muse streams usually do not provide a magnetometer heading reference.
- Yaw will drift slowly over time even with fusion.
- Use the **Recenter** button in the dashboard movement panel to zero current heading.

## Usage

### Recording Data

1. **Start the app:**
   ```bash
   python tools/start_stream.py
   ```

2. **Navigate to "Multi-Stream" tab** in NeuroDrive dashboard

3. **Click "Start Session"** (session tab) → Multi-stream CSV logging **automatically begins**

4. **Monitor live graphs** in the Multi-Stream tab
   - Green/orange/red dots indicate real-time stream activity
   - Stats bar shows cumulative sample counts

5. **Stop recording** with "Stop Session" → CSV file is finalized

### Output Location
```
data/neurodrive_session_20260408_1015.csv  (59,243 samples logged)
```

## Post-Processing

### Load CSV in Python
```python
import pandas as pd

df = pd.read_csv("data/neurodrive_session_20260408_1015.csv")
print(df.head())

# Plot EEG
import matplotlib.pyplot as plt
plt.plot(df["Timestamp"], df["EEG_AF7"], label="AF7")
plt.plot(df["Timestamp"], df["EEG_AF8"], label="AF8")
plt.legend()
plt.show()
```

### Filter by Stream Availability
```python
# Only rows with full fNIRS data
fnirs_rows = df[df["fNIRS_O2"].notna()]

# Only rows with ACC data
acc_rows = df[df["ACC_X"].notna()]
```

## Stream Discovery Troubleshooting

If not all sensors appear:

1. **Check OpenMuse output** for LSL stream announcements:
   ```
   [LSL] EEG stream connected
   [LSL] PPG stream found
   [MultiStream] fNIRS stream connected
   ```

2. **Verify LSL stream names** (if custom Muse setup):
   ```python
   from pylsl import resolve_byprop
   streams = resolve_byprop("type", "IMU-ACC")
   for s in streams:
       print(s.name(), s.channel_count())
   ```

3. **Optional streams gracefully degrade**: If fNIRS/ACC/GYRO unavailable, EEG/PPG still log normally with NULL values in missing columns.

## Performance Notes

- **EEG @ 256 Hz** → ~1024 samples/second → ~10 MB/hour (4 channels, 4 bytes each)
- **PPG @ 64 Hz** → ~256 samples/second → ~3 MB/hour
- **ACC/GYRO @ 52 Hz** → ~208 samples/second → ~2.5 MB/hour each
- **Total estimate:** ~20-25 MB per hour of continuous recording

## Configuration (Environment Variables)

```bash
# Control sync buffer window (seconds)
export NEURODRIVE_SYNC_WINDOW=0.15

# Control stream probe timeouts
export NEURODRIVE_NIRS_UI_HZ=8.0
export NEURODRIVE_NIRS_STALE_SECONDS=3.0
```

## Architecture Files

- **`utils/sync_buffer.py`** → Timestamp-based multi-rate synchronization
- **`utils/csv_logger.py`** → CSV file I/O with dynamic session naming
- **`core/multi_stream_worker.py`** → LSL discovery + threaded acquisition
- **`ui/multi_stream_tab.py`** → Real-time visualization (3 graphs + stats)

---

**Ready for your presentation!** The system is now recording all 5 sensor modalities in real-time with full timestamp alignment and CSV export.
