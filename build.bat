@echo off
rem Builds dist\ControllerSupercharge.exe
pushd "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --uac-admin --name ControllerSupercharge ^
  --icon icon.ico --version-file version_info.txt ^
  --add-data "drivers;drivers" --add-data "icon.ico;." --add-data "icon.png;." ^
  --hidden-import pystray._win32 app.py
popd
