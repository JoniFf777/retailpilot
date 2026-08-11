[CmdletBinding(DefaultParameterSetName = "Prepare")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Prepare")]
    [switch]$Prepare,
    [Parameter(Mandatory = $true, ParameterSetName = "Start")]
    [switch]$Start,
    [Parameter(Mandatory = $true, ParameterSetName = "Verify")]
    [switch]$Verify,
    [string]$BackendHost = "127.0.0.1",
    [int]$BackendPort = 8000,
    [string]$FrontendHost = "127.0.0.1",
    [int]$FrontendPort = 5173,
    [string]$PythonExecutable = $env:SHOPMIND_PYTHON,
    [Parameter(ParameterSetName = "Start")]
    [switch]$ReuseExisting,
    [Parameter(ParameterSetName = "Verify")]
    [string]$UserId = "demo-user",
    [Parameter(ParameterSetName = "Verify")]
    [string]$OrderId,
    [Parameter(ParameterSetName = "Verify")]
    [switch]$RequirePaid
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
function Resolve-ShopMindPython {
    param([string]$ExplicitPath)
    if ($ExplicitPath) {
        $command = Get-Command $ExplicitPath -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
        throw "Python executable '$ExplicitPath' was not found. Set -PythonExecutable or SHOPMIND_PYTHON to a valid interpreter."
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw "Python was not found on PATH. Activate the project environment or set SHOPMIND_PYTHON."
}

$python = Resolve-ShopMindPython -ExplicitPath $PythonExecutable
$localLogRoot = Join-Path $projectRoot ".local\shopmind-demo"

function Set-DemoEnvironment {
    # This is the server-owned, deterministic core-demo policy.  The browser
    # never selects payment outcomes, scenarios, or tracing providers.
    $env:SHOPMIND_DEPLOYMENT_PROFILE = "offline-demo"
    $env:LANGSMITH_TRACING = "false"
    $env:LANGCHAIN_TRACING_V2 = "false"
    $env:LANGSMITH_API_KEY = ""
    $env:LANGSMITH_PROJECT = "shopmind-offline-demo"
    $env:LANGSMITH_TRACING_SAMPLING_RATE = "1.0"
    $env:SHOPMIND_AGENT_MODE = "multi"
    $env:SHOPMIND_SUPERVISOR_ROUTER = "deterministic"
    $env:SHOPMIND_AGENT_PLANNER = "deterministic"
    $env:SHOPMIND_RAG_AGENT_TRANSPORT = "in_process"
    $env:SHOPMIND_IDENTITY_PROVIDER = "development_payload"
    $env:SHOPMIND_OUTBOX_ENABLED = "false"
    $env:VITE_SHOPMIND_DEMO_IDENTITY = "true"
    $env:SHOPMIND_CHECKOUT_SIGNING_SECRET = "shopmind-offline-demo-checkout-secret-2026"
    # Some conda-enabled Windows shells expose both PATH and Path.  Normalize
    # the process environment before Start-Process builds its child map.
    $processPath = [System.Environment]::GetEnvironmentVariable("Path", "Process")
    [System.Environment]::SetEnvironmentVariable("PATH", $null, "Process")
    [System.Environment]::SetEnvironmentVariable("Path", $processPath, "Process")
}

function Invoke-ShopMindPython {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    Push-Location $projectRoot
    try {
        & $python @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE." }
    }
    finally { Pop-Location }
}

function Test-TcpPort {
    param([Parameter(Mandatory = $true)][string]$HostName, [Parameter(Mandatory = $true)][int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        return $task.Wait(800)
    }
    catch { return $false }
    finally { $client.Dispose() }
}

function Assert-PortAvailable {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Service,
        [switch]$AllowReuse
    )
    if (Test-TcpPort -HostName $HostName -Port $Port) {
        if ($AllowReuse) { return $true }
        throw "$Service port $Port is already in use. Default -Start is clean-room/fail-closed and will not reuse an unknown process; stop the old $Service process or choose a different $Service port."
    }
    return $false
}

function Wait-ForOfflineDemoBackend {
    param([Parameter(Mandatory = $true)][string]$BaseUrl)
    $deadline = (Get-Date).AddSeconds(25)
    $lastError = "no response"
    while ((Get-Date) -lt $deadline) {
        try {
            $readiness = Invoke-RestMethod -Uri "$BaseUrl/api/health/readiness" -Method Get -TimeoutSec 2
            if ($readiness.profile -ne "offline-demo") {
                throw "readiness profile is '$($readiness.profile)'"
            }
            if ($readiness.ready -ne $true -or $readiness.status -ne "ready") {
                throw "readiness is not ready"
            }
            return
        }
        catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Started Backend did not prove offline-demo readiness at $BaseUrl ($lastError)."
}

function Wait-ForFrontendShell {
    param([Parameter(Mandatory = $true)][string]$BaseUrl)
    $deadline = (Get-Date).AddSeconds(20)
    $lastError = "no response"
    while ((Get-Date) -lt $deadline) {
        $response = $null
        $reader = $null
        try {
            $request = [System.Net.WebRequest]::Create("$BaseUrl/")
            $request.Timeout = 2000
            $response = $request.GetResponse()
            $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
            $content = $reader.ReadToEnd()
            if ([int]$response.StatusCode -eq 200 -and $content -match '<div id="root">') {
                return
            }
            throw "frontend did not return the ShopMind Vite shell"
        }
        catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
        finally {
            if ($reader) { $reader.Dispose() }
            if ($response) { $response.Dispose() }
        }
    }
    throw "Started Frontend did not serve the ShopMind shell at $BaseUrl ($lastError)."
}

function Invoke-Prepare {
    Set-DemoEnvironment
    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 5432)) {
        throw "PostgreSQL port 5432 is not reachable. Start the isolated local PostgreSQL service first."
    }
    $frontendPath = Join-Path $projectRoot "frontend"
    if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "package-lock.json"))) {
        throw "frontend/package-lock.json is missing; the clean-room setup must include the committed frontend lockfile."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "node_modules\.bin\vite.cmd"))) {
        throw "frontend dependencies are missing. Run 'npm --prefix frontend ci' once, then repeat -Prepare."
    }

    Write-Host "[Prepare] validate isolated local PostgreSQL, migrate to head, and seed without reset"
    Invoke-ShopMindPython -Arguments @("scripts\prepare_shopmind_demo.py", "--json")
    Write-Host "[Prepare] frontend dependencies available"
    Write-Host "[Prepare] complete; no RocketMQ SDK, broker, publisher, or LangSmith credential is required"
}

