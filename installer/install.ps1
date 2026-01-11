# =============================================================================
# Iris Network - Node Agent Installer for Windows
#
# One-line installation (PowerShell):
#   irm https://iris.network/install.ps1 | iex
#
# Or download and run:
#   Invoke-WebRequest -Uri https://iris.network/install.ps1 -OutFile install.ps1
#   .\install.ps1
# =============================================================================

param(
    [string]$AccountKey,
    [string]$LMStudioUrl = "http://localhost:1234/v1",
    [switch]$NoService,
    [switch]$Uninstall,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Configuration
$Version = "1.0.0"
$CoordinatorIP = "168.119.10.189"
$CoordinatorPort = "8000"
$CoordinatorUrl = "http://${CoordinatorIP}:${CoordinatorPort}"
$CoordinatorWs = "ws://${CoordinatorIP}:${CoordinatorPort}/nodes/connect"
$InstallDir = "$env:LOCALAPPDATA\Iris"
$BinName = "iris-node.exe"
$GitHubRepo = "iris-network/iris-node"
$DownloadBase = "https://github.com/$GitHubRepo/releases/download/v$Version"

# Colors via ANSI escape codes
$ESC = [char]27
$Red = "$ESC[91m"
$Green = "$ESC[92m"
$Yellow = "$ESC[93m"
$Blue = "$ESC[94m"
$Cyan = "$ESC[96m"
$Bold = "$ESC[1m"
$Reset = "$ESC[0m"

# =============================================================================
# Helper Functions
# =============================================================================

function Write-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "${Cyan}  `u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557} `u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557}    `u{2588}`u{2588}`u{2588}`u{2557}   `u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2557}    `u{2588}`u{2588}`u{2557} `u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557} `u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557} `u{2588}`u{2588}`u{2557}  `u{2588}`u{2588}`u{2557}${Reset}"
    Write-Host "${Cyan}  `u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2550}`u{2550}`u{255D}    `u{2588}`u{2588}`u{2588}`u{2588}`u{2557}  `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2550}`u{2550}`u{255D}`u{255A}`u{2550}`u{2550}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{255D}`u{2588}`u{2588}`u{2551}    `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2550}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2551} `u{2588}`u{2588}`u{2554}`u{255D}${Reset}"
    Write-Host "${Cyan}  `u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2554}`u{255D}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2554}`u{255D}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557}    `u{2588}`u{2588}`u{2554}`u{2588}`u{2588}`u{2557} `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557}     `u{2588}`u{2588}`u{2551}   `u{2588}`u{2588}`u{2551} `u{2588}`u{2557} `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2551}   `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2554}`u{255D}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2554}`u{255D} ${Reset}"
    Write-Host "${Cyan}  `u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2551}`u{255A}`u{2550}`u{2550}`u{2550}`u{2550}`u{2588}`u{2588}`u{2551}    `u{2588}`u{2588}`u{2551}`u{255A}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{255D}     `u{2588}`u{2588}`u{2551}   `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2551}   `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2588}`u{2588}`u{2557}`u{2588}`u{2588}`u{2554}`u{2550}`u{2550}`u{2588}`u{2588}`u{2557}${Reset}"
    Write-Host "${Cyan}  `u{2588}`u{2588}`u{2551}  `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2551}  `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2551}    `u{2588}`u{2588}`u{2551} `u{255A}`u{2588}`u{2588}`u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2557}   `u{2588}`u{2588}`u{2551}   `u{255A}`u{2588}`u{2588}`u{2588}`u{2554}`u{2588}`u{2588}`u{2588}`u{2554}`u{255D}`u{255A}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2588}`u{2554}`u{255D}`u{2588}`u{2588}`u{2551}  `u{2588}`u{2588}`u{2551}`u{2588}`u{2588}`u{2551}  `u{2588}`u{2588}`u{2557}${Reset}"
    Write-Host "${Cyan}  `u{255A}`u{2550}`u{255D}  `u{255A}`u{2550}`u{255D}`u{255A}`u{2550}`u{255D}`u{255A}`u{2550}`u{255D}  `u{255A}`u{2550}`u{255D}`u{255A}`u{2550}`u{255D}`u{255A}`u{2550}`u{2550}`u{2550}`u{2550}`u{2550}`u{2550}`u{255D}    `u{255A}`u{2550}`u{255D}  `u{255A}`u{2550}`u{2550}`u{2550}`u{255D}`u{255A}`u{2550}`u{2550}`u{2550}`u{2550}`u{2550}`u{2550}`u{255D}   `u{255A}`u{2550}`u{255D}    `u{255A}`u{2550}`u{2550}`u{255D}`u{255A}`u{2550}`u{2550}`u{255D}  `u{255A}`u{2550}`u{2550}`u{2550}`u{2550}`u{2550}`u{255D} `u{255A}`u{2550}`u{255D}  `u{255A}`u{2550}`u{255D}`u{255A}`u{2550}`u{255D}  `u{255A}`u{2550}`u{255D}${Reset}"
    Write-Host ""
    Write-Host "${Bold}  Distributed AI Inference Network - Node Installer v${Version}${Reset}"
    Write-Host ""
    Write-Host "  -------------------------------------------------------------------------"
    Write-Host ""
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "${Blue}>${Reset} ${Bold}$Message${Reset}"
}

