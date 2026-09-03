from __future__ import annotations

import json
import threading
from dataclasses import replace
from typing import ClassVar

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .agent import Agent
from .config import Settings
from .local_models import OllamaClient
from .providers import ModelProvider
from .tools import ToolRunner


class ApprovalRequest:
    def __init__(self):
        self.event = threading.Event()
        self.allowed = False


class ApprovalBridge(QObject):
    requested = Signal(str, object)

    def ask(self, name: str, arguments: dict) -> bool:
        request = ApprovalRequest()
        self.requested.emit(
            f"Allow action '{name}'?\n\n{json.dumps(arguments, indent=2, ensure_ascii=False)}",
            request,
        )
        request.event.wait()
        return request.allowed


class AgentWorker(QObject):
    event = Signal(str, str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, task: str, settings: Settings, approval: ApprovalBridge):
        super().__init__()
        self.task = task
        self.settings = settings
        self.approval = approval

    @Slot()
    def run(self):
        try:
            provider = ModelProvider(self.settings)
            tools = ToolRunner(self.approval.ask, self.settings.auto_approve)
            result = Agent(provider, tools, self.settings.max_steps).run(
                self.task, lambda kind, text: self.event.emit(kind, text)
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class PullWorker(QObject):
    progress = Signal(str, int)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, base_url: str, model: str):
        super().__init__()
        self.base_url = base_url
        self.model = model

    @Slot()
    def run(self):
        try:
            OllamaClient(self.base_url).pull(
                self.model, lambda status, percent: self.progress.emit(status, percent)
            )
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class LocalModelsDialog(QDialog):
    RECOMMENDED: ClassVar[list[str]] = [
        "qwen3:8b",
        "qwen2.5vl:7b",
        "gemma3:12b",
        "llama3.2-vision:11b",
        "mistral-small3.1:24b",
    ]

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.thread: QThread | None = None
        self.setWindowTitle("Local model downloader")
        self.resize(620, 440)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(self.RECOMMENDED)
        self.download = QPushButton("Download with Ollama")
        self.refresh = QPushButton("Refresh installed models")
        self.installed = QTextBrowser()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.note = QLabel(
            "Downloads are handled by Ollama running on this PC. Vision-capable models are recommended because the agent uses screenshots."
        )
        self.note.setWordWrap(True)
        self.download.clicked.connect(self._pull)
        self.refresh.clicked.connect(self._refresh)
        row = QHBoxLayout()
        row.addWidget(self.model, 1)
        row.addWidget(self.download)
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        layout.addLayout(row)
        layout.addWidget(self.progress)
        layout.addWidget(self.refresh)
        layout.addWidget(self.installed, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self._refresh()

    @Slot()
    def _refresh(self):
        try:
            models = OllamaClient(self.settings.base_url).installed()
            lines = [
                f"{item.get('name', 'unknown')}  —  {int(item.get('size') or 0) / 1_000_000_000:.1f} GB"
                for item in models
            ]
            self.installed.setPlainText("\n".join(lines) if lines else "No models installed.")
        except Exception as exc:
            self.installed.setPlainText(
                f"Could not reach Ollama: {exc}\n\nStart Ollama, then click Refresh."
            )

    @Slot()
    def _pull(self):
        model = self.model.currentText().strip()
        if not model or self.thread:
            return
        self.download.setEnabled(False)
        self.progress.setValue(0)
        self.thread = QThread(self)
        worker = PullWorker(self.settings.base_url, model)
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.finished.connect(self._pull_finished)
        worker.failed.connect(self._pull_failed)
        worker.finished.connect(self.thread.quit)
        worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(worker.deleteLater)
        self.thread.finished.connect(self._pull_thread_done)
        self.thread.start()

    @Slot(str, int)
    def _progress(self, status: str, percent: int):
        self.progress.setFormat(f"{status} — %p%")
        self.progress.setValue(percent)

    @Slot()
    def _pull_finished(self):
        self.progress.setValue(100)
        self.progress.setFormat("Download complete")
        self._refresh()

    @Slot(str)
    def _pull_failed(self, error: str):
        QMessageBox.critical(self, "Download failed", error)

    @Slot()
    def _pull_thread_done(self):
        thread = self.thread
        self.thread = None
        self.download.setEnabled(True)
        if thread:
            thread.deleteLater()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Provider settings")
        self.provider = QComboBox()
        self.provider.addItems(["Ollama", "OpenAI Compatible", "Anthropic"])
        self.provider.setCurrentText(settings.provider)
        self.url = QLineEdit(settings.base_url)
        self.model = QLineEdit(settings.model)
        self.key = QLineEdit(settings.api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.steps = QSpinBox()
        self.steps.setRange(1, 100)
        self.steps.setValue(settings.max_steps)
        self.auto = QCheckBox("Approve input and shell actions for this session")
        self.auto.setChecked(settings.auto_approve)
        form = QFormLayout(self)
        form.addRow("Provider", self.provider)
        form.addRow("Base URL", self.url)
        form.addRow("Model", self.model)
        form.addRow("API key", self.key)
        form.addRow("Maximum steps", self.steps)
        form.addRow("Auto-approval", self.auto)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def apply(self, settings: Settings) -> Settings:
        return replace(
            settings,
            provider=self.provider.currentText(),
            base_url=self.url.text().strip(),
            model=self.model.text().strip(),
            api_key=self.key.text().strip(),
            max_steps=self.steps.value(),
            auto_approve=self.auto.isChecked(),
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.thread: QThread | None = None
        self.approval = ApprovalBridge()
        self.approval.requested.connect(self._show_approval)
        self.setWindowTitle("Computer Agent")
        self.resize(900, 680)

        title = QLabel("Computer Agent")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.status = QLabel("Ready — actions require approval")
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        self.input = QTextEdit()
        self.input.setPlaceholderText("Tell the agent what to do on this PC…")
        self.input.setMaximumHeight(100)
        self.run_button = QPushButton("Run task")
        self.settings_button = QPushButton("Settings")
        self.models_button = QPushButton("Local models")
        self.run_button.clicked.connect(self._start)
        self.settings_button.clicked.connect(self._settings)
        self.models_button.clicked.connect(self._models)

        buttons = QHBoxLayout()
        buttons.addWidget(self.settings_button)
        buttons.addWidget(self.models_button)
        buttons.addStretch()
        buttons.addWidget(self.run_button)
        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self.status)
        layout.addWidget(self.chat, 1)
        layout.addWidget(self.input)
        layout.addLayout(buttons)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)

    def _append(self, label: str, text: str):
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.chat.append(f"<b>{label}</b><br><pre style='white-space:pre-wrap'>{safe}</pre>")

    @Slot()
    def _start(self):
        task = self.input.toPlainText().strip()
        if not task or self.thread:
            return
        self._append("You", task)
        self.input.clear()
        self.run_button.setEnabled(False)
        self.thread = QThread(self)
        worker = AgentWorker(task, replace(self.settings), self.approval)
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.event.connect(self._on_event)
        worker.finished.connect(self._finished)
        worker.failed.connect(self._failed)
        worker.finished.connect(self.thread.quit)
        worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(worker.deleteLater)
        self.thread.finished.connect(self._thread_done)
        self.thread.start()

    @Slot(str, str)
    def _on_event(self, kind: str, text: str):
        if kind == "status":
            self.status.setText(text)
        else:
            self._append(kind.title(), text)

    @Slot(str)
    def _finished(self, result: str):
        self._append("Agent", result)
        self.status.setText("Ready")

    @Slot(str)
    def _failed(self, error: str):
        self._append("Error", error)
        self.status.setText("Task failed")

    @Slot()
    def _thread_done(self):
        thread = self.thread
        self.thread = None
        self.run_button.setEnabled(True)
        if thread:
            thread.deleteLater()

    @Slot(str, object)
    def _show_approval(self, message: str, request: ApprovalRequest):
        answer = QMessageBox.question(
            self,
            "Computer Agent approval",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        request.allowed = answer == QMessageBox.StandardButton.Yes
        request.event.set()

    @Slot()
    def _settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings = dialog.apply(self.settings)
            self.settings.save()
            self.status.setText(f"Ready — {self.settings.provider}: {self.settings.model}")

    @Slot()
    def _models(self):
        LocalModelsDialog(self.settings, self).exec()


def run_app() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()
