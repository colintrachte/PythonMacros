Dim sh, base
Set sh = CreateObject("WScript.Shell")
base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' Launch pythonw (no console window) with the venv interpreter
sh.Run """" & base & ".venv\Scripts\pythonw.exe"" """ & base & "app.py""", 0, False

' Give Flask ~2s to bind before opening the browser
WScript.Sleep 2000
sh.Run "http://localhost:5000"