function Write-Success {
    param([string]$Message)
    Write-Host "  ${Green}[OK]${Reset} $Message"
}

function Write-Warning {
    param([string]$Message)
    Write-Host "  ${Yellow}[!]${Reset} $Message"
}

function Write-Error {
    param([string]$Message)
    Write-Host "  ${Red}[X]${Reset} $Message"
}

function Write-Info {
    param([string]$Message)
    Write-Host "  ${Cyan}[i]${Reset} $Message"
}

function Show-Help {
    Write-Host "Iris Network - Node Agent Installer for Windows"
    Write-Host ""
    Write-Host "Usage: install.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -AccountKey <key>         Use existing account key (16 digits)"
    Write-Host "  -LMStudioUrl <url>        LM Studio URL (default: http://localhost:1234/v1)"
    Write-Host "  -NoService                Skip Windows Service installation"
    Write-Host "  -Uninstall                Completely uninstall (removes all data)"
    Write-Host "  -Help                     Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\install.ps1"
    Write-Host "  .\install.ps1 -AccountKey '7294 8156 3047 9821'"
    Write-Host "  .\install.ps1 -Uninstall"
    Write-Host ""
    exit 0
}

# =============================================================================
# Uninstall
# =============================================================================

function Uninstall-Node {
    Write-Banner
    Write-Step "Uninstalling Iris Node Agent..."

    Write-Host ""
    Write-Host "  ${Yellow}WARNING!${Reset}"
    Write-Host "  This action will remove:"
    Write-Host "    - The iris-node binary"
    Write-Host "    - All configuration"
    Write-Host "    - All data and logs"
    Write-Host "    - The Windows service/startup shortcut"
    Write-Host "    - The node will disappear from the network"
    Write-Host ""

    $Confirm = Read-Host "  Are you sure? Type 'DELETE' to confirm"

    if ($Confirm -ne "DELETE") {
        Write-Info "Uninstall cancelled"
        exit 0
    }

    Write-Host ""

    # Stop and remove Windows Service
    $ServiceName = "IrisNode"
    $Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

    if ($Service) {
        Write-Info "Stopping Windows service..."
        try {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            $NssmPath = Get-Command nssm -ErrorAction SilentlyContinue
            if ($NssmPath) {
                & nssm remove $ServiceName confirm 2>$null
            } else {
                sc.exe delete $ServiceName 2>$null
            }
            Write-Success "Windows service removed"
        }
        catch {
            Write-Warning "Could not remove service: $($_.Exception.Message)"
        }
    }

    # Remove startup shortcut
    $StartupFolder = [Environment]::GetFolderPath("Startup")
    $ShortcutPath = "$StartupFolder\IrisNode.lnk"
    if (Test-Path $ShortcutPath) {
        Write-Info "Removing startup shortcut..."
        Remove-Item -Path $ShortcutPath -Force
        Write-Success "Startup shortcut removed"
    }

    # Remove from PATH
    Write-Info "Cleaning PATH..."
    $BinPath = "$InstallDir\bin"
    $CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($CurrentPath -like "*$BinPath*") {
        $NewPath = ($CurrentPath -split ";" | Where-Object { $_ -ne $BinPath }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
        Write-Success "PATH cleaned"
    }

    # Remove TUI directory
    $TuiDir = "$InstallDir\tui"
    if (Test-Path $TuiDir) {
        Write-Info "Removing TUI directory..."
        Remove-Item -Path $TuiDir -Recurse -Force
        Write-Success "TUI directory removed"
    }

    # Remove installation directory
    if (Test-Path $InstallDir) {
        Write-Info "Removing installation directory..."
        Remove-Item -Path $InstallDir -Recurse -Force
        Write-Success "Directory $InstallDir removed"
    }
    else {
        Write-Warning "Directory $InstallDir not found"
    }

    Write-Host ""
    Write-Host "${Green}  +=====================================================================+${Reset}"
    Write-Host "${Green}  |                    Uninstall Complete                               |${Reset}"
    Write-Host "${Green}  +=====================================================================+${Reset}"
    Write-Host ""
    Write-Host "  ${Cyan}Your node has been removed from Iris Network.${Reset}"
    Write-Host "  Thank you for participating."
    Write-Host ""

    exit 0
}

# =============================================================================
# Platform Detection
# =============================================================================

function Get-Platform {
    Write-Step "Detecting platform..."

    $Arch = if ([Environment]::Is64BitOperatingSystem) { "amd64" } else { "386" }
    $script:Platform = "windows-$Arch"

    Write-Success "Platform: $script:Platform"
    return $script:Platform
}

# =============================================================================
# Connectivity Check
# =============================================================================

function Test-Coordinator {
    Write-Step "Checking coordinator connection..."

    try {
        $Response = Invoke-RestMethod -Uri "${CoordinatorUrl}/health" -TimeoutSec 5 -ErrorAction Stop

        if ($Response.status -eq "healthy") {
            $NodesConnected = $Response.nodes_connected
            Write-Success "Coordinator active ($NodesConnected nodes connected)"
            return $true
        }
    }
    catch {
        Write-Error "Cannot connect to coordinator at ${CoordinatorIP}:${CoordinatorPort}"
        Write-Info "Check your internet connection"
        exit 1
    }
}

# =============================================================================
# LM Studio Check
# =============================================================================

function Test-LMStudio {
    Write-Step "Checking LM Studio..."

    $script:DetectedLMStudioUrl = $LMStudioUrl

    try {
        $Response = Invoke-RestMethod -Uri "${LMStudioUrl}/models" -TimeoutSec 3 -ErrorAction Stop

        if ($Response.data) {
            $Model = $Response.data[0].id
            Write-Success "LM Studio active - Model: $Model"
            return $true
        }
    }
    catch {
        Write-Warning "LM Studio not detected at $LMStudioUrl"
        Write-Host ""
        Write-Host "  ${Yellow}LM Studio is required to run inferences.${Reset}"
        Write-Host "  ${Cyan}1.${Reset} Download LM Studio: https://lmstudio.ai"
        Write-Host "  ${Cyan}2.${Reset} Load a model"
        Write-Host "  ${Cyan}3.${Reset} Start the local server (port 1234)"
        Write-Host ""

        $Continue = Read-Host "  Continue without LM Studio? [y/N]"
        if ($Continue -notmatch "^[YySs]$") {
            Write-Info "Install LM Studio and run the installer again"
            exit 0
        }
        return $false
    }
}

# =============================================================================
# Node.js Check
# =============================================================================

function Test-NodeJS {
    Write-Step "Checking Node.js..."

    $script:NodeJSAvailable = $false

    # Check if node is in PATH
    $NodePath = Get-Command node -ErrorAction SilentlyContinue

    if ($NodePath) {
        try {
            $NodeVersion = & node --version 2>$null
            $MajorVersion = [int]($NodeVersion -replace 'v(\d+)\..*', '$1')

            if ($MajorVersion -ge 16) {
                Write-Success "Node.js $NodeVersion detected"
                $script:NodeJSAvailable = $true
                return $true
            }
            else {
                Write-Warning "Node.js $NodeVersion is too old (v16+ required)"
            }
        }
        catch {
            Write-Warning "Could not determine Node.js version"
        }
    }

    Write-Warning "Node.js not detected"
    Write-Host ""
    Write-Host "  ${Yellow}Node.js is required for the dashboard (TUI).${Reset}"
    Write-Host "  ${Cyan}Installation options:${Reset}"
    Write-Host ""
    Write-Host "  ${Bold}Option 1 - winget (recommended):${Reset}"
    Write-Host "    winget install OpenJS.NodeJS.LTS"
    Write-Host ""
    Write-Host "  ${Bold}Option 2 - Download from website:${Reset}"
    Write-Host "    https://nodejs.org/en/download/"
    Write-Host ""
    Write-Host "  ${Bold}Option 3 - Chocolatey:${Reset}"
    Write-Host "    choco install nodejs-lts"
    Write-Host ""

    $InstallNode = Read-Host "  Try to install Node.js automatically? [Y/n]"
    if ($InstallNode -notmatch "^[Nn]$") {
        Install-NodeJS
    }
    else {
        Write-Warning "TUI will not be available without Node.js"
        $script:NodeJSAvailable = $false
    }
}

function Install-NodeJS {
    Write-Info "Installing Node.js..."

    # Try winget first
    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($Winget) {
        Write-Info "Installing via winget..."
        try {
            & winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
            # Refresh PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

            $NodeCheck = Get-Command node -ErrorAction SilentlyContinue
            if ($NodeCheck) {
                Write-Success "Node.js installed via winget"
                $script:NodeJSAvailable = $true
                return
            }
        }
        catch {
            Write-Warning "winget installation failed"
        }
    }

    # Try chocolatey
    $Choco = Get-Command choco -ErrorAction SilentlyContinue
    if ($Choco) {
        Write-Info "Installing via Chocolatey..."
        try {
            & choco install nodejs-lts -y
            # Refresh PATH
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

            $NodeCheck = Get-Command node -ErrorAction SilentlyContinue
            if ($NodeCheck) {
                Write-Success "Node.js installed via Chocolatey"
                $script:NodeJSAvailable = $true
                return
            }
        }
        catch {
            Write-Warning "Chocolatey installation failed"
        }
    }

    Write-Error "Could not install Node.js automatically"
    Write-Info "Please install manually from https://nodejs.org"
    $script:NodeJSAvailable = $false
}

# =============================================================================
# Account Key Setup
# =============================================================================

function Get-AccountKey {
    Write-Step "Account Setup"
    Write-Host ""
    Write-Host "  ${Cyan}Do you have an Iris Account Key?${Reset}"
    Write-Host "  ${Bold}1)${Reset} Yes, I have an Account Key"
    Write-Host "  ${Bold}2)${Reset} No, I need to generate one"
    Write-Host ""

    $Choice = Read-Host "  Select [1/2]"

    switch ($Choice) {
        "1" { Request-AccountKey }
        "2" { Show-GenerateInstructions }
        default {
            Write-Error "Invalid option"
            Get-AccountKey
        }
    }
}

function Request-AccountKey {
    Write-Host ""
    $Key = Read-Host "  Enter your Account Key (16 digits)"

    # Normalize (remove spaces and dashes)
    $script:AccountKey = $Key -replace '[\s-]', ''

    # Validate format (must be exactly 16 digits)
    if ($script:AccountKey -notmatch '^\d{16}$') {
        Write-Error "Invalid format. Must be 16 digits."
        Request-AccountKey
        return
    }

    Test-AccountKey
}

function Test-AccountKey {
    Write-Info "Validating account key..."

    try {
        $Body = @{ account_key = $script:AccountKey } | ConvertTo-Json
        $Response = Invoke-RestMethod -Uri "${CoordinatorUrl}/accounts/verify" `
            -Method Post `
            -Body $Body `
            -ContentType "application/json" `
            -ErrorAction Stop

        $Prefix = $Response.account_key_prefix
        $NodeCount = $Response.node_count
        Write-Success "Account verified (${Prefix} ****)"
        Write-Info "Existing nodes: $NodeCount"
    }
    catch {
        $ErrorDetail = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        $ErrorMsg = if ($ErrorDetail.detail) { $ErrorDetail.detail } else { "Invalid or inactive account key" }
        Write-Error "Account key error: $ErrorMsg"
        Write-Host ""

        $Retry = Read-Host "  Try again? [Y/n]"
        if ($Retry -notmatch "^[Nn]$") {
            Request-AccountKey
        }
        else {
            exit 1
        }
    }
}

function Show-GenerateInstructions {
    Write-Host ""
    Write-Host "  ${Yellow}===============================================================${Reset}"
    Write-Host "  ${Yellow}              Generate an Account Key First${Reset}"
    Write-Host "  ${Yellow}===============================================================${Reset}"
    Write-Host ""
    Write-Host "  You need an Account Key to run a node. Generate one with:"
    Write-Host ""
    Write-Host "  ${Bold}Option A - Using PowerShell:${Reset}"
    Write-Host "    Invoke-RestMethod -Uri '${CoordinatorUrl}/accounts/generate' -Method Post"
    Write-Host ""
    Write-Host "  ${Bold}Option B - Using the CLI:${Reset}"
    Write-Host "    pip install iris-network"
    Write-Host "    iris account generate"
    Write-Host ""
    Write-Host "  ${Red}IMPORTANT: Save your Account Key! It will only be shown once.${Reset}"
    Write-Host ""

    $Action = Read-Host "  Press Enter after you have your key, or 'q' to quit"
    if ($Action -eq 'q') {
        exit 0
    }

    Request-AccountKey
}

# =============================================================================
# Binary Download
# =============================================================================

function Get-Binary {
    Write-Step "Downloading Iris Node Agent..."

    $DownloadUrl = "${DownloadBase}/iris-node-${script:Platform}.exe"

    # Create directories
    New-Item -ItemType Directory -Force -Path "$InstallDir\bin" | Out-Null
    New-Item -ItemType Directory -Force -Path "$InstallDir\data" | Out-Null
    New-Item -ItemType Directory -Force -Path "$InstallDir\logs" | Out-Null

    Write-Info "URL: $DownloadUrl"

    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile "$InstallDir\bin\$BinName" -UseBasicParsing -ErrorAction Stop
        Write-Success "Binary installed at $InstallDir\bin\$BinName"
        $script:PythonMode = $false
    }
    catch {
        Write-Warning "Could not download pre-compiled binary"
        Write-Info "Using Python installation..."
        $script:PythonMode = $true
    }
}

