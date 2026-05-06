# planning-with-files: resolve active plan directory (PowerShell mirror).
#
# Resolution order matches scripts/resolve-plan-dir.sh:
#   1. $env:CODEX_PLAN_DIR if it contains task_plan.md
#   2. $env:PLAN_ID -> .\.planning\plans\$PLAN_ID\ or .\.planning\$PLAN_ID\
#   3. .\.planning\.active_plan content
#   4. Newest .\.planning\plans\<dir>\, then .\.planning\<dir>\ by LastWriteTime
#   5. Empty (legacy fallback to .\task_plan.md handled by caller)

param(
    [string]$PlanRoot = (Join-Path (Get-Location) ".planning")
)

$activeFile = Join-Path $PlanRoot ".active_plan"
$planContainer = Join-Path $PlanRoot "plans"

function Emit-IfPlanDir {
    param([string] $Candidate)
    if (-not $Candidate) { return $false }
    $planFile = Join-Path $Candidate "task_plan.md"
    if ((Test-Path $Candidate -PathType Container) -and (Test-Path $planFile -PathType Leaf)) {
        Write-Output $Candidate
        return $true
    }
    return $false
}

if ($env:CODEX_PLAN_DIR) {
    $candidate = $env:CODEX_PLAN_DIR
    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
        $candidate = Join-Path (Get-Location) $candidate
    }
    if (Emit-IfPlanDir $candidate) { exit 0 }
}

if ($env:PLAN_ID) {
    if (Emit-IfPlanDir (Join-Path $planContainer $env:PLAN_ID)) { exit 0 }
    if (Emit-IfPlanDir (Join-Path $PlanRoot $env:PLAN_ID)) { exit 0 }
}

if (Test-Path $activeFile) {
    $planId = (Get-Content $activeFile -Raw).Trim()
    if ($planId) {
        if (Emit-IfPlanDir (Join-Path $planContainer $planId)) { exit 0 }
        if (Emit-IfPlanDir (Join-Path $PlanRoot $planId)) { exit 0 }
    }
}

function Resolve-LatestIn {
    param([string] $Root)
    if (-not (Test-Path $Root -PathType Container)) { return $false }
    $latest = Get-ChildItem -Path $Root -Directory |
        Where-Object { -not $_.Name.StartsWith('.') } |
        Where-Object { Test-Path (Join-Path $_.FullName "task_plan.md") -PathType Leaf } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latest) {
        Write-Output $latest.FullName
        return $true
    }
    return $false
}

if (Resolve-LatestIn $planContainer) { exit 0 }
if (Resolve-LatestIn $PlanRoot) { exit 0 }

exit 0
