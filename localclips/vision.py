"""Local OBS webcam proposals: YuNet + persistence/corner priors, never identity recognition."""
from pathlib import Path
import math
import numpy as np
import cv2
from types import SimpleNamespace
from .paths import models_root
from .reframing import screen_crop


def face_detector():
    path=models_root()/'vision'/'yunet.onnx'
    if not path.is_file():
        raise RuntimeError('Modello YuNet assente. Usa la selezione manuale delle regioni.')
    return cv2.FaceDetectorYN.create(str(path),'',(640,360),.80,.3,500)


def detect_frame(frame,detector):
    h,w=frame.shape[:2]
    scale=min(1.,1280/w)
    small=cv2.resize(frame,(round(w*scale),round(h*scale)))
    detector.setInputSize((small.shape[1],small.shape[0]))
    _,faces=detector.detect(small)
    return [[float(f[0]/scale/w),float(f[1]/scale/h),float(f[2]/scale/w),float(f[3]/scale/h),float(f[-1])] for f in faces] if faces is not None else []


def expand_face(face):
    x,y,w,h=face[:4]
    cx,cy=x+w/2,y+h/2
    rw,rh=min(.45,w*3.2),min(.60,h*2.6)
    return [max(0,min(1-rw,cx-rw/2)),max(0,min(1-rh,cy-rh*.5)),rw,rh]


def corner(face):
    x,y,w,h=face[:4]
    cx,cy=x+w/2,y+h/2
    return (0 if cx<.35 else 1 if cx>.65 else -1,0 if cy<.40 else 1 if cy>.60 else -1)


def screen_region(frame,webcam):
    """Favor persistent text/edge density outside the webcam; return an editable ROI."""
    h,w=frame.shape[:2]
    small=cv2.resize(frame,(320,180))
    edges=cv2.Canny(small,60,140).astype(float)
    x,y,rw,rh=webcam
    edges[int(y*180):int((y+rh)*180),int(x*320):int((x+rw)*320)]=0
    # Group text/controls into useful desktop blocks; this is visual salience,
    # not a claim to recognize a particular browser or terminal application.
    blocks=cv2.dilate(edges.astype(np.uint8),np.ones((7,15),np.uint8))
    contours,_=cv2.findContours(blocks,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    seeds=[[float(left),.03,.45,.94] for left in np.linspace(0,.55,8)]
    for contour in contours:
        bx,by,bw,bh=cv2.boundingRect(contour)
        if bw*bh<320*180*.035:continue
        l,t=max(0,bx-8),max(0,by-8)
        r,b=min(320,bx+bw+8),min(180,by+bh+8)
        seeds.append([l/320,t/180,(r-l)/320,(b-t)/180])
    best=(-1,[0,0,1,1])
    m=SimpleNamespace(width=w,height=h)
    obstacle=(max(0,int(x*w)-6),max(0,int(y*h)-6),min(w,int(rw*w)+12),min(h,int(rh*h)+12))
    total=max(1,float(edges.sum()))
    for rect in seeds:
        px,py,pw,ph=screen_crop(m,rect,1080,1248,obstacle=obstacle)
        patch=edges[int(py/h*180):max(int((py+ph)/h*180),int(py/h*180)+1),int(px/w*320):max(int((px+pw)/w*320),int(px/w*320)+1)]
        if not patch.size:continue
        # Reward text density and coverage, but penalize excessive magnification.
        score=float(patch.mean())+30*float(patch.sum())/total+8*min(1,pw/(w*.45))
        if score>best[0]:best=(score,[px/w,py/h,pw/w,ph/h])
    return best[1]


def analyze_video(media,start=0,end=None,progress=lambda *_:None,max_samples=48):
    end=min(media.duration,end if end is not None else media.duration)
    detector=face_detector()
    capture=cv2.VideoCapture(media.path)
    if not capture.isOpened():
        raise RuntimeError('OpenCV non riesce ad aprire il video per l’analisi visiva.')
    count=min(max_samples,max(4,math.ceil((end-start)/3)))
    samples=[]
    tracks={}
    previous=None
    reference=None
    try:
        for i,t in enumerate(np.linspace(start,max(start,end-.05),count)):
            capture.set(cv2.CAP_PROP_POS_MSEC,float(t)*1000)
            ok,frame=capture.read()
            if not ok:
                continue
            reference=frame if reference is None else reference
            faces=detect_frame(frame,detector)
            gray=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(160,90))
            scene=float(np.abs(gray.astype(float)-previous).mean()/255) if previous is not None else 0.
            previous=gray.astype(float)
            entry={'time':float(t),'faces':faces,'scene_change':scene}
            samples.append(entry)
            for face in faces:
                group=corner(face)
                if -1 in group or face[2]*face[3]>.12:
                    continue
                tracks.setdefault(group,[]).append((float(t),face))
            progress((i+1)/count,f'Visione locale · campione {i+1}/{count}')
    finally:
        capture.release()
    ranked=[]
    for group,track in tracks.items():
        # Count distinct times, not multiple website faces in one corner frame.
        persistence=len({round(t,3) for t,_ in track})/max(len(samples),1)
        centers=np.array([[f[0]+f[2]/2,f[1]+f[3]/2] for _,f in track])
        stability=max(0,1-float(centers.std(axis=0).mean())*8)
        probability=float(np.median([f[-1] for _,f in track]))
        confidence=.5*persistence+.25*stability+.25*probability
        ranked.append((confidence,track))
    ranked.sort(key=lambda item:item[0],reverse=True)
    if not ranked:
        return {'confidence':0.,'reliable':False,'reason':'Nessun volto persistente in un angolo. Seleziona la webcam manualmente.','samples':samples,'webcam':None,'screen':None,'track':[]}
    confidence,track=ranked[0]
    ambiguous=len(ranked)>1 and ranked[1][0]>confidence-.12
    if ambiguous:
        confidence*=.6
    median=np.median(np.array([f[:4] for _,f in track]),axis=0).tolist()
    roi=expand_face(median)
    screen=screen_region(reference,roi)
    # Exponential smoothing and dead zone avoid face-detector jitter.
    smoothed=[]
    previous=None
    for t,face in track:
        rect=np.array(expand_face(face))
        if previous is not None:
            delta=np.abs(rect[:2]-previous[:2]).max()
            rect=previous if delta<.012 else previous*.75+rect*.25
        previous=rect
        smoothed.append({'time':t,'rect':rect.tolist()})
    return {'confidence':round(confidence,3),'reliable':confidence>=.78 and len(track)>=3,
            'reason':'Volto persistente in un angolo; regione stimata attorno al volto, da verificare.' if not ambiguous else 'Più volti persistenti: impossibile distinguere con affidabilità webcam e pagina web.',
            'webcam':roi,'screen':screen,'track':smoothed,'samples':samples}


