"""Regression check for the native GUI and media backend in a frozen bundle."""
import json
import os
import sys
from pathlib import Path


def check(report):
    os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"
    os.environ["QT_QPA_PLATFORM"] = "windows"
    from PySide6.QtCore import QTimer, qVersion
    from PySide6.QtWidgets import QApplication
    from .media import probe
    from .ui import Window, STYLE

    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    failures = []
    window.error = failures.append
    window.player.errorOccurred.connect(lambda _, text: failures.append(text))
    window.show()
    media_path = None
    if "--media" in sys.argv:
        media_path = Path(sys.argv[sys.argv.index("--media") + 1]).resolve()
        window.import_path(str(media_path))
    ticks = 0
    phase='import'
    actions=[]
    exported=[]
    live_checked=False
    window.jobs.exported.connect(exported.append)

    def inspect():
        nonlocal ticks,phase,live_checked
        ticks += 1
        ready = window.isVisible() and (media_path is None or (window.project is not None and window.player.duration() > 0 and not window.last_frame.isNull()))
        if media_path and ready and not window.jobs.busy and not failures:
            if phase=='import':
                actions.append('import_video_via_gui_worker')
                window.new_clip()
                window.start_time.setValue(.5)
                window.end_time.setValue(min(3.5,window.project.media.duration))
                window.rects={'webcam':[1900/2560,1040/1440,600/2560,360/1440],
                              'screen':[100/2560,80/1440,1100/2560,1280/1440]}
                if '--exclude-webcam-test' in sys.argv:
                    window.rects['screen']=[0,0,1,1]
                    window.scr_x.setValue(100)
                    window.scr_y.setValue(100)
                window.project.clips[0].webcam_confirmed=True
                window.layout_combo.setCurrentIndex(window.layout_combo.findData('split'))
                if window.apply_editor(quiet=True):
                    actions.append('select_and_apply_smart_split')
                    window.preview_current()
                    phase='preview'
                    QTimer.singleShot(100,inspect)
                    return
            elif phase in ('preview','preview-again') and window.preview_mode and (window.video.image.width(),window.video.image.height())==(360,640) and window.player.position()>0:
                if phase=='preview':
                    actions.append('render_and_play_vertical_preview')
                    if '--exclude-webcam-test' in sys.argv:
                        window.split_ratio.setValue(36)
                        phase='live-adjustment'
                        QTimer.singleShot(100,inspect)
                        return
                window.export_dir.setText(str(report.parent/'gui-export'))
                window.export_indices([0])
                phase='export'
                QTimer.singleShot(100,inspect)
                return
            elif phase=='live-adjustment' and not window.preview_mode and not window.prime_frame and window.video.image.width()==window.project.media.width:
                live_checked=not window.video.original
                if not live_checked:failures.append('Composition changes did not return to live preview')
                window.split_ratio.setValue(35)
                window.preview_current()
                phase='preview-again'
                QTimer.singleShot(100,inspect)
                return
            elif phase=='export':
                if exported and probe(exported[-1]).width==1080:
                    actions.append('export_1080x1920_from_gui')
                    phase='done'
                else:
                    failures.append('GUI export missing or invalid')
        done=ready and (not media_path or phase=='done')
        if not done and not failures and ticks < 600:
            QTimer.singleShot(100, inspect)
            return
        window.grab().save(str(report.with_suffix(".png")))
        # last_frame is an actual decoded video frame, independent of native
        # video surfaces being omitted by QWidget.grab on some drivers.
        if not window.video.image.isNull():
            window.video.image.save(str(report.with_name(report.stem + "-video.png")))
        value = {"ok": done and not failures, "qt": qVersion(), "visible": window.isVisible(),
                 "video_duration_ms": window.player.duration(), "decoded_frame": not window.video.image.isNull(),
                 'decoded_size':[window.video.image.width(),window.video.image.height()],
                 'webcam_exclusion_test':'--exclude-webcam-test' in sys.argv,
                 'live_adjustment_verified':live_checked,
                 "errors": failures, "frozen": bool(getattr(sys, "frozen", False)), 'actions':actions,'exports':exported}
        report.write_text(json.dumps(value, indent=2), encoding="utf-8")
        window.player.stop()
        window.dirty = False
        app.exit(0 if value["ok"] else 1)

    QTimer.singleShot(200, inspect)
    return app.exec()