# =============================================================================
# Node.js TUI Installation
# =============================================================================

function Install-NodeJSTUI {
    Write-Step "Installing dashboard (TUI)..."

    if (-not $script:NodeJSAvailable) {
        Write-Warning "Node.js not available, skipping TUI installation"
        return
    }

    $TuiDir = "$InstallDir\tui"
    New-Item -ItemType Directory -Force -Path $TuiDir | Out-Null

    # Check if source exists locally (for development)
    $TuiSource = "$env:USERPROFILE\Documents\clubai\client\tui-node"

    if (Test-Path $TuiSource) {
        Write-Info "Copying TUI from local source..."
        Copy-Item -Path "$TuiSource\src" -Destination $TuiDir -Recurse -Force
        Copy-Item -Path "$TuiSource\package.json" -Destination $TuiDir -Force
    }
    else {
        Write-Info "Downloading TUI from server..."
        $TuiUrl = "${CoordinatorUrl}/downloads/tui-node.zip"
        $TuiZip = "$env:TEMP\tui-node.zip"

        try {
            Invoke-WebRequest -Uri $TuiUrl -OutFile $TuiZip -UseBasicParsing -ErrorAction Stop
            Expand-Archive -Path $TuiZip -DestinationPath $TuiDir -Force
            Remove-Item -Path $TuiZip -Force
        }
        catch {
            Write-Warning "Could not download TUI"
            Write-Info "Clone the repository: git clone https://github.com/iris-network/client"
            return
        }
    }

    # Install npm dependencies
    Write-Info "Installing Node.js dependencies..."
    Push-Location $TuiDir

    try {
        & npm install --quiet 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Error installing npm dependencies"
            Pop-Location
            return
        }
        Write-Success "TUI dependencies installed"
    }
    catch {
        Write-Warning "Error running npm install: $($_.Exception.Message)"
        Pop-Location
        return
    }

    Pop-Location

    # Create iris.bat wrapper script
    $IrisBatContent = @"
