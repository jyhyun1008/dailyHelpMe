# 공개 GitHub 배포 절차

현재 준비 버전은 `0.1.0-beta.2`입니다. 이 문서는 공개 업로드를 자동 실행하지 않습니다.

## 지금 확인된 제한

- 개발 맥에서 만든 파일은 **arm64 / macOS 26 이상**입니다. 번들 안의 Python·Qt·OpenSSL 등을 모두 검사한 결과이며, Intel·구형 macOS 지원으로 표시하면 안 됩니다. 다른 macOS 버전용 빌드에는 그 버전에서 동작하는 Python과 Qt 휠을 사용하고 동일한 검사를 실행해야 합니다. Mach-O의 최소 버전 숫자만 낮추지 마세요.
- 현재 Apple Developer Program 계정과 Developer ID 인증서는 없습니다. 첫 배포는 이를 명시하는 **미공증 베타**로 준비합니다. ad-hoc 서명은 파일 무결성 확인용이며 Apple Developer ID 서명이나 공증을 대신하지 않습니다. GitHub에 미공증 앱을 배포하는 것과 Apple 공증은 별개이며, 첫 실행 시 macOS 안내가 나올 수 있습니다.
- 소스와 버전 태그가 아직 확정되지 않은 작업 트리에서 만든 준비용 파일입니다. 릴리스 태그는 검증한 소스 커밋과 일치해야 합니다.
- 다른 맥에서 다운로드한 파일을 새로 설치하는 검증과 실제 기기의 모바일 푸시 검증이 남아 있습니다.

## 로컬 준비 패키지

```bash
npm run pet:test
npm run pet:release
```

`dist/DailyHelpMe-0.1.0-beta.2-macos-arm64/`에 ZIP·DMG, 설치·개인정보·라이선스 안내, `release.json`, 실제 바이너리별 지원 OS를 기록한 `binary-audit.json`, SHA256 체크섬과 릴리스 설명을 생성합니다. DMG는 앱과 응용 프로그램 폴더로 이동하는 링크를 포함합니다. 파일명은 빌드의 실제 CPU에 따라 달라집니다.

개발용 환경에 설치된 Qt Addons가 배포물에 섞이지 않도록 쓰지 않는 PDF·가상 키보드 플러그인을 빌드 훅에서 제외합니다. 패키징 시 해당 모듈이 남아 있으면 중단합니다.

패키지는 작업 폴더 전체가 아니라 `build/날도와줘.app`과 공개 문서만 포함합니다. 앱 번들에 DB·인증 파일로 보이는 파일이 있으면 생성을 중단합니다. `.env`, `.local-backups/`, 개인 계정의 Codex 인증 폴더나 앱 데이터 폴더를 ZIP에 직접 넣지 마세요.

## 버전과 의존성

`desktop/python/branding.py`의 APP_VERSION·BUILD_NUMBER와 루트 package.json/package-lock.json의 버전을 함께 갱신합니다. 앱 정보에도 버전이 표시됩니다. 빌드 시 사용한 의존성 버전은 앱 내부 `Contents/Resources/licenses/dependencies.json`에 수집합니다. Python·Qt를 바꾼 빌드는 테스트와 최소 macOS 검사를 다시 수행합니다.

## 추후 Apple 서명과 공증 추가

먼저 Apple Developer 계정에서 **Developer ID Application** 인증서와 개인 키를 이 빌드 맥의 키체인에 준비합니다. 인증서·키·앱 전용 비밀번호를 저장소나 채팅에 올리지 않습니다. 다음 환경변수는 인증서 이름만 지정합니다.

```bash
security find-identity -v -p codesigning
DAILYHELPME_SIGN_IDENTITY='Developer ID Application: … (TEAMID)' npm run pet:build
codesign --verify --deep --strict 'build/날도와줘.app'
```

서명 빌드 경로는 hardened runtime과 Python 동적 모듈에 필요한 entitlements를 적용하도록 구성했습니다. 인증서가 없어 해당 경로와 공증 성공은 아직 실증하지 않았습니다.

`xcrun notarytool store-credentials`로 키체인 프로필을 준비한 뒤, 서명된 앱의 ZIP을 만들어 `xcrun notarytool submit ... --keychain-profile ... --wait`로 제출합니다. **Accepted** 상태와 notary log를 확인한 후 `xcrun stapler staple`·`validate`로 앱에 티켓을 붙입니다. 패키지를 다시 만들고 DMG도 제출·staple·validate합니다. 최종 DMG와 ZIP을 수정했다면 체크섬을 다시 생성해야 합니다. 준비용 `release.json`의 공증 false 표시는 자동으로 성공했다고 바꾸지 않습니다. 실증 결과와 함께 최종 메타데이터·설명을 갱신하세요.

공식 절차: [Apple 공증 문서](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution), [Gatekeeper와 앱 실행 안내](https://support.apple.com/102445).

## 공개 직전

1. 다른 맥의 새 사용자 환경에서 설치·실행, Codex 설치/로그인 실패 안내, 대화·일기 저장, 업데이트 후 데이터 유지, 모바일 연결을 확인합니다.
2. 실제 CPU·최소 OS·서명/공증 여부를 릴리스 설명에 반영합니다. Intel 빌드가 없으면 지원 목록에서 제외합니다.
3. MIT 원문과 서드파티 고지를 확인합니다. Qt 등 외부 구성 요소는 MIT로 재라이선스하지 않습니다. 원본 소스와 재빌드 방법을 유지합니다.
4. 준비한 앱 소스와 문서를 검토·커밋하고 깨끗한 작업 트리에서 다시 빌드·검증합니다. 소스 커밋에 `v0.1.0-beta.2` 태그를 연결합니다. 현재 원격 저장소의 과거 Node 앱 커밋에 새 Python 바이너리 태그를 붙이지 않습니다.
5. GitHub Release를 **prerelease**로 작성하고 ZIP·DMG·SHA256·설치/개인정보 문서를 올립니다. 최종 확인 전에는 draft 상태로 둡니다.

기본 배포 명령은 GitHub에 파일을 올리거나 태그·릴리스를 만들지 않습니다.
