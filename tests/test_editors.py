import hashlib
import os
import subprocess
import sys
import threading
import time
import wave
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from citrica.companion import ToolDialog
from citrica.core import Cancelled, ConversionError
from citrica.editors import ImageSelection, QMediaPlayer, Timeline, capture
from citrica.runtime import program


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def until(app, predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        # Let Python workers acquire the GIL as the real Qt event loop does.
        # QTest.qWait repeatedly reacquires it and can starve cold PDF imports.
        time.sleep(.02)
    assert predicate()


def close_editor(app, dialog):
    dialog.close()
    until(app, lambda: not dialog.busy())
    app.processEvents()
    dialog.close()
    app.processEvents()


def export(app, dialog):
    dialog.apply()
    assert dialog.worker is not None, dialog.message.text()
    until(app, lambda: dialog.worker.isFinished())
    app.processEvents()
    assert dialog.latest_output is not None, dialog.message.text()
    return dialog.latest_output


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_crop_canvas_uses_source_pixels_after_resize_and_move(app, tmp_path):
    source = tmp_path / 'foto.png'
    Image.new('RGB', (600, 400), 'orange').save(source)
    canvas = ImageSelection(source)
    canvas.resize(900, 500)
    canvas.show()
    app.processEvents()
    canvas.set_selection('100,80,200,120', emit=True)
    seen = []
    canvas.selected.connect(seen.append)
    rect = canvas.selection_rect()
    center = rect.center().toPoint()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=center)
    QTest.mouseMove(canvas, center + QPoint(60, 30))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=center + QPoint(60, 30))
    x, y, width, height = map(int, seen[-1].split(','))
    assert x > 100 and y > 80 and (width, height) == (200, 120)
    canvas.resize(400, 250)
    app.processEvents()
    assert tuple(map(round, (canvas.selection.width(), canvas.selection.height()))) == (200, 120)
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    assert int(seen[-1].split(',')[0]) == x + 1
    canvas.close()


def test_crop_handle_resize_exports_exact_selection_without_changing_source(app, tmp_path):
    source = tmp_path / 'retrato.png'
    Image.new('RGB', (600, 400), 'orange').save(source)
    before = digest(source)
    dialog = ToolDialog('crop', [source])
    dialog.show()
    app.processEvents()
    dialog.canvas.set_selection('100,80,240,160', emit=True)
    handle = dialog.canvas.handles()['se'].toPoint()
    QTest.mousePress(dialog.canvas, Qt.MouseButton.LeftButton, pos=handle)
    QTest.mouseMove(dialog.canvas, handle - QPoint(40, 20))
    QTest.mouseRelease(dialog.canvas, Qt.MouseButton.LeftButton, pos=handle - QPoint(40, 20))
    dimensions = tuple(map(int, dialog.fields['rect'].text().split(',')[2:]))
    output = export(app, dialog)
    with Image.open(output) as result:
        assert result.size == dimensions
    assert digest(source) == before
    close_editor(app, dialog)


def test_adjust_live_preview_and_export_share_values(app, tmp_path):
    source = tmp_path / 'cinza.png'
    Image.new('RGB', (80, 60), (80, 80, 80)).save(source)
    dialog = ToolDialog('adjust', [source])
    dialog.fields['brightness'].setValue(2)
    dialog.fields['contrast'].setValue(1)
    dialog.update_image_preview()
    assert dialog.canvas.display.toImage().pixelColor(10, 10).red() == 160
    output = export(app, dialog)
    with Image.open(output) as image:
        assert image.getpixel((10, 10))[:3] == (160, 160, 160)
    with Image.open(source) as image:
        assert image.getpixel((10, 10)) == (80, 80, 80)
    close_editor(app, dialog)


def test_background_preview_uses_result_aspect_and_exports_it(app, tmp_path):
    source = tmp_path / 'square.png'
    Image.new('RGB', (200, 200), 'orange').save(source)
    dialog = ToolDialog('background', [source])
    dialog.fields['aspect'].setText('16:9')
    dialog.fields['padding'].setValue(20)
    dialog.update_image_preview()
    preview = dialog.canvas.display
    assert abs(preview.width() / preview.height() - 16 / 9) < .01
    output = export(app, dialog)
    with Image.open(output) as image:
        assert abs(image.width / image.height - 16 / 9) < .01
    close_editor(app, dialog)


