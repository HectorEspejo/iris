# =============================================================================
# ClubAI Node Agent Installer for Windows
#
# One-line installation (PowerShell):
#   irm https://clubai.network/install.ps1 | iex
#
# Or download and run:
#   Invoke-WebRequest -Uri https://clubai.network/install.ps1 -OutFile install.ps1
#   .\install.ps1
# =============================================================================

param(
    [string]$EnrollmentToken,
    [string]$NodeId,
    [string]$LMStudioUrl = "http://localhost:1234/v1",
    [switch]$NoService,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# Configuration
$Version = "1.0.0"
$CoordinatorDefault = "168.119.10.189"
$CoordinatorPort = "8000"
$InstallDir = "$env:LOCALAPPDATA\ClubAI"
$BinName = "clubai-node.exe"
$GitHubRepo = "clubai/clubai-node"
$DownloadBase = "https://github.com/$GitHubRepo/releases/download/v$Version"

# Helper functions
function Write-Banner {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "         ClubAI Node Agent Installer v$Version" -ForegroundColor Cyan
    Write-Host "       Distributed AI Inference Network" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARN] " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] " -ForegroundColor Cyan -NoNewline
    Write-Host $Message
}

function Show-Help {
    Write-Host "Usage: install.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -EnrollmentToken <token>  Pre-set enrollment token"
    Write-Host "  -NodeId <id>              Pre-set node ID"
    Write-Host "  -LMStudioUrl <url>        LM Studio URL (default: http://localhost:1234/v1)"
    Write-Host "  -NoService                Skip Windows Service installation"
    Write-Host "  -Help                     Show this help message"
    Write-Host ""
    exit 0
}

# Detect architecture
function Get-Platform {
    $Arch = if ([Environment]::Is64BitOperatingSystem) { "amd64" } else { "386" }
    return "windows-$Arch"
}

# Download binary
function Get-Binary {
    $Platform = Get-Platform
    $DownloadUrl = "$DownloadBase/clubai-node-$Platform.exe"

    Write-Info "Downloading ClubAI Node Agent..."
    Write-Info "URL: $DownloadUrl"

    # Create directories
    New-Item -ItemType Directory -Force -Path "$InstallDir\bin" | Out-Null
    New-Item -ItemType Directory -Force -Path "$InstallDir\data" | Out-Null
    New-Item -ItemType Directory -Force -Path "$InstallDir\logs" | Out-Null

    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile "$InstallDir\bin\$BinName" -UseBasicParsing
        Write-Success "Binary downloaded to $InstallDir\bin\$BinName"
    }
    catch {
        Write-Error "Failed to download binary"
        Write-Info "This may mean the release hasn't been published yet."
        Write-Info "For now, you can build from source:"
        Write-Info "  git clone https://github.com/$GitHubRepo.git"
        Write-Info "  cd clubai-node && pip install pyinstaller pyyaml"
        Write-Info "  cd node_agent && pyinstaller clubai-node.spec"
        exit 1
    }
}

# Validate token with coordinator
function Test-Token {
    param([string]$Token)

    Write-Info "Validating enrollment token..."

    try {
        $Body = @{ token = $Token } | ConvertTo-Json
        $Response = Invoke-RestMethod -Uri "http://${CoordinatorDefault}:${CoordinatorPort}/nodes/validate-token" `
            -Method Post `
            -Body $Body `
            -ContentType "application/json" `
            -ErrorAction Stop

        if ($Response.valid -eq $true) {
            Write-Success "Token is valid"
            return $true
        }
        else {
            Write-Error "Invalid token: $($Response.error)"
            return $false
        }
    }
    catch {
        Write-Error "Failed to validate token: $($_.Exception.Message)"
        return $false
    }
}

