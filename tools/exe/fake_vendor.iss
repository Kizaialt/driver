; A harmless stand-in for a vendor's installer, used ONLY by the end-to-end test.
; Like the real AULA installer it is an Inno Setup program that copies a driver into
; a folder and records it in the Uninstall registry key (with InstallLocation), but it
; installs into a sandbox folder given by the PEAKLAB_FAKE_DIR environment variable.
;   ISCC /DSRCDIR=<folder with PeaklabProbe.exe and Cfg.ini> /DOUTDIR=<out> fake_vendor.iss
#ifndef SRCDIR
  #error SRCDIR is required
#endif
#ifndef OUTDIR
  #define OUTDIR "."
#endif
[Setup]
AppId=PeaklabFakeVendorForTests
AppName=Peaklab Fake Vendor
AppVersion=1.0
DefaultDirName={%PEAKLAB_FAKE_DIR|C:\PeaklabFakeVendor}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=yes
PrivilegesRequired=lowest
OutputDir={#OUTDIR}
OutputBaseFilename=fake_vendor
Compression=none
[Files]
Source: "{#SRCDIR}\PeaklabProbe.exe"; DestDir: "{app}"
Source: "{#SRCDIR}\Cfg.ini"; DestDir: "{app}"
