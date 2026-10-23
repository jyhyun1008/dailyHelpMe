"""Package only the built app and public docs; never archive the working tree."""
import hashlib
import json
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from bundle_audit import audit_bundle

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/python'))
from branding import APP_VERSION,BUILD_NUMBER
APP=ROOT/'build/날도와줘.app'
with (APP/'Contents/Info.plist').open('rb') as file:info=plistlib.load(file)
if info.get('DailyHelpMeVersion')!=APP_VERSION or info.get('CFBundleVersion')!=BUILD_NUMBER:
    raise SystemExit('앱 버전이 소스와 다릅니다. 먼저 npm run pet:build를 실행해주세요.')
subprocess.run(['codesign','--verify','--deep','--strict',str(APP)],check=True)
# Prevent accidental bundling of local data or developer credentials.
for path in APP.rglob('*'):
    if path.is_file() and (path.name in ('.env','auth.json','credentials.json','doa.sqlite3') or path.suffix in ('.db','.sqlite','.sqlite3','.p12','.key') or (path.suffix=='.pem' and not (path.name=='cacert.pem' and 'certifi' in path.parts)) or path.name.endswith(('-wal','-shm'))):
        raise SystemExit('배포 대상에 개인 데이터로 보이는 파일이 있습니다: '+path.name)
for unused in ('QtVirtualKeyboard','QtVirtualKeyboardQml','QtPdf','QtQuick','QtQml'):
    if (APP/'Contents/Frameworks'/unused).exists():
        raise SystemExit('사용하지 않는 Qt 추가 모듈이 번들에 있습니다: '+unused)
audit=audit_bundle(APP)
if info.get('LSMinimumSystemVersion')!=audit['minimum_macos']:
    raise SystemExit('실제 최소 macOS 버전과 앱 메타데이터가 다릅니다. 다시 빌드해주세요.')
arch='universal2' if set(audit['architectures'])=={'arm64','x86_64'} else '-'.join(audit['architectures'])
name=f'DailyHelpMe-{APP_VERSION}-macos-{arch}'
output=ROOT/'dist'/name
output.mkdir(parents=True,exist_ok=True)
# Only replace artifacts belonging to this release, leaving other versions alone.
for filename,source in [('INSTALL.md','docs/INSTALL.md'),('PRIVACY.md','docs/PRIVACY.md'),('THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.md'),('LICENSE','LICENSE')]:
    shutil.copyfile(ROOT/source,output/filename)
subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(APP),str(output/(name+'.zip'))],check=True)
staging=ROOT/'build/release-staging'
if staging.exists():shutil.rmtree(staging)
staging.mkdir()
subprocess.run(['ditto',str(APP),str(staging/APP.name)],check=True)
(staging/'Applications').symlink_to('/Applications')
shutil.copyfile(ROOT/'docs/INSTALL.md',staging/'설치 안내.md')
subprocess.run(['hdiutil','create','-volname','DailyHelpMe','-srcfolder',str(staging),'-ov','-format','UDZO',str(output/(name+'.dmg'))],check=True)
signature=subprocess.run(['codesign','-dv','--verbose=4',str(APP)],capture_output=True,text=True,check=True).stderr
signed='Authority=Developer ID Application:' in signature
revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip())
metadata={'name':'날도와줘','english_name':'DailyHelpMe!!','version':APP_VERSION,'build':BUILD_NUMBER,'architectures':audit['architectures'],'minimum_macos':audit['minimum_macos'],'developer_id_signed':signed,'notarized':False,'git_revision':revision,'working_tree_dirty':dirty,'release_mode':'unnotarized-beta' if not signed else 'developer-id-unnotarized','public_release_ready':False,'pending_checks':['source_commit_and_tag','clean_machine_install']}
(output/'release.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
(output/'binary-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
notes=f'''# 날도와줘 {APP_VERSION}

데스크톱 펫, 일정·2차 일정·루틴, 일기, ChatGPT 계정의 Codex 대화와 웹 검색, 커스텀 이모지·스티커를 포함하는 첫 베타입니다.

- CPU: {arch}
- 최소 macOS: {audit['minimum_macos']}
- 앱 실행에 Python 설치 불필요. AI 기능에는 별도 Codex CLI와 사용자의 ChatGPT 로그인이 필요합니다.
- Developer ID 서명: {'있음' if signed else '없음 (로컬 ad-hoc 서명)'}
- Apple 공증: 아직 진행하지 않음
- 자동 업데이트: 미지원

INSTALL.md·PRIVACY.md·THIRD_PARTY_NOTICES.md를 함께 확인해주세요. 데이터는 기존 DOA Pet 폴더를 사용합니다.

현재 산출물은 미공증 베타입니다. 공개 전에는 다른 맥의 새 설치 검증과 정확한 소스 커밋·태그 연결을 완료하고 미공증 상태를 명시합니다. Developer ID와 Apple 공증은 추후 추가할 수 있습니다. 현재 작업 트리에서 만든 준비용 산출물이며, 소스 커밋·태그가 확정되면 다시 빌드합니다. 소스 커밋: {revision}; 미커밋 변경: {dirty}.
'''
(output/'RELEASE_NOTES.md').write_text(notes)
checks=[]
for path in sorted(output.iterdir()):
    if path.is_file() and path.name!='SHA256SUMS.txt':
        checks.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name)
(output/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n')
print('Prepared:',output)
print('Requires macOS',audit['minimum_macos'],arch)
print('Public release ready: false (clean source tag and fresh-machine install check still required; unnotarized beta)')
