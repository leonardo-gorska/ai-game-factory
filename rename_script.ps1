$root = "c:\Users\Gorska\Desktop\ai-game-factory"
$extensions = @("*.tsx","*.ts","*.py","*.json","*.md","*.env","*.js","*.html")
$excludeDirs = @("node_modules","venv",".next","__pycache__",".git")

Get-ChildItem -Path $root -Recurse -Include $extensions -File | Where-Object {
    $path = $_.FullName
    $skip = $false
    foreach ($d in $excludeDirs) {
        if ($path -match [regex]::Escape($d)) { $skip = $true; break }
    }
    -not $skip
} | ForEach-Object {
    $content = Get-Content $_.FullName -Raw -Encoding UTF8
    if ($content -match "AI Game Factory|AI GAME FACTORY|ai-game-factory-dashboard") {
        $newContent = $content -replace "AI GAME FACTORY", "GORVAX GAME FACTORY"
        $newContent = $newContent -replace "AI Game Factory", "GorvaX Game Factory"
        $newContent = $newContent -replace "ai-game-factory-dashboard", "gorvax-game-factory-dashboard"
        Set-Content $_.FullName -Value $newContent -NoNewline -Encoding UTF8
        Write-Output ("Updated: " + $_.FullName)
    }
}
Write-Output "Done!"
