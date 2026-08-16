# Installs the standalone repo-scanner binary (specs/020-cli-packaging).
# Usage: irm <release-url>/install.ps1 | iex
#
# Downloads the Windows/x86_64 release asset from the latest GitHub Release
# of yassinelalaoui/repo-scanner, installs it to
# %LOCALAPPDATA%\repo-scanner\repo-scanner.exe, and adds that directory to
# the user PATH if it isn't already there. Re-running this script upgrades
# an existing install in place (research.md sections 5-6;
# contracts/packaging-interface.md).

$ErrorActionPreference = "Stop"

$Repo = "yassinelalaoui/repo-scanner"
$InstallDir = Join-Path $env:LOCALAPPDATA "repo-scanner"
$BinaryPath = Join-Path $InstallDir "repo-scanner.exe"

function Fail($Message) {
    Write-Error "Error: $Message"
    exit 1
}

$arch = $env:PROCESSOR_ARCHITECTURE
if ($arch -ne "AMD64") {
    Fail "Unsupported architecture: $arch. repo-scanner currently only ships x86_64 (AMD64) binaries - see specs/020-cli-packaging/research.md section 9."
}

$apiUrl = "https://api.github.com/repos/$Repo/releases/latest"
try {
    $release = Invoke-RestMethod -Uri $apiUrl -ErrorAction Stop
} catch {
    $statusCode = $null
    if ($_.Exception.Response) {
        try { $statusCode = [int]$_.Exception.Response.StatusCode } catch {}
    }
    if ($statusCode -eq 404) {
        Fail "No release of $Repo has been published yet. See packaging/README.md for the release process, or check https://github.com/$Repo/releases."
    } else {
        Fail "Could not reach GitHub to resolve the latest release. Check your network connection and try again."
    }
}

$asset = $release.assets | Where-Object { $_.name -match "^repo-scanner-.*-windows-x86_64\.exe$" } | Select-Object -First 1
if (-not $asset) {
    Fail "No release asset found for windows-x86_64. This build of repo-scanner does not (yet) support this platform - see specs/020-cli-packaging/research.md section 9."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$tmpFile = Join-Path $env:TEMP "repo-scanner-download-$([guid]::NewGuid()).exe"
try {
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tmpFile -ErrorAction Stop
} catch {
    Fail "Failed to download $($asset.browser_download_url). Check your network connection and try again."
}

Move-Item -Force $tmpFile $BinaryPath

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (";$userPath;" -like "*;$InstallDir;*")) {
    $newPath = if ([string]::IsNullOrEmpty($userPath)) { $InstallDir } else { "$userPath;$InstallDir" }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$env:Path;$InstallDir"
    Write-Host "Added $InstallDir to your user PATH. Open a new terminal for it to take effect everywhere."
}

$installedVersion = & $BinaryPath --version
Write-Host "repo-scanner $installedVersion installed to $BinaryPath"
Write-Host "Verify with: repo-scanner --version"
