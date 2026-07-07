param(
    [string]$DbHost = "127.0.0.1",
    [int]$DbPort = 5432,
    [string]$DbUser = "postgres",
    [string]$DbName = "华世王镞_v2",
    [switch]$SkipFrontendBuild,
    [switch]$SkipStart,
    [switch]$SkipSystemInstall,
    [switch]$SkipSeed,
    [switch]$SkipModules
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"

function Write-Step([string]$Message) {
    Write-Host "[deploy:windows] $Message"
}

function Fail([string]$Message) {
    throw "[deploy:windows] ERROR: $Message"
}

function Command-Exists([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ask-YesNo([string]$Prompt) {
    $answer = Read-Host "$Prompt [y/N]"
    return $answer -eq "y" -or $answer -eq "Y"
}

function Prompt-Proxy {
    Write-Step "Network acceleration is recommended. Agent-assisted installs often need a proxy for git, pip, npm and winget/choco."
    Write-Step "Example: http://127.0.0.1:7890 or socks5://127.0.0.1:7890"
    $proxy = Read-Host "Proxy URL for this deployment process (empty to skip)"
    if ([string]::IsNullOrWhiteSpace($proxy)) {
        return
    }

    $env:HTTP_PROXY = $proxy
    $env:HTTPS_PROXY = $proxy
    $env:ALL_PROXY = $proxy
    $env:http_proxy = $proxy
    $env:https_proxy = $proxy
    $env:all_proxy = $proxy
    $env:NO_PROXY = "127.0.0.1,localhost"
    $env:no_proxy = $env:NO_PROXY
    Write-Step "Proxy enabled for this process."

    if (Ask-YesNo "Also write proxy to global git and npm config") {
        if (Command-Exists "git") {
            git config --global http.proxy $proxy | Out-Null
            git config --global https.proxy $proxy | Out-Null
        }
        if (Command-Exists "npm") {
            npm config set proxy $proxy | Out-Null
            npm config set https-proxy $proxy | Out-Null
        }
        Write-Step "Global git/npm proxy updated."
    }
}

function Get-PackageManager {
    if (Command-Exists "winget") { return "winget" }
    if (Command-Exists "choco") { return "choco" }
    return ""
}

function Install-PackageIfMissing([string]$Binary, [string]$WingetId, [string]$ChocoName) {
    if (Command-Exists $Binary) {
        return
    }
    if ($SkipSystemInstall) {
        Fail "Missing dependency: $Binary. Install it and rerun."
    }

    $manager = Get-PackageManager
    if ($manager -eq "winget") {
        Write-Step "Installing $WingetId via winget..."
        winget install --id $WingetId --accept-package-agreements --accept-source-agreements
        return
    }
    if ($manager -eq "choco") {
        Write-Step "Installing $ChocoName via Chocolatey..."
        choco install $ChocoName -y
        return
    }
    Fail "No supported package manager found. Install winget or Chocolatey, then rerun."
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Find-Python314 {
    $cmd = Get-Command "python3.14" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $py = Get-Command "py" -ErrorAction SilentlyContinue
    if ($py) {
        try {
            py -3.14 --version | Out-Null
            return "py -3.14"
        } catch {
            return ""
        }
    }
    return ""
}

function Ensure-SystemDependencies {
    Install-PackageIfMissing "git" "Git.Git" "git"
    Refresh-ProcessPath
    Install-PackageIfMissing "node" "OpenJS.NodeJS.LTS" "nodejs-lts"
    Refresh-ProcessPath

    if ([string]::IsNullOrWhiteSpace((Find-Python314))) {
        if ($SkipSystemInstall) { Fail "Missing dependency: Python 3.14" }
        $manager = Get-PackageManager
        if ($manager -eq "winget") {
            Write-Step "Installing Python 3.14 via winget..."
            winget install --id Python.Python.3.14 --accept-package-agreements --accept-source-agreements
        } elseif ($manager -eq "choco") {
            Write-Step "Installing Python 3.14 via Chocolatey..."
            choco install python314 -y
        } else {
            Fail "No supported package manager found for Python 3.14."
        }
        Refresh-ProcessPath
    }

    if (-not (Command-Exists "psql")) {
        if ($SkipSystemInstall) { Fail "Missing dependency: psql" }
        $manager = Get-PackageManager
        if ($manager -eq "winget") {
            Write-Step "Installing PostgreSQL via winget..."
            winget install --id PostgreSQL.PostgreSQL.17 --accept-package-agreements --accept-source-agreements
        } elseif ($manager -eq "choco") {
            Write-Step "Installing PostgreSQL via Chocolatey..."
            choco install postgresql17 -y
        } else {
            Fail "No supported package manager found for PostgreSQL."
        }
        Refresh-ProcessPath
    }
}

function Test-PostgresReady {
    if (-not (Command-Exists "pg_isready")) {
        return $false
    }
    pg_isready -h $DbHost -p $DbPort | Out-Null
    return $LASTEXITCODE -eq 0
}

function Start-Postgres {
    if (Test-PostgresReady) {
        Write-Step "PostgreSQL is already accepting connections on ${DbHost}:${DbPort}."
        return
    }

    $services = Get-Service -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match "postgres" -or $_.DisplayName -match "PostgreSQL"
    }
    foreach ($service in $services) {
        if ($service.Status -ne "Running") {
            Write-Step "Trying to start PostgreSQL service: $($service.Name)"
            try { Start-Service $service.Name } catch { Write-Step "Service start failed: $($service.Name)" }
        }
    }
    Start-Sleep -Seconds 5
    if (Test-PostgresReady) {
        Write-Step "PostgreSQL is ready on ${DbHost}:${DbPort}."
        return
    }

    $pgCtlCandidates = @(
        "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe",
        "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe"
    )
    foreach ($pgCtl in $pgCtlCandidates) {
        $dataDir = Split-Path -Parent (Split-Path -Parent $pgCtl)
        $dataDir = Join-Path $dataDir "data"
        if ((Test-Path $pgCtl) -and (Test-Path $dataDir)) {
            Write-Step "Trying pg_ctl start: $pgCtl"
            & $pgCtl -D $dataDir start | Out-Null
            Start-Sleep -Seconds 5
            if (Test-PostgresReady) { return }
        }
    }

    Fail "PostgreSQL is not reachable on ${DbHost}:${DbPort}. Start PostgreSQL manually and rerun."
}

function Read-SecretText([string]$Prompt) {
    $secure = Read-Host $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Invoke-Python314([string[]]$Arguments) {
    $python = Find-Python314
    if ([string]::IsNullOrWhiteSpace($python)) {
        Fail "Python 3.14 is not available after installation."
    }
    if ($python -eq "py -3.14") {
        & py -3.14 @Arguments
    } else {
        & $python @Arguments
    }
}

function Install-Backend {
    Write-Step "Preparing backend virtual environment..."
    Push-Location $BackendDir
    try {
        Invoke-Python314 @("-m", "venv", ".venv")
        $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
        & $venvPython -m pip install --upgrade pip
        & $venvPython -m pip install -r requirements.txt
    } finally {
        Pop-Location
    }
}

function Install-Frontend {
    Write-Step "Installing frontend dependencies..."
    Push-Location $FrontendDir
    try {
        npm install
        npm run scan:modules
        if (-not $SkipFrontendBuild) {
            npm run build
        } else {
            Write-Step "Frontend build skipped."
        }
    } finally {
        Pop-Location
    }
}

function Run-Initializer {
    $dbPassword = Read-SecretText "PostgreSQL password for user '$DbUser' (empty allowed)"
    $seedPassword = ""
    if (-not $SkipSeed) {
        $seedPassword = Read-SecretText "Default password for admin/editor/viewer seed users"
        if ([string]::IsNullOrWhiteSpace($seedPassword)) {
            Fail "Seed password cannot be empty unless -SkipSeed is used."
        }
    }

    $env:DB_HOST = $DbHost
    $env:DB_PORT = [string]$DbPort
    $env:DB_USER = $DbUser
    $env:DB_PASSWORD = $dbPassword
    $env:DB_NAME = $DbName
    $env:V2_SEED_DEFAULT_PASSWORD = $seedPassword

    $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
    $initArgs = @(
        (Join-Path $ScriptDir "deploy_common.py"),
        "--db-host", $DbHost,
        "--db-port", [string]$DbPort,
        "--db-user", $DbUser,
        "--db-name", $DbName
    )
    if ($SkipSeed) { $initArgs += "--skip-seed" }
    if ($SkipModules) { $initArgs += "--skip-modules" }
    & $venvPython @initArgs
}

function Start-Backend {
    if ($SkipStart) {
        Write-Step "Backend startup skipped."
        return
    }

    Write-Step "Starting backend on 127.0.0.1:33000..."
    $venvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
    $logDir = Join-Path $BackendDir "logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Set-Content -Path (Join-Path $logDir ".backend.port") -Value "33000" -Encoding ascii
    $uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "33000")
    Start-Process -FilePath $venvPython -ArgumentList $uvicornArgs -WorkingDirectory $BackendDir -WindowStyle Minimized | Out-Null
    Write-Step "Backend process launched. Health check: http://127.0.0.1:33000/api/health"
}

function Main {
    Write-Step "Project root: $ProjectRoot"
    Prompt-Proxy
    Ensure-SystemDependencies
    Refresh-ProcessPath
    Start-Postgres
    Install-Backend
    Run-Initializer
    Install-Frontend
    Start-Backend
    Write-Step "Deployment completed."
    Write-Step "Backend health: http://127.0.0.1:33000/api/health"
    Write-Step "Frontend dev server: cd frontend && npm run dev, then open http://127.0.0.1:5173"
}

Main
