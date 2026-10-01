<#
  Run the one-file Peaklab installers (.exe) against a sandbox and check, byte for
  byte, what they do to the disk.

      powershell -NoProfile -ExecutionPolicy Bypass -File tools\qa\test_exe_installers.ps1
      ... -SkipBuild            use the TEST builds already in dist-exe-test
      ... -DummyVendor          CI: build without AULA's real installers (they are never run anyway)

  WHAT IT USES
  TEST builds (python tools\exe\build_exe.py --test): identical to the shipped
  installers except they ask for no administrator rights, and they NEVER launch the
  embedded vendor installer. They are driven with hidden switches:
      /DRIVERDIR=<folder>   use this folder instead of searching
      /LAD=<folder>         stand-in for %LOCALAPPDATA%   (AULA BYCOMBO4 lang.ini)
      /REGKEY=<key>         stand-in for HKCU\Software\Compx   (KYSONA)
      /SCANROOT=<folder>    point the folder-scan fallback at one place
  and PROBE builds that look for a made-up filename, so the driver SEARCH can be
  tested without ever finding - and patching - a real driver on this PC.

  THE ORACLE
  Every expected file is built independently here, in PowerShell, from the ORIGINAL
  bytes: not by running the installer's own logic again. If the installer and this
  test agree, two separate implementations agree.
#>
param([string]$Root, [switch]$SkipBuild, [switch]$DummyVendor)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$hub = Split-Path -Parent (Split-Path -Parent $here)
if (-not $Root) { $Root = Split-Path -Parent $hub }
$fs = Join-Path $Root 'aula-fseries-mn'
$ky = Join-Path $Root 'kysona-m600-mn'

