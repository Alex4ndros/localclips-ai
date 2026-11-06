import json
import threading
from pathlib import Path

import pytest
from localclips.domain import Caption, Clip, Media, Project, Word
from localclips.media import Cancelled, binary, capture, export_clip, layout_filter, probe, run_progress
from localclips.selection import propose
from localclips.subtitles import write_ass, write_srt, clock


def test_import_mp4(video):
    m = probe(video)
    assert (m.width, m.height, m.has_audio) == (640,360,True)
    assert m.duration == pytest.approx(6, abs=.1)
    assert m.fps == 30


def test_project_roundtrip(video, tmp_path):
    m = probe(video)
    p = Project(m, [Clip(.2,3,layout="split")], [Caption(.5,1.8,"Privacy locale.", [Word(.5,1,"Privacy"),Word(1,1.8,"locale.")])])
    path = tmp_path / "progetto.lcproj"
    p.save(path)
    assert Project.load(path) == p
    bad = p.to_dict()
    bad["schema"] = 99
    with pytest.raises(ValueError):
        Project.from_dict(bad)


def test_invalid_timing_and_rect():
    media = Media("x", 60,1920,1080,30,True)
    for clip in (Clip(4,3), Clip(-1,5), Clip(0,100), Clip(0,10,webcam=[.9,.9,.5,.5]), Clip(float("nan"),3)):
        with pytest.raises(ValueError):
            clip.validate(media)


def test_ranking_non_overlapping_complete_sentences():
    captions = [Caption(i*5,i*5+4, "Perché un modello locale protegge la privacy?" if i%2 else "Bitcoin e decentralizzazione sono importanti.") for i in range(24)]
    clips = propose(captions,120,5,10,25)
    # Repeated identical explanations should yield one distinct proposal.
    assert len(clips) == 1
    for i,c in enumerate(clips):
        assert 10 <= c.duration <= 25.3
        assert 0 <= c.score <= 100
        assert any(abs(c.start-max(0,cap.start-.1)) < .001 for cap in captions)
        assert any(abs(c.end-min(120,cap.end+.12)) < .001 for cap in captions)
        for other in clips[i+1:]:
            assert c.end <= other.start or c.start >= other.end


def test_no_fake_proposals_on_silence():
    assert propose([],60) == []
    assert propose([Caption(0,30,"una frase senza conclusione")],60) == []


def test_subtitles_rebased_and_clipped(tmp_path):
    captions = [Caption(9,12,"Uno due tre", [Word(9,9.8,"Uno"),Word(10.1,10.8,"due"),Word(11,12,"tre")])]
    clip = Clip(10,11.5,style="Dynamic")
    write_srt(tmp_path/"a.srt",captions,clip)
    text = (tmp_path/"a.srt").read_text(encoding="utf-8-sig")
    assert "00:00:00,000 --> 00:00:01,500" in text
    assert "due tre" in text and "Uno" not in text
    write_ass(tmp_path/"a.ass",captions,clip)
    ass = (tmp_path/"a.ass").read_text(encoding="utf-8-sig")
    assert r"\kf70" in ass
    assert "PlayResY: 1920" in ass
    assert clock(59.9996) == "00:01:00,000"


@pytest.mark.parametrize("layout", ["fit","crop","split","pip"])
def test_export_layout_with_audio_and_subtitles(video, tmp_path, layout):
    media = probe(video)
    clip = Clip(.5,2.5,layout=layout,style="Dynamic",webcam=[.75,.70,.25,.30])
    captions = [Caption(.7,2.1,"Privacy e LLM", [Word(.7,1,"Privacy"),Word(1,1.3,"e"),Word(1.3,2.1,"LLM")])]
    target = tmp_path / f"output {layout} à.mp4"
    observed = []
    result = export_clip(media,clip,captions,target,{"width":360,"height":640,"encoder":"cpu","bitrate":2},lambda p,m: observed.append(p))
    actual = probe(target)
    assert (actual.width,actual.height,actual.has_audio) == (360,640,True)
    assert actual.duration == pytest.approx(2,abs=.1)
    assert result["encoder"] == "libx264"
    assert observed[-1] == 1
    assert target.with_suffix(".srt").is_file()
    info = json.loads(capture([binary("ffprobe"),"-v","error","-show_streams","-of","json",str(target)]))
    assert {s["codec_name"] for s in info["streams"]} == {"h264","aac"}
    # Decoding the complete stream catches corrupt but probe-able containers.
    capture([binary("ffmpeg"),"-v","error","-i",str(target),"-f","null","-"])


