"""Actual model test, separate from fast unit tests. Supply a local speech WAV."""
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localclips.transcription import transcribe
from localclips.domain import Project, Caption, Word
from localclips.media import probe, export_clip, capture, binary
from localclips.selection import propose


def main():
    root = Path(__file__).resolve().parents[1]
    wav = Path(sys.argv[1]).resolve()
    destination = root / "examples"
    destination.mkdir(exist_ok=True)
    report = {}
    transcripts = {}
    for requested in ("cpu", "cuda"):
        started = time.monotonic()
        captions, language, actual, warning = transcribe(wav, "small", requested, "auto")
        text = " ".join(c.text for c in captions).lower()
        assert "privacy" in text and "computer" in text and "model" in text
        assert language == "en"
        assert actual == requested, warning
        assert all(c.start < c.end and c.words for c in captions)
        assert all(a.end <= b.start for a,b in zip(captions,captions[1:]))
        transcripts[requested] = captions
        report[requested] = {"seconds":round(time.monotonic()-started,3),"language":language,"captions":len(captions),
                             "words":sum(len(c.words) for c in captions), "device":actual}
    source = destination / "synthetic-source.mp4"
    capture([binary("ffmpeg"),"-v","error","-y","-f","lavfi","-i","testsrc2=s=1280x720:r=30",
             "-i",str(wav),"-vf","drawbox=x=960:y=500:w=320:h=220:color=0x146850:t=fill,drawtext=text='SYNTHETIC WEBCAM':fontcolor=white:fontsize=22:x=990:y=600",
             "-c:v","h264_nvenc","-b:v","3M","-c:a","aac","-shortest",str(source)],timeout=120)
    media = probe(source)
    captions = transcripts["cuda"]
    clips = propose(captions,media.duration,3,5,15)
    assert len(clips) >= 2
    for clip in clips:
        clip.layout="split"
        clip.webcam=[.75,500/720,.25,220/720]
        clip.screen=[0,0,.75,1]
        clip.style="Dynamic"
    project = Project(media,clips,captions,"en","small")
    project.save(destination/"example.lcproj")
    checked = Project.load(destination/"example.lcproj")
    assert len(checked.captions)==len(captions)
    results=[]
    for i,fps in enumerate((30,60)):
        target=destination/f"vertical-{fps}fps.mp4"
        if target.exists() or target.with_suffix('.srt').exists():
            raise RuntimeError('Use a fresh examples directory for this validation.')
        result=export_clip(media,clips[i],captions,target,{"fps":fps,"encoder":"nvenc","width":1080,"height":1920})
        assert result["encoder"]=="h264_nvenc"
        actual=probe(target)
        assert actual.fps==fps and actual.width==1080 and actual.height==1920 and actual.has_audio
        capture([binary("ffmpeg"),"-v","error","-i",str(target),"-f","null","-"],timeout=120)
        results.append(result)
    report['exports']=results
    report['scope']='English offline synthetic speech; not a quality benchmark for Italian OBS recordings.'
    (root/'inference-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
