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
    [string]$EnrollmentToken,
    [string]$LMStudioUrl = "http://localhost:1234/v1",
    [switch]$NoService,
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
    Write-Host "  -EnrollmentToken <token>  Use existing enrollment token (skip auth)"
    Write-Host "  -LMStudioUrl <url>        LM Studio URL (default: http://localhost:1234/v1)"
    Write-Host "  -NoService                Skip Windows Service installation"
    Write-Host "  -Help                     Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\install.ps1"
    Write-Host "  .\install.ps1 -EnrollmentToken 'iris_v1.eyJ...'"
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
# User Authentication
# =============================================================================

function Invoke-UserAuthentication {
    Write-Step "User authentication"
    Write-Host ""
    Write-Host "  ${Cyan}Do you have an Iris Network account?${Reset}"
    Write-Host "  ${Bold}1)${Reset} Yes, sign in"
    Write-Host "  ${Bold}2)${Reset} No, create new account"
    Write-Host ""

    $Choice = Read-Host "  Select [1/2]"

    switch ($Choice) {
        "1" { Invoke-Login }
        "2" { Invoke-Register }
        default {
            Write-Error "Invalid option"
            Invoke-UserAuthentication
        }
    }
}

function Invoke-Register {
    Write-Host ""
    Write-Info "New account registration"
    Write-Host ""

    $script:UserEmail = Read-Host "  Email"
    $SecurePassword = Read-Host "  Password" -AsSecureString
    $SecurePasswordConfirm = Read-Host "  Confirm password" -AsSecureString

    # Convert SecureString to plain text for comparison and API
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    $script:UserPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

    $BSTR2 = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePasswordConfirm)
    $PasswordConfirm = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR2)

    if ($script:UserPassword -ne $PasswordConfirm) {
        Write-Error "Passwords do not match"
        Invoke-Register
        return
    }

    Write-Info "Registering user..."

    try {
        $Body = @{
            email = $script:UserEmail
            password = $script:UserPassword
        } | ConvertTo-Json

        $Response = Invoke-RestMethod -Uri "${CoordinatorUrl}/auth/register" `
            -Method Post `
            -Body $Body `
            -ContentType "application/json" `
            -ErrorAction Stop

        Write-Success "Account created successfully"
        Invoke-DoLogin
    }
    catch {
        $ErrorDetail = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        $ErrorMsg = if ($ErrorDetail.detail) { $ErrorDetail.detail } else { "Unknown error" }
        Write-Error "Registration error: $ErrorMsg"
        Write-Host ""

        $TryLogin = Read-Host "  Try signing in instead? [Y/n]"
        if ($TryLogin -notmatch "^[Nn]$") {
            Invoke-DoLogin
        }
        else {
            exit 1
        }
    }
}

function Invoke-Login {
    Write-Host ""
    Write-Info "Sign in"
    Write-Host ""

    $script:UserEmail = Read-Host "  Email"
    $SecurePassword = Read-Host "  Password" -AsSecureString

    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    $script:UserPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

    Invoke-DoLogin
}

function Invoke-DoLogin {
    Write-Info "Signing in..."

    try {
        $Body = @{
            email = $script:UserEmail
            password = $script:UserPassword
        } | ConvertTo-Json

        $Response = Invoke-RestMethod -Uri "${CoordinatorUrl}/auth/login" `
            -Method Post `
            -Body $Body `
            -ContentType "application/json" `
            -ErrorAction Stop

        $script:AuthToken = $Response.access_token
        Write-Success "Signed in successfully"
    }
    catch {
        $ErrorDetail = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        $ErrorMsg = if ($ErrorDetail.detail) { $ErrorDetail.detail } else { "Invalid credentials" }
        Write-Error "Sign in error: $ErrorMsg"
        Write-Host ""

        $Retry = Read-Host "  Retry? [Y/n]"
        if ($Retry -notmatch "^[Nn]$") {
            Invoke-Login
        }
        else {
            exit 1
        }
    }
}

# =============================================================================
# Token Generation
# =============================================================================

