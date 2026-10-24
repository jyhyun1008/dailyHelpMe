"""Shared identifiers and bounded image decoding for user-owned chat artwork."""
import re
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImageReader, QMovie

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
        raise ValueError('PNG·JPG·WebP·GIF 이미지(1,600만 화소 이하)를 선택해주세요.')
    if bytes(reader.format()).lower() not in (b'png', b'jpeg', b'webp', b'gif'):
        raise ValueError('PNG·JPG·WebP·GIF 이미지를 선택해주세요.')
    if reader.supportsAnimation() and reader.imageCount() > 1:
        if reader.imageCount() > 300 or size.width()*size.height()*reader.imageCount() > 64000000:
            raise ValueError('움직이는 이미지는 300프레임·전체 6,400만 화소 이하로 선택해주세요.')
        for _ in range(reader.imageCount()):
            if reader.read().isNull():
                raise ValueError('움직이는 이미지를 읽지 못했어요.')
        return raw
    reader.setScaledSize(size.scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError('이미지를 읽지 못했어요.')
    result = QByteArray()
    output = QBuffer(result)
    output.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(output, 'PNG')
    return bytes(result)


def image_content_type(raw):
    if raw.startswith(b'GIF8'): return 'image/gif'
    if raw.startswith(b'RIFF') and raw[8:12] == b'WEBP': return 'image/webp'
    return 'image/png'


def artwork_movie(raw, parent, callback):
    """Keep the encoded buffer alive for Qt's streaming animation decoder."""
    buffer = QBuffer(parent)
    buffer.setData(QByteArray(raw))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    movie = QMovie(buffer, QByteArray(), parent)
    movie._buffer = buffer
    if not movie.isValid() or movie.frameCount() <= 1:
        movie.deleteLater();buffer.deleteLater()
        return None
    movie.jumpToFrame(0)
    size = movie.currentPixmap().size()
    if size.width() > 512 or size.height() > 512:
        movie.setScaledSize(size.scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio))
    movie.frameChanged.connect(lambda _: callback(movie.currentPixmap()))
    movie.start()
    return movie
