"""Lumen Player — минималистичный тёмный видеоплеер на libmpv.

Ключевые возможности:
  * HDR10 / HLG / Dolby Vision (P5/P7/P8) с корректным тон-маппингом на обычных (SDR) мониторах
    — движок gpu-next (libplacebo) + Direct3D 11;
  * режимы растяжки: по размеру, заполнить (обрезка), растянуть, 16:9, 4:3, 21:9, 1:1;
  * автоподгрузка субтитров рядом с файлом (как в VLC), автоопределение кодировки;
  * аппаратное декодирование (d3d11va / nvdec / dxva2).
"""
import os
import sys
import locale

# libmpv ищется рядом с exe (в сборке) или рядом с main.py (при запуске из исходников)
_base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
os.environ["PATH"] = _base + os.pathsep + os.environ.get("PATH", "")
if hasattr(os, "add_dll_directory"):
    try:
        os.add_dll_directory(_base)
    except OSError:
        pass

from PySide6.QtCore import Qt, QTimer, Signal, QSettings, QPoint
from PySide6.QtGui import QAction, QActionGroup, QColor, QPalette, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

locale.setlocale(locale.LC_NUMERIC, "C")  # libmpv требует C-локаль для чисел
import mpv  # noqa: E402  (импорт после настройки PATH)

APP_NAME = "Lumen Player"
VIDEO_EXT = (".mkv", ".mp4", ".avi", ".mov", ".webm", ".m4v", ".ts", ".m2ts",
             ".wmv", ".flv", ".mpg", ".mpeg", ".iso")
SUB_EXT = (".srt", ".ass", ".ssa", ".sub", ".vtt")

ASPECTS = [  # (название, video-aspect-override, panscan, keepaspect)
    ("По размеру окна", "-1", 0.0, True),
    ("Заполнить экран (обрезать)", "-1", 1.0, True),
    ("Растянуть на весь экран", "-1", 0.0, False),
    ("16:9", "16:9", 0.0, True),
    ("4:3", "4:3", 0.0, True),
    ("21:9", "21:9", 0.0, True),
    ("1:1", "1:1", 0.0, True),
]

HDR_MODES = [  # (название, target-colorspace-hint)
    ("Авто: HDR на HDR-мониторе, тон-маппинг на SDR", "auto"),
    ("Всегда тон-маппинг в SDR (цвета как задумано)", "no"),
]

KEYMAP = {  # клавиша mpv -> действие
    "SPACE": "pause", "MBTN_LEFT": "pause", "MBTN_LEFT_DBL": "fullscreen",
    "MBTN_RIGHT": "menu", "f": "fullscreen", "ESC": "exit_fs", "ENTER": "fullscreen",
    "RIGHT": "seek:5", "LEFT": "seek:-5", "shift+RIGHT": "seek:30", "shift+LEFT": "seek:-30",
    "ctrl+RIGHT": "seek:120", "ctrl+LEFT": "seek:-120",
    "UP": "vol:5", "DOWN": "vol:-5", "WHEEL_UP": "vol:5", "WHEEL_DOWN": "vol:-5",
    "m": "mute", "v": "sub_cycle", "b": "audio_cycle", "a": "aspect_cycle",
    "h": "hdr_cycle", "o": "open", "s": "sub_open", "z": "subdelay:-0.1",
    "x": "subdelay:0.1", "[": "speed:0.9", "]": "speed:1.1", "BS": "speed_reset",
    ".": "frame", ",": "frame_back", "n": "next", "p": "prev", "i": "info",
}


def fmt_time(sec):
    if sec is None or sec < 0:
        sec = 0
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


STYLE = """
* { font-family: 'Segoe UI', sans-serif; font-size: 13px; }
QMainWindow, QWidget#bar { background: #0f0f10; }
QLabel { color: #b8b8bc; }
QPushButton { background: transparent; color: #e8e8ea; border: none; padding: 6px 10px;
              font-size: 16px; border-radius: 6px; }
QPushButton:hover { background: #26262a; }
QSlider::groove:horizontal { height: 4px; background: #2e2e33; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #7c9cff; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;
                             background: #e8e8ea; }
QMenu { background: #18181a; color: #e8e8ea; border: 1px solid #2e2e33; padding: 4px; }
QMenu::item { padding: 6px 24px; border-radius: 4px; }
QMenu::item:selected { background: #2a2a30; }
QMenu::separator { height: 1px; background: #2e2e33; margin: 4px 8px; }
"""


class VideoSurface(QWidget):
    """Нативное окно, в которое рисует mpv."""
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setStyleSheet("background:#000;")


