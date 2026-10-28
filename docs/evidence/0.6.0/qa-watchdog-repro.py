"""Disposable QA experiment: CPython watchdog versus live Qt/Python frames.

No Cítrica imports, windows, input injection, files to convert or system changes.
Run with the VM's CPython 3.12 and PySide6 installed:
  python faulthandler-qthread-repro.py --seconds 8 --repeat 3 --interval 0.02 --output C:/CitricaVM/repro

Each case is a separate process. All cases enable fatal trace capture; only
periodic cases additionally call dump_traceback_later(..., repeat=True).
Native faults, timeouts and incomplete dumps are evidence, not hidden retries.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time


def frame_churn(depth, root, index):
    first = root / ('frame-' + str(index % 7))
    second = first.with_name(first.name + '-value')
    third = str(second)
    if depth:
        return frame_churn(depth - 1, second.parent, index + 1)
    return os.fspath(first), str(second), third


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def case(args):
    # Suppress only this disposable child's crash UI/core file. Defender,
    # SmartScreen, the parent process and the system configuration are untouched.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except ImportError:
        pass
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(2)  # SEM_NOGPFAULTERRORBOX

    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import QCoreApplication, QObject, QThread, QTimer, Signal, Slot, qVersion

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    state_file = output / 'state.json'
    stop = threading.Event()
    started = time.monotonic()
    app = QCoreApplication([])

    class Job(QThread):
        result = Signal(object)

        def run(self):
            value = None
            for index in range(48):
                if stop.is_set():
                    break
                value = frame_churn(64 + index % 8, output, index)
            self.result.emit(value)

    class Controller(QObject):
        def __init__(self):
            super().__init__()
            self.jobs = set()
            self.created = self.finished = self.results = self.ticks = 0
            self.stopping = False
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.tick)
            self.timer.start(1)
            self.report_timer = QTimer(self)
            self.report_timer.timeout.connect(self.report)
            self.report_timer.start(250)

        @Slot(object)
        def result(self, _result):
            self.results += 1

        @Slot()
        def done(self):
            job = self.sender()
            self.jobs.discard(job)
            job.deleteLater()
            self.finished += 1
            if self.stopping and not self.jobs:
                self.report()
                QTimer.singleShot(10, app.quit)

        @Slot()
        def tick(self):
            if self.stopping:
                return
            self.ticks += 1
            # Keep the main thread changing frames as native QThread states
            # start/finish. Pure pathlib work does no filesystem I/O.
            for index in range(4):
                frame_churn(96 + index % 8, output, self.ticks + index)
            if time.monotonic() - started >= args.seconds:
                self.stopping = True
                self.timer.stop()
                stop.set()
                if not self.jobs:
                    self.report()
                    QTimer.singleShot(10, app.quit)
                return
            while len(self.jobs) < args.threads:
                job = Job()
                self.jobs.add(job)
                job.result.connect(self.result)
                job.finished.connect(self.done)
                job.start()
                self.created += 1

        @Slot()
        def report(self):
            write_json(state_file, {
                'python': sys.version, 'platform': platform.platform(),
                'pyside': pyside_version, 'qt': qVersion(), 'mode': args.case,
                'interval': args.interval if args.case == 'periodic' else None,
                'seconds': round(time.monotonic() - started, 3),
                'created': self.created, 'finished': self.finished, 'results': self.results,
                'main_ticks': self.ticks, 'active': len(self.jobs),
                'orderly_shutdown': self.stopping and not self.jobs,
            })

    controller = Controller()
    controller.report()
    with (output / 'fatal-and-watchdog.log').open('wb', buffering=0) as traces:
        faulthandler.enable(file=traces, all_threads=True)
        if args.case == 'periodic':
            faulthandler.dump_traceback_later(args.interval, repeat=True, file=traces)
        try:
            code = app.exec()
        finally:
            faulthandler.cancel_dump_traceback_later()
            faulthandler.disable()
            stop.set()
            for job in list(controller.jobs):
                job.wait(5000)
            QCoreApplication.processEvents()
    print(state_file.read_text(), flush=True)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=8)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--interval', type=float, default=0.02)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--case', choices=['control', 'periodic'])
    parser.add_argument('--allow-other-python', action='store_true',
                        help='smoke-check the harness; results do not establish CPython3.12 behavior')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12) and not args.allow_other_python:
        parser.error('Use CPython3.12 for this hypothesis; --allow-other-python only checks the harness.')
    if not 0 < args.seconds <= 120 or not .001 <= args.interval <= 5 or not 1 <= args.threads <= 16:
        parser.error('Use seconds1..120, interval0.001..5, threads1..16.')
    if args.case:
        return case(args)
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(args.repeat):
        for mode in ['control', 'periodic']:
            destination = args.output / f'{index + 1:02d}-{mode}'
            destination.mkdir(exist_ok=True)
            command = [sys.executable, str(Path(__file__).resolve()), '--case', mode,
                       '--seconds', str(args.seconds), '--interval', str(args.interval),
                       '--threads', str(args.threads), '--output', str(destination)]
            if args.allow_other_python:
                command.append('--allow-other-python')
            started = time.monotonic()
            timed_out = False
            with (destination / 'process.log').open('wb') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                try:
                    returncode = process.wait(timeout=args.seconds + 15)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.kill()
                    returncode = process.wait(timeout=5)
            state_path = destination / 'state.json'
            trace_path = destination / 'fatal-and-watchdog.log'
            state = json.loads(state_path.read_text()) if state_path.is_file() else None
            trace = trace_path.read_text(errors='replace') if trace_path.is_file() else ''
            record = {'iteration': index + 1, 'mode': mode, 'returncode': returncode,
                      'exit_hex': hex(returncode & 0xffffffff), 'timed_out': timed_out,
                      'elapsed_seconds': round(time.monotonic() - started, 3),
                      'state': state, 'trace_bytes': trace_path.stat().st_size if trace_path.is_file() else 0,
                      'watchdog_dumps': trace.count('Timeout ('), 'trace_tail': trace[-2000:]}
            records.append(record)
            write_json(args.output / 'comparison.json', records)
            print(json.dumps({key: record[key] for key in ['iteration', 'mode', 'returncode',
                                                         'exit_hex', 'timed_out', 'elapsed_seconds',
                                                         'watchdog_dumps']}), flush=True)
    # Returning failure keeps native faults visible; comparison.json retains
    # every successful control and every failure independently.
    return int(any(item['returncode'] != 0 or item['timed_out'] for item in records))


if __name__ == '__main__':
    raise SystemExit(main())
