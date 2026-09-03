APP_STYLE = """
* {
    font-family: "Segoe UI";
    font-size: 10pt;
    color: #e5e7eb;
}
QMainWindow, QDialog, QWidget#appRoot { background: #0b1020; }
QFrame#sidebar {
    background: #0f172a;
    border-right: 1px solid #243047;
}
QFrame#composer, QFrame#settingsCard {
    background: #111827;
    border: 1px solid #29344a;
    border-radius: 12px;
}
QLabel#brandMark {
    background: #6d5dfc;
    color: white;
    border-radius: 10px;
    font-size: 15pt;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}
QLabel#brandName { font-size: 13pt; font-weight: 700; color: white; }
QLabel#pageTitle { font-size: 18pt; font-weight: 700; color: white; }
QLabel#muted, QLabel#sectionLabel { color: #8b9bb4; }
QLabel#sectionLabel { font-size: 9pt; font-weight: 600; }
QLabel#statusText { color: #8fa2c1; padding: 4px; }
QLabel#providerCard {
    background: #151f34;
    border: 1px solid #29344a;
    border-radius: 9px;
    padding: 10px;
    color: #c8d3e6;
}
QPushButton {
    background: #1b263b;
    border: 1px solid #30405d;
    border-radius: 8px;
    padding: 8px 13px;
    font-weight: 600;
}
QPushButton:hover { background: #243451; border-color: #496083; }
QPushButton:pressed { background: #182238; }
QPushButton:disabled { color: #68758a; background: #151d2c; border-color: #202a3c; }
QPushButton#primaryButton {
    background: #6d5dfc;
    border-color: #7c6cff;
    color: white;
    padding: 9px 18px;
}
QPushButton#primaryButton:hover { background: #7c6cff; }
QPushButton#navButton {
    background: transparent;
    border-color: transparent;
    text-align: left;
    padding: 10px 12px;
    color: #b8c4d8;
}
QPushButton#navButton:hover { background: #18243a; color: white; }
QPushButton#newChatButton {
    background: #18243a;
    border-color: #334766;
    text-align: left;
    padding: 10px 12px;
}
QListWidget#chatList {
    background: transparent;
    border: none;
    outline: none;
    padding: 0;
}
QListWidget#chatList::item {
    color: #aebbd0;
    border-radius: 7px;
    padding: 9px 10px;
    margin: 1px 0;
}
QListWidget#chatList::item:hover { background: #18243a; color: white; }
QListWidget#chatList::item:selected { background: #202e49; color: white; }
QListWidget#chatList QScrollBar:vertical {
    background: #111a2d;
    width: 9px;
    margin: 2px 0;
    border-radius: 4px;
}
QListWidget#chatList QScrollBar::handle:vertical {
    background: #465674;
    min-height: 32px;
    border-radius: 4px;
}
QListWidget#chatList QScrollBar::handle:vertical:hover { background: #607394; }
QTextBrowser#activity {
    background: transparent;
    border: none;
    padding: 4px;
}
QTextEdit#taskInput {
    background: transparent;
    border: none;
    padding: 4px;
    color: #f8fafc;
    selection-background-color: #6d5dfc;
}
QLineEdit, QComboBox, QSpinBox, QTextBrowser, QTextEdit {
    background: #0d1528;
    border: 1px solid #2a3851;
    border-radius: 7px;
    padding: 7px;
    selection-background-color: #6d5dfc;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
    border-color: #7567f8;
}
QComboBox::drop-down { border: none; width: 24px; }
QProgressBar {
    background: #111827;
    border: 1px solid #2a3851;
    border-radius: 6px;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk { background: #6d5dfc; border-radius: 5px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #33415c; border-radius: 5px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #182238; color: white; border: 1px solid #3b4d6d; padding: 5px; }
"""

CHAT_STYLE = """
body { color: #dbe4f3; font-family: 'Segoe UI'; }
.welcome { color: #94a3b8; text-align: center; margin: 70px 50px; }
.welcome h2 { color: #f8fafc; font-size: 20px; margin-bottom: 8px; }
.message { margin: 10px 4px; padding: 12px 14px; border-radius: 9px; }
.user { background: #1d2850; border: 1px solid #354677; }
.agent { background: #142c2a; border: 1px solid #27514c; }
.action, .result, .thought { background: #111827; border: 1px solid #29344a; }
.error { background: #351a24; border: 1px solid #6e2b3f; }
.label { color: #8fa2c1; font-size: 11px; font-weight: 600; margin-bottom: 5px; }
.body { color: #e7edf7; white-space: pre-wrap; }
"""
