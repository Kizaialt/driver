; ----------------------------------------------------------------------------
; Peaklab - ONE-FILE installer for the Mongolian driver language packs.
;
; The customer gets a single .exe and a normal Windows wizard in Mongolian.
; No PowerShell window, no .bat, no zip to unpack. It:
;   1. finds the AULA / KYSONA driver if it is already installed (on ANY drive),
;      otherwise runs the vendor's own, UNMODIFIED installer (embedded);
;   2. adds the Mongolian language file next to the vendor's own languages,
;      using the app's own language mechanism - the driver binary is never touched;
;   3. makes the driver open in Mongolian.
;
; Build one model (see tools/exe/build_exe.py, which does this for every model):
;
;   ISCC /DFAMILY=bycombo4 /DMODEL="AULA F65" /DVENDOR=C:\...\AULA_F65_driver.exe ^
;        /DLANGSRC=C:\...\text.xml /DOUTDIR=C:\...\dist-exe /DOUTNAME=AULA_F65_Mongol tools\exe\peaklab.iss
;
;   FAMILY   bycombo4  F65 F65Pro F75 F99 F99Pro F108   (OemDrv.exe, Text\<dir>\text.xml, Cfg.ini, lang.ini)
;            lan       F75MAX F98 F106 F108Pro ...      (DeviceDriver.exe, language\1104.lan, config.xml)
;            kysona    M600, M600 V2                    (Mouse Drive*.exe, Language\<n>-Монгол.xml, registry)
;   /DTESTBUILD=1   asks for no admin rights, so the sandbox test can run it unattended.
;                   NEVER ship a test build.
;
; Hidden switches, for the sandbox test and for support:
;   /DRIVERDIR="D:\Program Files (x86)\AULA\F65"   use this folder, skip the search and the vendor installer
;   /LAD="C:\path"                                  use this instead of %LOCALAPPDATA% (bycombo4 lang.ini)
;
; This file is UTF-8 with a BOM: it contains Mongolian text.
; ----------------------------------------------------------------------------

#ifndef FAMILY
  #error FAMILY is required: bycombo4, lan or kysona
#endif
#ifndef MODEL
  #error MODEL is required, e.g. "AULA F65"
#endif
#ifndef VENDOR
  #error VENDOR (path to the vendor installer) is required
#endif
#ifndef LANGSRC
  #error LANGSRC (path to the language file) is required
#endif
#ifndef OUTDIR
  #define OUTDIR "."
#endif
#ifndef OUTNAME
  #define OUTNAME "Peaklab_Mongol_Setup"
#endif
#ifndef VERSION
  #define VERSION "1.6"
#endif
#ifndef APPGUID
  #define APPGUID "B7B43F83-6C1E-4B7B-9E0A-5D3A1C9E0001"
#endif

#if FAMILY == "bycombo4"
  #define DRVMASK "OemDrv.exe"
  #define LANGFILE "text.xml"
  #define LANGPATH "Config -> Language"
#elif FAMILY == "lan"
  #define DRVMASK "DeviceDriver.exe"
  #define LANGFILE "1104.lan"
  #define LANGPATH "Settings -> Language"
#elif FAMILY == "kysona"
  #define DRVMASK "Mouse Drive*.exe"
  #define LANGFILE "mongol.xml"
  #define LANGPATH "Setting -> Language"
#else
  #error FAMILY must be bycombo4, lan or kysona
#endif

; A test build may look for a made-up filename, so the search tests cannot find
; (and patch) a real driver installed on the developer's own PC.
; Arguments for the vendor installer. Empty in every shipped build: the customer clicks
; through AULA's own wizard. Only the end-to-end test passes /VERYSILENT, to a stand-in.
#ifndef VENDORARGS
  #define VENDORARGS ""
#endif
#ifdef TESTRUNVENDOR
  #ifndef TESTBUILD
    #error TESTRUNVENDOR is only allowed together with TESTBUILD
  #endif
#endif
#if VENDORARGS != ""
  #ifndef TESTRUNVENDOR
    #error VENDORARGS is for the end-to-end test only
  #endif
