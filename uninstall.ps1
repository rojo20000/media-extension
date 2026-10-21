#Requires -Version 5.1
<#
.SYNOPSIS
  Unregisters the Media Downloader helper from Chrome.

.DESCRIPTION
  Leaves Python, yt-dlp, ffmpeg, Deno and your downloaded files alone. Remove those
  with winget or Settings > Apps if you no longer want them.
#>
$ErrorActionPreference = "Stop"
$HostName = "com.media_extension.host"
$regKey = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$HostName"
if (Test-Path $regKey) { Remove-Item $regKey -Force }
foreach ($file in "config.json", "media_host.bat", "$HostName.json") {
  $path = Join-Path (Join-Path $PSScriptRoot "host") $file
  if (Test-Path $path) { Remove-Item $path -Force }
}
Write-Host "The helper is unregistered. You can now remove the extension from chrome://extensions."
