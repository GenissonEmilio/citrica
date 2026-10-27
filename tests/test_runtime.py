from types import SimpleNamespace

from citrica import runtime


def test_windows_programs_use_bundle_and_standard_office_location(tmp_path, monkeypatch):
    monkeypatch.delenv('CITRICA_WINDOWS_ENGINES', raising=False)
    monkeypatch.setattr(runtime, 'sys', SimpleNamespace(platform='win32', _MEIPASS=str(tmp_path)))
    monkeypatch.setattr(runtime, 'shutil', SimpleNamespace(which=lambda name: None))
    program_files = tmp_path / 'Program Files'
    monkeypatch.setenv('ProgramFiles', str(program_files))
    (tmp_path / 'bin').mkdir()
    ffmpeg = tmp_path / 'bin/ffmpeg.exe'
    ffmpeg.write_bytes(b'test locator, not an executable')
    office = program_files / 'LibreOffice/program/soffice.com'
    office.parent.mkdir(parents=True)
    office.write_bytes(b'test locator, not an executable')
    assert runtime.program('ffmpeg') == str(ffmpeg)
    assert runtime.program('libreoffice') == str(office)
    assert runtime.program('missing') is None


def test_windows_offline_engines_win_over_path_and_use_complete_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'sys', SimpleNamespace(platform='win32', _MEIPASS=str(tmp_path)))
    monkeypatch.delenv('CITRICA_OFFICE_ENGINE', raising=False)
    monkeypatch.setattr(runtime, 'shutil', SimpleNamespace(which=lambda name: f'C:/system/{name}.exe'))
    engines = {'ffmpeg': 'tools/ffmpeg/bin/ffmpeg.exe', 'ffprobe': 'tools/ffmpeg/bin/ffprobe.exe',
               'libreoffice': 'tools/libreoffice/program/soffice.com', 'tesseract': 'ocr/tesseract.exe'}
    for name, relative in engines.items():
        file = tmp_path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'locator fixture')
        assert runtime.program(name) == str(file)
    monkeypatch.setenv('CITRICA_OFFICE_ENGINE', 'builtin')
    assert runtime.program('libreoffice') is None


def test_windows_source_can_use_prepared_engine_tree(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    engines = tmp_path / 'prepared engines'
    file = engines / 'tools/libreoffice/program/soffice.com'
    file.parent.mkdir(parents=True)
    file.write_bytes(b'locator fixture')
    monkeypatch.setattr(runtime, 'sys', SimpleNamespace(platform='win32', _MEIPASS=str(root)))
    monkeypatch.setenv('CITRICA_WINDOWS_ENGINES', str(engines))
    monkeypatch.delenv('CITRICA_OFFICE_ENGINE', raising=False)
    monkeypatch.setattr(runtime, 'shutil', SimpleNamespace(which=lambda name: None))
    assert runtime.program('libreoffice') == str(file)