class SeekSlider(QSlider):
    """Слайдер, по которому можно кликнуть в любое место."""
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            v = QSlider.minimum(self) + (QSlider.maximum(self) - QSlider.minimum(self)) * e.position().x() / self.width()
            self.setValue(int(v))
            self.sliderMoved.emit(int(v))
        super().mousePressEvent(e)


class Player(QMainWindow):
    action = Signal(str)
    pos_changed = Signal(float)
    dur_changed = Signal(float)
    pause_changed = Signal(bool)
    title_changed = Signal(str)

    def __init__(self, files):
        super().__init__()
        self.settings = QSettings("LumenPlayer", "Lumen")
        self.aspect_idx = 0
        self.hdr_idx = int(self.settings.value("hdr_idx", 0))
        self.duration = 0.0
        self.seeking = False
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.resize(1100, 660)
        self.setMinimumSize(480, 300)

        # --- UI ---
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.video = VideoSurface()
        lay.addWidget(self.video, 1)

        self.bar = QWidget()
        self.bar.setObjectName("bar")
        b = QHBoxLayout(self.bar)
        b.setContentsMargins(10, 6, 10, 8)
        self.btn_play = QPushButton("▶")
        self.btn_play.clicked.connect(lambda: self.do("pause"))
        self.btn_open = QPushButton("⏏")
        self.btn_open.clicked.connect(lambda: self.do("open"))
        self.lbl_pos = QLabel("00:00")
        self.slider = SeekSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(lambda: setattr(self, "seeking", True))
        self.slider.sliderReleased.connect(lambda: setattr(self, "seeking", False))
        self.slider.sliderMoved.connect(self.on_seek)
        self.lbl_dur = QLabel("00:00")
        self.btn_aspect = QPushButton("⛶")
        self.btn_aspect.setToolTip("Растяжка (A)")
        self.btn_aspect.clicked.connect(lambda: self.do("aspect_cycle"))
        self.btn_mute = QPushButton("🔊")
        self.btn_mute.clicked.connect(lambda: self.do("mute"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 130)
        self.vol.setFixedWidth(90)
        self.vol.valueChanged.connect(lambda v: self.set_volume(v))
        self.btn_fs = QPushButton("⤢")
        self.btn_fs.clicked.connect(lambda: self.do("fullscreen"))
        for w in (self.btn_open, self.btn_play, self.lbl_pos, self.slider, self.lbl_dur,
                  self.btn_aspect, self.btn_mute, self.vol, self.btn_fs):
            b.addWidget(w, 1 if w is self.slider else 0)
        lay.addWidget(self.bar)
        self.setCentralWidget(root)

        # --- mpv ---
        self.mpv = mpv.MPV(
            wid=str(int(self.video.winId())),
            vo="gpu-next", gpu_api="d3d11", gpu_context="d3d11",
            hwdec="auto-safe", video_sync="audio",
            # HDR / Dolby Vision: libplacebo сам применяет DV-реконструкцию (P5/P7/P8)
            # и тон-маппинг в цветовое пространство монитора.
            target_colorspace_hint=HDR_MODES[self.hdr_idx][1],
            tone_mapping="bt.2390", hdr_compute_peak="yes",
            gamut_mapping_mode="auto", target_trc="auto", target_prim="auto",
            # Производительность / качество
            scale="spline36", dscale="mitchell", cscale="bilinear",
            dither_depth="auto", deband="no", vd_lavc_dr="yes",
            cache="yes", demuxer_max_bytes="150MiB", demuxer_readahead_secs="20",
            # Субтитры как в VLC: файлы с тем же именем подхватываются автоматически
            sub_auto="fuzzy", sub_file_paths="subs:Subs:Subtitles:subtitles",
            sub_codepage="utf8:cp1251", slang="ru,rus,ru-RU,en,eng",
            alang="ru,rus,en,eng", sub_font="Segoe UI", sub_font_size=46,
            sub_border_size=2.4, sub_shadow_offset=1, sub_margin_y=36,
            # Интерфейс отдан Qt
            osc="no", osd_bar="no", input_default_bindings="no",
            input_vo_keyboard="yes", cursor_autohide=1500, keep_open="yes",
            border="no", force_window="yes", idle="yes",
            osd_font="Segoe UI", osd_font_size=30, osd_border_size=2,
            msg_level="all=warn",
        )
        self.mpv.volume = float(self.settings.value("volume", 80))
        self.vol.setValue(int(self.mpv.volume))
        self._bind_keys()
        self.mpv.observe_property("time-pos", lambda n, v: self.pos_changed.emit(v or 0.0))
        self.mpv.observe_property("duration", lambda n, v: self.dur_changed.emit(v or 0.0))
        self.mpv.observe_property("pause", lambda n, v: self.pause_changed.emit(bool(v)))
        self.mpv.observe_property("media-title", lambda n, v: self.title_changed.emit(v or ""))
        self.action.connect(self.do)
        self.pos_changed.connect(self.on_pos)
        self.dur_changed.connect(self.on_dur)
        self.pause_changed.connect(lambda p: self.btn_play.setText("▶" if p else "⏸"))
        self.title_changed.connect(lambda t: self.setWindowTitle(f"{t} — {APP_NAME}" if t else APP_NAME))

        # Автоскрытие панели в полноэкранном режиме (по движению курсора)
        self._last_cursor = QPoint()
        self._idle_ms = 0
        self.idle_timer = QTimer(self, interval=150, timeout=self.poll_cursor)
        self.idle_timer.start()

        if files:
            self.open_files(files)

    # ---------- привязки ----------
    def _bind_keys(self):
        @self.mpv.message_handler("lumen")
        def _handler(*args):
            if args:
                self.action.emit(str(args[0]))
        for key, act in KEYMAP.items():
            self.mpv.command("keybind", key, f"script-message lumen {act}")

    # ---------- действия ----------
    def do(self, act):
        m = self.mpv
        name, _, arg = act.partition(":")
        if name == "pause":
            m.pause = not m.pause
        elif name == "fullscreen":
            self.toggle_fullscreen()
        elif name == "exit_fs":
            if self.isFullScreen():
                self.toggle_fullscreen()
        elif name == "seek":
            m.command("seek", arg, "relative+exact" if abs(float(arg)) < 10 else "relative")
        elif name == "vol":
            self.vol.setValue(max(0, min(130, int(m.volume + float(arg)))))
            m.show_text(f"Громкость {int(m.volume)}%")
        elif name == "mute":
            m.mute = not m.mute
            self.btn_mute.setText("🔇" if m.mute else "🔊")
        elif name == "sub_cycle":
            m.command("cycle", "sub")
            m.show_text("Субтитры: ${sid} ${sub-lang}")
        elif name == "audio_cycle":
            m.command("cycle", "audio")
            m.show_text("Аудио: ${aid} ${audio-codec-name}")
        elif name == "aspect_cycle":
            self.set_aspect((self.aspect_idx + 1) % len(ASPECTS))
        elif name == "hdr_cycle":
            self.set_hdr((self.hdr_idx + 1) % len(HDR_MODES))
        elif name == "open":
            self.dialog_open()
        elif name == "sub_open":
            self.dialog_sub()
        elif name == "subdelay":
            m.sub_delay = round(m.sub_delay + float(arg), 2)
            m.show_text(f"Задержка субтитров {m.sub_delay:+.1f} с")
        elif name == "speed":
            m.speed = max(0.25, min(4.0, m.speed * float(arg)))
            m.show_text(f"Скорость x{m.speed:.2f}")
        elif name == "speed_reset":
            m.speed = 1.0
            m.show_text("Скорость x1.00")
        elif name == "frame":
            m.command("frame-step")
        elif name == "frame_back":
            m.command("frame-back-step")
        elif name == "next":
            m.command("playlist-next", "weak")
        elif name == "prev":
            m.command("playlist-prev", "weak")
        elif name == "info":
            m.command("script-binding", "stats/display-stats-toggle")
        elif name == "menu":
            self.show_menu()

    def set_volume(self, v):
        self.mpv.volume = float(v)
        self.settings.setValue("volume", v)

    def set_aspect(self, idx):
        self.aspect_idx = idx
        title, asp, pan, keep = ASPECTS[idx]
        self.mpv.video_aspect_override = asp
        self.mpv.panscan = pan
        self.mpv.keepaspect = "yes" if keep else "no"
        self.mpv.show_text(f"Растяжка: {title}")

    def set_hdr(self, idx):
        self.hdr_idx = idx
        self.settings.setValue("hdr_idx", idx)
        self.mpv.target_colorspace_hint = HDR_MODES[idx][1]
        self.mpv.show_text(f"HDR: {HDR_MODES[idx][0]}")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.bar.show()
            self.unsetCursor()
        else:
            self.showFullScreen()
            self.bar.hide()

    def poll_cursor(self):
        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor = pos
            self._idle_ms = 0
            if self.isFullScreen() and self.bar.isHidden():
                self.bar.show()
        else:
            self._idle_ms += 150
            if self.isFullScreen() and self._idle_ms > 2500 and not self.bar.underMouse():
                self.bar.hide()

    # ---------- UI-колбэки ----------
    def on_pos(self, t):
        self.lbl_pos.setText(fmt_time(t))
        if not self.seeking and self.duration > 0:
            self.slider.blockSignals(True)
            self.slider.setValue(int(t / self.duration * 1000))
            self.slider.blockSignals(False)

    def on_dur(self, d):
        self.duration = d
        self.lbl_dur.setText(fmt_time(d))

    def on_seek(self, v):
        if self.duration > 0:
            self.mpv.command("seek", str(v / 1000 * self.duration), "absolute", "exact")

    # ---------- открытие файлов ----------
    def open_files(self, paths):
        paths = [p for p in paths if os.path.exists(p) or "://" in p]
        if not paths:
            return
        self.mpv.command("loadfile", paths[0], "replace")
        for p in paths[1:]:
            self.mpv.command("loadfile", p, "append")
        self.mpv.pause = False

    def dialog_open(self):
        flt = "Видео (" + " ".join("*" + e for e in VIDEO_EXT) + ");;Все файлы (*)"
        files, _ = QFileDialog.getOpenFileNames(self, "Открыть видео", "", flt)
        self.open_files(files)

    def dialog_sub(self):
        flt = "Субтитры (" + " ".join("*" + e for e in SUB_EXT) + ");;Все файлы (*)"
        f, _ = QFileDialog.getOpenFileName(self, "Загрузить субтитры", "", flt)
        if f:
            self.mpv.command("sub-add", f, "select")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        subs = [p for p in paths if p.lower().endswith(SUB_EXT)]
        vids = [p for p in paths if p not in subs]
        if vids:
            self.open_files(vids)
        for s in subs:
            self.mpv.command("sub-add", s, "select")

    # ---------- контекстное меню (ПКМ) ----------
    def show_menu(self):
        menu = QMenu(self)
        menu.addAction("Открыть файл…\tO", lambda: self.do("open"))
        menu.addAction("Загрузить субтитры…\tS", lambda: self.do("sub_open"))
        menu.addSeparator()

        asp = menu.addMenu("Растяжка (A)")
        g = QActionGroup(asp)
        for i, (title, *_r) in enumerate(ASPECTS):
            a = asp.addAction(title)
            a.setCheckable(True)
            a.setChecked(i == self.aspect_idx)
            g.addAction(a)
            a.triggered.connect(lambda _c=False, i=i: self.set_aspect(i))

        hdr = menu.addMenu("HDR / Dolby Vision (H)")
        g2 = QActionGroup(hdr)
        for i, (title, _v) in enumerate(HDR_MODES):
            a = hdr.addAction(title)
            a.setCheckable(True)
            a.setChecked(i == self.hdr_idx)
            g2.addAction(a)
            a.triggered.connect(lambda _c=False, i=i: self.set_hdr(i))

        tracks = self.mpv.track_list or []
        for kind, label, prop in (("sub", "Субтитры (V)", "sid"), ("audio", "Аудиодорожка (B)", "aid")):
            sm = menu.addMenu(label)
            if kind == "sub":
                a = sm.addAction("Выключить")
                a.triggered.connect(lambda: setattr(self.mpv, "sid", "no"))
            cur = getattr(self.mpv, prop)
            for t in (x for x in tracks if x.get("type") == kind):
                name = f'{t["id"]}: {t.get("lang", "?")} {t.get("title", "")}'.strip()
                a = sm.addAction(name)
                a.setCheckable(True)
                a.setChecked(t["id"] == cur)
                a.triggered.connect(lambda _c=False, tid=t["id"], p=prop: setattr(self.mpv, p, tid))

        menu.addSeparator()
        menu.addAction("Статистика (I)", lambda: self.do("info"))
        menu.addAction("Полный экран\tF", lambda: self.do("fullscreen"))
        menu.addAction("Выход", self.close)
        menu.exec(QCursor.pos())

    def closeEvent(self, e):
        self.idle_timer.stop()
        try:
            self.mpv.terminate()
        except Exception:
            pass
        super().closeEvent(e)


def dark_palette(app):
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.Window, QColor("#0f0f10"))
    p.setColor(QPalette.WindowText, QColor("#e8e8ea"))
    p.setColor(QPalette.Base, QColor("#18181a"))
    p.setColor(QPalette.Text, QColor("#e8e8ea"))
    p.setColor(QPalette.Button, QColor("#18181a"))
    p.setColor(QPalette.ButtonText, QColor("#e8e8ea"))
    p.setColor(QPalette.Highlight, QColor("#7c9cff"))
    app.setPalette(p)
    app.setStyleSheet(STYLE)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    dark_palette(app)
    win = Player(sys.argv[1:])
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