function Invoke-Start {
    Set-DemoEnvironment
    New-Item -ItemType Directory -Force -Path $localLogRoot | Out-Null
    $backendUrl = "http://$BackendHost`:$BackendPort"
    $frontendUrl = "http://$FrontendHost`:$FrontendPort"
    # Validate both ports before starting either child.  A reachable port is
    # not proof of the intended demo process and must never be silently reused.
    # Reuse is an explicit convenience escape hatch only; clean-room runs leave
    # -ReuseExisting unset.
    $backendOccupied = Assert-PortAvailable -HostName $BackendHost -Port $BackendPort -Service "Backend" -AllowReuse:$ReuseExisting
    $frontendOccupied = Assert-PortAvailable -HostName $FrontendHost -Port $FrontendPort -Service "Frontend" -AllowReuse:$ReuseExisting

    $frontendRoot = Join-Path $projectRoot "frontend"
    $frontendBuildLog = Join-Path $localLogRoot "frontend-build.log"
    $frontendDistIndex = Join-Path $frontendRoot "dist\index.html"
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { throw "npm was not found on PATH. Install Node.js/npm before starting the demo." }
    Push-Location $frontendRoot
    try {
        & $npm.Source run build -- --configLoader native *> $frontendBuildLog
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed with exit code $LASTEXITCODE." }
    }
    finally { Pop-Location }
    $env:SHOPMIND_BACKEND_URL = $backendUrl

    $backendProcess = $null
    $frontendProcess = $null
    if ($backendOccupied) {
        Write-Host "[Start] reusing explicitly requested Backend on $backendUrl; verifying offline-demo readiness"
        Wait-ForOfflineDemoBackend -BaseUrl $backendUrl
    }
    else {
        $backendLog = Join-Path $localLogRoot "backend.log"
        $backendErr = Join-Path $localLogRoot "backend.error.log"
        # Use the same pinned pythonLearn interpreter as `conda run`, but launch it
        # directly so the child does not depend on a PowerShell conda alias.
        $backendArgs = @("-m", "uvicorn", "app.main:app", "--host", $BackendHost, "--port", "$BackendPort")
        $backendProcess = Start-Process -FilePath $python -ArgumentList $backendArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -PassThru
        Wait-ForOfflineDemoBackend -BaseUrl $backendUrl
    }

    if ($frontendOccupied) {
        Write-Host "[Start] reusing explicitly requested Frontend on $frontendUrl; verifying ShopMind shell"
        Wait-ForFrontendShell -BaseUrl $frontendUrl
    }
    else {
        $frontendLog = Join-Path $localLogRoot "frontend.log"
        $frontendErr = Join-Path $localLogRoot "frontend.error.log"
        $node = (Get-Command node.exe -ErrorAction Stop).Source
        $npmCli = Join-Path (Split-Path -Parent $node) "node_modules\npm\bin\npm-cli.js"
        $frontendProcess = Start-Process -FilePath $node -ArgumentList @($npmCli, "run", "preview", "--", "--host", $FrontendHost, "--port", "$FrontendPort", "--strictPort", "--configLoader", "native") -WorkingDirectory $frontendRoot -WindowStyle Hidden -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErr -PassThru
        Wait-ForFrontendShell -BaseUrl $frontendUrl
    }

    Write-Host "[Start] ReuseExisting: $($ReuseExisting.IsPresent)"
    Write-Host "[Start] backend pid: $(if ($backendProcess) { $backendProcess.Id } else { 'existing' })"
    Write-Host "[Start] frontend pid: $(if ($frontendProcess) { $frontendProcess.Id } else { 'existing' })"
    Write-Host "[Start] backend: $backendUrl"
    Write-Host "[Start] frontend: $frontendUrl"
    Write-Host "[Start] health: $backendUrl/api/health"
    Write-Host "[Start] readiness: $backendUrl/api/health/readiness"
    Write-Host "[Start] core demo does not start RocketMQ; run -Verify after both URLs are ready"
}

function Invoke-Verify {
    Set-DemoEnvironment
    $arguments = @(
        "scripts\smoke_shopmind_demo.py",
        "--backend-url", "http://$BackendHost`:$BackendPort",
        "--frontend-url", "http://$FrontendHost`:$FrontendPort",
        "--user-id", $UserId,
        "--json"
    )
    if ($OrderId) { $arguments += @("--order-id", $OrderId) }
    if ($RequirePaid) { $arguments += "--require-paid" }
    Invoke-ShopMindPython -Arguments $arguments
}

if ($Prepare) { Invoke-Prepare }
elseif ($Start) { Invoke-Start }
else { Invoke-Verify }
