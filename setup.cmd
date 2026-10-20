@echo off
setlocal
pushd "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python_fallback
py -3 -m venv .venv
goto venv_created
:python_fallback
python -m venv .venv
:venv_created
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m unittest -v
if errorlevel 1 goto failed
echo Setup and tests completed. See README.md for run commands.
popd
exit /b 0
:failed
echo Setup incomplete. Read the error above.
popd
exit /b 1
