# NeuroDrive Setup Guide

## Hardware
- Muse S Athena headband (MAC: 00:55:DA:BB:C4:8E, Device: MuseS-C48E)
- Windows 11 laptop with Bluetooth 4.0+

## IMPORTANT: Do NOT pair the headband in Windows Bluetooth settings
OpenMuse connects directly via Python BLE. If Windows has the headband paired,
the connection will fail. If it is currently paired, go to:
Settings -> Bluetooth & devices -> find MuseS-C48E -> three dots -> Remove device

## Installation
pip install -r requirements.txt
pip install https://github.com/DominiqueMakowski/OpenMuse/zipball/main

## Running the app
python tools/start_stream.py

This will connect to the headband, start the EEG stream, and launch NeuroDrive
automatically. Keep this terminal open while using the app.

## If the headband disconnects
Close NeuroDrive, run python tools/start_stream.py again.
