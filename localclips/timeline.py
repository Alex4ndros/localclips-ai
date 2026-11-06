"""Seek slider with draggable in/out handles and composition markers."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider


class Timeline(QSlider):
    trim=Signal(bool,float)
    def __init__(self,state,parent=None):
        super().__init__(Qt.Orientation.Horizontal,parent)
        self.state=state
        self.handle=None
        self.setMinimumHeight(44)
        self.setToolTip('Trascina IN / OUT per tagliare; clicca sulla barra per scorrere.')

    def x(self,seconds):
        return 9+(self.width()-18)*seconds*1000/max(1,self.maximum())

    def paintEvent(self,event):
        super().paintEvent(event)
        state=self.state()
        if state is None:return
        start,end,keys=state
        p=QPainter(self)
        p.setPen(QPen(QColor('#65e2b5'),3))
        a,b=self.x(start),self.x(end)
        p.drawLine(round(a),7,round(b),7)
        for x,text in ((a,'IN'),(b,'OUT')):
            p.drawLine(round(x),2,round(x),self.height()-3)
            p.drawText(round(max(0,min(self.width()-28,x-10))),self.height()-1,text)
        p.setPen(QPen(QColor('#edbc68'),2))
        for key in keys:
            x=round(self.x(key['time']))
            p.drawLine(x,13,x,29)

    def mousePressEvent(self,event):
        state=self.state()
        if state:
            for end,t in ((False,state[0]),(True,state[1])):
                if abs(event.position().x()-self.x(t))<10:
                    self.handle=end
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.handle is not None:
            value=max(0,min(1,(event.position().x()-9)/max(1,self.width()-18)))*self.maximum()/1000
            self.trim.emit(self.handle,value)
            self.update()
        else:super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.handle is not None:
            self.mouseMoveEvent(event)
            self.handle=None
        else:super().mouseReleaseEvent(event)
