# Check if all phases in task_plan.md are complete
# Always exits 0 -- uses stdout for status reporting
# Used by Stop hook to report task completion status

param(
    [string]$PlanFile = "task_plan.md"
)

if (-not (Test-Path $PlanFile)) {
    Write-Host '[planning-with-files] No task_plan.md found -- no active planning session.'
    exit 0
}

# Read file content
$content = Get-Content $PlanFile -Raw

$multiline = [System.Text.RegularExpressions.RegexOptions]::Multiline

# Count explicit phase headings. Anchor the match so examples in prose do not
# inflate the count.
$TOTAL = ([regex]::Matches($content, "^[ \t]*### Phase([ \t:]|$)", $multiline)).Count

# Check for **Status:** format first
$COMPLETE = ([regex]::Matches($content, "^[ \t]*(-[ \t]*)?\*\*Status:\*\*[ \t]*complete[ \t]*$", $multiline)).Count
$IN_PROGRESS = ([regex]::Matches($content, "^[ \t]*(-[ \t]*)?\*\*Status:\*\*[ \t]*in_progress[ \t]*$", $multiline)).Count
$PENDING = ([regex]::Matches($content, "^[ \t]*(-[ \t]*)?\*\*Status:\*\*[ \t]*pending[ \t]*$", $multiline)).Count

# Fallback: check for [complete] inline format if **Status:** not found
if ($COMPLETE -eq 0 -and $IN_PROGRESS -eq 0 -and $PENDING -eq 0) {
    $COMPLETE = ([regex]::Matches($content, "^[ \t]*-[ \t]*\[complete\]", $multiline)).Count
    $IN_PROGRESS = ([regex]::Matches($content, "^[ \t]*-[ \t]*\[in_progress\]", $multiline)).Count
    $PENDING = ([regex]::Matches($content, "^[ \t]*-[ \t]*\[pending\]", $multiline)).Count
}

if ($TOTAL -eq 0) {
    $TOTAL = $COMPLETE + $IN_PROGRESS + $PENDING
}

# Report status -- always exit 0, incomplete task is a normal state
if ($COMPLETE -eq $TOTAL -and $TOTAL -gt 0) {
    Write-Host ('[planning-with-files] ALL PHASES COMPLETE (' + $COMPLETE + '/' + $TOTAL + '). If the user has additional work, add new phases to task_plan.md before starting.')
} else {
    Write-Host ('[planning-with-files] Task in progress (' + $COMPLETE + '/' + $TOTAL + ' phases complete). Update progress.md before stopping.')
    if ($IN_PROGRESS -gt 0) {
        Write-Host ('[planning-with-files] ' + $IN_PROGRESS + ' phase(s) still in progress.')
    }
    if ($PENDING -gt 0) {
        Write-Host ('[planning-with-files] ' + $PENDING + ' phase(s) pending.')
    }
}
exit 0
