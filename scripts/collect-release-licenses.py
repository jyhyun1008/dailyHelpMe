"""Collect installed runtime package license files and exact dependency metadata."""
import json
import shutil
import sys
from importlib.metadata import distribution
from pathlib import Path
from packaging.requirements import Requirement

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/release-licenses'
if OUT.exists():shutil.rmtree(OUT)
OUT.mkdir(parents=True)
packages={}
queue=['PySide6-Essentials','pywebpush','pyinstaller','setuptools']
while queue:
    name=queue.pop()
    dist=distribution(name)
    key=dist.metadata['Name']
    if key in packages:continue
    packages[key]={'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License',''),'project_urls':dist.metadata.get_all('Project-URL') or []}
    for file in dist.files or []:
        relative=Path(str(file))
        if relative.is_absolute() or '..' in relative.parts:continue
        if any('license' in part.lower() or 'copying' in part.lower() for part in relative.parts):
            source=Path(dist.locate_file(file))
            if source.is_file():
                target=OUT/key/relative
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    if name!='pyinstaller':
        for value in dist.requires or []:
            requirement=Requirement(value)
            if not requirement.marker or requirement.marker.evaluate({'extra':''}):queue.append(requirement.name)
for folder in ['fonts','bongocat']:
    source=ROOT/'desktop/python/assets'/folder
    dest=OUT/folder;dest.mkdir()
    for path in source.iterdir():
        if path.suffix.lower() in ('.md','.txt'):shutil.copyfile(path,dest/path.name)
for path in (ROOT/'licenses').glob('*'):
    if path.is_file():shutil.copyfile(path,OUT/path.name)
shutil.copyfile(ROOT/'LICENSE',OUT/'DailyHelpMe-MIT.txt')
(OUT/'dependencies.json').write_text(json.dumps({'python':sys.version,'packages':packages},ensure_ascii=False,indent=2)+'\n')
print('Collected release licenses for',len(packages),'packages')
