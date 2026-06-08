#!/usr/bin/env python3
"""
NeuroDrive Web Server Launcher
Quick start script for the NeuroDrive EEG monitoring web application
"""

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Launch the NeuroDrive web application"""
    print("=" * 50)
    print("NEURODRIVE - EEG Anxiety Monitoring System")
    print("=" * 50)
    print()
    print("Starting web server...")
    print("Dashboard will be available at: http://localhost:5000")
    print()
    print("Make sure your Muse headset is streaming via:")
    print("  OpenMuse stream --address <your-headset-address>")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    print()

    # Import and run the app
    from app import main as app_main
    sys.exit(app_main())

if __name__ == "__main__":
    main()