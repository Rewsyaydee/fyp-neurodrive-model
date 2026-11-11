#!/usr/bin/env python3
"""
NeuroDrive - Muse Headband Connection Script
Handles the search and connection to Muse Athena S headband
"""

import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional

try:
    import pylsl

    StreamInlet = getattr(pylsl, "StreamInlet", None)
    resolve_stream = (
        getattr(pylsl, "resolve_stream", None)
        or getattr(pylsl, "resolve_streams", None)
        or getattr(pylsl, "resolve", None)
    )
except Exception:
    # Do not exit here — allow graceful fallback to simulation mode later
    StreamInlet = None
    resolve_stream = None

# Connection settings
DISCOVERY_TIMEOUT = 5.0
DISCOVERY_RETRY_DELAY = 2.0
CONNECTION_TIMEOUT = 10.0
MIN_CHANNELS = 4


def _resolve_lsl_streams(timeout=None):
    if resolve_stream is None:
        return []

    try:
        if timeout is None:
            return list(resolve_stream() or [])
        try:
            return list(resolve_stream(timeout=timeout) or [])
        except TypeError:
            return list(resolve_stream(wait_time=timeout) or [])
    except Exception:
        return []


def _stream_value(stream_info, field_name, default=""):
    try:
        value = getattr(stream_info, field_name, default)
        if callable(value):
            value = value()
        return default if value is None else value
    except Exception:
        return default


def _looks_like_muse_stream(stream_info):
    name = str(_stream_value(stream_info, "name", "")).lower()
    stream_type = str(_stream_value(stream_info, "type", "")).lower()
    channel_count = int(_stream_value(stream_info, "channel_count", 0) or 0)
    return "muse" in name or "muse" in stream_type or ("eeg" in stream_type and channel_count >= MIN_CHANNELS)

def clear_screen():
    """Clear the terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    """Print connection header"""
    print("=" * 60)
    print("NEURODRIVE - Muse Headband Connection")
    print("=" * 60)
    print()

def print_status(message, symbol="⏳"):
    """Print status message with symbol"""
    print(f"{symbol} {message}")
    sys.stdout.flush()

def print_success(message):
    """Print success message"""
    print(f"✅ {message}")

def print_error(message):
    """Print error message"""
    print(f"❌ {message}")

def animate_search():
    """Animate searching indicator"""
    for frame in ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]:
        yield frame

def discover_muse_stream():
    """Discover available Muse streams"""
    print_status("Scanning for Muse streams...")

    streams = []
    attempt = 0

    while not streams:
        try:
            found_streams = _resolve_lsl_streams(timeout=DISCOVERY_TIMEOUT)

            # Filter for Muse streams
            muse_streams = []
            for stream in found_streams:
                name = str(_stream_value(stream, 'name', 'Unknown'))

                if _looks_like_muse_stream(stream):
                    score = score_muse_stream(stream)
                    if score > 0:
                        muse_streams.append((score, stream, name))

            if muse_streams:
                # Sort by score (best first)
                muse_streams.sort(key=lambda x: x[0], reverse=True)
                streams = muse_streams

        except Exception as e:
            print_error(f"Scan error: {e}")

        if not streams:
            attempt += 1
            print_status(f"No streams found. Retrying... ({attempt})")
            time.sleep(DISCOVERY_RETRY_DELAY)

    return streams

def score_muse_stream(stream):
    """Score a stream to determine if it's a valid Muse stream"""
    score = 0
    name = str(_stream_value(stream, 'name', ''))
    stream_type = str(_stream_value(stream, 'type', ''))

    # Check name
    if 'muse' in name.lower():
        score += 100
    if 'athena' in name.lower():
        score += 50

    # Check type
    if 'eeg' in stream_type.lower():
        score += 30
    if 'muse' in stream_type.lower():
        score += 30

    # Check channel count
    try:
        channel_count = int(_stream_value(stream, 'channel_count', 0) or 0)
        if channel_count >= MIN_CHANNELS:
            score += 20
        else:
            score -= 10
    except:
        score -= 5

    return score

def connect_to_stream(stream_info):
    """Attempt to connect to a specific stream"""
    name = str(_stream_value(stream_info, 'name', 'Unknown'))
    print_status(f"Connecting to {name}...")

    try:
        inlet = StreamInlet(stream_info, max_buflen=8, recover=True)

        # Try to pull a sample to verify connection
        print_status("Establishing data stream...")
        start_time = time.time()

        while time.time() - start_time < CONNECTION_TIMEOUT:
            try:
                sample, timestamp = inlet.pull_sample(timeout=0.5)
                if sample is not None:
                    print_success(f"Connected! Receiving data from {name}")
                    return inlet
            except:
                pass

        print_error("Connection timeout - no data received")
        return None

    except Exception as e:
        print_error(f"Connection failed: {e}")
        return None

