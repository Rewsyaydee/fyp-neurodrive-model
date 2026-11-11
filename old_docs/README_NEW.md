# NeuroDrive Web Edition

NeuroDrive is a web-based EEG anxiety monitoring and reporting system for Muse headbands. This version provides two modes of operation: with real headband connection or simulation mode for demonstration.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install OpenMuse (separate installation)
pip install https://github.com/DominiqueMakowski/OpenMuse/zipball/main

# Run the launcher
python start.py
```

## Two Ways to Run

### 1️⃣ With Real Headband Connection

**Start:** `python start.py` → Option 1 (or `python connect_muse.py`)

This mode:
- First searches for and connects to your Muse headband
- Verifies the connection quality
- Only starts the dashboard after successful connection
- Dashboard URL: http://localhost:5000

**Requirements:**
- Muse headband turned on and paired via Bluetooth
- OpenMuse streaming: `OpenMuse stream --address <your-address>`

### 2️⃣ Without Headband (Demo Mode)

**Start:** `python start.py` → Option 2 (or `python withouttheadband.py`)

This mode:
- Uses simulated EEG data that varies realistically
- Dashboard starts immediately
- Great for demonstrations, testing, or UI development
- Dashboard URL: http://localhost:5001

## Connection Workflow

When using real headband mode:

1. **Terminal Connection Process**
   ```
   🔍 Scanning for Muse streams...
   ⏳ Found: Muse-A1234
   ✅ Connected! Receiving data
   ✓ Signal quality OK - 5 channels, ~20.0 Hz
   ```

2. **Automatic Dashboard Launch**
   - After successful connection, the dashboard automatically opens
   - Real-time data begins streaming immediately

3. **Connection Status**
   - Terminal shows connection status
   - Dashboard shows live indicators
   - Automatic reconnection on signal loss

## Features

### Real-Time Monitoring
- Live EEG brainwave visualization
- Anxiety level detection and feedback
- Heart rate monitoring
- Responsive animations based on brain activity

### Data Management
- Automatic session recording
- CSV export functionality
- Historical data viewing
- Session metrics tracking

### Web Interface
- Modern, responsive design
- Real-time WebSocket updates
- Toggle-able charts and visualizations
- Works on desktop and mobile

## Project Structure

```
FINALYEARPROJECTVOL2/
├── start.py                  # Main launcher script
├── connect_muse.py          # Headband connection script
├── withouttheadband.py      # Demo/simulation mode
├── app.py                   # Main app (requires headband)
├── templates/
│   └── fypdashboard.html    # Web dashboard
├── data/                    # Session CSV files
├── artifacts/
│   ├── models/             # ML models
│   └── reports/            # PDF reports
└── requirements.txt        # Dependencies
```

## Troubleshooting

### "No Muse headband detected"
1. Ensure headband is turned on
2. Check Bluetooth pairing
3. Start OpenMuse streaming:
   ```bash
   OpenMuse stream --address 00:55:DA:BB:C4:8E
   ```
4. Check if another app is using the headband

### Connection Issues
- Reset Bluetooth connection
- Restart OpenMuse streaming
- Try running the connection script again

### Simulation Mode Issues
- Runs on port 5001 (different from real mode)
- No special requirements needed
- Works offline

## API Endpoints

Both modes share similar APIs:

- `GET /` - Dashboard
- `GET /api/status` - Connection status
- `POST /api/start` - Start streaming
- `POST /api/stop` - Stop streaming
- `GET /api/sessions` - List sessions
- `GET /data/<filename>` - Download data

## Development

The code is organized to support both real and simulated data sources:

- `MuseStreamManager` - Handles real EEG data
- `SimulationStreamManager` - Generates realistic demo data
- Same Flask/SocketIO backend for both modes
- Identical dashboard UI works with either mode

## Next Steps

1. Pair your Muse headband via Bluetooth
2. Run `python start.py`
3. Choose connection mode
4. Start monitoring your brain activity! 🧠