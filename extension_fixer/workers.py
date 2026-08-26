# SPDX-FileCopyrightText: 2026 Steven
# SPDX-License-Identifier: GPL-3.0-only

"""Qt worker objects. Workers emit data and never touch widgets."""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from .core.scanner import FileScanner


class ScanWorker(QObject):
    batchReady = pyqtSignal(list)
    progress = pyqtSignal(int, int)
    logMessage = pyqtSignal(str)
    completed = pyqtSignal(dict)
    cancelled = pyqtSignal(dict)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        scanner: FileScanner,
        root_folder,
        recursive: bool,
        max_size_mb: float,
        blacklist: set[str],
        batch_size: int = 200,
        batch_interval: float = 0.08,
    ):
        super().__init__()
        self.scanner = scanner
        self.root_folder = root_folder
        self.recursive = recursive
        self.max_size_mb = max_size_mb
        self.blacklist = blacklist
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self._cancel_event = threading.Event()

    def request_cancel(self):
        """Thread-safe direct call; a queued slot cannot run during scan()."""
        self._cancel_event.set()

    @pyqtSlot()
    def run(self):
        processed = 0
        repairs = 0
        batch: list[dict] = []
        last_emit = time.monotonic()
        try:
            for record in self.scanner.scan_iter(
                self.root_folder,
                self.recursive,
                self.max_size_mb,
                self.blacklist,
                self.logMessage.emit,
                self._cancel_event.is_set,
            ):
                if self._cancel_event.is_set():
                    break
                batch.append(record)
                processed += 1
                repairs += record.get("status") == "Repair required"
                now = time.monotonic()
                if len(batch) >= self.batch_size or now - last_emit >= self.batch_interval:
                    self.batchReady.emit(batch)
                    batch = []
                    last_emit = now
                    self.progress.emit(processed, repairs)

            if batch:
                self.batchReady.emit(batch)
            summary = {"processed": processed, "repair_count": repairs}
            self.progress.emit(processed, repairs)
            if self._cancel_event.is_set():
                self.cancelled.emit(summary)
            else:
                self.completed.emit(summary)
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            self.finished.emit()


class OperationWorker(QObject):
    logMessage = pyqtSignal(str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, task: Callable[[Callable[[str], None]], object]):
        super().__init__()
        self.task = task

    @pyqtSlot()
    def run(self):
        try:
            self.succeeded.emit(self.task(self.logMessage.emit))
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            self.finished.emit()
