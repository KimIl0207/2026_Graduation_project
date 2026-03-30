param(
    [string]$RepoPath = ".",
    [string]$BaseBranch = "dev",
    [int]$IntervalSeconds = 30,
    [switch]$AutoFetch
)

Set-Location $RepoPath

function Get-CurrentBranch {
    git rev-parse --abbrev-ref HEAD 2>$null
}

function Get-LocalBaseHash {
    git rev-parse $BaseBranch 2>$null
}

function Get-RemoteBaseHash {
    git rev-parse "origin/$BaseBranch" 2>$null
}

function Has-UncommittedChanges {
    $status = git status --porcelain 2>$null
    return -not [string]::IsNullOrWhiteSpace($status)
}

Write-Host "=== dev 변경 감지 시작 ===" -ForegroundColor Cyan
Write-Host "RepoPath        : $(Get-Location)"
Write-Host "BaseBranch      : $BaseBranch"
Write-Host "IntervalSeconds : $IntervalSeconds"
Write-Host "AutoFetch       : $AutoFetch"
Write-Host ""

$lastRemoteHash = $null

while ($true) {
    try {
        if ($AutoFetch) {
            git fetch origin | Out-Null
        }

        $currentBranch = Get-CurrentBranch
        $localBaseHash = Get-LocalBaseHash
        $remoteBaseHash = Get-RemoteBaseHash

        if (-not $remoteBaseHash) {
            Write-Host "[오류] origin/$BaseBranch 를 찾을 수 없음" -ForegroundColor Red
            Start-Sleep -Seconds $IntervalSeconds
            continue
        }

        if ($lastRemoteHash -eq $null) {
            $lastRemoteHash = $remoteBaseHash
        }

        if ($remoteBaseHash -ne $lastRemoteHash) {
            Write-Host ""
            Write-Host "===============================" -ForegroundColor Yellow
            Write-Host "[감지] origin/$BaseBranch 에 새 커밋 발생" -ForegroundColor Yellow
            Write-Host "이전: $lastRemoteHash"
            Write-Host "현재: $remoteBaseHash"
            Write-Host "현재 작업 브랜치: $currentBranch"
            Write-Host "===============================" -ForegroundColor Yellow

            if (Has-UncommittedChanges) {
                Write-Host "[주의] 작업 중 변경사항이 있음. 바로 rebase 하지 마라." -ForegroundColor Red
            } else {
                Write-Host "[안내] 아래 명령으로 반영 가능:" -ForegroundColor Green
                Write-Host "git fetch origin"
                Write-Host "git rebase origin/$BaseBranch"
            }

            [console]::beep(1000, 400)
            $lastRemoteHash = $remoteBaseHash
        }

        if ($localBaseHash -and $remoteBaseHash -and $localBaseHash -ne $remoteBaseHash) {
            Write-Host "[참고] 로컬 $BaseBranch 가 origin/$BaseBranch 보다 오래됨" -ForegroundColor DarkYellow
        }

    } catch {
        Write-Host "[예외] $($_.Exception.Message)" -ForegroundColor Red
    }

    Start-Sleep -Seconds $IntervalSeconds
}