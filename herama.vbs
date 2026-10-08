' Starts herama without any console window: the app starts its own backend and stops it when you close the window.
' Run START.bat once first (it installs everything); after that you can double-click this file or a shortcut to it.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root & "\frontend"
sh.Run "cmd /c npm run dev > ""..\herama-run.log"" 2>&1", 0, False