#endif

#ifdef TESTMASK
  #ifndef TESTBUILD
    #error TESTMASK is only allowed together with TESTBUILD
  #endif
  #undef DRVMASK
  #define DRVMASK TESTMASK
#endif

#define VENDORFILE ExtractFileName(VENDOR)

[Setup]
AppId={{{#APPGUID}}
AppName={#MODEL} - Монгол хэл
AppVersion={#VERSION}
AppPublisher=Peaklab
VersionInfoVersion={#VERSION}.0.0
VersionInfoCompany=Peaklab
VersionInfoProductName={#MODEL} - Монгол хэл
VersionInfoDescription={#MODEL} драйверт монгол хэл нэмэх суулгагч
CreateAppDir=no
Uninstallable=no
DisableWelcomePage=no
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableReadyMemo=yes
AppVerName={#MODEL} - Монгол хэл
OutputDir={#OUTDIR}
OutputBaseFilename={#OUTNAME}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
MinVersion=10.0
#ifdef TESTBUILD
PrivilegesRequired=lowest
#else
PrivilegesRequired=admin
#endif

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupAppTitle=Peaklab
SetupWindowTitle=%1
ButtonBack=< Буцах
ButtonNext=Үргэлжлүүлэх >
ButtonInstall=Суулгах
ButtonOK=За
ButtonCancel=Цуцлах
ButtonYes=Тийм
ButtonNo=Үгүй
ButtonFinish=Дуусгах
ExitSetupTitle=Гарах
ExitSetupMessage=Суулгалт дуусаагүй байна. Одоо гарвал монгол хэл нэмэгдэхгүй.%n%nГарах уу?
WelcomeLabel1={#MODEL} - Монгол хэл
WizardInstalling=Суулгаж байна
InstallingLabel=Түр хүлээнэ үү...
FinishedHeadingLabel=Бэлэн боллоо
SetupAborted=Суулгалт амжилтгүй боллоо.
ErrorTitle=Алдаа

[Files]
Source: "{#VENDOR}"; DestName: "{#VENDORFILE}"; Flags: dontcopy
Source: "{#LANGSRC}"; DestName: "{#LANGFILE}"; Flags: dontcopy

[Run]
Filename: "{code:LaunchPath}"; Description: "Драйверыг одоо нээх"; Flags: postinstall nowait skipifsilent; Check: CanLaunch

[Code]
const
  DRIVER_MASK = '{#DRVMASK}';
  VENDOR_FILE = '{#VENDORFILE}';
  LANG_FILE   = '{#LANGFILE}';
  MODEL_NAME  = '{#MODEL}';

var
  GDrivers: TStringList;        { full paths of the driver exe(s) found }
  GFailed: Boolean;
  GManual: Boolean;             { Mongolian was added but could not be made the default }
  GDetail: String;              { what to tell the customer on the last page }
  GAddedCount: Integer;

{ ---------------------------------------------------------------- finding the driver }

function SamePathIn(List: TStringList; const P: String): Boolean;
var I: Integer;
begin
  Result := False;
  for I := 0 to List.Count - 1 do
    if CompareText(List[I], P) = 0 then begin Result := True; Exit; end;
end;

{ Is there a driver exe in Dir?  Mask may contain a wildcard. }
function ExeInDir(const Dir, Mask: String; var Found: String): Boolean;
var
  FR: TFindRec;
  D: String;
begin
  Result := False;
  if Dir = '' then Exit;
  if not DirExists(Dir) then Exit;
  D := AddBackslash(Dir);
  if FindFirst(D + Mask, FR) then
  begin
    try
      repeat
        if (FR.Attributes and FILE_ATTRIBUTE_DIRECTORY) = 0 then
        begin
          Found := D + FR.Name;
          Result := True;
          Exit;
        end;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
end;

procedure AddIfDriver(Hits: TStringList; Dir: String);
var
  Found: String;
begin
  Dir := Trim(Dir);
  if Dir = '' then Exit;
  { Some installers (Google Drive) record InstallLocation as the path of an .exe }
  if FileExists(Dir) then Dir := ExtractFileDir(Dir);
  if ExeInDir(Dir, DRIVER_MASK, Found) then
    if not SamePathIn(Hits, Found) then Hits.Add(Found);
end;

procedure ScanUninstall(RootKey: Integer; Hits: TStringList);
var
  Sub, Key, Loc, Un: String;
  Names: TArrayOfString;
  I, Q: Integer;
begin
  Sub := 'Software\Microsoft\Windows\CurrentVersion\Uninstall';
  if not RegGetSubkeyNames(RootKey, Sub, Names) then Exit;
  for I := 0 to GetArrayLength(Names) - 1 do
  begin
    Key := Sub + '\' + Names[I];
    Loc := '';
    if RegQueryStringValue(RootKey, Key, 'InstallLocation', Loc) then AddIfDriver(Hits, Loc);
    Un := '';
    if RegQueryStringValue(RootKey, Key, 'UninstallString', Un) then
    begin
      Un := Trim(Un);
      if (Length(Un) > 0) and (Un[1] = '"') then
      begin
        Delete(Un, 1, 1);
        Q := Pos('"', Un);
        if Q > 0 then Un := Copy(Un, 1, Q - 1);
      end else
      begin
        Q := Pos('.exe', Lowercase(Un));
        if Q > 0 then Un := Copy(Un, 1, Q + 3);
      end;
      AddIfDriver(Hits, ExtractFileDir(Un));
    end;
  end;
end;

procedure ScanTree(Dir: String; Depth: Integer; Hits: TStringList);
var
  FR: TFindRec;
  Found: String;
begin
  if ExeInDir(Dir, DRIVER_MASK, Found) then
    if not SamePathIn(Hits, Found) then Hits.Add(Found);
  if Depth <= 0 then Exit;
  if FindFirst(AddBackslash(Dir) + '*', FR) then
  begin
    try
      repeat
        if ((FR.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and (FR.Name <> '.') and (FR.Name <> '..') then
          ScanTree(AddBackslash(Dir) + FR.Name, Depth - 1, Hits);
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;
end;

{ Ask Windows where it was installed first (any drive), then look on every drive. }
procedure FindDrivers(Hits: TStringList);
var
  Forced: String;
  L: Integer;
begin
  Hits.Clear;
  Forced := ExpandConstant('{param:DRIVERDIR|}');
  if Forced <> '' then
  begin
    AddIfDriver(Hits, Forced);
    Exit;
  end;

  ScanUninstall(HKLM64, Hits);
  ScanUninstall(HKLM32, Hits);
  ScanUninstall(HKCU, Hits);
  if Hits.Count > 0 then Exit;

  for L := Ord('C') to Ord('Z') do
  begin
    if DirExists(Chr(L) + ':\') then
    begin
      ScanTree(Chr(L) + ':\Program Files', 4, Hits);
      ScanTree(Chr(L) + ':\Program Files (x86)', 4, Hits);
    end;
  end;
  ScanTree(ExpandConstant('{localappdata}\Programs'), 4, Hits);

  { /SCANROOT lets a test (or support) point the folder scan at one place }
  Forced := ExpandConstant('{param:SCANROOT|}');
  if Forced <> '' then ScanTree(Forced, 4, Hits);
end;

{ ---------------------------------------------------------------- bycombo4: Cfg.ini + lang.ini }

#if FAMILY == "bycombo4"

{ The bytes of "Монгол" in UTF-16 little endian }
function MongolBytes(): AnsiString;
begin
  Result := #$1C#$04#$3E#$04#$3D#$04#$33#$04#$3E#$04#$3B#$04;
end;

{ ASCII text as UTF-16 LE bytes }
function Ascii16(const S: String): AnsiString;
var
  I: Integer;
begin
  Result := '';
  for I := 1 to Length(S) do
    Result := Result + Chr(Ord(S[I])) + #0;
end;

function IsDigitChar(C: Char): Boolean;
begin
  Result := (C >= '0') and (C <= '9');
end;

{ Cfg.ini is UTF-16 LE with a BOM and CRLF. Edit it as BYTES so nothing else in
  the vendor's file can change: only one line is added.
  Returns the 0-based index of the Mongolian entry in the Lang list, or -1. }
function PatchCfgIni(const Cfg: String; var AppDir: String): Integer;
var
  Raw, NewRaw: AnsiString;
  Asc: String;
  I, N, MaxN, MnN, LineEnd, LastEnd, P, B, Count: Integer;
  Num, Rest: String;
  LineHasMn: Boolean;
begin
  Result := -1;
  AppDir := '';
  if not LoadStringFromFile(Cfg, Raw) then begin Log('cannot read ' + Cfg); Exit; end;
  if (Length(Raw) < 4) or (Ord(Raw[1]) <> $FF) or (Ord(Raw[2]) <> $FE) then
  begin
    Log('Cfg.ini is not UTF-16 LE with a BOM - refusing to touch it');
    Exit;
  end;

  { One char per UTF-16 unit; anything outside ASCII becomes '#'. Positions line
    up with the raw bytes: unit U is bytes 2U-1 and 2U. }
  Count := Length(Raw) div 2;
  Asc := '';
  for I := 1 to Count do
  begin
    if Ord(Raw[2 * I]) = 0 then Asc := Asc + Chr(Ord(Raw[2 * I - 1]))
    else Asc := Asc + '#';
  end;

  MaxN := 0; MnN := 0; LastEnd := 0;
  I := 1;
  while I <= Length(Asc) do
  begin
    if ((I = 1) or (Asc[I - 1] = #10)) and (Copy(Asc, I, 4) = 'Lang') then
    begin
      P := I + 4; Num := '';
      while (P <= Length(Asc)) and IsDigitChar(Asc[P]) do begin Num := Num + Asc[P]; P := P + 1; end;
      if (Num <> '') and (P <= Length(Asc)) and (Asc[P] = '=') then
      begin
        N := StrToIntDef(Num, 0);
        LineEnd := P;
        while (LineEnd <= Length(Asc)) and (Asc[LineEnd] <> #10) do LineEnd := LineEnd + 1;
        if LineEnd > Length(Asc) then LineEnd := Length(Asc);
        Rest := Copy(Asc, P, LineEnd - P + 1);
        LineHasMn := (Pos(',mn' + #13, Rest) > 0) or (Pos(',mn' + #10, Rest) > 0);
        if (not LineHasMn) and (Length(Rest) >= 3) then
          LineHasMn := (Copy(Rest, Length(Rest) - 2, 3) = ',mn');
        if LineHasMn then MnN := N;
        if N > MaxN then MaxN := N;
        LastEnd := LineEnd;
      end;
    end;
    I := I + 1;
  end;

  { the Appdir the driver keeps its settings under }
  P := Pos('Appdir=', Asc);
  if P > 0 then
  begin
    P := P + 7;
    while (P <= Length(Asc)) and (Asc[P] <> #13) and (Asc[P] <> #10) do begin AppDir := AppDir + Asc[P]; P := P + 1; end;
    AppDir := Trim(AppDir);
  end;

  if MnN > 0 then
  begin
    Log('Cfg.ini already lists Mongolian as Lang' + IntToStr(MnN));
    Result := MnN - 1;
    Exit;
  end;
  if (MaxN = 0) or (LastEnd = 0) then begin Log('Cfg.ini has no Lang list'); Exit; end;

  if not FileExists(Cfg + '.bak') then FileCopy(Cfg, Cfg + '.bak', False);

  NewRaw := Copy(Raw, 1, 2 * LastEnd);
  if Asc[LastEnd] <> #10 then NewRaw := NewRaw + Ascii16(#13#10);   { last line had no line end }
  NewRaw := NewRaw + Ascii16('Lang' + IntToStr(MaxN + 1) + '=') + MongolBytes() + Ascii16(',mn' + #13#10);
  NewRaw := NewRaw + Copy(Raw, 2 * LastEnd + 1, Length(Raw));

  if not SaveStringToFile(Cfg, NewRaw, False) then begin Log('cannot write ' + Cfg); Exit; end;
  Result := MaxN;       { Lang<MaxN+1>  ->  0-based index MaxN }
end;

function AddLanguage(const DriverExe: String): Boolean;
var
  Dir, Cfg, Dest, AppDir, Lad, Ini: String;
  Index: Integer;
begin
  Result := False;
  Dir := ExtractFileDir(DriverExe);
  Cfg := AddBackslash(Dir) + 'Cfg.ini';
  if not FileExists(Cfg) then begin Log('no Cfg.ini in ' + Dir); Exit; end;

  ExtractTemporaryFile(LANG_FILE);
  Dest := AddBackslash(Dir) + 'Text\mn';
  if not ForceDirectories(Dest) then begin Log('cannot create ' + Dest); Exit; end;
  if not FileCopy(ExpandConstant('{tmp}\') + LANG_FILE, Dest + '\text.xml', False) then
  begin Log('cannot write ' + Dest + '\text.xml'); Exit; end;
  Log('wrote ' + Dest + '\text.xml');

  Index := PatchCfgIni(Cfg, AppDir);
  if Index < 0 then Exit;
  Log('Mongolian is Lang' + IntToStr(Index + 1) + ' (LangIndex ' + IntToStr(Index) + ')');

  { the driver remembers its language as a 0-based index in %LOCALAPPDATA%\<Appdir>\lang.ini }
  if AppDir <> '' then
  begin
    Lad := ExpandConstant('{param:LAD|}');
    if Lad = '' then Lad := ExpandConstant('{localappdata}');
    Ini := AddBackslash(Lad) + AppDir + '\lang.ini';
    if ForceDirectories(ExtractFileDir(Ini)) then
      if SaveStringToFile(Ini, '[OPT]' + #13#10 + 'LangIndex=' + IntToStr(Index) + #13#10, False) then
        Log('wrote ' + Ini);
  end;
  Result := True;
end;

#elif FAMILY == "lan"

{ ---------------------------------------------------------------- lan: language\1104.lan + config.xml }

{ Find Pat in Raw by comparing BYTES. config.xml is UTF-8 and may hold Chinese; it
  must never be converted through the ANSI code page, so every edit below is made
  on the AnsiString as raw bytes and only ASCII text is ever inserted. }
function FindBytes(const Raw: AnsiString; const Pat: String; From: Integer): Integer;
var
  I, J, L: Integer;
  Ok: Boolean;
begin
  Result := 0;
  L := Length(Pat);
  if (L = 0) or (From < 1) then Exit;
  for I := From to Length(Raw) - L + 1 do
  begin
    Ok := True;
    for J := 1 to L do
      if Ord(Raw[I + J - 1]) <> Ord(Pat[J]) then begin Ok := False; Break; end;
    if Ok then begin Result := I; Exit; end;
  end;
end;

function AddLanguage(const DriverExe: String): Boolean;
var
  Dir, LangDir, Cfg: String;
  Raw, NewRaw: AnsiString;
  P, Q, E, S, V: Integer;
begin
  Result := False;
  Dir := ExtractFileDir(DriverExe);
  LangDir := AddBackslash(Dir) + 'language';
  if not DirExists(LangDir) then begin Log('no language folder in ' + Dir); Exit; end;

  ExtractTemporaryFile(LANG_FILE);
  if not FileCopy(ExpandConstant('{tmp}\') + LANG_FILE, LangDir + '\1104.lan', False) then
  begin Log('cannot write ' + LangDir + '\1104.lan'); Exit; end;
  Log('wrote ' + LangDir + '\1104.lan');
  Result := True;        { the language file is in place; making it the default is the bonus }

  { config.xml is edited in place, never replaced, so AULA's own updates are not
    overwritten by an old copy of ours }
  Cfg := AddBackslash(Dir) + 'config.xml';
  if not FileExists(Cfg) then begin Log('no config.xml'); GManual := True; Exit; end;
  if not LoadStringFromFile(Cfg, Raw) then begin Log('cannot read config.xml'); GManual := True; Exit; end;

  P := FindBytes(Raw, '<language.info', 1);
  if P = 0 then begin Log('config.xml has no <language.info> (older build)'); GManual := True; Exit; end;
  Q := P;
  while (Q <= Length(Raw)) and (Ord(Raw[Q]) <> Ord('>')) do Q := Q + 1;
  if Q > Length(Raw) then begin Log('config.xml: unterminated <language.info>'); GManual := True; Exit; end;

  if not FileExists(Cfg + '.bak') then FileCopy(Cfg, Cfg + '.bak', False);
  NewRaw := Raw;

  { make 1104 the default language }
  E := FindBytes(NewRaw, 'default_lan="', P);
  if (E > 0) and (E < Q) then
  begin
    S := E + 13;
    V := S;
    while (V <= Length(NewRaw)) and (Ord(NewRaw[V]) >= 48) and (Ord(NewRaw[V]) <= 57) do V := V + 1;
    NewRaw := Copy(NewRaw, 1, S - 1) + '1104' + Copy(NewRaw, V, Length(NewRaw));
  end else
    NewRaw := Copy(NewRaw, 1, P + 13) + ' default_lan="1104"' + Copy(NewRaw, P + 14, Length(NewRaw));

  { list it, as the first child of <language.info>, unless it is already there }
  if FindBytes(NewRaw, 'value="1104"', 1) = 0 then
  begin
    P := FindBytes(NewRaw, '<language.info', 1);
    Q := P;
    while (Q <= Length(NewRaw)) and (Ord(NewRaw[Q]) <> Ord('>')) do Q := Q + 1;
    NewRaw := Copy(NewRaw, 1, Q) + #13#10#9#9 + '<lan value="1104" />' + Copy(NewRaw, Q + 1, Length(NewRaw));
  end;

  if not SaveStringToFile(Cfg, NewRaw, False) then begin Log('cannot write config.xml'); GManual := True; Exit; end;
  Log('config.xml: Mongolian registered and made the default');
end;

#elif FAMILY == "kysona"

{ ---------------------------------------------------------------- kysona: Language\<n>-Монгол.xml + registry }

{ "2-Монгол.xml" -> 2;  anything that is not "<digits>-..." -> -1 }
function LeadingNumber(const Name: String): Integer;
var
  I: Integer;
  Num: String;
begin
  Num := '';
  I := 1;
  while (I <= Length(Name)) and (Name[I] >= '0') and (Name[I] <= '9') do
  begin
    Num := Num + Name[I];
    I := I + 1;
  end;
  if (Num <> '') and (I <= Length(Name)) and (Name[I] = '-') then Result := StrToIntDef(Num, -1)
  else Result := -1;
end;

function AddLanguage(const DriverExe: String): Boolean;
var
  Dir, LangDir, Dest, RegKey: String;
  FR: TFindRec;
  Old: TStringList;
  I, N, Next: Integer;
begin
  Result := False;
  Dir := ExtractFileDir(DriverExe);
  LangDir := AddBackslash(Dir) + 'Language';
  if not DirExists(LangDir) then begin Log('no Language folder in ' + Dir); Exit; end;

  { an earlier Mongolian file may have a different index: remove it, then re-add }
  Old := TStringList.Create;
  try
    if FindFirst(LangDir + '\*.xml', FR) then
    begin
      try
        repeat
          if Pos('Монгол', FR.Name) > 0 then Old.Add(LangDir + '\' + FR.Name);
        until not FindNext(FR);
      finally
        FindClose(FR);
      end;
    end;
    for I := 0 to Old.Count - 1 do DeleteFile(Old[I]);
  finally
    Old.Free;
  end;

  Next := 0;
  if FindFirst(LangDir + '\*.xml', FR) then
  begin
    try
      repeat
        N := LeadingNumber(FR.Name);
        if N >= Next then Next := N + 1;
      until not FindNext(FR);
    finally
      FindClose(FR);
    end;
  end;

  ExtractTemporaryFile(LANG_FILE);
  Dest := LangDir + '\' + IntToStr(Next) + '-Монгол.xml';
  if not FileCopy(ExpandConstant('{tmp}\') + LANG_FILE, Dest, False) then
  begin Log('cannot write ' + Dest); Exit; end;
  Log('wrote ' + Dest);
  Result := True;

  { the driver keeps its language as HKCU\Software\Compx\LanguageIndex. The key does
    not exist until the driver has run once, so this is best effort: if it does not
    take, picking the language once inside the driver is enough. }
  RegKey := ExpandConstant('{param:REGKEY|}');
  if RegKey = '' then RegKey := 'Software\Compx';
  if RegWriteDWordValue(HKCU, RegKey, 'LanguageIndex', Next) then Log('LanguageIndex = ' + IntToStr(Next))
  else begin Log('could not set LanguageIndex'); GManual := True; end;
end;

#endif

{ ---------------------------------------------------------------- the wizard }

function RunVendorInstaller(): Boolean;
var
  Rc: Integer;
begin
  Result := False;
#if defined(TESTBUILD) && !defined(TESTRUNVENDOR)
  { A test build must NEVER launch the embedded vendor installer: on a developer PC
    that is a real AULA installer. (The end-to-end test embeds a harmless stand-in
    and sets TESTRUNVENDOR to exercise this very path.) }
  Log('TEST BUILD: the vendor installer is NOT run');
  Result := True;
  Exit;
#endif
  ExtractTemporaryFile(VENDOR_FILE);
  Log('vendor installer SHA-256 ' + GetSHA256OfFile(ExpandConstant('{tmp}\') + VENDOR_FILE));
  if Exec(ExpandConstant('{tmp}\') + VENDOR_FILE, '{#VENDORARGS}', '', SW_SHOWNORMAL, ewWaitUntilTerminated, Rc) then
  begin
    Log('vendor installer exit code ' + IntToStr(Rc));
    Result := True;
  end;
end;

procedure InitializeWizard();
begin
  GDrivers := TStringList.Create;
  FindDrivers(GDrivers);
  if GDrivers.Count > 0 then
    WizardForm.WelcomeLabel2.Caption :=
      MODEL_NAME + ' драйвер аль хэдийн суусан байна:' + #13#10 + '    ' + ExtractFileDir(GDrivers[0]) + #13#10#13#10 +
      'Энэ суулгагч зөвхөн монгол хэлийг нэмнэ. Драйверыг дахин суулгахгүй.' + #13#10#13#10 +
      'Үргэлжлүүлэхийн тулд "Үргэлжлүүлэх" дарна уу.'
  else
    WizardForm.WelcomeLabel2.Caption :=
      'Энэ суулгагч:' + #13#10#13#10 +
      '    1. AULA-гийн жинхэнэ ' + MODEL_NAME + ' драйверыг суулгана' + #13#10 +
      '    2. Монгол хэлийг нэмнэ' + #13#10 +
      '    3. Драйвер монголоор нээгдэхээр тохируулна' + #13#10#13#10 +
      'AULA-гийн суулгагчийн цонх гарч ирвэл Next / Install дарж дуусгана уу.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  I: Integer;
  Browsed: String;
begin
  if CurStep <> ssInstall then Exit;

  GFailed := False; GManual := False; GAddedCount := 0; GDetail := '';

  if GDrivers.Count = 0 then
  begin
    WizardForm.StatusLabel.Caption := 'AULA-гийн драйверыг суулгаж байна...';
    if not RunVendorInstaller() then
    begin
      GFailed := True;
      GDetail := 'AULA-гийн суулгагчийг ажиллуулж чадсангүй.';
      Exit;
    end;
    FindDrivers(GDrivers);
  end;

  if (GDrivers.Count = 0) and WizardSilent then
  begin
    { no one is there to answer a dialog }
    GFailed := True;
    GDetail := 'Драйвер олдсонгүй.';
    Exit;
  end;

  if GDrivers.Count = 0 then
  begin
    { not found anywhere - let the customer point at it }
    if SuppressibleMsgBox('Драйверыг автоматаар олсонгүй.' + #13#10#13#10 +
         'Драйвер суусан хавтсыг сонгоно уу (' + DRIVER_MASK + ' байгаа хавтас).',
         mbInformation, MB_OKCANCEL, IDOK) <> IDOK then
    begin
      GFailed := True;
      GDetail := 'Драйвер олдсонгүй. Эхлээд AULA-гийн драйверыг суулгаад дахин оролдоно уу.';
      Exit;
    end;
    Browsed := '';
    if BrowseForFolder('Драйвер суусан хавтсыг сонгоно уу', Browsed, False) then
      AddIfDriver(GDrivers, Browsed);
  end;

  if GDrivers.Count = 0 then
  begin
    GFailed := True;
    GDetail := 'Драйвер олдсонгүй. Эхлээд AULA-гийн драйверыг суулгаад дахин оролдоно уу.';
    Exit;
  end;

  WizardForm.StatusLabel.Caption := 'Монгол хэл нэмж байна...';
  for I := 0 to GDrivers.Count - 1 do
  begin
    Log('adding Mongolian to ' + GDrivers[I]);
    if AddLanguage(GDrivers[I]) then GAddedCount := GAddedCount + 1;
  end;

  if GAddedCount = 0 then
  begin
    GFailed := True;
    GDetail := 'Монгол хэл нэмж чадсангүй. Лог файл: ' + ExpandConstant('{log}');
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID <> wpFinished then Exit;
  if GFailed then
  begin
    WizardForm.FinishedHeadingLabel.Caption := 'Алдаа гарлаа';
    WizardForm.FinishedLabel.Caption := GDetail;
  end else
  begin
    WizardForm.FinishedHeadingLabel.Caption := 'Бэлэн боллоо';
    if GManual then
      WizardForm.FinishedLabel.Caption :=
        'Монгол хэл нэмэгдлээ.' + #13#10#13#10 +
        'Драйверыг нээгээд {#LANGPATH} -> Монгол гэж нэг удаа сонгоно уу.' + #13#10 +
        '(дараа нь драйвер санана)'
    else
      WizardForm.FinishedLabel.Caption :=
        'Монгол хэл нэмэгдлээ.' + #13#10#13#10 +
        'Драйверыг нээхэд шууд монгол хэл дээр гарч ирнэ.' + #13#10 +
        'Хэлээ солихыг хүсвэл: {#LANGPATH}';
  end;
end;

{ The stock "Ready to Install" page is English and adds a click for nothing: the
  welcome page already says what will happen. DisableReadyPage alone did not hide it. }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = wpReady);
end;

function CanLaunch(): Boolean;
begin
  Result := (not GFailed) and (GDrivers <> nil) and (GDrivers.Count > 0);
end;

function LaunchPath(Param: String): String;
begin
  if (GDrivers <> nil) and (GDrivers.Count > 0) then Result := GDrivers[0]
  else Result := '';
end;

{ A non-zero exit code when it did not work, so a test or a script can tell. }
function InitializeSetup(): Boolean;
begin
  Result := True;
#ifndef TESTBUILD
  { Writing into Program Files needs administrator rights. Inno asks for them itself
    (PrivilegesRequired=admin); if that ever did not happen, say so plainly instead of
    failing halfway with an obscure "access denied". }
  if not IsAdmin then
  begin
    SuppressibleMsgBox('Энэ суулгагчийг администратор эрхээр ажиллуулна уу.' + #13#10#13#10 +
      'Файл дээр хулганы баруун товчийг дараад "Run as administrator" (Администратороор ажиллуулах) гэж сонгоно уу.',
      mbError, MB_OK, IDOK);
    Result := False;
  end;
#endif
end;

procedure DeinitializeSetup();
begin
  if GFailed then
  begin
    Log('FAILED: ' + GDetail);
    { Inno exits 0 after a finished wizard; there is no supported way to change
      the code from here, so the sandbox test reads the log line above instead. }
  end;
end;
