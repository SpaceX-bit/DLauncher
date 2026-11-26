; Установщик DLauncher (Inno Setup 6). Собирается из GitHub Actions: iscc /DAppVersion=2.0.0 packaging\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId — постоянный: новая версия ставится поверх старой, а не рядом
AppId={{6F0B1C54-3D7A-4E5B-9C21-D1A0C4E8B7F3}
AppName=DLauncher
AppVersion={#AppVersion}
AppPublisher=DpaceUK
VersionInfoVersion={#AppVersion}.0
VersionInfoProductName=DLauncher
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany=DpaceUK
VersionInfoDescription=DLauncher installer
DefaultDirName={autopf}\DLauncher
DefaultGroupName=DLauncher
; страница выбора папки (и диска) показывается всегда
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=DLauncher-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\DLauncher.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
UsePreviousAppDir=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\DLauncher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DLauncher"; Filename: "{app}\DLauncher.exe"
Name: "{autodesktop}\DLauncher"; Filename: "{app}\DLauncher.exe"; Tasks: desktopicon

[Run]
; «Запустить DLauncher» после установки (при тихом обновлении лаунчер перезапускается через RestartApplications)
Filename: "{app}\DLauncher.exe"; Description: "{cm:LaunchProgram,DLauncher}"; Flags: nowait postinstall skipifsilent
