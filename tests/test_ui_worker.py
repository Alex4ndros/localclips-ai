import json
import time
from pathlib import Path

from localclips.domain import Caption, Clip, Project
from localclips.jobs import Jobs
from localclips.media import probe
from localclips.ui import Window


def wait_for(qt_app, predicate, timeout=30):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        qt_app.processEvents()
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError("Timed out waiting for worker")


def test_gui_import_editor_and_caption_changes(qt_app,video):
    window = Window()
    errors = []
    window.error = errors.append
    window.import_path(str(video))
    wait_for(qt_app,lambda:not window.jobs.busy)
    assert window.project.media.width == 640
    window.new_clip()
    window.start_time.setValue(.5)
    window.end_time.setValue(3)
    assert window.apply_editor()
    assert window.project.clips[0].start == .5
    window.add_caption()
    window.captions_table.item(0,0).setText("0.6")
    window.captions_table.item(0,1).setText("1.6")
    window.captions_table.item(0,2).setText("Un modello locale.")
    assert window.commit_captions()
    assert window.project.captions[0].text == "Un modello locale."
    window.start_time.setValue(4)
    assert not window.apply_editor()
    assert errors
    window.dirty = False
    window.player.stop()
    window.close()


def test_background_batch(qt_app,video,tmp_path):
    project = Project(probe(video),[Clip(0,1,"Prima"),Clip(2,3,"Seconda")],[Caption(.1,.9,"Test.")])
    job = Jobs()
    results,errors = [],[]
    job.completed.connect(results.append)
    job.failed.connect(errors.append)
    job.start({"action":"export","project":project.to_dict(),"indices":[0,1],"directory":str(tmp_path),
               "options":{"encoder":"cpu","width":360,"height":640,"bitrate":2}})
    wait_for(qt_app,lambda:not job.busy,60)
    assert not errors, errors
    assert len(results[0]["exports"]) == 2
    assert len(list(tmp_path.glob("*.mp4"))) == 2


def test_background_cancel(qt_app,video,tmp_path):
    project = Project(probe(video),[Clip(0,6)])
    job = Jobs()
    cancelled = []
    job.cancelled.connect(lambda:cancelled.append(True))
    job.start({"action":"export","project":project.to_dict(),"indices":[0],"directory":str(tmp_path),
               "options":{"encoder":"cpu"}})
    wait_for(qt_app,lambda:job.process.processId()!=0)
    job.cancel()
    wait_for(qt_app,lambda:not job.busy)
    assert cancelled
    assert not list(tmp_path.glob("*.mp4"))


def test_editor_presets_keys_and_timeline(qt_app,video,tmp_path,monkeypatch):
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setenv('LOCALCLIPS_DATA',str(tmp_path/'data'))
    window=Window()
    window.set_project(Project(probe(video),[Clip(0,5,layout='split',webcam_confirmed=True)]))
    wait_for(qt_app,lambda:window.player.isSeekable() and not window.last_frame.isNull() and not window.prime_frame)
    window.load_clip(0)
    window.show_studio(2)
    window.show()
    qt_app.processEvents()
    window.exclusion_rect=[.75,.7,.25,.3]
    window.cam_zoom.setValue(2)
    window.balance_webcam()
    assert window.cam_zoom.value()==1 and window.cam_x.value()==50 and window.cam_y.value()==50
    window.split_ratio.setValue(42)
    monkeypatch.setattr(QInputDialog,'getText',lambda *a:('OBS personalizzato',True))
    window.save_layout()
    window.split_ratio.setValue(35)
    monkeypatch.setattr(QInputDialog,'getItem',lambda *a:('OBS personalizzato',True))
    window.load_layout()
    assert window.split_ratio.value()==42
    assert window.exclusion_rect==[.75,.7,.25,.3]
    window.player.setPosition(2000)
    wait_for(qt_app,lambda:abs(window.player.position()-2000)<50)
    window.add_layout_key()
    assert len(window.project.clips[0].keyframes)==1
    assert window.project.clips[0].keyframes[0]['time']==2
    window.seek.setRange(0,6000)
    QTest.mousePress(window.seek,Qt.MouseButton.LeftButton,pos=QPoint(round(window.seek.x(0)),10))
    QTest.mouseMove(window.seek,QPoint(round(window.seek.x(1)),10))
    QTest.mouseRelease(window.seek,Qt.MouseButton.LeftButton,pos=QPoint(round(window.seek.x(1)),10))
    assert .95<window.start_time.value()<1.05
    assert window.apply_editor(quiet=True)
    saved=tmp_path/'edited.lcproj'
    window.project.save(saved)
    assert Project.load(saved).clips[0].keyframes[0]['split_ratio']==.42
    assert Project.load(saved).clips[0].embedded_webcam==[.75,.7,.25,.3]
    window.dirty=False
    window.close()
