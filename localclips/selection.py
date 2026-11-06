"""Offline sentence boundaries, topic/hook scores and semantic-token diversity."""
import re
from .domain import Clip

TOPICS = {"privacy", "bitcoin", "locale", "locali", "llm", "modello", "modelli", "intelligenza", "decentralizzazione", "sicurezza", "gpu", "open", "source"}
HOOKS = {"perché", "come", "segreto", "problema", "attenzione", "errore", "scopri", "davvero", "però", "invece"}


def sentence_end(text):
    return bool(re.search(r"[.!?][\"”']?$",text.strip()))


def sentence_starts(captions):
    return [i for i,c in enumerate(captions) if i==0 or sentence_end(captions[i-1].text) or c.start-captions[i-1].end>=.65]


def diverse(candidates,count,captions):
    selected=[]
    signatures=[]
    for c in sorted(candidates,key=lambda c:-c.score):
        if any(c.start<x.end and c.end>x.start for x in selected): continue
        text=' '.join(x.text for x in captions if c.start<=x.start<c.end).lower()
        tokens={t for t in re.findall(r'\w+',text) if len(t)>3}
        if any(len(tokens&s)/max(1,len(tokens|s))>.72 for s in signatures): continue
        selected.append(c)
        signatures.append(tokens)
        if len(selected)>=count: break
    return selected


def propose(captions, duration, count=5, minimum=20, maximum=60):
    if not 1 <= count <= 30 or not 1 <= minimum <= maximum <= 180:
        raise ValueError("Numero o durata delle clip non valido.")
    # Whisper caption chunks are short; only start after punctuation or a clear pause.
    starts = sentence_starts(captions)
    candidates = []
    for i in starts:
        chunks = []
        for c in captions[i:]:
            length = c.end - captions[i].start
            if length > maximum+min(15,maximum*.25):
                break
            chunks.append(c)
            if length < minimum or not re.search(r"[.!?][\"”']?$", c.text.strip()):
                continue
            text = " ".join(x.text for x in chunks).strip()
            tokens = set(re.findall(r"\w+", text.lower()))
            topical = len(tokens & TOPICS)
            hooks = len(tokens & HOOKS)
            opening=' '.join(x.text for x in chunks[:2]).lower()
            hook_open=bool(set(re.findall(r'\w+',opening))&HOOKS)
            dependent=bool(re.match(r'^(quindi|questo|questa|come detto|e poi|anche questo)\b',opening))
            density = min(1, sum(x.end - x.start for x in chunks) / max(length, .1))
            score = round(min(95, 35 + min(20, topical * 4) + min(10, hooks * 3) + density * 10 + (10 if hook_open else 0) - (12 if dependent else 0)))
            candidates.append(Clip(max(0, captions[i].start - .1), min(duration, c.end + .12),
                                   text[:85] + ("…" if len(text) > 85 else ""), score,
                                   f"Offline: {topical} termini tematici; {'hook iniziale' if hook_open else 'spiegazione'}; confini di frase. Punteggio euristico, non viralità."))
    candidates.sort(key=lambda c:abs(c.duration-(minimum+maximum)/2))
    return diverse(candidates,count,captions)
