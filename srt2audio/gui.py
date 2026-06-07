"""PySide6 GUI for the SRT -> audio converter."""

from __future__ import annotations

import os
import threading
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .processor import JobResult, MAX_WORKERS_LIMIT, export_job, run_job
from .srt_parser import SrtParseError, parse_srt_file
from .tts_client import VOICES, CapCutTTSClient, DEFAULT_BASE_URL, TTSError, TTSParams


class JobWorker(QObject):
    """Runs a conversion job on a background thread and relays progress."""

    progress = Signal(int, int)
    log = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, config: dict, cancel_event: threading.Event) -> None:
        super().__init__()
        self._config = config
        self._cancel_event = cancel_event

    def run(self) -> None:
        cfg = self._config
        try:
            subtitles = parse_srt_file(cfg["srt_path"])
            self.log.emit(f"Đã đọc {len(subtitles)} đoạn từ SRT.")
            client = CapCutTTSClient(base_url=cfg["base_url"], timeout=cfg["timeout"])
            params = TTSParams(
                voice_type=cfg["voice_type"],
                pitch=cfg["pitch"],
                speed=cfg["speed"],
                volume=cfg["volume"],
            )
            job: JobResult = run_job(
                subtitles,
                client,
                params,
                max_workers=cfg["max_workers"],
                max_speed=cfg["max_speed"],
                progress_cb=lambda d, t: self.progress.emit(d, t),
                log_cb=lambda m: self.log.emit(m),
                cancel_event=self._cancel_event,
            )
            if job.cancelled:
                self.failed.emit("Đã hủy bởi người dùng.")
                return
            if job.timeline is None:
                self.failed.emit("Không có đoạn nào tạo audio thành công.")
                return
            export_job(job, cfg["out_path"], fmt=cfg["fmt"], bitrate=cfg["bitrate"])
            self.log.emit(f"Đã xuất file: {cfg['out_path']}")
            self.finished.emit(job)
        except (SrtParseError, TTSError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Lỗi không mong đợi: {exc}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SRT \u2192 Audio (CapCut TTS)")
        self.resize(820, 680)

        self._thread: Optional[QThread] = None
        self._worker: Optional[JobWorker] = None
        self._cancel_event: Optional[threading.Event] = None

        self._build_ui()

    # -- UI construction -------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)

        title = QLabel("SRT \u2192 Audio b\u1eb1ng CapCut TTS")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        root.addWidget(title)

        root.addWidget(self._build_file_group())
        root.addWidget(self._build_voice_group())
        root.addWidget(self._build_perf_group())

        # Progress + status
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)
        self.status_label = QLabel("S\u1eb5n s\u00e0ng.")
        root.addWidget(self.status_label)

        # Log
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(180)
        root.addWidget(self.log_view, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("B\u1eaft \u0111\u1ea7u")
        self.start_btn.clicked.connect(self._on_start)
        self.cancel_btn = QPushButton("H\u1ee7y")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addStretch(1)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.start_btn)
        root.addLayout(btn_row)

    def _build_file_group(self) -> QGroupBox:
        box = QGroupBox("File")
        grid = QGridLayout(box)

        grid.addWidget(QLabel("File SRT:"), 0, 0)
        self.srt_edit = QLineEdit()
        grid.addWidget(self.srt_edit, 0, 1)
        srt_btn = QPushButton("Ch\u1ecdn...")
        srt_btn.clicked.connect(self._pick_srt)
        grid.addWidget(srt_btn, 0, 2)

        grid.addWidget(QLabel("File xu\u1ea5t:"), 1, 0)
        self.out_edit = QLineEdit()
        grid.addWidget(self.out_edit, 1, 1)
        out_btn = QPushButton("L\u01b0u...")
        out_btn.clicked.connect(self._pick_out)
        grid.addWidget(out_btn, 1, 2)

        grid.addWidget(QLabel("\u0110\u1ecbnh d\u1ea1ng:"), 2, 0)
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["wav", "mp3", "m4a"])
        grid.addWidget(self.fmt_combo, 2, 1)
        return box

    def _build_voice_group(self) -> QGroupBox:
        box = QGroupBox("CapCut TTS")
        form = QFormLayout(box)

        self.base_url_edit = QLineEdit(DEFAULT_BASE_URL)
        url_row = QHBoxLayout()
        url_row.addWidget(self.base_url_edit, stretch=1)
        test_btn = QPushButton("Ki\u1ec3m tra k\u1ebft n\u1ed1i")
        test_btn.clicked.connect(self._on_test_connection)
        url_row.addWidget(test_btn)
        url_widget = QWidget()
        url_widget.setLayout(url_row)
        form.addRow("Base URL:", url_widget)

        self.voice_combo = QComboBox()
        for voice in VOICES:
            self.voice_combo.addItem(str(voice["label"]), voice["type"])
        form.addRow("Gi\u1ecdng:", self.voice_combo)

        self.pitch_spin = self._make_spin(0, 20, 10)
        self.speed_spin = self._make_spin(0, 20, 10)
        self.volume_spin = self._make_spin(0, 20, 10)
        form.addRow("Pitch:", self.pitch_spin)
        form.addRow("Speed (API):", self.speed_spin)
        form.addRow("Volume:", self.volume_spin)
        return box

    def _build_perf_group(self) -> QGroupBox:
        box = QGroupBox("Hi\u1ec7u n\u0103ng & kh\u1edbp th\u1eddi gian")
        form = QFormLayout(box)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, MAX_WORKERS_LIMIT)
        self.workers_spin.setValue(16)
        form.addRow(f"S\u1ed1 lu\u1ed3ng (1-{MAX_WORKERS_LIMIT}):", self.workers_spin)

        self.max_speed_spin = QDoubleSpinBox()
        self.max_speed_spin.setRange(1.0, 4.0)
        self.max_speed_spin.setSingleStep(0.1)
        self.max_speed_spin.setValue(2.0)
        form.addRow("T\u0103ng t\u1ed1c t\u1ed1i \u0111a (x):", self.max_speed_spin)
        return box

    @staticmethod
    def _make_spin(lo: int, hi: int, val: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(val)
        return spin

    # -- Slots -----------------------------------------------------------
    def _pick_srt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ch\u1ecdn file SRT", "", "SRT (*.srt);;All files (*)")
        if path:
            self.srt_edit.setText(path)
            if not self.out_edit.text():
                base, _ = os.path.splitext(path)
                self.out_edit.setText(base + ".wav")

    def _pick_out(self) -> None:
        fmt = self.fmt_combo.currentText()
        path, _ = QFileDialog.getSaveFileName(self, "L\u01b0u file audio", "", f"Audio (*.{fmt});;All files (*)")
        if path:
            self.out_edit.setText(path)

    def _append_log(self, msg: str) -> None:
        self.log_view.appendPlainText(msg)

    def _on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(done)
        self.status_label.setText(f"\u0110ang x\u1eed l\u00fd: {done}/{total}")

    def _set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)

    def _collect_config(self) -> Optional[dict]:
        srt_path = self.srt_edit.text().strip()
        out_path = self.out_edit.text().strip()
        if not srt_path or not os.path.isfile(srt_path):
            QMessageBox.warning(self, "Thi\u1ebfu file", "Vui l\u00f2ng ch\u1ecdn file SRT h\u1ee3p l\u1ec7.")
            return None
        if not out_path:
            QMessageBox.warning(self, "Thi\u1ebfu file", "Vui l\u00f2ng ch\u1ecdn n\u01a1i l\u01b0u file xu\u1ea5t.")
            return None
        return {
            "srt_path": srt_path,
            "out_path": out_path,
            "fmt": self.fmt_combo.currentText(),
            "bitrate": "192k",
            "base_url": self.base_url_edit.text().strip() or DEFAULT_BASE_URL,
            "timeout": 60.0,
            "voice_type": int(self.voice_combo.currentData()),
            "pitch": self.pitch_spin.value(),
            "speed": self.speed_spin.value(),
            "volume": self.volume_spin.value(),
            "max_workers": self.workers_spin.value(),
            "max_speed": self.max_speed_spin.value(),
        }

    def _on_test_connection(self) -> None:
        url = self.base_url_edit.text().strip() or DEFAULT_BASE_URL
        try:
            client = CapCutTTSClient(base_url=url, timeout=15.0, max_retries=1)
            client.check_connection(
                TTSParams(voice_type=int(self.voice_combo.currentData()))
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "K\u1ebft n\u1ed1i th\u1ea5t b\u1ea1i", str(exc))
        else:
            QMessageBox.information(self, "OK", "K\u1ebft n\u1ed1i t\u1edbi server TTS th\u00e0nh c\u00f4ng.")

    def _on_start(self) -> None:
        config = self._collect_config()
        if config is None:
            return
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self._set_running(True)

        self._cancel_event = threading.Event()
        self._thread = QThread()
        self._worker = JobWorker(config, self._cancel_event)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _on_cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.status_label.setText("\u0110ang h\u1ee7y...")
            self._append_log("Y\u00eau c\u1ea7u h\u1ee7y - ch\u1edd c\u00e1c lu\u1ed3ng \u0111ang ch\u1ea1y k\u1ebft th\u00fac.")

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self._set_running(False)

    def _on_finished(self, job: JobResult) -> None:
        self.status_label.setText(
            f"Xong: {job.success_count} th\u00e0nh c\u00f4ng, {job.failure_count} l\u1ed7i."
        )
        self._teardown_thread()
        QMessageBox.information(
            self,
            "Ho\u00e0n t\u1ea5t",
            f"\u0110\u00e3 xu\u1ea5t file.\nTh\u00e0nh c\u00f4ng: {job.success_count}\nL\u1ed7i: {job.failure_count}",
        )

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Th\u1ea5t b\u1ea1i / \u0111\u00e3 h\u1ee7y.")
        self._append_log(f"!! {message}")
        self._teardown_thread()
        QMessageBox.critical(self, "L\u1ed7i", message)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