function New-EnrollmentToken {
    Write-Step "Generating enrollment token..."

    $NodeLabel = "node-$($env:COMPUTERNAME.ToLower())-$(Get-Date -Format 'MMddHHmm')"

    try {
        $Body = @{
            label = $NodeLabel
        } | ConvertTo-Json

        $Headers = @{
            "Authorization" = "Bearer $script:AuthToken"
        }

        $Response = Invoke-RestMethod -Uri "${CoordinatorUrl}/admin/tokens/generate" `
            -Method Post `
            -Body $Body `
            -ContentType "application/json" `
            -Headers $Headers `
            -ErrorAction Stop

        $script:EnrollToken = $Response.token
        Write-Success "Token generated: $NodeLabel"
    }
    catch {
        $ErrorDetail = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        $ErrorMsg = if ($ErrorDetail.detail) { $ErrorDetail.detail } else { "Unknown error" }
        Write-Error "Token generation error: $ErrorMsg"
        exit 1
    }
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
# Configuration
# =============================================================================

function Set-NodeConfiguration {
    Write-Step "Configuring node..."

    # Generate node ID
    $script:NodeId = "node-$($env:COMPUTERNAME.ToLower())-$(Get-Date -Format 'MMddHHmm')"

    # Use detected or provided LM Studio URL
    $script:LMStudioUrlFinal = $script:DetectedLMStudioUrl

    # Create config file
    $ConfigContent = @"
# Iris Network - Node Configuration
# Generated: $(Get-Date -Format "yyyy-MM-ddTHH:mm:ss")

node_id: "$script:NodeId"
coordinator_url: "$CoordinatorWs"
lmstudio_url: "$script:LMStudioUrlFinal"
enrollment_token: "$script:EnrollToken"
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
            & nssm start $ServiceName

            Write-Success "Service installed with NSSM and started"
        }
        catch {
            Write-Warning "Failed to install service with NSSM"
        }
    }
    else {
        Write-Info "NSSM not found. Creating startup shortcut instead..."

        # Create startup shortcut
        $WshShell = New-Object -ComObject WScript.Shell
        $StartupFolder = [Environment]::GetFolderPath("Startup")
        $ShortcutPath = "$StartupFolder\IrisNode.lnk"

        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $BinPath
        $Shortcut.Arguments = "--config `"$ConfigPath`""
        $Shortcut.WorkingDirectory = $InstallDir
        $Shortcut.Description = "Iris Network Node Agent"
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
    Write-Host "  ${Bold}Useful commands:${Reset}"

    if ($script:PythonMode) {
        Write-Host "    ${Cyan}Start:${Reset}      python -m node_agent.standalone_main --config $InstallDir\config.yaml"
    }
    elseif ($script:PathConfigured) {
        Write-Host "    ${Cyan}Start:${Reset}      iris-node --config $InstallDir\config.yaml"
        Write-Host "    ${Cyan}Help:${Reset}       iris-node --help"
    }
    else {
        Write-Host "    ${Cyan}Start:${Reset}      $InstallDir\bin\$BinName --config $InstallDir\config.yaml"
    }

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

    Write-Banner

    # Step 1: Platform detection
    Get-Platform

    # Step 2: Check coordinator
    Test-Coordinator

    # Step 3: Check LM Studio
    Test-LMStudio

    # Step 4: Authentication (if no token provided)
    if ([string]::IsNullOrEmpty($EnrollmentToken)) {
        Invoke-UserAuthentication
        New-EnrollmentToken
    }
    else {
        $script:EnrollToken = $EnrollmentToken
        Write-Step "Using provided token"
        Write-Success "Token: $($EnrollmentToken.Substring(0, [Math]::Min(20, $EnrollmentToken.Length)))..."
    }

    # Step 5: Download binary
    Get-Binary

    # Step 6: Setup PATH
    if (-not $script:PythonMode) {
        Set-PathEnvironment
    }

    # Step 7: Configure
    Set-NodeConfiguration

    # Step 8: Service installation
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
