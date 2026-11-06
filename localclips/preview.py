"""Immediate source-frame composition; geometry comes from reframing.py."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QFont, QPen, QPainterPath, QTextLayout, QTextOption
from PySide6.QtWidgets import QWidget

from .reframing import placements, at_time, CompositionError
from types import SimpleNamespace
from .subtitles import clipped, font_name, text_area, OUTLINE_COLOR, SHADOW_ALPHA


def caption_path(text,clip):
    """Live typography uses the saved ASS style values, with no fixed-height box.

    Qt rasterization may differ slightly from libass; the rendered proxy uses
    write_ass itself and is the exact final typography/animation reference.
    """
    font=QFont(font_name(clip))
    font.setPixelSize(clip.font_size)
    font.setBold(clip.style=='Bold Social')
    x,width,bottom=text_area(clip)
    layout=QTextLayout(text.replace('\n','\u2028'),font)
    option=QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    lines=[]
    layout.beginLayout()
    while True:
        line=layout.createLine()
        if not line.isValid():break
        line.setLineWidth(width)
        lines.append(line)
    layout.endLayout()
    y=bottom-sum(line.height() for line in lines)
    path=QPainterPath()
    for line in lines:
        left=x+(width-line.naturalTextWidth())/2
        part=text.encode('utf-16-le')[2*line.textStart():2*(line.textStart()+line.textLength())].decode('utf-16-le').rstrip(' \t\n\u2028')
        path.addText(left,y+line.ascent(),font,part)
        y+=line.height()
    return path


class CompositionPreview(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.image = QImage()
        self.camera_image = QImage()
        self.original = True
        self.setMinimumSize(260,300)

    def set_frame(self, image):
        self.image=image
        self.update()

    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),QColor('#090d14'))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.image.isNull():
            p.setPen(QColor('#97a8bd'))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Importa un video per iniziare')
            return
        state=self.state()
        if self.original or state is None:
            ratio=min(self.width()/self.image.width(),self.height()/self.image.height())
            w,h=self.image.width()*ratio,self.image.height()*ratio
            p.drawImage(QRectF((self.width()-w)/2,(self.height()-h)/2,w,h),self.image)
            return
        media,clip,timestamp,captions=state
        factor=min(self.width()/1080,self.height()/1920)
        left=(self.width()-1080*factor)/2
        top=(self.height()-1920*factor)/2
        p.translate(left,top)
        p.scale(factor,factor)
        p.setClipRect(QRectF(0,0,1080,1920))
        camera=SimpleNamespace(width=self.camera_image.width(),height=self.camera_image.height()) if clip.camera_path and not self.camera_image.isNull() else None
        try:
            plan=placements(media,clip,timestamp=timestamp,camera=camera)
        except CompositionError as exc:
            p.setPen(QColor('#ffcc80'))
            p.setFont(QFont('Arial',28))
            p.drawText(QRectF(80,500,920,800),Qt.TextFlag.TextWordWrap,str(exc))
            return
        for part in plan:
            x,y,w,h=part.crop
            image=self.camera_image if part.source else self.image
            source=camera if part.source else media
            sx,sy=image.width()/source.width,image.height()/source.height
            p.drawImage(QRectF(*part.target),image,QRectF(x*sx,y*sy,w*sx,h*sy))
        if clip.camera_path and camera is None:
            p.fillRect(QRectF(0,0,1080,1920),QColor('#142132'))
            p.fillRect(QRectF(0,0,1080,110),QColor('#142132'))
            p.setPen(QColor('white'))
            p.setFont(QFont('Arial',24))
            p.drawText(QRectF(20,15,1040,80),Qt.AlignmentFlag.AlignCenter,'Caricamento webcam separata…')
        if clip.burn_captions:
            entry=next((row for row in clipped(captions,clip) if row[1]<=timestamp-clip.start<row[2]),None)
            if entry:
                path=caption_path(entry[3],clip)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                if clip.shadow:
                    shade=QColor(OUTLINE_COLOR)
                    shade.setAlpha(SHADOW_ALPHA)
                    p.setPen(QPen(shade,clip.outline*2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin) if clip.outline else Qt.PenStyle.NoPen)
                    p.setBrush(shade)
                    p.drawPath(path.translated(clip.shadow,clip.shadow))
                p.setPen(QPen(QColor(OUTLINE_COLOR),clip.outline*2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin) if clip.outline else Qt.PenStyle.NoPen)
                p.setBrush(QColor(clip.color))
                p.drawPath(path)
