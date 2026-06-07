import socket
import json
import threading
import os
import sys
import base64
import tempfile
import wave
from PySide6 import QtCore, QtWidgets, QtGui, QtMultimedia


def send_json(sock: socket.socket, message: dict) -> bool:
    try:
        data = json.dumps(message).encode()
        sock.sendall(len(data).to_bytes(4, "big"))
        sock.sendall(data)
    except Exception:
        return False
    return True


def recv_json(sock: socket.socket) -> dict | None:
    try:
        length_bytes = sock.recv(4)
        if not length_bytes:
            return None
        length = int.from_bytes(length_bytes, "big")
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode())
    except Exception:
        return None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".aac", ".m4a"}


def get_media_type(file_name: str) -> str:
    ext = os.path.splitext(file_name)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    return "file"


class AppSignals(QtCore.QObject):
    chats_received = QtCore.Signal(list)
    chat_created = QtCore.Signal(str, str, int)
    chat_opened = QtCore.Signal(int, list)
    more_messages = QtCore.Signal(list)
    new_message = QtCore.Signal(str, str, bool, str)
    file_received = QtCore.Signal(str, str, int, str, bool)
    file_download_ready = QtCore.Signal(str, str)
    logged_out = QtCore.Signal()
    server_message = QtCore.Signal(str, str)


class AppState:
    def __init__(self):
        self.sock: socket.socket | None = None
        self.username: str | None = None
        self.current_chat_id: int | None = None
        self.signals = AppSignals()
        self.settings = {
            "font_size": 12,
            "bubble_color_me": "#2e86de",
            "bubble_color_other": "hsl(0,0,30)",
            "send_on_enter": True,
            "show_timestamps": True,
        }


class ChatItem(QtWidgets.QFrame):
    def __init__(self, chat_name: str, last_message: str, chat_id: int):
        super().__init__()
        self.chat_id = chat_id
        self.setFixedHeight(70)
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)

        name_label = QtWidgets.QLabel(chat_name)
        name_font = QtGui.QFont()
        name_font.setPointSize(12)
        name_font.setBold(True)
        name_label.setFont(name_font)

        self.message_label = QtWidgets.QLabel(last_message)
        self.message_label.setFont(QtGui.QFont())
        self.message_label.setStyleSheet("color: hsl(0,0,100); font-weight: 500;")
        self.message_label.setWordWrap(True)

        text_layout = QtWidgets.QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 10, 0)
        text_layout.setSpacing(0)
        text_layout.addWidget(name_label)
        text_layout.addWidget(self.message_label)

        layout.addLayout(text_layout)
        layout.addStretch()

        self.setStyleSheet("""
            QFrame { background-color: hsl(0,0,28); }
            QFrame:hover { background-color: hsl(0,0,35); }
            QLabel { background-color: transparent; color: white; }
        """)


