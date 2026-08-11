[CmdletBinding()]
param(
    [ValidateSet("development", "offline-demo", "demo", "production", "public-demo", "evaluation")]
    [string]$Profile = "development",
    [ValidateSet("api", "tests", "langsmith-eval")]
    [string]$Action = "api",
    [switch]$Reload,
    [string]$PythonExecutable = $env:SHOPMIND_PYTHON,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

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
$env:SHOPMIND_DEPLOYMENT_PROFILE = $Profile

switch ($Profile) {
    "development" {
        $env:LANGSMITH_TRACING = "false"
        $env:LANGSMITH_PROJECT = "shopmind-development"
        $env:LANGSMITH_TRACING_SAMPLING_RATE = "1.0"
    }
    "offline-demo" {
        $env:LANGSMITH_TRACING = "false"
        $env:LANGSMITH_PROJECT = "shopmind-offline-demo"
        $env:LANGSMITH_TRACING_SAMPLING_RATE = "1.0"
    }
    "demo" {
        $env:LANGSMITH_TRACING = "true"
        $env:LANGSMITH_PROJECT = "shopmind-demo"
        $env:LANGSMITH_TRACING_SAMPLING_RATE = "1.0"
    }
    "production" {
        $env:LANGSMITH_TRACING = "true"
        $env:LANGSMITH_PROJECT = "shopmind-production"
        $env:LANGSMITH_TRACING_SAMPLING_RATE = "0.1"
    }
    "public-demo" {
        $env:LANGSMITH_TRACING = "true"
        $env:LANGSMITH_PROJECT = "shopmind-production"
        $env:LANGSMITH_TRACING_SAMPLING_RATE = "0.1"
    }
    "evaluation" {
        $env:LANGSMITH_TRACING = "true"
        $env:LANGSMITH_PROJECT = "shopmind-evaluation"
        $env:LANGSMITH_TRACING_SAMPLING_RATE = "1.0"
    }
}

if ($Action -eq "tests" -and $Profile -ne "development") {
    throw "Ordinary tests must use the development profile."
}

if ($Action -eq "langsmith-eval" -and $Profile -ne "evaluation") {
    throw "Cloud LangSmith evaluation requires the evaluation profile."
}

switch ($Action) {
    "api" {
        $uvicornArgs = @("-m", "uvicorn", "app.main:app")
        if ($Reload) {
            $uvicornArgs += "--reload"
        }
        & $python @uvicornArgs
    }
    "tests" {
        & $python -m pytest @Arguments
    }
    "langsmith-eval" {
        & $python evaluation\run_langsmith_eval.py @Arguments
    }
}

exit $LASTEXITCODE
