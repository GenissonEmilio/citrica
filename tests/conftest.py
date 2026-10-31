"""Keep Qt alive until every test-owned widget and worker has been disposed.

Closing a QWidget only hides it. Letting retained Python signal closures reach
PySide's interpreter-exit traversal can destroy its children out of order even
when all assertions passed. Tests must use the same deferred teardown boundary
as the standalone application, while QApplication and its event dispatcher live.
"""
import gc
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid


def dispose_test_widgets(app):
    for widget in app.topLevelWidgets():
        if not isValid(widget):
            continue
        threads = list(getattr(widget, 'preview_threads', []))
        worker = getattr(widget, 'worker', None)
        if isinstance(worker, QThread):
            threads.append(worker)
        if hasattr(widget, 'prepare_shutdown'):
            widget.prepare_shutdown()
        else:
            for thread in threads:
                if isValid(thread):
                    thread.cancel.set()
                    assert thread.wait(10_000), 'A test-owned Qt worker did not stop after cancellation'
        widget.close()
        for thread in threads:
            if isValid(thread):
                thread.deleteLater()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()


@pytest.fixture(scope='session', autouse=True)
def qt_application_lifetime():
    app = QApplication.instance() or QApplication([])
    yield app
    dispose_test_widgets(app)
    assert not app.topLevelWidgets(), 'Test-owned top-level widgets survived Qt teardown'


@pytest.fixture(autouse=True)
def qt_widgets_teardown(qt_application_lifetime):
    yield
    dispose_test_widgets(qt_application_lifetime)
