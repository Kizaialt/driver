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

## Signing, and why Windows warns

Windows (SmartScreen) judges two things: who signed the file, and whether that exact file or
signer has been downloaded often without trouble. Microsoft's own page
(learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation, updated
2026-08) says:

| file | first-download behaviour |
|---|---|
| unsigned, or self-signed | strong "Windows protected your PC" |
| signed with a real OV/EV certificate | **still warns** until reputation builds ("several weeks and hundreds of clean installs"), but names the verified publisher |
| EV | no longer instant - same as OV since 2024 |
| Microsoft Store | no warning at all |

So there is no code trick that removes the screen for a new publisher. What helps: sign every
release with the SAME certificate (reputation carries over; unsigned files start from zero
each release), and the publisher name replaces "Unknown publisher".

Options for a Mongolian publisher: Microsoft's cheap Artifact Signing (about $10/month) is
only for organisations in the US/Canada/EU/UK, so a traditional OV certificate (roughly
$130-300/year; SSL.com sells an individual-validation one, a business needs company papers)
is the realistic route. SignPath Foundation's free signing needs all-open-source code, and an
exe that embeds AULA's installer does not qualify. The Microsoft Store supports Mongolia and is
free for individuals, but a Store app that edits another vendor's installation is a poor fit.
The zero-warning route is for AULA and KYSONA to ship the Mongolian files in their own signed
installers.

Even the old zip + .bat is not warning-free: a .bat from the internet shows "Open File -
Security Warning".

### Signing a build

    $env:PEAKLAB_CERT_THUMBPRINT = '<thumbprint>'      # cert in Cert:\CurrentUser\My or LocalMachine\My
    python tools/exe/build_exe.py --sign

`sign_exe.ps1` uses only what ships with Windows (Set-AuthenticodeSignature), SHA-256, RFC 3161
timestamp, and exits non-zero unless every file ends up `Valid`. Certificates on a USB token or
in a cloud HSM (SSL.com eSigner, Certum SimplySign...) appear in that store through the vendor's
client. `--allow-untrusted` exists only to prove the pipeline with a self-signed certificate
(done: signs, timestamps, the signed installer still runs); such files must never be published.

## Verified vs not

Verified in a sandbox and in the wizard UI: everything above. **Not verified on a real
keyboard or mouse**: that the vendor's app then starts and renders Mongolian well for every
model (confirmed by hand for the F65 only), and the elevation prompt of the *shipping*
build (test builds do not elevate).
