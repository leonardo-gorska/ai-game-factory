$files = @(
    "c:\Users\Gorska\Desktop\ai-game-factory\dashboard\package.json",
    "c:\Users\Gorska\Desktop\ai-game-factory\dashboard\package-lock.json"
)
foreach ($f in $files) {
    $bytes = [System.IO.File]::ReadAllBytes($f)
    if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        $newBytes = $bytes[3..($bytes.Length - 1)]
        [System.IO.File]::WriteAllBytes($f, [byte[]]$newBytes)
        Write-Output ("Fixed BOM in: " + $f)
    }
    else {
        Write-Output ("No BOM in: " + $f)
    }
}
