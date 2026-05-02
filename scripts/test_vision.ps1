param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$ImagePath = "",
    [string]$UserId = "vision_test_u001",
    [string]$Prompt = ""
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

if ([string]::IsNullOrWhiteSpace($ImagePath)) {
    throw "Please provide -ImagePath. Example: powershell -ExecutionPolicy Bypass -File scripts\test_vision.ps1 -ImagePath data\characters\luotianyi\images\LUO1.jpg"
}

if (!(Test-Path -LiteralPath $ImagePath)) {
    throw "Image file not found: $ImagePath"
}

if ([string]::IsNullOrWhiteSpace($Prompt)) {
    $Prompt = [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String("6K+35YiG5p6Q6L+Z5byg5Zu+77yM5ZKM5YCZ6YCJ6KeS6Imy5a+55q+U77yM5aaC5p6c5LiN56Gu5a6a5LiN6KaB5by65Yi26K6k5YeG44CC")
    )
}

function Show-Json($Value) {
    $Value | ConvertTo-Json -Depth 50
}

Write-Host ""
Write-Host "== Vision Character Index Stats ==" -ForegroundColor Cyan
$stats = Invoke-RestMethod `
    -Method Get `
    -Uri "$BaseUrl/vision/characters/stats"
Show-Json $stats

Write-Host ""
Write-Host "== Rebuild Vision Character Index ==" -ForegroundColor Cyan
$rebuild = Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl/vision/characters/rebuild?force_rebuild=true"
Show-Json $rebuild

Write-Host ""
Write-Host "== Analyze Image ==" -ForegroundColor Cyan

$form = @{
    user_id = $UserId
    prompt = $Prompt
    file = Get-Item -LiteralPath $ImagePath
}

$result = Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl/vision/analyze" `
    -Form $form

Show-Json $result

Write-Host ""
Write-Host "== Key Result ==" -ForegroundColor Yellow
$result.result.recognized_characters | ConvertTo-Json -Depth 20
Write-Host "is_confident:" $result.result.is_confident
Write-Host "confidence  :" $result.result.confidence
Write-Host "summary     :" $result.result.summary

Write-Host ""
Write-Host "== Vision test completed ==" -ForegroundColor Green
