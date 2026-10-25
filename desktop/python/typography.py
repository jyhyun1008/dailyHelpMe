"""Register the bundled ThinMulmaru and Mulmaru faces without installing it on the user's Mac."""
from pathlib import Path
import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

FONT_FAMILY = "ThinMulmaru"
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
FONT_PATH = ROOT / "desktop/python/assets/fonts/ThinMulmaru.ttf"
_font_id = None
_bold_font_id = None
EMPHASIS_STYLESHEET = "b, strong { font-family: Mulmaru; font-weight: 500; }"


def initialize_typography():
    global _font_id, _bold_font_id
    if _font_id is None:
        # Loading bytes also works with macOS Qt backends that reject the file-path API.
        _font_id = QFontDatabase.addApplicationFontFromData(FONT_PATH.read_bytes())
        if _font_id < 0 or FONT_FAMILY not in QFontDatabase.applicationFontFamilies(_font_id):
            _font_id = None
            raise RuntimeError("ThinMulmaru 폰트를 불러오지 못했어요. 앱을 다시 빌드해주세요.")
    if _bold_font_id is None:
        _bold_font_id = QFontDatabase.addApplicationFontFromData(FONT_PATH.with_name("Mulmaru.ttf").read_bytes())
        if _bold_font_id < 0 or "Mulmaru" not in QFontDatabase.applicationFontFamilies(_bold_font_id):
            _bold_font_id = None
            raise RuntimeError("Mulmaru 폰트를 불러오지 못했어요. 앱을 다시 빌드해주세요.")
    default = QFont(FONT_FAMILY)
    default.setPixelSize(13)
    QApplication.instance().setFont(default)
