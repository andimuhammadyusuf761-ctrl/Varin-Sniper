@echo off
REM ============================================================
REM  MC-Sniper - one-click build Windows .exe
REM  Requirements: Python 3.10+ installed and in PATH
REM  Output      : dist\MC-Sniper.exe
REM ============================================================
setlocal

echo.
echo [1/3] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
if errorlevel 1 goto fail

echo.
echo [2/3] Building executable (this takes a few minutes)...
pyinstaller --clean --noconfirm MC-Sniper.spec
if errorlevel 1 goto fail

echo.
echo [3/3] Done!
echo    Output : %cd%\dist\MC-Sniper.exe
echo.
echo  Copy dist\MC-Sniper.exe anywhere (plus success.mp3 if you want
echo  sound notifications) and double-click to run.
goto end

:fail
echo.
echo BUILD FAILED - see the error messages above.
exit /b 1

:end
pause
