from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections import deque
from pathlib import Path


def thumbnail(media,clip,target,tool_dir=''):
    """One actual composited frame, generated in the worker, not the GUI thread."""
    import copy
    from .reframing import filter_graph
    c=copy.deepcopy(clip)
    c.keyframes=[]
    c.face_track=[]
    graph=filter_graph(media,c,180,320)
    capture([binary('ffmpeg',tool_dir),'-v','error','-y','-ss',str(c.start),'-i',media.path,
             '-filter_complex',graph,'-map','[base]','-frames:v','1',str(target)])
    return str(target)

from .domain import Media, Clip
from .paths import app_root
from .subtitles import write_ass, write_srt

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class Cancelled(Exception):
    pass


def binary(name, directory=""):
    filename = name + (".exe" if os.name == "nt" else "")
    candidates = ([Path(directory) / filename] if directory else []) + [app_root() / "tools" / filename]
    for p in candidates:
        if p.is_file():
            return str(p.resolve())
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"{name} non trovato. Seleziona nelle impostazioni la cartella contenente ffmpeg.exe e ffprobe.exe.")


def capture(args, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=timeout, creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:] or result.stdout[-5000:] or "Processo non riuscito.")
    return result.stdout


def probe(path, tool_dir=""):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("File video non trovato.")
    info = json.loads(capture([binary("ffprobe", tool_dir), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]))
    video = next((s for s in info["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    if not video:
        raise ValueError("Il file non contiene una traccia video.")
    duration = float(info.get("format", {}).get("duration", video.get("duration", 0)))
    if duration <= 0:
        raise ValueError("Impossibile determinare la durata del video.")
    numerator, denominator = map(float, video.get("avg_frame_rate", "30/1").split("/"))
    width, height = int(video["width"]), int(video["height"])
    rotation = next((abs(int(s.get("rotation", 0))) for s in video.get("side_data_list", []) if "rotation" in s), 0)
    if rotation % 180 == 90:
        width, height = height, width
    stat = path.stat()
    return Media(str(path), duration, width, height, numerator / denominator if denominator else 30,
                 any(s["codec_type"] == "audio" for s in info["streams"]), stat.st_size, stat.st_mtime_ns)


def run_progress(args, duration, progress=lambda *_: None, cancel=None, cwd=None):
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace", creationflags=NO_WINDOW, cwd=cwd)
    messages = queue.Queue()

    def reader():
        try:
            for line in process.stdout:
                messages.put(line.rstrip())
        finally:
            messages.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    tail = deque(maxlen=80)
    try:
        while True:
            if cancel and cancel.is_set():
                raise Cancelled("Operazione annullata.")
            try:
                line = messages.get(timeout=.15)
            except queue.Empty:
                continue
            if line is None:
                break
            tail.append(line)
            if line.startswith("out_time_us="):
                try:
                    progress(min(.995, max(0, float(line.split("=", 1)[1]) / 1_000_000 / max(duration, .1))), "Codifica video")
                except ValueError:
                    pass
        code = process.wait()
        if code:
            raise RuntimeError("FFmpeg: " + "\n".join(tail)[-5000:])
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        thread.join(timeout=2)
        process.stdout.close()


def extract_audio(media, destination, tool_dir="", progress=lambda *_: None, cancel=None):
    check_source(media)
    if not media.has_audio:
        raise ValueError("Il video non ha audio: puoi comunque creare ed esportare clip manualmente.")
    run_progress([binary("ffmpeg", tool_dir), "-hide_banner", "-nostdin", "-y", "-i", media.path,
                  "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-progress", "pipe:1", "-nostats", str(destination)],
                 media.duration, progress, cancel)


def check_source(media):
    source = Path(media.path)
    if not source.is_file():
        raise ValueError("Il file video locale non è disponibile. Ricollega il progetto all'originale.")
    stat = source.stat()
    if media.size and (stat.st_size != media.size or stat.st_mtime_ns != media.mtime_ns):
        raise ValueError("Il video è stato modificato dopo l'importazione: importalo nuovamente.")


def layout_filter(media, clip, width=1080, height=1920, camera=None):
    from .reframing import filter_graph
    return filter_graph(media, clip, width, height, camera)


def nvenc_available(tool_dir=""):
    try:
        capture([binary("ffmpeg", tool_dir), "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "color=s=320x240:d=0.1",
                 "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"], timeout=20)
        return True
    except (RuntimeError, subprocess.TimeoutExpired):
        return False


def export_clip(media, clip, captions, target, options=None, progress=lambda *_: None, cancel=None):
    options = options or {}
    check_source(media)
    clip.validate(media)
    target = Path(target).resolve()
    if target.exists():
        raise ValueError(f"Il file esiste già: {target.name}. Scegli un altro nome.")
    if target.suffix.lower() != ".mp4":
        raise ValueError("L'esportazione richiede un file .mp4.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if captions and target.with_suffix(".srt").exists():
        raise ValueError("Esiste già il file SRT associato: scegli un altro nome.")
    width, height = options.get("width", 1080), options.get("height", 1920)
    fps = int(options.get("fps", 30))
    bitrate = int(options.get("bitrate", 12))
    if fps not in (30, 60) or not 1 <= bitrate <= 100 or (width, height) not in ((1080,1920), (720,1280), (360,640)):
        raise ValueError("Parametri di esportazione non validi.")
    tool_dir = options.get("tool_dir", "")
    camera = None
    if clip.camera_path:
        camera = probe(clip.camera_path, tool_dir)
        if clip.start + clip.camera_offset < 0 or clip.end + clip.camera_offset > camera.duration + .03:
            raise ValueError("La webcam separata non copre l'intera clip con questo offset. Correggi la sincronizzazione.")
    encoder = options.get("encoder", "auto")
    use_nvenc = encoder != "cpu" and nvenc_available(tool_dir)
    if encoder == "nvenc" and not use_nvenc:
        progress(0, "NVENC indisponibile: utilizzo CPU")
    token = options.get("job_id", "") + uuid.uuid4().hex
    partial = target.with_name(f".localclips-{token}.mp4")
    srt_partial = target.with_name(f".localclips-{token}.srt")
    used_encoder = ""
    try:
        with tempfile.TemporaryDirectory(prefix="localclips-") as temporary:
            work = Path(temporary)
            graph = layout_filter(media, clip, width, height, camera)
            if clip.burn_captions and captions:
                write_ass(work / "captions.ass", captions, clip)
                graph += ";[base]subtitles=filename=captions.ass[outv]"
            else:
                graph += ";[base]null[outv]"
            # Relative ASS path avoids Windows drive/quote escaping bugs. Passing
            # the graph as a single argv element needs no shell or deprecated script flag.
            base_args = [binary("ffmpeg", tool_dir), "-hide_banner", "-nostdin", "-y", "-ss", f"{clip.start:.6f}", "-i", media.path]
            if camera:
                base_args += ['-ss',f'{clip.start+clip.camera_offset:.6f}','-i',camera.path]
            if not media.has_audio:
                base_args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            base_args += ["-t", f"{clip.duration:.6f}", "-filter_complex", graph, "-map", "[outv]", "-map", "0:a:0" if media.has_audio else ("2:a:0" if camera else "1:a:0"), "-r", str(fps), "-pix_fmt", "yuv420p"]
            for use_gpu in ([True, False] if use_nvenc else [False]):
                used_encoder = "h264_nvenc" if use_gpu else "libx264"
                args = base_args + ["-c:v", used_encoder, "-preset", "p4" if use_gpu else "fast", "-b:v", f"{bitrate}M"]
                if clip.normalize:
                    args += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"]
                args += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(partial)]
                try:
                    run_progress(args, clip.duration, progress, cancel, cwd=work)
                    break
                except RuntimeError:
                    if not use_gpu:
                        raise
                    progress(0, "Errore NVENC: nuovo tentativo CPU")
            verified = probe(partial, tool_dir)
            if not verified.has_audio or (verified.width, verified.height) != (width, height) or abs(verified.duration - clip.duration) > .25:
                raise RuntimeError("Verifica del video esportato non superata.")
            if cancel and cancel.is_set():
                raise Cancelled("Esportazione annullata.")
            if captions:
                write_srt(srt_partial, captions, clip)
                # Windows rename refuses replacement; preserve existing user files.
                os.rename(srt_partial, target.with_suffix(".srt"))
            os.rename(partial, target)
        progress(1, "Esportazione verificata")
        return {"path": str(target), "encoder": used_encoder, "duration": verified.duration,
                "srt": str(target.with_suffix(".srt")) if captions else ""}
    finally:
        partial.unlink(missing_ok=True)
        srt_partial.unlink(missing_ok=True)
