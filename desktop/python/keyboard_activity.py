"""Observe only an aggregate key-down count, never keys, characters or event payloads."""
import ctypes
import sys
import time
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication


class MacKeyCounter:
    def __init__(self):
        self.function = None
        if sys.platform == 'darwin' and QApplication.platformName() == 'cocoa':
            try:
                self.library = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
                self.function = self.library.CGEventSourceCounterForEventType
                self.function.argtypes = [ctypes.c_int32, ctypes.c_uint32]
                self.function.restype = ctypes.c_uint32
            except (OSError, AttributeError):
                pass

    def read(self):
        # kCGEventSourceStateHIDSystemState=1; kCGEventKeyDown=10.
        return self.function(1, 10) if self.function else None


class KeyboardActivity(QObject):
    tapped = Signal()

    def __init__(self, counter=None, clock=time.monotonic):
        super().__init__()
        self.counter = counter or MacKeyCounter()
        self.clock = clock
        self.enabled = True
        self.last_count = None
        self.last_pulse = float('-inf')
        self.available = self.counter.read() is not None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.last_count = None

    def pulse(self):
        now = self.clock()
        if self.enabled and now - self.last_pulse >= .045:
            self.last_pulse = now
            self.tapped.emit()

    def poll(self):
        if not self.enabled:
            return
        count = self.counter.read()
        if count is None:
            return
        if self.last_count is not None and count != self.last_count:
            self.pulse()
        self.last_count = count

    def close(self):
        self.enabled = False
