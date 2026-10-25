"""Verify the actual Wayland drag thumbnail remains visible above the wheel."""
import json

from PIL import Image, ImageChops, ImageStat

from run_flow import STATE, call, point_at, start_drag, status, step, wait_for


def thumbnail(name):
    layers = json.loads(call('Test', 'DragLayers')[0])
    icons = [i for i in layers['icons'] if i['width'] > 16 and i['height'] > 16]
    assert len(icons) == 1, layers
    icon = icons[0]
    path = STATE / f'stacking-{name}.png'
    call('Test', 'Screenshot', str(path))
    # Avoid the thumbnail's antialiased edge. Screenshots contain the compositor
    # output; an incorrectly stacked wheel changes these actual image pixels.
    x, y = round(icon['x']), round(icon['y'])
    with Image.open(path) as shot:
        crop = shot.convert('RGB').crop((x + 3, y + 3,
            x + round(icon['width']) - 3, y + round(icon['height']) - 3))
    return crop, layers


def main():
    call('Desktop', 'Hide')
    step('Prepare')
    start_drag()
    baseline, _ = thumbnail('baseline')
    results = {}
    for mode, key, item in [('actions', 65507, 'copy_path'),
                            ('tools', 65513, 'crop'), ('convert', 65505, 'jpg')]:
        step('Key', key, 'true')
        wheel = wait_for(lambda s: s['visible'] and s['mode'] == mode and s.get('items') and
                         (s.get('motion') or {}).get('settled'))
        point_at(wheel, item)
        actual, layers = thumbnail(mode)
        assert actual.size == baseline.size, (baseline.size, actual.size)
        error = max(ImageStat.Stat(ImageChops.difference(actual, baseline)).mean)
        results[mode] = {'feedback_above_wheel': layers['feedbackAboveWheel'],
                         'thumbnail_pixel_error': error}
        assert error < 2, f'{mode}: a roda está cobrindo a miniatura ({error=})'
        assert layers['feedbackAboveWheel'], layers
        step('Key', key, 'false')
    before = status()['counts']['converted']
    step('Button', 'false')
    wait_for(lambda s: not s['visible'] and not s['busy'] and
             s['counts']['converted'] == before + 1)
    call('Desktop', 'Show', '[]', 'convert')
    empty = wait_for(lambda s: s['visible'])
    assert not empty['paths'] and not empty['items']
    call('Desktop', 'Hide')
    (STATE / 'stacking-result.json').write_text(json.dumps({
        'native_drag_thumbnail': True, 'modes': results, 'drop_converts': True,
        'reopen_empty': True}, indent=2))
    print('GNOME: miniatura acima da roda em Ctrl, Alt e Shift, pixels visíveis, '
          'drop e reabertura vazia validados.')


if __name__ == '__main__':
    try:
        main()
    finally:
        for key in [65507, 65513, 65505]:
            call('Test', 'Key', key, 'false')
        call('Test', 'Button', 'false')
