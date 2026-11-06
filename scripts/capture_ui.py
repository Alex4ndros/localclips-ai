import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from localclips.ui import Window,STYLE
from localclips.domain import Project

app=QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)
window=Window()
window.resize(1480,960)
window.show()


def capture():
    window.grab().save(str(root/'ui-home.png'))
    window.set_project(Project.load(root/'examples'/'example.lcproj'))
    window.load_clip(0)
    window.show_studio(2)
    QTimer.singleShot(100,wait_frame)


attempts=0
def wait_frame():
    global attempts
    attempts+=1
    if window.last_frame.isNull() and attempts<150:
        QTimer.singleShot(100,wait_frame)
    else:
        QTimer.singleShot(300,editor)


def editor():
    window.grab().save(str(root/'ui-editor.png'))
    window.player.stop()
    window.dirty=False
    app.quit()


QTimer.singleShot(400,capture)
app.exec()
