$project = $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create .venv and install requirements.txt before making the shortcut.'
}

$shortcutPath = Join-Path $project 'SpeakRAG.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $python
$shortcut.Arguments = '"' + (Join-Path $project 'desktop_app.py') + '"'
$shortcut.WorkingDirectory = $project
$shortcut.IconLocation = Join-Path $project 'docs\SpeakRAG.ico'
$shortcut.Description = 'Launch the SpeakRAG speech lab'
$shortcut.Save()
Write-Host "Created $shortcutPath"
