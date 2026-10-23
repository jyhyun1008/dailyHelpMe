"""Keep a widgets-only build free of optional PDF and virtual-keyboard plugins."""
from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
# A development environment can also contain Qt Addons/WebEngine used by tests.
# Those optional image/keyboard plugins are not used by this app.
excluded = {'libqtvirtualkeyboardplugin.dylib','libqpdf.dylib','libqsvg.dylib','libqsvgicon.dylib'}
binaries = [(source,target) for source,target in binaries if Path(source).name not in excluded]
