"""Inspect encoded caption pixels on a bright/complex screen, not just ASS text."""
import copy
import json
from pathlib import Path
import numpy as np
from localclips.domain import Caption,Clip,Project,Word
from localclips.media import binary,capture,probe,export_clip
from localclips.subtitles import write_ass,text_area
from test_reframing import frame,split_clip,synthetic_desktop


def test_readable_subtitles_export(qt_app,tmp_path):
    desktop=synthetic_desktop(tmp_path,full_desktop=True)
    source=tmp_path/'bright-obs.mp4'
    capture([binary('ffmpeg'),'-v','error','-y','-i',str(desktop),
             '-vf','drawbox=x=0:y=850:w=1800:h=500:color=white:t=fill,drawgrid=w=120:h=120:t=1:color=gray',
             '-c:v','libx264','-preset','fast','-crf','18','-c:a','copy',str(source)])
    media=probe(source)
    clip=split_clip()
    clip.screen=[0,0,1,1]
    clip.screen_pan=[1,1]
    clip.burn_captions=True
    captions=[Caption(.7,1.8,'I tuoi dati restano sul computer.'),
              Caption(2,3.2,'Modelli locali: più privacy, nessun cloud.')]
    for c in captions:
        words=c.text.split()
        step=(c.end-c.start)/len(words)
        c.words=[Word(c.start+i*step,c.start+(i+1)*step,w) for i,w in enumerate(words)]
    output=tmp_path/'readable-1080p.mp4'
    baseline=tmp_path/'without-subtitles.mp4'
    export_clip(media,clip,captions,output,{'encoder':'cpu'})
    plain=copy.deepcopy(clip)
    plain.burn_captions=False
    export_clip(media,plain,[],baseline,{'encoder':'cpu'})
    observations=[]
    for t,active in ((.1,False),(.4,True),(1.4,False),(1.8,True),(2.85,False)):
        pixels=frame(output,t=t)
        original=frame(baseline,t=t)
        delta=np.abs(pixels.astype(float)-original.astype(float)).max(axis=2)>45
        # Ignore tiny inter-frame codec differences elsewhere; require captions
        # inside the original safe margins and wholly below the camera pane.
        roi=delta[1100:1700]
        ys,xs=np.where(roi)
        if active:
            assert len(xs)>1000
            box=[int(xs.min()),int(ys.min()+1100),int(xs.max()),int(ys.max()+1100)]
            assert box[0]>=79 and box[2]<=941
            assert box[1]>1250 and box[3]<=1596
            # Black contour is visible even where the white text meets white desktop.
            ink=(pixels[1300:1600].max(axis=2)<45)&roi[200:500]
            assert ink.sum()>500
            assert delta[:672].mean()<.001  # upper webcam geometry is unchanged
            observations.append({'time':t,'text_bounds':box,'dark_edge_pixels':int(ink.sum())})
        else:
            assert roi.sum()<100
            observations.append({'time':t,'caption_visible':False})
    for t,name in ((.4,'caption-1.png'),(1.8,'caption-2.png')):
        capture([binary('ffmpeg'),'-v','error','-ss',str(t),'-i',str(output),'-frames:v','1',str(tmp_path/name)])
    proxy=tmp_path/'readable-proxy.mp4'
    export_clip(media,clip,captions,proxy,{'encoder':'cpu','width':360,'height':640,'bitrate':4})
    assert np.abs(frame(output,360,640,t=.4).astype(float)-frame(proxy,360,640,t=.4)).mean()<4
    ass=tmp_path/'captions.ass'
    write_ass(ass,captions,clip)
    text=ass.read_text(encoding='utf-8-sig')
    assert 'Arial,66,' in text and ',1,4,1,2,85,145,330,1' in text
    assert r'\fad' not in text and r'\kf' not in text
    srt=output.with_suffix('.srt').read_text(encoding='utf-8-sig')
    assert '00:00:00,200 --> 00:00:01,300' in srt
    assert '00:00:01,500 --> 00:00:02,700' in srt
    capture([binary('ffmpeg'),'-v','error','-i',str(output),'-f','null','-'])
    assert probe(output).has_audio
    Project(media,[clip],captions).save(tmp_path/'readability.lcproj')
    (tmp_path/'caption-checks.json').write_text(json.dumps({'font_size':66,'increase_percent':round((66/58-1)*100,1),
        'outline':4,'shadow':1,'margin_bottom':330,'observations':observations},indent=2))


def test_live_caption_controls_and_multiline(qt_app,tmp_path,monkeypatch):
    from PySide6.QtGui import QFontDatabase,QFont
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
    from localclips.ui import Window
    from localclips.domain import Media
    from localclips.preview import caption_path
    monkeypatch.setenv('LOCALCLIPS_DATA',str(tmp_path))
    window=Window()
    window.project=Project(Media('unused',20,2560,1440,60,True),[Clip(0,10)])
    window.current_clip=0
    window.font_combo.setCurrentFont(QFont('Arial'))
    window.outline.setValue(4)
    window.shadow.setValue(2)
    window.font_size.setValue(66)
    window.color.setText('#FFFFFF')
    window.margin_v.setValue(330)
    draft=window.draft_clip()
    assert (draft.font_size,draft.outline,draft.shadow,draft.margin_v)==(66,4,2,330)
    text='Modelli linguistici locali: proteggi la privacy e mantieni tutti i tuoi dati sul computer.'
    bounds=caption_path(text,draft).boundingRect()
    x,w,bottom=text_area(draft)
    assert bounds.left()>=x-1 and bounds.right()<=x+w+1 and bounds.bottom()<=bottom
    window.readable_captions()
    assert window.shadow.value()==1 and window.outline.value()==4
    window.dirty=False
    window.close()
