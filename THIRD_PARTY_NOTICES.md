# Third-party notices

날도와줘의 자체 소스 코드는 루트 `LICENSE`의 MIT 라이선스를 따릅니다. 아래 구성 요소와 원본 자산은 각각의 라이선스를 유지합니다. MIT 라이선스가 이 구성 요소들의 라이선스를 대체하지 않습니다.

- 기본 봉고캣 PNG: QueenDekim/bongocat, MIT. 원본 고지와 출처는 `desktop/python/assets/bongocat/`에 포함합니다. 원작 정보도 SOURCES.md에 보존합니다.
- Mulmaru 폰트: Mushsooni, SIL Open Font License 1.1. 원문과 출처는 `desktop/python/assets/fonts/`에 포함합니다.
- ThinMulmaru 폰트: BinRecycle, SIL Open Font License 1.1. 원문과 출처는 `desktop/python/assets/fonts/`에 포함합니다.
- PySide6 Essentials / Shiboken6 / Qt: LGPLv3 등 각 모듈의 라이선스. 사용 중인 Qt는 별도 동적 프레임워크로 포함됩니다. Qt 라이브러리를 수정하지 않았습니다. 관련 소스와 라이선스: https://code.qt.io/cgit/qt/qtbase.git/ 및 https://code.qt.io/cgit/pyside/pyside-setup.git/ . 버전별 소스는 해당 버전 태그에서 확인할 수 있습니다. 빌드 의존성 및 실제 버전은 배포물 `licenses/dependencies.json`에 기록합니다. 사용자가 수정한 LGPL 라이브러리로 재빌드할 수 있도록 앱 소스와 빌드 스크립트를 제공합니다.
- Python: Python Software Foundation License 등 Python 배포의 고지.
- PyInstaller bootloader: GPLv2 with bootloader exception. 배포물에 원문을 수집합니다.
- liblzma: XZ Utils, 0BSD. 배포 원문의 COPYING을 보존합니다. https://github.com/tukaani-project/xz
- libmpdec: mpdecimal, BSD 계열. 원문의 COPYRIGHT.txt를 보존합니다. https://www.bytereef.org/mpdecimal/
- SQLite: 원문의 public-domain 안내를 포함합니다. https://sqlite.org/copyright.html
- Web Push 및 암호화·HTTP 의존성: 각 패키지 원문을 배포물의 `licenses/`에 수집합니다.

실제 패키지의 라이선스 메타데이터·LICENSE/COPYING 파일은 `scripts/collect-release-licenses.py`로 수집합니다. Qt 및 Python 원문은 `licenses/`에 포함합니다. [Qt 라이선스 안내](https://doc.qt.io/qtforpython-6/licenses.html)와 [LGPL 관련 안내](https://www.qt.io/development/open-source-lgpl-obligations)도 확인할 수 있습니다.
