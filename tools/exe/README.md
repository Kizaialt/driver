# One-file installers

A customer gets **one `.exe`** and a normal Windows wizard in Mongolian. No zip to unpack,
no `.bat`, no PowerShell window. Built with Inno Setup 6 (the tool AULA's own installers
use) from `peaklab.iss`.

What the exe does, in order:

1. Looks for the driver **on any drive**: Windows' own Uninstall registry entries
   (`InstallLocation`, then the uninstaller's folder), then a scan of every drive's
   `Program Files`. If it is not there, the vendor's own **unmodified** installer, embedded
   in the exe, is run and its wizard shown. (If the driver is already installed it is not
   reinstalled.)
2. Adds the Mongolian language file next to the vendor's own languages, using the app's own
   language mechanism. **The driver binary is never touched.**
3. Makes the driver open in Mongolian.

| family | models | language file | made the default by |
|---|---|---|---|
| `bycombo4` | F65, F65 Pro, F75, F99, F99 Pro, F108 | `Text\mn\text.xml` | one `LangN=Монгол,mn` line in `Cfg.ini` + `%LOCALAPPDATA%\BYCOMBO4\lang.ini` |
| `lan` | F75 MAX, F98 Pro, F98 Pro V3, F106 Pro, F108 Pro, F87 Wired | `language\1104.lan` | `config.xml` (`<lan value="1104"/>`, `default_lan`) |
| `kysona` | M600, M600 V2 | `Language\<n>-Монгол.xml` | `HKCU\Software\Compx\LanguageIndex` |

`Cfg.ini` (UTF-16) and `config.xml` (UTF-8, often no BOM) are edited **as raw bytes**: exactly
one line is added and nothing else in AULA's file changes. This is checked byte-for-byte.

## Build

    winget install JRSoftware.InnoSetup
    python tools/exe/build_exe.py                 # every model -> <pack repo>/dist-exe/
    python tools/exe/build_exe.py --only F65

Output is **gitignored**: each exe embeds a vendor installer. Publish them as GitHub release
assets, like the zips. The vendor installer's SHA-256 is written to the setup log.

## Test

    powershell -ExecutionPolicy Bypass -File tools\qa\test_exe_installers.ps1

~370 checks: every model, every family, every `Cfg.ini` / `config.xml` shape (no BOM, BOM,
Chinese text, no default, older build with no `language.info`, already registered), the
driver search (registry, uninstaller path, a decoy `InstallLocation` that is an `.exe`,
folder scan, nothing found) and a **fresh PC** where the vendor installer really runs (a
stand-in built from `fake_vendor.iss`). Each expected file is built independently in
PowerShell from the original bytes, not by re-running the installer's logic.

TEST builds (`--test`) differ from shipping builds only in that they ask for no
administrator rights and **never launch a vendor installer** - on a developer PC that would
be a real AULA installer. They take hidden switches (`/DRIVERDIR`, `/LAD`, `/REGKEY`,
`/SCANROOT`). `--probe` builds look for a made-up driver name so the search can be tested
without finding (and patching) a real driver on the machine.

## Not code-signed (yet)

Windows shows "Windows protected your PC" for an unsigned exe from an unknown publisher.
AULA's own F-series installers are signed; KYSONA's are not. The portal tells the customer
what they will see and offers the old zip as a fallback. Signing is the real fix: build the
exe, then `signtool sign ... *.exe`. The shipped build also refuses to run without
administrator rights and says so in Mongolian.

## Verified vs not

Verified in a sandbox and in the wizard UI: everything above. **Not verified on a real
keyboard or mouse**: that the vendor's app then starts and renders Mongolian well for every
model (confirmed by hand for the F65 only), and the elevation prompt of the *shipping*
build (test builds do not elevate).
