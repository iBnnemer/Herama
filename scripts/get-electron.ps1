param([string]$Dir)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ver = (Get-Content (Join-Path $Dir "package.json") -Raw | ConvertFrom-Json).version
$arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" }
$name = "electron-v$ver-win32-$arch.zip"
$url = "https://github.com/electron/electron/releases/download/v$ver/$name"
$zip = Join-Path $env:TEMP $name
Write-Host "      Downloading $url"
$ProgressPreference = "SilentlyContinue"
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
$dist = Join-Path $Dir "dist"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
Write-Host "      Extracting..."
Expand-Archive -Path $zip -DestinationPath $dist -Force
[IO.File]::WriteAllText((Join-Path $Dir "path.txt"), "electron.exe")
Remove-Item $zip -Force
Write-Host "      Electron $ver ready."
