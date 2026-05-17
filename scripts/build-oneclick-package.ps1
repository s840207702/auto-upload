[CmdletBinding()]
param(
    [string]$PackageName = "auto-upload-oneclick",
    [string]$PythonVersion = "3.12.3",
    [switch]$SkipFrontendBuild,
    [switch]$SkipRuntimeInstall
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-ChildPath {
    param(
        [string]$Child,
        [string]$Parent
    )
    $childFull = [System.IO.Path]::GetFullPath($Child)
    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $childFull.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside expected folder: $childFull"
    }
}

function Copy-CleanDirectory {
    param(
        [string]$Source,
        [string]$Destination
    )

    $sourceFull = (Resolve-Path -LiteralPath $Source).Path
    $prefix = $sourceFull.TrimEnd('\') + '\'
    $excludeDirs = @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'node_modules', '.vite')
    $excludeFiles = @('*.pyc', 'account.json', '*cookie*.json', '*token*.json', '*.log')

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $sourceFull -Recurse -Force -File | ForEach-Object {
        $relative = $_.FullName.Substring($prefix.Length)
        $segments = $relative -split '[\\/]'
        foreach ($segment in $segments) {
            if ($excludeDirs -contains $segment) {
                return
            }
        }
        foreach ($pattern in $excludeFiles) {
            if ($_.Name -like $pattern) {
                return
            }
        }

        $target = Join-Path $Destination $relative
        $targetParent = Split-Path -Parent $target
        New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

function Install-PortablePython {
    param(
        [string]$RuntimePythonDir,
        [string]$CacheDir,
        [string]$Version
    )

    New-Item -ItemType Directory -Force -Path $RuntimePythonDir | Out-Null
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

    $pythonZip = Join-Path $CacheDir "python-$Version-embed-amd64.zip"
    $pythonUrl = "https://www.python.org/ftp/python/$Version/python-$Version-embed-amd64.zip"

    if (-not (Test-Path -LiteralPath $pythonZip)) {
        Write-Step "Downloading portable Python $Version"
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip
    }

    Write-Step "Extracting portable Python"
    Expand-Archive -LiteralPath $pythonZip -DestinationPath $RuntimePythonDir -Force

    $pthFile = Get-ChildItem -LiteralPath $RuntimePythonDir -Filter "python*._pth" | Select-Object -First 1
    if (-not $pthFile) {
        throw "Cannot find python ._pth file in $RuntimePythonDir"
    }

    $pthContent = Get-Content -LiteralPath $pthFile.FullName
    $pthContent = $pthContent | ForEach-Object {
        if ($_ -eq "#import site") { "import site" } else { $_ }
    }
    foreach ($extraPath in @("..\..", "..\..\uploader", "..\..\myUtils", "..\..\utils")) {
        if ($pthContent -notcontains $extraPath) {
            $pthContent = @($extraPath) + $pthContent
        }
    }
    if ($pthContent -notcontains "import site") {
        $pthContent += "import site"
    }
    Set-Content -LiteralPath $pthFile.FullName -Value $pthContent -Encoding ASCII

    $pythonExe = Join-Path $RuntimePythonDir "python.exe"
    $getPip = Join-Path $CacheDir "get-pip.py"
    if (-not (Test-Path -LiteralPath $getPip)) {
        Write-Step "Downloading pip bootstrap"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
    }

    Write-Step "Installing pip into portable Python"
    & $pythonExe $getPip --no-warn-script-location 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "pip bootstrap failed"
    }

    return $pythonExe
}

function Write-PortableLauncher {
    param([string]$PackageDir)

    $launcher = @'
@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_PORT=5409"
set "PY=%CD%\runtime\python\python.exe"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=%CD%;%CD%\uploader;%CD%\myUtils;%CD%\utils"
set "PLAYWRIGHT_BROWSERS_PATH=%CD%\runtime\playwright-browsers"
set "PATH=%CD%\runtime\python\Scripts;%CD%\runtime\ffmpeg\bin;%PATH%"

echo.
echo ========================================
echo   Social Auto Upload - Portable Package
echo ========================================
echo.

if not exist "%PY%" (
  echo [ERROR] Missing runtime\python\python.exe
  echo Please extract the complete package folder before starting.
  pause
  exit /b 1
)

if not exist "videoFile" mkdir "videoFile"
if not exist "cookiesFile" mkdir "cookiesFile"
if not exist "db" mkdir "db"
if not exist "logs" mkdir "logs"
if not exist "avatars" mkdir "avatars"

echo [1/4] Checking runtime...
"%PY%" -c "import flask, flask_cors, playwright, xhs, biliup, loguru, qrcode, requests" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Bundled Python dependencies are incomplete.
  pause
  exit /b 1
)

echo [2/4] Cleaning old local service...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%APP_PORT%') do (
  taskkill /PID %%a /F >nul 2>nul
)

echo [3/4] Scheduling browser open...
start "" /b cmd /c "timeout /t 5 /nobreak >nul && start "" http://127.0.0.1:%APP_PORT%/"

echo.
echo App URL: http://127.0.0.1:%APP_PORT%/
echo Keep this window open while using the app.
echo.
echo [4/4] Starting local service...
"%PY%" main.py
echo.
echo Local service has stopped.
pause
endlocal
'@

    Set-Content -LiteralPath (Join-Path $PackageDir "start-oneclick.bat") -Value $launcher -Encoding ASCII
}

