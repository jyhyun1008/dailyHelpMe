"""Product identity; companion names and legacy data identifiers stay independent."""
import sys
from pathlib import Path

APP_NAME = '날도와줘'
APP_NAME_EN = 'DailyHelpMe!!'
ROOT = Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
APP_ICON = ROOT / 'desktop/python/assets/branding/app-icon.png'

APP_VERSION = '0.1.0-beta.1'
BUILD_NUMBER = '1'
