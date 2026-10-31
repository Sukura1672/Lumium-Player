@echo off
REM Сборка Lumen Player: exe (PyInstaller) + установщик (Inno Setup).
REM Нужно: Python 3.10+, 7-Zip (7z в PATH), Inno Setup 6 (iscc в PATH).
setlocal
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv || goto :err
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt || goto :err

REM --- libmpv (mpv-2.dll) ---
if not exist mpv-2.dll (
    echo.
    echo Скачайте "mpv-dev-x86_64-*.7z" с https://github.com/shinchiro/mpv-winbuild-cmake/releases
    echo и положите файл mpv-2.dll ^(в архиве libmpv-2.dll -^> переименуйте в mpv-2.dll^) рядом с build.bat.
    goto :err
)

pyinstaller --noconfirm --clean --windowed --name LumenPlayer ^
    --add-binary "mpv-2.dll;." main.py || goto :err

iscc installer.iss || goto :err
echo.
echo Готово: Output\LumenPlayer-Setup.exe
exit /b 0

:err
echo Ошибка сборки.
exit /b 1
