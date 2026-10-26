#ifndef AppVersion
  #define AppVersion "0.5.0"
#endif

[Setup]
AppId=io.github.GenissonEmilio.citrica
AppName=Cítrica
AppVersion={#AppVersion}
AppPublisher=GenissonEmilio
AppPublisherURL=https://github.com/GenissonEmilio/citrica
AppSupportURL=https://github.com/GenissonEmilio/citrica/issues
DefaultDirName={localappdata}\Programs\Citrica
DefaultGroupName=Cítrica
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=citrica-{#AppVersion}-windows-x86_64-setup
SetupIconFile=..\build\windows-package\citrica.ico
UninstallDisplayIcon={app}\Citrica.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked
Name: "startup"; Description: "Iniciar na bandeja ao entrar no Windows"; Flags: unchecked

[Files]
Source: "..\dist\Citrica\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Cítrica"; Filename: "{app}\Citrica.exe"
Name: "{userdesktop}\Cítrica"; Filename: "{app}\Citrica.exe"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Windows\SendTo\Cítrica"; Filename: "{app}\Citrica.exe"; Parameters: "--wheel"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Citrica"; ValueData: """{app}\Citrica.exe"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Citrica.exe"; Parameters: "--background"; Description: "Iniciar o Cítrica na bandeja"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\citrica-cli.exe"; Parameters: "--quit"; Flags: runhidden skipifdoesntexist; RunOnceId: "StopCitrica"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\citrica-cli.exe')) then
    if not Exec(ExpandConstant('{app}\citrica-cli.exe'), '--quit', '', SW_HIDE,
                ewWaitUntilTerminated, ExitCode) or (ExitCode <> 0) then
      Result := 'Feche o Cítrica pela bandeja antes de atualizar.';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Citrica');
end;
