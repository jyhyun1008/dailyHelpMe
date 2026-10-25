"""Lay out inline artwork as text objects; animate artwork without moving text."""
from html import escape
from message_formatting import emphasis_html
from typography import EMPHASIS_STYLESHEET
from PySide6.QtCore import QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import QImage, QTextDocument, QTextOption
from chat_media import TOKEN


def rich_layout(text, max_width, text_font, color, assets, emphasis=False):
    document = QTextDocument()
    document.setDocumentMargin(0)
    document.setDefaultFont(text_font)
    document.setDefaultStyleSheet(EMPHASIS_STYLESHEET)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    document.setDefaultTextOption(option)
    render = emphasis_html if emphasis else escape
    parts, images, start = [], [], 0
    blank = QImage(26,26,QImage.Format.Format_ARGB32)
    blank.fill(Qt.GlobalColor.transparent)
    for match in TOKEN.finditer(text):
        asset_id = match[1]
        asset = assets.get(asset_id)
        if not asset or asset['kind'] != 'emoji':
            continue
        parts.append(render(text[start:match.start()]).replace('\n','<br>'))
        key = 'emoji:' + str(len(images))
        document.addResource(QTextDocument.ResourceType.ImageResource,QUrl(key),blank)
        parts.append(f'<img src="{key}" width="26" height="26">')
        images.append((asset_id, asset['name']))
        start = match.end()
    parts.append(render(text[start:]).replace('\n','<br>'))
    document.setHtml('<span style="color:'+color+'">'+''.join(parts)+'</span>')
    document.setTextWidth(max_width)
    width = min(max_width,max(20,document.idealWidth()))
    document.setTextWidth(width)
    boxes = []
    block = document.begin()
    image_index = 0
    while block.isValid():
        iterator = block.begin()
        block_top = document.documentLayout().blockBoundingRect(block).top()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                offset = fragment.position()-block.position()
                line = block.layout().lineForTextPosition(offset)
                cursor_x = line.cursorToX(offset)
                x = cursor_x[0] if isinstance(cursor_x,tuple) else cursor_x
                asset_id, name = images[image_index]
                boxes.append((QRectF(x,block_top+line.y()+line.ascent()-26,26,26), asset_id, name, image_index))
                image_index += 1
            iterator += 1
        block = block.next()
    return document, width, document.size().height(), boxes


def draw_artwork(painter, rect, pixmap, scale):
    if pixmap.isNull():
        return
    size = pixmap.size().scaled(rect.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
    target = QRectF(0,0,size.width()*scale,size.height()*scale)
    target.moveCenter(rect.center())
    painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
    painter.drawPixmap(target,pixmap,QRectF(pixmap.rect()))
