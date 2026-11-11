# NeuroDrive Web Edition

NeuroDrive is now a web-based EEG anxiety monitoring and reporting system. This version removes the PyQt5 desktop dependency and runs entirely in your browser.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install OpenMuse (separate installation)
pip install https://github.com/DominiqueMakowski/OpenMuse/zipball/main

# Start the web server
python app.py
# or
python run.py

# Open your browser to
http://localhost:5000
```

## What's Changed?

### ✅ Web-Based Dashboard
- Fully responsive HTML dashboard with real-time updates
- No more PyQt5 dependencies
- Works in any modern browser

### ✅ Real-Time WebSocket Connection
- Uses Socket.IO for instant data streaming
- Live EEG metrics without page refresh
- Smooth visualizations and animations

### ✅ Simplified Architecture
- `app.py` - Flask web server with EEG streaming logic
- `templates/fypdashboard.html` - Main dashboard UI
- All sensor connectivity preserved from original version

## Features

- **Real-time EEG streaming** from Muse headsets
- **Live anxiety level detection** with visual feedback
- **Brainwave visualization** (Delta, Theta, Alpha, Gamma)
- **Heart rate monitoring**
- **Session recording** to CSV files
- **Web-based controls** (start/stop/export)
- **Responsive design** works on desktop and mobile

## EEG Data Streams

The application automatically discovers Muse streams and extracts:
- Delta waves (0.5-4 Hz)
- Theta waves (4-8 Hz)
- Alpha waves (8-12 Hz)
- Gamma waves (30-100 Hz)
- Heart rate (if available)
- Calculated anxiety levels

## Usage

1. **Start your Muse headset streaming**
   ```bash
   OpenMuse stream --address 00:55:DA:BB:C4:8E
   ```

2. **Launch the NeuroDrive web server**
   ```bash
   python app.py
   ```

3. **Open the dashboard**
   Navigate to http://localhost:5000 in your browser

4. **Control the session**
   - Click "Start Session" to begin recording
   - Monitor real-time metrics
   - Click "Stop Session" when finished
   - Export data using the export button

## Project Structure

```
FINALYEARPROJECTVOL2/
├── app.py                    # Flask web application
├── run.py                    # Easy launcher script
├── templates/
│   └── fypdashboard.html    # Web dashboard
├── data/                     # Session CSV files
├── artifacts/
│   ├── models/              # ML models
│   └── reports/             # PDF reports
├── requirements.txt          # Python dependencies
└── main_pyqt_backup.py      # Old PyQt5 version (backup)
```

## API Endpoints

- `GET /` - Main dashboard
- `GET /api/status` - Current streaming status
- `POST /api/start` - Start EEG streaming
- `POST /api/stop` - Stop EEG streaming
- `GET /api/sessions` - List past sessions
- `GET /api/session/<filename>` - Get session data
- `GET /data/<filename>` - Download CSV files

## Troubleshooting

### "No stream connected" message
- Make sure your Muse headset is streaming with OpenMuse
- Check that the headset is paired and connected
- Verify the headset address is correct

### Page won't load
- Check that the server started successfully
- Make sure port 5000 is not blocked by firewall
- Try http://127.0.0.1:5000 instead of localhost

### Real-time updates not working
- Check browser console for WebSocket errors
- Make sure JavaScript is enabled
- Try refreshing the page

## Development

The web version maintains all the functionality of the original PyQt5 version while being more accessible and easier to use. The core EEG processing logic remains unchanged, ensuring compatibility with existing data and models.

## License

This project maintains the same license as the original NeuroDrive project.