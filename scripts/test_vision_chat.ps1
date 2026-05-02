param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$ImagePath = "",
    [string]$UserId = "vision_chat_u001",
    [string]$Username = "vision_chat_user",
    [string]$Prompt = ""
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

if ([string]::IsNullOrWhiteSpace($ImagePath)) {
    throw "Please provide -ImagePath."
}

if (!(Test-Path -LiteralPath $ImagePath)) {
    throw "Image file not found: $ImagePath"
}

if ([string]::IsNullOrWhiteSpace($Prompt)) {
    $Prompt = [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String("6K+35L2g55yL55yL6L+Z5byg5Zu+77yM5ZKM5oiR6IGK6IGK5Zu+54mH6YeM55qE5YaF5a6544CC")
    )
}

Add-Type -AssemblyName System.Net.Http

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

function Invoke-VisionChat {
    param(
        [string]$Url,
        [string]$ImagePath,
        [string]$UserId,
        [string]$Username,
        [string]$Prompt
    )

    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromSeconds(240)

    $form = New-Object System.Net.Http.MultipartFormDataContent
    $fileStream = $null

    try {
        $form.Add((New-Object System.Net.Http.StringContent($UserId)), "user_id")
        $form.Add((New-Object System.Net.Http.StringContent($Username)), "username")
        $form.Add((New-Object System.Net.Http.StringContent($Prompt)), "prompt")

        $resolvedPath = (Resolve-Path -LiteralPath $ImagePath).Path
        $fileStream = [System.IO.File]::OpenRead($resolvedPath)

        $fileContent = New-Object System.Net.Http.StreamContent($fileStream)
        $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse((Get-MimeType $resolvedPath))

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

Write-Host ""
Write-Host "== Vision Chat Test ==" -ForegroundColor Cyan

$result = Invoke-VisionChat `
    -Url "$BaseUrl/vision/chat" `
    -ImagePath $ImagePath `
    -UserId $UserId `
    -Username $Username `
    -Prompt $Prompt

$result | ConvertTo-Json -Depth 60

Write-Host ""
Write-Host "== Key Result ==" -ForegroundColor Yellow
Write-Host "reply      :" $result.reply
Write-Host "emotion    :" $result.emotion
Write-Host "motion     :" $result.motion
Write-Host "expression :" $result.expression
Write-Host "vision confident:" $result.vision.result.is_confident
Write-Host "vision confidence:" $result.vision.result.confidence
$result.vision.result.recognized_characters | ConvertTo-Json -Depth 20

Write-Host ""
Write-Host "== Vision chat test completed ==" -ForegroundColor Green
