from types import SimpleNamespace

import pytest

from citrica.windows import app


@pytest.fixture(autouse=True)
def prohibit_asynchronous_frame_snapshots(monkeypatch):
    monkeypatch.setattr(app.faulthandler, 'dump_traceback_later',
                        lambda *a, **kw: pytest.fail('QA must never arm an asynchronous frame snapshot'))
    monkeypatch.setattr(app.faulthandler, 'cancel_dump_traceback_later',
                        lambda: pytest.fail('QA must not alter an external watchdog'))


@pytest.mark.parametrize('background, opt_in', [(True, False), (False, True)])
def test_fatal_capture_requires_explicit_opt_in_and_resident(tmp_path, monkeypatch, background, opt_in):
    path = tmp_path / 'stacks.log'
    monkeypatch.delenv('CITRICA_QA_TRACEBACK_LOG', raising=False)
    if opt_in:
        monkeypatch.setenv('CITRICA_QA_TRACEBACK_LOG', str(path))
    monkeypatch.setattr(app.faulthandler, 'enable',
                        lambda **kw: pytest.fail('QA fatal capture enabled without both conditions'))
    monkeypatch.setattr(app.faulthandler, 'disable',
                        lambda: pytest.fail('A disabled QA capture changed global state'))
    with app.qa_tracebacks(SimpleNamespace(background=background)):
        pass
    assert not path.exists()
    assert not path.with_suffix('.events.log').exists()


@pytest.mark.parametrize('fatal_already_enabled', [False, True])
def test_fatal_capture_restores_existing_handler_and_logging_after_failure(tmp_path, monkeypatch,
                                                                         fatal_already_enabled):
    path = tmp_path / 'stacks.log'
    monkeypatch.setenv('CITRICA_QA_TRACEBACK_LOG', str(path))
    fatal_calls = []
    monkeypatch.setattr(app.faulthandler, 'is_enabled', lambda: fatal_already_enabled)
    monkeypatch.setattr(app.faulthandler, 'enable', lambda **kw: fatal_calls.append(('enable', kw)))
    monkeypatch.setattr(app.faulthandler, 'disable', lambda: fatal_calls.append(('disable', {})))
    previous = (app.QA.level, app.QA.propagate, list(app.QA.handlers))
    with pytest.raises(RuntimeError, match='test failure'):
        with app.qa_tracebacks(SimpleNamespace(background=True)):
            app.QA.debug('ole.test_boundary')
            raise RuntimeError('test failure')
    if fatal_already_enabled:
        assert not fatal_calls, 'An existing fatal handler and its destination must remain untouched'
    else:
        assert fatal_calls[0][0] == 'enable'
        options = fatal_calls[0][1]
        assert options['all_threads'] is True and options['file'].closed
        assert fatal_calls[1] == ('disable', {})
    assert (app.QA.level, app.QA.propagate, list(app.QA.handlers)) == previous
    events = path.with_suffix('.events.log').read_text(encoding='utf-8')
    assert 'ole.test_boundary' in events and 'resident.qa_fatal_capture stop' in events
