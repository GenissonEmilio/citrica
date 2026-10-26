"""Select PDF→DOCX from the real GNOME wheel and inspect the saved document."""
import json
from tempfile import TemporaryDirectory
from pathlib import Path

import pymupdf
from docx import Document

from run_flow import STATE, call, point_at, status, step, wait_for


def main():
    call('Desktop', 'Hide')
    step('Prepare')
    with TemporaryDirectory(prefix='documents-', dir=STATE) as folder:
        source = Path(folder)/'Citrica PDF.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((50, 60), 'Citrica GNOME editable document')
            pdf.save(source)
        original = source.read_bytes()
        before = status()['counts']['converted']
        call('Desktop', 'Show', json.dumps([str(source)]), 'convert')
        wheel = wait_for(lambda s: any(i['id'] == 'docx' for i in s['items']))
        point_at(wheel, 'docx')
        call('Test', 'Screenshot', str(STATE/'documents-wheel.png'))
        step('Button', 'true')
        step('Button', 'false')
        wait_for(lambda s: not s['busy'] and s['counts']['converted'] == before+1, timeout=20)
        output = source.with_suffix('.docx')
        assert any('Citrica GNOME editable document' in p.text for p in Document(output).paragraphs)
        assert source.read_bytes() == original
        call('Desktop', 'Show', '[]', 'convert')
        empty = wait_for(lambda s: s['visible'])
        assert not empty['paths'] and not empty['items']
        call('Desktop', 'Hide')
    (STATE/'documents-result.json').write_text(json.dumps({'gnome_pdf_docx': True,
        'editable_text': True, 'original_preserved': True, 'reopen_empty': True}))
    print('GNOME: opção PDF→DOCX, documento editável, original e reabertura vazia validados.')


if __name__ == '__main__':
    main()
