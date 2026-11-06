import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from localclips.domain import Clip
from localclips.media import NO_WINDOW, binary, capture, export_clip, probe
from localclips.reframing import placements, at_time


def synthetic_desktop(folder,full_desktop=False):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
    image=QImage(2560,1440,QImage.Format.Format_RGB32)
    image.fill(QColor('#175bba' if full_desktop else '#435366'))
    painter=QPainter(image)
    painter.fillRect(100,80,1100,1280,QColor('#175bba'))
    painter.fillRect(1900,1040,600,360,QColor('#e77b25'))
    painter.setPen(QColor('white'))
    painter.setFont(QFont('Arial',36))
    painter.drawText(170,180,'LOCAL MODEL - PRIVATE WORKSPACE')
    painter.drawText(170,300,'MODEL   SMALL    GPU   CUDA')
    painter.drawText(170,410,'All data stays on this computer')
    painter.setFont(QFont('Arial',24))
    painter.drawText(1940,1090,'CAMERA - BOTTOM RIGHT')
    painter.setPen(QColor('#ff00ff'))
    painter.setBrush(QColor('#ff00ff'))
    painter.drawEllipse(QRectF(2135,1155,130,130))
    painter.setPen(QColor('#ffff00'))
    painter.setBrush(QColor('#ffff00'))
    painter.drawEllipse(QRectF(570,630,160,160))
    if full_desktop:
        painter.setPen(QColor('white'))
        painter.setFont(QFont('Arial',30))
        painter.drawText(1250,260,'TERMINAL - LOCAL MODEL')
        painter.drawText(1250,365,'MODEL: SMALL  /  GPU: CUDA')
        painter.drawText(1250,470,'PRIVATE DATA - OFFLINE')
        painter.setPen(QColor('#00ff00'))
        painter.setBrush(QColor('#00ff00'))
        painter.drawEllipse(QRectF(1400,600,160,160))
    painter.end()
    png=folder/'desktop-2560x1440.png'
    image.save(str(png))
    video=folder/'obs-synthetic-1440p.mp4'
    capture([binary('ffmpeg'),'-v','error','-y','-loop','1','-framerate','60','-i',str(png),
             '-f','lavfi','-i',r'aevalsrc=if(between(t\,2\,2.2)\,0.5*sin(2*PI*440*t)\,0):s=48000:d=4',
             '-t','4','-vf',r'drawbox=x=1400:y=0:w=200:h=200:c=white:t=fill:enable=between(t\,2\,2.2)',
             '-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(video)],timeout=120)
    return video


def split_clip():
    return Clip(.5,3.5,layout='split',webcam=[1900/2560,1040/1440,600/2560,360/1440],
                screen=[100/2560,80/1440,1100/2560,1280/1440],webcam_confirmed=True,burn_captions=False)


def frame(path,w=1080,h=1920,t=.5):
    result=subprocess.run([binary('ffmpeg'),'-v','error','-ss',str(t),'-i',str(path),'-frames:v','1',
                           '-vf',f'scale={w}:{h}','-pix_fmt','rgb24','-f','rawvideo','-'],
                          capture_output=True,creationflags=NO_WINDOW,check=True)
    return np.frombuffer(result.stdout,dtype=np.uint8).reshape(h,w,3)


def inspect_split(pixels):
    # Semantic markers from source regions, not merely output metadata.
    top=pixels[:672]; bottom=pixels[672:]
    orange=(top[:,:,0]>180)&(top[:,:,1]>70)&(top[:,:,1]<165)&(top[:,:,2]<90)
    blue=(bottom[:,:,0]<60)&(bottom[:,:,1]>55)&(bottom[:,:,1]<130)&(bottom[:,:,2]>135)
    assert orange.mean()>.80
    assert blue.mean()>.80
    black=(pixels.max(axis=2)<20)
    assert black.mean()<.005 and black.mean(axis=1).max()<.03
    for region,mask in [(top,(top[:,:,0]>200)&(top[:,:,1]<70)&(top[:,:,2]>170)),
                        (bottom,(bottom[:,:,0]>200)&(bottom[:,:,1]>190)&(bottom[:,:,2]<90))]:
        ys,xs=np.where(mask)
        assert len(xs)>1000
        ratio=(xs.max()-xs.min()+1)/(ys.max()-ys.min()+1)
        assert .97<ratio<1.03, f'Circle distorted: {ratio}'


def test_real_smart_split_1440p(qt_app,tmp_path):
    source=synthetic_desktop(tmp_path)
    media=probe(source)
    assert (media.width,media.height,media.fps)==(2560,1440,60)
    clip=split_clip()
    target=tmp_path/'split-vertical.mp4'
    export_clip(media,clip,[],target,{'encoder':'auto'})
    exported=probe(target)
    assert (exported.width,exported.height,exported.has_audio)==(1080,1920,True)
    for time in (.1,1,2.5):
        inspect_split(frame(target,t=time))
    info=json.loads(capture([binary('ffprobe'),'-v','error','-show_streams','-of','json',str(target)]))
    assert info['streams'][0]['sample_aspect_ratio']=='1:1'
    capture([binary('ffmpeg'),'-v','error','-i',str(target),'-f','null','-'])
    audio=subprocess.run([binary('ffmpeg'),'-v','error','-i',str(target),'-vn','-ac','1','-ar','48000','-f','f32le','-'],
                         capture_output=True,creationflags=NO_WINDOW,check=True).stdout
    samples=np.frombuffer(audio,dtype=np.float32)
    first=np.flatnonzero(np.abs(samples)>.08)[0]/48000
    assert first==pytest.approx(1.5,abs=.06)
    # Preview and final share canonical crop geometry.
    preview=tmp_path/'proxy.mp4'
    export_clip(media,clip,[],preview,{'encoder':'cpu','width':360,'height':640,'bitrate':4})
    assert np.abs(frame(target,360,640).astype(float)-frame(preview,360,640)).mean()<4


def test_composition_keyframes_and_proportions():
    from localclips.domain import Media
    media=Media('unused',60,2560,1440,60,True)
    c=split_clip()
    c.keyframes=[{'time':2,'layout':'screen','screen_pan':[.2,.8]}]
    c.validate(media)
    assert at_time(c,1).layout=='split'
    assert at_time(c,2.1).layout=='screen'
    assert len(placements(media,c,timestamp=1))==2
    assert len(placements(media,c,timestamp=2.1))==1
    assert placements(media,Clip(0,10),timestamp=0)[0].target==(0,0,1080,1920)


def test_dynamic_and_separate_camera(qt_app,tmp_path):
    source=synthetic_desktop(tmp_path)
    media=probe(source)
    c=split_clip()
    c.keyframes=[{'time':2,'layout':'screen'}]
    target=tmp_path/'dynamic.mp4'
    export_clip(media,c,[],target,{'encoder':'cpu','width':360,'height':640})
    a=frame(target,360,640,t=.5)
    b=frame(target,360,640,t=2)
    assert a[:220,:,0].mean()>180
    assert b[:,:,2].mean()>140 and b[:,:,0].mean()<70
    cam=tmp_path/'cam.mp4'
    capture([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=lime:s=640x480:d=5:r=30',
             '-c:v','libx264','-pix_fmt','yuv420p',str(cam)])
    c.keyframes=[]
    c.camera_path=str(cam)
    c.camera_offset=.5
    c.webcam=[0,0,1,1]
    target=tmp_path/'separate.mp4'
    export_clip(media,c,[],target,{'encoder':'cpu','width':360,'height':640})
    pixels=frame(target,360,640)
    assert pixels[:220,:,1].mean()>230 and pixels[:220,:,0].mean()<20
    assert pixels[230:,:,2].mean()>140
    assert probe(target).has_audio


def test_smooth_tracking_matches_export(qt_app,tmp_path):
    from localclips.reframing import track_value
    source=synthetic_desktop(tmp_path)
    media=probe(source)
    c=split_clip()
    c.face_track=[{'time':.5,'x':.70,'y':.70},{'time':3.4,'x':.75,'y':.70}]
    c.validate(media)
    assert track_value(c.face_track,1.95,'x')==pytest.approx(.725)
    target=tmp_path/'tracked.mp4'
    export_clip(media,c,[],target,{'encoder':'cpu','width':360,'height':640})
    # At the midpoint, moving crop agrees with a still composition using the
    # interpolated ROI. Check exported pixels, not just expression strings.
    reference=tmp_path/'reference.mp4'
    c2=at_time(c,1.95)
    c2.face_track=[]
    export_clip(media,c2,[],reference,{'encoder':'cpu','width':360,'height':640})
    assert np.abs(frame(target,360,640,t=1.45).astype(float)-frame(reference,360,640,t=1.45)).mean()<5


def test_no_duplicate_webcam_in_actual_export(qt_app,tmp_path):
    from localclips.reframing import fill_crop,intersects,overlay_bounds
    source=synthetic_desktop(tmp_path,full_desktop=True)
    media=probe(source)
    c=split_clip()
    c.screen=[0,0,1,1]
    c.screen_pan=[1,1]  # old code deliberately includes the original OBS overlay
    raw=fill_crop(media,c.screen,1080,1248,c.screen_pan)
    original=(1900,1040,600,360)
    assert intersects(raw,original)
    assert raw[0]<2200<raw[0]+raw[2] and raw[1]<1220<raw[1]+raw[3]
    plan=placements(media,c)
    assert not intersects(plan[1].crop,overlay_bounds(media,c,c.start))
    output=tmp_path/'single-webcam-1080p.mp4'
    export_clip(media,c,[],output,{'encoder':'auto'})
    measurements=[]
    for t in (.1,1.4,2.8):
        pixels=frame(output,t=t)
        top,bottom=pixels[:672],pixels[672:]
        def magenta(p): return (p[:,:,0]>195)&(p[:,:,1]<75)&(p[:,:,2]>165)
        orange=(bottom[:,:,0]>175)&(bottom[:,:,1]>65)&(bottom[:,:,1]<165)&(bottom[:,:,2]<90)
        blue=(bottom[:,:,0]<65)&(bottom[:,:,1]>50)&(bottom[:,:,1]<140)&(bottom[:,:,2]>140)
        black=bottom.max(axis=2)<20
        assert magenta(top).sum()>1000
        assert magenta(bottom).sum()==0 and orange.sum()==0
        assert blue.mean()>.9 and black.sum()==0
        # The content marker remains circular after the corrective crop.
        green=(bottom[:,:,0]<70)&(bottom[:,:,1]>180)&(bottom[:,:,2]<90)
        ys,xs=np.where(green)
        assert len(xs)>1000
        assert .97<(xs.max()-xs.min()+1)/(ys.max()-ys.min()+1)<1.03
        measurements.append({'time':t,'webcam_top_pixels':int(magenta(top).sum()),
                             'webcam_bottom_pixels':int(magenta(bottom).sum()+orange.sum()),
                             'black_bottom_pixels':int(black.sum()),'screen_coverage':float(blue.mean())})
    result=probe(output)
    assert (result.width,result.height,result.has_audio)==(1080,1920,True)
    capture([binary('ffmpeg'),'-v','error','-i',str(output),'-f','null','-'])
    capture([binary('ffmpeg'),'-v','error','-ss','1','-i',str(output),'-frames:v','1',str(tmp_path/'exported-frame.png')])
    proxy=tmp_path/'single-webcam-proxy.mp4'
    export_clip(media,c,[],proxy,{'encoder':'cpu','width':360,'height':640})
    assert np.abs(frame(output,360,640).astype(float)-frame(proxy,360,640)).mean()<4
    (tmp_path/'pixel-report.json').write_text(json.dumps({'legacy_crop':raw,'corrected_crop':plan[1].crop,'frames':measurements},indent=2))


@pytest.mark.parametrize('webcam',[[.75,.70,.25,.30],[0,.70,.25,.30],[0,0,.25,.30],[.75,0,.25,.30],[.4,.4,.2,.2]])
def test_exclusion_all_positions_zoom_and_pan(webcam):
    from localclips.domain import Media
    from localclips.reframing import intersects,overlay_bounds
    m=Media('unused',10,2560,1440,60,True)
    for pan in ([0,0],[.5,.5],[1,1]):
        for zoom in (1,1.5,3):
            c=Clip(0,5,layout='split',webcam=webcam,screen_pan=pan,screen_zoom=zoom)
            for target in ((1080,1920),(360,640)):
                lower=placements(m,c,*target)[1]
                assert not intersects(lower.crop,overlay_bounds(m,c,0))
                assert lower.target[1]+lower.target[3]==target[1]


def test_overlap_only_roi_fallback_and_impossible_case():
    from localclips.domain import Media
    from localclips.reframing import intersects,overlay_bounds,CompositionError
    m=Media('unused',10,1920,1080,30,True)
    c=Clip(0,5,layout='split',webcam=[.75,.7,.25,.3],screen=[.75,.7,.25,.3])
    assert not intersects(placements(m,c)[1].crop,overlay_bounds(m,c,0))
    c.webcam=[0,0,1,1]
    with pytest.raises(CompositionError):placements(m,c)


def test_static_exclusion_during_tracking_and_keyframes():
    from localclips.domain import Media
    from localclips.reframing import intersects,overlay_bounds
    m=Media('unused',6,2560,1440,60,True)
    c=Clip(0,5,layout='split',webcam=[.72,.72,.25,.25],screen_pan=[1,1],
           face_track=[{'time':0,'x':.68,'y':.7},{'time':4.9,'x':.75,'y':.75}])
    crop=placements(m,c,timestamp=0)[1].crop
    for t in (0,1,2.5,4.9):
        assert placements(m,c,timestamp=t)[1].crop==crop
        assert not intersects(crop,overlay_bounds(m,c,t))
    c.face_track=[]
    c.keyframes=[{'time':2.5,'webcam':[0,.7,.25,.3]}]
    assert not intersects(placements(m,c,timestamp=3)[1].crop,overlay_bounds(m,c,3))


def test_separate_webcam_preserves_explicit_obs_exclusion():
    from localclips.domain import Media,Project
    from localclips.reframing import intersects,overlay_bounds
    m=Media('unused',6,2560,1440,60,True)
    c=Clip(0,5,layout='split',camera_path='independent.mp4',webcam=[0,0,1,1],screen_pan=[1,1],embedded_webcam=[.75,.7,.25,.3])
    c=Project.from_dict(Project(m,[c]).to_dict()).clips[0]
    camera=Media('independent.mp4',6,640,480,30,False)
    assert not intersects(placements(m,c,camera=camera)[1].crop,overlay_bounds(m,c,0))
    c.embedded_webcam=None
    assert overlay_bounds(m,c,0) is None
