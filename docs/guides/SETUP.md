# NeuroDrive Setup Guide

## Hardware
- Muse 2 headband (device name: `Muse-2474`, MAC: `00:55:DA:B8:24:74`)
- Optional: Muse S Athena headband (MAC: `00:55:DA:BB:C4:8E`, device: `MuseS-C48E`)
- Windows 11 laptop with Bluetooth 4.0+

## IMPORTANT: Do NOT pair the headband in Windows Bluetooth settings
muselsl and OpenMuse connect directly via Python BLE. If Windows has the
headband paired, the connection can fail. If it is currently paired, go to:
Settings -> Bluetooth & devices -> find `Muse-2474` or `MuseS-C48E` ->
three dots -> Remove device.

## Installation
```bash
pip install -r requirements.txt
```

Muse 2 uses `muselsl`, which is included in `requirements.txt`.

Muse S Athena only:
```bash
pip install https://github.com/DominiqueMakowski/OpenMuse/zipball/main
```

## Running the app

### One-click launcher (Windows)
Double-click `START_NEURODRIVE.bat` in the project root, then choose:
- `1` for Muse 2 / legacy Muse (muselsl).
- `2` for Muse S Athena (OpenMuse).
- `3` for simulation mode.
- `4` to exit.

The launcher checks Python packages, warns if muselsl or OpenMuse is missing,
and opens the dashboard in your browser automatically.

### Manual Muse 2 (muselsl)
Confirm the device name or MAC address:
```bash
muselsl list
```

Start the stream:
```bash
muselsl stream --name Muse-2474 --model legacy
```

If the name is not found:
```bash
muselsl stream --address 00:55:DA:B8:24:74 --model legacy
```

In another terminal, start the dashboard:
```bash
python app.py
```

The launcher defaults to MAC `00:55:DA:B8:24:74` for `Muse-2474`. Optional
environment variables:
```bat
set NEURODRIVE_MUSE_ADDRESS=00:55:DA:B8:24:74
set NEURODRIVE_MUSE_NAME=Muse-2474
set NEURODRIVE_MUSELSL_MODEL=legacy
```

If `NEURODRIVE_MUSE_ADDRESS` is set, it is used instead of the name. Set it to
empty to connect by name:
```bat
set NEURODRIVE_MUSE_ADDRESS=
```

Use `NEURODRIVE_MUSELSL_MODEL=auto` for mixed Muse models, or `athena` for a
Muse S Athena through muselsl.

### Manual Muse S Athena (OpenMuse)
```bash
python tools/start_stream.py
```

Or start OpenMuse manually and then run the dashboard:
```bash
OpenMuse stream --address 00:55:DA:BB:C4:8E
python app.py
```

Run only one backend at a time. Do not run muselsl and OpenMuse together.

## Dashboard URL
```text
http://localhost:5000
```

## Session data
Each session is saved to `data/` as `neurodrive_session_YYYYMMDD_HHMMSS.csv`
when you click **Stop Session** in the dashboard or stop the server with
`Ctrl+C`.

## If the headband disconnects
Close NeuroDrive and start it again with `START_NEURODRIVE.bat`, or run the
relevant helper directly:
```bash
python tools/start_muselsl.py
python tools/start_stream.py
```

Heart rate stays at `0` for Muse 2 because the dashboard currently reads EEG
only; muselsl PPG/optics streams are not consumed by the single-stream manager.