@echo off
setlocal

set IRIS_DIR=%LOCALAPPDATA%\Iris
set TUI_DIR=%IRIS_DIR%\tui

rem Check for TUI mode (no args or 'tui' arg)
if "%~1"=="" goto :tui
if /i "%~1"=="tui" goto :tui
goto :cli

:tui
rem Launch Node.js TUI
if exist "%TUI_DIR%\src\index.js" (
    where node >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        node "%TUI_DIR%\src\index.js"
        exit /b
    )
)
echo Error: TUI not installed or Node.js not available
echo Run the installer again to set up the TUI
exit /b 1

:cli
rem Pass to Python CLI
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PROJECT_ROOT=%USERPROFILE%\Documents\clubai
    if exist "%PROJECT_ROOT%" (
        set PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%
    )
    python -m client.cli %*
    exit /b
)
echo Error: Python not found
exit /b 1
"@

    $IrisBatContent | Out-File -FilePath "$InstallDir\bin\iris.bat" -Encoding ASCII
    Write-Success "iris.bat (TUI/CLI) installed at $InstallDir\bin\iris.bat"

    # Also create a PowerShell wrapper for better terminal support
    $IrisPs1Content = @"
# Iris Network - Dashboard & CLI Launcher

`$IrisDir = "`$env:LOCALAPPDATA\Iris"
`$TuiDir = "`$IrisDir\tui"

