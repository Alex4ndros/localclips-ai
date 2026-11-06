import gc
import os
from pathlib import Path

from .domain import Caption, Word
from .media import Cancelled
from .paths import models_root, setup_cuda_paths

MODELS = ("tiny", "base", "small", "medium", "large-v3", "turbo")


def model_path(name):
    p = Path(name)
    if p.is_dir():
        return p.resolve()
    if name not in MODELS:
        raise ValueError("Modello non riconosciuto.")
    return models_root() / name


def download(name, progress=lambda *_: None):
    if name not in MODELS:
        raise ValueError("Modello non riconosciuto.")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from faster_whisper.utils import download_model
    progress(None, f"Download esplicito del modello {name}; attesa trasferimento…")
    path = download_model(name, output_dir=str(model_path(name)))
    progress(1, "Modello disponibile offline")
    return {"model_path": str(path)}


def transcribe(audio, name="small", device="auto", language="auto", progress=lambda *_: None, cancel=None):
    path = model_path(name)
    if not (path / "model.bin").is_file():
        raise RuntimeError(f"Il modello {name} non è installato. Apri Impostazioni e premi Scarica modello. L'analisi non accede a Internet.")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    handles = setup_cuda_paths()
    from faster_whisper import WhisperModel
    import ctranslate2
    try:
        cuda = ctranslate2.get_cuda_device_count() > 0
    except RuntimeError:
        cuda = False
    devices = ["cuda", "cpu"] if device != "cpu" and cuda else ["cpu"]
    warning = ""
    model = None
    for chosen in devices:
        try:
            progress(None, f"Caricamento {name} su {chosen.upper()}…")
            model = WhisperModel(str(path), device=chosen, compute_type="float16" if chosen == "cuda" else "int8",
                                 cpu_threads=min(12, os.cpu_count() or 4), num_workers=1, local_files_only=True)
            segments, info = model.transcribe(str(audio), language=None if language == "auto" else language,
                                             word_timestamps=True, vad_filter=True, beam_size=5,
                                             vad_parameters={"min_silence_duration_ms": 500},
                                             initial_prompt="Intelligenza artificiale, LLM, LM Studio, privacy, Bitcoin, CUDA, GPU, open source, decentralizzazione.")
            captions = []
            for segment in segments:
                if cancel and cancel.is_set():
                    raise Cancelled("Trascrizione annullata.")
                words = [Word(float(w.start), float(w.end), w.word.strip()) for w in (segment.words or []) if w.word.strip() and w.end > w.start]
                # Short readable caption groups; keep true Whisper word timing.
                group = []
                for word in words:
                    if group and (len(" ".join(w.text for w in group)) + len(word.text) > 40 or word.end - group[0].start > 3.5):
                        captions.append(Caption(group[0].start, group[-1].end, " ".join(w.text for w in group), group))
                        group = []
                    group.append(word)
                    if word.text.endswith((".", "?", "!")):
                        captions.append(Caption(group[0].start, group[-1].end, " ".join(w.text for w in group), group))
                        group = []
                if group:
                    captions.append(Caption(group[0].start, group[-1].end, " ".join(w.text for w in group), group))
                if not words and segment.text.strip() and segment.end > segment.start:
                    captions.append(Caption(segment.start, segment.end, segment.text.strip()))
                progress(min(.99, segment.end / max(info.duration, .1)), f"Trascrizione {chosen.upper()} · {segment.end:.0f}/{info.duration:.0f} s")
            # Word boundaries can overlap slightly; trim rather than creating invalid projects.
            cleaned = []
            for c in captions:
                c.start = max(c.start, cleaned[-1].end if cleaned else 0)
                c.end = min(c.end, info.duration)
                if c.end <= c.start:
                    continue
                c.words = [Word(max(c.start, w.start), min(c.end, w.end), w.text) for w in c.words if min(c.end, w.end) > max(c.start, w.start)]
                cleaned.append(c)
            progress(1, "Trascrizione completata")
            return cleaned, info.language, chosen, warning
        except Cancelled:
            raise
        except Exception as exc:
            if chosen == "cpu":
                raise
            warning = f"CUDA non utilizzabile ({exc}); trascrizione su CPU int8."
            progress(None, warning)
        finally:
            del model
            model = None
            gc.collect()
