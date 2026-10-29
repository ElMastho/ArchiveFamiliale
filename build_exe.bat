@echo off
rem Genere dans dist\ :
rem   ArchiveFamiliale\ArchiveFamiliale.exe   (programme, mode dossier)
rem   ArchiveFamiliale.zip                    (version portable)
rem   ArchiveFamiliale-Setup.exe              (installateur Windows, si Inno Setup 6 est installe)
rem   *.sha256                                (empreintes, utilisees par la mise a jour automatique)
rem Mode dossier (--onedir) : pas de decompression au lancement, donc pas de conflit avec l'antivirus.
setlocal
cd /d "%~dp0"

if not exist .build-venv (
    echo Creation de l'environnement de construction...
    py -3 -m venv .build-venv || python -m venv .build-venv || goto :error
)
call .build-venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip pyinstaller sv-ttk qrcode || goto :error

echo.
echo Tests...
python -m unittest test_archive || goto :error

for /f %%v in ('python -c "import archive; print(archive.VERSION)"') do set "VERSION=%%v"
echo.
echo Construction de l'executable, version %VERSION%...
rem Fichiers intermediaires hors du projet : seul dist\ contient un programme utilisable.
set "WORK=%TEMP%\ArchiveFamiliale-build"
pyinstaller --noconfirm --clean --onedir --windowed ^
    --name ArchiveFamiliale ^
    --workpath "%WORK%" --specpath "%WORK%" ^
    --add-data "%~dp0README.md;." ^
    --collect-data sv_ttk ^
    archive_gui.py || goto :error
if exist build rmdir /s /q build
if exist ArchiveFamiliale.spec del /q ArchiveFamiliale.spec

echo.
echo Creation du zip portable...
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\ArchiveFamiliale' -DestinationPath 'dist\ArchiveFamiliale.zip'" || goto :error

set "ISCC="
for %%p in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do (
    if exist %%p set "ISCC=%%~p"
)
if defined ISCC (
    echo.
    echo Creation de l'installateur...
    "%ISCC%" /Q /DAppVersion=%VERSION% installer.iss || goto :error
) else (
    echo.
    echo Inno Setup 6 introuvable : pas d'installateur ^(winget install JRSoftware.InnoSetup^).
)

echo.
echo Empreintes SHA-256...
powershell -NoProfile -Command "Get-ChildItem -Path dist\* -Include *.zip,*.exe -File |ForEach-Object { '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name | Set-Content -Encoding ascii -NoNewline ($_.FullName + '.sha256') }" || goto :error

echo.
echo OK : version %VERSION% dans dist\
dir /b dist
goto :eof

:error
echo.
echo ECHEC de la construction.
exit /b 1
