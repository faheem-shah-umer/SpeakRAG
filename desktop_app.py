"""Desktop controls for SpeakRAG's microphone, playback, and audio analysis."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from asr import transcribe_audio
from voice_loop import analyse_audio, get_audio_devices, play_audio, record_audio, save_plot


ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT / "plots" / "current.png"
APP_ICON = ROOT / "docs" / "SpeakRAG.ico"
HANDBOOK_INDEX = ROOT / "data" / "handbook_index.json"


class AudioJob(QThread):
    progress = Signal(int)
    stage = Signal(str)
    result = Signal(object)
    problem = Signal(str)

    def __init__(self, task: str, path: Path, options: dict | None = None, parent=None):
        super().__init__(parent)
        self.task = task
        self.path = path
        self.options = options or {}
        self.stop_event = Event()

    def request_stop(self):
        self.stop_event.set()

    def run(self):
        try:
            if self.task == "index":
                from handbook_rag import download_handbook, index_handbook

                self.stage.emit("Preparing the official handbook and building its Qdrant index…")
                manifest = index_handbook(download_handbook())
                self.result.emit({"task": "index", "manifest": manifest})
                return
            if self.task in ("search", "ask"):
                from handbook_rag import ask_handbook, search_handbook

                question = self.options["question"]
                self.stage.emit("Searching the handbook…")
                if self.task == "ask":
                    result = ask_handbook(question)
                    self.result.emit({"task": "ask", **result})
                else:
                    self.result.emit({
                        "task": "search", "hits": search_handbook(question), "answer": None
                    })
                return
            if self.task == "record":
                record_audio(
                    self.path,
                    self.options["seconds"],
                    self.options["sample_rate"],
                    self.options["channels"],
                    self.options["input_device"],
                    stop_requested=self.stop_event.is_set,
                    on_progress=lambda fraction: self.progress.emit(round(fraction * 100)),
                )
            elif self.task == "play":
                play_audio(
                    self.path,
                    self.options["output_device"],
                    stop_requested=self.stop_event.is_set,
                )
                self.result.emit({"task": "play"})
                return
            elif self.task == "transcribe":
                self.stage.emit("Transcribing audio. The first run downloads the selected model…")
                transcript = transcribe_audio(self.path, self.options["model"])
                self.result.emit({"task": "transcribe", "transcript": transcript})
                return

            self.stage.emit("Analysing audio and drawing the preview…")
            report = analyse_audio(self.path)
            save_plot(self.path, PREVIEW)
            self.result.emit(
                {"task": self.task, "path": self.path, "report": report, "plot": PREVIEW}
            )
        except Exception as exc:
            self.problem.emit(str(exc))


def metric_card(title: str) -> tuple[QFrame, QLabel]:
    card = QFrame()
    card.setObjectName("metricCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(17, 12, 17, 12)
    layout.setSpacing(3)
    caption = QLabel(title)
    caption.setObjectName("metricCaption")
    value = QLabel("—")
    value.setObjectName("metricValue")
    layout.addWidget(caption)
    layout.addWidget(value)
    return card, value


class SpeakRAGWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpeakRAG · Speech Lab")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1240, 830)
        self.setMinimumSize(960, 680)
        self.current_audio: Path | None = None
        self.current_plot: Path | None = None
        self.current_transcript: dict | None = None
        self._pixmap: QPixmap | None = None
        self._worker: AudioJob | None = None
        self._build_ui()
        self._refresh_devices()

    def _build_ui(self):
        shell = QWidget()
        shell.setObjectName("shell")
        self.setCentralWidget(shell)
        root = QVBoxLayout(shell)
        root.setContentsMargins(32, 26, 32, 24)
        root.setSpacing(23)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setObjectName("logo")
        logo.setFixedSize(58, 58)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(
            QPixmap(str(APP_ICON)).scaled(
                46, 46, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        header.addWidget(logo)
        header.addSpacing(12)
        identity = QVBoxLayout()
        identity.setSpacing(2)
        brand = QLabel("SpeakRAG")
        brand.setObjectName("brand")
        subtitle = QLabel("An ASR · RAG · TTS assistant")
        subtitle.setObjectName("muted")
        identity.addWidget(brand)
        identity.addWidget(subtitle)
        header.addLayout(identity)
        header.addStretch()
        badge = QLabel("02  /  SPEECH LAB")
        badge.setObjectName("badge")
        header.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, stretch=1)

        controls = QFrame()
        self.controls = controls
        controls.setObjectName("panel")
        controls.setFixedWidth(306)
        left = QVBoxLayout(controls)
        left.setContentsMargins(21, 21, 21, 21)
        left.setSpacing(13)
        section = QLabel("CAPTURE")
        section.setObjectName("eyebrow")
        left.addWidget(section)
        title = QLabel("Give audio a shape.")
        title.setObjectName("sectionTitle")
        left.addWidget(title)
        hint = QLabel("Record a sample or open an existing WAV file to inspect it.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        left.addWidget(hint)
        left.addSpacing(7)

        self.input_device = self._field(left, "MICROPHONE", QComboBox())
        self.output_device = self._field(left, "SPEAKER", QComboBox())
        self.rate = self._field(left, "SAMPLE RATE", QComboBox())
        for text, value in [
            ("Device native rate", None),
            ("16,000 Hz", 16_000),
            ("44,100 Hz", 44_100),
            ("48,000 Hz", 48_000),
        ]:
            self.rate.addItem(text, value)

        settings = QHBoxLayout()
        settings.setSpacing(10)
        duration_box = QVBoxLayout()
        duration_label = QLabel("MAX LENGTH")
        duration_label.setObjectName("fieldLabel")
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(1, 60)
        self.seconds.setValue(5)
        self.seconds.setSingleStep(1)
        self.seconds.setSuffix(" sec")
        duration_box.addWidget(duration_label)
        duration_box.addWidget(self.seconds)
        settings.addLayout(duration_box)
        channels_box = QVBoxLayout()
        channels_label = QLabel("CHANNELS")
        channels_label.setObjectName("fieldLabel")
        self.channels = QComboBox()
        self.channels.addItem("Mono", 1)
        self.channels.addItem("Stereo", 2)
        channels_box.addWidget(channels_label)
        channels_box.addWidget(self.channels)
        settings.addLayout(channels_box)
        left.addLayout(settings)
        left.addSpacing(5)

        self.record_button = QPushButton("●  Record audio")
        self.record_button.setObjectName("primaryButton")
        self.record_button.clicked.connect(self._record)
        left.addWidget(self.record_button)
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.setEnabled(False)
        left.addWidget(self.stop_button)
        self.open_button = QPushButton("Open WAV file")
        self.open_button.clicked.connect(self._open_file)
        left.addWidget(self.open_button)
        self.play_button = QPushButton("▶  Play current audio")
        self.play_button.clicked.connect(self._play)
        self.play_button.setEnabled(False)
        left.addWidget(self.play_button)
        left.addStretch()
        self.refresh_button = QPushButton("↻  Refresh audio devices")
        self.refresh_button.setObjectName("quietButton")
        self.refresh_button.clicked.connect(self._refresh_devices)
        left.addWidget(self.refresh_button)
        body.addWidget(controls)

        content = QVBoxLayout()
        content.setSpacing(17)
        body.addLayout(content, stretch=1)
        topline = QHBoxLayout()
        toptext = QVBoxLayout()
        overline = QLabel("YOUR SIGNAL, EXPLAINED")
        self.content_overline = overline
        overline.setObjectName("eyebrow")
        heading = QLabel("Listen. Inspect. Transcribe.")
        self.content_heading = heading
        heading.setObjectName("heading")
        toptext.addWidget(overline)
        toptext.addWidget(heading)
        topline.addLayout(toptext)
        topline.addStretch()
        self.export_button = QPushButton("Export plot")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_plot)
        topline.addWidget(self.export_button, alignment=Qt.AlignmentFlag.AlignBottom)
        content.addLayout(topline)

        self.metric_widget = QWidget()
        metric_grid = QGridLayout(self.metric_widget)
        metric_grid.setContentsMargins(0, 0, 0, 0)
        metric_grid.setSpacing(10)
        self.metrics = {}
        for index, label in enumerate(
            ("DURATION", "SAMPLE RATE", "PEAK LEVEL", "AVERAGE LEVEL", "CLIPPING", "SILENCE")
        ):
            card, value = metric_card(label)
            self.metrics[label] = value
            metric_grid.addWidget(card, index // 3, index % 3)
        content.addWidget(self.metric_widget)

        self.tabs = QTabWidget()
        chart = QFrame()
        chart.setObjectName("panel")
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(17, 16, 17, 16)
        chart_title = QLabel("WAVEFORM  /  SPECTROGRAM")
        chart_title.setObjectName("eyebrow")
        chart_layout.addWidget(chart_title)
        self.plot_label = QLabel("Your waveform will appear here.\nRecord audio or open a WAV file to begin.")
        self.plot_label.setObjectName("plotPlaceholder")
        self.plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.plot_label.setMinimumHeight(250)
        chart_layout.addWidget(self.plot_label, stretch=1)
        self.tabs.addTab(chart, "Signal")

        transcript_panel = QFrame()
        transcript_panel.setObjectName("panel")
        transcript_layout = QVBoxLayout(transcript_panel)
        transcript_layout.setContentsMargins(21, 20, 21, 20)
        transcript_layout.setSpacing(13)
        transcript_title = QLabel("AUTOMATIC SPEECH RECOGNITION")
        transcript_title.setObjectName("eyebrow")
        transcript_layout.addWidget(transcript_title)
        transcript_controls = QHBoxLayout()
        self.asr_model = QComboBox()
        self.asr_model.addItem("base.en · English", "base.en")
        self.asr_model.addItem("tiny.en · faster English", "tiny.en")
        self.asr_model.addItem("base · multilingual", "base")
        transcript_controls.addWidget(self.asr_model, stretch=1)
        self.transcribe_button = QPushButton("Transcribe WAV")
        self.transcribe_button.setObjectName("primaryButton")
        self.transcribe_button.setEnabled(False)
        self.transcribe_button.clicked.connect(self._transcribe)
        transcript_controls.addWidget(self.transcribe_button)
        self.copy_button = QPushButton("Copy text")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_transcript)
        transcript_controls.addWidget(self.copy_button)
        transcript_layout.addLayout(transcript_controls)
        self.transcript_meta = QLabel("Choose an audio file, then transcribe it.")
        self.transcript_meta.setObjectName("muted")
        transcript_layout.addWidget(self.transcript_meta)
        self.transcript_text = QPlainTextEdit()
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setPlaceholderText("Recognised speech will appear here.")
        transcript_layout.addWidget(self.transcript_text, stretch=1)
        segment_label = QLabel("TIMESTAMPED SEGMENTS")
        segment_label.setObjectName("eyebrow")
        transcript_layout.addWidget(segment_label)
        self.segment_text = QPlainTextEdit()
        self.segment_text.setReadOnly(True)
        self.segment_text.setMaximumHeight(95)
        self.segment_text.setPlaceholderText("No segments yet.")
        transcript_layout.addWidget(self.segment_text)
        self.tabs.addTab(transcript_panel, "Transcript")

        handbook_panel = QFrame()
        handbook_panel.setObjectName("panel")
        handbook_layout = QVBoxLayout(handbook_panel)
        handbook_layout.setContentsMargins(21, 20, 21, 20)
        handbook_layout.setSpacing(12)
        handbook_title = QLabel("AUTOMOTIVE HANDBOOK  /  QDRANT")
        handbook_title.setObjectName("eyebrow")
        handbook_layout.addWidget(handbook_title)
        self.handbook_meta = QLabel(
            "Index the official Hyundai IONIQ 5 manual once to search it locally."
        )
        self.handbook_meta.setObjectName("muted")
        self.handbook_meta.setWordWrap(True)
        handbook_layout.addWidget(self.handbook_meta)
        self.prepare_handbook_button = QPushButton("Prepare sample handbook")
        self.prepare_handbook_button.clicked.connect(self._prepare_handbook)
        handbook_layout.addWidget(self.prepare_handbook_button)
        self.handbook_query = QLineEdit()
        self.handbook_query.setPlaceholderText("Ask a question about the handbook…")
        handbook_layout.addWidget(self.handbook_query)
        handbook_actions = QHBoxLayout()
        self.use_transcript_button = QPushButton("Use transcript")
        self.use_transcript_button.clicked.connect(self._use_transcript)
        handbook_actions.addWidget(self.use_transcript_button)
        self.search_handbook_button = QPushButton("Search pages")
        self.search_handbook_button.clicked.connect(lambda: self._handbook_job("search"))
        handbook_actions.addWidget(self.search_handbook_button)
        self.ask_handbook_button = QPushButton("Generate answer")
        self.ask_handbook_button.setObjectName("primaryButton")
        self.ask_handbook_button.clicked.connect(lambda: self._handbook_job("ask"))
        handbook_actions.addWidget(self.ask_handbook_button)
        handbook_layout.addLayout(handbook_actions)
        self.handbook_answer = QPlainTextEdit()
        self.handbook_answer.setReadOnly(True)
        self.handbook_answer.setPlaceholderText("The grounded answer will appear here.")
        self.handbook_answer.setMaximumHeight(130)
        handbook_layout.addWidget(self.handbook_answer)
        sources_label = QLabel("RETRIEVED PASSAGES  /  PDF PAGE REFERENCES")
        sources_label.setObjectName("eyebrow")
        handbook_layout.addWidget(sources_label)
        self.handbook_sources = QPlainTextEdit()
        self.handbook_sources.setReadOnly(True)
        self.handbook_sources.setPlaceholderText("Search results will appear here.")
        handbook_layout.addWidget(self.handbook_sources, stretch=1)
        self.tabs.addTab(handbook_panel, "Handbook")
        self.tabs.currentChanged.connect(self._tab_changed)
        self._refresh_handbook_state()
        content.addWidget(self.tabs, stretch=1)

        footer = QFrame()
        footer.setObjectName("statusPanel")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(17, 12, 17, 12)
        footer_layout.setSpacing(6)
        self.status = QLabel("Ready to inspect audio. Recordings stay on this computer.")
        self.status.setObjectName("statusText")
        self.status.setWordWrap(True)
        footer_layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        footer_layout.addWidget(self.progress)
        self.file_label = QLabel("NO FILE SELECTED")
        self.file_label.setObjectName("fileLabel")
        footer_layout.addWidget(self.file_label)
        content.addWidget(footer)

        self.setStyleSheet(STYLE)

    def _field(self, layout: QVBoxLayout, label: str, widget: QComboBox):
        caption = QLabel(label)
        caption.setObjectName("fieldLabel")
        layout.addWidget(caption)
        layout.addWidget(widget)
        return widget

    def _refresh_devices(self):
        self.input_device.clear()
        self.output_device.clear()
        self.input_device.addItem("System default", None)
        self.output_device.addItem("System default", None)
        try:
            for device in get_audio_devices():
                label = f"[{device['index']}] {device['name']}"
                if device["maxInputChannels"]:
                    self.input_device.addItem(label, device["index"])
                if device["maxOutputChannels"]:
                    self.output_device.addItem(label, device["index"])
            self._status("Audio devices refreshed.")
        except Exception as exc:
            self._status(f"Could not list audio devices: {exc}", error=True)

    def _start_job(self, task: str, path: Path, options: dict | None = None):
        if self._worker is not None:
            return
        self._worker = AudioJob(task, path, options, self)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.stage.connect(self._busy_stage)
        self._worker.result.connect(self._job_result)
        self._worker.problem.connect(self._job_error)
        self._worker.finished.connect(self._job_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._set_busy(True)
        self.progress.setRange(0, 100 if task == "record" else 0)
        self.progress.setValue(0)
        self._worker.start()

    def _record(self):
        filename = f"voice-{datetime.now():%Y%m%d-%H%M%S}.wav"
        path = ROOT / "recordings" / filename
        options = {
            "seconds": self.seconds.value(),
            "sample_rate": self.rate.currentData(),
            "channels": self.channels.currentData(),
            "input_device": self.input_device.currentData(),
        }
        self._status(f"Recording up to {options['seconds']:g} seconds…")
        self._start_job("record", path, options)

    def _open_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open uncompressed WAV", str(ROOT / "recordings"), "WAV audio (*.wav)"
        )
        if filename:
            self._status("Loading and analysing WAV…")
            self._start_job("load", Path(filename))

    def _play(self):
        if self.current_audio:
            self._status("Playing audio…")
            self._start_job(
                "play", self.current_audio, {"output_device": self.output_device.currentData()}
            )

    def _transcribe(self):
        if self.current_audio:
            self._status("Starting local transcription…")
            self._start_job(
                "transcribe", self.current_audio, {"model": self.asr_model.currentData()}
            )

    def _copy_transcript(self):
        if self.current_transcript:
            QApplication.clipboard().setText(self.current_transcript["text"])
            self._status("Transcript copied to the clipboard.")

    def _refresh_handbook_state(self):
        ready = HANDBOOK_INDEX.exists()
        try:
            title = json.loads(HANDBOOK_INDEX.read_text(encoding="utf-8"))["title"] if ready else None
        except (OSError, ValueError, KeyError):
            ready = False
            title = None
        self.search_handbook_button.setEnabled(ready)
        self.ask_handbook_button.setEnabled(ready)
        self.handbook_meta.setText(
            f"{title} is indexed. Ask a question or use a transcript."
            if ready else "Index the official Hyundai IONIQ 5 manual once to search it locally."
        )

    def _tab_changed(self, index: int):
        handbook = index == 2
        self.controls.setVisible(not handbook)
        self.metric_widget.setVisible(not handbook)
        self.export_button.setVisible(not handbook)
        self.content_overline.setText("AUTOMOTIVE KNOWLEDGE, GROUNDED" if handbook else "YOUR SIGNAL, EXPLAINED")
        self.content_heading.setText("Ask. Retrieve. Verify." if handbook else "Listen. Inspect. Transcribe.")

    def _prepare_handbook(self):
        self._status("Preparing the handbook. The first run downloads the PDF and embedding model…")
        self._start_job("index", ROOT)

    def _use_transcript(self):
        if self.current_transcript and self.current_transcript["text"]:
            self.handbook_query.setText(self.current_transcript["text"])
            self.tabs.setCurrentIndex(2)
        else:
            self._status("Transcribe a WAV file first, or type a handbook question.")

    def _handbook_job(self, task: str):
        question = self.handbook_query.text().strip()
        if not question:
            self._status("Type a handbook question first.")
            return
        self._start_job(task, ROOT, {"question": question})

    def _stop(self):
        if self._worker:
            self._worker.request_stop()
            self._status("Stopping after the current audio chunk…")

    def _busy_stage(self, message: str):
        self._status(message)
        self.progress.setRange(0, 0)
        self.stop_button.setEnabled(False)

    def _job_result(self, payload: dict):
        if payload["task"] == "index":
            self._refresh_handbook_state()
            self._status(
                f"Indexed {payload['manifest']['chunks']} passages from "
                f"{payload['manifest']['pdf_pages']} PDF pages."
            )
            return
        if payload["task"] in ("search", "ask"):
            self.handbook_answer.setPlainText(payload["answer"] or "Search results are shown below.")
            self.handbook_sources.setPlainText("\n\n".join(
                f"[{number}] {hit['title']} · PDF page {hit['pdf_page']} "
                f"· relevance {hit['score']:.3f}\n{hit['text']}\n{hit['source_url']}"
                for number, hit in enumerate(payload["hits"], start=1)
            ))
            self.tabs.setCurrentIndex(2)
            self._status(
                "Answer ready with source pages." if payload["task"] == "ask"
                else "Relevant handbook passages are ready."
            )
            return
        if payload["task"] == "play":
            self._status("Playback finished.")
            return
        if payload["task"] == "transcribe":
            self.current_transcript = payload["transcript"]
            result = self.current_transcript
            self.transcript_text.setPlainText(result["text"] or "[No speech detected]")
            self.segment_text.setPlainText(
                "\n".join(
                    f"{part['start']:.2f}–{part['end']:.2f} s   {part['text']}"
                    for part in result["segments"]
                )
            )
            self.transcript_meta.setText(
                f"{result['model']}  ·  {result['language']}  ·  "
                f"ASR {result['transcription_seconds']:.2f} s  ·  "
                f"model load {result['model_load_seconds']:.2f} s"
            )
            self.tabs.setCurrentIndex(1)
            self._status("Transcription ready. Review the text before using it for retrieval.")
            return
        self.current_audio = payload["path"]
        self.current_plot = payload["plot"]
        self.current_transcript = None
        self.transcript_text.clear()
        self.segment_text.clear()
        self.transcript_meta.setText("Choose an audio file, then transcribe it.")
        self._pixmap = QPixmap(str(self.current_plot))
        self._show_plot()
        self._show_metrics(payload["report"])
        self.file_label.setText(str(self.current_audio))
        self.file_label.setToolTip(str(self.current_audio))
        self._status("Audio ready. Compare the levels and shape, or play it back.")

    def _job_error(self, message: str):
        if "-9999" in message or "-9996" in message:
            message += ". Try another microphone in the list and check Windows microphone access."
        self._status(f"Error: {message}", error=True)

    def _job_finished(self):
        self._worker = None
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self.record_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy)
        self.play_button.setEnabled(not busy and self.current_audio is not None)
        self.export_button.setEnabled(not busy and self.current_plot is not None)
        self.transcribe_button.setEnabled(not busy and self.current_audio is not None)
        self.copy_button.setEnabled(
            not busy and self.current_transcript is not None and bool(self.current_transcript["text"])
        )
        self.prepare_handbook_button.setEnabled(not busy)
        self.use_transcript_button.setEnabled(not busy)
        self.search_handbook_button.setEnabled(not busy and HANDBOOK_INDEX.exists())
        self.ask_handbook_button.setEnabled(not busy and HANDBOOK_INDEX.exists())
        self.stop_button.setEnabled(
            busy and self._worker is not None and self._worker.task in ("record", "play")
        )
        for widget in (
            self.input_device, self.output_device, self.rate, self.channels, self.seconds,
            self.asr_model, self.handbook_query,
        ):
            widget.setEnabled(not busy)

    def _show_metrics(self, report: dict):
        values = {
            "DURATION": f"{report['duration_seconds']:.2f} s",
            "SAMPLE RATE": f"{report['sample_rate_hz'] / 1000:g} kHz",
            "PEAK LEVEL": self._level(report["peak_dbfs"]),
            "AVERAGE LEVEL": self._level(report["rms_dbfs"]),
            "CLIPPING": f"{report['clipped_samples_percent']:.2f}%",
            "SILENCE": f"{report['silent_frames_percent']:.1f}%",
        }
        for name, value in values.items():
            self.metrics[name].setText(value)

    @staticmethod
    def _level(value):
        return "Silence" if value is None else f"{value:.1f} dBFS"

    def _show_plot(self):
        if self._pixmap and not self._pixmap.isNull():
            size = self.plot_label.size()
            self.plot_label.setPixmap(
                self._pixmap.scaled(
                    size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )

    def _export_plot(self):
        if self.current_plot is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export plot", str(ROOT / "plots" / "audio-analysis.png"), "PNG image (*.png)"
        )
        if filename:
            target = Path(filename)
            if target.resolve() != self.current_plot.resolve():
                shutil.copyfile(self.current_plot, target)
            self._status(f"Plot exported to {target}")

    def _status(self, message: str, error: bool = False):
        self.status.setText(message)
        self.status.setProperty("error", error)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show_plot()

    def closeEvent(self, event):
        if self._worker is not None:
            self._worker.request_stop()
            self._worker.wait()
        super().closeEvent(event)


STYLE = """
QWidget#shell { background: #0b1117; color: #e9f0ee; font-family: 'Segoe UI'; font-size: 13px; }
QLabel#brand { font-size: 27px; font-weight: 800; color: #f3f8f6; }
QLabel#logo { background: transparent; }
QLabel#muted { color: #8fa39f; font-size: 12px; }
QLabel#badge { color: #7ce5b5; background: #17372c; border: 1px solid #2b7553;
               border-radius: 11px; padding: 9px 15px; font-size: 11px; font-weight: 700; }
