"""Settings/themes UIA against only the isolated unsigned-QA MSIX identity."""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import time
import winreg

from v070_editor_cases import Driver, Input, Union, Keyboard, Mouse, digest
from citrica.windows import ipc


def inno_startup():
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            value, kind = winreg.QueryValueEx(key, "Citrica")
    except FileNotFoundError:
        return {"present": False}
    return {
        "present": True,
        "kind": kind,
        "value_sha256": hashlib.sha256(str(value).encode("utf-8")).hexdigest(),
    }


def window_bounds(driver):
    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("monitor", wintypes.RECT),
            ("work", wintypes.RECT),
            ("flags", wintypes.DWORD),
        ]

    driver.user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    driver.user.MonitorFromWindow.restype = wintypes.HANDLE
    driver.user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    monitor = driver.user.MonitorFromWindow(driver.hwnd, 2)
    assert monitor and driver.user.GetMonitorInfoW(monitor, ctypes.byref(info))
    rect = wintypes.RECT()
    dwm = ctypes.WinDLL("dwmapi")
    dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
    assert dwm.DwmGetWindowAttribute(driver.hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0
    frame = [rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top]
    work = [info.work.left, info.work.top, info.work.right - info.work.left, info.work.bottom - info.work.top]
    return {
        "frame_physical": frame,
        "work_area_physical": work,
        "fits": rect.left >= info.work.left
        and rect.top >= info.work.top
        and rect.right <= info.work.right
        and rect.bottom <= info.work.bottom,
    }


def buttons_bounds(driver, work):
    result = {}
    x, y, width, height = work
    for name in ("SavePreferences", "SaveAndTestWheel"):
        control = driver.uia("find", AutomationId=name)
        fits = (
            not control["offscreen"]
            and control["x"] >= x
            and control["y"] >= y
            and control["x"] + control["width"] <= x + width
            and control["y"] + control["height"] <= y + height
        )
        assert fits, control
        result[name] = {
            "visible": True,
            "fits_work_area": True,
            "rect": [control["x"], control["y"], control["width"], control["height"]],
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", required=True, type=Path)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--family", required=True)
    parser.add_argument("--uia", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--stage", choices=("all", "reload", "shutdown"), default="all")
    parser.add_argument(
        "--keep-size",
        action="store_true",
        help="Preserve the initial app geometry for the environment-scale150 pass.",
    )
    parser.add_argument(
        "--expected-scale",
        type=float,
        default=1.0,
        help="Check scale from the actual physical UIA width of a fixed158-logical-pixel card.",
    )
    args = parser.parse_args()
    assert args.family == "Emilians.Ctrica.UnsignedQA_p9dw1q8pw0bz6"
    assert os.name == "nt" and not args.state.exists()
    args.state.mkdir(parents=True)
    prefs = Path(os.environ["LOCALAPPDATA"]) / "Packages" / args.family / "LocalState/Citrica/settings.json"
    identity = (args.family + "\0" + str(Path.home())).encode("utf-8")
    pipe = "LOCAL\\citrica-store-" + hashlib.sha256(identity).hexdigest()[:20]
    ipc.server_name = lambda: pipe
    driver = Driver(args.gui, args.uia, args.state)
    driver.pid, driver.case = args.pid, "settings-" + args.stage
    assert driver.image_path(args.pid).resolve() == args.gui.resolve()
    assert driver.process_package_family(args.pid) == args.family
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        driver.user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != args.pid or not driver.user.IsWindowVisible(hwnd):
            return True
        text = ctypes.create_unicode_buffer(driver.user.GetWindowTextLengthW(hwnd) + 1)
        driver.user.GetWindowTextW(hwnd, text, len(text))
        if text.value == "Cítrica · configurações":
            windows.append(hwnd)
        return True

    def locate_settings():
        until = time.monotonic() + 10
        while time.monotonic() < until:
            windows.clear()
            driver.user.EnumWindows(visit, 0)
            if windows:
                assert len(windows) == 1, windows
                driver.hwnd = windows[0]
                return
            time.sleep(0.05)
        raise AssertionError("The owned packaged Settings window did not appear")

    def appearance_tab():
        if not args.keep_size:
            driver.user.SetWindowPos(driver.hwnd, None, 170, 100, 1366, 900, 0x40)
        driver.user.SetForegroundWindow(driver.hwnd)
        tab = driver.find("Personalizar a roda")
        driver.click((tab["x"] + tab["width"] / 2, tab["y"] + tab["height"] / 2))

    def reopen_settings():
        assert ipc.send({"op": "settings"}) == {"ok": True}
        locate_settings()
        appearance_tab()

    assert ipc.send({"op": "settings"}) == {"ok": True}
    locate_settings()
    initial_bounds = window_bounds(driver)
    assert initial_bounds["fits"], initial_bounds
    initial_buttons = buttons_bounds(driver, initial_bounds["work_area_physical"])
    appearance_tab()
    first_card = driver.uia("find", AutomationId="wheel-theme-classic")
    effective_scale = first_card["width"] / 158.0
    assert abs(effective_scale - args.expected_scale) < 0.015, (
        effective_scale,
        args.expected_scale,
        first_card,
    )
    startup_before = inno_startup()
    report = {
        "result": "running",
        "isolated_qa_family": args.family,
        "gui_sha256": digest(args.gui),
        "stage": args.stage,
        "themes": {},
        "screenshots": {},
        "inno_startup_before": startup_before,
        "initial_bounds": initial_bounds,
        "initial_buttons": initial_buttons,
        "actual_process_package_family_verified": args.family,
        "native_os_window_dpi": driver.user.GetDpiForWindow(driver.hwnd),
        "expected_qt_scale": args.expected_scale,
        "observed_qt_scale_from_fixed_card_physical_width": effective_scale,
        "fixed_card_logical_width": 158,
        "first_card_physical_size": [first_card["width"], first_card["height"]],
        "default_size_preserved": args.keep_size,
    }

    def status_until(predicate, timeout=10):
        until, current = time.monotonic() + timeout, None
        while time.monotonic() < until:
            current = ipc.send({"op": "status"}, timeout=250)
            if current and predicate(current):
                return current
            time.sleep(0.08)
        raise AssertionError(current)

    try:
        themes = (
            ["classic", "glass", "graphite", "contrast", "watercolor"]
            if args.stage == "all"
            else ["watercolor"]
        )
        if args.stage == "shutdown":
            themes = []
        for theme in themes:
            control = driver.uia("find", AutomationId="wheel-theme-" + theme)
            scroll_steps = 0
            while control["offscreen"] and scroll_steps < 6:
                frame = window_bounds(driver)["frame_physical"]
                driver.move((frame[0] + frame[2] / 2, frame[1] + frame[3] / 2))
                delta = 360 if theme in {"classic", "glass", "watercolor"} else -360
                driver.inject(Input(0, Union(mouse=Mouse(0, 0, delta, 0x0800, 0, 0))))
                time.sleep(0.2)
                control = driver.uia("find", AutomationId="wheel-theme-" + theme)
                scroll_steps += 1
            assert control["enabled"] and not control["offscreen"]
            if args.stage == "all":
                driver.click((control["x"] + control["width"] / 2, control["y"] + control["height"] / 2))
                driver.uia("invoke", AutomationId="SavePreferences")
            else:
                assert control.get("toggle") == "On" or control.get("selected") is True, control
            saved_until = time.monotonic() + 10
            while True:
                stored = json.loads(prefs.read_text(encoding="utf-8-sig"))
                if stored["wheel_theme"] == theme:
                    break
                assert time.monotonic() < saved_until, stored
                time.sleep(0.05)
            status_until(lambda item: not item["visible"])
            driver.uia("invoke", AutomationId="SaveAndTestWheel")
            status_until(lambda item: item["visible"] and not item["paths"])
            hidden_until = time.monotonic() + 10
            while driver.user.IsWindowVisible(driver.hwnd) and time.monotonic() < hidden_until:
                time.sleep(0.02)
            assert not driver.user.IsWindowVisible(driver.hwnd), "Real Save-and-test must hide Settings"
            assert ipc.send({"op": "show", "paths": [str(args.file)]}) == {"ok": True}
            wheel = status_until(
                lambda item: item["visible"] and item["paths"] == [str(args.file)] and bool(item["items"])
            )
            assert not wheel["elevated"]
            time.sleep(0.35)
            report["screenshots"][theme] = driver.screenshot(
                "windows-wheel-" + theme + "-" + args.stage, activate=False
            )
            driver.inject(Input(1, Union(keyboard=Keyboard(0x1B, 0, 0, 0, 0))))
            time.sleep(0.12)
            driver.inject(Input(1, Union(keyboard=Keyboard(0x1B, 0, 2, 0, 0))))
            cleared = status_until(lambda item: not item["visible"])
            assert not cleared["paths"] and not cleared["cachedSelection"]
            reopen_settings()
            report["themes"][theme] = {
                "saved": True,
                "actual_wheel_visible": True,
                "escape_cleared": True,
                "reloaded_process": args.stage == "reload",
                "scroll_steps": scroll_steps,
            }
        report["screenshots"]["settings"] = driver.screenshot("windows-settings-five-themes-" + args.stage)
        report["final_buttons"] = buttons_bounds(driver, initial_bounds["work_area_physical"])
        if args.stage == "shutdown":
            handle = driver.kernel.OpenProcess(0x101000, False, args.pid)
            assert handle, "Cannot retain the owned resident handle for exact exit status"
            try:
                driver.uia("invoke", AutomationId="SaveAndTestWheel")
                status_until(lambda item: item["visible"] and not item["paths"])
                hidden_until = time.monotonic() + 10
                while driver.user.IsWindowVisible(driver.hwnd) and time.monotonic() < hidden_until:
                    time.sleep(0.02)
                assert not driver.user.IsWindowVisible(driver.hwnd), "Save-and-test must hide Settings"
                report["save_and_test_hidden_settings_verified"] = True
                try:
                    ipc.send({"op": "quit"}, timeout=500)
                except RuntimeError:
                    pass  # The server may close before acknowledging the one quit.
                driver.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                driver.kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                assert driver.kernel.WaitForSingleObject(handle, 30000) == 0, (
                    "Resident quit exceeded30seconds"
                )
                code = wintypes.DWORD()
                assert driver.kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                report["actual_native_resident_exit_code"] = code.value
                assert code.value == 0, ("Actual resident failed normal quit", code.value)
            finally:
                driver.kernel.CloseHandle(handle)
        assert inno_startup() == startup_before
        report["inno_startup_not_touched"] = True
        report["result"] = "passed"
    except Exception as error:
        report["result"], report["error"] = "failed", str(error)
        try:
            reopen_settings()
            report["failure_controls"] = driver.uia()
            report["failure_screenshot"] = driver.screenshot("settings-failure")
        except Exception as diagnostic:
            report["diagnostic_error"] = str(diagnostic)
        raise
    finally:
        report["inno_startup_after"] = inno_startup()
        (args.state / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps({"result": report["result"], "report": str(args.state / "report.json")}))


if __name__ == "__main__":
    main()
