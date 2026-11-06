"""Isolated worker. JSONL progress on stdout, diagnostics on stderr, no GUI imports."""
import json
import logging
import re
import sys
from pathlib import Path
from dataclasses import asdict

from .domain import Project, atomic_json
from .media import probe, extract_audio, export_clip
from .selection import propose


def emit(kind, **values):
    print(json.dumps({"event": kind, **values}, ensure_ascii=False), flush=True)


def main(request_path):
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    folder = Path(request_path).parent
    logging.basicConfig(filename=folder / "worker.log", level=logging.INFO, encoding="utf-8")
    progress = lambda value, message: emit("progress", value=value, message=message)
    try:
        action = request["action"]
        options = request.get("options", {})
        if action in ("probe", "probe_camera"):
            progress(None, "Lettura metadati video…")
            result = asdict(probe(request["path"], options.get("tool_dir", "")))
        elif action == "download":
            from .transcription import download
            result = download(options["model"], progress)
        elif action == "analyze":
            from .transcription import transcribe
            project = Project.from_dict(request["project"])
            if not project.captions or options.get("retranscribe"):
                audio = folder / "audio.wav"
                try:
                    extract_audio(project.media, audio, options.get("tool_dir", ""), lambda v, m: progress(v * .1, "Estrazione audio · " + m))
                    captions, language, device, warning = transcribe(audio, options.get("model", "small"), options.get("device", "auto"), options.get("language", "auto"),
                        lambda v, m: progress(None if v is None else .1 + v * .73, m))
                    project.captions, project.language = captions, language
                    project.transcript_model = options.get("model", "small")
                finally:
                    audio.unlink(missing_ok=True)
            else:
                device, warning = "cache", "Trascrizione salvata riutilizzata."
            progress(.84, "Selezione su confini di frase…")
            # Persist expensive local work even when an optional provider fails.
            project.save(folder/'transcription-recovery.lcproj')
            if options.get('ai_mode','offline')=='offline':
                project.clips = propose(project.captions, project.media.duration, options.get("count", 5), options.get("minimum", 20), options.get("maximum", 60))
            else:
                from .semantic import select
                project.clips = select(project.captions,project.media.duration,options,
                    lambda v,m:progress(.85+.05*v,m))
            if options.get('vision', True):
                from .vision import analyze_video, apply_detection
                for i, clip in enumerate(project.clips):
                    try:
                        report = analyze_video(project.media, clip.start, clip.end,
                            lambda v,m: progress(.90+.09*(i+v)/max(1,len(project.clips)),m))
                        if not apply_detection(clip, report, options.get('dynamic',False)):
                            clip.reason += ' Webcam non affidabile: seleziona la regione manualmente.'
                        atomic_json(folder / f'vision-{clip.uid}.json', report)
                    except Exception as exc:
                        logging.exception('Vision unavailable')
                        warning += ' Visione non disponibile: ' + str(exc)
                        break
            from .media import thumbnail
            for i,clip in enumerate(project.clips):
                progress(.99,f'Miniatura {i+1}/{len(project.clips)}')
                clip.thumbnail=thumbnail(project.media,clip,folder/f'{clip.uid}.jpg',options.get('tool_dir',''))
            result = {"project": project.to_dict(), "device": device, "warning": warning}
        elif action == 'detect':
            from .vision import analyze_video
            project = Project.from_dict(request['project'])
            clip = project.clips[request['index']]
            if clip.camera_path:
                raise ValueError('Per una sorgente webcam separata seleziona manualmente la regione.')
            result = analyze_video(project.media, clip.start, clip.end, progress)
        elif action=='signin':
            from .auth import sign_in
            progress(None,'Completa l’accesso nel browser. Nessuna trascrizione viene inviata durante l’accesso.')
            result=sign_in(options.get('account',''),options.get('allow_plan',False),lambda url:emit('auth_url',url=url))
        elif action=='signout':
            from .auth import sign_out
            result=sign_out(options['account'])
        elif action=='models':
            from .semantic import model_catalog
            result=model_catalog(options)
        elif action in ("export", "preview"):
            project = Project.from_dict(request["project"])
            indices = request["indices"]
            if not indices:
                raise ValueError("Nessuna clip selezionata.")
            results = []
            export_dir = Path(request["directory"]).resolve()
            export_dir.mkdir(parents=True, exist_ok=True)
            for position, index in enumerate(indices):
                clip = project.clips[index]
                stem = re.sub(r"[^\w -]", "", clip.title, flags=re.UNICODE).strip()[:60] or "clip"
                target = export_dir / f"{stem}_{clip.uid}.mp4"
                # Every run preserves existing exports with a numbered name.
                number = 2
                while target.exists() or target.with_suffix(".srt").exists():
                    target = export_dir / f"{stem}_{clip.uid}_{number}.mp4"
                    number += 1
                result_clip = export_clip(project.media, clip, project.captions, target, options,
                        lambda v, m: progress((position + v) / len(indices), f"Clip {position+1}/{len(indices)} · {m}"))
                results.append(result_clip)
                emit("exported", **result_clip)
            result = {"exports": results}
        else:
            raise ValueError("Operazione non supportata.")
        atomic_json(folder / "result.json", result)
        emit("done", result_path=str(folder / "result.json"))
        return 0
    except Exception as exc:
        logging.exception("Worker failure")
        emit("error", message=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
