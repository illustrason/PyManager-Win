@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PyManager

rem ---------------------------------------------------------------------------
rem  PyManager - demarrage autonome
rem  1er lancement : cree .venv, installe les dependances des scripts, ouvre l'interface.
rem  Lancements suivants : ouvre directement l'interface.
rem  Option --reset : supprime et recree l'environnement (utilise par l'onglet Sante).
rem ---------------------------------------------------------------------------

if /i "%~1"=="--reset" (
    echo Recreation de l'environnement...
    ping -n 3 127.0.0.1 >nul
    if exist ".venv" rmdir /s /q ".venv"
    if exist ".venv" (
        echo Impossible de supprimer .venv. Fermez les scripts en cours puis relancez start.bat.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\pythonw.exe" goto :setup
if not exist ".venv\.pm_ready" goto :install
goto :run

:setup
set "PY="
set "PREF="
if exist ".python-version" set /p PREF=<".python-version"
if defined PREF call :try "py -%PREF%"
if not defined PY call :try "py -3"
if not defined PY call :try "python"
if not defined PY call :try "python3"
if not defined PY (
    echo [ERREUR] Python 3.10 ou plus recent, avec tkinter, est introuvable.
    echo Installez-le depuis https://www.python.org/downloads/ puis relancez start.bat.
    pause
    exit /b 1
)
echo Creation de l'environnement virtuel avec : %PY%
%PY% -m venv .venv
if errorlevel 1 (
    echo [ERREUR] Impossible de creer l'environnement virtuel.
    pause
    exit /b 1
)

:install
echo Installation des dependances des scripts...
".venv\Scripts\python.exe" -m pymanager --install
if errorlevel 1 (
    echo.
    echo [ATTENTION] Certaines dependances n'ont pas pu etre installees.
    echo Vous pourrez relancer l'installation depuis l'onglet Sante de PyManager.
    pause
)
> ".venv\.pm_ready" echo ok

:run
start "" ".venv\Scripts\pythonw.exe" -m pymanager
exit /b 0

:try
if defined PY exit /b 0
%~1 -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%~1"
exit /b 0
