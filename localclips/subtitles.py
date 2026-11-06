from pathlib import Path
import re

from .domain import Caption, Clip

# Canonical 1080×1920 style values, shared with the live editor. Existing saved
# projects keep their explicit values; selecting a preset applies these defaults.
PRESETS = {'Minimal': (58,4,1), 'Dynamic': (68,4,1),
           'Bold Social': (85,4,1), 'Tech Clean': (66,4,1)}
CANVAS_WIDTH, CANVAS_HEIGHT = 1080, 1920
MARGIN_LEFT, MARGIN_RIGHT = 85, 145
OUTLINE_COLOR = '#000000'
SHADOW_ALPHA = 128


def font_name(clip):
    return re.sub(r"[,\r\n]", "", clip.font)[:80] or 'Arial'


def text_area(clip):
    """Left, available width and bottom baseline area in canonical pixels."""
    return MARGIN_LEFT, CANVAS_WIDTH-MARGIN_LEFT-MARGIN_RIGHT, CANVAS_HEIGHT-clip.margin_v


def clock(seconds, ass=False):
    scale = 100 if ass else 1000
    ticks = max(0, round(seconds * scale))
    hours, ticks = divmod(ticks, 3600 * scale)
    minutes, ticks = divmod(ticks, 60 * scale)
    seconds, fraction = divmod(ticks, scale)
    return f"{hours}:{minutes:02}:{seconds:02}.{fraction:02}" if ass else f"{hours:02}:{minutes:02}:{seconds:02},{fraction:03}"


def clipped(captions, clip):
    for c in captions:
        a, b = max(c.start, clip.start), min(c.end, clip.end)
        if b <= a:
            continue
        words = [w for w in c.words if w.end > a and w.start < b]
        # Text edited by the user has no word timestamps; preserve that text.
        text = " ".join(w.text.strip() for w in words) if words else c.text.strip()
        yield c, a - clip.start, b - clip.start, text, words


def write_srt(path, captions, clip):
    lines = []
    for i, (_, a, b, text, _) in enumerate(clipped(captions, clip), 1):
        lines.append(f"{i}\n{clock(a)} --> {clock(b)}\n{text}\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8-sig")


def escape(text):
    return text.replace("\\", "／").replace("{", "(").replace("}", ")").replace("\n", r"\N").replace("\r", "")


def ass_color(value):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Colore non valido: usa #RRGGBB.")
    return "&H00" + value[5:7] + value[3:5] + value[1:3]


def write_ass(path, captions: list[Caption], clip: Clip):
    primary = ass_color(clip.highlight if clip.style in ("Dynamic", "Bold Social") else clip.color)
    secondary = ass_color(clip.color)
    font = font_name(clip)
    bold = -1 if clip.style == "Bold Social" else 0
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{clip.font_size},{primary},{secondary},{ass_color(OUTLINE_COLOR)},&H80000000,{bold},0,0,0,100,100,0,0,1,{clip.outline},{clip.shadow},2,{MARGIN_LEFT},{MARGIN_RIGHT},{clip.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for c, a, b, text, words in clipped(captions, clip):
        if clip.style in ("Dynamic", "Bold Social") and words:
            parts = []
            cursor = a
            for w in words:
                start = max(a, w.start - clip.start)
                end = min(b, w.end - clip.start)
                gap = max(0, round((start - cursor) * 100))
                if gap:
                    parts.append(r"{\k" + str(gap) + "} ")
                parts.append(r"{\kf" + str(max(1, round((end - start) * 100))) + "}" + escape(w.text.strip()) + " ")
                cursor = end
            body = "".join(parts).strip()
        else:
            body = escape(text)
        if clip.style == "Bold Social":
            body = r"{\fad(60,60)}" + body
        lines.append(f"Dialogue: 0,{clock(a, True)},{clock(b, True)},Default,,0,0,0,,{body}")
    Path(path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8-sig")
