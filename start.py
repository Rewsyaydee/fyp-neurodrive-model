#!/usr/bin/env python3
"""
NeuroDrive Launcher
Choose between connected mode or simulation mode.
"""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def print_header():
    print("=" * 60)
    print("NEURODRIVE - EEG Anxiety Monitoring System")
    print("=" * 60)
    print()


def print_menu():
    print("Choose how to run NeuroDrive:")
    print()
    print("1) Connect with Muse headband")
    print("   - Starts OpenMuse automatically in this terminal")
    print("   - Dashboard opens after the stream is detected")
    print()
    print("2) Run without headband (Demo mode)")
    print("   - Uses simulated data for demonstration")
    print("   - Dashboard starts immediately")
    print()
    print("3) Exit")
    print()


def get_choice():
    while True:
        choice = input("Enter your choice (1-3): ").strip()
        if choice in ["1", "2", "3"]:
            return choice
        print("Invalid choice. Please enter 1, 2, or 3")


def run_with_headband():
    print("\n" + "=" * 60)
    print("STARTING WITH HEADBAND CONNECTION")
    print("=" * 60)
    print()
    print("This will start OpenMuse, wait for your Muse stream, then start the dashboard.")
    print("Make sure your headband is:")
    print("  - Turned on")
    print("  - Not paired in Windows Bluetooth settings")
    print("  - Close enough to this laptop")
    print()
    input("Press Enter to continue...")
    print()

    start_stream = ROOT / "tools" / "start_stream.py"
    return subprocess.call([sys.executable, str(start_stream)], cwd=ROOT)


def run_simulation():
    print("\n" + "=" * 60)
    print("STARTING IN SIMULATION MODE")
    print("=" * 60)
    print()
    print("Running without headband - using simulated data.")
    print("Dashboard will start immediately at http://localhost:5001")
    print()
    input("Press Enter to continue...")
    print()

    return os.system(f"{sys.executable} withouttheadband.py")


def main():
    print_header()
    print_menu()

    choice = get_choice()

    if choice == "1":
        return run_with_headband()
    if choice == "2":
        return run_simulation()

    print("\nGoodbye!")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        raise SystemExit(0)