def test_pdf_reorder_controls_export_every_page_once(app, tmp_path):
    import pymupdf
    source = tmp_path / 'páginas.pdf'
    with pymupdf.open() as document:
        for index in range(1, 4):
            page = document.new_page()
            page.insert_text((30, 30), f'Page {index}')
        document.save(source)
    before = digest(source)
    dialog = ToolDialog('reorder_pdf', [source])
    assert not dialog.pdf_image.pixmap().isNull()
    dialog.pdf_order.setCurrentRow(2)
    dialog.move_pdf_page(-1)
    dialog.move_pdf_page(-1)
    assert dialog.fields['pages'].text() == '3,1,2'
    output = export(app, dialog)
    with pymupdf.open(output) as result:
        assert [page.get_text().strip() for page in result] == ['Page 3', 'Page 1', 'Page 2']
    assert digest(source) == before
    close_editor(app, dialog)


def test_pdf_preview_fits_small_viewport_and_keeps_top_and_bottom_visible(app, tmp_path):
    import pymupdf

    source = tmp_path / 'página inteira.pdf'
    with pymupdf.open() as document:
        page = document.new_page(width=720, height=1024)
        page.draw_rect((0, 0, 720, 40), color=None, fill=(1, 0, 0))
        page.draw_rect((0, 984, 720, 1024), color=None, fill=(0, 0, 1))
        document.save(source)
    before = digest(source)
    dialog = ToolDialog('edit_metadata', [source])
    dialog.show()
    heights = []
    for width, height in [(1120, 760), (760, 570), (1280, 800)]:
        dialog.resize(width, height)
        app.processEvents()
        preview = dialog.pdf_image.pixmap()
        available = dialog.pdf_image.contentsRect()
        assert 0 < preview.width() <= available.width()
        assert 0 < preview.height() <= available.height()
        assert abs(preview.width() / preview.height() - 720 / 1024) < .01
        pixels = preview.toImage()
        assert pixels.pixelColor(preview.width() // 2, 2).red() > 230
        assert pixels.pixelColor(preview.width() // 2, preview.height() - 3).blue() > 230
        heights.append(preview.height())
    assert heights[1] < heights[0] < heights[2]
    dialog.fields['author'].setText('QA preview')
    output = export(app, dialog)
    with pymupdf.open(output) as result:
        assert tuple(result[0].rect) == (0, 0, 720, 1024)
        assert result.metadata['author'] == 'QA preview'
    assert digest(source) == before
    close_editor(app, dialog)


def test_timeline_handles_and_seek_are_separate(app):
    timeline = Timeline(selection=True)
    timeline.resize(700, 116)
    timeline.duration = 30
    timeline.set_range(0, 30)
    timeline.show()
    app.processEvents()
    ranges, seeks = [], []
    timeline.rangeChanged.connect(lambda start, end: ranges.append((start, end)))
    timeline.seek.connect(seeks.append)
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(round(timeline.x(0)), 45))
    QTest.mouseMove(timeline, QPoint(round(timeline.x(9)), 45))
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=QPoint(round(timeline.x(9)), 45))
    assert abs(ranges[-1][0] - 9) < .1 and ranges[-1][1] == 30
    QTest.mouseClick(timeline, Qt.MouseButton.LeftButton, pos=QPoint(round(timeline.x(15)), 45))
    assert abs(seeks[-1] - 15) < .1
    assert abs(timeline.start - 9) < .1
    timeline.close()


@pytest.fixture
def video(tmp_path):
    ffmpeg = program('ffmpeg')
    if not ffmpeg or not program('ffprobe'):
        pytest.skip('FFmpeg/FFprobe required for real preview/export')
    source = tmp_path / 'vídeo teste.mp4'
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'testsrc2=size=320x180:rate=12', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
                    '-t', '3', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', str(source)], check=True, capture_output=True)
    return source


def test_media_trim_has_real_thumbnails_seek_and_export(app, video):
    from citrica.tools import media_info
    before = digest(video)
    dialog = ToolDialog('trim', [video])
    dialog.show()
    until(app, lambda: dialog.media_duration is not None and dialog.canvas is not None and len(dialog.timeline.frames) == 8)
    assert all(not frame.isNull() for frame in dialog.timeline.frames)
    dialog.timeline.set_range(.5, 1.75, emit=True)
    assert dialog.fields['start'].text() == '0.5'
    assert dialog.fields['duration'].text() == '1.25'
    assert dialog.end_field.text() == '1.75'
    dialog.seek_media(1.0)
    until(app, lambda: dialog._frame_thread is None)
    output = export(app, dialog)
    assert abs(float(media_info(output)['format']['duration']) - 1.25) < .15
    assert digest(video) == before
    close_editor(app, dialog)


