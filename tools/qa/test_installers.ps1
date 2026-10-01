<#
  Run every customer-facing install script against a sandbox and check what it
  does to the disk.

      powershell -NoProfile -ExecutionPolicy Bypass -File tools\qa\test_installers.ps1
      ... -Root C:\path\containing\the\repos

  WHY THIS EXISTS
  The first release of these installers was never executed by anyone. Every one
  of the five scripts failed to parse on Windows PowerShell 5.1 (UTF-8 without a
  BOM), so customers saw an error flash and a window close. The build had been
  verified; the thing the customer actually runs had not. This test runs it.

  It must run on WINDOWS POWERSHELL 5.1 - the one that ships with Windows 10/11 -
  not pwsh 7, which reads BOM-less UTF-8 happily and would hide the very bug.

  HOW
  Each script is copied, and only two things are changed in the copy: the UAC
  elevation check (cannot be answered unattended) and the driver search, which
  is pointed at a sandbox folder. Everything else - the Cfg.ini / config.xml /
  language-file / registry logic - is the shipped code. The search itself
  (Find-Driver) is tested separately, against fake registry entries.

  Needs only committed files: the pack scripts and the committed language files.
  No vendor binaries.
#>
param([string]$Root)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Root) { $Root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $here)) }

if ($PSVersionTable.PSVersion.Major -ne 5) {
    Write-Host "This test must run on Windows PowerShell 5.1 (found $($PSVersionTable.PSVersion))." -ForegroundColor Red
    Write-Host "pwsh 7 reads BOM-less UTF-8 correctly and would hide the exact bug this test guards against." -ForegroundColor Red
    exit 2
}

$fs  = Join-Path $Root 'aula-fseries-mn'
$ky  = Join-Path $Root 'kysona-m600-mn'
foreach ($d in $fs, $ky) { if (-not (Test-Path $d)) { Write-Host "repo not found: $d" -ForegroundColor Red; exit 2 } }

$mn = ([char]0x041C).ToString() + [char]0x043E + [char]0x043D + [char]0x0433 + [char]0x043E + [char]0x043B   # Монгол
$utf8bom = New-Object Text.UTF8Encoding($true)
$work = Join-Path ([IO.Path]::GetTempPath()) ('peaklab-installer-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $work | Out-Null

$results = New-Object System.Collections.ArrayList
function Check([string]$group, [string]$name, $ok, [string]$detail = '') {
    [void]$results.Add([pscustomobject]@{ group = $group; name = $name; ok = [bool]$ok; detail = $detail })
}
function Same-Bytes($a, $b) { return (($a -join ',') -eq ($b -join ',')) }
function Bytes($p) { return [IO.File]::ReadAllBytes($p) }

# Copy a shipped script, change ONLY the elevation check and the driver search.
function Make-TestScript([string]$source, [string]$destDir, [string]$driverExe) {
    New-Item -ItemType Directory -Force $destDir | Out-Null
    $text = [IO.File]::ReadAllText($source, [Text.Encoding]::UTF8)
    $before = $text
    $text = $text.Replace('if (-not $admin) {', 'if ($false) {')
    $text = [regex]::Replace($text, "\`$exes = @\(Find-Driver '[^']+'\)", "`$exes = @('" + $driverExe + "')")
    if ($text -eq $before) { throw "test harness could not patch $source" }
    $dst = Join-Path $destDir 'run.ps1'
    [IO.File]::WriteAllText($dst, $text, $utf8bom)
    return $dst
}

# Run a script with Enter piped to every prompt; return everything it printed.
function Run-Script([string]$script, [string]$extraArgs = '') {
    $o = & cmd /c "echo.| powershell -NoProfile -ExecutionPolicy Bypass -File `"$script`" $extraArgs 2>&1"
    return ($o -join "`n")
}
$errPattern = 'АЛДАА|Exception|At line|Cannot|missing the terminator'

# =============================================================== 1. static
$scripts = @(
    @{ n = 'F-series one-click (BYCOMBO4)'; p = Join-Path $fs 'pack\install-auto.ps1' },
    @{ n = 'F-series one-click (.lan)';     p = Join-Path $fs 'pack\install-auto-lan.ps1' },
    @{ n = 'F-series language-only';        p = Join-Path $fs 'pack\install-mn.ps1' },
    @{ n = 'KYSONA one-click';              p = Join-Path $ky 'pack\install-auto.ps1' },
    @{ n = 'KYSONA language-only';          p = Join-Path $ky 'pack\install-mn.ps1' }
)
$blockHashes = @{}
foreach ($s in $scripts) {
    $b = Bytes $s.p
    Check 'static' "$($s.n): has a UTF-8 BOM" ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) 'without it Windows PowerShell 5.1 reads Cyrillic as cp1252 and fails to parse'
    $tok = $null; $perr = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($s.p, [ref]$tok, [ref]$perr)
    $first = if ($perr.Count) { $perr[0].Message } else { '' }
    Check 'static' "$($s.n): parses on Windows PowerShell $($PSVersionTable.PSVersion)" ($perr.Count -eq 0) $first
    $src = [IO.File]::ReadAllText($s.p, [Text.Encoding]::UTF8)
    $i = $src.IndexOf('#region peaklab-common'); $j = $src.IndexOf('#endregion peaklab-common')
    if ($i -ge 0 -and $j -gt $i) {
        $blk = $src.Substring($i, $j - $i).Replace("`r`n", "`n")
        $blockHashes[[BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($blk)))] = 1
        Check 'static' "$($s.n): has the error handler" ($blk -match '(?m)^trap \{') ''
    } else { Check 'static' "$($s.n): has the shared block" $false 'region markers missing' }
}
Check 'static' 'shared block identical in all five scripts' ($blockHashes.Count -eq 1) "$($blockHashes.Count) distinct version(s)"
foreach ($bat in @((Join-Path $fs 'pack\install-mn.bat'), (Join-Path $ky 'pack\install-mn.bat'))) {
    $t = [IO.File]::ReadAllText($bat)
    Check 'static' "$(Split-Path -Leaf (Split-Path -Parent (Split-Path -Parent $bat)))\pack\install-mn.bat: pauses and uses CRLF" (($t -match '(?im)^pause\s*$') -and -not ($t -match '(?<!\r)\n')) 'a launcher that closes on error hides the error'
}
foreach ($bp in @('aula-fseries-mn\tools\bundle.py', 'aula-fseries-mn\tools\bundle_lan.py', 'kysona-m600-mn\tools\bundle.py')) {
    $t = [IO.File]::ReadAllText((Join-Path $Root $bp))
    Check 'static' "${bp}: generated launcher ends with pause" ($t -match '(?m)^BAT = .*pause') ''
}

