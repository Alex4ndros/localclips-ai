"""Refresh documentation and integrity manifest without recompiling unchanged code."""
import hashlib
import json
import shutil
from pathlib import Path

root=Path(__file__).resolve().parents[1]
target=root/'dist'/'LocalClipsAI'
for name in ('README.md','STATUS.md','WEBCAM-FIX.md','THIRD_PARTY_NOTICES.md','test-results.xml','inference-results.json','bundle-results.json','portable-gui-results.json','requirements-lock.txt'):
    shutil.copy2(root/name,target/name)
if (root/'gui-startup-results.json').exists():
    shutil.copy2(root/'gui-startup-results.json',target/'gui-startup-results.json')
shutil.copytree(root/'licenses',target/'licenses',dirs_exist_ok=True)
manifest={}
for path in sorted(target.rglob('*')):
    if path.is_file() and path.name!='manifest.json' and 'data' not in path.relative_to(target).parts:
        with path.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        manifest[str(path.relative_to(target))]={'bytes':path.stat().st_size,'sha256':digest}
(target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'files':len(manifest),'size_GB':round(sum(v['bytes'] for v in manifest.values())/10**9,2),
                  'exe_sha256':manifest['LocalClipsAI.exe']['sha256']}))
