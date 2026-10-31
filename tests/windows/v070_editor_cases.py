"""Exercise an actual frozen Windows GUI on the dedicated QA desktop.

No product source imports, GUI hooks, or IPC-only substitutes for editor input.
All fixtures/exports belong to the supplied new state directory.
"""

from __future__ import annotations

import argparse
import array
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import wave

from PIL import Image, ImageGrab

# Load the independent oracle's C++ runtime locally, as the existing Explorer
# controller does. The frozen child gets a clean PATH and its own Qt plugins.
if os.name == "nt":
    pass
import pymupdf


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, *, timeout=40):
    result = subprocess.run(
        list(map(str, command)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"QA command failed ({result.returncode}): {result.stderr[-1500:]}")
    return result.stdout


def engine(gui, name):
    for root in (gui.parent / "_internal", gui.parent):
        path = root / "tools/ffmpeg/bin" / (name + ".exe")
        if path.is_file():
            return path
    raise FileNotFoundError("The exact frozen candidate must include its FFmpeg engines.")


class Mouse(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra", ctypes.c_size_t),
    ]


class Keyboard(ctypes.Structure):
    _fields_ = [
        ("vk", wintypes.WORD),
        ("scan", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra", ctypes.c_size_t),
    ]


class Union(ctypes.Union):
    _fields_ = [("mouse", Mouse), ("keyboard", Keyboard)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", Union)]


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("size", wintypes.DWORD),
        ("usage", wintypes.DWORD),
        ("pid", wintypes.DWORD),
        ("heap", ctypes.c_size_t),
        ("module", wintypes.DWORD),
        ("threads", wintypes.DWORD),
        ("parent_pid", wintypes.DWORD),
        ("priority", wintypes.LONG),
        ("flags", wintypes.DWORD),
        ("name", wintypes.WCHAR * 260),
    ]


class Driver:
    def __init__(self, gui, helper, state):
        self.gui, self.helper, self.state = gui, helper, state
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        self.user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND
        self.user.WindowFromPhysicalPoint.argtypes = [wintypes.POINT]
        self.user.WindowFromPhysicalPoint.restype = wintypes.HWND
        self.user.SetPhysicalCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self.user.SetPhysicalCursorPos.restype = wintypes.BOOL
        self.user.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self.user.GetDpiForWindow.argtypes = [wintypes.HWND]
        self.user.GetDpiForWindow.restype = wintypes.UINT
        self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.user.SendInput.restype = wintypes.UINT
        self.user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        self.process = self.log = self.hwnd = self.pid = None
        self.sequence = 0

    def image_path(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            value = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(value))
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, value, ctypes.byref(size)):
                return None
            return Path(value.value)
        finally:
            self.kernel.CloseHandle(handle)

    def process_package_family(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        assert handle, "Cannot query the owned GUI package identity"
        try:
            function = self.kernel.GetPackageFamilyName
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
            function.restype = wintypes.LONG
            size = wintypes.UINT(0)
            status = function(handle, ctypes.byref(size), None)
            assert status == 122 and 1 < size.value <= 256, ("Expected packaged GUI, status", status)
            value = ctypes.create_unicode_buffer(size.value)
            assert function(handle, ctypes.byref(size), value) == 0
            return value.value
        finally:
            self.kernel.CloseHandle(handle)

    def preview_children(self):
        self.kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        self.kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        snapshot = self.kernel.CreateToolhelp32Snapshot(2, 0)
        assert snapshot and snapshot != ctypes.c_void_p(-1).value
        try:
            entry = ProcessEntry()
            entry.size = ctypes.sizeof(entry)
            rows = []
            current = self.kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while current:
                if entry.parent_pid == self.pid and entry.name.lower() in {"ffmpeg.exe", "ffprobe.exe"}:
                    rows.append({"pid": int(entry.pid), "name": entry.name})
                current = self.kernel.Process32NextW(snapshot, ctypes.byref(entry))
            return rows
        finally:
            self.kernel.CloseHandle(snapshot)

    def open(self, tool, path, title, *, wait_controls=True):
        assert self.process is None
        self.sequence += 1
        self.case = f"{self.sequence:02}-" + tool + "-" + path.suffix.lstrip(".")
        self.log = (self.state / (self.case + ".log")).open("w", encoding="utf-8")
        environment = dict(os.environ)
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
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
            environment.pop(key, None)
        self.process = subprocess.Popen(
            [str(self.gui), "--tool", tool, str(path)],
            stdout=self.log,
            stderr=subprocess.STDOUT,
            env=environment,
        )
        wanted = "Cítrica · " + title
        until = time.monotonic() + 30
        while time.monotonic() < until:
            found = []
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            @callback_type
            def visit(hwnd, _):
                if not self.user.IsWindowVisible(hwnd):
                    return True
                text = ctypes.create_unicode_buffer(self.user.GetWindowTextLengthW(hwnd) + 1)
                self.user.GetWindowTextW(hwnd, text, len(text))
                if text.value == wanted:
                    pid = wintypes.DWORD()
                    self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    candidate = self.image_path(pid.value)
                    if (
                        candidate
                        and candidate.resolve() == self.gui.resolve()
                        and pid.value == self.process.pid
                    ):
                        found.append((hwnd, pid.value))
                return True

            self.user.EnumWindows(visit, 0)
            if found:
                assert len(found) == 1, "Only one owned editor may exist for this case."
                self.hwnd, self.pid = found[0]
                assert self.pid == self.process.pid
                self.appeared_at = time.monotonic()
                if not wait_controls:
                    return
                self.user.SetWindowPos(self.hwnd, None, 170, 100, 1366, 900, 0x40)
                self.user.SetForegroundWindow(self.hwnd)
                time.sleep(0.4)
                return self.wait(
                    lambda rows: any(r["automation_id"].rsplit(".", 1)[-1] == "EditorPrimary" for r in rows)
                )
            if self.process.poll() is not None:
                raise RuntimeError("Frozen editor exited before presenting its window.")
            time.sleep(0.1)
        raise TimeoutError("Frozen editor window did not appear.")

    def close_while_preview_prepares(self, *, require_observed_worker=False):
        observed = self.preview_children()
        until = time.monotonic() + 2
        while require_observed_worker and not observed and time.monotonic() < until:
            time.sleep(0.005)
            observed = self.preview_children()
        assert observed or not require_observed_worker, (
            "A real preview subprocess must be observed for this case"
        )
        elapsed = time.monotonic() - self.appeared_at
        assert self.user.PostMessageW(self.hwnd, 0x10, 0, 0), (
            "Cannot send normal WM_CLOSE to the owned editor"
        )
        code = self.process.wait(timeout=30)
        self.log.close()
        self.process = self.log = self.hwnd = self.pid = None
        assert code == 0, f"Immediate media close returned {code}"
        return {
            "exit_code": code,
            "seconds_from_window_appearance_to_close": round(elapsed, 4),
            "owned_preview_subprocesses_observed": observed,
        }

    def uia(self, operation="dump", **filters):
        command = [
            self.powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            self.helper,
            "-GuiProcessId",
            str(self.pid),
            "-Operation",
            operation,
        ]
        for key, value in filters.items():
            command += ["-" + key, str(value)]
        return json.loads(run(command, timeout=20))

    def wait(self, predicate, timeout=25):
        until, rows = time.monotonic() + timeout, []
        while time.monotonic() < until:
            rows = self.uia()
            if predicate(rows):
                return rows
            time.sleep(0.15)
        raise AssertionError({"case": self.case, "controls": rows})

    def find(self, name):
        return self.uia("find", Name=name)

    def value(self, name, value):
        return self.uia(
            "setvalue",
            Name=name,
            Value=value,
            ControlType="Slider" if "controle deslizante" in name else "Spinner",
        )

    def invoke(self, name):
        return self.uia("invoke", Name=name)

    def inject(self, data):
        assert self.user.SendInput(1, ctypes.byref(data), ctypes.sizeof(Input)) == 1

    def button(self, down):
        self.inject(Input(0, Union(mouse=Mouse(0, 0, 0, 2 if down else 4, 0, 0))))

    def key(self, code):
        self.inject(Input(1, Union(keyboard=Keyboard(code, 0, 0, 0, 0))))
        self.inject(Input(1, Union(keyboard=Keyboard(code, 0, 2, 0, 0))))

    def move(self, point):
        assert self.user.SetPhysicalCursorPos(round(point[0]), round(point[1]))

    def click(self, point):
        self.move(point)
        under = self.user.WindowFromPhysicalPoint(wintypes.POINT(round(point[0]), round(point[1])))
        assert self.user.GetAncestor(under, 2) == self.hwnd, "Owned editor is covered."
        self.button(True)
        time.sleep(0.05)
        self.button(False)
        time.sleep(0.15)

    def drag(self, start, end):
        self.move(start)
        under = self.user.WindowFromPhysicalPoint(wintypes.POINT(round(start[0]), round(start[1])))
        assert self.user.GetAncestor(under, 2) == self.hwnd, "Owned editor is covered."
        self.button(True)
        try:
            for index in range(1, 16):
                self.move(tuple(a + (b - a) * index / 15 for a, b in zip(start, end)))
                time.sleep(0.02)
        finally:
            self.button(False)
        time.sleep(0.3)

    def screenshot(self, name, *, activate=True):
        # Full dedicated guest desktop, actual frozen GUI; no console is opened.
        if activate:
            self.user.SetForegroundWindow(self.hwnd)
        time.sleep(0.3)
        path = self.state / (name + ".png")
        ImageGrab.grab(all_screens=True).save(path)
        return {"path": str(path), "sha256": digest(path)}

    def save(self, source):
        before = set(source.parent.iterdir())
        self.invoke("Salvar cópia")
        self.wait(lambda rows: any("cópia(s) salva(s)" in r["name"] for r in rows), timeout=90)
        outputs = [p for p in source.parent.iterdir() if p not in before and p.is_file()]
        assert len(outputs) == 1, outputs
        return outputs[0]

    def close(self):
        if self.process is None:
            return
        self.invoke("Fechar")
        code = self.process.wait(timeout=30)
        self.log.close()
        self.process = self.log = self.hwnd = self.pid = None
        assert code == 0, f"Normal editor close returned {code}; lifecycle regression."


def controls_map(rows):
    return {row["name"]: row for row in rows}


def playback_seconds(rows):
    labels = [r["name"] for r in rows if re.match(r"\d\d:\d\d:\d\d", r["name"])]
    assert labels, "The actual player must expose its current playback time."
    hours, minutes, seconds = labels[0].split(" / ")[0].split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def play_and_pause(driver, start, end):
    button = driver.find("▶ Reproduzir")
    point = (button["x"] + button["width"] / 2, button["y"] + button["height"] / 2)
    # Physical transport clicks keep a short real clip from finishing while
    # another PowerShell/UIA observer starts on the low-memory QA VM.
    driver.click(point)
    time.sleep(0.45)
    driver.click(point)
    rows = driver.wait(lambda items: any(r["name"] == "▶ Reproduzir" for r in items))
    position = playback_seconds(rows)
    assert start + 0.05 < position < end, (position, start, end)
    return position


def duration(ffprobe, path):
    return float(
        json.loads(run([ffprobe, "-v", "error", "-show_format", "-of", "json", path]))["format"]["duration"]
    )


def tone_energy(path, frequency, second):
    with wave.open(str(path), "rb") as stream:
        assert stream.getsampwidth() == 2
        rate, channels = stream.getframerate(), stream.getnchannels()
        stream.setpos(round(second * rate))
        pcm = array.array("h", stream.readframes(4096))[::channels]
    return abs(
        sum(
            value
            * complex(
                math.cos(2 * math.pi * frequency * i / rate), math.sin(2 * math.pi * frequency * i / rate)
            )
            for i, value in enumerate(pcm)
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", type=Path, required=True)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--uia", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--only", choices=("all", "pdf", "close-media", "pdf-close"), default="all")
    args = parser.parse_args()
    assert os.name == "nt" and not args.state.exists(), "Use a new dedicated Windows QA state directory."
    args.state.mkdir(parents=True)
    ffmpeg, ffprobe = engine(args.gui, "ffmpeg"), engine(args.gui, "ffprobe")
    fixture_dir = args.state / "fixtures"
    fixture_dir.mkdir()
    photo = fixture_dir / "Astronauta.png"
    shutil.copy2(args.photo, photo)
    gray = fixture_dir / "Cinza.png"
    Image.new("RGB", (160, 120), (80, 80, 80)).save(gray)
    video = fixture_dir / "Movimento.mp4"
    run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-loop",
            "1",
            "-i",
            photo,
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "6",
            "-vf",
            "scale=640:640,zoompan=z='1+on*0.002':x='iw/2-iw/(zoom*2)':y='ih/2-ih/(zoom*2)':d=1:s=640x360:fps=12",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            video,
        ],
        timeout=60,
    )
    audio = fixture_dir / "Tom.wav"
    run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=6",
            audio,
        ]
    )
    pdf = fixture_dir / "Páginas.pdf"
    with pymupdf.open() as document:
        for page in range(1, 4):
            document.new_page().insert_text((60, 100), f"CITRICA PAGE {page}", fontsize=28)
        document.save(pdf)
    originals = {str(p): digest(p) for p in (photo, gray, video, audio, pdf)}
    report = {
        "result": "running",
        "actual_frozen_gui": str(args.gui),
        "gui_sha256": digest(args.gui),
        "product_source_imported": False,
        "cases": {},
        "screenshots": {},
        "originals": originals,
    }
    driver = Driver(args.gui, args.uia, args.state)
    try:
        if args.only == "all":
            driver.open("crop", photo, "Recortar")
            prefix = "Área selecionada · pixels · "
            for key, value in zip(("X", "Y", "Largura", "Altura"), (20, 30, 240, 160)):
                driver.value(prefix + key, value)
            canvas = driver.find("Prévia da imagem e seleção em pixels")
            sw, sh = Image.open(photo).size
            dpi = driver.user.GetDpiForWindow(driver.hwnd) / 96
            scale = min((canvas["width"] - 24 * dpi) / sw, (canvas["height"] - 24 * dpi) / sh)
            ox = canvas["x"] + (canvas["width"] - sw * scale) / 2
            oy = canvas["y"] + (canvas["height"] - sh * scale) / 2
            driver.drag((ox + 260 * scale, oy + 190 * scale), (ox + 300 * scale, oy + 220 * scale))
            selected = [
                round(float(str(driver.find(prefix + key)["value"]).replace(",", ".")))
                for key in ("X", "Y", "Largura", "Altura")
            ]
            assert 275 <= selected[2] <= 285 and 185 <= selected[3] <= 195, selected
            report["screenshots"]["image"] = driver.screenshot("windows-editor-image")
            output = driver.save(photo)
            with Image.open(output) as result, Image.open(photo) as original:
                assert result.size == tuple(selected[2:])
                oracle = original.crop(
                    (selected[0], selected[1], selected[0] + selected[2], selected[1] + selected[3])
                )
                assert result.convert("RGB").tobytes() == oracle.convert("RGB").tobytes()
            driver.close()
            report["cases"]["crop_actual_handle_export_normal_close"] = {
                "selection": selected,
                "output": str(output),
            }

            driver.open("adjust", gray, "Ajustar foto")
            driver.value("Brilho · controle deslizante", 200)
            for name in ("Contraste", "Saturação", "Nitidez"):
                driver.value(name, 1)
            driver.uia("toggle", Name="Ver original")
            driver.uia("toggle", Name="Ver original")
            output = driver.save(gray)
            with Image.open(output) as result:
                assert result.convert("RGB").getpixel((40, 40)) == (160, 160, 160)
            driver.close()
            report["cases"]["brightness_slider_comparison_export_normal_close"] = {"output": str(output)}

            driver.open("trim", video, "Cortar tempo")
            timeline_name = "Linha do tempo; arraste as alças amarelas para selecionar o trecho"
            driver.wait(lambda rows: any(r["name"] == timeline_name and r["enabled"] for r in rows))
            driver.value("Início", 1)
            driver.value("Duração", 2)
            timeline = driver.find(timeline_name)
            left, width = timeline["x"] + 14 * dpi, timeline["width"] - 28 * dpi
            y = timeline["y"] + 45 * dpi
            driver.drag((left + width * 3 / 6, y), (left + width * 3.5 / 6, y))
            requested_duration = float(
                str(driver.uia("find", Name="Duração", ControlType="Spinner")["value"])
                .replace(",", ".")
                .split()[0]
            )
            assert 2.4 <= requested_duration <= 2.6
            played_position = play_and_pause(driver, 1, 1 + requested_duration)
            driver.click((left + width * 2.5 / 6, y))
            seek_rows = driver.wait(lambda rows: abs(playback_seconds(rows) - 2.5) < 0.16)
            seek_position = playback_seconds(seek_rows)
            report["screenshots"]["video"] = driver.screenshot("windows-editor-video")
            output = driver.save(video)
            observed = duration(ffprobe, output)
            assert abs(observed - requested_duration) < 0.16, (observed, requested_duration)
            driver.close()
            report["cases"]["video_handle_play_pause_seek_trim_normal_close"] = {
                "requested_seconds": requested_duration,
                "output_seconds": observed,
                "actual_player_advanced_to_seconds": played_position,
                "actual_seek_position_seconds": seek_position,
                "output": str(output),
            }

            driver.open("bleep", audio, "Censurar áudio")
            driver.wait(lambda rows: any(r["name"] == timeline_name and r["enabled"] for r in rows))
            driver.value("Início", 1)
            driver.value("Duração", 2)
            played_position = play_and_pause(driver, 1, 3)
            report["screenshots"]["audio"] = driver.screenshot("windows-editor-audio")
            output = driver.save(audio)
            assert abs(duration(ffprobe, output) - 6) < 0.02
            assert tone_energy(output, 1000, 1.5) > tone_energy(output, 440, 1.5) * 10
            assert tone_energy(output, 440, 0.25) > tone_energy(output, 1000, 0.25) * 10
            driver.close()
            report["cases"]["audio_play_pause_bleep_pcm_oracle_normal_close"] = {
                "output": str(output),
                "actual_player_advanced_to_seconds": played_position,
            }

        if args.only in {"all", "pdf", "pdf-close"}:
            driver.open("reorder_pdf", pdf, "Ordenar PDF")
            page = driver.find("Página 3")
            driver.click((page["x"] + page["width"] / 2, page["y"] + page["height"] / 2))
            driver.wait(
                lambda rows: any(
                    r["name"] == "Página do PDF na prévia" and r.get("value", "").startswith("Página 3")
                    for r in rows
                )
            )
            driver.invoke("↑ Subir")
            driver.invoke("↑ Subir")
            driver.wait(
                lambda rows: (
                    [
                        r["name"]
                        for r in sorted(
                            (
                                r
                                for r in rows
                                if r["type"] == "ControlType.ListItem"
                                and r["name"] in {"Página 1", "Página 2", "Página 3"}
                            ),
                            key=lambda r: r["y"],
                        )
                    ]
                    == ["Página 3", "Página 1", "Página 2"]
                )
            )
            report["screenshots"]["pdf"] = driver.screenshot("windows-editor-pdf")
            output = driver.save(pdf)
            with pymupdf.open(output) as document:
                assert [page.get_text().strip() for page in document] == [
                    "CITRICA PAGE 3",
                    "CITRICA PAGE 1",
                    "CITRICA PAGE 2",
                ]
            driver.close()
            report["cases"]["pdf_visual_reorder_export_normal_process_exit"] = {"output": str(output)}

        if args.only in {"all", "close-media", "pdf-close"}:
            pending_closes = []
            for media, require_worker in [(video, False), (video, True), (audio, True)]:
                driver.open("trim", media, "Cortar tempo", wait_controls=False)
                pending_closes.append(
                    driver.close_while_preview_prepares(require_observed_worker=require_worker)
                )
            report["cases"]["immediate_media_close_and_observed_active_preview_exit0"] = pending_closes
        assert all(digest(path) == checksum for path, checksum in originals.items())
        assert not any(p.is_dir() and p.name.startswith(".citrica-") for p in fixture_dir.iterdir())
        report["originals_preserved"] = True
        report["result"] = "passed"
    except Exception as error:
        report["result"] = "failed"
        report["error"] = str(error)
        if driver.hwnd:
            try:
                report["failure_screenshot"] = driver.screenshot("failure")
                report["failure_controls"] = driver.uia()
            except Exception as diagnostic:
                report["diagnostic_error"] = str(diagnostic)
        raise
    finally:
        if driver.process is not None:
            # A failed assertion is never converted into a pass by cleanup.
            # Ask only the owned window to close through its normal handler.
            if driver.hwnd:
                driver.user.PostMessageW(driver.hwnd, 0x10, 0, 0)
            try:
                report["failed_case_normal_cleanup_exit"] = driver.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                report["failed_case_cleanup_pending"] = {"pid": driver.pid, "window": int(driver.hwnd or 0)}
            if driver.log:
                driver.log.close()
        (args.state / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps({"result": report["result"], "report": str(args.state / "report.json")}))


if __name__ == "__main__":
    main()
