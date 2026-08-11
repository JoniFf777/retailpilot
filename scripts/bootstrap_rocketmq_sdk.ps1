[CmdletBinding()]
param(
    [string]$PythonExecutable = $env:SHOPMIND_PYTHON,
    [string]$OutputDirectory = (Join-Path (Get-Location) "artifacts\rocketmq-sdk")
)

$ErrorActionPreference = "Stop"

if (-not $PythonExecutable) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found on PATH. Activate the project environment or set SHOPMIND_PYTHON."
    }
    $PythonExecutable = $pythonCommand.Source
}
elseif (-not (Get-Command $PythonExecutable -ErrorAction SilentlyContinue)) {
    throw "Python executable '$PythonExecutable' was not found. Set -PythonExecutable or SHOPMIND_PYTHON to a valid interpreter."
}
$sourceCommit = "d463e6400e9819f95a944fa086877336d2e6aad8"
$tempRoot = Join-Path $env:TEMP ("shopmind-rocketmq-sdk-" + [guid]::NewGuid().ToString("N"))
$sourceDirectory = Join-Path $tempRoot "rocketmq-clients"
$buildEnvironment = Join-Path $tempRoot "build-env"
$wheelhouse = Join-Path $tempRoot "wheelhouse"

$dependencies = @(
    "setuptools==84.0.0",
    "wheel==0.46.1",
    "packaging==26.3",
    "grpcio==1.83.0",
    "grpcio-tools==1.83.0",
    "protobuf==7.35.1",
    "opentelemetry-api==1.44.0",
    "opentelemetry-sdk==1.44.0",
    "opentelemetry-exporter-otlp==1.44.0"
)

try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    git clone --no-checkout https://github.com/apache/rocketmq-clients.git $sourceDirectory
    git -C $sourceDirectory fetch --depth 1 origin $sourceCommit
    git -C $sourceDirectory checkout --detach $sourceCommit
    $resolvedCommit = (git -C $sourceDirectory rev-parse HEAD).Trim()
    if ($resolvedCommit -ne $sourceCommit) {
        throw "Resolved Apache RocketMQ client commit '$resolvedCommit' does not match '$sourceCommit'."
    }

    & $PythonExecutable -m venv $buildEnvironment
    $buildPython = Join-Path $buildEnvironment "Scripts\python.exe"
    & $buildPython -m pip install @dependencies
    $env:SOURCE_DATE_EPOCH = "0"
    New-Item -ItemType Directory -Force -Path $wheelhouse | Out-Null
    & $buildPython -m pip wheel --no-cache-dir --no-build-isolation --no-deps `
        --wheel-dir $wheelhouse (Join-Path $sourceDirectory "python")

    $wheel = Get-ChildItem -LiteralPath $wheelhouse -Filter "rocketmq_python_client-5.1.1-*.whl" -File | Select-Object -First 1
    if ($null -eq $wheel) {
        throw "The Apache RocketMQ Python wheel was not produced."
    }
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $destination = Join-Path $OutputDirectory $wheel.Name
    Copy-Item -LiteralPath $wheel.FullName -Destination $destination -Force
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
    [pscustomobject]@{
        source_commit = $resolvedCommit
        wheel = $destination
        sha256 = $hash
        source_date_epoch = $env:SOURCE_DATE_EPOCH
    } | ConvertTo-Json
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
