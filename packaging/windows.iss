#ifndef AppVersion
  #define AppVersion "0.6.0"
#endif

[Setup]
AppId=io.github.GenissonEmilio.citrica
AppName=Cítrica
AppVersion={#AppVersion}
AppPublisher=GenissonEmilio
AppPublisherURL=https://github.com/GenissonEmilio/citrica
AppSupportURL=https://github.com/GenissonEmilio/citrica/issues
AppUpdatesURL=https://github.com/GenissonEmilio/citrica/releases
VersionInfoCompany=GenissonEmilio
VersionInfoDescription=Cítrica · conversor local de arquivos
VersionInfoProductName=Cítrica
VersionInfoProductVersion={#AppVersion}
UninstallDisplayName=Cítrica {#AppVersion}
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
#ifdef SigningEnabled
SignTool=citrica
SignedUninstaller=yes
SignToolRetryCount=2
SignToolRetryDelay=5000
#endif

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked
Name: "startup"; Description: "Iniciar na bandeja ao entrar no Windows"; Flags: unchecked

[Files]
; Keep the new independent helper first in the solid stream so it can stop an
; old resident before copying/replacing any installed application files.
Source: "..\dist\Citrica\citrica-stop.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\Citrica\*"; DestDir: "{app}"; Excludes: "citrica-stop.exe"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; PrepareToInstall closes the resident first. Preferences live in AppData,
; outside this bundled runtime, so obsolete DLLs can be removed on upgrade.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{userprograms}\Cítrica"; Filename: "{app}\Citrica.exe"
Name: "{userdesktop}\Cítrica"; Filename: "{app}\Citrica.exe"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Windows\SendTo\Cítrica"; Filename: "{app}\Citrica.exe"; Parameters: "--wheel"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Citrica"; ValueData: """{app}\Citrica.exe"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Citrica.exe"; Parameters: "--background"; Description: "Iniciar o Cítrica na bandeja"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Retain this RunOnceId to supersede older installed CLI-based stop entries.
; The mandatory pre-removal check below already verified a successful stop.
Filename: "{app}\citrica-stop.exe"; Parameters: "--install-dir ""{app}"""; Flags: runhidden skipifdoesntexist; RunOnceId: "StopCitrica"

[Code]
function StopInstalledCitrica(const Helper: String): Boolean;
var ExitCode: Integer;
begin
  Result := False;
  if not FileExists(Helper) then begin
    Log('Citrica stop helper is missing; application files will be preserved.');
    Exit;
  end;
  if not Exec(Helper, '--install-dir ' + AddQuotes(ExpandConstant('{app}')), '',
              SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
    Log(Format('Citrica stop helper could not start (Windows error %d).', [ExitCode]));
    Exit;
  end;
  Log(Format('Citrica stop helper returned exit code %d.', [ExitCode]));
  Result := ExitCode = 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\Citrica.exe')) then begin
    ExtractTemporaryFile('citrica-stop.exe');
    if not StopInstalledCitrica(ExpandConstant('{tmp}\citrica-stop.exe')) then
      Result := 'Feche o Cítrica pela bandeja antes de atualizar.';
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { This event follows the user's confirmation and precedes all file removal.
    Abort here is fatal to uninstall; a failed helper must never be ignored. }
  if CurUninstallStep = usAppMutexCheck then begin
    if not StopInstalledCitrica(ExpandConstant('{app}\citrica-stop.exe')) then begin
      Log('Uninstall aborted: Cítrica could not be stopped; application files were preserved.');
      if not UninstallSilent then
        SuppressibleMsgBox('Não foi possível encerrar o Cítrica. Feche-o pela bandeja e tente desinstalar novamente. Os arquivos do aplicativo foram preservados.',
                          mbError, MB_OK, IDOK);
      Abort;
    end;
  end;
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Citrica');
end;