$mn = ([char]0x041C).ToString() + [char]0x043E + [char]0x043D + [char]0x0433 + [char]0x043E + [char]0x043B   # Монгол
$utf8bom = New-Object Text.UTF8Encoding($true)
$utf8 = New-Object Text.UTF8Encoding($false)
$work = Join-Path ([IO.Path]::GetTempPath()) ('peaklab-exe-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $work | Out-Null

$results = New-Object System.Collections.ArrayList
function Check([string]$group, [string]$name, $ok, [string]$detail = '') {
    [void]$results.Add([pscustomobject]@{ group = $group; name = $name; ok = [bool]$ok; detail = $detail })
}
function Bytes($p) { return [IO.File]::ReadAllBytes($p) }
function Same($a, $b) { return (($a -join ',') -eq ($b -join ',')) }

# ------------------------------------------------------------------ build
if (-not $SkipBuild) {
    $extra = @(); if ($DummyVendor) { $extra += '--dummy-vendor' }
    foreach ($mode in @('--test'), @('--test', '--probe'), @('--test', '--e2e')) {
        $o = & python (Join-Path $hub 'tools\exe\build_exe.py') @mode @extra 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { Write-Host $o; throw "build_exe.py $($mode -join ' ') failed" }
    }
}
$exeDir = Join-Path $fs 'dist-exe-test'
$exeDirKy = Join-Path $ky 'dist-exe-test'

# Run an installer silently. It exits 0 even when it could not add the language (the
# wizard finishes), so success is read from the setup log, which is also what a
# support request would attach.
function Run-Exe([string]$exe, [string[]]$switches) {
    $log = Join-Path $work ([guid]::NewGuid().ToString('N').Substring(0, 6) + '.log')
    $argList = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$log`"") + $switches
    $p = Start-Process -FilePath $exe -ArgumentList $argList -Wait -PassThru
    $t = if (Test-Path -LiteralPath $log) { [IO.File]::ReadAllText($log) } else { '' }
    return [pscustomobject]@{ code = $p.ExitCode; log = $t; failed = ($t -match 'FAILED:') }
}
function Sw([string]$name, [string]$value) { return "/$name=`"$value`"" }

# ======================================================== 1. BYCOMBO4 (6 models)
function New-CfgBytes([string]$text) { return (New-Object Text.UnicodeEncoding($false, $true)).GetPreamble() + [Text.Encoding]::Unicode.GetBytes($text) }
$cn = [string][char]0x7B80 + [char]0x4F53 + [char]0x4E2D + [char]0x6587                         # 简体中文
$cfgHead = "[OPT]`r`nTitle=AULA`r`nAppdir=BYCOMBO4`r`nclrLine=49,49,49`r`n;comment`r`nGoWithNoDev=0`r`n`r`n"
$cfgCases = @(
    @{ n = 'normal (vendor shape: Lang list then blank lines)'; t = $cfgHead + "Lang1=English,en`r`nLang2=$cn,sc`r`n`r`n"; expectIndex = 2 },
    @{ n = 'last Lang line has no line ending (EOF)';           t = $cfgHead + "Lang1=English,en`r`nLang2=$cn,sc";        expectIndex = 2 },
    @{ n = 'Mongolian already registered';                     t = $cfgHead + "Lang1=English,en`r`nLang2=$cn,sc`r`nLang3=$mn,mn`r`n`r`n"; expectIndex = 2; unchanged = $true }
)
$byModels = @('F65', 'F65Pro', 'F75', 'F99', 'F99Pro', 'F108')
foreach ($key in $byModels) {
    $exe = Join-Path $exeDir "AULA_${key}_driver_mn_setup.exe"
    $srcXml = Join-Path $fs "dist\AULA_${key}_driver\text.xml"
    foreach ($case in $cfgCases) {
        $g = "BYCOMBO4 $key - $($case.n)"
        try {
            $sb = Join-Path $work ("by-$key-" + [guid]::NewGuid().ToString('N').Substring(0, 5))
            $inst = Join-Path $sb 'install'; $lad = Join-Path $sb 'lad'
            New-Item -ItemType Directory -Force (Join-Path $inst 'Text\en') | Out-Null; New-Item -ItemType Directory -Force $lad | Out-Null
            Set-Content (Join-Path $inst 'OemDrv.exe') 'x'
            $orig = New-CfgBytes $case.t
            [IO.File]::WriteAllBytes((Join-Path $inst 'Cfg.ini'), $orig)

            # the oracle: insert one line after the last "LangN=" line, nothing else
            $text = [Text.Encoding]::Unicode.GetString($orig)
            $mm = [regex]::Matches($text, '(?m)^Lang(\d+)=[^\r\n]*(\r\n|$)')
            $last = $mm[$mm.Count - 1]; $nn = [int]$last.Groups[1].Value
            $hasMn = ($text -match ",mn\r")
            if ($hasMn) { $expect = $orig }
            else {
                $ins = $text.Substring(0, $last.Index + $last.Length)
                if (-not $last.Groups[2].Value) { $ins += "`r`n" }
                $expect = [Text.Encoding]::Unicode.GetBytes($ins + "Lang$($nn + 1)=$mn,mn`r`n" + $text.Substring($last.Index + $last.Length))
            }

            $r = Run-Exe $exe @((Sw 'DRIVERDIR' $inst), (Sw 'LAD' $lad))
            $got = Bytes (Join-Path $inst 'Cfg.ini')
            Check $g 'installer reports no failure' (-not $r.failed) ($r.log -split "`n" | Select-String 'FAILED' | Select-Object -First 1)
            Check $g 'Cfg.ini is BYTE-IDENTICAL to the independently built expectation' (Same $got $expect) "got $($got.Length) bytes, expected $($expect.Length)"
            Check $g 'Cfg.ini keeps its UTF-16 LE BOM' ($got[0] -eq 0xFF -and $got[1] -eq 0xFE) ''
            if (-not $case.unchanged) {
                $wantGrow = [Text.Encoding]::Unicode.GetByteCount("Lang$($nn + 1)=$mn,mn`r`n") + $(if (-not $last.Groups[2].Value) { 4 } else { 0 })
                Check $g 'grows by exactly the one new line' (($got.Length - $orig.Length) -eq $wantGrow) "grew $($got.Length - $orig.Length), expected $wantGrow"
                Check $g 'keeps Cfg.ini.bak = the original' ((Test-Path (Join-Path $inst 'Cfg.ini.bak')) -and (Same (Bytes (Join-Path $inst 'Cfg.ini.bak')) $orig)) ''
            } else {
                Check $g 'file untouched when already registered' (Same $got $orig) ''
                Check $g 'no .bak made when nothing changed' (-not (Test-Path (Join-Path $inst 'Cfg.ini.bak'))) ''
            }
            Check $g 'Text\mn\text.xml is byte-identical to the shipped language file' ((Test-Path (Join-Path $inst 'Text\mn\text.xml')) -and (Same (Bytes (Join-Path $inst 'Text\mn\text.xml')) (Bytes $srcXml))) ''
            $ini = Join-Path $lad 'BYCOMBO4\lang.ini'
            $wantIni = [Text.Encoding]::ASCII.GetBytes("[OPT]`r`nLangIndex=$($case.expectIndex)`r`n")
            Check $g "lang.ini = [OPT] LangIndex=$($case.expectIndex), byte-exact" ((Test-Path $ini) -and (Same (Bytes $ini) $wantIni)) ''
            $r2 = Run-Exe $exe @((Sw 'DRIVERDIR' $inst), (Sw 'LAD' $lad))
            Check $g 'second run changes nothing' ((Same (Bytes (Join-Path $inst 'Cfg.ini')) $got) -and -not $r2.failed) ''
        } catch { Check $g 'test ran to completion' $false ("aborted: " + $_.Exception.Message) }
    }
}

# ============================================================ 2. .lan family (6 models)
$cfgXmlBody = "<?xml version=`"1.0`" encoding=`"UTF-8`"?>`r`n<config>`r`n`t<language.info default_lan=`"1033`">`r`n`t`t<lan value=`"2052`" />`r`n`t`t<lan value=`"1033`" />`r`n`t</language.info>`r`n</config>`r`n"
$cfgXmlNoDefault = $cfgXmlBody.Replace(' default_lan="1033"', '')
$cfgXmlOld = "<?xml version=`"1.0`" encoding=`"UTF-8`"?>`r`n<config>`r`n`t<software name=`"AULA F87`" />`r`n</config>`r`n"
$cfgXmlChinese = $cfgXmlBody.Replace('<config>', "<config>`r`n`t<!-- " + [char]0x4E1C + [char]0x839E + [char]0x5E02 + " -->")
$lanCases = @(
    @{ n = 'config.xml without a BOM (5 of 6 vendor builds)'; x = $cfgXmlBody; bom = $false },
    @{ n = 'config.xml WITH a BOM';                           x = $cfgXmlBody; bom = $true },
    @{ n = 'language.info without default_lan';               x = $cfgXmlNoDefault; bom = $false },
    @{ n = 'Chinese text in config.xml (no code-page damage)'; x = $cfgXmlChinese; bom = $false },
    @{ n = 'older build with no language.info (F87 Wired)';   x = $cfgXmlOld; bom = $true; noInfo = $true }
)
foreach ($key in 'F75MAX', 'F98PRO', 'F98pro_V3', 'F106Pro', 'F108Pro', 'F87_Wired') {
    $exe = Join-Path $exeDir "AULA_${key}_driver_mn_setup.exe"
    $srcLan = Join-Path $fs "dist-lan\AULA_${key}_driver\app\language\1104.lan"
    foreach ($case in $lanCases) {
        $g = ".lan $key - $($case.n)"
        try {
            $sb = Join-Path $work ("lan-$key-" + [guid]::NewGuid().ToString('N').Substring(0, 5))
            $inst = Join-Path $sb 'install'
            New-Item -ItemType Directory -Force (Join-Path $inst 'language') | Out-Null
            Set-Content (Join-Path $inst 'DeviceDriver.exe') 'x'
            Set-Content (Join-Path $inst 'language\1033.lan') 'x'
            $orig = $(if ($case.bom) { $utf8bom.GetPreamble() } else { @() }) + $utf8.GetBytes($case.x)
            [IO.File]::WriteAllBytes((Join-Path $inst 'config.xml'), $orig)

            $t = $case.x
            if (-not $case.noInfo) {
                if ($t -match 'default_lan="\d+"') { $t = [regex]::Replace($t, 'default_lan="\d+"', 'default_lan="1104"', 1) }
                else { $t = [regex]::Replace($t, '(<language\.info)', '$1 default_lan="1104"', 1) }
                if ($t -notmatch 'value="1104"') { $t = [regex]::Replace($t, '(<language\.info[^>]*>)', "`$1`r`n`t`t<lan value=`"1104`" />", 1) }
            }
            $expect = $(if ($case.bom) { $utf8bom.GetPreamble() } else { @() }) + $utf8.GetBytes($t)

            $r = Run-Exe $exe @((Sw 'DRIVERDIR' $inst))
            $got = Bytes (Join-Path $inst 'config.xml')
            Check $g 'installer reports no failure' (-not $r.failed) ''
            Check $g 'language\1104.lan is byte-identical to the shipped file' ((Test-Path (Join-Path $inst 'language\1104.lan')) -and (Same (Bytes (Join-Path $inst 'language\1104.lan')) (Bytes $srcLan))) ''
            Check $g 'config.xml is BYTE-IDENTICAL to the independently built expectation' (Same $got $expect) "got $($got.Length) bytes, expected $($expect.Length)"
            $hasBom = ($got.Length -ge 3 -and $got[0] -eq 0xEF -and $got[1] -eq 0xBB -and $got[2] -eq 0xBF)
            Check $g "keeps the vendor's BOM state (had BOM: $($case.bom))" ($hasBom -eq $case.bom) ''
            if (-not $case.noInfo) {
                Check $g 'keeps config.xml.bak = the original' ((Test-Path (Join-Path $inst 'config.xml.bak')) -and (Same (Bytes (Join-Path $inst 'config.xml.bak')) $orig)) ''
            } else {
                Check $g 'config.xml left alone when it has no language.info' (Same $got $orig) ''
            }
            $r2 = Run-Exe $exe @((Sw 'DRIVERDIR' $inst))
            Check $g 'second run changes nothing' ((Same (Bytes (Join-Path $inst 'config.xml')) $got) -and -not $r2.failed) ''
        } catch { Check $g 'test ran to completion' $false ("aborted: " + $_.Exception.Message) }
    }
}

# ================================================================== 3. KYSONA
$testReg = 'HKCU:\Software\PeaklabExeTest'
foreach ($key in 'M600', 'M600_V2') {
    $g = "KYSONA $key"
    try {
        $exe = Join-Path $exeDirKy "KYSONA_${key}_driver_mn_setup.exe"
        $srcXml = (Get-ChildItem (Join-Path $ky "dist\KYSONA_${key}_driver") -Filter '*.xml' | Select-Object -First 1).FullName
        $sb = Join-Path $work ("ky-$key"); $inst = Join-Path $sb 'install'; $lang = Join-Path $inst 'Language'
        New-Item -ItemType Directory -Force $lang | Out-Null
        Set-Content (Join-Path $inst 'Mouse Drive Beta.exe') 'x'
        Set-Content (Join-Path $lang '0-English.xml') 'x'; Set-Content (Join-Path $lang '1-Chinese.xml') 'x'
        Set-Content (Join-Path $lang "5-$mn.xml") 'an OLD Mongolian file with a stale index'
        if (Test-Path $testReg) { Remove-Item $testReg -Recurse -Force }
        $r = Run-Exe $exe @((Sw 'DRIVERDIR' $inst), (Sw 'REGKEY' 'Software\PeaklabExeTest'))
        Check $g 'installer reports no failure' (-not $r.failed) ''
        Check $g 'removes the stale Mongolian file' (-not (Test-Path (Join-Path $lang "5-$mn.xml"))) ''
        Check $g 'adds 2-Монгол.xml (next free index after 0 and 1)' (Test-Path (Join-Path $lang "2-$mn.xml")) ((Get-ChildItem $lang | ForEach-Object Name) -join ',')
        Check $g 'language file is byte-identical to the shipped one' ((Test-Path (Join-Path $lang "2-$mn.xml")) -and (Same (Bytes (Join-Path $lang "2-$mn.xml")) (Bytes $srcXml))) ''
        Check $g 'leaves the existing languages alone' ((Test-Path (Join-Path $lang '0-English.xml')) -and (Test-Path (Join-Path $lang '1-Chinese.xml'))) ''
        $v = $null; try { $v = (Get-ItemProperty $testReg -Name LanguageIndex).LanguageIndex } catch { }
        Check $g 'sets LanguageIndex = 2 as a DWORD' ($v -eq 2) "value = $v"
        $r2 = Run-Exe $exe @((Sw 'DRIVERDIR' $inst), (Sw 'REGKEY' 'Software\PeaklabExeTest'))
        $mnFiles = @(Get-ChildItem $lang -Filter "*$mn*")
        Check $g 'second run replaces rather than duplicates' ($mnFiles.Count -eq 1 -and $mnFiles[0].Name -eq "2-$mn.xml" -and -not $r2.failed) (($mnFiles | ForEach-Object Name) -join ',')
    } catch { Check $g 'test ran to completion' $false ("aborted: " + $_.Exception.Message) }
    finally { if (Test-Path $testReg) { Remove-Item $testReg -Recurse -Force } }
}

# ================================================= 4. the driver SEARCH (probe builds)
$g = 'search'
$ukey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
$keys = @("$ukey\PeaklabExeTestA", "$ukey\PeaklabExeTestB", "$ukey\PeaklabExeTestC")
function Clean-Keys { foreach ($k in $keys) { if (Test-Path $k) { Remove-Item $k -Recurse -Force } } }
try {
    $probe = Join-Path $exeDir 'PROBE_bycombo4.exe'
    function New-ProbeInstall([string]$name) {
        $sb = Join-Path $work $name; $inst = Join-Path $sb 'Program Files (x86)\Vendor\Product'
        New-Item -ItemType Directory -Force $inst | Out-Null; New-Item -ItemType Directory -Force (Join-Path $sb 'lad') | Out-Null
        Set-Content (Join-Path $inst 'PeaklabProbe.exe') 'x'
        [IO.File]::WriteAllBytes((Join-Path $inst 'Cfg.ini'), (New-CfgBytes ($cfgHead + "Lang1=English,en`r`nLang2=$cn,sc`r`n`r`n")))
        return @{ sb = $sb; inst = $inst; lad = (Join-Path $sb 'lad') }
    }
    function Patched($p) { return ([Text.Encoding]::Unicode.GetString((Bytes (Join-Path $p.inst 'Cfg.ini'))) -match "Lang3=$mn,mn") }

    # (a) found through the registry InstallLocation, with a Google-Drive-style decoy beside it
    Clean-Keys; $p = New-ProbeInstall 'search-a'
    $decoy = Join-Path $work 'decoy\Other.exe'; New-Item -ItemType Directory -Force (Split-Path $decoy) | Out-Null; Set-Content $decoy 'x'
    New-Item $keys[0] -Force | Out-Null; New-ItemProperty $keys[0] -Name InstallLocation -Value $p.inst -Force | Out-Null
    New-Item $keys[1] -Force | Out-Null; New-ItemProperty $keys[1] -Name InstallLocation -Value $decoy -Force | Out-Null
    $r = Run-Exe $probe @((Sw 'LAD' $p.lad))
    Check $g 'finds a driver from its registry InstallLocation (any drive)' ((Patched $p) -and -not $r.failed) ''
    Check $g 'an InstallLocation that is an .exe path (Google Drive) does no harm' (-not $r.failed) ''

    # (b) only an uninstaller path recorded, as Inno Setup does
    Clean-Keys; $p = New-ProbeInstall 'search-b'
    New-Item $keys[2] -Force | Out-Null
    New-ItemProperty $keys[2] -Name UninstallString -Value ('"' + (Join-Path $p.inst 'unins000.exe') + '"') -Force | Out-Null
    $r = Run-Exe $probe @((Sw 'LAD' $p.lad))
    Check $g 'finds a driver from the uninstaller path alone' ((Patched $p) -and -not $r.failed) ''

    # (c) not in the registry at all: the folder scan finds it
    Clean-Keys; $p = New-ProbeInstall 'search-c'
    $r = Run-Exe $probe @((Sw 'LAD' $p.lad), (Sw 'SCANROOT' (Join-Path $p.sb 'Program Files (x86)')))
    Check $g 'folder scan finds a driver the registry does not list' ((Patched $p) -and -not $r.failed) ''

    # (d) nowhere: must say so (silent mode cannot ask) and must not run the vendor installer
    Clean-Keys; $p = New-ProbeInstall 'search-d'; Remove-Item (Join-Path $p.inst 'PeaklabProbe.exe')
    $r = Run-Exe $probe @((Sw 'LAD' $p.lad))
    Check $g 'reports failure when the driver is nowhere' ($r.failed) ''
    Check $g 'a test build never launches the vendor installer' ($r.log -match 'vendor installer is NOT run' -or $r.log -notmatch 'vendor installer SHA') ''

    # the other two families' searches (wildcard mask for KYSONA)
    foreach ($fam in @(@('lan', 'PeaklabLan.exe'), @('kysona', 'PeaklabMouse1.exe'))) {
        Clean-Keys
        $sb = Join-Path $work ("search-$($fam[0])"); $inst = Join-Path $sb 'Product'
        New-Item -ItemType Directory -Force $inst | Out-Null
        New-Item -ItemType Directory -Force (Join-Path $inst $(if ($fam[0] -eq 'lan') { 'language' } else { 'Language' })) | Out-Null
        Set-Content (Join-Path $inst $fam[1]) 'x'
        if ($fam[0] -eq 'lan') { [IO.File]::WriteAllBytes((Join-Path $inst 'config.xml'), $utf8.GetBytes($cfgXmlBody)) }
        New-Item $keys[0] -Force | Out-Null; New-ItemProperty $keys[0] -Name InstallLocation -Value $inst -Force | Out-Null
        $exeP = Join-Path $exeDir "PROBE_$($fam[0]).exe"
        $swList = @(); if ($fam[0] -eq 'kysona') { $swList += (Sw 'REGKEY' 'Software\PeaklabExeTest') }
        $r = Run-Exe $exeP $swList
        $added = if ($fam[0] -eq 'lan') { Test-Path (Join-Path $inst 'language\1104.lan') } else { @(Get-ChildItem (Join-Path $inst 'Language') -Filter "*$mn*").Count -eq 1 }
        Check $g "$($fam[0]): found via the registry ($($fam[1]))" ($added -and -not $r.failed) ''
        if (Test-Path $testReg) { Remove-Item $testReg -Recurse -Force }
    }
} catch { Check $g 'test ran to completion' $false ("aborted: " + $_.Exception.Message) }
finally { Clean-Keys }

# ======================================= 5. a FRESH PC: the vendor installer must run
# The commonest customer case is "driver not installed yet". Every other test hands the
# installer a driver folder, so the real path - run the vendor's installer, then carry on -
# would otherwise never execute. The "vendor" here is a stand-in Inno installer of our own
# that drops a stand-in driver into a sandbox and registers it the way AULA's does.
$g = 'fresh PC (vendor installer runs)'
$fakeKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PeaklabFakeVendorForTests_is1'
try {
    $e2e = Join-Path $exeDir 'E2E_bycombo4.exe'
    $sb = Join-Path $work 'e2e'; $fake = Join-Path $sb 'Program Files (x86)\AULA\F65'; $lad = Join-Path $sb 'lad'
    New-Item -ItemType Directory -Force $lad | Out-Null
    if (Test-Path $fakeKey) { Remove-Item $fakeKey -Recurse -Force }
    $env:PEAKLAB_FAKE_DIR = $fake
    $r = Run-Exe $e2e @((Sw 'LAD' $lad))
    Remove-Item Env:PEAKLAB_FAKE_DIR -ErrorAction SilentlyContinue
    Check $g 'the embedded vendor installer was launched and finished' (($r.log -match 'vendor installer SHA-256') -and ($r.log -match 'vendor installer exit code 0')) ($r.log -split "`n" | Select-String 'vendor installer' | Select-Object -First 2)
    Check $g 'the stand-in vendor installed its driver where we told it' (Test-Path (Join-Path $fake 'PeaklabProbe.exe')) ''
    Check $g 'afterwards the installer FOUND that new install (registry) and carried on' ((-not $r.failed) -and ($r.log -match 'adding Mongolian')) ''
    $cfgNow = [Text.Encoding]::Unicode.GetString((Bytes (Join-Path $fake 'Cfg.ini')))
    Check $g 'Cfg.ini now lists Lang3=Монгол,mn' ($cfgNow -match "Lang3=$mn,mn") ''
    Check $g 'Text\mn\text.xml is the shipped F65 language file' ((Test-Path (Join-Path $fake 'Text\mn\text.xml')) -and (Same (Bytes (Join-Path $fake 'Text\mn\text.xml')) (Bytes (Join-Path $fs 'dist\AULA_F65_driver\text.xml')))) ''
    $wantIni = [Text.Encoding]::ASCII.GetBytes("[OPT]`r`nLangIndex=2`r`n")
    Check $g 'lang.ini says LangIndex=2' ((Test-Path (Join-Path $lad 'BYCOMBO4\lang.ini')) -and (Same (Bytes (Join-Path $lad 'BYCOMBO4\lang.ini')) $wantIni)) ''
} catch { Check $g 'test ran to completion' $false ("aborted: " + $_.Exception.Message) }
finally {
    Remove-Item Env:PEAKLAB_FAKE_DIR -ErrorAction SilentlyContinue
    if (Test-Path $fakeKey) { Remove-Item $fakeKey -Recurse -Force }
}

# ============================================================== 6. what ships
$g = 'shipped file'
foreach ($e in @(Get-ChildItem $exeDir -Filter '*_mn_setup.exe') + @(Get-ChildItem $exeDirKy -Filter '*_mn_setup.exe')) {
    $vi = (Get-Item $e.FullName).VersionInfo
    Check $g "$($e.Name): carries Peaklab version info (publisher shown in file properties)" ($vi.CompanyName.Trim() -eq 'Peaklab' -and $vi.ProductName.Trim().Length -gt 0) "$($vi.CompanyName) / $($vi.ProductName)"
}

# ================================================================== report
Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
$fail = 0; $last = ''
foreach ($r in $results) {
    if ($r.group -ne $last) { Write-Host ''; Write-Host "== $($r.group)" -ForegroundColor Cyan; $last = $r.group }
    if (-not $r.ok) { $fail++ }
    $line = '  {0}  {1}' -f $(if ($r.ok) { 'PASS' } else { 'FAIL' }), $r.name
    if (-not $r.ok -and $r.detail) { $line += "   [$($r.detail)]" }
    if (-not $r.ok) { Write-Host $line -ForegroundColor Red }
}
Write-Host ''
Write-Host ("{0} of {1} checks passed" -f ($results.Count - $fail), $results.Count)
if ($fail) { exit 1 } else { exit 0 }
