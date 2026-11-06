from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Caption:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Media:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    size: int = 0
    mtime_ns: int = 0


@dataclass
class Clip:
    start: float
    end: float
    title: str = "Nuova clip"
    score: int = 0
    reason: str = "Selezione manuale"
    selected: bool = True
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    layout: str = "screen"
    crop_x: float = 0.5
    webcam: list[float] = field(default_factory=lambda: [0.75, 0.70, 0.25, 0.30])
    screen: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0, 1.0])
    style: str = "Tech Clean"
    font: str = "Arial"
    font_size: int = 66
    color: str = "#FFFFFF"
    highlight: str = "#55E0B0"
    outline: int = 4
    shadow: int = 1
    margin_v: int = 330
    burn_captions: bool = True
    normalize: bool = True
    description: str = ""
    split_ratio: float = 0.35
    webcam_pan: list[float] = field(default_factory=lambda: [0.5, 0.5])
    screen_pan: list[float] = field(default_factory=lambda: [0.5, 0.5])
    webcam_zoom: float = 1.0
    screen_zoom: float = 1.0
    webcam_confirmed: bool = False
    camera_path: str = ""
    camera_offset: float = 0.0
    keyframes: list[dict] = field(default_factory=list)
    face_track: list[dict] = field(default_factory=list)
    thumbnail: str = ''
    # OBS overlay bounds are independent of the zoomed/tracked face crop.
    # None keeps old projects compatible: use webcam for embedded sources.
    embedded_webcam: list[float] | None = None

    @property
    def duration(self):
        return self.end - self.start

    def validate(self, media: Media):
        if not all(math.isfinite(x) for x in (self.start, self.end, self.crop_x)):
            raise ValueError("Intervallo non valido.")
        if not 0 <= self.start < self.end <= media.duration + 0.05:
            raise ValueError("La clip deve essere compresa nella durata del video.")
        if self.duration < 0.2:
            raise ValueError("La clip deve durare almeno 0,2 secondi.")
        if self.layout not in {"fit", "crop", "split", "pip", "face", "screen", "dynamic", "manual"}:
            raise ValueError("Layout non riconosciuto.")
        if not 0 <= self.crop_x <= 1:
            raise ValueError("Posizione crop non valida.")
        for rect in (self.webcam, self.screen, *([self.embedded_webcam] if self.embedded_webcam is not None else [])):
            if len(rect) != 4 or not all(math.isfinite(v) for v in rect):
                raise ValueError("Rettangolo non valido.")
            x, y, w, h = rect
            if min(x, y) < 0 or min(w, h) < 0.01 or x + w > 1.001 or y + h > 1.001:
                raise ValueError("Il rettangolo deve restare nel video.")
        if not 20 <= self.font_size <= 150 or not 0 <= self.margin_v <= 800:
            raise ValueError("Dimensione o posizione sottotitoli non valida.")
        if not math.isfinite(self.split_ratio) or not .2 <= self.split_ratio <= .65:
            raise ValueError("La webcam deve occupare tra il 20% e il 65% dell'altezza.")
        for zoom in (self.webcam_zoom, self.screen_zoom):
            if not math.isfinite(zoom) or not 1 <= zoom <= 4:
                raise ValueError("Zoom non valido (1–4).")
        for pan in (self.webcam_pan, self.screen_pan):
            if len(pan) != 2 or not all(math.isfinite(v) and 0 <= v <= 1 for v in pan):
                raise ValueError("Posizione del ritaglio non valida.")
        if not math.isfinite(self.camera_offset):
            raise ValueError("Offset webcam non valido.")
        if len(self.keyframes) > 24:
            raise ValueError("Massimo 24 cambi di composizione per clip.")
        if len(self.face_track)>240:
            raise ValueError('Troppi campioni di tracking.')
        previous=-1
        for point in self.face_track:
            if set(point)!={'time','x','y'} or not all(math.isfinite(v) for v in point.values()):
                raise ValueError('Campione tracking non valido.')
            if point['time']<=previous or not self.start<=point['time']<self.end:
                raise ValueError('Timestamp tracking non valido.')
            if not 0<=point['x']<=1-self.webcam[2]+.001 or not 0<=point['y']<=1-self.webcam[3]+.001:
                raise ValueError('Tracking fuori dalla sorgente.')
            previous=point['time']
        previous = -1.
        allowed = {"time", "layout", "webcam", "screen", "split_ratio", "webcam_zoom", "screen_zoom", "webcam_pan", "screen_pan", "embedded_webcam"}
        for key in self.keyframes:
            if set(key) - allowed or "time" not in key:
                raise ValueError("Campi del cambio layout non validi.")
            t = key["time"]
            if not math.isfinite(t) or t <= previous or not self.start <= t < self.end:
                raise ValueError("I cambi layout devono essere ordinati e dentro la clip.")
            previous = t
            import copy
            candidate = copy.deepcopy(self)
            candidate.keyframes = []
            candidate.face_track = []
            for name, value in key.items():
                if name != "time":
                    setattr(candidate, name, value)
            candidate.validate(media)


def atomic_json(path: str | Path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass
class Project:
    media: Media
    clips: list[Clip] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    language: str = ""
    transcript_model: str = ""
    schema: int = 1

    def to_dict(self):
        return asdict(self)

    def save(self, path):
        atomic_json(path, self.to_dict())

    @classmethod
    def from_dict(cls, data):
        if data.get("schema") != 1:
            raise ValueError("Versione del progetto non supportata.")
        media = Media(**data["media"])
        if not math.isfinite(media.duration) or media.duration <= 0 or min(media.width, media.height) <= 0:
            raise ValueError("Metadati video non validi.")
        captions = [Caption(c["start"], c["end"], c["text"], [Word(**w) for w in c.get("words", [])]) for c in data.get("captions", [])]
        last = -1.0
        for c in captions:
            if not all(math.isfinite(t) for t in (c.start, c.end)) or c.start < last or not 0 <= c.start < c.end <= media.duration + 0.2:
                raise ValueError("Timestamp dei sottotitoli non validi.")
            last = c.end
            if len(c.text) > 10000:
                raise ValueError("Sottotitolo troppo lungo.")
            for w in c.words:
                if not all(math.isfinite(t) for t in (w.start, w.end)) or not c.start - .1 <= w.start <= w.end <= c.end + .1:
                    raise ValueError("Timestamp parola non valido.")
        project = cls(media, [Clip(**c) for c in data.get("clips", [])], captions,
                      data.get("language", ""), data.get("transcript_model", ""))
        for clip in project.clips:
            clip.validate(media)
        return project

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
