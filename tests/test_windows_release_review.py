"""A retained/manual wheel must participate in a subsequent physical drag."""
import pytest
from PIL import Image
from PySide6.QtTest import QTest

from test_windows import desktop as desktop, image_file, spin_until


def next_physical_drag(desktop, tmp_path, monkeypatch):
    source = tmp_path / 'second-drag.png'
    Image.new('RGB', (20, 30), 'navy').save(source)
    down = {'left': True}
    monkeypatch.setattr(desktop.native, 'left_down', lambda: down['left'])
    monkeypatch.setattr('citrica.windows.explorer.preview_files', lambda hwnd: [source])
    desktop.prepare_drag(123)
    spin_until(lambda: desktop.drag_candidates == [source])
    desktop.drag_mode('actions')
    down['left'] = False
    desktop.release()
    desktop.poll_pointer()
    spin_until(lambda: not desktop.active and not desktop.armed)
    spin_until(lambda: not desktop.jobs)
    assert desktop.paths == [] and desktop.wheel.paths == []
    assert desktop.wheel.info is None and not desktop.pending_drop
    assert desktop.counts == {'converted': 0, 'errors': 0}
    assert source.is_file()


def test_new_ctrl_drag_after_more_dismisses_outside(desktop, tmp_path, monkeypatch):
    source = image_file(tmp_path)
    desktop.show_wheel([source], 'tools', dragging=True)
    spin_until(lambda: desktop.wheel.items)
    desktop.apply(next(item for item in desktop.wheel.items if item['kind'] == 'page'))
    desktop.release()
    QTest.qWait(300)
    assert desktop.active and desktop.paths == [source] and not desktop.dragging
    next_physical_drag(desktop, tmp_path, monkeypatch)


@pytest.mark.parametrize('has_files', [False, True])
def test_manual_wheel_survives_idle_but_next_ctrl_drag_dismisses_outside(
        desktop, tmp_path, monkeypatch, has_files):
    paths = [image_file(tmp_path)] if has_files else []
    desktop.show_wheel(paths)
    if paths:
        spin_until(lambda: desktop.wheel.items)
    desktop.poll_pointer()
    desktop.release()
    QTest.qWait(300)
    assert desktop.active and not desktop.dragging
    next_physical_drag(desktop, tmp_path, monkeypatch)
