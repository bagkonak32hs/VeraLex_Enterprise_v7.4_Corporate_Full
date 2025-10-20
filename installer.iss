
; Inno Setup template (edit paths as needed)
[Setup]
AppName=VeraLex Enterprise
AppVersion=7.0.0
DefaultDirName={pf}\VeraLex
DefaultGroupName=VeraLex
OutputBaseFilename=VeraLex_Setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\VeraLex\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\VeraLex"; Filename: "{app}\VeraLex.exe"
Name: "{commondesktop}\VeraLex"; Filename: "{app}\VeraLex.exe"

[Run]
Filename: "{app}\VeraLex.exe"; Description: "VeraLex'i çalıştır"; Flags: nowait postinstall skipifsilent
