from __future__ import annotations

import copy
import json
import logging
import sys
import time
import uuid
from pathlib import Path

import psutil
from PySide6.QtCore import Qt, QTimer, QUrl, QRectF, Signal, QSize
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QPen, QPixmap, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QInputDialog,
    QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .domain import Caption, Clip, Media, Project, atomic_json
from .jobs import Jobs
from .paths import app_root, data_root, models_root
from .transcription import MODELS
from .preview import CompositionPreview
from .subtitles import PRESETS
from .timeline import Timeline
from .reframing import warnings as framing_warnings

STYLE = """
QWidget { background: #10141d; color: #e5eaf2; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow { background: #10141d; }
QLabel#brand { font-size: 23px; font-weight: 700; color: #6ce9be; }
QLabel#title { font-size: 23px; font-weight: 600; }
QLabel#muted { color: #9baac0; }
QFrame#sidebar { background: #151b27; border-right: 1px solid #293347; }
QFrame#sidebar QLabel, QFrame#sidebar QPushButton { background: #151b27; }
QPushButton { background: #263247; border: 1px solid #35435b; border-radius: 7px; padding: 9px 12px; }
QPushButton:hover { background: #344660; border-color: #69d9ba; }
QPushButton:disabled { color: #6e798b; background: #1b2230; border-color: #283244; }
QPushButton#primary { background: #65e2b5; color: #10251f; font-weight: 700; border: none; }
QPushButton#primary:hover { background: #8af1ce; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox { background: #1b2433; padding: 7px; border: 1px solid #334158; border-radius: 5px; }
QTableWidget, QListWidget { background: #171f2d; border: 1px solid #2b3950; border-radius: 7px; alternate-background-color: #1c2636; }
QListWidget::item { padding: 12px; border-bottom: 1px solid #29364a; }
QListWidget::item:selected { background: #29463f; }
QHeaderView::section { background: #253247; padding: 6px; border: none; }
QProgressBar { background: #253247; border: 0; border-radius: 5px; text-align: center; min-height: 13px; }
QProgressBar::chunk { background: #65e2b5; border-radius: 5px; }
QSlider::groove:horizontal { height: 6px; background: #34435c; border-radius: 3px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: #6ce9be; }
QCheckBox { spacing: 8px; padding: 4px 0; }
QScrollArea { border: none; }
QToolTip { background: #263247; color: #ffffff; padding: 8px; border: 1px solid #65e2b5; }
"""


def label(text, muted=False):
    w = QLabel(text)
    w.setWordWrap(True)
    if muted:
        w.setObjectName("muted")
    return w


def button(text, slot, primary=False):
    w = QPushButton(text)
    w.clicked.connect(slot)
    if primary:
        w.setObjectName("primary")
    return w


def spin(minimum, maximum, value, suffix="", decimal=False):
    w = QDoubleSpinBox() if decimal else QSpinBox()
    w.setRange(minimum, maximum)
    w.setValue(value)
    w.setSuffix(suffix)
    if decimal:
        w.setDecimals(2)
        w.setSingleStep(.1)
    return w


def combo(items):
    w = QComboBox()
    for text, value in items:
        w.addItem(text, value)
    return w


def set_combo(w, value):
    index = w.findData(value)
    if index >= 0:
        w.setCurrentIndex(index)


def format_time(seconds):
    seconds = max(0, seconds)
    return f"{int(seconds)//60:02}:{seconds%60:05.2f}"


class RegionCanvas(QWidget):
    def __init__(self, image, rect, parent=None, excluded=None):
        super().__init__(parent)
        self.image = image
        self.rect = QRectF(*rect)
        self.origin = None
        self.excluded=excluded
        self.setMinimumSize(640, 360)

    def image_rect(self):
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())

    def normalized(self, point):
        r = self.image_rect()
        return (max(0., min(1., (point.x()-r.x())/r.width())), max(0., min(1., (point.y()-r.y())/r.height())))

    def paintEvent(self, event):
        painter = QPainter(self)
        target = self.image_rect()
        painter.drawImage(target, self.image)
        if self.excluded:
            x,y,w,h=self.excluded
            painter.setPen(QPen(QColor('#ff746e'),3))
            painter.setBrush(QColor(255,80,70,65))
            painter.drawRect(QRectF(target.x()+x*target.width(),target.y()+y*target.height(),w*target.width(),h*target.height()))
        r = self.rect
        painter.setPen(QPen(QColor("#65e2b5"), 3))
        painter.setBrush(QColor(101, 226, 181, 45))
        painter.drawRect(QRectF(target.x()+r.x()*target.width(), target.y()+r.y()*target.height(), r.width()*target.width(), r.height()*target.height()))

    def mousePressEvent(self, event):
        self.origin = self.normalized(event.position())
        self.initial=self.rect
        x,y=self.origin
        near_corner=abs(x-self.rect.right())<.04 and abs(y-self.rect.bottom())<.04
        self.mode='resize' if near_corner else ('move' if self.rect.contains(x,y) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 'new')

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            x, y = self.normalized(event.position())
            ox, oy = self.origin
            if self.mode=='move':
                r=self.initial
                self.rect=QRectF(max(0,min(1-r.width(),r.x()+x-ox)),max(0,min(1-r.height(),r.y()+y-oy)),r.width(),r.height())
            elif self.mode=='resize':
                r=self.initial
                self.rect=QRectF(r.x(),r.y(),max(.01,min(1-r.x(),x-r.x())),max(.01,min(1-r.y(),y-r.y())))
            else:
                self.rect = QRectF(min(x, ox), min(y, oy), max(.01, abs(x-ox)), max(.01, abs(y-oy)))
            self.update()

    def mouseReleaseEvent(self, event):
        self.mouseMoveEvent(event)
        self.origin = None