QFrame#panel { background: #121d24; border: 1px solid #273b43; border-radius: 16px; }
QFrame#metricCard { background: #17252c; border: 1px solid #294047; border-radius: 12px; }
QFrame#statusPanel { background: #10202a; border: 1px solid #274351; border-radius: 12px; }
QTabWidget::pane { border: 0; background: transparent; }
QTabBar::tab { background: #17262e; color: #93aaa3; border: 1px solid #294047;
               border-bottom: 0; padding: 9px 19px; margin-right: 4px;
               border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #234738; color: #abf4d0; }
QPlainTextEdit { background: #0e191f; color: #e9f0ee; border: 1px solid #355058;
                 border-radius: 9px; padding: 12px; font-family: 'Consolas'; font-size: 14px; }
QLabel#eyebrow, QLabel#fieldLabel, QLabel#metricCaption, QLabel#fileLabel {
    color: #75c8a3; font-size: 10px; font-weight: 800; letter-spacing: 1px;
}
QLabel#sectionTitle { color: #f0f6f3; font-size: 20px; font-weight: 700; }
QLabel#heading { color: #f0f6f3; font-size: 25px; font-weight: 700; }
QLabel#metricValue { color: #f3f8f6; font-size: 22px; font-weight: 700; }
QLabel#plotPlaceholder { color: #77908e; background: #0e191f; border: 1px dashed #35505a;
                         border-radius: 10px; font-size: 15px; }
