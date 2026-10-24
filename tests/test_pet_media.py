"""Image persistence, inline layout and sticker isolation from inference."""
import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/python'))
from PySide6.QtCore import QByteArray,QBuffer,QIODevice,QPoint,QSettings,Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from chat_media import normalize_image,emoji_token
from store import Store
from app import Companion


def sample_png():
    image=QImage(40,30,QImage.Format.Format_ARGB32);image.fill(QColor('#d64289'))
    output=QByteArray();buffer=QBuffer(output);buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG')
    return bytes(output)


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt=QApplication.instance() or QApplication([])
        cls.qt.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,self.temp.name)
        QSettings('Cybermaid','DOAPet').clear()
        self.path=Path(self.temp.name)/'test.db'
        self.store=Store(self.path)
        self.companion=Companion(self.store)
        self.companion.timer.stop();self.companion.pet.motion.stop()

    def tearDown(self):
        if self.companion.worker:self.companion.worker.wait(3000)
        self.companion.dispose();self.qt.processEvents();self.store.db.close();self.temp.cleanup()

    def test_animated_webp_and_gif_preserved_and_played(self):
        from media_picker import ArtworkButton
        from chat_media import image_content_type
        for extension in ('webp', 'gif'):
            with self.subTest(extension=extension):
                raw = (Path(__file__).parent / 'fixtures' / ('animated.' + extension)).read_bytes()
                self.assertEqual(normalize_image(raw), raw)
                self.assertEqual(image_content_type(raw), 'image/' + extension)
                key = self.store.add_media('emoji', extension, normalize_image(raw))
                self.assertEqual(self.store.media_image(key), raw)
                asset = next(a for a in self.store.media_assets() if a['id'] == key)
                button = ArtworkButton(asset, raw, lambda: None)
                self.assertIsNotNone(button.movie)
                composer = self.companion.panel.input
                composer.insert_emoji(key, raw)
                messages = self.companion.panel.messages
                messages.set_media(self.store)
                movie = messages.media_movies[key]
                movie.jumpToFrame(0)
                first = movie.currentPixmap().toImage().pixelColor(0, 0)
                self.assertTrue(movie.jumpToFrame(1))
                self.assertNotEqual(first, messages.media_pixmaps[key].toImage().pixelColor(0, 0))
                self.assertTrue(button.movie.jumpToFrame(1))
                self.assertTrue(composer.emoji_movies[key].jumpToFrame(1))
                self.assertIn(emoji_token(key), composer.message_text())
                button.deleteLater()

    def test_image_validation_and_archive_preserves_history(self):
        with self.assertRaises(ValueError):normalize_image(b'<svg onload="bad"/>')
        with self.assertRaises(ValueError):normalize_image(b'a'*(4*1024*1024+1))
        png=normalize_image(sample_png())
        key=self.store.add_media('sticker','인사',png)
        self.companion.send_sticker(key)
        self.store.archive_media(key)
        self.assertEqual(self.store.media_assets(),[])
        self.assertEqual(self.store.media_image(key),png)
        self.assertEqual(self.store.history()[-1]['sticker']['id'],key)
        with self.assertRaises(ValueError):self.store.send_sticker(key)
        self.store.db.close();self.store=Store(self.path);self.companion.store=self.store;self.companion.panel.store=self.store
        self.assertEqual(self.store.history()[-1]['sticker']['id'],key)
        self.assertEqual(self.store.media_image(key),png)

    def test_sticker_never_requests_ai_and_text_emoji_has_named_context(self):
        key=self.store.add_media('sticker','웃음',normalize_image(sample_png()))
        emoji=self.store.add_media('emoji','기쁨',normalize_image(sample_png()))
        with patch('app.request_reply') as request,patch.object(self.companion,'start_reply') as start:
            self.companion.send_sticker(key)
            start.assert_not_called();request.assert_not_called()
        self.assertEqual(self.store.context()['history'],[])
        self.store.message('user','오늘 '+emoji_token(emoji)+' 기분 좋아')
        context=self.store.context()
        self.assertEqual(context['history'][0]['content'],'오늘 [이모지: 기쁨] 기분 좋아')
        day=self.store.history()[-1]['created_at'][:10]
        self.assertEqual(len(self.store.diary_draft_context(day)['history']),1)
        self.assertNotIn('png',str(context))

    def test_native_picker_register_insert_and_sticker(self):
        from media_picker import MediaPicker
        path=Path(self.temp.name)/'custom.png';path.write_bytes(sample_png())
        picker=MediaPicker(self.companion,self.companion.panel)
        picker.name.setText('새 이모지')
        with patch('media_picker.QFileDialog.getOpenFileName',return_value=(str(path),'PNG')):
            picker.choose()
        asset=self.store.media_assets()[0]
        self.assertEqual(asset['name'],'새 이모지')
        self.companion.panel.input.insertPlainText('반가워 ')
        picker.select(asset)
        self.assertEqual(self.companion.panel.input.message_text(),'반가워 '+emoji_token(asset['id']))
        sticker_picker=MediaPicker(self.companion,self.companion.panel)
        sticker_picker.kind.setCurrentIndex(1);sticker_picker.name.setText('새 스티커')
        with patch('media_picker.QFileDialog.getOpenFileName',return_value=(str(path),'PNG')):
            sticker_picker.choose()
        sticker=self.store.media_assets()[-1]
        with patch.object(self.companion,'start_reply') as start:
            sticker_picker.select(sticker)
            start.assert_not_called()
        self.assertEqual(self.store.history()[-1]['sticker']['name'],'새 스티커')

    def test_inline_composer_render_and_elastic_hover_returns_to_original(self):
        png=normalize_image(sample_png())
        emoji=self.store.add_media('emoji','인사',png)
        sticker=self.store.add_media('sticker','큰 인사',png)
        composer=self.companion.panel.input
        composer.insertPlainText('안녕 ');composer.insert_emoji(emoji,png);composer.insertPlainText(' 반가워')
        text='안녕 '+emoji_token(emoji)+' 반가워'
        self.assertEqual(composer.message_text(),text)
        with patch.object(self.companion,'start_reply') as start:
            self.companion.send()
            start.assert_called_once()
        self.assertEqual(self.store.history()[-1]['content'],text)
        self.companion.send_sticker(sticker)
        panel=self.companion.panel;panel.show_page(1);panel.show();self.qt.processEvents()
        view=panel.messages
        view.viewport().update();self.qt.processEvents()
        self.assertEqual(len(view.media_hits),2)
        # Inline image occupies its own text object, without displaying raw tokens.
        row=view.item(0);message=row.data(Qt.ItemDataRole.UserRole+1)
        doc,width,height,boxes=view.itemDelegate().rich(250,message)
        self.assertEqual(len(boxes),1)
        self.assertNotIn(':emoji_',doc.toPlainText())
        self.assertIn('안녕',doc.toPlainText());self.assertIn('반가워',doc.toPlainText())
        rect,key,_=view.media_hits[-1]
        QTest.mouseMove(view.viewport(),rect.center().toPoint());QTest.qWait(330)
        self.assertEqual(view.hovered_media,key)
        self.assertAlmostEqual(view.media_scales[key],1.08,places=2)
        QTest.mouseMove(view.viewport(),QPoint(1,1));QTest.qWait(330)
        self.assertIsNone(view.hovered_media)
        self.assertAlmostEqual(view.media_scales.get(key,1.0),1.0,places=2)
        self.assertEqual(view.visualItemRect(row).height(),view.sizeHintForRow(0))


if __name__=='__main__':unittest.main()
