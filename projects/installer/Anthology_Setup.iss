#define MyAppName "ANTHOLOGY"
#define MyAppVersion "2.1"
#define GameArchive "Anthology_Game.bin"
#define Mo2Archive "Anthology_Modpack.bin"
#define LauncherRelativePath "Anomaly-1.5.3-Anthology 2.1\AnomalyLauncher.exe"

[Setup]
AppId={{8D79E936-A73F-4F95-98FC-1C3A2A7E5F9A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Anthology
DefaultDirName={sd}\Games\ANTHOLOGY
DisableDirPage=no
UsePreviousAppDir=no
AlwaysShowDirOnReadyPage=yes
DisableProgramGroupPage=yes
OutputDir=D:\Games
OutputBaseFilename=Anthology_Setup
SetupIconFile=E:\dev\Anthology-Work-Git\projects\installer\AnthologyLauncher.ico
WizardImageFile=E:\dev\Anthology-Work-Git\projects\installer\assets\wizard-image.bmp
WizardSmallImageFile=E:\dev\Anthology-Work-Git\projects\installer\assets\wizard-background.bmp
UninstallDisplayIcon={app}\{#LauncherRelativePath}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern dynamic
WizardBackColor=#101818
WizardBackColorDynamicDark=#101818
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DiskSpanning=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Messages]
SelectDirDesc=Куда установить ANTHOLOGY?
SelectDirLabel3=Выберите папку ANTHOLOGY. Можно указать готовую папку ANTHOLOGY или выбрать родительскую папку, например D:\Games; установщик сам добавит ANTHOLOGY.
SelectComponentsDesc=Что установить?
SelectComponentsLabel2=Выберите состав установки. Если второй архив не скачан, установите только ANTHOLOGY.
ReadyMemoDir=Папка установки:
InstallingLabel=Идет установка ANTHOLOGY. Во время распаковки появится окно прогресса без кнопок отмены архива.

[Types]
Name: "full"; Description: "ANTHOLOGY + модпак"
Name: "gameonly"; Description: "Только ANTHOLOGY"
Name: "custom"; Description: "Выборочная установка"; Flags: iscustom

[Components]
Name: "game"; Description: "ANTHOLOGY"; Types: full gameonly custom; Flags: fixed
Name: "modpack"; Description: "SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT"; Types: full custom

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык ANTHOLOGY на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: checkedonce

[Files]
Source: "C:\Program Files\7-Zip\7z.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "C:\Program Files\7-Zip\7z.dll"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "E:\dev\Anthology-Work-Git\projects\installer\bin\ExtractWithProgress.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{userprograms}\ANTHOLOGY"; Filename: "{app}\{#LauncherRelativePath}"; WorkingDir: "{app}\Anomaly-1.5.3-Anthology 2.1"
Name: "{userdesktop}\ANTHOLOGY"; Filename: "{app}\{#LauncherRelativePath}"; WorkingDir: "{app}\Anomaly-1.5.3-Anthology 2.1"; Tasks: desktopicon

[Run]
Filename: "{app}\{#LauncherRelativePath}"; Description: "Запустить ANTHOLOGY"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}\Anomaly-1.5.3-Anthology 2.1"
Type: filesandordirs; Name: "{app}\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT"

[Code]
const
  GameArchiveName = '{#GameArchive}';
  Mo2ArchiveName = '{#Mo2Archive}';
  RequiredGameOnlySpaceMB = 60000;
  RequiredFullInstallSpaceMB = 125000;

function IsAnthologyDir(Path: string): Boolean;
begin
  Result := CompareText(ExtractFileName(RemoveBackslashUnlessRoot(Path)), 'ANTHOLOGY') = 0;
end;

procedure NormalizeInstallDir();
var
  Dir: string;
begin
  Dir := RemoveBackslashUnlessRoot(WizardForm.DirEdit.Text);
  if not IsAnthologyDir(Dir) then
    WizardForm.DirEdit.Text := AddBackslash(Dir) + 'ANTHOLOGY';
end;

function SpaceText(Megabytes: Int64): string;
begin
  Result := IntToStr((Megabytes + 999) div 1000) + ' GB';
end;

function IsModpackSelected(): Boolean;
begin
  Result := WizardIsComponentSelected('modpack');
end;

function SelectedInstallSpaceMB(): Int64;
begin
  Result := RequiredGameOnlySpaceMB;
  if IsModpackSelected() then
    Result := RequiredFullInstallSpaceMB;
end;

procedure UpdateDiskSpaceLabel();
begin
  WizardForm.DiskSpaceLabel.Caption :=
    'Требуется как минимум ' + SpaceText(SelectedInstallSpaceMB()) + ' свободного места на выбранном диске.';
end;

function CheckSelectedArchives(): Boolean;
var
  GameArchivePath: string;
  Mo2ArchivePath: string;
begin
  Result := True;
  GameArchivePath := ExpandConstant('{src}\') + GameArchiveName;
  Mo2ArchivePath := ExpandConstant('{src}\') + Mo2ArchiveName;

  if not FileExists(GameArchivePath) then
  begin
    MsgBox('Рядом с установщиком не найден обязательный архив:' + #13#10 + GameArchiveName + #13#10#13#10 +
      'Положите архив в одну папку с Anthology_Setup.exe и запустите установщик снова.', mbError, MB_OK);
    Result := False;
    Exit;
  end;

  if IsModpackSelected() and (not FileExists(Mo2ArchivePath)) then
  begin
    MsgBox('Вы выбрали установку модпака, но рядом с установщиком не найден архив:' + #13#10 + Mo2ArchiveName + #13#10#13#10 +
      'Положите архив рядом с Anthology_Setup.exe или выберите вариант "Только ANTHOLOGY".', mbError, MB_OK);
    Result := False;
    Exit;
  end;
end;

function CheckInstallSpace(InstallDir: string): Boolean;
var
  FreeMB: Int64;
  FreeBytes: Int64;
  TotalBytes: Int64;
  DriveRoot: string;
  RequiredMB: Int64;
begin
  Result := True;
  RequiredMB := SelectedInstallSpaceMB();
  DriveRoot := AddBackslash(ExtractFileDrive(InstallDir));

  if not GetSpaceOnDisk64(DriveRoot, FreeBytes, TotalBytes) then
  begin
    MsgBox('Не удалось проверить свободное место на диске:' + #13#10 + DriveRoot + #13#10#13#10 +
      'Выберите другой путь установки или проверьте диск вручную.', mbError, MB_OK);
    Result := False;
    Exit;
  end;

  FreeMB := FreeBytes div 1048576;

  if FreeMB < RequiredMB then
  begin
    MsgBox('Недостаточно свободного места для установки ANTHOLOGY.' + #13#10#13#10 +
      'Выбранный диск: ' + DriveRoot + #13#10 +
      'Свободно: ' + SpaceText(FreeMB) + #13#10 +
      'Нужно минимум: ' + SpaceText(RequiredMB) + #13#10#13#10 +
      'Освободите место или выберите другой диск.', mbError, MB_OK);
    Result := False;
    Exit;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    NormalizeInstallDir();
  end
  else if (CurPageID = wpSelectComponents) or (CurPageID = wpReady) then
  begin
    Result := CheckSelectedArchives();
    if Result then
      Result := CheckInstallSpace(WizardForm.DirEdit.Text);
  end;

  UpdateDiskSpaceLabel();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  UpdateDiskSpaceLabel();
end;

function InitializeSetup(): Boolean;
var
  GameArchivePath: string;
begin
  Result := True;
  GameArchivePath := ExpandConstant('{src}\') + GameArchiveName;

  if not FileExists(GameArchivePath) then
  begin
    MsgBox('Рядом с установщиком не найден обязательный архив:' + #13#10 + GameArchiveName + #13#10#13#10 +
      'Положите архив в одну папку с Anthology_Setup.exe и запустите установщик снова.', mbError, MB_OK);
    Result := False;
    Exit;
  end;
end;

procedure InitializeWizard();
var
  BackImages: array of TGraphic;
begin
  BackImages := [WizardForm.WizardSmallBitmapImage.Bitmap];
  WizardSetBackImage(BackImages, True, True, 120);
  WizardForm.WizardBitmapImage.Visible := False;
  WizardForm.WizardBitmapImage2.Visible := False;
  WizardForm.WizardSmallBitmapImage.Visible := False;

  WizardForm.SelectDirLabel.Caption :=
    'Выберите, куда установить ANTHOLOGY.' + #13#10#13#10 +
    'Если выбрать D:\Games, итоговый путь будет D:\Games\ANTHOLOGY.' + #13#10 +
    'Если выбрать уже готовую папку ANTHOLOGY, второй раз ANTHOLOGY не добавится.' + #13#10#13#10 +
    'Перед установкой будет проверено свободное место на выбранном диске.';

  UpdateDiskSpaceLabel();
end;

procedure ExtractArchive(ArchiveName: string; StatusText: string);
var
  ResultCode: Integer;
  Params: string;
begin
  WizardForm.StatusLabel.Caption := StatusText + #13#10 +
    'Окно распаковки покажет прогресс. Кнопок Pause/Cancel/Background в нем не будет.';
  WizardForm.StatusLabel.Refresh;
  WizardForm.FilenameLabel.Caption := ArchiveName;
  WizardForm.FilenameLabel.Refresh;
  WizardForm.ProgressGauge.Position := 0;
  WizardForm.ProgressGauge.Refresh;

  Params := '"' + ExpandConstant('{src}\') + ArchiveName + '" "' + ExpandConstant('{app}') + '" "' + StatusText + '"';

  if not Exec(ExpandConstant('{tmp}\ExtractWithProgress.exe'), Params, '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('Не удалось запустить распаковку архива:' + #13#10 + ArchiveName, mbError, MB_OK);
    Abort;
  end;

  if ResultCode <> 0 then
  begin
    MsgBox('7-Zip вернул ошибку ' + IntToStr(ResultCode) + ' при распаковке:' + #13#10 + ArchiveName, mbError, MB_OK);
    Abort;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsModpackSelected() then
    begin
      ExtractArchive(GameArchiveName, 'Шаг 1 из 2: распаковка игровых файлов ANTHOLOGY.');
      ExtractArchive(Mo2ArchiveName, 'Шаг 2 из 2: распаковка Mod Organizer 2 и модпака.');
    end
    else
    begin
      ExtractArchive(GameArchiveName, 'Шаг 1 из 1: распаковка игровых файлов ANTHOLOGY.');
    end;
  end;
end;