function Write-UserReadme {
    param([string]$PackageDir)

    $readme = @(
        "Social Auto Upload - Portable Package",
        "",
        "How to use:",
        "1. Extract the whole folder.",
        "2. Double-click start-oneclick.bat.",
        "3. When the browser opens, log in to each platform in Account Management.",
        "4. Go to Publish Center, choose media and platforms, then publish.",
        "",
        "Notes:",
        "- Python, Node, npm and Playwright are already bundled.",
        "- Keep the package path short, for example Desktop or D:\auto-upload-oneclick.",
        "- Login states, media, logs and database files stay in cookiesFile, videoFile, logs, db and avatars.",
        "- Before sharing a package, make sure those runtime data folders are empty.",
        "",
        "Troubleshooting:",
        "- If the page cannot open, close the launcher window and run start-oneclick.bat again.",
        "- If a platform asks for QR login again, the platform login state has expired.",
        "- If antivirus blocks it, allow the bundled local Python runtime. The app only starts a 127.0.0.1 local service."
    )

    Set-Content -LiteralPath (Join-Path $PackageDir "README-FIRST.txt") -Value $readme -Encoding ASCII

    $zhReadme = Join-Path $repoRoot "packaging\README-zh-CN.txt"
    if (Test-Path -LiteralPath $zhReadme) {
        Copy-Item -LiteralPath $zhReadme -Destination (Join-Path $PackageDir "README-zh-CN.txt") -Force
    }

    $newUserGuide = Join-Path $repoRoot "packaging\new-user-guide.html"
    if (Test-Path -LiteralPath $newUserGuide) {
        Copy-Item -LiteralPath $newUserGuide -Destination (Join-Path $PackageDir "new-user-guide.html") -Force
    }
}

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$releaseRoot = Join-Path $repoRoot "release"
$cacheDir = Join-Path $releaseRoot ".cache"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$packageDir = Join-Path $releaseRoot "$PackageName-$stamp"
$zipPath = "$packageDir.zip"

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
Assert-ChildPath -Child $packageDir -Parent $releaseRoot
Assert-ChildPath -Child $zipPath -Parent $releaseRoot

if (Test-Path -LiteralPath $packageDir) {
    Remove-Item -LiteralPath $packageDir -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
New-Item -ItemType Directory -Force -Path $packageDir | Out-Null

if (-not $SkipFrontendBuild) {
    Write-Step "Building frontend"
    Push-Location (Join-Path $repoRoot "frontend")
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "frontend build failed"
        }
    }
    finally {
        Pop-Location
    }
}

$frontendDist = Join-Path $repoRoot "frontend\dist"
if (-not (Test-Path -LiteralPath $frontendDist)) {
    throw "frontend/dist does not exist. Run without -SkipFrontendBuild first."
}

Write-Step "Copying application files"
$files = @(
    "main.py",
    "conf.example.py",
    "requirements-oneclick.txt",
    "README.md",
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "bg1.png"
)
foreach ($file in $files) {
    $src = Join-Path $repoRoot $file
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $packageDir $file) -Force
    }
}
Copy-Item -LiteralPath (Join-Path $repoRoot "conf.example.py") -Destination (Join-Path $packageDir "conf.py") -Force

foreach ($dir in @("myUtils", "uploader", "utils", "docs")) {
    Copy-CleanDirectory -Source (Join-Path $repoRoot $dir) -Destination (Join-Path $packageDir $dir)
}
Copy-CleanDirectory -Source $frontendDist -Destination (Join-Path $packageDir "frontend\dist")

foreach ($runtimeDir in @("cookiesFile", "videoFile", "db", "logs", "avatars")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageDir $runtimeDir) | Out-Null
}

Write-PortableLauncher -PackageDir $packageDir
Write-UserReadme -PackageDir $packageDir

if (-not $SkipRuntimeInstall) {
    $runtimePythonDir = Join-Path $packageDir "runtime\python"
    $pythonExe = Install-PortablePython -RuntimePythonDir $runtimePythonDir -CacheDir $cacheDir -Version $PythonVersion

    Write-Step "Installing Python dependencies"
    & $pythonExe -m pip install --no-warn-script-location -r (Join-Path $packageDir "requirements-oneclick.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "dependency install failed"
    }

    Write-Step "Installing bundled Playwright Chromium"
    $playwrightBrowsers = Join-Path $packageDir "runtime\playwright-browsers"
    New-Item -ItemType Directory -Force -Path $playwrightBrowsers | Out-Null
    $oldBrowsersPath = $env:PLAYWRIGHT_BROWSERS_PATH
    $env:PLAYWRIGHT_BROWSERS_PATH = $playwrightBrowsers
    try {
        & $pythonExe -m playwright install chromium
        if ($LASTEXITCODE -ne 0) {
            throw "playwright chromium install failed"
        }
    }
    finally {
        $env:PLAYWRIGHT_BROWSERS_PATH = $oldBrowsersPath
    }
}

Write-Step "Checking package does not contain sensitive runtime data"
$blocked = @(
    "cookiesFile\*.json",
    "db\*.db",
    "logs\*.log",
    "avatars\*",
    "videoFile\*",
    ".git\*",
    ".venv\*",
    "frontend\node_modules\*"
)
foreach ($pattern in $blocked) {
    $matches = Get-ChildItem -LiteralPath $packageDir -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName.Substring($packageDir.Length + 1) -like $pattern }
    if ($matches) {
        throw "Package contains blocked runtime data matching $pattern"
    }
}

Write-Step "Creating zip archive"
Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Package folder: $packageDir" -ForegroundColor Green
Write-Host "Package zip:    $zipPath" -ForegroundColor Green
