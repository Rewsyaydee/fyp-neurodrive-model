from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADSET_ADDRESS = os.environ.get("NEURODRIVE_ATHENA_ADDRESS", "00:55:DA:BB:C4:8E").strip()
OPENMUSE_ARGS = [
    "stream",
    "--address",
    HEADSET_ADDRESS,
    "--sensors",
    "EEG",
    "ACCGYRO",
]


def find_openmuse():
    """Locate the OpenMuse executable, including virtual environments."""
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


def wait_for_lsl_stream(timeout: float = 20.0) -> bool:
    try:
        import pylsl
    except Exception as exc:
        print(f"Cannot import pylsl: {exc}")
        return False

    resolve_stream = (
        getattr(pylsl, "resolve_stream", None)
        or getattr(pylsl, "resolve_streams", None)
        or getattr(pylsl, "resolve", None)
    )
    if resolve_stream is None:
        print("No compatible pylsl resolver found.")
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            try:
                streams = list(resolve_stream(timeout=2.0) or [])
            except TypeError:
                streams = list(resolve_stream(wait_time=2.0) or [])
        except Exception as exc:
            print(f"LSL check failed: {exc}")
            streams = []

        for stream in streams:
            name = stream.name() if callable(getattr(stream, "name", None)) else getattr(stream, "name", "")
            stream_type = stream.type() if callable(getattr(stream, "type", None)) else getattr(stream, "type", "")
            channel_count = (
                stream.channel_count()
                if callable(getattr(stream, "channel_count", None))
                else getattr(stream, "channel_count", 0)
            )
            text = f"{name} {stream_type}".lower()
            # Wait specifically for an EEG stream. OpenMuse also publishes
            # ACCGYRO/PPG/BATTERY streams; starting the dashboard on one of
            # those would make the anxiety estimate use non-EEG data.
            if int(channel_count or 0) >= 4 and "eeg" in text:
                print(f"LSL stream detected: {name} ({stream_type}, {channel_count} channels)")
                return True

        print("Waiting for OpenMuse EEG stream...")

    return False


def run_dashboard_until_stream_stops(openmuse_process: subprocess.Popen) -> int | None:
    environment = os.environ.copy()
    environment["NEURODRIVE_SKIP_MUSE_CHECK"] = "1"
    environment["PYTHONUTF8"] = "1"
    dashboard_process = subprocess.Popen([sys.executable, str(ROOT / "app.py")], cwd=ROOT, env=environment)

    while dashboard_process.poll() is None:
        openmuse_exit = openmuse_process.poll()
        if openmuse_exit is not None:
            print(f"OpenMuse stopped with exit code {openmuse_exit}. Restarting stream...")
            dashboard_process.terminate()
            try:
                dashboard_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                dashboard_process.kill()
                dashboard_process.wait(timeout=5)
            return None
        time.sleep(1)

    return int(dashboard_process.returncode or 0)


def main() -> int:
    openmuse_cmd = find_openmuse()
    if openmuse_cmd is None:
        print("OpenMuse is not installed.")
        print("Install it with:")
        print(f"  {sys.executable} -m pip install https://github.com/DominiqueMakowski/OpenMuse/zipball/main")
        return 1

    command = [openmuse_cmd, *OPENMUSE_ARGS]
    print(f"Using OpenMuse: {openmuse_cmd}")
    print("Starting OpenMuse for Muse S Athena with EEG and ACC/GYRO sensors only.")
    print("If Windows has the Muse paired, remove it from Bluetooth settings first.")
    print("Press Ctrl+C to stop.")
    print()

    while True:
        print("Launching:", " ".join(command))
        try:
            process = subprocess.Popen(command, cwd=ROOT)
        except OSError as exc:
            print(f"Could not start OpenMuse: {exc}")
            print("Install it with:")
            print(f"  {sys.executable} -m pip install https://github.com/DominiqueMakowski/OpenMuse/zipball/main")
            return 1

        try:
            if wait_for_lsl_stream():
                print("Starting NeuroDrive dashboard...")
                dashboard_exit = run_dashboard_until_stream_stops(process)
                if dashboard_exit is not None:
                    process.terminate()
                    return dashboard_exit

            print("OpenMuse did not publish a usable EEG LSL stream in time.")
        except KeyboardInterrupt:
            print("\nStopping OpenMuse...")
            process.terminate()
            return 1

        exit_code = process.poll()
        if exit_code is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        else:
            print(f"OpenMuse stopped with exit code {exit_code}.")

        print("Retrying in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