# Check for TUI mode (no args or 'tui' arg)
if (`$args.Count -eq 0 -or `$args[0] -eq "tui") {
    # Launch Node.js TUI
    if ((Test-Path "`$TuiDir\src\index.js") -and (Get-Command node -ErrorAction SilentlyContinue)) {
        & node "`$TuiDir\src\index.js"
        exit
    }
    else {
        Write-Host "Error: TUI not installed or Node.js not available"
        Write-Host "Run the installer again to set up the TUI"
        exit 1
    }
}
else {
    # Pass to Python CLI
    `$PythonPath = Get-Command python -ErrorAction SilentlyContinue
    if (`$PythonPath) {
        `$ProjectRoot = "`$env:USERPROFILE\Documents\clubai"
        if (Test-Path `$ProjectRoot) {
            `$env:PYTHONPATH = "`$ProjectRoot;`$env:PYTHONPATH"
        }
        & python -m client.cli `$args
    }
    else {
        Write-Host "Error: Python not found"
        exit 1
    }
}
"@

    $IrisPs1Content | Out-File -FilePath "$InstallDir\bin\iris.ps1" -Encoding UTF8
    Write-Success "iris.ps1 (TUI/CLI) installed at $InstallDir\bin\iris.ps1"
}

# =============================================================================
# Configuration
# =============================================================================

function Set-NodeConfiguration {
    Write-Step "Configuring node..."

    # Generate node ID
    $script:NodeId = "node-$($env:COMPUTERNAME.ToLower())-$(Get-Date -Format 'MMddHHmm')"

    # Use detected or provided LM Studio URL
    $script:LMStudioUrlFinal = $script:DetectedLMStudioUrl

    # Format account key with spaces for readability
    $AccountKeyFormatted = $script:AccountKey -replace '(.{4})(.{4})(.{4})(.{4})', '$1 $2 $3 $4'

    # Create config file
    $ConfigContent = @"
# Iris Network - Node Configuration
# Generated: $(Get-Date -Format "yyyy-MM-ddTHH:mm:ss")

node_id: "$script:NodeId"
coordinator_url: "$CoordinatorWs"
lmstudio_url: "$script:LMStudioUrlFinal"
account_key: "$AccountKeyFormatted"
data_dir: "$InstallDir\data"
log_dir: "$InstallDir\logs"
"@

    $ConfigContent | Out-File -FilePath "$InstallDir\config.yaml" -Encoding UTF8

    Write-Success "Configuration saved to $InstallDir\config.yaml"
    Write-Success "Node ID: $script:NodeId"
}

# =============================================================================
# PATH Setup
# =============================================================================

function Set-PathEnvironment {
    Write-Step "Configuring PATH..."

    $BinPath = "$InstallDir\bin"
    $CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")

    if ($CurrentPath -notlike "*$BinPath*") {
        try {
            $NewPath = "$BinPath;$CurrentPath"
            [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
            $env:Path = "$BinPath;$env:Path"
            Write-Success "PATH updated - iris-node is now available"
            $script:PathConfigured = $true
        }
        catch {
            Write-Warning "Could not update PATH automatically"
            Write-Info "Add manually: $BinPath"
            $script:PathConfigured = $false
        }
    }
    else {
        Write-Success "PATH already configured"
        $script:PathConfigured = $true
    }
}

# =============================================================================
# Service Installation
# =============================================================================

function Request-Autostart {
    Write-Host ""
    $script:EnableAutostart = Read-Host "  Start automatically with system? [Y/n]"
    if ([string]::IsNullOrEmpty($script:EnableAutostart)) {
        $script:EnableAutostart = "Y"
    }
    return $script:EnableAutostart -match "^[YySs]$"
}

function Install-WindowsService {
    Write-Step "Installing Windows Service..."

    $ServiceName = "IrisNode"
    $BinPath = "$InstallDir\bin\$BinName"
    $ConfigPath = "$InstallDir\config.yaml"

    # Check if NSSM is available
    $NssmPath = Get-Command nssm -ErrorAction SilentlyContinue

    if ($NssmPath) {
        Write-Info "Using NSSM for service installation..."

        try {
            & nssm install $ServiceName "$BinPath"
            & nssm set $ServiceName AppParameters "--config `"$ConfigPath`""
            & nssm set $ServiceName AppDirectory "$InstallDir"
            & nssm set $ServiceName Start SERVICE_AUTO_START
            & nssm set $ServiceName AppStdout "$InstallDir\logs\node.log"
            & nssm set $ServiceName AppStderr "$InstallDir\logs\node.log"
            & nssm set $ServiceName AppRotateFiles 1
            & nssm set $ServiceName AppRotateBytes 10485760
            # Set environment variables
            & nssm set $ServiceName AppEnvironmentExtra "IRIS_ACCOUNT_KEY=$($script:AccountKey)" "COORDINATOR_URL=$CoordinatorWs" "LMSTUDIO_URL=$($script:LMStudioUrlFinal)"
            & nssm start $ServiceName

            Write-Success "Service installed with NSSM and started"
        }
        catch {
            Write-Warning "Failed to install service with NSSM"
        }
    }
    else {
        Write-Info "NSSM not found. Creating startup shortcut instead..."

        # Create startup shortcut with environment variables via batch wrapper
        $WrapperBat = "$InstallDir\bin\start-node.bat"
        $WrapperContent = @"
@echo off
set IRIS_ACCOUNT_KEY=$($script:AccountKey)
set COORDINATOR_URL=$CoordinatorWs
set LMSTUDIO_URL=$($script:LMStudioUrlFinal)
"$BinPath" --config "$ConfigPath"
"@
        $WrapperContent | Out-File -FilePath $WrapperBat -Encoding ASCII

        $WshShell = New-Object -ComObject WScript.Shell
        $StartupFolder = [Environment]::GetFolderPath("Startup")
        $ShortcutPath = "$StartupFolder\IrisNode.lnk"

        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $WrapperBat
        $Shortcut.WorkingDirectory = $InstallDir
        $Shortcut.Description = "Iris Network Node Agent"
        $Shortcut.WindowStyle = 7  # Minimized
        $Shortcut.Save()

        Write-Success "Startup shortcut created"
        Write-Info "For better service management, consider installing NSSM:"
        Write-Info "  winget install nssm"
        Write-Info "  choco install nssm"
    }
}

