@echo off
setlocal EnableDelayedExpansion

title PY-AUTOMATE Setup

echo.
echo  ==========================================
echo   PY-AUTOMATE  --  Environment Setup
echo  ==========================================
echo.

:: ── Locate Python ─────────────────────────────────────────────────────────

set PYTHON=
for %%C in (python python3) do (
    if not defined PYTHON (
        where %%C >nul 2>&1
        if !errorlevel! == 0 (
            set PYTHON=%%C
        )
    )
)

if not defined PYTHON (
    echo  [ERROR] Python not found on PATH.
    echo.
    echo  Install Python 3.9 or newer from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Verify minimum version (3.9+)
for /f "tokens=2 delims= " %%V in ('"%PYTHON%" --version 2^>^&1') do set PY_VER=%%V
for /f "tokens=1,2 delims=." %%A in ("%PY_VER%") do (
    set PY_MAJOR=%%A
    set PY_MINOR=%%B
)

if %PY_MAJOR% LSS 3 (
    echo  [ERROR] Python 3.9+ required. Found %PY_VER%.
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 9 (
    echo  [ERROR] Python 3.9+ required. Found %PY_VER%.
    pause
    exit /b 1
)

echo  [OK] Python %PY_VER% found at:
for /f "delims=" %%P in ('where %PYTHON%') do echo        %%P
echo.

:: ── Create virtual environment ─────────────────────────────────────────────

set VENV_DIR=%~dp0.venv

if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo  [OK] Virtual environment already exists.
) else (
    echo  [..] Creating virtual environment in .venv ...
    "%PYTHON%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
)
echo.

:: ── Activate venv ──────────────────────────────────────────────────────────

call "%VENV_DIR%\Scripts\activate.bat"

:: ── Upgrade pip silently ───────────────────────────────────────────────────

echo  [..] Upgrading pip ...
python -m pip install --upgrade pip --quiet
echo  [OK] pip up to date.
echo.

:: ── Install core dependencies ──────────────────────────────────────────────

echo  [..] Installing core dependencies ...
echo.

pip install flask flask-cors

if errorlevel 1 (
    echo.
    echo  [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo  [OK] Core dependencies installed.
echo.

:: ── Create required project folders ───────────────────────────────────────

echo  [..] Checking project folders ...

for %%D in (plugins workspaces history static templates) do (
    if not exist "%~dp0%%D\" (
        mkdir "%~dp0%%D"
        echo  [+] Created: %%D\
    ) else (
        echo  [OK] Exists:  %%D\
    )
)

echo.

:: ── Move static assets into Flask's expected layout ───────────────────────
:: Flask serves static files from /static and templates from /templates.
:: If index.html is sitting next to app.py, move it to templates/.
:: If styles.css / scripts.js are next to app.py, move them to static/.

set MOVED=0

if exist "%~dp0index.html" (
    if not exist "%~dp0templates\index.html" (
        move "%~dp0index.html" "%~dp0templates\index.html" >nul
        echo  [+] Moved index.html  ->  templates\index.html
        set MOVED=1
    )
)

for %%F in (styles.css scripts.js) do (
    if exist "%~dp0%%F" (
        if not exist "%~dp0static\%%F" (
            move "%~dp0%%F" "%~dp0static\%%F" >nul
            echo  [+] Moved %%F  ->  static\%%F
            set MOVED=1
        )
    )
)

if %MOVED% == 0 (
    echo  [OK] Static assets already in place.
)

echo.

:: ── Copy plugin files into plugins\ if they are next to app.py ────────────

set PLUGINS_MOVED=0
for %%F in ("%~dp0endmill_utils.py" "%~dp0laser_utils.py") do (
    if exist "%%F" (
        move "%%F" "%~dp0plugins\" >nul
        echo  [+] Moved %%~nxF  ->  plugins\
        set PLUGINS_MOVED=1
    )
)
if %PLUGINS_MOVED% == 0 (
    echo  [OK] Plugin files already in plugins\
)

echo.

:: ── Write launcher scripts ──────────────────────────────────────────────────

set LAUNCHER=%~dp0run.bat
if not exist "%LAUNCHER%" (
    (
        echo @echo off
        echo call "%%~dp0.venv\Scripts\activate.bat"
        echo start "" http://localhost:5000
        echo python "%%~dp0app.py"
    ) > "%LAUNCHER%"
    echo  [+] Created run.bat  -- CMD-window launcher.
) else (
    echo  [OK] run.bat already exists.
)

set VBS_LAUNCHER=%~dp0launch.vbs
if not exist "%VBS_LAUNCHER%" (
    (
        echo Dim sh, base
        echo Set sh = CreateObject("WScript.Shell"^)
        echo base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"^)^)
        echo sh.Run """" ^& base ^& ".venv\Scripts\pythonw.exe"" """ ^& base ^& "app.py""", 0, False
        echo WScript.Sleep 2000
        echo sh.Run "http://localhost:5000"
    ) > "%VBS_LAUNCHER%"
    echo  [+] Created launch.vbs  -- no-window launcher (recommended^).
) else (
    echo  [OK] launch.vbs already exists.
)

echo.

:: ── Summary ────────────────────────────────────────────────────────────────

echo  ==========================================
echo   Setup complete.
echo  ==========================================
echo.
echo  To start PY-AUTOMATE:
echo.
echo    launch.vbs    (double-click -- no CMD window, opens browser automatically)
echo    run.bat       (CMD window stays open -- useful if you need to see output)
echo.
echo  Or manually:
echo.
echo    .venv\Scripts\activate
echo    python app.py
echo.
echo  The app will be available at http://localhost:5000
echo.
echo  Tip: enable "Server logs in console" in the Settings panel to see
echo       Flask output inside the app's own output console.
echo.

pause
endlocal
