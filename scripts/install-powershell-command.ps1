param(
    [string] $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string] $ProfilePath = $PROFILE.CurrentUserAllHosts,
    [string] $ShimDir = (Join-Path $env:LOCALAPPDATA "Programs\Voicesss\bin")
)

$ErrorActionPreference = "Stop"

$cliPath = Join-Path $ProjectRoot ".venv\Scripts\voicesss.exe"
$appPath = Join-Path $ProjectRoot ".venv\Scripts\voicesss-app.exe"

if (-not (Test-Path -LiteralPath $cliPath)) {
    throw "Nao encontrei $cliPath. Crie/instale a .venv antes: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e `".[all]`""
}

if (-not (Test-Path -LiteralPath $appPath)) {
    throw "Nao encontrei $appPath. Reinstale o projeto: .\.venv\Scripts\python.exe -m pip install -e `".[all]`""
}

function Write-CmdShim {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Directory,
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string] $Target
    )

    if (-not (Test-Path -LiteralPath $Directory)) {
        New-Item -ItemType Directory -Path $Directory | Out-Null
    }

    $cmdPath = Join-Path $Directory "$Name.cmd"
    $content = @"
@echo off
"$Target" %*
"@
    Set-Content -LiteralPath $cmdPath -Value $content -Encoding ASCII
}

function Add-DirectoryToUserPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Directory
    )

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($userPath)) {
        $parts = $userPath -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    }

    $alreadyInPath = $parts | Where-Object { $_.TrimEnd("\") -ieq $Directory.TrimEnd("\") }
    if (-not $alreadyInPath) {
        $newPath = if ($parts.Count -gt 0) {
            ($parts + $Directory) -join ";"
        } else {
            $Directory
        }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    }

    $currentParts = $env:Path -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $alreadyInCurrentPath = $currentParts | Where-Object { $_.TrimEnd("\") -ieq $Directory.TrimEnd("\") }
    if (-not $alreadyInCurrentPath) {
        $env:Path = "$Directory;$env:Path"
    }
}

function Get-CurrentPathShimDir {
    $preferred = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\Scripts"),
        (Join-Path $env:APPDATA "npm")
    )

    $currentParts = $env:Path -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($candidate in $preferred) {
        $isInCurrentPath = $currentParts | Where-Object { $_.TrimEnd("\") -ieq $candidate.TrimEnd("\") }
        if ($isInCurrentPath) {
            return $candidate
        }
    }

    return $null
}

$shimTargets = @($ShimDir)
$currentPathShimDir = Get-CurrentPathShimDir
if ($currentPathShimDir -and ($currentPathShimDir.TrimEnd("\") -ine $ShimDir.TrimEnd("\"))) {
    $shimTargets += $currentPathShimDir
}

foreach ($targetDir in $shimTargets) {
    Write-CmdShim -Directory $targetDir -Name "voicesss" -Target $cliPath
    Write-CmdShim -Directory $targetDir -Name "voicesss-app" -Target $appPath
}

Add-DirectoryToUserPath -Directory $ShimDir

$profileDir = Split-Path -Parent $ProfilePath
if (-not (Test-Path -LiteralPath $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir | Out-Null
}

if (-not (Test-Path -LiteralPath $ProfilePath)) {
    New-Item -ItemType File -Path $ProfilePath | Out-Null
}

$startMarker = "# >>> voicesss command >>>"
$endMarker = "# <<< voicesss command <<<"
$profileContent = Get-Content -LiteralPath $ProfilePath -Raw

$escapedProjectRoot = $ProjectRoot.Replace("'", "''")
$escapedCliPath = $cliPath.Replace("'", "''")
$escapedAppPath = $appPath.Replace("'", "''")

$block = @"
$startMarker
`$env:VOICESSS_PROJECT = '$escapedProjectRoot'
function voicesss {
    & '$escapedCliPath' @args
}
function voicesss-app {
    & '$escapedAppPath' @args
}
$endMarker
"@

$pattern = "(?s)\r?\n?$([regex]::Escape($startMarker)).*?$([regex]::Escape($endMarker))\r?\n?"
if ($profileContent -match [regex]::Escape($startMarker)) {
    $profileContent = [regex]::Replace($profileContent, $pattern, "`r`n$block`r`n")
} else {
    if ($profileContent.Trim().Length -gt 0) {
        $profileContent = $profileContent.TrimEnd() + "`r`n`r`n" + $block + "`r`n"
    } else {
        $profileContent = $block + "`r`n"
    }
}

Set-Content -LiteralPath $ProfilePath -Value $profileContent -Encoding UTF8
. $ProfilePath

Write-Host "Comandos instalados no perfil:" -ForegroundColor Green
Write-Host "  $ProfilePath"
Write-Host "Atalhos .cmd instalados em:"
foreach ($targetDir in $shimTargets) {
    Write-Host "  $targetDir"
}
Write-Host ""
Write-Host "Agora voce pode usar:"
Write-Host "  voicesss normalize `"eu estou cansado`""
Write-Host "  voicesss-app"
