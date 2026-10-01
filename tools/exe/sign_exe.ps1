<#
  Code-sign the one-file installers (Authenticode, SHA-256, RFC 3161 timestamp).

      $env:PEAKLAB_CERT_THUMBPRINT = '<thumbprint of your code-signing certificate>'
      python tools/exe/build_exe.py --sign

  or directly:   powershell -File tools\exe\sign_exe.ps1 -Files a.exe,b.exe

  The certificate must be in Cert:\CurrentUser\My or Cert:\LocalMachine\My. That is where a
  cloud-HSM / token vendor's client (SSL.com eSigner, Certum SimplySign, a USB token...)
  exposes it, so this works with any certificate authority that issues a standard
  Authenticode code-signing certificate. Uses only what ships with Windows
  (Set-AuthenticodeSignature): no Windows SDK needed.

  Always timestamped, so the signature stays valid after the certificate expires.

  -AllowUntrusted   accept a certificate Windows does not trust (a self-signed one). ONLY for
                    proving this pipeline works; such a file is NOT safe to publish.
  -NoTimestamp      skip the timestamp. Same warning: tests only.

  Exits non-zero unless every file ends up with a Valid signature (or, with -AllowUntrusted,
  a signature whose only problem is an untrusted root).
#>
param(
    [Parameter(Mandatory = $true)][string[]]$Files,
    [string]$Thumbprint = $env:PEAKLAB_CERT_THUMBPRINT,
    [string]$TimestampUrl = $(if ($env:PEAKLAB_TIMESTAMP_URL) { $env:PEAKLAB_TIMESTAMP_URL } else { 'http://timestamp.digicert.com' }),
    [switch]$AllowUntrusted,
    [switch]$NoTimestamp
)
$ErrorActionPreference = 'Stop'

if (-not $Thumbprint) {
    Write-Host 'No certificate chosen. Set PEAKLAB_CERT_THUMBPRINT to the thumbprint of your code-signing' -ForegroundColor Red
    Write-Host 'certificate (see: Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert).' -ForegroundColor Red
    exit 2
}
$Thumbprint = ($Thumbprint -replace '\s', '').ToUpper()

$cert = $null
foreach ($store in 'Cert:\CurrentUser\My', 'Cert:\LocalMachine\My') {
    $cert = Get-ChildItem $store -ErrorAction SilentlyContinue | Where-Object { $_.Thumbprint -eq $Thumbprint } | Select-Object -First 1
    if ($cert) { break }
}
if (-not $cert) { Write-Host "Certificate $Thumbprint not found in the CurrentUser or LocalMachine 'My' store." -ForegroundColor Red; exit 2 }
if (-not $cert.HasPrivateKey) { Write-Host 'That certificate has no private key here (is the token / cloud-signing client connected?).' -ForegroundColor Red; exit 2 }
if ($cert.NotAfter -lt (Get-Date)) { Write-Host "That certificate expired on $($cert.NotAfter)." -ForegroundColor Red; exit 2 }
Write-Host ("signing with: {0}   (expires {1:yyyy-MM-dd})" -f $cert.Subject, $cert.NotAfter)

$fail = 0
foreach ($f in $Files) {
    $path = (Resolve-Path -LiteralPath $f).Path
    $args2 = @{ FilePath = $path; Certificate = $cert; HashAlgorithm = 'SHA256' }
    if (-not $NoTimestamp) { $args2.TimestampServer = $TimestampUrl }
    try {
        [void](Set-AuthenticodeSignature @args2)
    } catch {
        Write-Host ("  FAIL  {0}: {1}" -f (Split-Path -Leaf $path), $_.Exception.Message) -ForegroundColor Red
        $fail++; continue
    }
    $s = Get-AuthenticodeSignature -LiteralPath $path
    $stamped = [bool]$s.TimeStamperCertificate
    # An untrusted root reports as UnknownError; that is the ONLY problem -AllowUntrusted forgives.
    $ok = ($s.Status -eq 'Valid') -or ($AllowUntrusted -and $s.Status -eq 'UnknownError' -and $s.SignerCertificate)
    if (-not $NoTimestamp -and -not $stamped) { $ok = $false }
    Write-Host ("  {0}  {1}   status={2}  timestamped={3}" -f $(if ($ok) { 'ok  ' } else { 'FAIL' }), (Split-Path -Leaf $path), $s.Status, $stamped) -ForegroundColor $(if ($ok) { 'Gray' } else { 'Red' })
    if (-not $ok) { $fail++ }
}
if ($fail) { exit 1 } else { exit 0 }
