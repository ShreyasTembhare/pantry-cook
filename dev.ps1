# Start Pantry Cook via dev.sh (Git Bash). From repo root:  .\dev.ps1
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

$bashCandidates = @(
  "$env:ProgramFiles\Git\bin\bash.exe",
  "$env:ProgramFiles\Git\usr\bin\bash.exe",
  "$env:LocalAppData\Programs\Git\bin\bash.exe"
)

function Convert-ToGitBashPath([string]$Path) {
  $normalized = $Path -replace '\\', '/'
  if ($normalized -match '^([A-Za-z]):(/.*)$') {
    return ('/' + $Matches[1].ToLower() + $Matches[2])
  }
  return $normalized
}

foreach ($bash in $bashCandidates) {
  if (Test-Path -LiteralPath $bash) {
    $rootForBash = Convert-ToGitBashPath $Root
    & $bash -lc "cd '$rootForBash' && ./dev.sh"
    exit $LASTEXITCODE
  }
}

Write-Error @"
Git Bash was not found. Install Git for Windows, then run:

  ./dev.sh

from Git Bash in the repo root, or run the API and frontend manually (see README).
"@
