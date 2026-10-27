@echo off
:: Varin Sniper — proxyless checker (multi-source, zero-false-flag)
:: Chain: playerdb.co -> api.minecraftservices.com (lookup/name) -> api.mojang.com
:: Status code dipercaya, BUKAN isi body (body 404 resmi mengandung kata "name").
:: TANPA proxy. TANPA substring guessing. Bypass 429 = pindah sumber otomatis.
chcp 65001>nul
setlocal enabledelayedexpansion

:retry
cls
title Varin Sniper Name Checker
echo.
echo  █▀▄▀█ █ █▄ █ █▀▀ █▀▀ █▀█ ▄▀█ █▀▀ ▀█▀   █▄ █ ▄▀█ █▀▄▀█ █▀▀   █▀▀ █ █ █▀▀ █▀▀ █▄▀ █▀▀ █▀█
echo  █ ▀ █ █ █ ▀█ ██▄ █▄▄ █▀▄ █▀█ █▀    █    █ ▀█ █▀█ █ ▀ █ ██▄   █▄▄ █▀█ ██▄ █▄▄ █ █ ██▄ █▀▄
echo.
echo  Drag the combo file (.txt) to this consoleecho.
set /p combo="[?] Path: "
if not exist "%combo%" echo  [-] File not found & pause>nul & goto retry
echo  [+] Combo loaded
set /p namemc="[?] Open NameMC on hit? (Y/N): "
echo  [+] Starting
echo.

if exist hits.txt del hits.txt /q

for /F "usebackq tokens=*" %%M in ("%combo%") do (
    set "CODE="
    set "CODE2="
    rem --- sumber 1: playerdb.co (limit sangat longgar) ---
    for /F %%C in ('curl -s -o "%temp%\mclogs.txt" -w "%%{http_code}" -A "MC-Sniper/2.2" https://playerdb.co/api/player/minecraft/%%M') do set "CODE=%%C"
    if "!CODE!"=="200" (
        echo  [-] %%M
    ) else if "!CODE!"=="400" (
        rem --- konfirmasi live sumber 2: minecraftservices lookup/name ---
        for /F %%D in ('curl -s -o "%temp%\mclogs2.txt" -w "%%{http_code}" https://api.minecraftservices.com/minecraft/profile/lookup/name/%%M') do set "CODE2=%%D"
        if "!CODE2!"=="404" (
            echo  [+] %%M
            echo %%M>>hits.txt
            if /i "%namemc%"=="Y" start "" https://namemc.com/search?q=%%M
        ) else if "!CODE2!"=="429" (
            echo  [!] %%M  ^(verify 429 - recheck later^)
        ) else (
            echo  [-] %%M  ^(profile found live^)
        )
    ) else (
        rem --- fallback: mojang legacy ---
        for /F %%D in ('curl -s -o "%temp%\mclogs3.txt" -w "%%{http_code}" https://api.mojang.com/users/profiles/minecraft/%%M') do set "CODE2=%%D"
        if "!CODE2!"=="204" (
            echo  [+] %%M
            echo %%M>>hits.txt
            if /i "%namemc%"=="Y" start "" https://namemc.com/search?q=%%M
        ) else if "!CODE2!"=="404" (
            echo  [+] %%M
            echo %%M>>hits.txt
            if /i "%namemc%"=="Y" start "" https://namemc.com/search?q=%%M
        ) else (
            echo  [!] %%M  ^(HTTP !CODE2! - limited / error^)
        )
    )
)

echo.
echo  Valid names saved in hits.txt
pause>nul
exit
