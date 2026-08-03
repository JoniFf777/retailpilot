[CmdletBinding()]
param(
    [ValidateSet("development", "demo", "production", "public-demo", "evaluation")]
    [string]$Profile = "development",
    [ValidateSet("api", "tests", "langsmith-eval")]
    [string]$Action = "api",
    [switch]$Reload,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

$python = "D:\DL\Anaconda3\envs\pythonLearn\python.exe"
$env:SHOPMIND_DEPLOYMENT_PROFILE = $Profile

switch ($Profile) {
    "development" {
        $env:LANGSMITH_TRACING = "false"
        $env:LANGSMITH_PROJECT = "shopmind-development"
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
        & conda run -n pythonLearn $python @uvicornArgs
    }
    "tests" {
        & conda run -n pythonLearn $python -m pytest @Arguments
    }
    "langsmith-eval" {
        & conda run -n pythonLearn $python evaluation\run_langsmith_eval.py @Arguments
    }
}

exit $LASTEXITCODE
