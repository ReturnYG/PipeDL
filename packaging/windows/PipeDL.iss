#define MyAppName "PipeDL"
#define MyAppVersion GetEnv("PIPEDL_VERSION")
#if MyAppVersion == ""
#define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "PipeDL"
#define MyAppExeName "PipeDL.exe"

[Setup]
AppId={{A0C43C5B-F25A-4F13-A64E-B6D2CDAEBE20}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\PipeDL
DefaultGroupName=PipeDL
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=PipeDL-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes

[Files]
Source: "..\..\dist\PipeDL\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\pipedl.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PipeDL"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\PipeDL"; Filename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch PipeDL"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;
