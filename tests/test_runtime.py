from types import SimpleNamespace

from citrica import runtime


def test_windows_programs_use_bundle_and_standard_office_location(tmp_path, monkeypatch):
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
