"""Desktop workflow for capture, transcription, retrieval, and speech."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

from asr import transcribe_audio
from tts import DEFAULT_OUTPUT, list_voices, synthesize_speech
from ui_layout import build_ui
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
            elif self.task == "speak":
                self.stage.emit("Creating speech from the answer. The first use of a voice downloads its model…")
                try:
                    synthesize_speech(
                        self.options["answer"], self.path, self.options["voice"],
                        self.options["rate"], stop_requested=self.stop_event.is_set,
                    )
                except InterruptedError:
                    self.result.emit({"task": "speak", "stopped": True})
                    return
                if self.stop_event.is_set():
                    self.result.emit({"task": "speak", "stopped": True})
                    return
                self.stage.emit("Playing the spoken answer…")
                play_audio(
                    self.path, self.options["output_device"],
                    stop_requested=self.stop_event.is_set,
                )
                self.result.emit({"task": "speak", "stopped": self.stop_event.is_set()})
                return

            self.stage.emit("Analysing audio and drawing the preview…")
            report = analyse_audio(self.path)
            save_plot(self.path, PREVIEW)
            self.result.emit(
                {"task": self.task, "path": self.path, "report": report, "plot": PREVIEW}
            )
        except Exception as exc:
            self.problem.emit(str(exc))


class SpeakRAGWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpeakRAG · Voice Studio")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1440, 900)
        self.setMinimumSize(1160, 700)
        self.current_audio: Path | None = None
        self.current_plot: Path | None = None
        self.current_transcript: dict | None = None
        self.current_answer: str | None = None
        self._pixmap: QPixmap | None = None
        self._worker: AudioJob | None = None
        self._build_ui()
        self._refresh_devices()
        self._refresh_voices()

    def _build_ui(self):
        build_ui(self, APP_ICON)

    def _refresh_devices(self):
        self.input_device.clear()
        self.output_device.clear()
        self.tts_output_device.clear()
        self.input_device.addItem("System default", None)
        self.output_device.addItem("System default", None)
        self.tts_output_device.addItem("System default speaker", None)
        try:
            for device in get_audio_devices():
                label = f"[{device['index']}] {device['name']}"
                if device["maxInputChannels"]:
                    self.input_device.addItem(label, device["index"])
                if device["maxOutputChannels"]:
                    self.output_device.addItem(label, device["index"])
                    self.tts_output_device.addItem(label, device["index"])
            self._status("Audio devices refreshed.")
        except Exception as exc:
            self._status(f"Could not list audio devices: {exc}", error=True)

    def _refresh_voices(self):
        self.tts_voice.clear()
        for voice in list_voices():
            self.tts_voice.addItem(f"{voice['name']} · {voice['language']}", voice["model"])

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
        pages = (
            ("01 / CAPTURE", "Make the question audible.",
             "Record a short question or open a WAV file. Inspect the signal before transcription."),
            ("02 / TRANSCRIBE", "Turn speech into intent.",
             "Review the words Whisper heard before sending them into retrieval."),
            ("03 / ASK & LISTEN", "Answers you can trace.",
             "Search the handbook, inspect the cited pages, then hear the grounded answer."),
        )
        eyebrow, heading, description = pages[index]
        self.content_overline.setText(eyebrow)
        self.content_heading.setText(heading)
        self.content_description.setText(description)
        self.step_badge.setText(f"STEP {index + 1} OF 3")
        for position, button in enumerate(self.nav_buttons):
            button.setProperty("active", position == index)
            button.style().unpolish(button)
            button.style().polish(button)

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
        self.current_answer = None
        self.speak_answer_button.setEnabled(False)
        self._start_job(task, ROOT, {"question": question})

    def _speak_answer(self):
        if self.current_answer:
            self._start_job("speak", DEFAULT_OUTPUT, {
                "answer": self.current_answer,
                "voice": self.tts_voice.currentData(),
                "rate": self.tts_rate.currentData(),
                "output_device": self.tts_output_device.currentData(),
            })

    def _stop(self):
        if self._worker:
            self._worker.request_stop()
            self._status("Stopping after the current audio chunk…")

    def _busy_stage(self, message: str):
        self._status(message)
        self.progress.setRange(0, 0)
        if self._worker and self._worker.task != "speak":
            self.stop_button.setEnabled(False)
            self.global_stop_button.setEnabled(False)

    def _job_result(self, payload: dict):
        if payload["task"] == "index":
            self._refresh_handbook_state()
            self._status(
                f"Indexed {payload['manifest']['chunks']} passages from "
                f"{payload['manifest']['pdf_pages']} PDF pages."
            )
            return
        if payload["task"] in ("search", "ask"):
            self.current_answer = payload["answer"] if payload["task"] == "ask" else None
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
        if payload["task"] == "speak":
            self._status(
                "Speech stopped." if payload["stopped"]
                else f"Spoken answer finished. WAV saved to {DEFAULT_OUTPUT}"
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
        self.file_label.setText(f"CURRENT FILE  /  {self.current_audio.name}")
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
        self.capture_next_button.setEnabled(not busy and self.current_audio is not None)
        self.copy_button.setEnabled(
            not busy and self.current_transcript is not None and bool(self.current_transcript["text"])
        )
        self.transcript_to_ask_button.setEnabled(
            not busy and self.current_transcript is not None and bool(self.current_transcript["text"])
        )
        self.prepare_handbook_button.setEnabled(not busy)
        self.use_transcript_button.setEnabled(not busy)
        self.search_handbook_button.setEnabled(not busy and HANDBOOK_INDEX.exists())
        self.ask_handbook_button.setEnabled(not busy and HANDBOOK_INDEX.exists())
        self.speak_answer_button.setEnabled(not busy and bool(self.current_answer))
        can_stop = busy and self._worker is not None and self._worker.task in ("record", "play", "speak")
        self.stop_button.setEnabled(can_stop)
        self.global_stop_button.setEnabled(can_stop)
        for widget in (
            self.input_device, self.output_device, self.rate, self.channels, self.seconds,
            self.asr_model, self.handbook_query, self.tts_voice, self.tts_rate,
            self.tts_output_device,
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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SpeakRAG")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    window = SpeakRAGWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
