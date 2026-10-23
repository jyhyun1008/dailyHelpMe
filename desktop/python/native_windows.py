"""macOS window policy for the pet; no focus stealing or repeated raise timers."""
from __future__ import annotations

import ctypes
import platform
import sys
from functools import lru_cache

from PySide6.QtWidgets import QApplication


@lru_cache(maxsize=1)
def _cocoa():
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    graphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    graphics.CGWindowLevelForKey.argtypes = [ctypes.c_int]
    graphics.CGWindowLevelForKey.restype = ctypes.c_int32
    return objc, graphics


def _send(objc, receiver, selector, result_type, *arguments):
    """Give every Objective-C call its exact ABI, including 64-bit NSInteger values."""
    signature = ctypes.CFUNCTYPE(result_type, ctypes.c_void_p, ctypes.c_void_p,
                                 *(kind for kind, _ in arguments))
    function = signature(("objc_msgSend", objc))
    return function(receiver, objc.sel_registerName(selector), *(value for _, value in arguments))


def configure_pet_window(widget):
    if sys.platform != "darwin" or QApplication.platformName() != "cocoa":
        return False
    try:
        objc, graphics = _cocoa()
        # On Qt's Cocoa backend QWidget.winId() identifies the NSView, not the NSWindow.
        window = _send(objc, int(widget.winId()), b"window", ctypes.c_void_p)
        if not window:
            return False
        behavior = _send(objc, window, b"collectionBehavior", ctypes.c_ulong)
        # Avoid mutually exclusive policies left by the toolkit.
        behavior &= ~((1 << 1) | (1 << 7) | (1 << 9) | (1 << 16) | (1 << 17))
        behavior |= (1 << 0) | (1 << 8)  # canJoinAllSpaces, fullScreenAuxiliary
        if int(platform.mac_ver()[0].split(".")[0]) >= 13:
            behavior |= 1 << 18  # canJoinAllApplications, including Stage Manager sets
        _send(objc, window, b"setCollectionBehavior:", None, (ctypes.c_ulong, behavior))
        # CGWindowLevelKey 9 is kCGStatusWindowLevelKey: above ordinary/floating windows.
        _send(objc, window, b"setLevel:", None, (ctypes.c_long, graphics.CGWindowLevelForKey(9)))
        _send(objc, window, b"setHidesOnDeactivate:", None, (ctypes.c_bool, False))
        return True
    except (OSError, AttributeError, ValueError):
        # Other platforms retain Qt's WindowStaysOnTopHint policy.
        return False
