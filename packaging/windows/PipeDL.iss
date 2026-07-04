#define MyAppName "PipeDL"
#define MyAppVersion GetEnv("PIPEDL_VERSION")
#if MyAppVersion == ""
#define MyAppVersion "0.1.6"
#endif
#define SourceRoot GetEnv("PIPEDL_SOURCE_ROOT")
#if SourceRoot == ""
#define SourceRoot "..\.."
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
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
CloseApplicationsFilter=PipeDL.exe,pipedl_cli.exe

[Files]
Source: "{#SourceRoot}\dist\PipeDL\PipeDL.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\dist\PipeDL\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\dist\pipedl_cli.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PipeDL"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\PipeDL"; Filename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch PipeDL"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM PipeDL.exe /F /T >nul 2>nul"; Flags: runhidden; RunOnceId: "StopPipeDL"
Filename: "{cmd}"; Parameters: "/C taskkill /IM pipedl_cli.exe /F /T >nul 2>nul"; Flags: runhidden; RunOnceId: "StopPipeDLCLI"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\PipeDL"
Type: filesandordirs; Name: "{app}"

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

function RemovePathEntry(PathValue: string; Entry: string): string;
var
  Work: string;
  Needle: string;
begin
  Work := ';' + PathValue + ';';
  Needle := ';' + Entry + ';';
  while Pos(Uppercase(Needle), Uppercase(Work)) > 0 do
  begin
    Delete(Work, Pos(Uppercase(Needle), Uppercase(Work)), Length(Needle) - 1);
  end;
  if Copy(Work, 1, 1) = ';' then
    Delete(Work, 1, 1);
  if Copy(Work, Length(Work), 1) = ';' then
    Delete(Work, Length(Work), 1);
  Result := Work;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  OrigPath: string;
  NewPath: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
    begin
      NewPath := RemovePathEntry(OrigPath, ExpandConstant('{app}'));
      RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', NewPath);
    end;
  end;
end;