class RegionDialog(QDialog):
    def __init__(self, image, rect, title, parent=None, excluded=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Trascina dentro per spostare; angolo in basso a destra per ridimensionare; Shift + trascina per ridisegnare. I pixel nascosti dalla webcam non sono recuperabili.", True))
        if excluded:
            layout.addWidget(label('Rosso: webcam OBS esclusa. Verde: contenuto preferito. Il ritaglio finale resta sempre fuori dal rosso.',True))
        self.canvas = RegionCanvas(image, rect, excluded=excluded)
        layout.addWidget(self.canvas, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_rect(self):
        r = self.canvas.rect
        return [r.x(), r.y(), min(r.width(), 1-r.x()), min(r.height(), 1-r.y())]


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LocalClips AI · Studio locale")
        self.resize(1480, 960)
        self.setMinimumSize(1080, 740)
        self.setAcceptDrops(True)
        self.project = None
        self.project_path = None
        self.dirty = False
        self.current_clip = -1
        self.preview_mode = False
        self.last_frame = QImage()
        self.prime_frame = False
        self.pending_source_seek=None
        self.config_path = data_root() / "settings.json"
        try:
            self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.config = {}
        self.jobs = Jobs(self)
        self.jobs.progress.connect(self.job_progress)
        self.jobs.completed.connect(self.job_done)
        self.jobs.failed.connect(self.job_failed)
        self.jobs.cancelled.connect(self.job_cancelled)
        self.jobs.exported.connect(lambda path: self.statusBar().showMessage(f"Salvato: {path}"))
        self.jobs.auth_url.connect(lambda url:QDesktopServices.openUrl(QUrl(url)))
        self.action = ""
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.65)
        self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(lambda value: self.seek.setRange(0, max(1, value)))
        self.player.errorOccurred.connect(lambda error, text: self.statusBar().showMessage("Anteprima: " + text))
        self.camera_player = QMediaPlayer(self)
        self.camera_sink = QVideoSink(self)
        self.camera_player.setVideoSink(self.camera_sink)
        self.camera_sink.videoFrameChanged.connect(self.camera_frame_changed)
        self.player.playbackStateChanged.connect(self.sync_camera)
        self.build()
        self.load_settings()
        self.refresh_recent()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.resources)
        self.timer.start(2000)
        self.resources()

    def build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        body = QHBoxLayout()
        outer.addLayout(body, 1)
        self.interaction = QWidget()
        body.addWidget(self.interaction)
        layout = QHBoxLayout(self.interaction)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)
        nav = QVBoxLayout(sidebar)
        brand = label("LocalClips\nAI")
        brand.setObjectName("brand")
        nav.addWidget(brand)
        nav.addWidget(label("IL TUO STUDIO, LOCALE", True))
        nav.addSpacing(24)
        for title, action in [("⌂  Home", lambda: self.pages.setCurrentIndex(0)), ("01  Analisi", lambda: self.show_studio(0)),
                              ("02  Risultati", lambda: self.show_studio(1)), ("03  Editor", lambda: self.show_studio(2)),
                              ('04  Esportazione',lambda:self.show_studio(3)),
                              ("⚙  Impostazioni", lambda: self.pages.setCurrentIndex(2))]:
            nav.addWidget(button(title, action))
        nav.addStretch()
        nav.addWidget(button("Apri progetto", self.open_project))
        nav.addWidget(button("Salva progetto", self.save_project))
        nav.addWidget(button("Apri esportazioni", self.open_exports))
        nav.addWidget(label("0.2.2 · Smart composition\nNessun upload dei video", True))
        layout.addWidget(sidebar)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.make_home()
        self.make_studio()
        self.make_settings()
        footer = QHBoxLayout()
        self.status = label("Pronto. Importa un video per iniziare.", True)
        self.status.setMinimumWidth(300)
        footer.addWidget(self.status, 2)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        footer.addWidget(self.progress, 1)
        self.cancel_button = button("Annulla", self.jobs.cancel)
        self.cancel_button.setEnabled(False)
        footer.addWidget(self.cancel_button)
        outer.addLayout(footer)
        self.resource_label = label("", True)
        outer.addWidget(self.resource_label)

    def make_home(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = label("Da un video lungo, nuove clip.")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(label("Importa una registrazione, trascrivi sul tuo PC e prepara il taglio verticale.", True))
        layout.addSpacing(35)
        hero = QFrame()
        hero.setObjectName("importCard")
        hero.setStyleSheet("QFrame#importCard { background:#192637; border:1px dashed #5d8c83; border-radius:14px; }")
        box = QVBoxLayout(hero)
        box.setContentsMargins(45, 50, 45, 50)
        box.addWidget(label("Trascina qui il tuo video"))
        box.addWidget(label("MP4 · MOV · MKV · WEBM — il file originale rimane sul computer", True))
        box.addWidget(button("Seleziona video", self.import_dialog, True))
        layout.addWidget(hero)
        layout.addSpacing(20)
        layout.addWidget(label("Progetti recenti"))
        self.recent = QListWidget()
        self.recent.itemDoubleClicked.connect(lambda item: self.load_project_path(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.recent, 1)
        layout.addWidget(label("Primo utilizzo: il modello Small multilingue è consigliato. Scaricalo una volta nelle Impostazioni; poi trascrizione e montaggio funzionano offline. Questa versione usa proposte euristiche e ritaglio manuale.", True))
        self.pages.addWidget(page)

    def make_studio(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        head = QHBoxLayout()
        self.media_label = label("Nessun video importato")
        self.media_label.setObjectName("title")
        head.addWidget(self.media_label, 1)
        head.addWidget(button("Importa video", self.import_dialog))
        layout.addLayout(head)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        view = QWidget()
        vl = QVBoxLayout(view)
        vl.setContentsMargins(0, 0, 10, 0)
        self.preview_label = label("ORIGINALE · nessuna modifica al file sorgente", True)
        vl.addWidget(self.preview_label)
        self.video = CompositionPreview(self.live_state)
        self.sink=QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self.frame_changed)
        vl.addWidget(self.video, 3)
        self.seek = Timeline(self.timeline_state)
        self.seek.trim.connect(self.trim_timeline)
        self.seek.sliderMoved.connect(self.player.setPosition)
        vl.addWidget(self.seek)
        controls = QHBoxLayout()
        controls.addWidget(button("▶ / Ⅱ", self.toggle_play))
        controls.addWidget(button("Originale", self.source_preview))
        controls.addWidget(button("Verticale live", self.vertical_live))
        self.time_label = label("00:00.00 / 00:00.00", True)
        controls.addWidget(self.time_label, 1)
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(65)
        volume.setMaximumWidth(100)
        volume.setToolTip("Volume dell'anteprima")
        volume.valueChanged.connect(lambda v: self.audio.setVolume(v/100))
        controls.addWidget(volume)
        vl.addLayout(controls)
        self.caption_panel = QWidget()
        cl = QVBoxLayout(self.caption_panel)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(label("Sottotitoli del progetto · tempi in secondi sul video originale", True))
        self.captions_table = QTableWidget(0, 3)
        self.captions_table.setHorizontalHeaderLabels(["Inizio", "Fine", "Testo"])
        self.captions_table.horizontalHeader().setStretchLastSection(True)
        self.captions_table.setColumnWidth(0, 80)
        self.captions_table.setColumnWidth(1, 80)
        self.captions_table.setAlternatingRowColors(True)
        self.captions_table.cellDoubleClicked.connect(self.caption_seek)
        self.captions_table.itemChanged.connect(self.mark_dirty)
        cl.addWidget(self.captions_table)
        row = QHBoxLayout()
        row.addWidget(button("+ Riga", self.add_caption))
        row.addWidget(button("− Riga", self.delete_caption))
        row.addWidget(button("Applica sottotitoli", self.commit_captions))
        cl.addLayout(row)
        vl.addWidget(self.caption_panel, 2)
        self.caption_panel.hide()
        splitter.addWidget(view)
        self.panels = QStackedWidget()
        self.panels.setMinimumWidth(350)
        splitter.addWidget(self.panels)
        splitter.setSizes([850, 420])
        self.make_analysis_panel()
        self.make_results_panel()
        self.make_editor_panel()
        self.make_export_panel()
        self.pages.addWidget(page)

    def timeline_state(self):
        if not self.project or self.current_clip<0 or self.preview_mode:return None
        return self.start_time.value(),self.end_time.value(),self.project.clips[self.current_clip].keyframes

    def trim_timeline(self,end,value):
        value=max(self.start_time.value()+.2,value) if end else min(self.end_time.value()-.2,value)
        (self.end_time if end else self.start_time).setValue(value)
        self.player.setPosition(round(value*1000))

    def make_export_panel(self):
        panel=QWidget()
        layout=QVBoxLayout(panel)
        title=label('Pronte per il tuo pubblico')
        title.setObjectName('title')
        layout.addWidget(title)
        layout.addWidget(label('MP4 · H.264 / AAC · nessun watermark. I file originali sono conservati.',True))
        layout.addWidget(button('Esporta le clip selezionate',self.export_batch,True))
        layout.addWidget(button('Esporta la clip in modifica',self.export_current))
        layout.addWidget(button('Risoluzione, fps e bitrate',lambda:self.pages.setCurrentIndex(2)))
        layout.addWidget(button('Apri cartella esportazioni',self.open_exports))
        self.export_history=QListWidget()
        self.export_history.itemDoubleClicked.connect(lambda item:QDesktopServices.openUrl(QUrl.fromLocalFile(item.text())))
        self.jobs.exported.connect(lambda path:self.export_history.addItem(path) if self.action=='export' else None)
        layout.addWidget(self.export_history,1)
        self.panels.addWidget(panel)

    def make_analysis_panel(self):
        panel = QWidget()
        l = QVBoxLayout(panel)
        title = label("Analizza e prepara")
        title.setObjectName("title")
        l.addWidget(title)
        l.addWidget(label("Trascrizione locale + proposte iniziali basate su frasi e termini tematici. Nessuna promessa di viralità.", True))
        form = QFormLayout()
        self.clip_count = spin(1, 30, 5)
        self.min_duration = spin(1, 180, 20, " s")
        self.max_duration = spin(1, 180, 60, " s")
        self.language = combo([("Automatico", "auto"), ("Italiano", "it"), ("English", "en")])
        form.addRow("Numero indicativo", self.clip_count)
        form.addRow("Durata minima", self.min_duration)
        form.addRow("Durata massima", self.max_duration)
        form.addRow("Lingua", self.language)
        l.addLayout(form)
        self.retranscribe = QCheckBox("Ricalcola trascrizione salvata")
        l.addWidget(self.retranscribe)
        self.vision_enabled = QCheckBox('Rileva webcam e proponi Smart Split')
        self.vision_enabled.setChecked(True)
        self.dynamic_enabled = QCheckBox('Proponi cambi layout sulle scene')
        l.addWidget(self.vision_enabled)
        l.addWidget(self.dynamic_enabled)
        l.addWidget(button("Analizza e genera clip", self.analyze, True))
        l.addWidget(button("Crea clip manuale", self.new_clip))
        l.addWidget(label("I confini delle proposte rispettano la punteggiatura riconosciuta. Se il parlato non offre segmenti adatti, vengono proposte meno clip: puoi aggiungerle dall'editor.", True))
        l.addStretch()
        l.addWidget(label("Rivedi le regioni proposte: visione e punteggi sono euristici. I silenzi sono rilevati per trascrivere, senza rimuovere parti della spiegazione.", True))
        self.panels.addWidget(panel)

    def make_results_panel(self):
        panel = QWidget()
        l = QVBoxLayout(panel)
        title = label("Le tue clip")
        title.setObjectName("title")
        l.addWidget(title)
        l.addWidget(label("Spunta le clip da esportare. Doppio clic per modificarle.", True))
        self.clip_list = QListWidget()
        self.clip_list.setIconSize(QSize(72,128))
        self.clip_list.itemDoubleClicked.connect(lambda _: self.edit_selected())
        self.clip_list.itemChanged.connect(self.selection_changed)
        l.addWidget(self.clip_list, 1)
        l.addWidget(button("Modifica clip", self.edit_selected))
        l.addWidget(button("Anteprima verticale", self.preview_selected))
        l.addWidget(button("Esporta selezionate", self.export_batch, True))
        l.addWidget(button("+ Clip manuale", self.new_clip))
        l.addWidget(button("Elimina clip evidenziata", self.delete_clip))
        self.panels.addWidget(panel)

    def make_editor_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        l = QVBoxLayout(panel)
        title = label("Editor clip")
        title.setObjectName("title")
        l.addWidget(title)
        form = QFormLayout()
        self.clip_title = QLineEdit()
        self.clip_description = QLineEdit()
        self.start_time = spin(0, 999999, 0, " s", True)
        self.end_time = spin(.2, 999999, 30, " s", True)
        form.addRow("Titolo", self.clip_title)
        form.addRow('Descrizione',self.clip_description)
        form.addRow("Inizio", self.start_time)
        form.addRow("Fine", self.end_time)
        l.addLayout(form)
        row = QHBoxLayout()
        row.addWidget(button("Inizio qui", lambda: self.mark_boundary(False)))
        row.addWidget(button("Fine qui", lambda: self.mark_boundary(True)))
        l.addLayout(row)
        self.layout_combo = combo([("Smart Split · riempi 35 / 65", "split"), ("Face Focus", "face"), ("Screen Focus", "screen"), ("Screen + Picture in Picture", "pip"), ("Dynamic · cambi sulla timeline", "dynamic"), ("Composizione manuale", "manual"), ("Crop verticale", "crop"), ("Adatta con bande · opzionale", "fit")])
        l.addWidget(label("Composizione"))
        l.addWidget(self.layout_combo)
        self.crop_position = QSlider(Qt.Orientation.Horizontal)
        self.crop_position.setRange(0, 1000)
        self.crop_position.setValue(500)
        l.addWidget(label("Posizione orizzontale del ritaglio", True))
        l.addWidget(self.crop_position)
        self.split_ratio=spin(20,65,35,' %')
        self.cam_zoom=spin(1,4,1,' ×',True)
        self.scr_zoom=spin(1,4,1,' ×',True)
        self.cam_x=spin(0,100,50,' %')
        self.cam_y=spin(0,100,50,' %')
        self.scr_x=spin(0,100,50,' %')
        self.scr_y=spin(0,100,50,' %')
        composition=QFormLayout()
        composition.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for text,widget in [('Altezza webcam',self.split_ratio),('Zoom webcam',self.cam_zoom),('Webcam X',self.cam_x),('Webcam Y',self.cam_y),('Zoom schermo',self.scr_zoom),('Schermo X',self.scr_x),('Schermo Y',self.scr_y)]:
            composition.addRow(text,widget)
            widget.valueChanged.connect(self.visual_changed)
        l.addLayout(composition)
        l.addWidget(button("Seleziona regione webcam…", lambda: self.choose_region("webcam")))
        l.addWidget(button("Seleziona area schermo…", lambda: self.choose_region("screen")))
        l.addWidget(button('Area webcam OBS da escludere…',lambda:self.choose_region('embedded_webcam')))
        l.addWidget(button('Bilancia webcam · margini e zoom',self.balance_webcam))
        l.addWidget(button('Rileva webcam nella clip', self.detect_webcam))
        l.addWidget(button('Disattiva tracking automatico', self.clear_tracking))
        l.addWidget(button('Collega video webcam separato…', self.choose_camera))
        l.addWidget(button('Usa webcam incorporata', self.clear_camera))
        self.camera_offset = spin(-99999,99999,0,' s',True)
        self.camera_offset.valueChanged.connect(self.visual_changed)
        l.addWidget(label('Offset webcam: tempo webcam = tempo sorgente + offset',True))
        l.addWidget(self.camera_offset)
        row=QHBoxLayout()
        row.addWidget(button('Salva layout…', self.save_layout))
        row.addWidget(button('Carica layout…', self.load_layout))
        l.addLayout(row)
        self.layout_keys=QListWidget()
        self.layout_keys.setMaximumHeight(115)
        self.layout_keys.itemDoubleClicked.connect(self.seek_layout_key)
        l.addWidget(label('Cambi di composizione · tempo originale'))
        l.addWidget(self.layout_keys)
        l.addWidget(button('Inserisci composizione qui', self.add_layout_key))
        l.addWidget(button('Rimuovi cambio selezionato', self.remove_layout_key))
        l.addWidget(button('Mostra / nascondi sottotitoli', lambda: self.caption_panel.setVisible(not self.caption_panel.isVisible())))
        self.rects = {"webcam": [.75,.7,.25,.3], "screen": [0,0,1,1]}
        self.exclusion_rect=None
        self.framing_note=label('',True)
        l.addWidget(self.framing_note)
        l.addWidget(label("La webcam OBS è esclusa dal contenuto inferiore con un ritaglio reale. Seleziona l'intero riquadro originale, inclusi bordi: zoom e tracking del volto non cambiano l'area esclusa. Nessun riempimento dei pixel nascosti.", True))
        self.style_combo = combo([(x,x) for x in ("Minimal", "Dynamic", "Bold Social", "Tech Clean")])
        self.style_combo.currentTextChanged.connect(self.preset_changed)
        self.font_combo = QFontComboBox()
        self.font_combo.setMaximumWidth(230)
        self.font_size = spin(20, 150, Clip.font_size, " px")
        self.margin_v = spin(0, 800, Clip.margin_v, " px")
        self.outline = spin(0, 12, Clip.outline, " px")
        self.shadow = spin(0, 12, Clip.shadow, " px")
        self.color = QLineEdit("#FFFFFF")
        self.highlight = QLineEdit("#55E0B0")
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addRow("Stile", self.style_combo)
        form.addRow("Font", self.font_combo)
        form.addRow("Dimensione (1080p)", self.font_size)
        form.addRow("Margine dal basso", self.margin_v)
        form.addRow("Contorno nero (1080p)", self.outline)
        form.addRow("Ombra nera (1080p)", self.shadow)
        form.addRow("Testo #RRGGBB", self.color)
        form.addRow("Evidenza #RRGGBB", self.highlight)
        l.addLayout(form)
        l.addWidget(button('Valori di leggibilità consigliati',self.readable_captions))
        l.addWidget(button('Scegli colore del testo…',self.choose_caption_color))
        self.burn = QCheckBox("Imprimi sottotitoli nel video")
        self.burn.setChecked(True)
        self.normalize = QCheckBox("Normalizza audio a −16 LUFS")
        self.normalize.setChecked(True)
        l.addWidget(self.burn)
        l.addWidget(self.normalize)
        l.addWidget(label("Safe area iniziale: 330 px dal basso, 145 px a destra. Verifica sempre l'anteprima. Testo corretto manualmente: timing di frase, senza evidenziazione parola finché non ritrascritto.", True))
        l.addWidget(button("Applica modifiche", self.apply_editor))
        l.addWidget(button("Genera anteprima verticale", self.preview_current))
        l.addWidget(button("Esporta questa clip", self.export_current, True))
        scroll.setWidget(panel)
        self.panels.addWidget(scroll)
        for w in (self.clip_title, self.clip_description, self.color, self.highlight):
            w.textEdited.connect(self.mark_dirty)
        for w in (self.start_time, self.end_time, self.font_size, self.margin_v, self.outline, self.shadow, self.crop_position):
            w.valueChanged.connect(self.mark_dirty)
        self.layout_combo.currentIndexChanged.connect(self.mark_dirty)
        self.layout_combo.currentIndexChanged.connect(self.visual_changed)
        self.style_combo.currentIndexChanged.connect(self.mark_dirty)
        self.font_combo.currentFontChanged.connect(self.mark_dirty)
        self.burn.toggled.connect(self.mark_dirty)
        self.normalize.toggled.connect(self.mark_dirty)
        for w in (self.font_size,self.margin_v,self.outline,self.shadow):
            w.valueChanged.connect(self.visual_changed)
        self.color.textChanged.connect(self.visual_changed)
        self.highlight.textChanged.connect(self.visual_changed)
        self.font_combo.currentFontChanged.connect(self.visual_changed)
        self.burn.toggled.connect(self.visual_changed)

    def make_settings(self):
        page = QWidget()
        l = QVBoxLayout(page)
        title = label("Impostazioni")
        title.setObjectName("title")
        l.addWidget(title)
        form = QFormLayout()
        self.model = combo([(x, x) for x in MODELS])
        self.device = combo([("Automatico · CUDA → CPU", "auto"), ("CPU · int8", "cpu"), ("Preferisci CUDA · fallback CPU", "cuda")])
        self.ffmpeg_dir = QLineEdit()
        self.export_dir = QLineEdit()
        self.fps = combo([("30 fps", 30), ("60 fps", 60)])
        self.encoder = combo([("Automatico · NVENC → CPU", "auto"), ("CPU · H.264", "cpu"), ("Preferisci NVIDIA NVENC", "nvenc")])
        self.resolution = combo([("1080 × 1920", 1080), ("720 × 1280", 720)])
        self.bitrate = spin(1, 100, 12, " Mbps")
        self.platform = combo([(x,x) for x in ("YouTube Shorts", "Instagram Reels", "TikTok", "Custom")])
        form.addRow("Modello Whisper", self.model)
        form.addRow("Inferenza", self.device)
        form.addRow("Cartella FFmpeg", self.ffmpeg_dir)
        form.addRow("Cartella export", self.export_dir)
        form.addRow("Preset destinazione", self.platform)
        form.addRow("Risoluzione", self.resolution)
        form.addRow("Frame rate", self.fps)
        form.addRow("Encoder", self.encoder)
        form.addRow("Bitrate video", self.bitrate)
        self.ai_mode=combo([('Offline · nessun servizio','offline'),('LM Studio · solo localhost','lmstudio'),('ChatGPT · quota autorizzata','chatgpt')])
        self.lm_endpoint=QLineEdit('http://127.0.0.1:1234/v1')
        self.ai_model=QComboBox()
        self.ai_model.setEditable(True)
        self.context_tokens=spin(4096,262144,8192,' token')
        form.addRow('Analisi semantica',self.ai_mode)
        form.addRow('Endpoint LM Studio',self.lm_endpoint)
        form.addRow('Modello AI',self.ai_model)
        form.addRow('Contesto disponibile',self.context_tokens)
        l.addLayout(form)
        l.addWidget(button('Leggi modelli disponibili',self.fetch_models))
        self.account=QComboBox()
        l.addWidget(label('Account ChatGPT · credenziali protette da Windows'))
        l.addWidget(self.account)
        self.allow_plan=QCheckBox('Autorizza anche l’uso del mio piano ChatGPT')
        self.allow_plan.setChecked(False)
        l.addWidget(self.allow_plan)
        l.addWidget(button('Continua con ChatGPT',self.signin))
        l.addWidget(button('Disconnetti account selezionato',self.signout))
        l.addWidget(button('Visualizza limiti del piano ChatGPT',lambda:QDesktopServices.openUrl(QUrl('https://chatgpt.com/settings/usage'))))
        self.account_status=label('',True)
        l.addWidget(self.account_status)
        self.account.currentIndexChanged.connect(self.account_changed)
        self.ai_mode.currentIndexChanged.connect(lambda:self.ai_model.clear())
        l.addWidget(label('Offline è la modalità predefinita. ChatGPT riceve solo testo e timestamp dopo una conferma per ogni analisi; può consumare la quota autorizzata. Nessun fallback automatico a servizi a pagamento. Accesso OAuth in anteprima: richiede verifica con il tuo account.',True))
        self.platform.currentIndexChanged.connect(self.platform_changed)
        l.addWidget(button("Scegli cartella FFmpeg", self.choose_ffmpeg))
        l.addWidget(button("Scegli cartella esportazioni", self.choose_export_dir))
        self.model_status = label("", True)
        l.addWidget(self.model_status)
        self.model.currentIndexChanged.connect(self.refresh_model)
        l.addWidget(button("Scarica modello selezionato", self.download_model))
        l.addWidget(label("Solo questo comando contatta Hugging Face per scaricare pesi pubblici. Nessun video, audio o testo viene caricato. Small ≈ 0,5 GB; Tiny è rapido ma meno accurato. I download possono essere ripresi.", True))
        l.addWidget(button("Salva impostazioni", self.save_settings, True))
        l.addWidget(button("Apri log diagnostici", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_root() / "jobs")))))
        l.addWidget(label("CUDA usa cuBLAS/cuDNN inclusi; in caso di errore riprova su CPU. NVENC è rilevato con una codifica effettiva. Visione YuNet locale; i cambi scena rimangono correggibili.", True))
        l.addStretch()
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.pages.addWidget(scroll)

    def account_changed(self):
        self.ai_model.clear()
        info=self.account.currentData(Qt.ItemDataRole.UserRole+1) or {}
        self.account_status.setText('Piano ChatGPT autorizzato' if info.get('plan') and info.get('connected') else 'Accesso o permesso del piano da autorizzare')

    def refresh_accounts(self,status=None):
        from .auth import public_status
        try:
            status=status or public_status()
            self.account.clear()
            self.account.addItem('Aggiungi un account / workspace','')
            for info in status['accounts']:
                self.account.addItem(info['label'],info['id'])
                self.account.setItemData(self.account.count()-1,info,Qt.ItemDataRole.UserRole+1)
            set_combo(self.account,status.get('active',''))
            self.account_changed()
        except Exception as exc:
            self.account_status.setText('Archivio credenziali: '+str(exc))

    def signin(self):
        self.start_job('signin',{'options':{'account':self.account.currentData(),'allow_plan':self.allow_plan.isChecked()}})

    def signout(self):
        if self.account.currentData():
            self.start_job('signout',{'options':{'account':self.account.currentData()}})

    def fetch_models(self):
        if self.ai_mode.currentData()=='offline':
            self.status.setText('Seleziona LM Studio o ChatGPT per leggere i modelli.'); return
        self.start_job('models',{'options':self.options()})

    def platform_changed(self):
        if self.platform.currentData() != "Custom":
            set_combo(self.resolution, 1080)
            set_combo(self.fps, 30)
            self.bitrate.setValue(12)

    def options(self):
        width = self.resolution.currentData()
        return {"model": self.model.currentData(), "device": self.device.currentData(), "tool_dir": self.ffmpeg_dir.text().strip(),
                "fps": self.fps.currentData(), "encoder": self.encoder.currentData(), "width": width, "height": width * 16 // 9,
                "bitrate": self.bitrate.value(),'ai_mode':self.ai_mode.currentData(),'lm_endpoint':self.lm_endpoint.text().strip(),
                'ai_model':self.ai_model.currentData() or self.ai_model.currentText(),'context_tokens':self.context_tokens.value(),
                'account':self.account.currentData() or ''}

    def load_settings(self):
        c = self.config
        set_combo(self.model, c.get("model", "small"))
        set_combo(self.device, c.get("device", "auto"))
        self.ffmpeg_dir.setText(c.get("tool_dir", str(app_root() / "tools")))
        self.export_dir.setText(c.get("export_dir", str(app_root() / "exports")))
        set_combo(self.platform, c.get("platform", "YouTube Shorts"))
        set_combo(self.fps, c.get("fps", 30))
        set_combo(self.encoder, c.get("encoder", "auto"))
        set_combo(self.resolution, c.get("width", 1080))
        self.bitrate.setValue(c.get("bitrate", 12))
        self.refresh_accounts()
        set_combo(self.ai_mode,c.get('ai_mode','offline'))
        self.lm_endpoint.setText(c.get('lm_endpoint','http://127.0.0.1:1234/v1'))
        self.ai_model.setEditText(c.get('ai_model',''))
        self.context_tokens.setValue(c.get('context_tokens',8192))
        self.refresh_model()

    def save_settings(self):
        self.config.update(self.options())
        self.config.update(export_dir=self.export_dir.text().strip(), platform=self.platform.currentData())
        atomic_json(self.config_path, self.config)
        self.status.setText("Impostazioni salvate.")

    def choose_ffmpeg(self):
        path = QFileDialog.getExistingDirectory(self, "Cartella FFmpeg", self.ffmpeg_dir.text())
        if path:
            self.ffmpeg_dir.setText(path)

    def choose_export_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Cartella esportazioni", self.export_dir.text())
        if path:
            self.export_dir.setText(path)

    def refresh_model(self):
        path = models_root() / (self.model.currentData() or "small")
        ready = (path / "model.bin").is_file()
        self.model_status.setText(("Installato: " if ready else "Da scaricare: ") + str(path))

    def download_model(self):
        self.start_job("download", {"options": self.options()})

    def resources(self):
        memory = psutil.virtual_memory()
        self.resource_label.setText(f"CPU {psutil.cpu_percent():.0f}%   •   RAM {memory.used / 2**30:.1f} / {memory.total / 2**30:.1f} GB   •   Inferenza isolata in processo separato   •   Dati locali")

    def mark_dirty(self, *args):
        if self.project:
            self.dirty = True
        if hasattr(self,'video'):
            self.video.update()
        if hasattr(self,'seek'):
            self.seek.update()

    def visual_changed(self,*args):
        self.mark_dirty()
        if self.project and self.current_clip>=0:
            if self.preview_mode:
                position=self.project.clips[self.current_clip].start+self.player.position()/1000
                self.source_preview(position)
            self.video.original=False
            self.video.update()
            state=self.live_state()
            if state and hasattr(self,'framing_note'):
                self.framing_note.setText('\n'.join(framing_warnings(state[0],state[1])))

    def draft_clip(self):
        if not self.project or self.current_clip<0:
            return None
        c=copy.deepcopy(self.project.clips[self.current_clip])
        c.layout=self.layout_combo.currentData()
        c.webcam,c.screen=self.rects['webcam'][:],self.rects['screen'][:]
        c.embedded_webcam=copy.deepcopy(self.exclusion_rect)
        c.crop_x=self.crop_position.value()/1000
        c.split_ratio=self.split_ratio.value()/100
        c.webcam_zoom,c.screen_zoom=self.cam_zoom.value(),self.scr_zoom.value()
        c.webcam_pan=[self.cam_x.value()/100,self.cam_y.value()/100]
        c.screen_pan=[self.scr_x.value()/100,self.scr_y.value()/100]
        c.style,c.font=self.style_combo.currentData(),self.font_combo.currentText()
        c.font_size,c.margin_v=self.font_size.value(),self.margin_v.value()
        c.outline,c.shadow=self.outline.value(),self.shadow.value()
        c.highlight=self.highlight.text()
        c.color,c.burn_captions=self.color.text(),self.burn.isChecked()
        c.description=self.clip_description.text().strip()
        c.camera_offset=self.camera_offset.value()
        return c

    def live_state(self):
        c=self.draft_clip()
        if c is None or self.preview_mode:
            return None
        return self.project.media,c,self.player.position()/1000,self.project.captions

    def vertical_live(self):
        if self.preview_mode:
            self.source_preview()
        self.video.original=False
        self.video.update()
        self.preview_label.setText('VERTICALE LIVE · geometria export · per karaoke esatto usa anteprima renderizzata')

    def camera_frame_changed(self, frame):
        image=frame.toImage()
        if not image.isNull() and hasattr(self,'video'):
            self.video.camera_image=image
            self.video.update()
            if self.player.playbackState()!=QMediaPlayer.PlaybackState.PlayingState:
                self.camera_player.pause()

    def sync_camera(self,*args):
        if not self.project or self.current_clip<0 or self.preview_mode:
            self.camera_player.pause()
            return
        c=self.project.clips[self.current_clip]
        if not c.camera_path:
            self.camera_player.stop()
            return
        url=QUrl.fromLocalFile(c.camera_path)
        if self.camera_player.source()!=url:
            self.video.camera_image=QImage()
            self.camera_player.setSource(url)
            self.camera_player.play()
        target=max(0,self.player.position()+round(self.camera_offset.value()*1000))
        if abs(self.camera_player.position()-target)>100:
            self.camera_player.setPosition(target)
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:
            self.camera_player.play()

    def choose_camera(self):
        if self.current_clip<0 or not self.apply_editor(quiet=True):
            return
        path,_=QFileDialog.getOpenFileName(self,'Video webcam separato','','Video (*.mp4 *.mkv *.mov)')
        if path:
            self.start_job('probe_camera',{'path':path,'options':self.options()})

    def clear_camera(self):
        if self.project and self.current_clip>=0:
            c=self.project.clips[self.current_clip]
            c.camera_path=''
            c.webcam_confirmed=False
            self.camera_player.stop()
            self.visual_changed()

    def detect_webcam(self):
        if self.project and self.current_clip>=0 and self.apply_editor(quiet=True):
            self.start_job('detect',{'project':self.project.to_dict(),'index':self.current_clip})

    def clear_tracking(self):
        if self.project and self.current_clip>=0:
            self.project.clips[self.current_clip].face_track=[]
            self.visual_changed()

    def balance_webcam(self):
        if not self.project or self.current_clip<0:return
        c=self.draft_clip()
        media=self.project.media
        w,h=media.width,media.height
        if c.camera_path:
            if self.video.camera_image.isNull():
                self.error('Attendi un fotogramma della webcam separata.'); return
            w,h=self.video.camera_image.width(),self.video.camera_image.height()
        # Match the pane aspect to the complete webcam ROI within UI limits;
        # retain headroom instead of adding digital zoom to fill a fixed ratio.
        ratio=1080*c.webcam[3]*h/(1920*c.webcam[2]*w)
        self.split_ratio.setValue(round(max(.2,min(.65,ratio))*100))
        self.cam_zoom.setValue(1)
        self.cam_x.setValue(50)
        self.cam_y.setValue(50)
        self.visual_changed()

    def layout_values(self):
        c=self.draft_clip()
        names=('layout','webcam','screen','split_ratio','webcam_zoom','screen_zoom','webcam_pan','screen_pan','embedded_webcam')
        return {name:copy.deepcopy(getattr(c,name)) for name in names}

    def save_layout(self):
        if self.current_clip<0 or not self.apply_editor(quiet=True):
            return
        name,ok=QInputDialog.getText(self,'Preset composizione','Nome del layout')
        if ok and name.strip():
            self.config.setdefault('layouts',{})[name.strip()]=self.layout_values()
            self.save_settings()

    def load_layout(self):
        presets=self.config.get('layouts',{})
        if not presets or self.current_clip<0:
            self.status.setText('Salva prima un layout da riutilizzare.')
            return
        name,ok=QInputDialog.getItem(self,'Preset composizione','Layout',list(presets),0,False)
        if ok:
            c=copy.deepcopy(self.project.clips[self.current_clip])
            c.embedded_webcam=None  # old presets did not store separate OBS bounds
            for key,value in presets[name].items():
                if key in self.layout_values():
                    setattr(c,key,copy.deepcopy(value))
            c.keyframes=[]
            c.face_track=[]
            c.webcam_confirmed=True
            try:
                c.validate(self.project.media)
            except ValueError as exc:
                self.error(str(exc)); return
            self.project.clips[self.current_clip]=c
            self.load_clip(self.current_clip)
            self.dirty=True

    def refresh_layout_keys(self):
        self.layout_keys.clear()
        if self.project and self.current_clip>=0:
            for k in self.project.clips[self.current_clip].keyframes:
                self.layout_keys.addItem(f"{format_time(k['time'])} · {k.get('layout','split')}")

    def seek_layout_key(self,item):
        k=self.project.clips[self.current_clip].keyframes[self.layout_keys.row(item)]
        if self.preview_mode:
            self.source_preview()
        self.player.setPosition(round(k['time']*1000))

    def add_layout_key(self):
        if self.current_clip<0 or self.preview_mode or not self.apply_editor(quiet=True):
            return
        c=self.project.clips[self.current_clip]
        c.face_track=[]
        t=round(self.player.position()/1000,3)
        if not c.start<=t<c.end:
            self.error('Sposta il cursore dentro la clip prima di inserire un cambio.'); return
        original=copy.deepcopy(c.keyframes)
        c.keyframes=[k for k in c.keyframes if abs(k['time']-t)>.1]+[{'time':t,**self.layout_values()}]
        c.keyframes.sort(key=lambda k:k['time'])
        try:
            c.validate(self.project.media)
        except ValueError as exc:
            c.keyframes=original
            self.error(str(exc)); return
        self.refresh_layout_keys()
        self.visual_changed()

    def remove_layout_key(self):
        row=self.layout_keys.currentRow()
        if self.project and self.current_clip>=0 and row>=0:
            del self.project.clips[self.current_clip].keyframes[row]
            self.refresh_layout_keys()
            self.visual_changed()

    def confirm_discard(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Modifiche non salvate", "Salvare il progetto prima di continuare?",
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def import_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importa video", "", "Video (*.mp4 *.mkv *.mov *.webm *.avi);;Tutti i file (*)")
        if path:
            self.import_path(path)

    def import_path(self, path):
        if self.jobs.busy or not self.confirm_discard():
            return
        self.start_job("probe", {"path": str(path), "options": self.options()})

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.jobs.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            path = urls[0].toLocalFile()
            if path.endswith(".lcproj"):
                self.load_project_path(path)
            else:
                self.import_path(path)

    def set_project(self, project, path=None):
        self.project = project
        self.project_path = Path(path) if path else None
        self.current_clip = -1
        self.dirty = False
        self.media_label.setText(Path(project.media.path).name)
        self.source_preview()
        self.refresh_clips()
        self.refresh_captions()
        self.show_studio(0)

    def show_studio(self, panel):
        if not self.project:
            self.status.setText("Importa prima un video.")
            self.pages.setCurrentIndex(0)
            return
        if self.panels.currentIndex() == 2 and panel != 2 and not self.apply_editor(quiet=True):
            return
        if panel == 2 and self.current_clip < 0:
            if self.project.clips:
                self.load_clip(0)
            else:
                self.new_clip()
                return
        self.pages.setCurrentIndex(1)
        self.panels.setCurrentIndex(panel)
        if panel!=2:
            self.caption_panel.hide()

    def source_preview(self,position=0):
        if not self.project:
            return
        self.preview_mode = False
        self.video.original=True
        self.last_frame = QImage()
        self.video.set_frame(QImage())
        self.pending_source_seek=round(float(position)*1000)
        self.prime_frame = True
        self.audio.setMuted(True)
        self.player.setSource(QUrl.fromLocalFile(self.project.media.path))
        self.preview_label.setText(f"ORIGINALE · {self.project.media.width} × {self.project.media.height} · {self.project.media.fps:.2f} fps")
        # Pause when a frame really arrives; loading may exceed a fixed delay.
        self.player.play()

    def frame_changed(self, frame):
        if not self.preview_mode and frame.isValid() and self.pending_source_seek is not None and self.player.isSeekable():
            target=self.pending_source_seek
            self.pending_source_seek=None
            if target>0:
                self.player.setPosition(target)
                return
        if frame.isValid():
            self.video.set_frame(frame.toImage())
        if not self.preview_mode and frame.isValid():
            self.last_frame = frame.toImage()
            if self.prime_frame:
                self.prime_frame = False
                QTimer.singleShot(0, self.finish_priming)

    def finish_priming(self):
        self.player.pause()
        self.audio.setMuted(False)

    def toggle_play(self):
        self.prime_frame = False
        self.audio.setMuted(False)
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def position_changed(self, value):
        self.video.update()
        self.sync_camera()
        if not self.seek.isSliderDown():
            self.seek.setValue(value)
        self.time_label.setText(f"{format_time(value/1000)} / {format_time(self.player.duration()/1000)}")

    def analyze(self):
        if not self.project:
            return
        if not self.commit_captions():
            return
        if self.min_duration.value() > self.max_duration.value():
            self.error("La durata minima supera la massima.")
            return
        if self.project.clips:
            answer = QMessageBox.question(self, "Rigenera proposte", "Le proposte attuali saranno sostituite. Continuare?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        options = self.options() | {"count": self.clip_count.value(), "minimum": self.min_duration.value(), "maximum": self.max_duration.value(),
                                    "language": self.language.currentData(), "retranscribe": self.retranscribe.isChecked(),
                                    'vision':self.vision_enabled.isChecked(),'dynamic':self.dynamic_enabled.isChecked()}
        if options['ai_mode']=='chatgpt':
            answer=QMessageBox.question(self,'Analisi con il piano ChatGPT',
                'Inviare la trascrizione e i timestamp a OpenAI per questa analisi? Il video e l’audio restano locali. Questa azione usa il piano ChatGPT e gli eventuali crediti che hai autorizzato nelle impostazioni ChatGPT.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes: return
            options['cloud_consent']=True
        self.start_job("analyze", {"project": self.project.to_dict(), "options": options})

    def new_clip(self):
        if not self.project:
            return
        if self.current_clip >= 0 and self.panels.currentIndex() == 2 and not self.apply_editor(quiet=True):
            return
        start = 0 if self.preview_mode else min(self.player.position()/1000, max(0, self.project.media.duration-.3))
        clip = Clip(start, min(self.project.media.duration, start+30), f"Clip {len(self.project.clips)+1}")
        self.project.clips.append(clip)
        self.dirty = True
        self.refresh_clips()
        self.load_clip(len(self.project.clips)-1)
        self.show_studio(2)

    def refresh_clips(self):
        self.clip_list.blockSignals(True)
        self.clip_list.clear()
        if self.project:
            for c in self.project.clips:
                score = f"{c.score}/100" if c.score else "Manuale"
                item = QListWidgetItem(f"{c.title}\n{format_time(c.start)} → {format_time(c.end)} · {c.duration:.1f} s · {score}\n{c.reason}")
                if c.thumbnail and Path(c.thumbnail).is_file():
                    item.setIcon(QIcon(c.thumbnail))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if c.selected else Qt.CheckState.Unchecked)
                self.clip_list.addItem(item)
        self.clip_list.blockSignals(False)
        if self.clip_list.count():
            self.clip_list.setCurrentRow(max(0, min(self.current_clip, self.clip_list.count()-1)))

    def selection_changed(self, item):
        if self.project:
            self.project.clips[self.clip_list.row(item)].selected = item.checkState() == Qt.CheckState.Checked
            self.dirty = True

    def delete_clip(self):
        row = self.clip_list.currentRow()
        if self.project and row >= 0:
            del self.project.clips[row]
            self.current_clip = -1
            self.dirty = True
            self.refresh_clips()

    def edit_selected(self):
        row = self.clip_list.currentRow()
        if row >= 0:
            self.load_clip(row)
            self.show_studio(2)

    def load_clip(self, index):
        was_dirty = self.dirty
        self.current_clip = index
        c = self.project.clips[index]
        self.clip_title.setText(c.title)
        self.clip_description.setText(c.description)
        self.start_time.setMaximum(self.project.media.duration)
        self.end_time.setMaximum(self.project.media.duration)
        self.start_time.setValue(c.start)
        self.end_time.setValue(c.end)
        set_combo(self.layout_combo, c.layout)
        set_combo(self.style_combo, c.style)
        self.font_combo.setCurrentText(c.font)
        self.font_size.setValue(c.font_size)
        self.outline.setValue(c.outline)
        self.shadow.setValue(c.shadow)
        self.margin_v.setValue(c.margin_v)
        self.color.setText(c.color)
        self.highlight.setText(c.highlight)
        self.crop_position.setValue(round(c.crop_x * 1000))
        self.burn.setChecked(c.burn_captions)
        self.normalize.setChecked(c.normalize)
        self.rects = {"webcam": c.webcam[:], "screen": c.screen[:]}
        self.exclusion_rect=copy.deepcopy(c.embedded_webcam)
        self.split_ratio.setValue(round(c.split_ratio*100))
        self.cam_zoom.setValue(c.webcam_zoom)
        self.scr_zoom.setValue(c.screen_zoom)
        self.cam_x.setValue(round(c.webcam_pan[0]*100))
        self.cam_y.setValue(round(c.webcam_pan[1]*100))
        self.scr_x.setValue(round(c.screen_pan[0]*100))
        self.scr_y.setValue(round(c.screen_pan[1]*100))
        self.camera_offset.setValue(c.camera_offset)
        self.refresh_layout_keys()
        self.sync_camera()
        if self.preview_mode:
            self.source_preview()
        self.player.setPosition(round(c.start*1000))
        self.vertical_live()
        self.dirty = was_dirty

    def preset_changed(self, name):
        size, outline, shadow = PRESETS[name]
        self.font_size.setValue(size)
        self.outline.setValue(outline)
        self.shadow.setValue(shadow)

    def readable_captions(self):
        self.preset_changed(self.style_combo.currentData())
        self.color.setText('#FFFFFF')
        self.visual_changed()

    def choose_caption_color(self):
        value=QColorDialog.getColor(QColor(self.color.text()),self,'Colore sottotitoli')
        if value.isValid():self.color.setText(value.name().upper())

    def mark_boundary(self, end):
        if self.preview_mode:
            self.error("Torna all'originale prima di impostare i confini.")
            return
        (self.end_time if end else self.start_time).setValue(self.player.position()/1000)

    def choose_region(self, name):
        if self.preview_mode or self.last_frame.isNull():
            self.error("Apri l'originale e riproduci un fotogramma prima di selezionare la regione.")
            return
        self.player.pause()
        c=self.project.clips[self.current_clip]
        image=self.video.camera_image if name=='webcam' and c.camera_path else self.last_frame
        if image.isNull():
            self.error('Attendi un fotogramma della webcam separata.'); return
        rect=(self.exclusion_rect or self.rects['webcam']) if name=='embedded_webcam' else self.rects[name]
        excluded=None
        if name=='screen':
            from .reframing import overlay_bounds
            box=overlay_bounds(self.project.media,self.draft_clip(),self.player.position()/1000)
            if box:
                m=self.project.media
                excluded=[box[0]/m.width,box[1]/m.height,box[2]/m.width,box[3]/m.height]
        dialog = RegionDialog(image, rect, "Regione " + name, self,excluded=excluded)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if name=='embedded_webcam':
                self.exclusion_rect=dialog.result_rect()
            else:
                self.rects[name] = dialog.result_rect()
            if name=='webcam':
                self.project.clips[self.current_clip].webcam_confirmed=True
                self.project.clips[self.current_clip].face_track=[]
                if not c.camera_path:
                    self.exclusion_rect=self.rects[name][:]
            self.dirty = True
            self.visual_changed()

    def refresh_captions(self):
        self.captions_table.blockSignals(True)
        self.captions_table.setRowCount(len(self.project.captions) if self.project else 0)
        for row, c in enumerate(self.project.captions if self.project else []):
            for col, text in enumerate((f"{c.start:.3f}", f"{c.end:.3f}", c.text)):
                self.captions_table.setItem(row, col, QTableWidgetItem(text))
        self.captions_table.blockSignals(False)

    def caption_seek(self, row, column):
        if column == 0 and not self.preview_mode:
            try:
                self.player.setPosition(int(float(self.captions_table.item(row,0).text())*1000))
            except ValueError:
                pass

    def add_caption(self):
        if not self.project:
            return
        row = self.captions_table.rowCount()
        self.captions_table.insertRow(row)
        start = min(self.player.position()/1000, max(0, self.project.media.duration-.5))
        for col, text in enumerate((f"{start:.3f}", f"{min(start+2,self.project.media.duration):.3f}", "Testo")):
            self.captions_table.setItem(row, col, QTableWidgetItem(text))
        self.dirty = True

    def delete_caption(self):
        row = self.captions_table.currentRow()
        if row >= 0:
            self.captions_table.removeRow(row)
            self.dirty = True

    def commit_captions(self):
        if not self.project:
            return True
        try:
            rows = []
            existing = {(round(c.start,3), round(c.end,3), c.text): c for c in self.project.captions}
            for row in range(self.captions_table.rowCount()):
                a, b = [float(self.captions_table.item(row, col).text().replace(",", ".")) for col in (0,1)]
                text = self.captions_table.item(row,2).text().strip()
                if not text or not 0 <= a < b <= self.project.media.duration + .05:
                    raise ValueError(f"Controlla la riga {row+1}: testo e tempi devono essere validi.")
                rows.append(copy.deepcopy(existing.get((a,b,text), Caption(a,b,text))))
            rows.sort(key=lambda c: c.start)
            if any(a.end > b.start for a,b in zip(rows, rows[1:])):
                raise ValueError("Due sottotitoli si sovrappongono: correggi i timestamp.")
            if rows != self.project.captions:
                self.project.captions = rows
                self.dirty = True
            self.refresh_captions()
            return True
        except (ValueError, AttributeError) as exc:
            self.error(str(exc))
            return False

    def apply_editor(self, checked=False, quiet=False):
        if not self.project or self.current_clip < 0:
            return True
        try:
            from .subtitles import ass_color
            ass_color(self.color.text().strip())
            ass_color(self.highlight.text().strip())
            c = self.draft_clip()
            c.start, c.end = self.start_time.value(), self.end_time.value()
            if c.face_track:
                from .reframing import track_value
                first={'time':c.start,**{axis:track_value(c.face_track,c.start,axis) for axis in ('x','y')}}
                c.face_track=[first]+[p for p in c.face_track if c.start<p['time']<c.end]
            c.keyframes=[k for k in c.keyframes if c.start<=k['time']<c.end]
            c.title = self.clip_title.text().strip() or "Clip"
            c.layout = self.layout_combo.currentData()
            c.crop_x = self.crop_position.value()/1000
            c.webcam, c.screen = self.rects["webcam"][:], self.rects["screen"][:]
            c.style, c.font = self.style_combo.currentData(), self.font_combo.currentText()
            c.font_size, c.margin_v = self.font_size.value(), self.margin_v.value()
            c.outline, c.shadow = self.outline.value(), self.shadow.value()
            c.color, c.highlight = self.color.text().strip(), self.highlight.text().strip()
            c.burn_captions, c.normalize = self.burn.isChecked(), self.normalize.isChecked()
            c.validate(self.project.media)
            if not self.commit_captions():
                return False
            if c != self.project.clips[self.current_clip]:
                self.project.clips[self.current_clip] = c
                self.dirty = True
            self.refresh_clips()
            if not quiet:
                self.status.setText("Modifiche applicate. Genera l'anteprima per verificare il risultato.")
            return True
        except ValueError as exc:
            self.error(str(exc))
            return False

    def preview_selected(self):
        row = self.clip_list.currentRow()
        if row >= 0:
            self.load_clip(row)
            self.preview_current()

    def preview_current(self):
        if self.current_clip < 0 or not self.apply_editor(quiet=True):
            return
        options = self.options() | {"width":360, "height":640, "bitrate":2, "fps":30}
        self.start_job("preview", {"project": self.project.to_dict(), "indices":[self.current_clip], "options":options,
                                   "directory":str(data_root() / "previews")})

    def export_current(self):
        if self.current_clip >= 0 and self.apply_editor(quiet=True):
            self.export_indices([self.current_clip])

    def export_batch(self):
        if self.project:
            self.export_indices([i for i,c in enumerate(self.project.clips) if c.selected])

    def export_indices(self, indices):
        if not indices:
            self.error("Seleziona almeno una clip.")
            return
        if not self.export_dir.text().strip():
            self.error("Scegli la cartella esportazioni nelle Impostazioni.")
            return
        self.start_job("export", {"project": self.project.to_dict(), "indices":indices, "options":self.options(), "directory": self.export_dir.text().strip()})

    def open_exports(self):
        path = Path(self.export_dir.text().strip() or app_root() / "exports")
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def start_job(self, action, request):
        if self.jobs.busy:
            return
        self.player.pause()
        self.action = action
        self.progress.setRange(0,0)
        self.status.setText("Avvio operazione…")
        self.interaction.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.jobs.start({"action": action, **request})

    def job_progress(self, value, message):
        self.status.setText(message)
        self.status.setToolTip(message)
        if value is None:
            self.progress.setRange(0,0)
        else:
            self.progress.setRange(0,1000)
            self.progress.setValue(round(value*1000))

    def end_job(self):
        self.interaction.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.setRange(0,1000)

    def job_done(self, result):
        self.end_job()
        self.progress.setValue(1000)
        if self.action == "probe":
            self.set_project(Project(Media(**result)))
            self.dirty = True
            self.status.setText("Video importato. Analizza il parlato oppure crea una clip manuale.")
        elif self.action == 'probe_camera':
            c=self.project.clips[self.current_clip]
            if not c.camera_path and c.webcam_confirmed and c.embedded_webcam is None:
                c.embedded_webcam=c.webcam[:]
            c.camera_path=result['path']
            c.webcam=[0,0,1,1]
            c.webcam_confirmed=True
            c.keyframes=[]
            c.face_track=[]
            self.load_clip(self.current_clip)
            self.dirty=True
            self.status.setText('Webcam collegata. Regola l’offset e controlla la sincronizzazione nell’anteprima renderizzata.')
        elif self.action == 'detect':
            from .vision import apply_detection
            c=self.project.clips[self.current_clip]
            applied=apply_detection(c,result,c.layout=='dynamic')
            self.load_clip(self.current_clip)
            self.dirty=True
            self.status.setText(f"Affidabilità webcam {result['confidence']:.0%}. {result['reason']}")
            if not applied:
                self.error(result['reason']+' Usa Seleziona regione webcam.')
        elif self.action in ('signin','signout'):
            self.refresh_accounts(result)
            self.status.setText(result.get('warning') or ('Accesso completato. Verifica il permesso del piano prima di analizzare.' if self.action=='signin' else 'Credenziali locali rimosse.'))
        elif self.action=='models':
            self.ai_model.clear()
            for model in result['models']:
                self.ai_model.addItem(model['name'],model['id'])
            self.status.setText(f"{len(result['models'])} modelli disponibili.")
        elif self.action == "analyze":
            path = self.project_path
            self.set_project(Project.from_dict(result["project"]), path)
            self.dirty = True
            self.show_studio(1)
            self.status.setText(f"{len(self.project.clips)} proposte · {len(self.project.captions)} sottotitoli · {result['device']}. {result.get('warning','')}")
            # Automatic recovery snapshot, including captions, after the expensive phase.
            self.project.save(data_root() / "recovery.lcproj")
        elif self.action == "download":
            self.refresh_model()
            self.status.setText("Modello scaricato e disponibile offline.")
        elif self.action == "preview":
            self.prime_frame = False
            self.audio.setMuted(False)
            self.preview_mode = True
            self.video.original=True
            self.video.set_frame(QImage())
            self.player.setSource(QUrl.fromLocalFile(result["exports"][0]["path"]))
            self.preview_label.setText("ANTEPRIMA VERTICALE · render 360 × 640 · modifiche applicate")
            self.player.play()
            self.status.setText("Anteprima pronta. L'export usa la risoluzione scelta nelle Impostazioni.")
        elif self.action == "export":
            exports = result["exports"]
            self.status.setText(f"Esportate e verificate {len(exports)} clip. Encoder: {', '.join(sorted({e['encoder'] for e in exports}))}.")

    def job_failed(self, message):
        self.end_job()
        self.progress.setValue(0)
        self.status.setText("Operazione non completata. Consulta i dettagli e i log.")
        self.error(message)

    def job_cancelled(self):
        self.end_job()
        self.progress.setValue(0)
        self.status.setText("Operazione annullata. Eventuali clip già esportate sono conservate.")

    def error(self, message):
        QMessageBox.warning(self, "LocalClips AI", message)

    def save_project(self):
        if not self.project:
            return False
        if self.current_clip >= 0 and not self.apply_editor(quiet=True):
            return False
        if not self.commit_captions():
            return False
        path = str(self.project_path or data_root() / (Path(self.project.media.path).stem + ".lcproj"))
        path, _ = QFileDialog.getSaveFileName(self, "Salva progetto modificabile", path, "LocalClips (*.lcproj)")
        if not path:
            return False
        if not path.endswith(".lcproj"):
            path += ".lcproj"
        try:
            self.project.save(path)
            self.project_path = Path(path)
            self.dirty = False
            self.remember(path)
            self.status.setText("Progetto salvato: " + path)
            return True
        except OSError as exc:
            self.error(str(exc))
            return False

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Apri progetto", str(data_root()), "LocalClips (*.lcproj)")
        if path:
            self.load_project_path(path)

    def load_project_path(self, path):
        if not self.confirm_discard():
            return
        try:
            project = Project.load(path)
            source = Path(project.media.path)
            if not source.is_file():
                replacement, _ = QFileDialog.getOpenFileName(self, "Ricollega il video originale mancante")
                if not replacement:
                    return
                source = Path(replacement)
            stat = source.stat()
            if project.media.size and stat.st_size != project.media.size:
                raise ValueError("Il video ha una dimensione diversa dall'originale. Importalo come nuovo progetto per evitare tagli non corretti.")
            if str(source) == project.media.path and project.media.mtime_ns and stat.st_mtime_ns != project.media.mtime_ns:
                raise ValueError("Il video originale è stato modificato. Importalo come nuovo progetto.")
            project.media.path = str(source.resolve())
            project.media.mtime_ns = stat.st_mtime_ns
            self.set_project(project, path)
            self.remember(path)
            self.status.setText("Progetto caricato senza rianalizzare il video.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.error("Impossibile aprire il progetto: " + str(exc))

    def remember(self, path):
        recent = self.config.get("recent", [])
        self.config["recent"] = [str(path)] + [p for p in recent if p != str(path)][:11]
        atomic_json(self.config_path, self.config)
        self.refresh_recent()

    def refresh_recent(self):
        self.recent.clear()
        paths = self.config.get("recent", [])
        recovery = data_root() / "recovery.lcproj"
        if recovery.is_file():
            paths = [str(recovery)] + paths
        for p in paths:
            if Path(p).is_file():
                item = QListWidgetItem(f"{Path(p).stem}\n{p}")
                item.setData(Qt.ItemDataRole.UserRole, p)
                self.recent.addItem(item)

    def closeEvent(self, event):
        if self.jobs.busy:
            self.status.setText("Annulla l'operazione in corso prima di chiudere.")
            event.ignore()
            return
        if not self.confirm_discard():
            event.ignore()
            return
        self.player.stop()
        self.camera_player.stop()
        self.save_settings()
        event.accept()


def run():
    logging.basicConfig(filename=data_root() / "application.log", level=logging.INFO, encoding="utf-8")
    app = QApplication(sys.argv)
    app.setApplicationName("LocalClips AI")
    app.setOrganizationName("LocalClips")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        arg = sys.argv[1]
        QTimer.singleShot(0, lambda: window.load_project_path(arg) if arg.endswith(".lcproj") else window.import_path(arg))
    return app.exec()