# =============================================================================
# Completion
# =============================================================================

function Show-Completion {
    Write-Host ""
    Write-Host "${Green}  +=====================================================================+${Reset}"
    Write-Host "${Green}  |                    Installation Complete!                           |${Reset}"
    Write-Host "${Green}  +=====================================================================+${Reset}"
    Write-Host ""
    Write-Host "  ${Bold}Your node is configured:${Reset}"
    Write-Host "    Node ID:     ${Cyan}$script:NodeId${Reset}"
    Write-Host "    Directory:   ${Cyan}$InstallDir${Reset}"
    Write-Host "    Config:      ${Cyan}$InstallDir\config.yaml${Reset}"
    Write-Host ""
    Write-Host "  ${Bold}Available commands:${Reset}"
    Write-Host "    ${Cyan}iris${Reset}           Open interactive dashboard (TUI)"
    Write-Host "    ${Cyan}iris-node${Reset}      Start the node agent"
    Write-Host ""
    Write-Host "  ${Bold}Other CLI commands:${Reset}"
    Write-Host "    ${Cyan}iris stats${Reset}     View network statistics"
    Write-Host "    ${Cyan}iris nodes${Reset}     View active nodes"
    Write-Host "    ${Cyan}iris ask${Reset}       Send inference prompt"
    Write-Host "    ${Cyan}iris --help${Reset}    Show all commands"
    Write-Host ""

    if ($script:PythonMode) {
        Write-Host "  ${Bold}Manual node start:${Reset}"
        Write-Host "    ${Cyan}Start:${Reset}      python -m node_agent.standalone_main --config $InstallDir\config.yaml"
    }
    elseif ($script:PathConfigured) {
        Write-Host "  ${Bold}Manual node start:${Reset}"
        Write-Host "    ${Cyan}Start:${Reset}      iris-node --config $InstallDir\config.yaml"
    }
    else {
        Write-Host "  ${Bold}Manual node start:${Reset}"
        Write-Host "    ${Cyan}Start:${Reset}      $InstallDir\bin\$BinName --config $InstallDir\config.yaml"
    }

    Write-Host ""
    Write-Host "  ${Bold}Service management:${Reset}"
    Write-Host "    ${Cyan}View logs:${Reset}  Get-Content -Tail 50 -Wait $InstallDir\logs\node.log"
    Write-Host "    ${Cyan}Status:${Reset}     Get-Service IrisNode -ErrorAction SilentlyContinue"
    Write-Host ""
    Write-Host "  ${Green}Your node is now part of Iris Network!${Reset}"
    Write-Host ""
}

