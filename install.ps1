#Requires -Version 5.1
<#
.SYNOPSIS
  One-time setup for the Media Downloader extension's helper on Windows.

.DESCRIPTION
  Installs whatever is missing (Python, yt-dlp, ffmpeg, Deno) with winget,
  records their locations for the helper, and registers the helper with Chrome.
  Safe to run again at any time, for example after moving this folder.

  Run it from this folder with:
    powershell -ExecutionPolicy Bypass -File install.ps1
#>
[CmdletBinding()]
param(
  # The ID Chrome shows for the unpacked extension. The manifest's "key" pins it,
  # so the default only needs changing if you replaced that key.
  [string]$ExtensionId = "fcpcapkmpgmfjiohfmgemjolajbhonjb"
)

$ErrorActionPreference = "Stop"
$HostName = "com.media_extension.host"
$HostDir = Join-Path $PSScriptRoot "host"
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Update-SessionPath {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User")
}

function Find-Exe([string]$Name) {
  $found = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -notlike "*\WindowsApps\*" } |  # skip Microsoft Store stubs
    Select-Object -First 1
  if ($found) { return $found.Source }
}

function Install-WithWinget([string]$Id, [string]$Label) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget isn't available. Install 'App Installer' from the Microsoft Store, then run this again."
  }
  Write-Host "Installing $Label with winget..."
  winget install -e --id $Id --accept-source-agreements --accept-package-agreements --silent
  Update-SessionPath
}

function Get-Tool([string]$Exe, [string]$WingetId, [string]$Label) {
  $path = Find-Exe $Exe
  if (-not $path) {
    Install-WithWinget $WingetId $Label
    $path = Find-Exe $Exe
  }
  if (-not $path) {
    throw "$Label was installed, but $Exe still can't be found. Open a new PowerShell window and run this again."
  }
  Write-Host ("  {0,-8} {1}" -f $Label, $path)
  return $path
}

function Find-Python {
  # Windows PowerShell turns a native program's stderr into a terminating error
  # under "Stop", so this probe runs with "Continue".
  $ErrorActionPreference = "Continue"
  $check = "import sys; assert sys.version_info >= (3, 9); print(sys.executable)"
  $launcher = Find-Exe "py"
  if ($launcher) {
    $out = & $launcher -3 -c $check 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { return "$out".Trim() }
  }
  $python = Find-Exe "python"
  if ($python) {
    $out = & $python -c $check 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { return "$out".Trim() }
  }
}

function Write-Utf8File([string]$Path, [string]$Text) {
  [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

Write-Host "Checking tools..."
Update-SessionPath
$python = Find-Python
if (-not $python) {
  Install-WithWinget "Python.Python.3.12" "Python"
  $python = Find-Python
}
if (-not $python) {
  throw "Python 3.9 or newer couldn't be found after installing. Open a new PowerShell window and run this again."
}
Write-Host ("  {0,-8} {1}" -f "Python", $python)
$ytdlp = Get-Tool "yt-dlp" "yt-dlp.yt-dlp" "yt-dlp"
$ffmpeg = Get-Tool "ffmpeg" "Gyan.FFmpeg" "ffmpeg"
try {
  $deno = Get-Tool "deno" "DenoLand.Deno" "Deno"
} catch {
  # Optional: without it yt-dlp still works, but may miss some YouTube formats.
  Write-Warning "Deno couldn't be set up ($($_.Exception.Message)). Some YouTube formats may be missing."
  $deno = $null
}

# Chrome starts the helper with the PATH it had when it was opened, which may be
# older than this install, so the helper gets absolute paths instead.
Write-Host "Configuring the helper..."
$config = [ordered]@{ python = $python; ytdlp = $ytdlp; ffmpeg = $ffmpeg; deno = $deno }
Write-Utf8File (Join-Path $HostDir "config.json") ($config | ConvertTo-Json)

# cmd.exe reads .bat files in the console's OEM code page.
$launcher = Join-Path $HostDir "media_host.bat"
$oem = [System.Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
[System.IO.File]::WriteAllText($launcher, "@echo off`r`n`"$python`" -u `"%~dp0media_host.py`" %*`r`n", $oem)

$manifestPath = Join-Path $HostDir "$HostName.json"
$manifest = [ordered]@{
  name = $HostName
  description = "Media Downloader helper (runs yt-dlp)"
  path = $launcher
  type = "stdio"
  allowed_origins = @("chrome-extension://$ExtensionId/")
}
Write-Utf8File $manifestPath ($manifest | ConvertTo-Json)

# reg.exe creates any missing parent keys.
reg.exe add "HKCU\Software\Google\Chrome\NativeMessagingHosts\$HostName" /ve /t REG_SZ /d "$manifestPath" /f | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Couldn't register the helper with Chrome (reg.exe exit code $LASTEXITCODE)." }

# Ask the helper's own code where files will go, which also proves Python can run it.
$ErrorActionPreference = "Continue"
$mediaDir = & $python -c "import sys; sys.path.insert(0, r'$HostDir'); from mdl.paths import media_dir; print(media_dir())" 2>&1
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) { throw "The helper couldn't start with ${python}: $mediaDir" }

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Downloads will be saved to: $mediaDir"
Write-Host "  Chrome extension ID:        $ExtensionId"
Write-Host "Reopen the extension's popup to use it. If Chrome was open during setup, that's all you need."
