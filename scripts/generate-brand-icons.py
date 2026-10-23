"""Derive reproducible app/PWA sizes from the user-provided root logo."""
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]
app=QApplication.instance() or QApplication([])
source=QImage(str(ROOT/'dailyhelpme_logo.png'))
if source.isNull():raise SystemExit('dailyhelpme_logo.png를 읽지 못했어요.')
background=source.pixelColor(source.width()//2,2)
background.setAlpha(255)
branding=ROOT/'desktop/python/assets/branding'
mobile=ROOT/'desktop/python/mobile'
branding.mkdir(parents=True,exist_ok=True)


def render(path,size,scale=1.0,opaque=False):
    image=QImage(size,size,QImage.Format.Format_ARGB32)
    image.fill(background if opaque else Qt.GlobalColor.transparent)
    painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    side=size*scale
    painter.drawImage(QRectF((size-side)/2,(size-side)/2,side,side),source)
    painter.end()
    if not image.save(str(path),'PNG'):raise SystemExit(f'Could not save {path}')


render(branding/'app-icon.png',1024,.82)
render(mobile/'icon.png',192,opaque=True)
render(mobile/'icon-512.png',512,opaque=True)
render(mobile/'icon-maskable-512.png',512,.74,opaque=True)
render(mobile/'apple-touch-icon.png',180,opaque=True)
render(mobile/'favicon.png',32,opaque=True)
iconset=ROOT/'build/DailyHelpMe.iconset'
iconset.mkdir(parents=True,exist_ok=True)
app_icon=QImage(str(branding/'app-icon.png'))
for size in (16,32,128,256,512):
    for factor,suffix in ((1,''),(2,'@2x')):
        image=app_icon.scaled(size*factor,size*factor,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
        if not image.save(str(iconset/f'icon_{size}x{size}{suffix}.png')):raise SystemExit('Icon conversion failed')
print('Generated 날도와줘 / DailyHelpMe!! app and PWA icons')
