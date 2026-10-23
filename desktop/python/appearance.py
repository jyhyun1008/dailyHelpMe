"""User-owned appearance, shared by native and mobile surfaces."""
import hashlib
import re
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

DEFAULT_NAME = '봉고캣'
DEFAULT_COLOR = '#d64289'
HEX = re.compile(r'#[0-9a-fA-F]{6}\b')


def read_appearance(store):
    avatar = store.get('avatar_png')
    return {'name': store.get('companion_name', DEFAULT_NAME),
            'color': store.get('theme_color', DEFAULT_COLOR),
            'avatar': hashlib.sha256(avatar.encode()).hexdigest()[:16] if avatar else ''}


def validate(name, color):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 30 or any(ord(c) < 32 for c in name):
        raise ValueError('이름은 줄바꿈 없이 1~30자로 적어주세요.')
    if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError('테마색은 #RRGGBB 형식으로 입력해주세요.')
    return name.strip(), color.lower()


def current():
    app = QApplication.instance()
    return (app.property('doa_appearance') if app else None) or {'name': DEFAULT_NAME, 'color': DEFAULT_COLOR}


def map_color(value, accent=None):
    accent = accent or current()['color']
    if accent == DEFAULT_COLOR:
        return value
    if value.lower() in (DEFAULT_COLOR, '#b65d88'):
        return accent
    original = QColor(value)
    if not original.isValid():
        return value
    hue, saturation, lightness, alpha = original.getHslF()
    if hue < 0 or not .78 <= hue <= .98:
        return value  # Preserve category colours, neutral white and warning colours.
    target = QColor(accent)
    th, ts, _, _ = target.getHslF()
    return QColor.fromHslF(max(0, th), min(1, saturation * ts / .65), lightness, alpha).name()


def style(text, accent=None):
    result = HEX.sub(lambda match: map_color(match.group(), accent), text)
    return result.replace('color: white', 'color: ' + foreground(accent)).replace('color:white', 'color:'+foreground(accent))


def color(*args):
    return QColor(map_color(args[0])) if len(args) == 1 and isinstance(args[0], str) else QColor(*args)


def foreground(accent=None):
    c = QColor(accent or current()['color'])
    def linear(v):
        return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
    luminance = sum(weight*linear(v) for weight, v in zip((.2126,.7152,.0722), (c.redF(),c.greenF(),c.blueF())))
    return '#352431' if luminance > .179 else '#ffffff'