class ImageViewer(QtWidgets.QDialog):
    def __init__(self, pixmap: QtGui.QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image")
        self.setModal(True)
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        max_w, max_h = int(screen.width() * 0.85), int(screen.height() * 0.85)
        scaled = pixmap.scaled(max_w, max_h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.resize(scaled.width() + 20, scaled.height() + 20)
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel()
        label.setPixmap(scaled)
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Escape, QtCore.Qt.Key_Return):
            self.close()
        super().keyPressEvent(event)


class InlineImageWidget(QtWidgets.QLabel):
    def __init__(self, pixmap: QtGui.QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        thumb = pixmap.scaled(320, 240, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.setPixmap(thumb)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip("Click to open")

    def mousePressEvent(self, event):
        ImageViewer(self._pixmap, self).exec()


class InlineVideoWidget(QtWidgets.QWidget):
    def __init__(self, file_path: str, max_width: int = 400, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self.setMaximumWidth(max_width)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        btn = QtWidgets.QPushButton("▶")
        btn.setFixedSize(36, 36)
        btn.setToolTip("Open video in system player")
        btn.setStyleSheet(
            "QPushButton{background:hsl(0,0,45);color:white;border-radius:5px;"
            "font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:hsl(213,100%,50%);}"
        )
        btn.clicked.connect(self._open)
        layout.addWidget(btn)

        name = QtWidgets.QLabel(os.path.basename(file_path))
        name.setStyleSheet("color:white;font-size:11px;")
        name.setWordWrap(True)
        layout.addWidget(name, stretch=1)

    def _open(self):
        import subprocess, platform
        try:
            if platform.system() == "Windows":
                os.startfile(self._file_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", self._file_path])
            else:
                subprocess.Popen(["xdg-open", self._file_path])
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Could not open file:\n{e}")


class InlineAudioWidget(QtWidgets.QWidget):
    def __init__(self, file_path: str, label: str = "Voice message", parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self._is_wav = file_path.lower().endswith(".wav")
        self._sink: QtMultimedia.QAudioSink | None = None
        self._io_device = None
        self._playing = False
        self._wav_data: bytes | None = None
        self._wav_fmt: QtMultimedia.QAudioFormat | None = None

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._play_btn = QtWidgets.QPushButton("▶")
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.setToolTip("Play" if self._is_wav else "Open in system player")
        self._play_btn.setStyleSheet(
            "QPushButton{background:hsl(0,0,45);color:white;border-radius:5px;"
            "font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:hsl(213,100%,50%);}"
        )
        self._play_btn.clicked.connect(self._toggle_play)
        layout.addWidget(self._play_btn)

        lbl = QtWidgets.QLabel(label)
        lbl.setStyleSheet("color:white;font-size:11px;")
        layout.addWidget(lbl, stretch=1)

        if self._is_wav:
            self._load_wav()

    def _load_wav(self):
        try:
            with wave.open(self._file_path, "rb") as wf:
                fmt = QtMultimedia.QAudioFormat()
                fmt.setSampleRate(wf.getframerate())
                fmt.setChannelCount(wf.getnchannels())
                sw = wf.getsampwidth()
                if sw == 1:
                    fmt.setSampleFormat(QtMultimedia.QAudioFormat.UInt8)
                elif sw == 2:
                    fmt.setSampleFormat(QtMultimedia.QAudioFormat.Int16)
                elif sw == 4:
                    fmt.setSampleFormat(QtMultimedia.QAudioFormat.Int32)
                else:
                    raise ValueError(f"Unsupported sample width {sw}")
                self._wav_fmt = fmt
                self._wav_data = wf.readframes(wf.getnframes())
        except Exception:
            self._is_wav = False

    def _toggle_play(self):
        if not self._is_wav:
            self._open_system()
            return
        if self._playing:
            self._stop()
        else:
            self._play()

    def _play(self):
        if self._wav_data is None or self._wav_fmt is None:
            return
        if self._sink:
            self._sink.stop()
            self._sink.deleteLater()
            self._sink = None

        device = QtMultimedia.QMediaDevices.defaultAudioOutput()
        self._sink = QtMultimedia.QAudioSink(device, self._wav_fmt)

        self._io_device = QtCore.QBuffer()
        self._io_device.setData(self._wav_data)
        self._io_device.open(QtCore.QIODevice.ReadOnly)

        self._sink.start(self._io_device)
        self._playing = True
        self._play_btn.setText("■")

        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll_playback)
        self._poll_timer.start()

    def _poll_playback(self):
        if not self._playing:
            self._poll_timer.stop()
            return
        if self._io_device and self._io_device.atEnd():
            QtCore.QTimer.singleShot(200, self._finish_playback)
            self._poll_timer.stop()

    def _finish_playback(self):
        if self._playing:
            self._stop()

    def _stop(self):
        if hasattr(self, "_poll_timer"):
            self._poll_timer.stop()
        if self._sink:
            self._sink.stop()
        if self._io_device:
            self._io_device.close()
            self._io_device = None
        self._playing = False
        self._play_btn.setText("▶")

    def _open_system(self):
        import subprocess, platform
        try:
            if platform.system() == "Windows":
                os.startfile(self._file_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", self._file_path])
            else:
                subprocess.Popen(["xdg-open", self._file_path])
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Could not open file:\n{e}")


class FileMessageWidget(QtWidgets.QFrame):
    def __init__(self, sender: str, file_name: str, message_id: int, sent_at: str,
                 me: bool, state: "AppState", file_data_b64: str | None = None):
        super().__init__()
        self.message_id = message_id
        self._me = me
        self._sender = sender
        self._sent_at = sent_at
        self._file_name = file_name
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        name_label = QtWidgets.QLabel(sender)
        name_label.setStyleSheet("color:white;font-weight:bold;font-size:15px;")
        layout.addWidget(name_label)

        media_type = get_media_type(file_name)

        if file_data_b64 and media_type in ("image", "video", "audio"):
            raw = base64.b64decode(file_data_b64)
            suffix = os.path.splitext(file_name)[1] or ".bin"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(raw)
            tmp.flush()
            tmp.close()

            if media_type == "image":
                pm = QtGui.QPixmap()
                pm.loadFromData(raw)
                layout.addWidget(InlineImageWidget(pm))
            elif media_type == "video":
                mw = self.maximumWidth()
                video_max = (mw - 32) if mw < 16_000_000 else 460
                layout.addWidget(InlineVideoWidget(tmp.name, max_width=video_max))
            elif media_type == "audio":
                layout.addWidget(InlineAudioWidget(tmp.name, file_name))
        else:
            file_label = QtWidgets.QLabel(file_name)
            file_label.setStyleSheet("color:white;")
            file_label.setWordWrap(True)
            layout.addWidget(file_label)

            download_btn = QtWidgets.QPushButton("Download")
            download_btn.setStyleSheet(
                "QPushButton{background:rgba(255,255,255,0.2);color:white;"
                "border-radius:4px;padding:4px 8px;}"
                "QPushButton:hover{background:rgba(255,255,255,0.35);}"
            )
            download_btn.clicked.connect(lambda: send_json(state.sock, {
                "type": "request_download",
                "file_id": message_id,
                "chat_id": state.current_chat_id,
            }))
            layout.addWidget(download_btn)

        if state.settings.get("show_timestamps", True) and sent_at:
            time_label = QtWidgets.QLabel(sent_at)
            time_label.setStyleSheet(
                "color:rgba(255,255,255,0.6);font-weight:300;font-size:10px;"
            )
            layout.addWidget(time_label)

        bg = state.settings["bubble_color_me"] if me else state.settings["bubble_color_other"]
        self.setStyleSheet(
            f"QFrame{{background-color:{bg};border-radius:8px;margin:2px;}}"
        )


class PasswordChangeWindow(QtWidgets.QWidget):
    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self.setWindowTitle("Change Password")
        self.setFixedSize(300, 200)
        self.setStyleSheet("""
            QWidget{background-color:hsl(0,0,22);color:white;font-size:12pt;}
            QLineEdit{background-color:hsl(0,0,32);border-radius:5px;padding:5px;color:white;}
            QPushButton{background-color:hsl(213,100%,50%);border-radius:5px;padding:8px;font-weight:bold;}
            QPushButton:hover{background-color:hsl(213,100%,60%);}
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.old_pass = QtWidgets.QLineEdit()
        self.old_pass.setPlaceholderText("Old Password")
        self.old_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.old_pass)

        self.new_pass = QtWidgets.QLineEdit()
        self.new_pass.setPlaceholderText("New Password")
        self.new_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.new_pass)

        btn = QtWidgets.QPushButton("Confirm")
        btn.clicked.connect(self._confirm)
        layout.addWidget(btn)

    def _confirm(self):
        old = self.old_pass.text().strip()
        new = self.new_pass.text().strip()
        if not old or not new:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in both fields.")
            return
        send_json(self.state.sock, {
            "type": "change_password",
            "username": self.state.username,
            "old_password": old,
            "new_password": new,
        })
        self.close()


class SettingsWindow(QtWidgets.QDialog):
    settings_changed = QtCore.Signal()

    def __init__(self, state: "AppState", parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Settings")
        self.setFixedSize(400, 560)
        self.setStyleSheet("""
            QDialog{background-color:hsl(0,0,22);color:white;}
            QLabel{color:white;font-size:11pt;}
            QGroupBox{color:#aaa;font-size:10pt;border:1px solid hsl(0,0,35);
                      border-radius:6px;margin-top:10px;padding:10px 8px 8px 8px;}
            QGroupBox::title{subcontrol-origin:margin;subcontrol-position:top left;
                             padding:0 4px;left:10px;}
            QCheckBox{color:white;spacing:8px;}
            QLineEdit{background:hsl(0,0,35);color:white;border-radius:4px;padding:5px;}
            QPushButton{background-color:hsl(213,100%,50%);color:white;border-radius:5px;
                        padding:7px 14px;font-weight:bold;}
            QPushButton:hover{background-color:hsl(213,100%,60%);}
            QPushButton#cancel{background-color:hsl(0,0,40);}
            QPushButton#cancel:hover{background-color:hsl(0,0,50);}
            QPushButton#pw_btn{background-color:hsl(0,0,40);}
            QPushButton#pw_btn:hover{background-color:hsl(0,0,50);}
        """)

        s = state.settings
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        app_group = QtWidgets.QGroupBox("Appearance")
        ag = QtWidgets.QFormLayout(app_group)

        self._font_val = s["font_size"]
        spin_row = QtWidgets.QHBoxLayout()
        self._font_display = QtWidgets.QLineEdit(str(self._font_val))
        self._font_display.setReadOnly(True)
        self._font_display.setFixedWidth(38)
        self._font_display.setAlignment(QtCore.Qt.AlignCenter)
        self._font_display.setStyleSheet(
            "background:hsl(0,0,35);color:white;border:none;border-radius:0;padding:3px;"
        )
        _btn = ("QPushButton{background:hsl(0,0,45);color:white;border-radius:3px;"
                "min-width:24px;min-height:24px;font-size:10pt;padding:0;}"
                "QPushButton:hover{background:hsl(0,0,58);color:white;}")
        dn = QtWidgets.QPushButton("▼")
        dn.setFixedSize(24, 24)
        dn.setStyleSheet(_btn)
        dn.clicked.connect(lambda: self._step(-1))
        up = QtWidgets.QPushButton("▲")
        up.setFixedSize(24, 24)
        up.setStyleSheet(_btn)
        up.clicked.connect(lambda: self._step(1))
        spin_row.addWidget(self._font_display)
        spin_row.addSpacing(4)
        spin_row.addWidget(dn)
        spin_row.addWidget(up)
        spin_row.addStretch()
        w = QtWidgets.QWidget()
        w.setStyleSheet("background:transparent;")
        w.setLayout(spin_row)
        ag.addRow("Font size (pt):", w)

        self._color_me = QtGui.QColor(s["bubble_color_me"])
        self._btn_me = QtWidgets.QPushButton()
        self._btn_me.setStyleSheet(f"background:{s['bubble_color_me']};min-width:80px;min-height:24px;border-radius:4px;border:1px solid hsl(0,0,50);")
        self._btn_me.setText(self._color_me.name())
        self._btn_me.clicked.connect(lambda: self._pick("me"))
        ag.addRow("My message colour:", self._btn_me)

        self._color_other = QtGui.QColor(s["bubble_color_other"])
        self._btn_other = QtWidgets.QPushButton()
        self._btn_other.setStyleSheet(f"background:hsl(0,0,30);min-width:80px;min-height:24px;border-radius:4px;border:1px solid hsl(0,0,50);")
        self._btn_other.setText(self._color_other.name())
        self._btn_other.clicked.connect(lambda: self._pick("other"))
        ag.addRow("Their message colour:", self._btn_other)

        root.addWidget(app_group)

        beh_group = QtWidgets.QGroupBox("Behaviour")
        bl = QtWidgets.QVBoxLayout(beh_group)
        self._enter_check = QtWidgets.QCheckBox("Send message on Enter")
        self._enter_check.setChecked(s["send_on_enter"])
        bl.addWidget(self._enter_check)
        self._ts_check = QtWidgets.QCheckBox("Show timestamps on messages")
        self._ts_check.setChecked(s["show_timestamps"])
        bl.addWidget(self._ts_check)
        root.addWidget(beh_group)

        note = QtWidgets.QLabel("⚠  Some settings only apply after restarting.")
        note.setStyleSheet("color:hsl(45,100%,65%);font-size:9pt;font-style:italic;")
        note.setWordWrap(True)
        root.addWidget(note)

        pw_group = QtWidgets.QGroupBox("Change Password")
        pg = QtWidgets.QVBoxLayout(pw_group)
        self._old_pw = QtWidgets.QLineEdit()
        self._old_pw.setPlaceholderText("Current password")
        self._old_pw.setEchoMode(QtWidgets.QLineEdit.Password)
        pg.addWidget(self._old_pw)
        self._new_pw = QtWidgets.QLineEdit()
        self._new_pw.setPlaceholderText("New password")
        self._new_pw.setEchoMode(QtWidgets.QLineEdit.Password)
        pg.addWidget(self._new_pw)
        pw_btn = QtWidgets.QPushButton("Change Password")
        pw_btn.setObjectName("pw_btn")
        pw_btn.clicked.connect(self._change_password)
        pg.addWidget(pw_btn)
        root.addWidget(pw_group)

        root.addStretch()

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.setObjectName("cancel")
        cancel.clicked.connect(self.reject)
        save = QtWidgets.QPushButton("Save")
        save.clicked.connect(self._save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        root.addLayout(btn_row)

    def _step(self, d: int):
        self._font_val = max(8, min(24, self._font_val + d))
        self._font_display.setText(str(self._font_val))

    def _pick(self, target: str):
        init = self._color_me if target == "me" else self._color_other
        c = QtWidgets.QColorDialog.getColor(init, self)
        if not c.isValid():
            return
        if target == "me":
            self._color_me = c
            self._btn_me.setStyleSheet(f"background:{c.name()};min-width:80px;min-height:24px;border-radius:4px;border:1px solid hsl(0,0,50);")
            self._btn_me.setText(c.name())
        else:
            self._color_other = c
            self._btn_other.setStyleSheet(f"background:{c.name()};min-width:80px;min-height:24px;border-radius:4px;border:1px solid hsl(0,0,50);")
            self._btn_other.setText(c.name())

    def _save(self):
        s = self.state.settings
        s["font_size"] = self._font_val
        s["bubble_color_me"] = self._color_me.name()
        s["bubble_color_other"] = self._color_other.name()
        s["send_on_enter"] = self._enter_check.isChecked()
        s["show_timestamps"] = self._ts_check.isChecked()
        self.settings_changed.emit()
        self.accept()

    def _change_password(self):
        old = self._old_pw.text().strip()
        new = self._new_pw.text().strip()
        if not old or not new:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in both password fields.")
            return
        send_json(self.state.sock, {
            "type": "change_password",
            "username": self.state.username,
            "old_password": old,
            "new_password": new,
        })
        self._old_pw.clear()
        self._new_pw.clear()


class VoiceRecorder(QtWidgets.QWidget):
    recording_ready = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedSize(240, 64)

        self._frames: list = []
        self._recording = False
        self._thread: threading.Thread | None = None
        self._tmp_path: str | None = None
        self._sd = None
        self._samplerate = 44100
        self._channels = 1

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._rec_btn = QtWidgets.QPushButton("🎙 Record")
        self._rec_btn.setFixedHeight(44)
        self._rec_btn.setStyleSheet(self._css_idle())
        self._rec_btn.clicked.connect(self._toggle)
        layout.addWidget(self._rec_btn)

        self._send_btn = QtWidgets.QPushButton("Send")
        self._send_btn.setFixedHeight(44)
        self._send_btn.setEnabled(False)
        self._send_btn.setStyleSheet(
            "QPushButton{background:hsl(213,100%,50%);color:white;border-radius:6px;"
            "font-weight:bold;font-size:12px;padding:0 10px;}"
            "QPushButton:disabled{background:hsl(0,0,40);color:hsl(0,0,60);}"
            "QPushButton:hover:!disabled{background:hsl(213,100%,60%);}"
        )
        self._send_btn.clicked.connect(self._send)
        layout.addWidget(self._send_btn)

        self.setStyleSheet("background:hsl(0,0,25);border-radius:10px;")

    def _css_idle(self):
        return ("QPushButton{background:#e74c3c;color:white;border-radius:6px;"
                "font-weight:bold;font-size:12px;padding:0 10px;}"
                "QPushButton:hover{background:#c0392b;color:white;}")

    def _css_rec(self):
        return ("QPushButton{background:#e67e22;color:white;border-radius:6px;"
                "font-weight:bold;font-size:12px;padding:0 10px;}"
                "QPushButton:hover{background:#d35400;color:white;}")

    def _get_sd(self):
        if self._sd is None:
            try:
                import sounddevice as sd
                self._sd = sd
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    None, "Missing dependency",
                    f"sounddevice is not installed.\nRun: pip install sounddevice\n\n{e}"
                )
                return None
        return self._sd

    def _toggle(self):
        if not self._recording:
            self._start()
        else:
            self._stop()

    def _start(self):
        sd = self._get_sd()
        if sd is None:
            return
        self._frames = []
        self._recording = True
        self._send_btn.setEnabled(False)
        self._rec_btn.setText("⏹ Stop")
        self._rec_btn.setStyleSheet(self._css_rec())

        def _record():
            try:
                with sd.InputStream(samplerate=self._samplerate,
                                    channels=self._channels,
                                    dtype="int16") as stream:
                    while self._recording:
                        chunk, _ = stream.read(1024)
                        self._frames.append(bytes(chunk))
            except Exception as e:
                QtCore.QMetaObject.invokeMethod(
                    self, "_recording_error",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(str, str(e))
                )

        self._thread = threading.Thread(target=_record, daemon=True)
        self._thread.start()

    def _stop(self):
        self._recording = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._rec_btn.setText("🎙 Record")
        self._rec_btn.setStyleSheet(self._css_idle())
        self._finalize()

    def _finalize(self):
        if not self._frames:
            QtWidgets.QMessageBox.warning(
                None, "Recording empty", "No audio was recorded. Check your microphone."
            )
            return
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp.close()
        self._tmp_path = tmp.name
        try:
            with wave.open(self._tmp_path, "wb") as wf:
                wf.setnchannels(self._channels)
                wf.setsampwidth(2)
                wf.setframerate(self._samplerate)
                wf.writeframes(b"".join(self._frames))
            self._send_btn.setEnabled(True)
        except Exception as e:
            QtWidgets.QMessageBox.warning(None, "Recording error", str(e))

    @QtCore.Slot(str)
    def _recording_error(self, msg: str):
        self._recording = False
        self._rec_btn.setText("🎙 Record")
        self._rec_btn.setStyleSheet(self._css_idle())
        QtWidgets.QMessageBox.warning(None, "Recording error", msg)

    def _send(self):
        if self._tmp_path and os.path.exists(self._tmp_path):
            self.recording_ready.emit(self._tmp_path)
        self.hide()
        self._send_btn.setEnabled(False)
        self._frames = []
        self._tmp_path = None


class ChatPanel(QtWidgets.QWidget):
    load_more_requested = QtCore.Signal(int, int)

    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self._voice_recorder: VoiceRecorder | None = None
        self._pending_media: dict[int, FileMessageWidget] = {}
        self._msg_offset = 0
        self._loading_more = False
        self._has_more = True

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self._messages_container = QtWidgets.QWidget()
        self.messages_layout = QtWidgets.QVBoxLayout(self._messages_container)
        self.messages_layout.setAlignment(QtCore.Qt.AlignTop)
        self.messages_layout.addStretch()
        self.scroll_area.setWidget(self._messages_container)
        main_layout.addWidget(self.scroll_area)

        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

        input_container = QtWidgets.QWidget()
        input_container.setStyleSheet("background-color:hsl(0,0,28);")
        il = QtWidgets.QHBoxLayout(input_container)
        il.setContentsMargins(8, 8, 8, 8)
        il.setSpacing(6)

        self.message_input = QtWidgets.QLineEdit()
        self.message_input.setFixedHeight(36)
        self.message_input.setPlaceholderText("Type a message...")
        self.message_input.returnPressed.connect(self._on_send)

        send_btn = QtWidgets.QPushButton("Send")
        send_btn.setStyleSheet(
            "QPushButton{background:hsl(213,100%,50%);color:white;border-radius:5px;"
            "padding:6px 14px;font-weight:bold;}"
            "QPushButton:hover{background:hsl(213,100%,60%);}"
        )
        send_btn.clicked.connect(self._on_send)

        file_btn = QtWidgets.QPushButton("🗎")
        file_btn.setFixedSize(36, 36)
        file_btn.setStyleSheet(
            "QPushButton{background:hsl(0,0,45);color:white;border-radius:5px;font-size:14pt;}"
            "QPushButton:hover{background:hsl(0,0,55);}"
        )
        file_btn.clicked.connect(self._on_send_file)

        voice_btn = QtWidgets.QPushButton("🎙")
        voice_btn.setFixedSize(36, 36)
        voice_btn.setToolTip("Send voice message")
        voice_btn.setStyleSheet(
            "QPushButton{background:hsl(0,0,45);color:white;border-radius:5px;font-size:14pt;}"
            "QPushButton:hover{background:hsl(348,83%,47%);}"
        )
        voice_btn.clicked.connect(self._on_voice)

        il.addWidget(self.message_input)
        il.addWidget(file_btn)
        il.addWidget(voice_btn)
        il.addWidget(send_btn)
        main_layout.addWidget(input_container)

    def open_chat(self, chat_id: int):
        self.state.current_chat_id = chat_id
        self._pending_media = {}
        self._msg_offset = 0
        self._loading_more = False
        self._has_more = True
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def prepend_messages(self, msgs: list):
        self._loading_more = False
        if len(msgs) < 50:
            self._has_more = False

        sb = self.scroll_area.verticalScrollBar()
        old_max = sb.maximum()

        for i, m in enumerate(msgs):
            me = m["sender"] == self.state.username
            widget = self._make_message_widget(m, me)
            if widget:
                self.messages_layout.insertWidget(i, widget)

        QtCore.QTimer.singleShot(0, lambda: sb.setValue(
            sb.value() + (sb.maximum() - old_max)
        ))

    def add_message(self, sender: str, content: str, me: bool = False, sent_at: str = ""):
        s = self.state.settings
        color = s["bubble_color_me"] if me else s["bubble_color_other"]
        ts_html = ""
        if s.get("show_timestamps", True) and sent_at:
            ts_html = (
                f'<br><span style="color:rgba(255,255,255,0.55);'
                f'font-size:{max(8, s["font_size"] - 2)}pt;">{sent_at}</span>'
            )
        bubble = QtWidgets.QLabel(f"<b>{sender}</b><br>{content}{ts_html}")
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(min(500, int(self.width() * 0.65)))
        bubble.setTextFormat(QtCore.Qt.RichText)
        bubble.setStyleSheet(
            f"padding:8px;border-radius:8px;margin:2px;"
            f"background-color:{color};color:white;font-size:{s['font_size']}pt;"
        )
        self._insert_row(bubble, me)

    def add_file_message(self, sender: str, file_name: str, message_id: int,
                         sent_at: str, me: bool = False, file_data_b64: str | None = None):
        widget = FileMessageWidget(
            sender, file_name, message_id, sent_at, me, self.state, file_data_b64
        )
        widget.setMaximumWidth(min(500, int(self.width() * 0.65)))
        self._insert_row(widget, me)

        if file_data_b64 is None and get_media_type(file_name) in ("image", "video", "audio"):
            self._pending_media[message_id] = widget
            send_json(self.state.sock, {
                "type": "request_download",
                "file_id": message_id,
                "chat_id": self.state.current_chat_id,
            })

    def resolve_media_widget(self, message_id: int, file_name: str, file_data_b64: str):
        placeholder = self._pending_media.pop(message_id, None)
        if placeholder is None:
            return
        new_widget = FileMessageWidget(
            placeholder._sender, file_name, message_id,
            placeholder._sent_at, placeholder._me, self.state, file_data_b64
        )
        new_widget.setMaximumWidth(placeholder.maximumWidth())
        container = placeholder.parent()
        if container is not None:
            row = container.layout()
            for i in range(row.count()):
                item = row.itemAt(i)
                if item and item.widget() is placeholder:
                    row.removeWidget(placeholder)
                    placeholder.setParent(None)
                    row.insertWidget(i, new_widget)
                    break

    def _apply_settings(self):
        try:
            self.message_input.returnPressed.disconnect()
        except RuntimeError:
            pass
        if self.state.settings.get("send_on_enter", True):
            self.message_input.returnPressed.connect(self._on_send)

    def _make_message_widget(self, m: dict, me: bool) -> QtWidgets.QWidget | None:
        if m.get("file_name"):
            w = FileMessageWidget(
                m["sender"], m["file_name"], m["message_id"],
                m.get("sent_at", ""), me, self.state
            )
            w.setMaximumWidth(min(500, int(self.width() * 0.65)))
            if get_media_type(m["file_name"]) in ("image", "video", "audio"):
                self._pending_media[m["message_id"]] = w
                send_json(self.state.sock, {
                    "type": "request_download",
                    "file_id": m["message_id"],
                    "chat_id": self.state.current_chat_id,
                })
            return self._wrap_row(w, me)
        else:
            s = self.state.settings
            color = s["bubble_color_me"] if me else s["bubble_color_other"]
            sent_at = m.get("sent_at", "")
            ts_html = ""
            if s.get("show_timestamps", True) and sent_at:
                ts_html = (
                    f'<br><span style="color:rgba(255,255,255,0.55);'
                    f'font-size:{max(8, s["font_size"]-2)}pt;">{sent_at}</span>'
                )
            bubble = QtWidgets.QLabel(f"<b>{m['sender']}</b><br>{m.get('content','')}{ts_html}")
            bubble.setWordWrap(True)
            bubble.setMaximumWidth(min(500, int(self.width() * 0.65)))
            bubble.setTextFormat(QtCore.Qt.RichText)
            bubble.setStyleSheet(
                f"padding:8px;border-radius:8px;margin:2px;"
                f"background-color:{color};color:white;font-size:{s['font_size']}pt;"
            )
            return self._wrap_row(bubble, me)

    def _wrap_row(self, widget: QtWidgets.QWidget, me: bool) -> QtWidgets.QWidget:
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(4, 2, 4, 2)
        if me:
            row.addStretch()
            row.addWidget(widget)
        else:
            row.addWidget(widget)
            row.addStretch()
        container = QtWidgets.QWidget()
        container.setLayout(row)
        container.setStyleSheet("background:transparent;")
        return container

    def _insert_row(self, widget: QtWidgets.QWidget, me: bool):
        container = self._wrap_row(widget, me)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, container)
        QtCore.QTimer.singleShot(
            50, lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            )
        )

    def _on_scroll(self, value: int):
        if value == 0 and self._has_more and not self._loading_more:
            cid = self.state.current_chat_id
            if cid is not None:
                self._loading_more = True
                self._msg_offset += 50
                self.load_more_requested.emit(cid, self._msg_offset)

    def _on_send(self):
        text = self.message_input.text().strip()
        if text and self.state.current_chat_id is not None:
            send_json(self.state.sock, {
                "type": "msg",
                "chat_id": self.state.current_chat_id,
                "sender": self.state.username,
                "content": text,
            })
            self.message_input.clear()

    def _on_send_file(self):
        if self.state.current_chat_id is None:
            QtWidgets.QMessageBox.warning(self, "Error", "Open a chat first")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self._send_file_path(path)

    def _send_file_path(self, file_path: str):
        file_name = os.path.basename(file_path) or "voice.wav"
        try:
            with open(file_path, "rb") as f:
                file_data = base64.b64encode(f.read()).decode()
            if not file_data:
                raise ValueError("File is empty")
            send_json(self.state.sock, {
                "type": "send_file",
                "chat_id": self.state.current_chat_id,
                "file_name": file_name,
                "file_data": file_data,
            })
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to send file: {e}")

    def _on_voice(self):
        if self.state.current_chat_id is None:
            QtWidgets.QMessageBox.warning(self, "Error", "Open a chat first")
            return
        if self._voice_recorder is None:
            self._voice_recorder = VoiceRecorder()
            self._voice_recorder.recording_ready.connect(self._send_file_path)

        if self._voice_recorder.isVisible():
            self._voice_recorder.hide()
        else:
            gp = self.mapToGlobal(self.rect().bottomLeft())
            self._voice_recorder.move(gp.x() + 8, gp.y() - self._voice_recorder.height() - 70)
            self._voice_recorder.show()
            self._voice_recorder.raise_()


class NewChatWindow(QtWidgets.QWidget):
    def __init__(self, all_users: list, state: "AppState"):
        super().__init__()
        self.state = state
        self.all_users = all_users
        self.setWindowTitle("Create New Chat")
        self.setFixedSize(400, 500)
        self.setStyleSheet("""
            QWidget{background-color:hsl(0,0,22);color:white;font-size:12pt;}
            QLineEdit{background-color:hsl(0,0,32);border-radius:5px;padding:5px;color:white;}
            QPushButton{background-color:hsl(213,100%,50%);border-radius:5px;padding:8px;font-weight:bold;}
            QPushButton:hover{background-color:hsl(213,100%,60%);}
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("Chat Name")
        layout.addWidget(self.name_input)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search users...")
        self.search_input.textChanged.connect(self._refresh)
        layout.addWidget(self.search_input)

        self.list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.list_widget)
        self._refresh()

        create_btn = QtWidgets.QPushButton("Create Chat")
        create_btn.clicked.connect(self._create)
        layout.addWidget(create_btn)

    def _refresh(self):
        q = self.search_input.text().lower()
        self.list_widget.clear()
        for u in self.all_users:
            if u.lower() == self.state.username.lower():
                continue
            if q in u.lower():
                item = QtWidgets.QListWidgetItem(u)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.Unchecked)
                self.list_widget.addItem(item)

    def _create(self):
        name = self.name_input.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Error", "Please enter a chat name")
            return
        users = [
            self.list_widget.item(i).text()
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == QtCore.Qt.Checked
        ]
        if not users:
            QtWidgets.QMessageBox.warning(self, "Error", "Select at least one user")
            return
        users.append(self.state.username)
        send_json(self.state.sock, {
            "type": "create_chat",
            "creator": self.state.username,
            "users": users,
            "name": name,
        })
        self.close()


class LeftPanel(QtWidgets.QWidget):
    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self.setStyleSheet("background-color:hsl(0,0,22);")
        self.setFixedWidth(300)

        ml = QtWidgets.QVBoxLayout(self)
        ml.setContentsMargins(10, 10, 10, 10)
        ml.setSpacing(10)

        add_btn = QtWidgets.QPushButton("＋ New Chat")
        add_btn.setFixedSize(140, 40)
        add_btn.setStyleSheet(
            "QPushButton{background:hsl(213,100%,50%);color:white;font-weight:bold;"
            "font-size:12pt;border-radius:6px;}"
            "QPushButton:hover{background:hsl(213,100%,60%);}"
        )
        add_btn.clicked.connect(self._new_chat)
        tr = QtWidgets.QHBoxLayout()
        tr.addStretch()
        tr.addWidget(add_btn)
        ml.addLayout(tr)

        self._chats_container = QtWidgets.QWidget()
        self._chats_layout = QtWidgets.QVBoxLayout(self._chats_container)
        self._chats_layout.setContentsMargins(0, 0, 0, 0)
        self._chats_layout.setSpacing(5)
        self._chats_layout.addStretch()

        sa = QtWidgets.QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        sa.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        sa.setStyleSheet("border:none;")
        sa.setWidget(self._chats_container)
        ml.addWidget(sa)

        bottom = QtWidgets.QFrame()
        bottom.setFixedHeight(60)
        bottom.setStyleSheet("background-color:hsl(0,0,18);")
        bl = QtWidgets.QHBoxLayout(bottom)
        bl.setContentsMargins(10, 5, 10, 5)

        self.username_label = QtWidgets.QLabel(state.username or "")
        self.username_label.setStyleSheet(
            "font-weight:bold;font-size:12pt;padding-left:8px;color:white;"
        )
        self.username_label.setMaximumWidth(180)
        self.username_label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        bl.addWidget(self.username_label)
        bl.addStretch()

        menu_btn = QtWidgets.QPushButton("☰")
        menu_btn.setFixedSize(36, 36)
        menu_btn.setStyleSheet(
            "QPushButton{background:transparent;color:white;font-size:18pt;border-radius:5px;}"
            "QPushButton:hover{background:hsl(0,0,32);}"
        )
        menu_btn.clicked.connect(self._menu)
        self._menu_btn = menu_btn
        bl.addWidget(menu_btn)
        ml.addWidget(bottom)

    def _menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu{background:hsl(0,0,22);color:white;border:1px solid hsl(0,0,35);
                  padding:4px;border-radius:6px;}
            QMenu::item{padding:8px 20px;border-radius:4px;}
            QMenu::item:selected{background:hsl(213,100%,50%);}
            QMenu::separator{height:1px;background:hsl(0,0,35);margin:4px 8px;}
        """)
        a_settings = menu.addAction("Settings")
        menu.addSeparator()
        a_logout = menu.addAction("Logout")

        act = menu.exec(self._menu_btn.mapToGlobal(QtCore.QPoint(0, -menu.sizeHint().height())))
        if act == a_settings:
            dlg = SettingsWindow(self.state, self)
            mw = self.window()
            if hasattr(mw, "chat_panel"):
                dlg.settings_changed.connect(mw.chat_panel._apply_settings)
            dlg.exec()
        elif act == a_logout:
            send_json(self.state.sock, {"type": "logout", "username": self.state.username})
            self.state.signals.logged_out.emit()

    def add_chat(self, chat_name: str, last_message: str, chat_id: int, on_click):
        if not last_message:
            last_message = "Start the conversation"
        if len(last_message) > 45:
            last_message = last_message[:42] + "..."
        item = ChatItem(chat_name, last_message, chat_id)
        item.mousePressEvent = lambda e, cid=chat_id: on_click(cid)
        self._chats_layout.insertWidget(self._chats_layout.count() - 1, item)

    def update_last_message(self, chat_id: int, content: str):
        for i in range(self._chats_layout.count()):
            w = self._chats_layout.itemAt(i).widget()
            if isinstance(w, ChatItem) and w.chat_id == chat_id:
                t = content if len(content) <= 45 else content[:42] + "..."
                w.message_label.setText(t)
                break

    def update_chats(self, chats: list, on_click):
        for c in chats:
            self.add_chat(c.get("name"), c.get("last_message", ""), c.get("id"), on_click)

    def _new_chat(self):
        if hasattr(self, "_ncw") and self._ncw.isVisible():
            self._ncw.raise_()
            return
        self._ncw = NewChatWindow([], self.state)
        self._ncw.show()
        send_json(self.state.sock, {"type": "get_users"})

    def update_new_chat_users(self, users: list):
        if hasattr(self, "_ncw") and self._ncw.isVisible():
            self._ncw.all_users = users
            self._ncw._refresh()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self.setMinimumSize(700, 800)
        self.setWindowTitle("Chat App")

        central = QtWidgets.QWidget()
        central.setStyleSheet("background-color:hsl(0,0,18);")
        self.setCentralWidget(central)

        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.left_panel = LeftPanel(state)
        layout.addWidget(self.left_panel)

        sep = QtWidgets.QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet("background:hsl(0,0,32);")
        layout.addWidget(sep)

        self.chat_panel = ChatPanel(state)
        layout.addWidget(self.chat_panel)

    def open_chat(self, chat_id: int):
        self.chat_panel.open_chat(chat_id)
        send_json(self.state.sock, {
            "type": "open_chat",
            "chat_id": chat_id,
            "offset": 0,
        })


class LoginWindow(QtWidgets.QWidget):
    login_success = QtCore.Signal(str)
    login_error   = QtCore.Signal(str)

    def __init__(self, state: "AppState"):
        super().__init__()
        self.state = state
        self.setFixedSize(400, 300)
        self.setWindowTitle("Login")
        self.setStyleSheet("""
            QWidget{background-color:hsl(0,0,22);color:white;font-size:12pt;}
            QLineEdit{background-color:hsl(0,0,32);border-radius:5px;padding:5px;color:white;}
            QPushButton{background-color:hsl(213,100%,50%);border-radius:5px;padding:8px;font-weight:bold;}
            QPushButton:hover{background-color:hsl(213,100%,60%);}
            QLabel{color:white;font-size:24pt;}
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QtWidgets.QLabel("Chat App")
        title.setAlignment(QtCore.Qt.AlignCenter)
        f = QtGui.QFont()
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        self.username_input = QtWidgets.QLineEdit()
        self.username_input.setPlaceholderText("Username")
        layout.addWidget(self.username_input)

        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.password_input)

        login_btn = QtWidgets.QPushButton("Login")
        login_btn.clicked.connect(lambda: self._submit("login"))
        layout.addWidget(login_btn)

        reg_btn = QtWidgets.QPushButton("Register")
        reg_btn.setStyleSheet(
            "QPushButton{background:hsl(0,0,35);color:white;border-radius:5px;padding:8px;font-weight:bold;}"
            "QPushButton:hover{background:hsl(0,0,45);}"
        )
        reg_btn.clicked.connect(lambda: self._submit("register"))
        layout.addWidget(reg_btn)

    def _submit(self, kind: str):
        u = self.username_input.text().strip()
        p = self.password_input.text().strip()
        if not u or not p:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in all inputs")
            return
        self.state.username = u
        send_json(self.state.sock, {"type": kind, "username": u, "password": p})


class ConnectWindow(QtWidgets.QWidget):
    connected = QtCore.Signal(socket.socket)

    def __init__(self):
        super().__init__()
        self.setFixedSize(400, 300)
        self.setWindowTitle("Connect to Server")
        self.setStyleSheet("""
            QWidget{background-color:hsl(0,0,22);color:white;font-size:12pt;}
            QLineEdit{background-color:hsl(0,0,32);border-radius:5px;padding:5px;color:white;}
            QPushButton{background-color:hsl(213,100%,50%);border-radius:5px;padding:8px;font-weight:bold;}
            QPushButton:hover{background-color:hsl(213,100%,60%);}
            QLabel{color:white;font-size:24pt;}
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        title = QtWidgets.QLabel("Connect to Server")
        title.setAlignment(QtCore.Qt.AlignCenter)
        f = QtGui.QFont()
        f.setBold(True)
        f.setPointSize(20)
        title.setFont(f)
        layout.addWidget(title)

        self.ip_input = QtWidgets.QLineEdit()
        self.ip_input.setPlaceholderText("Server IP")
        layout.addWidget(self.ip_input)

        self.port_input = QtWidgets.QLineEdit()
        self.port_input.setPlaceholderText("Port")
        layout.addWidget(self.port_input)

        btn = QtWidgets.QPushButton("Connect")
        btn.clicked.connect(self._connect)
        layout.addWidget(btn)

    def _connect(self):
        ip = self.ip_input.text().strip()
        port_text = self.port_input.text().strip()
        if not ip or not port_text:
            QtWidgets.QMessageBox.warning(self, "Error", "Please fill in all inputs")
            return
        try:
            port = int(port_text)
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Error", "Port must be a number")
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((ip, port))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Error connecting: {e}")
            sock.close()
            return
        self.connected.emit(sock)
        self.close()


class App:
    def __init__(self):
        self.state = AppState()
        self.qt_app = QtWidgets.QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.connect_window: ConnectWindow | None = None
        self.login_window: LoginWindow | None = None
        self.main_window: MainWindow | None = None

        self.state.signals.logged_out.connect(self._do_logout)
        self.connect_window = ConnectWindow()
        self.connect_window.connected.connect(self._start_login)
        self.connect_window.show()

    def run(self) -> int:
        return self.qt_app.exec()

    def _start_login(self, sock: socket.socket):
        self.state.sock = sock
        threading.Thread(target=self._listener, daemon=True).start()
        self.login_window = LoginWindow(self.state)
        self.login_window.login_success.connect(self._on_login_success)
        self.login_window.login_error.connect(
            lambda err: QtWidgets.QMessageBox.warning(self.login_window, "Login Failed", err)
        )
        self.login_window.show()

    def _on_login_success(self, username: str):
        self.state.username = username
        self.main_window = MainWindow(self.state)
        self.main_window.left_panel.username_label.setText(username)
        self.main_window.show()
        self.login_window.close()

        sig = self.state.signals
        cp  = self.main_window.chat_panel
        lp  = self.main_window.left_panel

        sig.chats_received.connect(lambda c: lp.update_chats(c, self.main_window.open_chat))
        sig.chat_created.connect(lambda n, l, cid: lp.add_chat(n, l, cid, self.main_window.open_chat))
        sig.chat_opened.connect(self._on_chat_opened)
        sig.more_messages.connect(cp.prepend_messages)
        sig.new_message.connect(lambda s, c, me, sat: cp.add_message(s, c, me, sat))
        sig.new_message.connect(lambda s, c, me, sat: lp.update_last_message(self.state.current_chat_id, c))
        sig.file_received.connect(lambda s, fn, mid, sat, me: cp.add_file_message(s, fn, mid, sat, me))
        sig.file_download_ready.connect(self._handle_download)
        sig.server_message.connect(lambda lvl, txt: QtWidgets.QMessageBox.warning(
            self.main_window, "Success" if lvl == "info" else "Error", txt
        ))

        cp.load_more_requested.connect(self._load_more)
        send_json(self.state.sock, {"type": "get_chats", "user": username})

    def _load_more(self, chat_id: int, offset: int):
        send_json(self.state.sock, {
            "type": "open_chat",
            "chat_id": chat_id,
            "offset": offset,
        })

    def _on_chat_opened(self, chat_id: int, msgs: list):
        self.main_window.chat_panel.open_chat(chat_id)
        for m in msgs:
            me = m["sender"] == self.state.username
            if m.get("file_name"):
                self.main_window.chat_panel.add_file_message(
                    m["sender"], m["file_name"], m["message_id"], m.get("sent_at", ""), me
                )
            else:
                self.main_window.chat_panel.add_message(
                    m["sender"], m["content"] or "", me, m.get("sent_at", "")
                )

    def _handle_download(self, file_name: str, file_data: str):
        cp = self.main_window.chat_panel if self.main_window else None
        pending = getattr(cp, "_pending_media", {}) if cp else {}

        matched_id = next(
            (mid for mid, w in list(pending.items()) if w._file_name == file_name),
            None
        )
        if matched_id is not None and cp:
            cp.resolve_media_widget(matched_id, file_name, file_data)
            return

        media_type = get_media_type(file_name)
        raw = base64.b64decode(file_data)

        if media_type == "image":
            pm = QtGui.QPixmap()
            pm.loadFromData(raw)
            viewer = ImageViewer(pm)
            bar = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Close
            )
            bar.rejected.connect(viewer.close)
            bar.accepted.connect(lambda: self._save_raw(file_name, raw))
            viewer.layout().addWidget(bar)
            viewer.exec()
            return

        if media_type in ("video", "audio"):
            suffix = os.path.splitext(file_name)[1]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(raw)
            tmp.flush()
            tmp.close()
            dlg = QtWidgets.QDialog()
            dlg.setWindowTitle(file_name)
            dlg.resize(400, 300 if media_type == "video" else 120)
            dl = QtWidgets.QVBoxLayout(dlg)
            dl.addWidget(
                InlineVideoWidget(tmp.name) if media_type == "video"
                else InlineAudioWidget(tmp.name, file_name)
            )
            bar = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Close
            )
            bar.rejected.connect(dlg.close)
            bar.accepted.connect(lambda: self._save_raw(file_name, raw))
            dl.addWidget(bar)
            dlg.exec()
            return

        self._save_raw(file_name, raw)

    def _save_raw(self, file_name: str, raw: bytes):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(None, "Save File", file_name)
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(raw)
        except Exception as e:
            QtWidgets.QMessageBox.warning(None, "Error", f"Failed to save: {e}")

    def _do_logout(self):
        sig = self.state.signals
        for attr in ("chats_received", "chat_created", "chat_opened", "more_messages",
                     "new_message", "file_received", "file_download_ready", "server_message"):
            try:
                getattr(sig, attr).disconnect()
            except Exception:
                pass
        if self.main_window:
            try:
                self.main_window.chat_panel.load_more_requested.disconnect()
            except Exception:
                pass
            self.main_window.close()
            self.main_window = None
        try:
            self.state.sock.close()
        except Exception:
            pass
        self.state.sock = None
        self.state.username = None
        self.state.current_chat_id = None
        self.connect_window = ConnectWindow()
        self.connect_window.connected.connect(self._start_login)
        self.connect_window.show()

    def _listener(self):
        while True:
            try:
                msg = recv_json(self.state.sock)
                if msg is None:
                    break
                msg_type = msg.get("type")
                sig = self.state.signals

                if msg_type in ("success", "error"):
                    sig.server_message.emit(
                        "info" if msg_type == "success" else "error",
                        msg.get("content", "")
                    )
                elif msg_type == "loginsuccess":
                    self.login_window.login_success.emit(msg.get("content"))
                elif msg_type == "loginerror":
                    self.login_window.login_error.emit(msg.get("content"))
                elif msg_type == "users_got":
                    if self.main_window:
                        self.main_window.left_panel.update_new_chat_users(msg.get("users", []))
                elif msg_type == "chats_got":
                    sig.chats_received.emit(msg.get("chats", []))
                elif msg_type == "chat_open":
                    cid  = msg.get("chat_id")
                    msgs = msg.get("messages", [])
                    off  = msg.get("offset", 0)
                    self.state.current_chat_id = cid
                    if off == 0:
                        sig.chat_opened.emit(cid, msgs)
                    else:
                        sig.more_messages.emit(msgs)
                elif msg_type == "chat_created":
                    sig.chat_created.emit(
                        msg.get("chat_name", ""),
                        msg.get("last_message", ""),
                        msg.get("chat_id"),
                    )
                elif msg_type == "new_msg":
                    if msg.get("chat_id") == self.state.current_chat_id:
                        me = msg.get("sender") == self.state.username
                        sig.new_message.emit(
                            msg.get("sender"), msg.get("content"), me, msg.get("sent_at", "")
                        )
                elif msg_type == "new_file":
                    if msg.get("chat_id") == self.state.current_chat_id:
                        me = msg.get("sender") == self.state.username
                        sig.file_received.emit(
                            msg.get("sender"), msg.get("file_name"),
                            msg.get("message_id"), msg.get("sent_at", ""), me
                        )
                elif msg_type == "file_download":
                    sig.file_download_ready.emit(msg.get("file_name"), msg.get("file_data"))

            except Exception:
                pass


if __name__ == "__main__":
    app = App()
    sys.exit(app.run())
