from __future__ import annotations

import html
import json
import threading
from dataclasses import replace
from typing import ClassVar

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
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

from . import __version__
from .agent import Agent
from .config import Settings
from .local_models import OllamaClient, OllamaInstaller
from .providers import ModelProvider
from .theme import APP_STYLE, CHAT_STYLE
from .tools import ToolRunner
from .updater import ReleaseInfo, UpdateClient


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


class OllamaInstallWorker(QObject):
    progress = Signal(str, int)
    finished = Signal(object)
    failed = Signal(str)

    @Slot()
    def run(self):
        try:
            path = OllamaInstaller.download(
                lambda status, percent: self.progress.emit(status, percent)
            )
            self.finished.emit(path)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class UpdateCheckWorker(QObject):
    available = Signal(object)
    current = Signal()
    failed = Signal(str)

    @Slot()
    def run(self):
        try:
            release = UpdateClient().check(__version__)
            if release:
                self.available.emit(release)
            else:
                self.current.emit()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class UpdateDownloadWorker(QObject):
    progress = Signal(str, int)
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, release: ReleaseInfo):
        super().__init__()
        self.release = release

    @Slot()
    def run(self):
        try:
            path = UpdateClient().download(
                self.release, lambda status, percent: self.progress.emit(status, percent)
            )
            self.ready.emit(path)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class LocalModelsDialog(QDialog):
    RECOMMENDED: ClassVar[list[str]] = [
        "qwen2.5vl:7b",
        "gemma3:12b",
        "llama3.2-vision:11b",
        "qwen3:8b",
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
        self.install_ollama = QPushButton("Install Ollama")
        self.refresh = QPushButton("Refresh installed models")
        self.installed = QTextBrowser()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.note = QLabel(
            "Downloads are handled by Ollama running on this PC. Vision-capable models are recommended because the agent uses screenshots."
        )
        self.note.setWordWrap(True)
        self.download.clicked.connect(self._pull)
        self.install_ollama.clicked.connect(self._install_runtime)
        self.refresh.clicked.connect(self._refresh)
        row = QHBoxLayout()
        row.addWidget(self.model, 1)
        row.addWidget(self.download)
        layout = QVBoxLayout(self)
        layout.addWidget(self.note)
        runtime_row = QHBoxLayout()
        runtime_row.addWidget(QLabel("Local runtime:"))
        runtime_row.addStretch()
        runtime_row.addWidget(self.install_ollama)
        layout.addLayout(runtime_row)
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

    @Slot()
    def _install_runtime(self):
        if self.thread:
            return
        answer = QMessageBox.question(
            self,
            "Download Ollama",
            "Download the official Ollama installer from ollama.com? The app will verify its Windows digital signature before it can be launched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.install_ollama.setEnabled(False)
        self.progress.setValue(0)
        self.thread = QThread(self)
        worker = OllamaInstallWorker()
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.finished.connect(self._installer_ready)
        worker.failed.connect(self._pull_failed)
        worker.finished.connect(self.thread.quit)
        worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(worker.deleteLater)
        self.thread.finished.connect(self._install_thread_done)
        self.thread.start()

    @Slot(object)
    def _installer_ready(self, path):
        self.progress.setValue(100)
        self.progress.setFormat("Ollama installer verified")
        answer = QMessageBox.question(
            self,
            "Launch Ollama installer",
            "The installer has a valid Windows digital signature. Launch it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            OllamaInstaller.launch(path)

    @Slot()
    def _install_thread_done(self):
        thread = self.thread
        self.thread = None
        self.install_ollama.setEnabled(True)
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
        self.update_thread: QThread | None = None
        self.pending_update: ReleaseInfo | None = None
        self.approval = ApprovalBridge()
        self.approval.requested.connect(self._show_approval)
        self.setWindowTitle("Computer Agent")
        self.resize(1040, 720)
        self.setMinimumSize(820, 580)

        self.status = QLabel("●  Ready")
        self.status.setObjectName("statusPill")
        self.chat = QTextBrowser()
        self.chat.setObjectName("activity")
        self.chat.setOpenExternalLinks(True)
        self.chat.document().setDefaultStyleSheet(CHAT_STYLE)
        self._show_welcome()
        self.input = QTextEdit()
        self.input.setObjectName("taskInput")
        self.input.setPlaceholderText("Describe what you want Computer Agent to do…")
        self.input.setMinimumHeight(80)
        self.input.setMaximumHeight(130)
        self.run_button = QPushButton("Run task  →")
        self.run_button.setObjectName("primaryButton")
        self.run_button.setDefault(True)
        self.settings_button = QPushButton("⚙   Settings")
        self.settings_button.setObjectName("navButton")
        self.models_button = QPushButton("◫   Local models")
        self.models_button.setObjectName("navButton")
        self.update_button = QPushButton("↻   Check for updates")
        self.update_button.setObjectName("navButton")
        self.clear_button = QPushButton("Clear activity")
        self.run_button.clicked.connect(self._start)
        self.settings_button.clicked.connect(self._settings)
        self.models_button.clicked.connect(self._models)
        self.update_button.clicked.connect(self._check_updates)
        self.clear_button.clicked.connect(self._clear_activity)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(215)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 22, 18, 18)
        sidebar_layout.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_mark = QLabel("CA")
        brand_mark.setObjectName("brandMark")
        brand_mark.setFixedSize(42, 42)
        brand_name = QLabel("Computer\nAgent")
        brand_name.setObjectName("brandName")
        brand_row.addWidget(brand_mark)
        brand_row.addWidget(brand_name)
        brand_row.addStretch()
        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addSpacing(28)
        section = QLabel("WORKSPACE")
        section.setObjectName("sectionLabel")
        sidebar_layout.addWidget(section)
        sidebar_layout.addWidget(self.models_button)
        sidebar_layout.addWidget(self.settings_button)
        sidebar_layout.addWidget(self.update_button)
        sidebar_layout.addStretch()
        provider_label = QLabel("ACTIVE MODEL")
        provider_label.setObjectName("sectionLabel")
        sidebar_layout.addWidget(provider_label)
        self.provider_card = QLabel()
        self.provider_card.setObjectName("providerCard")
        self.provider_card.setWordWrap(True)
        sidebar_layout.addWidget(self.provider_card)
        safety = QLabel("Move the pointer to the upper-left corner to stop automation.")
        safety.setObjectName("muted")
        safety.setWordWrap(True)
        sidebar_layout.addWidget(safety)

        page_title = QLabel("New task")
        page_title.setObjectName("pageTitle")
        subtitle = QLabel("Ask the agent to work with apps, files, or Windows.")
        subtitle.setObjectName("muted")
        heading_text = QVBoxLayout()
        heading_text.setSpacing(2)
        heading_text.addWidget(page_title)
        heading_text.addWidget(subtitle)
        header = QHBoxLayout()
        header.addLayout(heading_text)
        header.addStretch()
        header.addWidget(self.clear_button)
        header.addWidget(self.status)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(14, 12, 14, 12)
        composer_layout.addWidget(self.input)
        composer_actions = QHBoxLayout()
        approval_note = QLabel("Actions that change your PC require approval")
        approval_note.setObjectName("muted")
        composer_actions.addWidget(approval_note)
        composer_actions.addStretch()
        composer_actions.addWidget(self.run_button)
        composer_layout.addLayout(composer_actions)

        content = QVBoxLayout()
        content.setContentsMargins(28, 24, 28, 24)
        content.setSpacing(14)
        content.addLayout(header)
        content.addWidget(self.chat, 1)
        content.addWidget(composer)
        shell = QHBoxLayout()
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(sidebar)
        shell.addLayout(content, 1)
        root = QWidget()
        root.setObjectName("appRoot")
        root.setLayout(shell)
        self.setCentralWidget(root)
        self._refresh_provider_card()

    def _append(self, label: str, text: str):
        css_class = (
            label.lower()
            if label.lower() in {"user", "agent", "action", "result", "thought", "error"}
            else "result"
        )
        self.chat.append(
            f'<div class="message {css_class}"><div class="label">'
            f'{html.escape(label.upper())}</div><div class="body">'
            f"{html.escape(text)}</div></div>"
        )
        bar = self.chat.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _show_welcome(self):
        self.chat.setHtml(
            '<div class="welcome"><h2>What should we work on?</h2>'
            "<p>Computer Agent can operate Windows, work with files, and use your apps. "
            "You will review actions before they run.</p></div>"
        )

    def _refresh_provider_card(self):
        self.provider_card.setText(f"{self.settings.provider}\n{self.settings.model}")

    @Slot()
    def _clear_activity(self):
        self._show_welcome()

    @Slot()
    def _start(self):
        task = self.input.toPlainText().strip()
        if not task or self.thread:
            return
        if "What should we work on?" in self.chat.toPlainText():
            self.chat.clear()
        self._append("You", task)
        self.input.clear()
        self.run_button.setEnabled(False)
        self.clear_button.setEnabled(False)
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
            self.status.setText(f"●  {text}")
        else:
            self._append(kind.title(), text)

    @Slot(str)
    def _finished(self, result: str):
        self._append("Agent", result)
        self.status.setText("●  Ready")

    @Slot(str)
    def _failed(self, error: str):
        self._append("Error", error)
        self.status.setText("●  Task failed")

    @Slot()
    def _thread_done(self):
        thread = self.thread
        self.thread = None
        self.run_button.setEnabled(True)
        self.clear_button.setEnabled(True)
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
            self.status.setText("●  Ready")
            self._refresh_provider_card()

    @Slot()
    def _models(self):
        LocalModelsDialog(self.settings, self).exec()

    @Slot()
    def _check_updates(self):
        if self.update_thread:
            return
        self.update_button.setEnabled(False)
        self.status.setText("●  Checking for updates")
        self.update_thread = QThread(self)
        worker = UpdateCheckWorker()
        worker.moveToThread(self.update_thread)
        self.update_thread.started.connect(worker.run)
        worker.available.connect(self._update_available)
        worker.current.connect(self._already_current)
        worker.failed.connect(self._update_failed)
        worker.available.connect(self.update_thread.quit)
        worker.current.connect(self.update_thread.quit)
        worker.failed.connect(self.update_thread.quit)
        self.update_thread.finished.connect(worker.deleteLater)
        self.update_thread.finished.connect(self._update_thread_done)
        self.update_thread.start()

    @Slot(object)
    def _update_available(self, release: ReleaseInfo):
        answer = QMessageBox.question(
            self,
            "Update available",
            f"Computer Agent {release.version} is available. Download and install it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.pending_update = release
            self.status.setText("●  Preparing update")
        else:
            self.status.setText("●  Ready")

    @Slot()
    def _already_current(self):
        self.status.setText("●  Up to date")
        QMessageBox.information(
            self, "No updates", f"Computer Agent {__version__} is the latest version."
        )

    @Slot(str)
    def _update_failed(self, error: str):
        self.status.setText("●  Update check failed")
        QMessageBox.warning(self, "Update unavailable", error)

    @Slot()
    def _update_thread_done(self):
        thread = self.update_thread
        self.update_thread = None
        self.update_button.setEnabled(True)
        if thread:
            thread.deleteLater()
        if self.pending_update:
            release = self.pending_update
            self.pending_update = None
            self._download_update(release)

    def _download_update(self, release: ReleaseInfo):
        self.update_button.setEnabled(False)
        self.update_thread = QThread(self)
        worker = UpdateDownloadWorker(release)
        worker.moveToThread(self.update_thread)
        self.update_thread.started.connect(worker.run)
        worker.progress.connect(self._update_progress)
        worker.ready.connect(self._update_ready)
        worker.failed.connect(self._update_failed)
        worker.ready.connect(self.update_thread.quit)
        worker.failed.connect(self.update_thread.quit)
        self.update_thread.finished.connect(worker.deleteLater)
        self.update_thread.finished.connect(self._update_thread_done)
        self.update_thread.start()

    @Slot(str, int)
    def _update_progress(self, status: str, percent: int):
        self.status.setText(f"●  {status} {percent}%")

    @Slot(object)
    def _update_ready(self, path):
        self.status.setText("●  Update verified")
        answer = QMessageBox.question(
            self,
            "Install update",
            "The update passed SHA-256 verification. Launch the installer now? Computer Agent will remain open until you close it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            UpdateClient.launch(path)


def run_app() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
