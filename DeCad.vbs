' DeCad desktop launcher: runs start-native.ps1 with no console window (the Desktop / Start Menu icon points here).
Set shell = CreateObject("WScript.Shell")
dir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & dir & "\start-native.ps1""", 0, False