def apply_detection(clip,result,dynamic=False):
    if not result['reliable']:
        return False
    clip.webcam=result['webcam']
    # Freeze the whole proposed OBS region independently from tracked face pan.
    regions=[result['webcam']]+[s['rect'] for s in result['track']]
    x,y=min(r[0] for r in regions),min(r[1] for r in regions)
    right,bottom=max(r[0]+r[2] for r in regions),max(r[1]+r[3] for r in regions)
    clip.embedded_webcam=[x,y,right-x,bottom-y]
    clip.screen=result['screen']
    clip.webcam_confirmed=True
    clip.layout='dynamic' if dynamic else 'split'
    clip.keyframes=[]
    # Fixed crop dimensions, smoothed center path. FFmpeg and live preview use
    # the same continuous interpolation; no per-frame neural inference needed.
    w,h=clip.webcam[2:]
    clip.face_track=[]
    for sample in result['track']:
        t=sample['time']
        if clip.start<=t<clip.end:
            x,y,rw,rh=sample['rect']
            clip.face_track.append({'time':t,'x':max(0,min(1-w,x+rw/2-w/2)),
                                    'y':max(0,min(1-h,y+rh/2-h/2))})
    last=clip.start-8
    for sample in result['samples']:
        t=sample['time']
        if not clip.start<=t<clip.end or t-last<6 or len(clip.keyframes)>=20:
            continue
        tracked=min(result['track'],key=lambda x:abs(x['time']-t)) if result['track'] else None
        key={'time':t,'layout':('screen' if sample['scene_change']>.12 else 'split') if dynamic else 'split'}
        if dynamic and (not clip.keyframes or key['layout']!=clip.keyframes[-1]['layout']):
            clip.keyframes.append(key)
            last=t
    return True
