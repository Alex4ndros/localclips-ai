import json
import os
import sys
import uuid
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QProcess, Signal

from .domain import atomic_json
from .paths import data_root, app_root


class Jobs(QObject):
    progress = Signal(object, str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    exported = Signal(str)
    auth_url = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.buffer = ""
        self.error = ""
        self.result_path = None
        self.stopping = False
        self.targets = []

    @property
    def busy(self):
        return self.process is not None

    def start(self, request):
        if self.busy:
            raise RuntimeError("Operazione già in corso.")
        self.folder = data_root() / "jobs" / uuid.uuid4().hex
        self.folder.mkdir(parents=True)
        request.setdefault("options", {})["job_id"] = self.folder.name
        atomic_json(self.folder / "request.json", request)
        self.buffer, self.error, self.result_path, self.stopping = "", "", None, False
        self.targets = [Path(request["directory"])] if request.get("directory") else []
        p = self.process = QProcess(self)
        p.setWorkingDirectory(str(app_root()))
        p.setProgram(sys.executable)
        prefix = [] if getattr(sys, "frozen", False) else [str(app_root() / "main.py")]
        p.setArguments(prefix + ["--worker", str(self.folder / "request.json")])
        p.readyReadStandardOutput.connect(self.read)
        p.readyReadStandardError.connect(self.read_errors)
        p.finished.connect(self.finish)
        p.errorOccurred.connect(self.process_error)
        p.start()

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.error = self.process.errorString()
            self.finish(-1, QProcess.ExitStatus.CrashExit)

    def read(self):
        self.buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if item["event"] == "progress":
                self.progress.emit(item["value"], item["message"])
            elif item["event"] == "done":
                self.result_path = item["result_path"]
            elif item["event"] == "error":
                self.error = item["message"]
            elif item["event"] == "exported":
                self.exported.emit(item["path"])
            elif item['event']=='auth_url':
                self.auth_url.emit(item['url'])

    def read_errors(self):
        text = bytes(self.process.readAllStandardError()).decode("utf-8", "replace")
        with (self.folder / "native.log").open("a", encoding="utf-8") as f:
            f.write(text)

    def cancel(self):
        if not self.process:
            return
        self.stopping = True
        try:
            parent = psutil.Process(self.process.processId())
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
        except psutil.Error:
            pass
        self.process.kill()

    def finish(self, code, status):
        if not self.process:
            return
        self.read()
        self.read_errors()
        p, self.process = self.process, None
        p.deleteLater()
        if self.stopping:
            # Worker uses atomic final outputs; partial files have a reserved prefix.
            for folder in self.targets:
                for file in folder.glob(".localclips-" + self.folder.name + "*"):
                    try:
                        file.unlink()
                    except OSError:
                        pass
            try:
                (self.folder / "audio.wav").unlink(missing_ok=True)
            except OSError:
                pass
            self.cancelled.emit()
        elif code == 0 and self.result_path:
            try:
                value = json.loads(Path(self.result_path).read_text(encoding="utf-8"))
            except Exception as exc:
                self.failed.emit(str(exc))
            else:
                self.completed.emit(value)
        else:
            self.failed.emit(self.error or f"Il processo si è interrotto (codice {code}). Log: {self.folder}")
