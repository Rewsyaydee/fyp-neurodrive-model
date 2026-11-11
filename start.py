#!/usr/bin/env python3
"""
NeuroDrive Launcher
Choose between connected mode or simulation mode.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def find_openmuse():
    """Locate the OpenMuse executable, including virtual environments.

    ``shutil.which`` only searches PATH. Check the active/venv scripts
    directory and the per-user pip install directory as fallbacks.
    """
    override = os.environ.get("NEURODRIVE_OPENMUSE", "").strip()
    if override and Path(override).is_file():
        return override

    executable = shutil.which("OpenMuse")
    if executable:
        return executable

    executable_name = "OpenMuse.exe" if os.name == "nt" else "OpenMuse"
    candidates = []

    try:
        candidates.append(Path(sysconfig.get_path("scripts")) / executable_name)
    except Exception:
        pass

    try:
        candidates.append(
            Path(sysconfig.get_path("scripts", scheme="nt_user")) / executable_name
        )
    except Exception:
        pass

    # Virtual environments put scripts next to python.exe.
    candidates.append(Path(sys.executable).parent / executable_name)
    # Global Python installs put scripts in a sibling Scripts folder.
    candidates.append(Path(sys.executable).parent / "Scripts" / executable_name)

    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return str(candidate)
    return None


def print_header():
    print("=" * 60)
    print("NEURODRIVE - EEG Anxiety Monitoring System")
    print("=" * 60)
    print()


def print_menu():
    print("Choose how to run NeuroDrive:")
    print()
    print("1) Connect Muse 2 / legacy Muse (muselsl)")
    print("   - Recommended for Muse-2474")
    print("   - Starts muselsl automatically in this terminal")
    print("   - Dashboard opens after the stream is detected")
    print()
    print("2) Connect Muse S Athena (OpenMuse)")
    print("   - Athena only; use option 1 for Muse 2")
    print("   - Starts OpenMuse automatically in this terminal")
    print()
    print("3) Run without headband (Demo mode)")
    print("   - Uses simulated data for demonstration")
    print("   - Dashboard starts immediately")
    print()
    print("4) Exit")
    print()


def get_choice():
    while True:
        choice = input("Enter your choice (1-4): ").strip()
        if choice in ["1", "2", "3", "4"]:
            return choice
        print("Invalid choice. Please enter 1, 2, 3, or 4")


def run_with_muselsl():
    print("\n" + "=" * 60)
    print("STARTING WITH MUSELSL (MUSE 2 / LEGACY MUSE)")
    print("=" * 60)
    print()

    has_muselsl = importlib.util.find_spec("muselsl") is not None or shutil.which("muselsl") is not None
    if not has_muselsl:
        print("muselsl is not installed or is not on PATH.")
        print("Install it with:")
        print("  python -m pip install muselsl")
        print("Or with pipx: pipx install muselsl")
        print()
        return 1

    address_override = os.environ.get("NEURODRIVE_MUSE_ADDRESS")
    target_address = ("00:55:DA:B8:24:74" if address_override is None else address_override).strip()
    target_name = os.environ.get("NEURODRIVE_MUSE_NAME", "Muse-2474").strip() or "(first Muse found)"
    model = os.environ.get("NEURODRIVE_MUSELSL_MODEL", "legacy").strip() or "legacy"
    target = f"address {target_address} ({target_name})" if target_address else f"name {target_name}"

    print(f"Target: {target} (model: {model})")
    print("Make sure your headband is:")
    print("  - Turned on")
    print("  - Not paired in Windows Bluetooth settings")
    print("  - Not connected to OpenMuse or another app")
    print()
    input("Press Enter to continue...")
    print()

    return subprocess.call([sys.executable, str(ROOT / "tools" / "start_muselsl.py")], cwd=ROOT)


def run_with_openmuse():
    print("\n" + "=" * 60)
    print("STARTING WITH OPENMUSE (MUSE S ATHENA)")
    print("=" * 60)
    print()

    openmuse_cmd = find_openmuse()
    if openmuse_cmd is None:
        print("OpenMuse is not installed.")
        print("Install it with:")
        print("  python -m pip install https://github.com/DominiqueMakowski/OpenMuse/zipball/main")
        print()
        return 1

    print(f"Using OpenMuse: {openmuse_cmd}")
    print("OpenMuse only supports Muse S Athena. For Muse 2, use option 1 (muselsl).")
    print("This will start OpenMuse, wait for the Athena stream, then start the dashboard.")
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
    print("Your browser should open automatically.")
    print()
    input("Press Enter to continue...")
    print()

    return subprocess.call([sys.executable, str(ROOT / "withouttheadband.py")], cwd=ROOT)


def main():
    print_header()
    print_menu()

    choice = get_choice()

    if choice == "1":
        return run_with_muselsl()
    if choice == "2":
        return run_with_openmuse()
    if choice == "3":
        return run_simulation()

    print("\nGoodbye!")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        raise SystemExit(0)
