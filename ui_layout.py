"""The SpeakRAG desktop layout and visual language."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


def label(text: str, kind: str, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(kind)
    widget.setWordWrap(wrap)
    return widget


def field(layout: QVBoxLayout, title: str, widget: QWidget) -> QWidget:
    layout.addWidget(label(title, "fieldLabel"))
    layout.addWidget(widget)
    return widget


def panel(layout: QVBoxLayout | QHBoxLayout, name: str = "panel") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(name)
    inner = QVBoxLayout(frame)
    inner.setContentsMargins(24, 22, 24, 22)
    inner.setSpacing(14)
    layout.addWidget(frame)
    return frame, inner


def page(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("pageScroll")
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll


def metric_card(title: str) -> tuple[QFrame, QLabel]:
    card = QFrame()
    card.setObjectName("metricCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(4)
    layout.addWidget(label(title, "metricCaption"))
    value = label("—", "metricValue")
    layout.addWidget(value)
    return card, value


def build_ui(window, icon_path: Path) -> None:
    shell = QWidget()
    shell.setObjectName("shell")
    window.setCentralWidget(shell)
    root = QHBoxLayout(shell)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    sidebar = QFrame()
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(236)
    rail = QVBoxLayout(sidebar)
    rail.setContentsMargins(22, 27, 22, 24)
    rail.setSpacing(0)
    brand = QHBoxLayout()
    brand.setSpacing(11)
    logo = label("", "logo")
    logo.setFixedSize(42, 42)
    logo.setPixmap(QPixmap(str(icon_path)).scaled(
        42, 42, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ))
    brand.addWidget(logo)
    brand_text = QVBoxLayout()
    brand_text.setSpacing(1)
    brand_text.addWidget(label("SpeakRAG", "brand"))
    brand_text.addWidget(label("VOICE INTELLIGENCE", "brandCaption"))
    brand.addLayout(brand_text)
    rail.addLayout(brand)
    rail.addSpacing(42)
    rail.addWidget(label("WORKFLOW", "railCaption"))
    rail.addSpacing(12)
    window.nav_buttons = []
    for number, title, detail in (
        ("01", "Capture", "Record or open audio"),
        ("02", "Transcribe", "Turn sound into text"),
        ("03", "Ask & listen", "Ground and speak"),
    ):
        button = QPushButton(f"{number}   {title}\n       {detail}")
        button.setObjectName("navButton")
        button.setProperty("active", False)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(64)
        button.clicked.connect(
            lambda _checked=False, index=len(window.nav_buttons): window.tabs.setCurrentIndex(index)
        )
        rail.addWidget(button)
        rail.addSpacing(7)
        window.nav_buttons.append(button)
    rail.addStretch()
    rail.addWidget(label("LOCAL AUDIO  ·  GROUNDED ANSWERS", "railCaption", True))
    rail.addSpacing(9)
    rail.addWidget(label(
        "Your recordings and voice models stay on this computer. "
        "Answer generation uses OpenRouter.", "railNote", True,
    ))
    root.addWidget(sidebar)

    workspace = QWidget()
    workspace.setObjectName("workspace")
    main = QVBoxLayout(workspace)
    main.setContentsMargins(32, 24, 32, 22)
    main.setSpacing(16)
    root.addWidget(workspace, stretch=1)

    top = QHBoxLayout()
    window.content_overline = label("01 / CAPTURE", "eyebrow")
    top.addWidget(window.content_overline)
    top.addStretch()
    window.step_badge = label("STEP 1 OF 3", "stepBadge")
    top.addWidget(window.step_badge)
    main.addLayout(top)
    window.content_heading = label("Make the question audible.", "heading")
    main.addWidget(window.content_heading)
    window.content_description = label(
        "Record a short question or open a WAV file. Inspect the signal before transcription.",
        "subheading", True,
    )
    main.addWidget(window.content_description)

    window.tabs = QStackedWidget()
    window.tabs.setObjectName("pages")
    main.addWidget(window.tabs, stretch=1)

    capture = QWidget()
    capture_row = QHBoxLayout(capture)
    capture_row.setContentsMargins(0, 0, 0, 0)
    capture_row.setSpacing(18)
    controls, left = panel(capture_row)
    controls.setFixedWidth(294)
    left.addWidget(label("INPUT / 01", "eyebrow"))
    left.addWidget(label("Audio source", "sectionTitle"))
    left.addWidget(label("Keep the clip short and speak clearly.", "muted", True))
    left.addSpacing(4)
    window.input_device = field(left, "MICROPHONE", QComboBox())
    window.output_device = field(left, "PLAYBACK DEVICE", QComboBox())
    window.rate = field(left, "SAMPLE RATE", QComboBox())
    for title, value in (
        ("Device native rate", None), ("16,000 Hz", 16_000),
        ("44,100 Hz", 44_100), ("48,000 Hz", 48_000),
    ):
        window.rate.addItem(title, value)
    settings = QHBoxLayout()
    settings.setSpacing(9)
    duration = QVBoxLayout()
    window.seconds = QDoubleSpinBox()
    window.seconds.setRange(1, 60)
    window.seconds.setValue(5)
    window.seconds.setSingleStep(1)
    window.seconds.setSuffix(" sec")
    field(duration, "MAX LENGTH", window.seconds)
    settings.addLayout(duration)
    channels = QVBoxLayout()
    window.channels = QComboBox()
    window.channels.addItem("Mono", 1)
    window.channels.addItem("Stereo", 2)
    field(channels, "CHANNELS", window.channels)
    settings.addLayout(channels)
    left.addLayout(settings)
    left.addSpacing(4)
    window.record_button = QPushButton("●   Record question")
    window.record_button.setObjectName("primaryButton")
    window.record_button.clicked.connect(window._record)
    left.addWidget(window.record_button)
    window.open_button = QPushButton("Open a WAV file")
    window.open_button.clicked.connect(window._open_file)
    left.addWidget(window.open_button)
    window.play_button = QPushButton("▶   Play current audio")
    window.play_button.setEnabled(False)
    window.play_button.clicked.connect(window._play)
    left.addWidget(window.play_button)
    window.stop_button = QPushButton("■   Stop audio")
    window.stop_button.setObjectName("stopButton")
    window.stop_button.setEnabled(False)
    window.stop_button.clicked.connect(window._stop)
    left.addWidget(window.stop_button)
    left.addStretch()
    window.refresh_button = QPushButton("↻   Refresh devices")
    window.refresh_button.setObjectName("textButton")
    window.refresh_button.clicked.connect(window._refresh_devices)
    left.addWidget(window.refresh_button)

    signal_column = QVBoxLayout()
    signal_column.setSpacing(14)
    capture_row.addLayout(signal_column, stretch=1)
    signal_frame, signal = panel(signal_column)
    signal_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    signal_head = QHBoxLayout()
    title_stack = QVBoxLayout()
    title_stack.setSpacing(2)
    title_stack.addWidget(label("SIGNAL MONITOR", "eyebrow"))
    title_stack.addWidget(label("Waveform & spectrum", "sectionTitle"))
    signal_head.addLayout(title_stack)
    signal_head.addStretch()
    window.export_button = QPushButton("Export plot")
    window.export_button.setObjectName("textButton")
    window.export_button.setEnabled(False)
    window.export_button.clicked.connect(window._export_plot)
    signal_head.addWidget(window.export_button, alignment=Qt.AlignmentFlag.AlignTop)
    signal.addLayout(signal_head)
    window.plot_label = label(
        "No waveform yet\nRecord a question or open a WAV file to inspect its signal.",
        "plotPlaceholder", True,
    )
    window.plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.plot_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    window.plot_label.setMinimumHeight(220)
    window.plot_label.setMaximumHeight(300)
    signal.addWidget(window.plot_label)
    window.metric_widget = QWidget()
    grid = QGridLayout(window.metric_widget)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(8)
    window.metrics = {}
    for index, title in enumerate((
        "DURATION", "SAMPLE RATE", "PEAK LEVEL", "AVERAGE LEVEL", "CLIPPING", "SILENCE"
    )):
        card, value = metric_card(title)
        window.metrics[title] = value
        grid.addWidget(card, index // 3, index % 3)
    signal.addWidget(window.metric_widget)
    window.capture_next_button = QPushButton("Continue to transcription  →")
    window.capture_next_button.setObjectName("nextButton")
    window.capture_next_button.setEnabled(False)
    window.capture_next_button.clicked.connect(lambda: window.tabs.setCurrentIndex(1))
    signal_column.addWidget(window.capture_next_button)
    signal_column.addStretch()
    window.tabs.addWidget(page(capture))

    transcript = QWidget()
    transcript_body = QVBoxLayout(transcript)
    transcript_body.setContentsMargins(0, 0, 0, 0)
    transcript_body.setSpacing(14)
    transcribe_frame, transcribe = panel(transcript_body, "featurePanel")
    transcribe.addWidget(label("RECOGNITION / 02", "eyebrow"))
    transcribe.addWidget(label("From voice to a usable question", "sectionTitle"))
    transcribe.addWidget(label(
        "Choose an ASR model, transcribe the current WAV, then review the words before retrieval.",
        "muted", True,
    ))
    asr_controls = QHBoxLayout()
    window.asr_model = QComboBox()
    window.asr_model.addItem("base.en · English", "base.en")
    window.asr_model.addItem("tiny.en · faster English", "tiny.en")
    window.asr_model.addItem("base · multilingual", "base")
    asr_controls.addWidget(window.asr_model, stretch=1)
    window.transcribe_button = QPushButton("Transcribe WAV")
    window.transcribe_button.setObjectName("primaryButton")
    window.transcribe_button.setEnabled(False)
    window.transcribe_button.clicked.connect(window._transcribe)
    asr_controls.addWidget(window.transcribe_button)
    transcribe.addLayout(asr_controls)
    result_frame, result = panel(transcript_body)
    result_head = QHBoxLayout()
    result_head.addWidget(label("TRANSCRIPT", "eyebrow"))
    result_head.addStretch()
    window.copy_button = QPushButton("Copy text")
    window.copy_button.setObjectName("textButton")
    window.copy_button.setEnabled(False)
    window.copy_button.clicked.connect(window._copy_transcript)
    result_head.addWidget(window.copy_button)
    result.addLayout(result_head)
    window.transcript_meta = label("Choose an audio file, then transcribe it.", "muted", True)
    result.addWidget(window.transcript_meta)
    window.transcript_text = QPlainTextEdit()
    window.transcript_text.setReadOnly(True)
    window.transcript_text.setPlaceholderText("Recognised speech will appear here.")
    window.transcript_text.setMinimumHeight(180)
    result.addWidget(window.transcript_text, stretch=1)
    result.addWidget(label("TIMESTAMPED SEGMENTS", "fieldLabel"))
    window.segment_text = QPlainTextEdit()
    window.segment_text.setObjectName("sourceText")
    window.segment_text.setReadOnly(True)
    window.segment_text.setMaximumHeight(90)
    window.segment_text.setPlaceholderText("No segments yet.")
    result.addWidget(window.segment_text)
    window.transcript_to_ask_button = QPushButton("Use transcript as question  →")
    window.transcript_to_ask_button.setObjectName("nextButton")
    window.transcript_to_ask_button.setEnabled(False)
    window.transcript_to_ask_button.clicked.connect(window._use_transcript)
    transcript_body.addWidget(window.transcript_to_ask_button)
    window.tabs.addWidget(page(transcript))

    handbook = QWidget()
    handbook_body = QVBoxLayout(handbook)
    handbook_body.setContentsMargins(0, 0, 0, 0)
    handbook_body.setSpacing(14)
    knowledge_frame, knowledge = panel(handbook_body, "featurePanel")
    knowledge_head = QHBoxLayout()
    knowledge_title = QVBoxLayout()
    knowledge_title.setSpacing(2)
    knowledge_title.addWidget(label("RETRIEVAL / 03", "eyebrow"))
    knowledge_title.addWidget(label("Ask the handbook", "sectionTitle"))
    knowledge_head.addLayout(knowledge_title)
    knowledge_head.addStretch()
    window.prepare_handbook_button = QPushButton("Prepare handbook")
    window.prepare_handbook_button.clicked.connect(window._prepare_handbook)
    knowledge_head.addWidget(window.prepare_handbook_button)
    knowledge.addLayout(knowledge_head)
    window.handbook_meta = label(
        "Index the official Hyundai IONIQ 5 manual once to search it locally.",
        "muted", True,
    )
    knowledge.addWidget(window.handbook_meta)
    window.handbook_query = QLineEdit()
    window.handbook_query.setPlaceholderText("What would you like to know?")
    window.handbook_query.returnPressed.connect(lambda: window._handbook_job("ask"))
    knowledge.addWidget(window.handbook_query)
    actions = QHBoxLayout()
    window.use_transcript_button = QPushButton("Use transcript")
    window.use_transcript_button.clicked.connect(window._use_transcript)
    actions.addWidget(window.use_transcript_button)
    actions.addStretch()
    window.search_handbook_button = QPushButton("Search pages")
    window.search_handbook_button.clicked.connect(lambda: window._handbook_job("search"))
    actions.addWidget(window.search_handbook_button)
    window.ask_handbook_button = QPushButton("Generate answer  →")
    window.ask_handbook_button.setObjectName("primaryButton")
    window.ask_handbook_button.clicked.connect(lambda: window._handbook_job("ask"))
    actions.addWidget(window.ask_handbook_button)
    knowledge.addLayout(actions)

    answer_frame, answer = panel(handbook_body)
    answer.addWidget(label("GROUNDED ANSWER", "eyebrow"))
    window.handbook_answer = QPlainTextEdit()
    window.handbook_answer.setObjectName("answerText")
    window.handbook_answer.setReadOnly(True)
    window.handbook_answer.setPlaceholderText("Your answer will appear here with source markers.")
    window.handbook_answer.setMinimumHeight(100)
    answer.addWidget(window.handbook_answer)
    speech = QHBoxLayout()
    window.tts_voice = QComboBox()
    speech.addWidget(window.tts_voice, stretch=2)
    window.tts_rate = QComboBox()
    window.tts_rate.addItem("Slow", 1.2)
    window.tts_rate.addItem("Normal", 1.0)
    window.tts_rate.addItem("Fast", 0.85)
    window.tts_rate.setCurrentIndex(1)
    speech.addWidget(window.tts_rate, stretch=1)
    window.tts_output_device = QComboBox()
    speech.addWidget(window.tts_output_device, stretch=2)
    window.speak_answer_button = QPushButton("▶   Speak answer")
    window.speak_answer_button.setObjectName("voiceButton")
    window.speak_answer_button.setEnabled(False)
    window.speak_answer_button.clicked.connect(window._speak_answer)
    speech.addWidget(window.speak_answer_button)
    answer.addLayout(speech)
    sources_frame, sources = panel(handbook_body)
    sources.addWidget(label("SOURCE PASSAGES  ·  PDF PAGE REFERENCES", "eyebrow"))
    window.handbook_sources = QPlainTextEdit()
    window.handbook_sources.setObjectName("sourceText")
    window.handbook_sources.setReadOnly(True)
    window.handbook_sources.setPlaceholderText("Retrieved handbook passages will appear here.")
    window.handbook_sources.setMinimumHeight(140)
    sources.addWidget(window.handbook_sources)
    window.tabs.addWidget(page(handbook))
    window.tabs.currentChanged.connect(window._tab_changed)
    window._refresh_handbook_state()

    status = QFrame()
    status.setObjectName("statusPanel")
    status_row = QHBoxLayout(status)
    status_row.setContentsMargins(16, 10, 16, 10)
    status_row.setSpacing(14)
    status_row.addWidget(label("●", "statusDot"))
    status_text = QVBoxLayout()
    status_text.setSpacing(3)
    window.status = label("Ready. Record or open audio to begin.", "statusText", True)
    status_text.addWidget(window.status)
    window.file_label = label("NO FILE SELECTED", "fileLabel")
    window.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    status_text.addWidget(window.file_label)
    status_row.addLayout(status_text, stretch=1)
    window.global_stop_button = QPushButton("■   Stop")
    window.global_stop_button.setObjectName("stopButton")
    window.global_stop_button.setEnabled(False)
    window.global_stop_button.clicked.connect(window._stop)
    status_row.addWidget(window.global_stop_button)
    window.progress = QProgressBar()
    window.progress.setFixedWidth(110)
    window.progress.setRange(0, 100)
    window.progress.setValue(0)
    window.progress.setTextVisible(False)
    status_row.addWidget(window.progress)
    main.addWidget(status)

    window.setStyleSheet(STYLE)
    window._tab_changed(0)


STYLE = """
QWidget#shell, QWidget#workspace, QStackedWidget#pages, QScrollArea#pageScroll {
    background: #0b1116; color: #eef1e9; font-family: 'Segoe UI'; font-size: 13px;
}
QScrollArea#pageScroll > QWidget > QWidget { background: #0b1116; }
QFrame#sidebar { background: #111a20; border-right: 1px solid #28363b; }
QLabel#brand { font-size: 22px; font-weight: 800; color: #f5f1e8; }
QLabel#brandCaption, QLabel#railCaption, QLabel#fieldLabel, QLabel#metricCaption,
QLabel#fileLabel, QLabel#eyebrow { color: #a6b4aa; font-size: 10px; font-weight: 700;
    letter-spacing: 1.3px; }