# ===================================================== 2. Find-Driver (D: etc.)
try {
$srcA = [IO.File]::ReadAllText($scripts[0].p, [Text.Encoding]::UTF8)
$blockText = $srcA.Substring($srcA.IndexOf('#region peaklab-common'), $srcA.IndexOf('#endregion peaklab-common') - $srcA.IndexOf('#region peaklab-common'))
$trapless = [regex]::Replace($blockText, '(?s)trap \{.*?\r?\n\}\r?\n', '')   # do not install the trap into this session
. ([scriptblock]::Create($trapless))

$fake = Join-Path $work 'FakeDrive\Program Files (x86)\Vendor\Product'
New-Item -ItemType Directory -Force $fake | Out-Null
Set-Content (Join-Path $fake 'PeaklabProbe.exe') 'x'
$decoyExe = Join-Path $work 'decoy\Other.exe'
New-Item -ItemType Directory -Force (Split-Path $decoyExe) | Out-Null
Set-Content $decoyExe 'x'
$ukey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
$k1 = "$ukey\PeaklabTestA"; $k2 = "$ukey\PeaklabTestB"; $k3 = "$ukey\PeaklabTestC"
try {
    New-Item $k1 -Force | Out-Null; New-ItemProperty $k1 -Name InstallLocation -Value $fake -Force | Out-Null
    # what Google Drive does: InstallLocation is the path of an .exe, not a folder
    New-Item $k2 -Force | Out-Null; New-ItemProperty $k2 -Name InstallLocation -Value $decoyExe -Force | Out-Null
    # only an uninstaller recorded, as Inno Setup does
    New-Item $k3 -Force | Out-Null; New-ItemProperty $k3 -Name UninstallString -Value ('"' + (Join-Path $fake 'unins000.exe') + '"') -Force | Out-Null

    $r = @(Find-Driver 'PeaklabProbe.exe')
    Check 'Find-Driver' 'finds a driver recorded in the registry (any drive, e.g. D:)' ($r.Count -ge 1 -and $r -contains (Join-Path $fake 'PeaklabProbe.exe')) ($r -join ' ; ')
    Check 'Find-Driver' 'finds it through the uninstaller path alone' ($r.Count -eq 1) "got $($r.Count) result(s) - the same exe via two entries must collapse to one"
    $none = @(Find-Driver 'NoSuchPeaklabDriver.exe')
    Check 'Find-Driver' 'returns NOTHING for a driver that is not there' ($none.Count -eq 0) ($none -join ' ; ')
    $wild = @(Find-Driver 'PeaklabPro*.exe')
    Check 'Find-Driver' 'wildcard names work (KYSONA: Mouse Drive*.exe)' ($wild.Count -eq 1) ($wild -join ' ; ')
    $leaf = @(Find-Driver 'Other.exe')
    Check 'Find-Driver' 'an InstallLocation that is an .exe path (Google Drive) is not treated as a folder' ($leaf.Count -le 1 -and -not ($leaf | Where-Object { $_ -notlike '*Other.exe' })) ($leaf -join ' ; ')
} finally {
    foreach ($k in $k1, $k2, $k3) { if (Test-Path $k) { Remove-Item $k -Recurse -Force } }
}
} catch {
    Check 'Find-Driver' 'section ran to completion' $false ("aborted: " + $_.Exception.Message)
}

