"""Shared identifiers and bounded image decoding for user-owned chat artwork."""
import re
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImageReader

TOKEN = re.compile(r':emoji_([a-f0-9]{32}):')
MAX_UPLOAD = 4 * 1024 * 1024


def emoji_token(asset_id):
    return ':emoji_' + asset_id + ':'


def normalize_image(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_UPLOAD:
        raise ValueError('이미지는 4MB 이하로 선택해주세요.')
    data = QByteArray(raw)
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width()*size.height() > 16000000:
        raise ValueError('PNG·JPG·WebP 이미지(1,600만 화소 이하)를 선택해주세요.')
    if bytes(reader.format()).lower() not in (b'png', b'jpeg', b'webp'):
        raise ValueError('PNG·JPG·WebP 이미지를 선택해주세요.')
    reader.setScaledSize(size.scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError('이미지를 읽지 못했어요.')
    result = QByteArray()
    output = QBuffer(result)
    output.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(output, 'PNG')
    return bytes(result)
