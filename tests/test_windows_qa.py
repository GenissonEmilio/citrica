from types import SimpleNamespace

import pytest

from citrica.windows import app


@pytest.mark.parametrize('background, opt_in', [(True, False), (False, True)])
def test_watchdog_requires_explicit_opt_in_and_resident(tmp_path, monkeypatch, background, opt_in):
    path = tmp_path / 'stacks.log'
    monkeypatch.delenv('CITRICA_QA_TRACEBACK_LOG', raising=False)
    if opt_in:
        monkeypatch.setenv('CITRICA_QA_TRACEBACK_LOG', str(path))
    monkeypatch.setattr(app.faulthandler, 'dump_traceback_later',
                        lambda *a, **kw: pytest.fail('QA watchdog enabled without both conditions'))
    monkeypatch.setattr(app.faulthandler, 'cancel_dump_traceback_later',
                        lambda: pytest.fail('A disabled QA watchdog changed global state'))
    with app.qa_tracebacks(SimpleNamespace(background=background)):
        pass
    assert not path.exists()
    assert not path.with_suffix('.events.log').exists()


def test_watchdog_captures_outside_ipc_and_restores_logging_after_failure(tmp_path, monkeypatch):
    path = tmp_path / 'stacks.log'
    monkeypatch.setenv('CITRICA_QA_TRACEBACK_LOG', str(path))
    calls = []
    monkeypatch.setattr(app.faulthandler, 'dump_traceback_later', lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(app.faulthandler, 'cancel_dump_traceback_later', lambda: calls.append('cancel'))
    previous = (app.QA.level, app.QA.propagate, list(app.QA.handlers))
    with pytest.raises(RuntimeError, match='test failure'):
        with app.qa_tracebacks(SimpleNamespace(background=True)):
            app.QA.debug('ole.test_boundary')
            raise RuntimeError('test failure')
    arguments, options = calls[0]
    assert arguments == (5,) and options['repeat'] is True
    assert options['file'].closed
    assert calls[-1] == 'cancel'
    assert (app.QA.level, app.QA.propagate, list(app.QA.handlers)) == previous
    events = path.with_suffix('.events.log').read_text(encoding='utf-8')
    assert 'ole.test_boundary' in events and 'resident.watchdog stop' in events
