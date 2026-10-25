from pathlib import Path

from PIL import Image

from citrica.desktop import request
from citrica.preview import selection_info


def test_empty_and_multiple_selection_never_reuse_thumbnail(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    source = tmp_path / 'photo.jpg'
    Image.new('RGB', (400, 200), 'orange').save(source)
    assert selection_info([source])['preview']
    assert selection_info([]) == {'count': 0, 'label': '', 'bytes': 0,
                                  'preview': None, 'icon': 'document-open-symbolic'}
    result = selection_info([source, source])
    assert result['preview'] is None and result['count'] == 2


def test_thumbnail_is_small_oriented_cached_and_original_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    source = tmp_path / 'photo.jpg'
    image = Image.new('RGB', (400, 200), 'orange')
    exif = image.getexif()
    exif[274] = 6
    image.save(source, exif=exif)
    original = source.read_bytes()
    result = selection_info([source])
    preview = Path(result['preview'])
    with Image.open(preview) as thumbnail:
        assert thumbnail.size == (128, 128)
        assert thumbnail.getbbox() == (32, 0, 96, 128)
    modified = preview.stat().st_mtime_ns
    assert selection_info([source]) == result
    assert preview.stat().st_mtime_ns == modified
    assert source.read_bytes() == original
    assert result['bytes'] == len(original)
    # A changed file must not reuse its previous thumbnail.
    Image.new('RGB', (200, 400), 'blue').save(source)
    assert selection_info([source])['preview'] != result['preview']


def test_bad_thumbnail_does_not_hide_conversion_options(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    source = tmp_path / 'broken.png'
    source.write_bytes(b'not an image')
    result = request({'op': 'palette', 'paths': [str(source)]})
    assert result['selection']['preview'] is None
    assert any(i['id'] == 'jpg' for i in result['modes']['convert'])
    assert any(i['id'] == 'crop' for i in result['modes']['tools'])
    assert any(i['id'] == 'copy_path' for i in result['modes']['actions'])
