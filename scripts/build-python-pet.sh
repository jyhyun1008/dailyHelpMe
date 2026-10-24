#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv-pet/bin/python ]]; then
  echo '먼저 npm run pet:start로 Python 환경을 준비해주세요.' >&2
  exit 1
fi
# Generate both native and installed-web icons from the same root logo.
.venv-pet/bin/python scripts/generate-brand-icons.py
iconutil -c icns "$PWD/build/DailyHelpMe.iconset" -o "$PWD/build/DailyHelpMe.icns"
.venv-pet/bin/python scripts/collect-release-licenses.py
PET_SIGN_ARGS=(--noconfirm)
if [[ -n "${DAILYHELPME_SIGN_IDENTITY:-}" ]]; then
  PET_SIGN_ARGS+=(--codesign-identity "$DAILYHELPME_SIGN_IDENTITY" --osx-entitlements-file "$PWD/scripts/macos-entitlements.plist")
fi
export PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller-cache"
.venv-pet/bin/python -m PyInstaller --windowed --name 'DailyHelpMe' \
  "${PET_SIGN_ARGS[@]}" --distpath build --workpath build/python-work --specpath build \
  --additional-hooks-dir "$PWD/scripts/pyinstaller-hooks" --osx-bundle-identifier com.cybermaid.doapet --icon "$PWD/build/DailyHelpMe.icns" \
  --add-data "$PWD/desktop/python/assets:desktop/python/assets" \
  --add-data "$PWD/desktop/python/mobile:mobile" \
  --add-data "$PWD/build/release-licenses:licenses" \
  --add-data "$PWD/docs:docs" --add-data "$PWD/LICENSE:." \
  --add-data "$PWD/THIRD_PARTY_NOTICES.md:." desktop/python/app.py
# Localized product names; keep the existing bundle identifier for installed users.
.venv-pet/bin/python - <<'PYBRAND'
import plistlib
import sys
sys.path.insert(0,"desktop/python")
sys.path.insert(0,"scripts")
from branding import APP_VERSION, BUILD_NUMBER
from bundle_audit import audit_bundle
from pathlib import Path
bundle = Path('build/DailyHelpMe.app/Contents')
path = bundle / 'Info.plist'
with path.open('rb') as file: info = plistlib.load(file)
info.update(CFBundleShortVersionString=APP_VERSION.split('-')[0], CFBundleVersion=BUILD_NUMBER, DailyHelpMeVersion=APP_VERSION, LSMinimumSystemVersion=audit_bundle(bundle.parent)['minimum_macos'], CFBundleName='DailyHelpMe!!', CFBundleDisplayName='날도와줘', CFBundleDevelopmentRegion='ko', CFBundleLocalizations=['ko','en'])
with path.open('wb') as file: plistlib.dump(info,file)
for locale,name in [('ko','날도와줘'),('en','DailyHelpMe!!')]:
    resources = bundle / 'Resources' / (locale + '.lproj')
    resources.mkdir(exist_ok=True)
    (resources / 'InfoPlist.strings').write_text('"CFBundleDisplayName" = "' + name + '";\n"CFBundleName" = "' + name + '";\n',encoding='utf-8')
PYBRAND
if [[ -n "${DAILYHELPME_SIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp --entitlements "$PWD/scripts/macos-entitlements.plist" --sign "$DAILYHELPME_SIGN_IDENTITY" "$PWD/build/DailyHelpMe.app"
else
  codesign --force --deep --sign - "$PWD/build/DailyHelpMe.app"
fi
# Keep Mach-O executable names ASCII; localize the app shown in Finder instead.
.venv-pet/bin/python - <<'PYMOVE'
from pathlib import Path
import shutil
source = Path('build/DailyHelpMe.app')
target = Path('build/날도와줘.app')
if target.exists(): shutil.rmtree(target)
source.rename(target)
PYMOVE
# Build directly into the canonical location so removed assets cannot linger in a merged bundle.
touch "$PWD/build/날도와줘.app"
codesign --verify --deep --strict "$PWD/build/날도와줘.app"
# Finder users also launch the staging copy; never leave it on an older build.
.venv-pet/bin/python - <<'PYSTAGING'
from pathlib import Path
import shutil
import subprocess
staging = Path('build/release-staging')
staging.mkdir(exist_ok=True)
target = staging / '날도와줘.app'
if target.exists(): shutil.rmtree(target)
subprocess.run(['ditto', 'build/날도와줘.app', str(target)], check=True)
PYSTAGING
printf 'Built: %s/build/날도와줘.app\n' "$PWD"