def test_media_player_can_play_pause_and_seek_original(app, video):
    if QMediaPlayer is None:
        pytest.skip('Qt Multimedia is optional in source-only installations')
    dialog = ToolDialog('trim', [video])
    dialog.show()
    until(app, lambda: dialog.media_duration is not None)
    dialog.audio_output.setMuted(True)
    dialog.toggle_playback()
    until(app, lambda: dialog.player.position() > 150)
    dialog.toggle_playback()
    assert dialog.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    dialog.seek_media(1.0)
    assert abs(dialog.player.position() - 1000) < 100
    close_editor(app, dialog)


def test_audio_waveform_selection_and_bleep_export(app, tmp_path):
    if not program('ffmpeg') or not program('ffprobe'):
        pytest.skip('FFmpeg required')
    import math
    import struct
    source = tmp_path / 'áudio.wav'
    rate = 16000
    with wave.open(str(source), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b''.join(struct.pack('<h', round(6000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(rate * 3)))
    before = digest(source)
    dialog = ToolDialog('bleep', [source])
    until(app, lambda: dialog.media_duration is not None and not dialog.timeline.waveform.isNull())
    dialog.timeline.set_range(.75, 1.25, emit=True)
    output = export(app, dialog)
    with wave.open(str(output)) as censored:
        assert abs(censored.getnframes() / censored.getframerate() - 3) < .02
    assert digest(source) == before
    close_editor(app, dialog)


def test_preview_close_cancels_process_without_destroying_running_thread(app, video):
    dialog = ToolDialog('trim', [video])
    assert dialog.preview_threads
    threads = dialog.preview_threads.copy()
    dialog.close()
    assert all(thread.cancel.is_set() for thread in threads)
    until(app, lambda: not dialog.busy())
    assert all(thread.isFinished() for thread in threads)
    dialog.close()


def test_capture_cancellation_and_timeout_stop_child():
    cancel = threading.Event()
    timer = threading.Timer(.15, cancel.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(Cancelled):
            capture([sys.executable, '-c', 'import time; time.sleep(20)'], cancel)
    finally:
        timer.cancel()
    assert time.monotonic() - started < 3
    with pytest.raises(ConversionError, match='tempo limite'):
        capture([sys.executable, '-c', 'import time; time.sleep(20)'], threading.Event(), timeout=.1)


def test_duplicate_pdf_page_is_rejected_before_export(app, tmp_path):
    import pymupdf
    source = tmp_path / 'duas.pdf'
    with pymupdf.open() as document:
        document.new_page()
        document.new_page()
        document.save(source)
    dialog = ToolDialog('reorder_pdf', [source])
    dialog.fields['pages'].setText('1,1')
    dialog.apply()
    assert dialog.worker is None
    assert 'uma única vez' in dialog.message.text()
    assert list(tmp_path.iterdir()) == [source]
    close_editor(app, dialog)


def test_completed_copy_is_reported_if_cancel_arrives_after_commit(app, tmp_path):
    source = tmp_path / 'original.png'
    Image.new('RGB', (24, 24), 'red').save(source)
    committed = tmp_path / 'committed.png'
    entered = threading.Event()

    def finishes_before_cancel(_tool, _paths, _params, cancel):
        entered.set()
        cancel.wait(3)
        committed.write_bytes(source.read_bytes())
        return {'outputs': [committed]}

    with patch('citrica.companion.execute', side_effect=finishes_before_cancel):
        dialog = ToolDialog('compress', [source])
        dialog.apply()
        assert entered.wait(2)
        assert dialog.cancel_export()
        until(app, lambda: dialog.worker.isFinished())
        app.processEvents()
        assert dialog.latest_output == committed
        assert 'antes do cancelamento' in dialog.message.text()
        assert committed.read_bytes() == source.read_bytes()
        close_editor(app, dialog)


def test_existing_metadata_is_loaded_in_typed_editor(app, tmp_path):
    from PIL.PngImagePlugin import PngInfo
    source = tmp_path / 'tags.png'
    info = PngInfo()
    info.add_itxt('Author', 'João')
    info.add_itxt('Title', 'Minha imagem')
    Image.new('RGB', (24, 24), 'blue').save(source, pnginfo=info)
    dialog = ToolDialog('edit_metadata', [source])
    assert dialog.fields['author'].text() == 'João'
    assert dialog.fields['title'].text() == 'Minha imagem'
    dialog.fields['title'].setText('Novo título')
    output = export(app, dialog)
    with Image.open(output) as result:
        assert result.info['Author'] == 'João'
        assert result.info['Title'] == 'Novo título'
    with Image.open(source) as original:
        assert original.info['Title'] == 'Minha imagem'
    close_editor(app, dialog)


@pytest.mark.parametrize('rotation', [90, 270])
def test_rotated_video_crop_uses_display_axes_in_preview_and_export(app, video, rotation):
    from io import BytesIO
    from PIL import ImageChops, ImageStat
    from citrica.editors import media_frame
    from citrica.tools import media_info, oriented_video_size

    source = video.with_name(f'rotacionado-{rotation}.mp4')
    help_text = subprocess.run([program('ffmpeg'), '-hide_banner', '-h', 'full'],
                               check=True, capture_output=True, text=True).stdout
    # FFmpeg 8 no longer converts rotate tags to a display matrix. Older
    # releases without -display_rotation use that historical metadata route.
    if '-display_rotation' in help_text:
        args = ['-display_rotation:v:0', str(rotation), '-i', str(video), '-c', 'copy']
    else:
        args = ['-i', str(video), '-c', 'copy', '-metadata:s:v:0', f'rotate={rotation}']
    subprocess.run([program('ffmpeg'), '-nostdin', '-v', 'error', '-y', *args, str(source)],
                   check=True, capture_output=True)
    stream = next(item for item in media_info(source)['streams'] if item['codec_type'] == 'video')
    assert (stream['width'], stream['height']) == (320, 180)
    assert oriented_video_size(stream) == (180, 320)
    before = digest(source)
    dialog = ToolDialog('crop', [source])
    dialog.show()
    until(app, lambda: dialog.canvas is not None and len(dialog.timeline.frames) == 8)
    try:
        assert dialog.canvas.source_size == (180, 320)
        assert dialog.fields['rect'].text() == '0,0,180,320'
        # This area fits the displayed portrait frame, but not the encoded
        # landscape height. Both the canvas and export must use display axes.
        dialog.canvas.set_selection('20,200,100,80', emit=True)
        output = export(app, dialog)
        result_stream = next(item for item in media_info(output)['streams'] if item['codec_type'] == 'video')
        assert oriented_video_size(result_stream) == (100, 80)
        original_frame = Image.open(BytesIO(media_frame(source, 0, threading.Event(), width=180))).convert('RGB')
        result_frame = Image.open(BytesIO(media_frame(output, 0, threading.Event(), width=100))).convert('RGB')
        expected = original_frame.crop((20, 200, 120, 280))
        assert result_frame.size == expected.size == (100, 80)
        # H.264 re-encoding can perturb pixels; comparing the actual content
        # catches crops taken from the wrong orientation or location.
        assert max(ImageStat.Stat(ImageChops.difference(expected, result_frame)).mean) < 8
        assert digest(source) == before
    finally:
        close_editor(app, dialog)


def test_long_audio_waveform_bounds_samples_and_preserves_tone(tmp_path):
    from array import array
    from io import BytesIO
    from citrica.editors import WAVEFORM_SAMPLE_LIMIT, waveform_filter

    ffmpeg = program('ffmpeg')
    if not ffmpeg:
        pytest.skip('FFmpeg required')
    filters, sampled = waveform_filter(96)
    assert sampled
    source = ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=8000:duration=96']
    bounded_audio = capture([ffmpeg, '-nostdin', '-v', 'error', *source,
                             '-filter_complex', filters.rsplit(',showwavespic=', 1)[0],
                             '-f', 'f32le', 'pipe:1'], threading.Event())
    values = array('f')
    values.frombytes(bounded_audio)
    assert len(values) <= WAVEFORM_SAMPLE_LIMIT
    assert len(values) > 1_000_000
    # Sparse block selection must keep normal speech/tone frequencies, unlike
    # resampling the complete recording to a sample rate of only a few Hz.
    assert max(values) > .1 and min(values) < -.1
    image = capture([ffmpeg, '-nostdin', '-v', 'error', *source, '-filter_complex', filters,
                     '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1'],
                    threading.Event())
    with Image.open(BytesIO(image)) as waveform:
        assert waveform.size == (1024, 160)
        assert waveform.getbbox() is not None
    assert waveform_filter(3)[1] is False
