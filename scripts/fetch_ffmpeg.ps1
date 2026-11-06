$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$downloadDir = Join-Path $projectRoot 'build\ffmpeg-download'
New-Item -ItemType Directory -Force $downloadDir | Out-Null
$archive = Join-Path $downloadDir 'ffmpeg.zip'
# Fixed tested release rather than a moving "latest" download.
$uri = 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
Invoke-WebRequest -Uri $uri -OutFile $archive
$expected = (Get-Content (Join-Path $projectRoot 'tools\ffmpeg.sha256') -Raw).Trim().Split(' ')[0]
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'Checksum FFmpeg non corrispondente. Non eseguire questo download.' }
Expand-Archive -LiteralPath $archive -DestinationPath $downloadDir -Force
$binDir = Join-Path $downloadDir 'ffmpeg-9.0.2-essentials_build\bin'
New-Item -ItemType Directory -Force (Join-Path $projectRoot 'tools') | Out-Null
Copy-Item -LiteralPath (Join-Path $binDir 'ffmpeg.exe') -Destination (Join-Path $projectRoot 'tools\ffmpeg.exe')
Copy-Item -LiteralPath (Join-Path $binDir 'ffprobe.exe') -Destination (Join-Path $projectRoot 'tools\ffprobe.exe')
