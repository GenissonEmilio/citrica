"""Capture the actual QA Settings in a desktop region, with no image edits."""

import argparse
import ctypes
import json
import time
from pathlib import Path
from ctypes import wintypes
from PIL import ImageGrab
from v070_editor_cases import Driver, digest

p = argparse.ArgumentParser()
p.add_argument("--gui", type=Path, required=True)
p.add_argument("--pid", type=int, required=True)
p.add_argument("--state", type=Path, required=True)
a = p.parse_args()
assert not a.state.exists()
a.state.mkdir()
d = Driver(a.gui, Path(__file__).with_name("editor_uia.ps1"), a.state)
d.pid = a.pid
d.case = "settings-store-region"
assert d.process_package_family(a.pid) == "Emilians.Ctrica.UnsignedQA_p9dw1q8pw0bz6"
assert d.image_path(a.pid).resolve() == a.gui.resolve()
windows = []
cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


@cb
def visit(hwnd, _):
    pid = wintypes.DWORD()
    d.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == a.pid and d.user.IsWindowVisible(hwnd):
        title = ctypes.create_unicode_buffer(256)
        d.user.GetWindowTextW(hwnd, title, 256)
        if title.value == "Cítrica · configurações":
            windows.append(hwnd)
    return True


d.user.EnumWindows(visit, 0)
assert len(windows) == 1
d.hwnd = windows[0]
d.user.SetWindowPos(d.hwnd, None, 15, 15, 1400, 870, 0x40)
d.user.SetForegroundWindow(d.hwnd)
t = d.find("Personalizar a roda")
d.click((t["x"] + t["width"] / 2, t["y"] + t["height"] / 2))
time.sleep(0.4)
for theme in ("classic", "glass", "graphite", "contrast", "watercolor"):
    control = d.uia("find", AutomationId="wheel-theme-" + theme)
    assert not control["offscreen"]
    assert (
        0 <= control["x"]
        and control["x"] + control["width"] < 1440
        and control["y"] + control["height"] < 900
    )
for button in ("SavePreferences", "SaveAndTestWheel"):
    control = d.uia("find", AutomationId=button)
    assert not control["offscreen"] and control["y"] + control["height"] < 900
out = a.state / "windows-settings-store-region.png"
ImageGrab.grab(bbox=(0, 0, 1440, 900), all_screens=True).save(out)
(a.state / "report.json").write_text(
    json.dumps(
        {
            "result": "passed",
            "native_capture_region": [0, 0, 1440, 900],
            "image_manipulation": False,
            "all_five_cards_and_both_buttons_inside": True,
            "sha256": digest(out),
        }
    ),
    encoding="utf-8",
)
print("Native Settings region captured")
