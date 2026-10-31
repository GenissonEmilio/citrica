"""Normal-integrity exact QA package launch/control, independent of the app."""

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from v070_editor_cases import Driver, digest
from citrica.windows import ipc

p = argparse.ArgumentParser()
p.add_argument("--gui", type=Path, required=True)
p.add_argument("--state", type=Path, required=True)
p.add_argument("--op", choices=("launch", "quit"), default="launch")
p.add_argument("--pid", type=int)
p.add_argument("--scale", default="1")
a = p.parse_args()
assert not a.state.exists()
a.state.mkdir()
family = "Emilians.Ctrica.UnsignedQA_p9dw1q8pw0bz6"
assert digest(a.gui) == "5cf40dd9550b41becfe6f902b4259a64e777d2a61370d5eb775e9942c8d89688"
identity = (family + "\0" + str(Path.home())).encode("utf-8")
ipc.server_name = lambda: "LOCAL\\citrica-store-" + hashlib.sha256(identity).hexdigest()[:20]
driver = Driver(a.gui, Path(__file__).with_name("editor_uia.ps1"), a.state)
report = {"result": "running", "operation": a.op, "gui_sha256": digest(a.gui)}
try:
    if a.op == "launch":
        assert ipc.send({"op": "status"}, timeout=150) is None, "Refuse duplicate QA resident"
        env = dict(os.environ)
        env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        env["QT_SCALE_FACTOR"] = a.scale
        for key in (
            "PYTHONPATH",
            "PYTHONHOME",
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QT_MEDIA_BACKEND",
            "QT_QPA_PLATFORM",
            "CITRICA_OFFICE_ENGINE",
            "CITRICA_WINDOWS_ENGINES",
            "CITRICA_TOOL_DIR",
            "CITRICA_OCR_DIR",
        ):
            env.pop(key, None)
        log = (a.state / "resident.log").open("w", encoding="utf-8")
        process = subprocess.Popen([str(a.gui), "--settings"], env=env, stdout=log, stderr=subprocess.STDOUT)
        a.pid = process.pid
        report.update(actual_gui_pid=a.pid, requested_environment_scale=a.scale)
        assert driver.process_package_family(a.pid) == family
        report["actual_process_package_family"] = family
        until = time.monotonic() + 30
        while time.monotonic() < until:
            status = ipc.send({"op": "status"}, timeout=250)
            if status and status["hotkey_active"]:
                break
            if process.poll() is not None:
                raise AssertionError(("Packaged GUI exited before ready", process.returncode))
            time.sleep(0.1)
        assert (
            status and status["version"] == "0.7.0" and not status["elevated"] and status["hotkey_active"]
        ), status
        report.update(actual_normal_integrity=True, actual_hotkey_active=True, result="ready")
    else:
        assert a.pid and driver.image_path(a.pid).resolve() == a.gui.resolve()
        assert driver.process_package_family(a.pid) == family
        handle = driver.kernel.OpenProcess(0x101000, False, a.pid)
        assert handle
        try:
            status = ipc.send({"op": "status"})
            assert status and not status["busy"] and not status["elevated"]
            try:
                ipc.send({"op": "quit"}, timeout=500)
            except RuntimeError:
                pass
            driver.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            driver.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            assert driver.kernel.WaitForSingleObject(handle, 30000) == 0
            code = wintypes.DWORD()
            assert driver.kernel.GetExitCodeProcess(handle, ctypes.byref(code))
            report["actual_native_resident_exit_code"] = code.value
            assert code.value == 0
            report.update(result="passed", actual_process_package_family=family)
        finally:
            driver.kernel.CloseHandle(handle)
except Exception as error:
    report.update(result="failed", error=str(error))
    raise
finally:
    (a.state / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
