@echo off
chcp 65001 >nul
title Peaklab - @@MODEL@@ - Монгол хэл
cd /d "%~dp0"

rem Opened from INSIDE the zip? Windows then copies only this one file to a temp folder.
if not exist "@@EXE@@" goto :notextracted

echo.
echo   Peaklab - @@MODEL@@ - Монгол хэл
echo   Суулгагчийг нээж байна...
start "" "@@EXE@@"
exit /b 0

:notextracted
echo.
echo   Суулгагч файл олдсонгүй.
echo.
echo   Та zip файлаа задлаагүй байна. Ингэж хийнэ үү:
echo     1. zip файл дээр хулганы баруун товчийг дарна
echo     2. "Extract All..." (Бүгдийг задлах) гэж сонгоод "Extract" дарна
echo     3. Гарч ирсэн хавтас доторх энэ файлыг дахин нээнэ
echo.
pause
exit /b 1
