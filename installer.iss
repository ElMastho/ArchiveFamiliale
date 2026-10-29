; Installateur Windows d'Archive Familiale (Inno Setup 6).
; Construit par build_exe.bat ou par la CI :  ISCC /DAppVersion=2.1.0 installer.iss
; Installation pour l'utilisateur seul (%LOCALAPPDATA%\Programs), sans droits administrateur :
; le programme peut ainsi se mettre à jour lui-même.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{F326F30E-FE5B-4B50-A07D-4FD2F5F2581E}
AppName=Archive Familiale
AppVersion={#AppVersion}
AppVerName=Archive Familiale {#AppVersion}
AppPublisher=Archive Familiale
AppPublisherURL=https://github.com/ElMastho/ArchiveFamiliale
AppUpdatesURL=https://github.com/ElMastho/ArchiveFamiliale/releases
DefaultDirName={autopf}\ArchiveFamiliale
DefaultGroupName=Archive Familiale
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=ArchiveFamiliale-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ArchiveFamiliale.exe
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; anciennes bibliothèques d'une version précédente
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\ArchiveFamiliale\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Archive Familiale"; Filename: "{app}\ArchiveFamiliale.exe"
Name: "{autodesktop}\Archive Familiale"; Filename: "{app}\ArchiveFamiliale.exe"; Tasks: desktopicon

[Run]
; installation normale : case « Lancer Archive Familiale » à la fin
Filename: "{app}\ArchiveFamiliale.exe"; Description: "{cm:LaunchProgram,Archive Familiale}"; Flags: nowait postinstall skipifsilent
; mise à jour automatique (installation silencieuse) : on relance le programme
Filename: "{app}\ArchiveFamiliale.exe"; Flags: nowait; Check: WizardSilent
