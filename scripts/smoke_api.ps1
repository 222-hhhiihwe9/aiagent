param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$UserId = "phase1_smoke_u001",
    [string]$Username = ""
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

if ([string]::IsNullOrWhiteSpace($Username)) {
    $Username = [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String("6Zi25q616Zuq5rWL6K+V55So5oi3")
    )
}

$KnowledgeQuery = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String("5rSb5aSp5L6d55qE5bqU5o+05LyN5piv5LuA5LmI77yf")
)

$MemoryWriteText = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String("6K+36K6w5L2P77yM5oiR5Zac5qyi5pma5LiK5YaZ5Luj56CB77yM6ICM5LiU5LiT5rOo5pe25LiN5Zac5qyi6KKr5omT5pat44CC")
)

$MemorySearchQuery = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String("5pma5LiK5YaZ5Luj56CB")
)

function Show-Json($Value) {
    $Value | ConvertTo-Json -Depth 30
}

function Invoke-JsonPost($Path, $Body) {
    $json = $Body | ConvertTo-Json -Depth 20

    Invoke-RestMethod `
        -Method Post `
        -Uri "$($BaseUrl)$Path" `
        -ContentType "application/json; charset=utf-8" `
        -Body $json
}

function Invoke-JsonGet($Path) {
    Invoke-RestMethod `
        -Method Get `
        -Uri "$($BaseUrl)$Path"
}

Write-Host ""
Write-Host "== AIAgent Phase 1 Smoke Test ==" -ForegroundColor Cyan
Write-Host "BaseUrl: $BaseUrl"
Write-Host "UserId : $UserId"
Write-Host ""

Write-Host "1. Health check" -ForegroundColor Yellow
$health = Invoke-JsonGet "/health"
Show-Json $health

Write-Host ""
Write-Host "2. Knowledge stats" -ForegroundColor Yellow
$knowledgeStats = Invoke-JsonGet "/knowledge/stats"
Show-Json $knowledgeStats

Write-Host ""
Write-Host "3. Start async RAG rebuild" -ForegroundColor Yellow
$rebuild = Invoke-JsonPost "/knowledge/rebuild" @{
    force_rebuild = $true
    async_rebuild = $true
}
Show-Json $rebuild

Write-Host ""
Write-Host "4. RAG rebuild status" -ForegroundColor Yellow
$rebuildStatus = Invoke-JsonGet "/knowledge/rebuild/status"
Show-Json $rebuildStatus

Write-Host ""
Write-Host "5. Knowledge search" -ForegroundColor Yellow
$knowledgeSearch = Invoke-JsonPost "/knowledge/search" @{
    query = $KnowledgeQuery
    top_k = 3
    include_prompt_context = $true
}
Show-Json $knowledgeSearch

Write-Host ""
Write-Host "6. Chat memory write test" -ForegroundColor Yellow
$chat = Invoke-JsonPost "/chat" @{
    user_id = $UserId
    username = $Username
    text = $MemoryWriteText
}
Show-Json $chat

Write-Host ""
Write-Host "7. Memory search" -ForegroundColor Yellow
$encodedQuery = [System.Uri]::EscapeDataString($MemorySearchQuery)
$memorySearch = Invoke-JsonGet "/memory/user/$UserId/search?query=$encodedQuery&limit=5"
Show-Json $memorySearch

Write-Host ""
Write-Host "8. Memory stats" -ForegroundColor Yellow
$memoryStats = Invoke-JsonGet "/memory/user/$UserId/stats"
Show-Json $memoryStats

Write-Host ""
Write-Host "== Smoke test completed ==" -ForegroundColor Green