def test_export_no_overwrite(video,tmp_path):
    target = tmp_path/"existing.mp4"
    target.write_bytes(b"keep me")
    with pytest.raises(ValueError):
        export_clip(probe(video),Clip(0,1),[],target)
    assert target.read_bytes() == b"keep me"


def test_cancellation_terminates_ffmpeg(tmp_path):
    cancel = threading.Event()
    timer = threading.Timer(.35,cancel.set)
    timer.start()
    try:
        with pytest.raises(Cancelled):
            run_progress([binary("ffmpeg"),"-v","error","-re","-f","lavfi","-i","testsrc2=s=320x240:r=30:d=60",
                          "-progress","pipe:1","-f","null","-"],60,cancel=cancel)
    finally:
        timer.cancel()


def test_cancel_export_leaves_no_partial(video,tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        export_clip(probe(video),Clip(0,5),[],tmp_path/"cancel.mp4",{"encoder":"cpu","width":360,"height":640},cancel=cancel)
    assert not list(tmp_path.iterdir())


def test_video_without_audio_gets_silent_aac(tmp_path):
    source = tmp_path/"silent.mp4"
    capture([binary("ffmpeg"),"-v","error","-f","lavfi","-i","color=c=blue:s=320x240:d=1","-c:v","libx264",str(source)])
    target = tmp_path/"out.mp4"
    export_clip(probe(source),Clip(0,1),[],target,{"encoder":"cpu","width":360,"height":640})
    assert probe(target).has_audio


def test_audio_video_flash_alignment(tmp_path):
    import numpy as np
    import subprocess
    from localclips.media import NO_WINDOW
    source=tmp_path/'sync.mp4'
    capture([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=30:d=3',
             '-f','lavfi','-i',r'aevalsrc=if(between(t\,1.5\,1.7)\,0.5*sin(2*PI*440*t)\,0):s=48000:d=3',
             '-vf',r'drawbox=c=white:t=fill:enable=between(t\,1.5\,1.7)','-c:v','libx264','-c:a','aac',str(source)])
    target=tmp_path/'sync-out.mp4'
    export_clip(probe(source),Clip(.5,2.5),[],target,{'encoder':'cpu','width':360,'height':640})
    def raw(args):
        p=subprocess.run([binary('ffmpeg'),'-v','error','-i',str(target),*args],capture_output=True,creationflags=NO_WINDOW,check=True)
        return p.stdout
    audio=np.frombuffer(raw(['-vn','-ac','1','-ar','48000','-f','f32le','-']),dtype=np.float32)
    frames=np.frombuffer(raw(['-an','-vf','scale=36:64','-pix_fmt','gray','-f','rawvideo','-']),dtype=np.uint8).reshape(-1,64,36)
    sound_time=np.flatnonzero(np.abs(audio)>.08)[0]/48000
    flash_time=np.flatnonzero(frames.mean(axis=(1,2))>30)[0]/30
    assert sound_time==pytest.approx(1,abs=.06)
    assert abs(sound_time-flash_time)<.06


def test_nvenc_failure_retries_cpu(video,tmp_path,monkeypatch):
    import localclips.media as module
    original=module.run_progress
    attempts=[]
    def run(args,*a,**kw):
        attempts.append(args[args.index('-c:v')+1])
        if 'h264_nvenc' in args:
            raise RuntimeError('Simulated encoder failure')
        return original(args,*a,**kw)
    monkeypatch.setattr(module,'nvenc_available',lambda _:True)
    monkeypatch.setattr(module,'run_progress',run)
    result=export_clip(probe(video),Clip(0,1),[],tmp_path/'fallback.mp4',{'width':360,'height':640})
    assert attempts==['h264_nvenc','libx264']
    assert result['encoder']=='libx264'


def test_source_replaced_is_rejected(video,tmp_path):
    import shutil
    copy=tmp_path/'source.mp4'
    shutil.copy2(video,copy)
    media=probe(copy)
    with copy.open('ab') as f:
        f.write(b'changed')
    with pytest.raises(ValueError,match='modificato'):
        export_clip(media,Clip(0,1),[],tmp_path/'out.mp4')
