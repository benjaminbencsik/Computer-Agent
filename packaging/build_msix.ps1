<#
.SYNOPSIS
    Packages the PyInstaller build of Computer Agent as a signed MSIX.

.DESCRIPTION
    Requires the Windows SDK (for makeappx.exe and signtool.exe) and a completed
    PyInstaller build at dist\ComputerAgent (see .github\workflows\windows-build.yml
    for the pyinstaller invocation this expects).

    This script does NOT embed or fetch a code-signing certificate -- there isn't one
    checked into this repository, and there shouldn't be. Before running with -Sign,
    obtain your own certificate (an Azure Trusted Signing profile, a hardware token, or
    a traditional .pfx from a CA) and either:
      - pass -CertPath/-CertPassword for a .pfx, or
      - pass -CertThumbprint to sign with a certificate already in the machine/user
        certificate store (e.g. installed from a hardware token or smart card).

    Also update packaging\msix\AppxManifest.xml's Identity/Publisher to exactly match
    your certificate's Subject before signing -- MSIX validation rejects a mismatch.

.EXAMPLE
    .\packaging\build_msix.ps1 -Sign -CertPath C:\secrets\codesign.pfx -CertPassword $env:CODESIGN_PASSWORD
#>
param(
    [string]$DistDir = "dist\ComputerAgent",
    [string]$OutputDir = "dist-msix",
    [switch]$Sign,
    [string]$CertPath,
    [string]$CertPassword,
    [string]$CertThumbprint
)

$ErrorActionPreference = "Stop"

$makeappx = (Get-Command makeappx.exe -ErrorAction SilentlyContinue).Source
if (-not $makeappx) {
    throw "makeappx.exe not found. Install the Windows 10/11 SDK and run this from a Developer PowerShell."
}

if (-not (Test-Path $DistDir)) {
    throw "PyInstaller output not found at '$DistDir'. Build it first, e.g.:`n" +
          "  pyinstaller --noconfirm --clean --windowed --name ComputerAgent --paths src --collect-all pyautogui launcher.py"
}

$assetsDir = Join-Path $PSScriptRoot "msix\Assets"
if (-not (Test-Path $assetsDir)) {
    throw "Missing $assetsDir. MSIX requires Square44x44Logo.png, Square150x150Logo.png, and " +
          "StoreLogo.png (see AppxManifest.xml) -- add your own app icon assets there first."
}

$stagingDir = Join-Path $env:TEMP "computer-agent-msix-staging"
if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
New-Item -ItemType Directory -Path $stagingDir | Out-Null

Copy-Item "$DistDir\*" $stagingDir -Recurse
Copy-Item (Join-Path $PSScriptRoot "msix\AppxManifest.xml") $stagingDir
Copy-Item $assetsDir (Join-Path $stagingDir "Assets") -Recurse

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$msixPath = Join-Path $OutputDir "ComputerAgent.msix"

& $makeappx pack /d $stagingDir /p $msixPath /overwrite
if ($LASTEXITCODE -ne 0) { throw "makeappx failed with exit code $LASTEXITCODE" }
Write-Host "Built $msixPath"

if ($Sign) {
    $signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
    if (-not $signtool) {
        throw "signtool.exe not found. Install the Windows 10/11 SDK and run this from a Developer PowerShell."
    }
    if ($CertThumbprint) {
        & $signtool sign /sha1 $CertThumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $msixPath
    } elseif ($CertPath) {
        & $signtool sign /f $CertPath /p $CertPassword /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $msixPath
    } else {
        throw "-Sign requires either -CertThumbprint or -CertPath/-CertPassword."
    }
    if ($LASTEXITCODE -ne 0) { throw "signtool failed with exit code $LASTEXITCODE" }
    Write-Host "Signed $msixPath"
} else {
    Write-Host "Built unsigned. Re-run with -Sign (and your own certificate) before distributing."
}
