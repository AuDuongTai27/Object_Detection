$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop "FabLab AI Dobot Studio.lnk"
$targetBat = "C:\Users\PC\OneDrive\Desktop\EIU\FabLabExecutive\ObjectDetection\run_web_studio.bat"
$workDir = "C:\Users\PC\OneDrive\Desktop\EIU\FabLabExecutive\ObjectDetection"
$iconPath = "C:\Users\PC\OneDrive\Desktop\EIU\FabLabExecutive\ObjectDetection\fablab_icon.ico"

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($lnkPath)
$shortcut.TargetPath = $targetBat
$shortcut.WorkingDirectory = $workDir
$shortcut.Description = "FabLab AI & Dobot Studio (1-Click Launcher)"
$shortcut.IconLocation = "$iconPath, 0"
$shortcut.Save()

Write-Host "SUCCESS: Shortcut updated with FabLab icon at $lnkPath"
