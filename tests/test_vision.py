from pathlib import Path
import cv2
import numpy as np
from localclips.media import capture, binary, probe
from localclips.vision import analyze_video, apply_detection
from localclips.domain import Clip


def make_face_video(tmp_path, ambiguous=False):
    astronaut=cv2.imread(str(Path(__file__).parent/'assets'/'astronaut.png'))
    assert astronaut is not None
    image=np.full((720,1280,3),90,np.uint8)
    # Real NASA face in a small corner webcam; an additional centered face must
    # not steal the webcam. Two persistent corners must trigger ambiguity.
    image[440:696,1000:1256]=cv2.resize(astronaut,(256,256))
    if ambiguous:
        image[440:696,20:276]=cv2.resize(astronaut,(256,256))
    else:
        image[230:486,450:706]=cv2.resize(astronaut,(256,256))
    png=tmp_path/'faces.png'
    cv2.imwrite(str(png),image)
    video=tmp_path/'faces.mp4'
    capture([binary('ffmpeg'),'-v','error','-loop','1','-i',str(png),'-t','3','-r','10',
             '-c:v','libx264','-pix_fmt','yuv420p',str(video)])
    return probe(video)


def test_webcam_real_face_corner(tmp_path):
    media=make_face_video(tmp_path)
    report=analyze_video(media)
    assert report['reliable'] and report['confidence']>.78
    assert report['webcam'][0]>.65 and report['webcam'][1]>.5
    clip=Clip(0,3)
    assert apply_detection(clip,report)
    clip.validate(media)
    assert clip.layout=='split' and clip.webcam_confirmed
    from localclips.reframing import placements
    face=next(f for f in report['samples'][0]['faces'] if f[0]>.65)
    x,y,w,h=placements(media,clip)[0].crop
    fx,fy,fw,fh=face[:4]
    # Real detector face box plus headroom stays inside the upper crop.
    assert x<=(fx-.1*fw)*media.width and x+w>=(fx+1.1*fw)*media.width
    assert y<=(fy-.1*fh)*media.height and y+h>=(fy+1.1*fh)*media.height


def test_ambiguous_webcams_require_manual(tmp_path):
    report=analyze_video(make_face_video(tmp_path,True))
    assert not report['reliable']
    clip=Clip(0,3)
    assert not apply_detection(clip,report)
    assert clip.layout=='screen' and not clip.webcam_confirmed


def test_no_face_requires_manual(video):
    report=analyze_video(probe(video))
    assert not report['reliable']
