# NeuroDrive Project Structure

This document describes the reorganized project structure for the NeuroDrive EEG Anxiety Monitoring System.

## Project Architecture

The NeuroDrive system consists of several key components working together to stream EEG data from a Muse headband, process it in real-time, and visualize it through a web dashboard.

### Core Components

1. **app.py** - Main Flask application with SocketIO for real-time communication
2. **connect_muse.py** - Handles Muse headband connection and LSL stream discovery
3. **start.py** - Launcher script to choose between headband or simulation mode
4. **withouttheadband.py** - Demo/simulation mode for testing without hardware
5. **index.html** - Main web dashboard (served from templates folder)
6. **templates/fypdashboard.html** - Production dashboard template
7. **static.py** - Static file serving configuration

### Data Flow

```
Muse Headband -> OpenMuse -> LSL Stream -> app.py -> SocketIO -> Dashboard
```

1. **OpenMuse** streams EEG data via LSL (Lab Streaming Layer)
2. **app.py** connects to the stream and processes data
3. Real-time anxiety calculations are performed using band power analysis
4. Data is sent to dashboard via SocketIO
5. Dashboard visualizes EEG metrics and anxiety levels

### Key Classes

- `MuseStreamManager` - Manages LSL stream connection and data processing
- `StreamRecord` - Data structure for EEG recordings
- Anxiety calculation utilities in `utils/anxiety_calculator.py`

## Folder Structure

```
FINALYEARPROJECTVOL2/
├── .venv/                  # Created by START_NEURODRIVE.bat (machine-specific)
├── app.py                  # Main Flask application
├── START_NEURODRIVE.bat    # Self-bootstrapping Windows launcher
├── requirements-athena.txt # Athena-only deps for Python 3.13/3.14
├── connect_muse.py         # Headband connection script
├── start.py               # Application launcher
├── withouttheadband.py    # Demo mode
├── index.html             # Alternative dashboard
├── static.py              # Static file routes
├── data/                  # All CSV session data (merged)
├── templates/             # HTML templates
│   └── fypdashboard.html  # Production dashboard
├── utils/                 # Utility modules
│   └── anxiety_calculator.py
├── tools/                 # Helper scripts
│   ├── start_muselsl.py   # Muse 2 / legacy Muse launcher
│   └── start_stream.py    # OpenMuse / Muse S Athena launcher
├── artifacts/             # Model artifacts & reports
├── docs/                  # Documentation & references
├── backups/               # Backup files
│   ├── fypdashboard.html  # Old dashboard backup
│   ├── main_pyqt_backup.py
│   └── style.qss
├── old_docs/              # Alternate documentation
│   ├── README_NEW.md
│   └── README_WEB.md
└── utils/                 # Utility functions
```

## Known Issues

### Stream Synchronization
The streaming works well in terminal but may have synchronization issues with the dashboard. This is likely due to:

1. **Timing mismatches** between LSL stream rate and dashboard refresh
2. **Buffer overflow** in the SocketIO communication
3. **Race conditions** when starting/stopping streams

### Potential Solutions

1. Adjust `TARGET_HZ` in app.py to match actual stream rate
2. Implement flow control in SocketIO emissions
3. Add connection state management
4. Use web workers for dashboard processing

## Development Notes

- `START_NEURODRIVE.bat` bootstraps a project-local `.venv`: it locates or
  downloads Python 3.12+, installs the project requirements and OpenMuse, then
  launches `start.py`.
- The system uses Flask with SocketIO for real-time communication
- EEG data is processed at 20Hz target rate (adjustable via `TARGET_HZ`)
- Anxiety levels calculated using theta/beta and alpha ratio methods
- All session data is saved to CSV in the data folder
- The dashboard supports dark/light theme switching
- Chart visualization is optional and can be toggled

## Dependencies

- Flask
- Flask-SocketIO
- pylsl (for LSL streaming)
- numpy (for EEG processing)
- muselsl (Muse 2 / legacy Muse)
- OpenMuse (Muse S Athena)