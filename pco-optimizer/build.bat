@echo off
REM Compila PCO OPTIMIZATION APP en un solo .exe (requiere Python 3.10+ para Windows).
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
  --name "PCO_Optimization_App" --icon "assets\icon.ico" ^
  --add-data "assets\icon.ico;assets" --add-data "assets\badge_96.png;assets" ^
  pco_app.py || exit /b 1
echo.
echo Listo: dist\PCO_Optimization_App.exe
