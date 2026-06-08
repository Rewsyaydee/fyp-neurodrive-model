# 3D Head Viewer Integration Guide

## Overview

The dashboard uses a real-time 3D head viewer backed by Three.js in PyQtWebEngine. The implementation is now stability-first for moderate Windows laptops:

- Low-resource rendering is enabled by default.
- Model-load failures automatically fall back to a simple mesh.
- Python-to-JavaScript pose updates are throttled before crossing the bridge.

## Current Runtime Behavior

### Viewer States

The viewer exposes runtime status with these main states:

- loading: booted and trying to load scene.gltf
- loaded: scene.gltf loaded successfully
- fallback: fallback mesh active (model timeout/failure, or no WebEngine)

Status also includes:

- model: currently scene.gltf
- fallback: boolean
- antialias: boolean
- message: detail text for latest state

### Model Source

- Required model file: head_study/scene.gltf
- Associated binary/material files are resolved relative to the same folder.
- If loading exceeds 12 seconds, fallback mode is activated.

### Rendering Defaults

- Three.js r128 + GLTFLoader
- Renderer power preference: low-power
- Pixel ratio cap: 1.5
- Antialiasing:
  - Off by default in low-resource mode
  - Controlled by env var NEURODRIVE_3D_LOW_RESOURCE

Env var interpretation:

- Low-resource enabled when value is not in: 0, false, no, off
- Default when unset: enabled

## Dashboard Bridge Behavior

### Rotation Flow

Data path:

1. MultiStreamWorker provides synchronized payloads.
2. Dashboard receives orientation_quat (preferred) or ACC/GYRO fallback.
3. Quaternion is converted to Euler pitch/yaw/roll.
4. Yaw recenter offset is applied.
5. Values are clipped for display safety.
6. Pose is pushed to 3D viewer through throttled bridge logic.

### Bridge Throttling

The dashboard reduces bridge load before calling update_head_rotation:

- Max send frequency: 30 FPS
- Minimum pose delta to send: 0.35 degrees (max axis delta)

This avoids flooding runJavaScript during high-frequency IMU updates and lowers UI event loop pressure.

### Sensor Timeout Rules

Dashboard sensor badges automatically drop to OFF when stale:

- EEG timeout: 2.5 seconds
- IMU timeout: 2.5 seconds
- PPG timeout: 3.0 seconds
- NIRS timeout: 4.0 seconds

### Runtime Status Display

Dashboard status text now includes viewer runtime data:

- Viewer state (loading/loaded/fallback)
- Render mode (AA ON/OFF)

## Fallback Modes

### Model Load Fallback (WebEngine Available)

If scene.gltf fails or times out:

- A procedural sphere-like head mesh is created.
- Live pitch/yaw/roll updates continue.
- Runtime status reports fallback.

### No PyQtWebEngine Fallback

If PyQtWebEngine is not installed:

- A QWidget fallback is used instead of crashing startup.
- Live numeric pose text remains visible.
- get_runtime_status reports fallback with antialias false.

## API Surface (Current)

Head3DViewer methods used by dashboard:

- update_head_rotation(pitch, yaw, roll)
- get_runtime_status()

Compatibility no-op methods retained:

- update_blink_cue(...)
- update_drowsiness_indicator(...)

These methods are intentionally inert in the current viewer implementation.

## Troubleshooting

### Viewer stuck in loading

Checks:

1. Confirm head_study/scene.gltf exists.
2. Confirm referenced assets from scene.gltf are present.
3. Wait for timeout path; viewer should switch to fallback instead of freezing.

### Viewer reports fallback unexpectedly

Checks:

1. Look for model load errors in app logs.
2. Verify GPU/driver can initialize WebGL in embedded WebEngine.
3. Confirm file permissions for head_study assets.

### Movement feels laggy or too sensitive

Tune in dashboard:

1. _head_update_min_interval (lower = more updates)
2. _head_delta_threshold_deg (lower = more sensitivity)

## Key Files

- ui/head_3d_viewer.py
- ui/dashboard_tab.py
- head_study/scene.gltf
- requirements.txt

## Dependencies

- PyQtWebEngine==5.15.11

Install/update:

```bash
pip install -r requirements.txt
```

## Notes

- This guide documents current shipped behavior.
- Blink and drowsiness visuals are not active in the present 3D renderer.
- Future enhancements can reuse existing compatibility methods if needed.
