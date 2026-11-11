@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
chcp 65001 >nul
cd /d "%~dp0"
title NeuroDrive Launcher

rem Include per-user Python Scripts folders (created by pip install --user).
rem This uses CALL instead of a parenthesized block so paths containing
rem parentheses (for example "...\FINALYEARPROJECTVOL2 (2)\...") are safe.
for /d %%D in ("%APPDATA%\Python\Python*") do call :add_scripts_path "%%~fD"

echo ============================================================
echo NEURODRIVE - EEG Anxiety Monitoring System
echo ============================================================
echo.

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_OPENMUSE=%VENV%\Scripts\OpenMuse.exe"

rem Pinned to the tested OpenMuse 0.1.8 commit so new devices get the same version.
set "OPENMUSE_URL=https://github.com/DominiqueMakowski/OpenMuse/zipball/a9be252188321e269537eabf609bc207be293f8c"

rem Reuse a working project-local environment when possible.
if not exist "%VENV_PY%" goto :setup
"%VENV_PY%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :rebuild_venv
"%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto :rebuild_venv
"%VENV_PY%" -c "import pylsl, flask, flask_socketio, OpenMuse" >nul 2>&1
if errorlevel 1 goto :install_deps
if not exist "%VENV_OPENMUSE%" goto :install_deps
goto :run_app

:rebuild_venv
echo Existing virtual environment is not usable. Rebuilding...
rmdir /s /q "%VENV%"
goto :setup

:setup
echo First run setup: downloading Python (if needed) and dependencies.
echo Internet access is required for the first run.
echo.

set "BOOT_PY="

call :try_py_cmd "py -3.12"
if defined BOOT_PY goto :got_python
call :try_py_cmd "py -3.13"
if defined BOOT_PY goto :got_python
call :try_py_cmd "py -3.14"
if defined BOOT_PY goto :got_python
call :try_py_cmd "python"
if defined BOOT_PY goto :got_python

call :try_py_path "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined BOOT_PY goto :got_python
call :try_py_path "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined BOOT_PY goto :got_python
call :try_py_path "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if defined BOOT_PY goto :got_python
call :try_py_path "%ProgramFiles%\Python312\python.exe"
if defined BOOT_PY goto :got_python
call :try_py_path "%ProgramFiles%\Python313\python.exe"
if defined BOOT_PY goto :got_python
call :try_py_path "%ProgramFiles%\Python314\python.exe"
if defined BOOT_PY goto :got_python
call :try_py_path "C:\Python312\python.exe"
if defined BOOT_PY goto :got_python
call :try_py_path "C:\Python313\python.exe"
if defined BOOT_PY goto :got_python
call :try_py_path "C:\Python314\python.exe"
if defined BOOT_PY goto :got_python

echo No Python 3.12+ found. Downloading Python 3.12.10...
set "PY_INSTALLER=%TEMP%\neurodrive-python-3.12.10-amd64.exe"
set "PY_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"

if not exist "%PY_INSTALLER%" goto :download_python
for %%A in ("%PY_INSTALLER%") do if %%~zA GEQ 1000000 goto :install_python
del /q "%PY_INSTALLER%"

:download_python
echo Downloading: %PY_URL%
curl.exe -L --fail --retry 3 --retry-delay 3 -o "%PY_INSTALLER%" "%PY_URL%"
if not exist "%PY_INSTALLER%" goto :try_powershell
for %%A in ("%PY_INSTALLER%") do if %%~zA LSS 1000000 goto :try_powershell
goto :install_python

:try_powershell
echo curl failed; trying PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%'"

:verify_download
if not exist "%PY_INSTALLER%" goto :python_download_failed
for %%A in ("%PY_INSTALLER%") do if %%~zA LSS 1000000 goto :python_download_failed

:install_python
echo Installing Python 3.12.10 for the current user...
start "" /wait "%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 InstallLauncherAllUsers=0 Include_pip=1 Include_test=0 Shortcuts=0
set "PY_RC=%ERRORLEVEL%"
if "%PY_RC%"=="0" goto :python_installed
if "%PY_RC%"=="3010" goto :python_installed
if "%PY_RC%"=="1638" goto :python_installed
echo Python installer returned code %PY_RC%.
goto :python_install_failed

:python_installed
set "BOOT_PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%BOOT_PY%" set "BOOT_PY=%ProgramFiles%\Python312\python.exe"
if not exist "%BOOT_PY%" set "BOOT_PY=C:\Python312\python.exe"
if not exist "%BOOT_PY%" goto :python_install_failed

:got_python
echo Using Python: "%BOOT_PY%"
"%BOOT_PY%" -c "import sys; print(sys.version)" 2>nul

:create_venv
if not exist "%VENV_PY%" goto :make_venv
"%VENV_PY%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :remove_venv
goto :install_deps

:remove_venv
echo Rebuilding unusable virtual environment...
rmdir /s /q "%VENV%"

