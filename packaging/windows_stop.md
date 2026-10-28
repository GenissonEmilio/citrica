# Standalone installer stop helper

`windows_stop.cpp` is a console-only WinAPI helper for the **new** setup to carry.
It does not load Python, Qt, .NET, the installed CLI or external MSVC runtime DLLs.
MSVC builds it with `/MT`; its system dependencies are Windows Kernel32, BCrypt
and PathCch (Windows 10+).

Build on the existing Windows 2022 toolchain:

```powershell
python packaging/windows_stop.py --output build/windows-package/citrica-stop.exe
python -m pytest tests/test_windows_stop_helper.py -q
```

The native tests need that executable, or `CITRICA_STOP_HELPER` pointing to it.
They create their own copied Python executable named `Citrica.exe` and a Qt
**QCoreApplication** named-pipe fixture: no application UI, Explorer input or
existing Cítrica session is controlled. They check Unicode/root home hashing,
Qt's actual pipe name, graceful exit, acknowledgement racing process exit,
missing replies, acknowledgement without exit and another installation's
isolation. Linux skips these native cases explicitly.

## Installer integration

1. Build the helper before compiling Inno Setup; include it in the publisher's
   own signing scope when signing is enabled.
2. Place this newly built file first in the **new**
   setup payload, then call `ExtractTemporaryFile('citrica-stop.exe')` in
   `PrepareToInstall`.
3. Execute **`{tmp}\citrica-stop.exe --install-dir "{app}"`**, hidden, with an
   explicitly quoted installation directory. Capture its stderr in the setup
   log. On nonzero exit, abort the upgrade and ask the user to close the tray
   application. Do not invoke `{app}\citrica-cli.exe` from the old installation.
4. The installed uninstaller uses the same independent helper before file removal,
   aborting if it cannot confirm process exit. The old RunOnceId is retained to
   supersede previously installed CLI-based stop entries.

The helper's total default budget is 15 seconds, including the quit request and
process waits; the optional `--timeout-ms` accepts 100–15000 milliseconds for
controlled tests. Named-pipe connection waits never use Windows' zero/default
wait; each overlapped operation uses the remaining absolute deadline. Pipe I/O
gets at most five seconds, leaving the rest for process termination. No
`TerminateProcess`, shell execution or message-box API is used.

It identifies only `Citrica.exe` processes whose canonical executable path is
`{app}\Citrica.exe`. With no matching process, it returns success without
contacting the user-wide pipe. Before sending `{"op":"quit"}\n`, it verifies
that the pipe server PID also belongs to that executable path. The process
actually exiting is authoritative: losing a final pipe acknowledgement during
shutdown is acceptable, while receiving `{"ok":true}` without exit is not.
Access errors, a live unresponsive target or any leftover matching process fail
with stderr and exit code 1. It never kills an application process.

The pipe is `\\.\pipe\citrica-` followed by the first 20 lowercase hex digits
of SHA-256 of the UTF-8 user profile spelling, matching the Python desktop
protocol. Profile case is preserved and trailing separators are removed while
preserving drive/UNC roots. Executable-path comparison separately resolves
junctions/final paths and compares ordinally without case.

Qt 6.12 confirms the `\\.\pipe\` prefix and byte/overlapped mode in
[qlocalserver_win.cpp](https://github.com/qt/qtbase/blob/v6.12.0/src/network/socket/qlocalserver_win.cpp#L197).
The caller PID is verified through
[GetNamedPipeServerProcessId](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeserverprocessid).
A cancelled overlapped buffer is retained until helper process exit if cancellation
has not yet completed, as required by
[CancelIoEx](https://learn.microsoft.com/en-us/windows/win32/api/ioapiset/nf-ioapiset-cancelioex).

The helper compiled on MSVC 2022, passed 19 Windows tests and live upgrades
from the published 0.5.0 and earlier 0.6.0 candidate. Missing-helper uninstall
fails before removing files or registration. See docs/VALIDACAO-0.6.0.md for
exact package hashes and VM receipts. No public signing identity has been provisioned.
