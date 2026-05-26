@echo off
cd /d "%~dp0"
set "PYTHON_EXE=%TG_DIGEST_PYTHON%"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
"%PYTHON_EXE%" -m tg_portfolio_bot run --config config.toml --dry-run %*
