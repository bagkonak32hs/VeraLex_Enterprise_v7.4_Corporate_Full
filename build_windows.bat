
@echo off
pip install --upgrade pip
pip install pyinstaller
pyinstaller --noconsole --name VeraLex --icon assets\icon.ico app.py
echo Dist: dist\VeraLex\VeraLex.exe
pause
