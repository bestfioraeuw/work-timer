Set sh = CreateObject("WScript.Shell")
root = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
extra = ""
If WScript.Arguments.Count > 0 Then extra = " " & WScript.Arguments(0)
sh.Run """C:\Program Files\Python312\pythonw.exe"" """ & root & "\app.py""" & extra, 0, False