QLabel#railNote { color: #829395; font-size: 12px; line-height: 1.4; }
QLabel#eyebrow { color: #d8c49a; }
QLabel#heading { color: #f6f2e9; font-size: 31px; font-weight: 700; }
QLabel#subheading { color: #9eb0ad; font-size: 13px; }
QLabel#stepBadge { color: #d8c49a; background: #222620; border: 1px solid #505039;
    border-radius: 12px; padding: 8px 13px; font-size: 10px; font-weight: 800; }
QLabel#sectionTitle { color: #f6f2e9; font-size: 19px; font-weight: 700; }
QLabel#muted { color: #91a4a2; font-size: 12px; }
QFrame#panel, QFrame#featurePanel { background: #151f25; border: 1px solid #2a3940;
    border-radius: 16px; }
QFrame#featurePanel { background: #1a2628; border-color: #3b4c47; }
QFrame#metricCard { background: #1b292f; border: 1px solid #2d4248; border-radius: 10px; }
QLabel#metricValue { color: #f4f1e7; font-size: 20px; font-weight: 700; }
QLabel#plotPlaceholder { color: #839a9b; background: #10191f; border: 1px dashed #34505a;
    border-radius: 11px; font-size: 13px; }
QFrame#statusPanel { background: #131d23; border: 1px solid #2b3b42; border-radius: 11px; }
QLabel#statusDot { color: #bfe6c0; font-size: 16px; }
QLabel#statusText { color: #d4ded9; font-size: 12px; }
QLabel#statusText[error="true"] { color: #f4a895; }
QComboBox, QDoubleSpinBox, QLineEdit { background: #0e181e; color: #edf1eb;
    border: 1px solid #3a5158; border-radius: 8px; padding: 9px 11px; min-height: 20px; }
QComboBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border-color: #77948a; }
QComboBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border-color: #d9c99f; }
QComboBox QAbstractItemView { background: #19262d; color: #eef1e9;
    selection-background-color: #3a584f; }
QPlainTextEdit { background: #101a20; color: #e7eee9; border: 1px solid #344950;
    border-radius: 9px; padding: 14px; font-family: 'Segoe UI'; font-size: 14px; }
QPlainTextEdit#answerText { color: #f6f2e8; font-size: 15px; }
QPlainTextEdit#sourceText { color: #c1d2cf; font-family: 'Consolas'; font-size: 11px; }
QPushButton { background: #26363d; color: #e6eee9; border: 1px solid #415960;
    border-radius: 8px; padding: 10px 14px; font-size: 12px; font-weight: 650; }
QPushButton:hover { background: #344b51; border-color: #688078; }
QPushButton:pressed { background: #21343b; }
QPushButton:disabled { background: #1a282e; color: #718783; border-color: #2b4147; }
QPushButton#primaryButton { color: #17221c; background: #d6eab9; border: 1px solid #d6eab9;
    font-weight: 800; }
QPushButton#primaryButton:hover { background: #e8f5d4; border-color: #e8f5d4; }
QPushButton#primaryButton:disabled { background: #4e6555; color: #9fb4a1; border-color: #4e6555; }
QPushButton#voiceButton { background: #dfc69b; color: #231f19; border: 1px solid #dfc69b;
    font-weight: 800; }
QPushButton#voiceButton:hover { background: #f2d9a9; }
QPushButton#voiceButton:disabled { background: #6d634f; color: #b0a486; border-color: #6d634f; }
QPushButton#navButton { background: transparent; color: #9badab; border: 1px solid transparent;
    border-left: 3px solid transparent; border-radius: 7px; text-align: left;
    padding: 9px 13px; font-size: 13px; font-weight: 650; }
QPushButton#navButton:hover { background: #1c2c32; color: #e8eee6; }
QPushButton#navButton[active="true"] { background: #25352f; color: #eaf3dc;
    border-left-color: #d6eab9; }
QPushButton#nextButton { background: #1f312c; color: #d8efcb; border-color: #4a6a55;
    text-align: right; }
QPushButton#nextButton:hover { background: #2b4538; }
QPushButton#nextButton:disabled { background: #1b2b29; color: #718e7d; border-color: #31483a; }
QPushButton#textButton { background: transparent; color: #d8c49a; border: 0; padding: 7px; }
QPushButton#textButton:hover { color: #f3ddb0; }
QPushButton#stopButton { background: transparent; color: #d1a99c; border-color: #664e4b; }
QPushButton#stopButton:hover { background: #3b2928; }
QProgressBar { background: #24343b; border: 0; border-radius: 4px; height: 7px; }
QProgressBar::chunk { background: #d6eab9; border-radius: 4px; }
QScrollBar:vertical { background: #101a20; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #40545a; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
