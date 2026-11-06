"""Copy and test the frozen application outside the source tree with a clean PATH."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
destination=Path(sys.argv[1]).resolve()
if destination.is_relative_to(root):
    raise RuntimeError('Portable test folder must be outside the repository')
destination.mkdir(parents=True,exist_ok=True)
shutil.copytree(root/'dist'/'LocalClipsAI',destination/'LocalClipsAI',dirs_exist_ok=True)
source=destination/'source-1440p.mp4'
exclusion='--exclusion' in sys.argv
shutil.copy2(root/'examples'/('no-duplicate' if exclusion else 'smart-split')/'source-1440p.mp4',source)
report=destination/'portable-gui-results.json'
env=os.environ.copy()
system=Path(env.get('SystemRoot','C:/Windows'))
env['PATH']=str(system/'System32')+os.pathsep+str(system)
env['LOCALCLIPS_DATA']=str(destination/'data')
for key in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QT_QPA_PLATFORM'):
    env.pop(key,None)
exe=destination/'LocalClipsAI'/'LocalClipsAI.exe'
process=subprocess.run([str(exe),'--self-test-gui',str(report),'--media',str(source)]+(['--exclude-webcam-test'] if exclusion else []),cwd=destination,
                       env=env,creationflags=subprocess.CREATE_NO_WINDOW,timeout=90)
result=json.loads(report.read_text(encoding='utf-8'))
assert process.returncode==0 and result['ok'],result
assert len(result['actions'])==4 and result['decoded_frame'],result
result.update(executable=str(exe),working_directory=str(destination),clean_path=env['PATH'])
if exclusion:
    assert result['live_adjustment_verified']
    import numpy as np
    results=[]
    for t in (.1,1.4,2.8):
        frame=subprocess.run([str(root/'tools'/'ffmpeg.exe'),'-v','error','-ss',str(t),'-i',result['exports'][-1],
                              '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,
                              check=True,creationflags=subprocess.CREATE_NO_WINDOW).stdout
        pixels=np.frombuffer(frame,dtype=np.uint8).reshape(1920,1080,3)
        top,bottom=pixels[:672],pixels[672:]
        pink=lambda p:(p[:,:,0]>195)&(p[:,:,1]<75)&(p[:,:,2]>165)
        orange=(bottom[:,:,0]>175)&(bottom[:,:,1]>65)&(bottom[:,:,1]<165)&(bottom[:,:,2]<90)
        black=bottom.max(axis=2)<20
        assert pink(top).sum()>1000 and pink(bottom).sum()==0 and orange.sum()==0 and black.sum()==0
        results.append({'time':t,'webcam_top_pixels':int(pink(top).sum()),'webcam_bottom_pixels':0,'black_bottom_pixels':0})
    result['exported_pixel_checks']=results
target=root/'portable-gui-results.json'
target.write_text(json.dumps(result,indent=2),encoding='utf-8')
shutil.copy2(report.with_suffix('.png'),root/'portable-gui.png')
print(json.dumps(result,indent=2))