:make_venv
echo Creating virtual environment: "%VENV%"
"%BOOT_PY%" -m venv "%VENV%"
if errorlevel 1 goto :venv_failed
if not exist "%VENV_PY%" goto :venv_failed

:install_deps
echo Installing dependencies. This may take several minutes on the first run...
set "PATH=%VENV%\Scripts;%PATH%"
set "NEURODRIVE_OPENMUSE=%VENV_OPENMUSE%"

"%VENV_PY%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :upgrade_pip
"%VENV_PY%" -m ensurepip --upgrade

:upgrade_pip
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel --retries 5 --timeout 60 --no-input
if not errorlevel 1 goto :check_python_version
echo Warning: could not upgrade pip/setuptools/wheel; continuing.

:check_python_version
set "VENV_IS_312=0"
"%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)" >nul 2>&1
if not errorlevel 1 set "VENV_IS_312=1"
if not "%VENV_IS_312%"=="1" goto :install_athena

echo Installing full project requirements (Muse 2 and Athena)...
"%VENV_PY%" -m pip install -r "%ROOT%requirements.txt" --retries 5 --timeout 60 --prefer-binary --no-input
if not errorlevel 1 goto :install_openmuse
echo Full requirements failed; falling back to the Athena-only set...

:install_athena
echo Installing Athena-only requirements...
"%VENV_PY%" -m pip install -r "%ROOT%requirements-athena.txt" --retries 5 --timeout 60 --prefer-binary --no-input
if errorlevel 1 goto :deps_failed

:install_openmuse
echo Installing OpenMuse from GitHub...
"%VENV_PY%" -m pip install --retries 5 --timeout 60 --prefer-binary --no-input "%OPENMUSE_URL%"
if errorlevel 1 goto :openmuse_failed
if not exist "%VENV_OPENMUSE%" goto :openmuse_failed

"%VENV_PY%" -c "import pylsl, flask, flask_socketio, OpenMuse" >nul 2>&1
if errorlevel 1 goto :deps_failed

> "%VENV%\.deps-ok" echo installed %DATE% %TIME%
echo.
echo Setup complete.
echo.

:run_app
set "PATH=%VENV%\Scripts;%PATH%"
set "NEURODRIVE_OPENMUSE=%VENV_OPENMUSE%"
echo Using Python: "%VENV_PY%"
echo.
"%VENV_PY%" "%ROOT%start.py"
set "EXITCODE=%ERRORLEVEL%"
if "%EXITCODE%"=="0" exit /b 0
echo.
echo NeuroDrive exited with code %EXITCODE%.
pause
exit /b %EXITCODE%

:add_scripts_path
if exist "%~1\Scripts\OpenMuse.exe" set "PATH=%~1\Scripts;%PATH%"
goto :eof

:try_py_cmd
set "BOOT_PY="
%~1 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
for /f "usebackq delims=" %%P in (`%~1 -c "import sys; print(sys.executable)" 2^>nul`) do set "BOOT_PY=%%P"
goto :eof

:try_py_path
if not exist "%~1" goto :eof
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
set "BOOT_PY=%~1"
goto :eof

:python_download_failed
echo.
echo ERROR: Could not download Python 3.12.10.
echo Check your internet connection and try again, or install Python 3.12 manually:
echo   https://www.python.org/downloads/
echo During installation, select "Add python.exe to PATH".
goto :fallback_or_exit

:python_install_failed
echo.
echo ERROR: Python 3.12 could not be installed automatically.
echo Install it manually from https://www.python.org/downloads/ and run this file again.
goto :fallback_or_exit

:venv_failed
echo.
echo ERROR: Could not create the virtual environment at "%VENV%".
goto :fallback_or_exit

:deps_failed
echo.
echo ERROR: Python dependencies could not be installed.
echo Check your internet connection and run this file again.
goto :fallback_or_exit

:openmuse_failed
echo.
echo ERROR: OpenMuse could not be installed from GitHub.
echo Check your internet connection and try again.
goto :fallback_or_exit

:fallback_or_exit
echo.
echo Trying the existing system Python as a fallback...
py -3 -c "import flask, flask_socketio, pylsl, OpenMuse" >nul 2>&1
if not errorlevel 1 goto :fallback_py
python -c "import flask, flask_socketio, pylsl, OpenMuse" >nul 2>&1
if not errorlevel 1 goto :fallback_python
echo No usable Python environment was found.
echo Install Python 3.12 from https://www.python.org/downloads/ and try again.
pause
exit /b 1

:fallback_py
py -3 "%ROOT%start.py"
set "FALLBACK_RC=%ERRORLEVEL%"
if "%FALLBACK_RC%"=="0" exit /b 0
pause
exit /b %FALLBACK_RC%

:fallback_python
python "%ROOT%start.py"
set "FALLBACK_RC=%ERRORLEVEL%"
if "%FALLBACK_RC%"=="0" exit /b 0
pause
exit /b %FALLBACK_RC%
