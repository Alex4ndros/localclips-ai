"""Exercise actual windowed EXE workers, including CUDA model assets and FFmpeg."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
exe = Path(os.environ.get('LOCALCLIPS_TEST_EXE',str(root / "dist" / "LocalClipsAI" / "LocalClipsAI.exe"))).resolve()
work = root / "build" / ("validation-" + str(int(time.time())))
work.mkdir(parents=True)
source = root / "examples" / "synthetic-source.mp4"
results = []

# Regression: headless workers can pass even if Qt DLL loading is broken.
gui_report = root / 'gui-startup-results.json'
gui_env = os.environ.copy()
system = Path(gui_env.get('SystemRoot', 'C:/Windows'))
gui_env['PATH'] = str(system / 'System32') + os.pathsep + str(system)
gui_env['LOCALCLIPS_DATA'] = str(work / 'gui-data')
for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'PYTHONPATH'):
    gui_env.pop(key, None)
gui_process = subprocess.run([str(exe), '--self-test-gui', str(gui_report), '--media', str(source)],
                             env=gui_env, creationflags=subprocess.CREATE_NO_WINDOW, timeout=45)
assert gui_process.returncode == 0, gui_report.read_text(encoding='utf-8') if gui_report.exists() else 'No GUI report'
gui_result = json.loads(gui_report.read_text(encoding='utf-8'))
assert gui_result['ok'] and gui_result['frozen'] and gui_result['decoded_frame'], gui_result
results.append({'action':'native_gui_and_playback', 'ok':True})


def run(action, **values):
    folder = work / action
    folder.mkdir()
    request = folder / "request.json"
    request.write_text(json.dumps({"action":action,**values}),encoding="utf-8")
    started=time.monotonic()
    process=subprocess.run([str(exe),"--worker",str(request)],capture_output=True,text=True,encoding="utf-8",errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW,timeout=120)
    (folder/'stdout.log').write_text(process.stdout,encoding='utf-8')
    (folder/'stderr.log').write_text(process.stderr,encoding='utf-8')
    assert process.returncode==0, (process.returncode,process.stdout,process.stderr)
    assert '"event": "done"' in process.stdout,process.stdout
    result=json.loads((folder/'result.json').read_text(encoding='utf-8'))
    results.append({'action':action,'seconds':round(time.monotonic()-started,3),'ok':True})
    return result


media=run('probe',path=str(source))
project={'schema':1,'media':media,'clips':[],'captions':[],'language':'','transcript_model':''}
analysis=run('analyze',project=project,options={'model':'small','device':'cuda','count':3,'minimum':5,'maximum':15})
assert analysis['device']=='cuda',analysis.get('warning')
project=analysis['project']
assert len(project['captions'])>=10 and len(project['clips'])>=2
exports=run('export',project=project,indices=[0,1],directory=str(work/'exports'),options={'encoder':'auto','width':360,'height':640,'bitrate':2})
assert len(exports['exports'])==2
assert all(e['encoder']=='h264_nvenc' for e in exports['exports'])
(root/'bundle-results.json').write_text(json.dumps({'checks':results,'exe':str(exe),'device':analysis['device'],'exports':exports},indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
