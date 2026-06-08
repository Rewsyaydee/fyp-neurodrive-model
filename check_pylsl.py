#!/usr/bin/env python3
"""
Check if pylsl is properly installed and working
"""

import sys
import subprocess

def check_pylsl():
    print("Checking pylsl installation...")
    print("=" * 50)

    # Check if pylsl is installed
    try:
        import pylsl
        print(f"✅ pylsl imported successfully")
        print(f"   Version: {pylsl.__version__}")
        print(f"   Location: {pylsl.__file__}")
    except ImportError as e:
        print(f"❌ Cannot import pylsl: {e}")
        print("\nPossible solutions:")
        print("1. Install pylsl: pip install pylsl")
        print("2. Check your Python environment")
        print("3. Try: pip install --upgrade pylsl")
        return False

    # Check if LSL functions are available
    try:
        import pylsl
        StreamInlet = getattr(pylsl, "StreamInlet", None)
        resolve_fn = (
            getattr(pylsl, "resolve_stream", None)
            or getattr(pylsl, "resolve_streams", None)
            or getattr(pylsl, "resolve", None)
        )
        if StreamInlet is None or resolve_fn is None:
            raise ImportError("No compatible StreamInlet/resolve function found")
        print(f"✅ LSL functions imported successfully")
    except ImportError as e:
        print(f"❌ Cannot import LSL functions: {e}")
        return False

    # Try to resolve streams (this will show if LSL is working)
    print("\nTesting LSL functionality...")
    try:
        try:
            streams = list(resolve_fn(timeout=1.0))
        except TypeError:
            streams = list(resolve_fn(wait_time=1.0))
        print(f"✅ LSL is working (found {len(streams)} streams)")
    except Exception as e:
        print(f"⚠️  LSL test failed: {e}")
        print("   This is normal if no streams are active")

    return True

def check_python_path():
    print("\nPython environment info:")
    print("-" * 30)
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version}")

    print("\nPython path:")
    for p in sys.path[:5]:  # Show first 5 paths
        print(f"  {p}")
    if len(sys.path) > 5:
        print(f"  ... and {len(sys.path) - 5} more")

def main():
    if not check_pylsl():
        print("\n❌ pylsl not properly installed")
        print("\nTo fix this issue:")
        print("1. Make sure you're in the correct Python environment")
        print("2. Install pylsl:")
        print("   pip install pylsl>=1.17.0,<2")
        print("3. If using conda:")
        print("   conda install -c conda-forge pylsl")
        print("\nThen try running connect_muse.py again")
        return 1

    check_python_path()
    print("\n✅ pylsl is ready to use!")
    return 0

if __name__ == "__main__":
    sys.exit(main())