def verify_stream_quality(inlet, duration=5.0):
    """Verify stream quality by checking data consistency"""
    print_status("Verifying signal quality...")

    sample_count = 0
    start_time = time.time()
    channels = 0

    try:
        channels = inlet.channel_count
        while time.time() - start_time < duration:
            sample, _ = inlet.pull_sample(timeout=1.0)
            if sample:
                sample_count += 1

        if sample_count > 0:
            rate = sample_count / duration
            print_success(f"Signal quality OK - {channels} channels, ~{rate:.1f} Hz")
            return True
        else:
            print_error("No data received during verification")
            return False

    except Exception as e:
        print_error(f"Stream verification failed: {e}")
        return False

def main():
    """Main connection routine"""
    import os
    global StreamInlet, resolve_stream

    clear_screen()
    print_header()

    print("This script will search for and connect to your Muse headband.")
    print("Make sure your headband is:")
    print("  NOTE: Do not pair it in Windows Bluetooth settings; OpenMuse connects directly.")
    print("  • Turned on")
    print("  • Connected via Bluetooth to your computer")
    print("  • Streaming (if using OpenMuse, run: OpenMuse stream)")
    print()

    input("Press Enter to start searching for Muse headband...")
    print()

    # If pylsl isn't available, offer fallback to simulation mode
    if resolve_stream is None:
        print_error("pylsl is not available in this Python environment.")
        print()
        choice = input("Attempt to install pylsl now? [Y]es / [S]imulation / [N]o: ").strip().lower()
        if choice in ("", "y", "yes"):
            # Try to install using pip
            try:
                import subprocess
                print_status("Installing pylsl via pip...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pylsl"])
                # Try importing into module scope
                try:
                    import pylsl as _pylsl
                    StreamInlet = getattr(_pylsl, "StreamInlet", None)
                    resolve_stream = (
                        getattr(_pylsl, "resolve_stream", None)
                        or getattr(_pylsl, "resolve_streams", None)
                        or getattr(_pylsl, "resolve", None)
                    )
                    if StreamInlet is None or resolve_stream is None:
                        raise RuntimeError("No compatible LSL resolver found in pylsl")
                    print_success("pylsl installed and imported successfully.")
                except Exception as e:
                    print_error(f"Installed but failed to import pylsl: {e}")
                    print()
                    fallback = input("Run simulation mode instead? [Y/n]: ").strip().lower()
                    if fallback in ("", "y", "yes"):
                        os.system(f"{sys.executable} withouttheadband.py")
                        return True
                    return False
            except Exception as e:
                print_error(f"Automatic pip install failed: {e}")
                print()
                print("If pip install fails, try installing with conda:")
                print("  conda install -c conda-forge pylsl")
                fallback = input("Run simulation mode instead? [Y/n]: ").strip().lower()
                if fallback in ("", "y", "yes"):
                    os.system(f"{sys.executable} withouttheadband.py")
                    return True
                return False
        elif choice.startswith('s'):
            print("Starting simulation mode (without headband)...")
            os.system(f"{sys.executable} withouttheadband.py")
            return True
        else:
            print("Install pylsl (pip install pylsl) to use a real headband.")
            return False

    # Discover streams
    streams = discover_muse_stream()

    if not streams:
        print_error("No Muse streams found!")
        print()
        print("Troubleshooting:")
        print("1. Ensure your Muse headband is on and paired via Bluetooth")
        print("2. Start streaming with: OpenMuse stream --address <headset-address>")
        print("3. Check if the headset is connected to another application")
        print()
        return False

    # Show discovered streams
    print(f"Found {len(streams)} potential stream(s):")
    for i, (score, stream, name) in enumerate(streams):
        print(f"  {i+1}. {name} (score: {score})")
    print()

    # Use the best stream
    _, stream_info, stream_name = streams[0]
    print(f"Using best match: {stream_name}")

    # Connect
    inlet = connect_to_stream(stream_info)
    if not inlet:
        return False

    # Verify quality
    if not verify_stream_quality(inlet):
        inlet.close_stream()
        return False

    print()
    print_success("Connection established successfully!")
    print()

    # Save connection info for the main app
    connection_file = Path(__file__).parent / "muse_connection.txt"
    with connection_file.open('w', encoding='utf-8') as f:
        f.write(f"Connected to: {stream_name}\n")
        f.write(f"Channels: {inlet.channel_count}\n")
        f.write(f"Status: Connected\n")

    print("Connection info saved. Starting dashboard...")
    print()
    print("-" * 60)

    # Keep the stream open for the main app
    try:
        print("✓ Stream active. Press Ctrl+C to stop...")
        print()
        print("Starting web dashboard in 3 seconds...")
        time.sleep(3)

        # Import and run the main app
        from app import main as app_main
        print("Launching NeuroDrive Dashboard...")
        print("Dashboard URL: http://localhost:5000")
        print()

        app_main()

    except KeyboardInterrupt:
        print("\nStopping...")
        if inlet:
            inlet.close_stream()
        return False
    except Exception as e:
        print_error(f"Failed to start dashboard: {e}")
        if inlet:
            inlet.close_stream()
        return False

    return True

if __name__ == "__main__":
    try:
        success = main()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nConnection cancelled.")
        sys.exit(1)
