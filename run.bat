@echo off
call "%~dp0.venv\Scripts\activate.bat"
start "" http://localhost:5000
python "%~dp0app.py"
