import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from localclips.media import binary, capture


@pytest.fixture(scope="session")
def video(tmp_path_factory):
    path = tmp_path_factory.mktemp("media") / "test video à.mp4"
    capture([binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6", "-vf", "drawbox=x=480:y=260:w=160:h=100:color=green:t=fill",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)])
    return path


@pytest.fixture(scope="session")
def qt_app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app