# Interactive configuration
function Get-Configuration {
    Write-Host ""
    Write-Host "=== Node Configuration ===" -ForegroundColor Green
    Write-Host ""

    # Enrollment token
    $script:EnrollToken = $EnrollmentToken
    while ([string]::IsNullOrEmpty($script:EnrollToken)) {
        $script:EnrollToken = Read-Host "Enter your enrollment token"
        if ([string]::IsNullOrEmpty($script:EnrollToken)) {
            Write-Error "Enrollment token is required"
            continue
        }

        if (-not (Test-Token -Token $script:EnrollToken)) {
            $retry = Read-Host "Try again? [Y/n]"
            if ($retry -match "^[Nn]$") {
                Write-Error "Cannot proceed without a valid token"
                exit 1
            }
            $script:EnrollToken = ""
        }
    }

    # LM Studio URL
    Write-Host ""
    $inputUrl = Read-Host "LM Studio URL [$LMStudioUrl]"
    if (-not [string]::IsNullOrEmpty($inputUrl)) {
        $script:LMStudioUrl = $inputUrl
    }
    else {
        $script:LMStudioUrl = $LMStudioUrl
    }

    # Node ID
    $DefaultNodeId = "node-$($env:COMPUTERNAME.ToLower())-$(Get-Date -Format 'MMddHHmm')"
    Write-Host ""
    $inputNodeId = Read-Host "Node ID [$DefaultNodeId]"
    if (-not [string]::IsNullOrEmpty($inputNodeId)) {
        $script:NodeIdValue = $inputNodeId
    }
    else {
        $script:NodeIdValue = $DefaultNodeId
    }

    # Autostart
    Write-Host ""
    $script:Autostart = Read-Host "Enable autostart on boot? [Y/n]"
    if ([string]::IsNullOrEmpty($script:Autostart)) {
        $script:Autostart = "Y"
    }

    # Write configuration file
    $ConfigContent = @"
# ClubAI Node Agent Configuration
# Generated by installer on $(Get-Date -Format "yyyy-MM-ddTHH:mm:ss")

node_id: "$script:NodeIdValue"
coordinator_url: "ws://${CoordinatorDefault}:${CoordinatorPort}/nodes/connect"
lmstudio_url: "$script:LMStudioUrl"
enrollment_token: "$script:EnrollToken"
data_dir: "$InstallDir\data"
log_dir: "$InstallDir\logs"
"@

    $ConfigContent | Out-File -FilePath "$InstallDir\config.yaml" -Encoding UTF8
    Write-Success "Configuration saved to $InstallDir\config.yaml"
}

# Install Windows Service using NSSM or sc.exe
function Install-WindowsService {
    Write-Info "Installing Windows Service..."

    $ServiceName = "ClubAINode"
    $BinPath = "$InstallDir\bin\$BinName"
    $ConfigPath = "$InstallDir\config.yaml"

    # Check if NSSM is available
    $NssmPath = Get-Command nssm -ErrorAction SilentlyContinue

    if ($NssmPath) {
        # Use NSSM for better service management
        Write-Info "Using NSSM for service installation..."

        & nssm install $ServiceName "$BinPath"
        & nssm set $ServiceName AppParameters "--config `"$ConfigPath`""
        & nssm set $ServiceName AppDirectory "$InstallDir"
        & nssm set $ServiceName Start SERVICE_AUTO_START
        & nssm set $ServiceName AppStdout "$InstallDir\logs\node.log"
        & nssm set $ServiceName AppStderr "$InstallDir\logs\node.log"
        & nssm set $ServiceName AppRotateFiles 1
        & nssm set $ServiceName AppRotateBytes 10485760
        & nssm start $ServiceName

        Write-Success "Service installed with NSSM and started"
    }
    else {
        # Create a wrapper batch file for sc.exe
        Write-Info "NSSM not found, using sc.exe (limited functionality)..."

        $WrapperContent = "@echo off`r`n`"$BinPath`" --config `"$ConfigPath`""
        $WrapperContent | Out-File -FilePath "$InstallDir\bin\run-node.bat" -Encoding ASCII

        # Note: sc.exe doesn't handle console apps well
        # This will create a service but it may not work perfectly
        try {
            sc.exe create $ServiceName binPath= "`"$InstallDir\bin\run-node.bat`"" start= auto
            sc.exe description $ServiceName "ClubAI Node Agent - Distributed AI Inference"
            sc.exe start $ServiceName
            Write-Success "Service installed and started"
        }
        catch {
            Write-Warning "Failed to create service with sc.exe"
            Write-Info "Consider installing NSSM for better service support:"
            Write-Info "  winget install nssm"
            Write-Info "  choco install nssm"
        }
    }
}

# Print completion message
function Show-Completion {
    Write-Host ""
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host "              Installation Complete!" -ForegroundColor Green
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Node ID:      $script:NodeIdValue"
    Write-Host "  Config:       $InstallDir\config.yaml"
    Write-Host "  Logs:         $InstallDir\logs\node.log"
    Write-Host ""
    Write-Host "  Useful Commands:" -ForegroundColor Cyan
    Write-Host "    Start:      $InstallDir\bin\$BinName --config $InstallDir\config.yaml"
    Write-Host "    View logs:  Get-Content -Tail 50 -Wait $InstallDir\logs\node.log"
    Write-Host "    Status:     sc.exe query ClubAINode"
    Write-Host "    Stop:       sc.exe stop ClubAINode"
    Write-Host "    Restart:    sc.exe stop ClubAINode; sc.exe start ClubAINode"
    Write-Host ""
    Write-Host "  Your node is now part of the ClubAI network!" -ForegroundColor Green
    Write-Host ""
}

# Main installation flow
function Main {
    if ($Help) {
        Show-Help
    }

    Write-Banner

    # Detect platform
    $Platform = Get-Platform
    Write-Success "Detected platform: $Platform"

    # Download binary
    Get-Binary

    # Configure node
    Get-Configuration

    # Install service
    if ($script:Autostart -match "^[Yy]$" -and -not $NoService) {
        Install-WindowsService
    }

    # Show completion
    Show-Completion
}

# Run main
Main