# =============================================================================
# Main
# =============================================================================

function Main {
    if ($Help) {
        Show-Help
    }

    if ($Uninstall) {
        Uninstall-Node
    }

    Write-Banner

    # Step 1: Platform detection
    Get-Platform

    # Step 2: Check coordinator
    Test-Coordinator

    # Step 3: Check Node.js (for TUI)
    Test-NodeJS

    # Step 4: Check LM Studio
    Test-LMStudio

    # Step 5: Account Key (if not provided via CLI)
    if ([string]::IsNullOrEmpty($AccountKey)) {
        Get-AccountKey
    }
    else {
        # Normalize provided key (remove spaces/dashes)
        $script:AccountKey = $AccountKey -replace '[\s-]', ''
        Write-Step "Using provided account key"
        $KeyPrefix = $script:AccountKey.Substring(0, 4)
        Write-Success "Account key: ${KeyPrefix} ****"
        Test-AccountKey
    }

    # Step 6: Download binary
    Get-Binary

    # Step 7: Setup PATH
    if (-not $script:PythonMode) {
        Set-PathEnvironment
    }

    # Step 8: Install Node.js TUI
    Install-NodeJSTUI

    # Step 9: Configure
    Set-NodeConfiguration

    # Step 10: Service installation
    if (-not $NoService) {
        if (Request-Autostart) {
            Install-WindowsService
        }
    }

    # Done!
    Show-Completion
}

# Run main
Main
