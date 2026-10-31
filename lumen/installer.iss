; Inno Setup 6 — установщик Lumen Player
#define AppName "Lumen Player"
#define AppVersion "1.0.0"
#define AppExe "LumenPlayer.exe"

[Setup]
AppId={{6E1F7B52-3C0A-4E8B-9C57-0A1B2C3D4E5F}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename=LumenPlayer-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
DisableProgramGroupPage=yes
ChangesAssociations=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; Flags: unchecked
Name: "assoc"; Description: "Открывать видеофайлы (mkv, mp4, avi, ...) в Lumen Player"

[Files]
Source: "dist\LumenPlayer\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\LumenPlayer.Video"; ValueType: string; ValueData: "Видео (Lumen Player)"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\LumenPlayer.Video\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueName: "LumenPlayer.Video"; ValueType: string; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueName: "LumenPlayer.Video"; ValueType: string; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.avi\OpenWithProgids"; ValueName: "LumenPlayer.Video"; ValueType: string; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.mov\OpenWithProgids"; ValueName: "LumenPlayer.Video"; ValueType: string; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueName: "LumenPlayer.Video"; ValueType: string; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.m4v\OpenWithProgids"; ValueName: "LumenPlayer.Video"; ValueType: string; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.ts\OpenWithProgids"; ValueName: "LumenPlayer.Video"; ValueType: string; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "Запустить Lumen Player"; Flags: nowait postinstall skipifsilent
