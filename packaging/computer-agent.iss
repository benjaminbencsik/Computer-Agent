#define MyAppName "Computer Agent"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "Ben Bencsik"
#define MyAppExeName "ComputerAgent.exe"

[Setup]
AppId={{69D86A02-204C-4D7D-9D3A-5EB8A5E738C2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Computer Agent
DefaultGroupName=Computer Agent
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=ComputerAgent-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\ComputerAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Computer Agent"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Computer Agent"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Computer Agent"; Flags: nowait postinstall skipifsilent
