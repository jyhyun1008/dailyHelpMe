"""Inspect actual Mach-O load commands instead of guessing distribution support."""
from pathlib import Path
from macholib.MachO import MachO

MAGICS = (b'\xcf\xfa\xed\xfe',b'\xfe\xed\xfa\xcf',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf')
ARCHES = {16777228:'arm64',16777223:'x86_64'}


def audit_bundle(bundle):
    seen, records, minimums, common = set(), [], [], None
    for path in sorted(Path(bundle).rglob('*')):
        if not path.is_file() or path.resolve() in seen:continue
        seen.add(path.resolve())
        with path.open('rb') as file:magic=file.read(4)
        if magic not in MAGICS:continue
        archs, versions = set(), []
        for header in MachO(str(path)).headers:
            archs.add(ARCHES.get(header.header.cputype,str(header.header.cputype)))
            for load,command,data in header.commands:
                version=getattr(command,'minos',None) or (getattr(command,'version',None) if load.cmd==0x24 else None)
                if version:versions.append((version>>16,(version>>8)&255,version&255))
        common = archs if common is None else common & archs
        minimums.extend(versions)
        records.append({'path':str(path.relative_to(bundle)),'architectures':sorted(archs),'minimum_macos':'.'.join(map(str,max(versions))) if versions else None})
    if not records or not common:raise RuntimeError('배포 번들의 CPU 구성이 올바르지 않습니다.')
    minimum=max(minimums)
    return {'architectures':sorted(common),'minimum_macos':'.'.join(map(str,minimum)),'binaries':records}
