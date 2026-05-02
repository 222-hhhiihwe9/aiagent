param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$RootDir = "data\characters",
    [int]$MaxPerCharacter = 10,
    [string]$UserId = "vision_batch_test"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

Add-Type -AssemblyName System.Net.Http

$Prompt = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String("6K+35L2g6K6k55yf6K+G5Yir5Zu+54mH5Lit55qE6KeS6Imy44CC5aaC5p6c5LiN56Gu5a6a77yM5LiN6KaB5by65Yi26K6k5YeG44CC")
)

function Get-ExpectedId {
    param([string]$Path)

    $parts = $Path -split "[\\/]"
    $index = [Array]::IndexOf($parts, "characters")

    if ($index -ge 0 -and $parts.Length -gt ($index + 1)) {
        return $parts[$index + 1]
    }

    return ""
}

function Get-MimeType {
    param([string]$Path)

    $ext = [System.IO.Path]::GetExtension($Path).ToLower()

    switch ($ext) {
        ".jpg" { return "image/jpeg" }
        ".jpeg" { return "image/jpeg" }
        ".png" { return "image/png" }
        ".webp" { return "image/webp" }
        default { return "application/octet-stream" }
    }
}

function Invoke-VisionAnalyze {
    param(
        [string]$Url,
        [string]$ImagePath,
        [string]$UserId,
        [string]$Prompt
    )

    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromSeconds(240)

    $form = New-Object System.Net.Http.MultipartFormDataContent
    $fileStream = $null

    try {
        $userContent = New-Object System.Net.Http.StringContent($UserId)
        $promptContent = New-Object System.Net.Http.StringContent($Prompt)

        $form.Add($userContent, "user_id")
        $form.Add($promptContent, "prompt")

        $resolvedPath = (Resolve-Path -LiteralPath $ImagePath).Path
        $fileStream = [System.IO.File]::OpenRead($resolvedPath)

        $fileContent = New-Object System.Net.Http.StreamContent($fileStream)
        $mimeType = Get-MimeType $resolvedPath
        $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse($mimeType)

        $fileName = [System.IO.Path]::GetFileName($resolvedPath)
        $form.Add($fileContent, "file", $fileName)

        $response = $client.PostAsync($Url, $form).Result
        $text = $response.Content.ReadAsStringAsync().Result

        if (-not $response.IsSuccessStatusCode) {
            throw ("HTTP " + [int]$response.StatusCode + ": " + $text)
        }

        return $text | ConvertFrom-Json
    }
    finally {
        if ($fileStream -ne $null) {
            $fileStream.Dispose()
        }

        if ($form -ne $null) {
            $form.Dispose()
        }

        if ($client -ne $null) {
            $client.Dispose()
        }
    }
}

function Show-Json {
    param($Value)
    $Value | ConvertTo-Json -Depth 50
}

Write-Host ""
Write-Host "== Vision Batch Test ==" -ForegroundColor Cyan
Write-Host "BaseUrl        : $BaseUrl"
Write-Host "RootDir        : $RootDir"
Write-Host "MaxPerCharacter: $MaxPerCharacter"
Write-Host ""

Write-Host "1. Rebuild vision character index" -ForegroundColor Yellow
$rebuild = Invoke-RestMethod `
    -Method Post `
    -Uri "$BaseUrl/vision/characters/rebuild?force_rebuild=true"
Show-Json $rebuild

Write-Host ""
Write-Host "2. Load test images" -ForegroundColor Yellow

$images = Get-ChildItem -LiteralPath $RootDir -Recurse -File |
    Where-Object { $_.Extension.ToLower() -in @(".jpg", ".jpeg", ".png", ".webp") } |
    Group-Object { Get-ExpectedId $_.FullName } |
    ForEach-Object { $_.Group | Select-Object -First $MaxPerCharacter }

Write-Host "Image count: $($images.Count)"

$total = 0
$correct = 0
$wrong = 0
$uncertain = 0
$errorCount = 0
$rows = @()

foreach ($image in $images) {
    $expected = Get-ExpectedId $image.FullName

    if ([string]::IsNullOrWhiteSpace($expected)) {
        continue
    }

    Write-Host ""
    Write-Host "Testing: $($image.FullName)" -ForegroundColor Yellow
    Write-Host "Expected: $expected"

    try {
        $result = Invoke-VisionAnalyze `
            -Url "$BaseUrl/vision/analyze" `
            -ImagePath $image.FullName `
            -UserId $UserId `
            -Prompt $Prompt

        $chars = @($result.result.recognized_characters)

        $predicted = ""
        $confidence = 0.0
        $isConfident = [bool]$result.result.is_confident

        if ($chars.Count -gt 0) {
            $top = $chars[0]
            $predicted = [string]$top.character_id
            $confidence = [double]$top.confidence
        }

        $status = "uncertain"

        if ($isConfident -and $predicted -eq $expected) {
            $status = "correct"
            $correct += 1
        }
        elseif ($isConfident -and $predicted -ne $expected) {
            $status = "wrong"
            $wrong += 1
        }
        else {
            $status = "uncertain"
            $uncertain += 1
        }

        $total += 1

        Write-Host "Predicted : $predicted"
        Write-Host "Confidence: $confidence"
        Write-Host "Confident : $isConfident"
        Write-Host "Status    : $status"

        $rows += [PSCustomObject]@{
            image = $image.FullName
            expected = $expected
            predicted = $predicted
            confidence = $confidence
            is_confident = $isConfident
            status = $status
            summary = [string]$result.result.summary
        }
    }
    catch {
        $total += 1
        $wrong += 1
        $errorCount += 1

        Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red

        $rows += [PSCustomObject]@{
            image = $image.FullName
            expected = $expected
            predicted = "ERROR"
            confidence = 0
            is_confident = $false
            status = "error"
            summary = $_.Exception.Message
        }
    }
}

$accuracyOnAll = 0
$wrongRate = 0
$uncertainRate = 0

if ($total -gt 0) {
    $accuracyOnAll = [Math]::Round($correct / $total, 4)
    $wrongRate = [Math]::Round($wrong / $total, 4)
    $uncertainRate = [Math]::Round($uncertain / $total, 4)
}

$summary = [PSCustomObject]@{
    total = $total
    correct = $correct
    wrong = $wrong
    uncertain = $uncertain
    errors = $errorCount
    accuracy_on_all = $accuracyOnAll
    wrong_rate = $wrongRate
    uncertain_rate = $uncertainRate
}

Write-Host ""
Write-Host "== Batch Summary ==" -ForegroundColor Cyan
$summary | ConvertTo-Json -Depth 10

Write-Host ""
Write-Host "== Wrong / Uncertain Details ==" -ForegroundColor Cyan
$rows |
    Where-Object { $_.status -ne "correct" } |
    Format-Table expected, predicted, confidence, is_confident, status, image -AutoSize

$reportPath = "data\cache\vision\vision_batch_report.json"
$reportDir = Split-Path $reportPath
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

$report = [PSCustomObject]@{
    summary = $summary
    rows = $rows
}

$report | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $reportPath -Encoding UTF8

Write-Host ""
Write-Host "Report saved to: $reportPath" -ForegroundColor Green
Write-Host "== Vision batch test completed ==" -ForegroundColor Green