# ====================================================== 3. F-series BYCOMBO4
try {
$cfgFixture = "[OPT]`r`nTitle=AULA F65`r`nAppdir=BYCOMBO4`r`nClrLine=49,49,49`r`nGoWithNoDev=0`r`nMacLayout=1`r`n`r`nLang1=English,en`r`nLang2=" + [char]0x7B80 + [char]0x4F53 + [char]0x4E2D + [char]0x6587 + ",sc`r`n`r`n"
foreach ($mode in 'auto', 'langonly') {
    $g = "F-series BYCOMBO4 ($mode)"
    $sb = Join-Path $work "bycombo4-$mode"
    $inst = Join-Path $sb 'install'; $lad = Join-Path $sb 'localappdata'; $bundle = Join-Path $sb 'bundle'
    New-Item -ItemType Directory -Force (Join-Path $inst 'Text\en') | Out-Null
    New-Item -ItemType Directory -Force $lad | Out-Null; New-Item -ItemType Directory -Force $bundle | Out-Null
    Set-Content (Join-Path $inst 'OemDrv.exe') 'x'
    [IO.File]::WriteAllBytes((Join-Path $inst 'Cfg.ini'), (New-Object Text.UnicodeEncoding($false, $true)).GetPreamble() + [Text.Encoding]::Unicode.GetBytes($cfgFixture))
    $orig = Bytes (Join-Path $inst 'Cfg.ini')
    $srcXml = Join-Path $fs 'dist\AULA_F65_driver\text.xml'
    if ($mode -eq 'auto') {
        New-Item -ItemType Directory -Force (Join-Path $bundle 'lang') | Out-Null
        Copy-Item $srcXml (Join-Path $bundle 'lang\text.xml')
        $script = Make-TestScript (Join-Path $fs 'pack\install-auto.ps1') $bundle (Join-Path $inst 'OemDrv.exe')
        $run = { Run-Script $script "-Applied -UserLocalAppData `"$lad`"" }
    } else {
        Copy-Item $srcXml (Join-Path $bundle 'text.xml')
        $script = Make-TestScript (Join-Path $fs 'pack\install-mn.ps1') $bundle (Join-Path $inst 'OemDrv.exe')
        $run = { Run-Script $script }
    }
    $out = & $run
    Check $g 'runs without an error' ($out -notmatch $errPattern) (($out -split "`n" | Select-String $errPattern | Select-Object -First 1) -join '')
    $b = Bytes (Join-Path $inst 'Cfg.ini'); $cfg = [Text.Encoding]::Unicode.GetString($b)
    Check $g 'Cfg.ini stays UTF-16 LE with BOM' ($b[0] -eq 0xFF -and $b[1] -eq 0xFE) ''
    Check $g 'adds Lang3=Монгол,mn directly after Lang2' ($cfg -match "Lang2=.*\r\nLang3=$mn,mn\r\n") ''
    Check $g 'Cfg.ini is CRLF only' (-not ($cfg -match '(?<!\r)\n')) ''
    $oldL = ([Text.Encoding]::Unicode.GetString($orig) -replace "`r`n", "`n").TrimEnd("`n").Split("`n")
    $newL = ($cfg -replace "`r`n", "`n").TrimEnd("`n").Split("`n")
    Check $g 'changes exactly one line (adds one, removes none)' (@($newL | Where-Object { $oldL -notcontains $_ }).Count -eq 1 -and @($oldL | Where-Object { $newL -notcontains $_ }).Count -eq 0) ''
    Check $g 'keeps a .bak of the original' ((Test-Path (Join-Path $inst 'Cfg.ini.bak')) -and (Same-Bytes (Bytes (Join-Path $inst 'Cfg.ini.bak')) $orig)) ''
    Check $g 'copies Text\mn\text.xml unchanged' ((Test-Path (Join-Path $inst 'Text\mn\text.xml')) -and (Same-Bytes (Bytes (Join-Path $inst 'Text\mn\text.xml')) (Bytes $srcXml))) ''
    if ($mode -eq 'auto') {
        $ini = Join-Path $lad 'BYCOMBO4\lang.ini'
        $want = [Text.Encoding]::ASCII.GetBytes("[OPT]`r`nLangIndex=2`r`n")
        Check $g 'lang.ini = "[OPT] LangIndex=2" (0-based index of Lang3), byte-exact' ((Test-Path $ini) -and (Same-Bytes (Bytes $ini) $want)) ''
    }
    $out2 = & $run; $cfg2 = [Text.Encoding]::Unicode.GetString((Bytes (Join-Path $inst 'Cfg.ini')))
    Check $g 'second run is idempotent (still exactly 3 Lang lines)' ($out2 -notmatch $errPattern -and ([regex]::Matches($cfg2, '(?m)^Lang\d+=')).Count -eq 3) ''
    # driver not found -> must say so and wait, not vanish
    $nf = Make-TestScript (Join-Path $fs $(if ($mode -eq 'auto') { 'pack\install-auto.ps1' } else { 'pack\install-mn.ps1' })) (Join-Path $sb 'notfound') (Join-Path $work 'does\not\exist\OemDrv.exe')
    if ($mode -eq 'auto') { New-Item -ItemType Directory -Force (Join-Path $sb 'notfound\lang') | Out-Null; Copy-Item $srcXml (Join-Path $sb 'notfound\lang\text.xml'); $o3 = Run-Script $nf "-Applied -UserLocalAppData `"$lad`"" }
    else { Copy-Item $srcXml (Join-Path $sb 'notfound\text.xml'); $o3 = Run-Script $nf }
}
} catch {
    Check 'F-series BYCOMBO4' 'section ran to completion' $false ("aborted: " + $_.Exception.Message)
}

# ========================================================== 4. F-series .lan
try {
$g = 'F-series .lan family (one-click)'
$sb = Join-Path $work 'lan'; $inst = Join-Path $sb 'install'; $bundle = Join-Path $sb 'bundle'
New-Item -ItemType Directory -Force (Join-Path $inst 'language') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $bundle 'lang') | Out-Null
Set-Content (Join-Path $inst 'DeviceDriver.exe') 'x'
foreach ($l in '1033', '2052') { Set-Content (Join-Path $inst "language\$l.lan") 'x' }
$cfgXml = "<?xml version=`"1.0`" encoding=`"UTF-8`"?>`r`n<config>`r`n`t<language.info default_lan=`"1033`">`r`n`t`t<lan value=`"2052`" />`r`n`t`t<lan value=`"1033`" />`r`n`t</language.info>`r`n</config>`r`n"
$srcLan = Join-Path $fs 'dist-lan\AULA_F106Pro_driver\app\language\1104.lan'
Copy-Item $srcLan (Join-Path $bundle 'lang\1104.lan')
foreach ($bomCase in $false, $true) {
    $gg = "$g, vendor config.xml " + $(if ($bomCase) { 'WITH BOM' } else { 'without BOM' })
    [IO.File]::WriteAllBytes((Join-Path $inst 'config.xml'), $(if ($bomCase) { $utf8bom.GetPreamble() } else { @() }) + (New-Object Text.UTF8Encoding($false)).GetBytes($cfgXml))
    Remove-Item (Join-Path $inst 'config.xml.bak') -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $inst 'language\1104.lan') -ErrorAction SilentlyContinue
    $orig = Bytes (Join-Path $inst 'config.xml')
    $script = Make-TestScript (Join-Path $fs 'pack\install-auto-lan.ps1') $bundle (Join-Path $inst 'DeviceDriver.exe')
    $out = Run-Script $script '-Applied'
    Check $gg 'runs without an error' ($out -notmatch $errPattern) (($out -split "`n" | Select-String $errPattern | Select-Object -First 1) -join '')
    Check $gg 'copies language\1104.lan unchanged' ((Test-Path (Join-Path $inst 'language\1104.lan')) -and (Same-Bytes (Bytes (Join-Path $inst 'language\1104.lan')) (Bytes $srcLan))) ''
    $b = Bytes (Join-Path $inst 'config.xml'); $t = [Text.Encoding]::UTF8.GetString($b)
    Check $gg 'registers <lan value="1104" />' ($t -match '<lan value="1104" />') ''
    Check $gg 'makes 1104 the default language' ($t -match 'default_lan="1104"') ''
    $hasBom = ($b.Length -ge 3 -and $b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)
    Check $gg "keeps the vendor's BOM state exactly (had BOM: $bomCase)" ($hasBom -eq $bomCase) 'adding a BOM to AULA''s file is a change nobody asked for and nobody has tested'
    Check $gg 'config.xml stays CRLF only' (-not ($t -match '(?<!\r)\n')) ''
    Check $gg 'keeps a .bak of the original' ((Test-Path (Join-Path $inst 'config.xml.bak')) -and (Same-Bytes (Bytes (Join-Path $inst 'config.xml.bak')) $orig)) ''
    $out2 = Run-Script $script '-Applied'
    Check $gg 'second run does not duplicate the <lan> entry' (([regex]::Matches([Text.Encoding]::UTF8.GetString((Bytes (Join-Path $inst 'config.xml'))), 'value="1104"')).Count -eq 1) ''
}
} catch {
    Check 'F-series .lan' 'section ran to completion' $false ("aborted: " + $_.Exception.Message)
}

# ================================================================== 5. KYSONA
try {
foreach ($mode in 'auto', 'langonly') {
    $g = "KYSONA ($mode)"
    $sb = Join-Path $work "kysona-$mode"; $inst = Join-Path $sb 'install'; $bundle = Join-Path $sb 'bundle'
    $langDir = Join-Path $inst 'Language'
    New-Item -ItemType Directory -Force $langDir | Out-Null; New-Item -ItemType Directory -Force $bundle | Out-Null
    Set-Content (Join-Path $inst 'Mouse Drive Beta.exe') 'x'
    Set-Content (Join-Path $langDir '0-English.xml') 'x'; Set-Content (Join-Path $langDir '1-Chinese.xml') 'x'
    $srcKy = Join-Path $ky 'dist\KYSONA_M600_driver\2-' ; $srcKy = (Get-ChildItem (Join-Path $ky 'dist\KYSONA_M600_driver') -Filter '*.xml' | Select-Object -First 1).FullName
    if ($mode -eq 'auto') {
        New-Item -ItemType Directory -Force (Join-Path $bundle 'lang') | Out-Null; Copy-Item $srcKy (Join-Path $bundle 'lang\text.xml')
        $script = Make-TestScript (Join-Path $ky 'pack\install-auto.ps1') $bundle (Join-Path $inst 'Mouse Drive Beta.exe')
        # never touch the real HKCU\Software\Compx
        $t = [IO.File]::ReadAllText($script, [Text.Encoding]::UTF8).Replace("'HKCU:\Software\Compx'", "'HKCU:\Software\PeaklabInstallerTest'")
        [IO.File]::WriteAllText($script, $t, $utf8bom)
        if (Test-Path 'HKCU:\Software\PeaklabInstallerTest') { Remove-Item 'HKCU:\Software\PeaklabInstallerTest' -Recurse -Force }
        $out = Run-Script $script '-Applied'
    } else {
        Copy-Item $srcKy (Join-Path $bundle 'lang.xml')
        $script = Make-TestScript (Join-Path $ky 'pack\install-mn.ps1') $bundle (Join-Path $inst 'Mouse Drive Beta.exe')
        $out = Run-Script $script
    }
    Check $g 'runs without an error' ($out -notmatch $errPattern) (($out -split "`n" | Select-String $errPattern | Select-Object -First 1) -join '')
    $added = @(Get-ChildItem $langDir -Filter '*.xml' | Where-Object { $_.Name -like "*$mn*" })
    Check $g 'adds exactly one Монгол language file' ($added.Count -eq 1) (($added | ForEach-Object Name) -join ',')
    Check $g 'takes the next free index (2-Монгол.xml)' ($added.Count -eq 1 -and $added[0].Name -eq "2-$mn.xml") (($added | ForEach-Object Name) -join ',')
    Check $g 'language file is byte-identical to the shipped one' ($added.Count -eq 1 -and (Same-Bytes (Bytes $added[0].FullName) (Bytes $srcKy))) ''
    Check $g 'leaves the existing languages alone' ((Test-Path (Join-Path $langDir '0-English.xml')) -and (Test-Path (Join-Path $langDir '1-Chinese.xml'))) ''
    if ($mode -eq 'auto') {
        $v = $null; try { $v = (Get-ItemProperty 'HKCU:\Software\PeaklabInstallerTest' -Name LanguageIndex).LanguageIndex } catch { }
        Check $g 'sets LanguageIndex = 2 as a DWORD' ($v -eq 2) "value = $v"
        if (Test-Path 'HKCU:\Software\PeaklabInstallerTest') { Remove-Item 'HKCU:\Software\PeaklabInstallerTest' -Recurse -Force }
    }
    $out2 = if ($mode -eq 'auto') { Run-Script $script '-Applied' } else { Run-Script $script }
    $added2 = @(Get-ChildItem $langDir -Filter '*.xml' | Where-Object { $_.Name -like "*$mn*" })
    Check $g 'second run replaces rather than duplicates' ($out2 -notmatch $errPattern -and $added2.Count -eq 1) "$($added2.Count) file(s)"
    if (Test-Path 'HKCU:\Software\PeaklabInstallerTest') { Remove-Item 'HKCU:\Software\PeaklabInstallerTest' -Recurse -Force }
}
} catch {
    Check 'KYSONA' 'section ran to completion' $false ("aborted: " + $_.Exception.Message)
}

# ======================================================= 6. the built zips
# dist-auto/ is gitignored (it holds vendor installers), so CI skips this; run
# locally it catches the case that matters most: a zip built BEFORE a fix, about
# to be published. Every script in every zip must be byte-identical to the
# current pack source.
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipCount = 0
    foreach ($repo in @($fs, $ky)) {
        $srcScripts = @(Get-ChildItem (Join-Path $repo 'pack') -Filter '*.ps1' | ForEach-Object { , (Bytes $_.FullName) })
        foreach ($sub in 'dist-auto', 'dist') {
            $zdir = Join-Path $repo $sub
            if (-not (Test-Path $zdir)) { continue }
            foreach ($zf in Get-ChildItem $zdir -Filter '*.zip') {
                $zipCount++
                $z = [IO.Compression.ZipFile]::OpenRead($zf.FullName)
                try {
                    foreach ($en in $z.Entries) {
                        if ($en.Name -like '*.ps1') {
                            $ms = New-Object IO.MemoryStream; $st = $en.Open(); $st.CopyTo($ms); $st.Close()
                            $zb = $ms.ToArray()
                            $isCurrent = $false
                            foreach ($cand in $srcScripts) { if (Same-Bytes $zb $cand) { $isCurrent = $true } }
                            Check 'built zips' "$($zf.Name): $($en.Name) is the current pack script" $isCurrent 'stale zip - built before the fix?'
                        }
                        if ($en.Name -like '*.bat') {
                            $sr = New-Object IO.StreamReader($en.Open()); $bt = $sr.ReadToEnd(); $sr.Close()
                            Check 'built zips' "$($zf.Name): $($en.Name) pauses" ($bt -match '(?im)^pause\s*$') 'a launcher that closes on error hides the error'
                        }
                    }
                } finally { $z.Dispose() }
            }
        }
    }
    if ($zipCount -eq 0) { Write-Host '  (no built zips found - skipping the built-zip check)' -ForegroundColor DarkGray }
} catch {
    Check 'built zips' 'section ran to completion' $false ("aborted: " + $_.Exception.Message)
}

# ================================================================== report
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
$fail = 0; $lastGroup = ''
foreach ($r in $results) {
    if ($r.group -ne $lastGroup) { Write-Host ''; Write-Host "== $($r.group)" -ForegroundColor Cyan; $lastGroup = $r.group }
    if (-not $r.ok) { $fail++ }
    $line = '  {0}  {1}' -f $(if ($r.ok) { 'PASS' } else { 'FAIL' }), $r.name
    if (-not $r.ok -and $r.detail) { $line += "   [$($r.detail)]" }
    Write-Host $line -ForegroundColor $(if ($r.ok) { 'Gray' } else { 'Red' })
}
Write-Host ''
Write-Host ("{0} of {1} checks passed on Windows PowerShell {2}" -f ($results.Count - $fail), $results.Count, $PSVersionTable.PSVersion)
if ($fail) { exit 1 } else { exit 0 }
