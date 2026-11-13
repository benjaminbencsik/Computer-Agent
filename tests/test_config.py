from __future__ import annotations

import json
from dataclasses import replace
from typing import ClassVar

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from . import __version__
from .agent import Agent
from .checkpoints import CheckpointStore
from .config import Settings
from .hardware import HardwareError, HardwareProfile, detect_hardware, recommend_model
from .history import ChatHistory, Conversation
from .local_models import OllamaClient, OllamaInstaller, WslOllamaClient
from .providers import ModelProvider
from .secrets_store import SecretStore
from .theme import APP_STYLE, CHAT_STYLE
from .tools import ToolError, ToolRunner
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

    def __init__(self, task: str, settings: Settings, approval: ApprovalBridge, conversation_id: str):
        super().__init__()
        self.task = task
        self.settings = settings
        self.approval = approval
        self.conversation_id = conversation_id

    @Slot()
    def run(self):
        tools = ToolRunner(
            self.approval.ask,
            self.settings.auto_approve,
            safe_roots=self.settings.safe_roots,
            allow_filesystem=self.settings.filesystem_control,
            allow_wsl=self.settings.wsl_control,
        )
        try:
            runtime_settings = replace(self.settings)
            if runtime_settings.provider == "Ollama":
                runtime_settings = replace(
                    runtime_settings,
                    base_url=OllamaClient(runtime_settings.base_url).ensure_running(),
                )
            elif runtime_settings.provider == "Ollama (WSL)":
                runtime_settings = replace(
                    runtime_settings,
                    base_url=WslOllamaClient().ensure_running(),
                )
            provider = ModelProvider(runtime_settings)
            checkpoints = CheckpointStore(self.conversation_id)
            result = Agent(provider, tools, self.settings.max_steps).run(
                self.task, lambda kind, text: self.event.emit(kind, text), checkpoints=checkpoints
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            tools.close()


class SettingsDialog(QDialog):
    update_requested = Signal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Provider settings")
        self.provider = QComboBox()
        self.provider.addItems(["Ollama", "Ollama (WSL)", "OpenAI Compatible", "Anthropic"])
        self.provider.setCurrentText(settings.provider)
        self.url = QLineEdit(settings.base_url)
        self.model = QLineEdit(settings.model)
        self.key = QLineEdit(settings.api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.provider.currentTextChanged.connect(self._provider_changed)
        self.steps = QSpinBox()
        self.steps.setRange(1, 100)
        self.steps.setValue(settings.max_steps)
        self.auto = QCheckBox("Approve input and shell actions for this session")
        self.auto.setChecked(settings.auto_approve)
        self.native_tools = QCheckBox("Use native tool calling when the model supports it")
        self.native_tools.setChecked(settings.native_tool_calling)
        self.filesystem_control = QCheckBox("Enable filesystem control")
        self.filesystem_control.setChecked(settings.filesystem_control)
        self.wsl_control = QCheckBox("Enable WSL control")
        self.wsl_control.setChecked(settings.wsl_control)
        self.safe_roots = QLineEdit("; ".join(settings.safe_roots))
        self.safe_roots.setPlaceholderText("C:\\Users\\YourName; C:\\Projects; /home/user")
        self.update_channel = QComboBox()
        self.update_channel.addItems(["Stable", "Beta"])
        self.update_channel.setCurrentText(settings.update_channel.capitalize())
        self.local_models = QPushButton("Manage local models")
        self.check_updates = QPushButton("Check for updates")
        self.local_models.clicked.connect(self._open_local_models)
        self.check_updates.clicked.connect(self._request_update)
        form = QFormLayout(self)
        form.addRow("Provider", self.provider)
        form.addRow("Base URL", self.url)
        form.addRow("Model", self.model)
        form.addRow("API key", self.key)
        form.addRow("Maximum steps", self.steps)
        form.addRow("Auto-approval", self.auto)
        form.addRow("Tool calling", self.native_tools)
        form.addRow("Filesystem control", self.filesystem_control)
        form.addRow("WSL control", self.wsl_control)
        form.addRow("Safe roots", self.safe_roots)
        form.addRow("Local AI", self.local_models)
        form.addRow("Update channel", self.update_channel)
        form.addRow("Application", self.check_updates)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self._provider_changed(self.provider.currentText())

    @Slot(str)
    def _provider_changed(self, provider: str):
        self.key.setText(SecretStore.get(provider))
        if provider == "Ollama (WSL)":
            self.url.setText("Auto-detected from WSL")
            self.url.setEnabled(False)
            self.key.setEnabled(False)
        else:
            if not self.url.isEnabled() or self.url.text() == "Auto-detected from WSL":
                self.url.setText("http://localhost:11434/v1" if provider == "Ollama" else "")
            self.url.setEnabled(True)
            self.key.setEnabled(provider not in {"Ollama", "Ollama (WSL)"})

    @Slot()
    def _open_local_models(self):
        LocalModelsDialog(self.apply(self.settings), self).exec()

    @Slot()
    def _request_update(self):
        self.update_requested.emit()
        self.accept()

    def apply(self, settings: Settings) -> Settings:
        roots = [
            part.strip()
            for part in self.safe_roots.text().split(";")
            if part.strip()
        ]
        return replace(
            settings,
            provider=self.provider.currentText(),
            base_url=(
                "http://localhost:11434/v1"
                if self.provider.currentText() == "Ollama (WSL)"
                else self.url.text().strip()
            ),
            model=self.model.text().strip(),
            api_key=self.key.text().strip(),
            max_steps=self.steps.value(),
            auto_approve=self.auto.isChecked(),
            native_tool_calling=self.native_tools.isChecked(),
            filesystem_control=self.filesystem_control.isChecked(),
            wsl_control=self.wsl_control.isChecked(),
            safe_roots=roots,
            update_channel=self.update_channel.currentText().lower(),
        )