QLabel#statusText { color: #bfdbd3; }
QLabel#statusText[error="true"] { color: #ffb0a1; }
QLabel#fileLabel { color: #729e9d; }
QComboBox, QDoubleSpinBox { background: #0c171d; color: #e9f0ee; border: 1px solid #355058;
                           border-radius: 8px; padding: 9px; min-height: 19px; }
QComboBox QAbstractItemView { background: #15242b; color: #e9f0ee; selection-background-color: #266b54; }
QLineEdit { background: #0c171d; color: #e9f0ee; border: 1px solid #355058;
            border-radius: 8px; padding: 10px; }
QPushButton { background: #21343b; color: #e6f1ec; border: 1px solid #38565e;
              border-radius: 9px; padding: 10px; font-weight: 600; }
QPushButton:hover { background: #2b4850; }
QPushButton:disabled { color: #6d8585; background: #19282e; border-color: #273d43; }
QPushButton#primaryButton { background: #7ce5b5; color: #09231a; border: 0; font-weight: 800; }
QPushButton#primaryButton:hover { background: #9cf1ca; }
QPushButton#primaryButton:disabled { background: #376954; color: #9bb8aa; }
QPushButton#quietButton { background: transparent; border: 0; color: #86b9a5; }
QProgressBar { background: #172b33; border: 0; border-radius: 4px; height: 7px; }
QProgressBar::chunk { background: #7ce5b5; border-radius: 4px; }
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SpeakRAG")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    window = SpeakRAGWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
