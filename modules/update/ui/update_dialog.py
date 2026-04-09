from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from modules.update.service import UpdateCheckResult


class UpdateDialog(QDialog):
    def __init__(self, result: UpdateCheckResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result = result
        self.selected_action = "later"

        self.setWindowTitle("Cập nhật ứng dụng")
        self.setModal(True)
        self.resize(480, 320)

        layout = QVBoxLayout(self)

        title = QLabel("Đã có phiên bản mới sẵn sàng.")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        if result.is_forced_update:
            forced_label = QLabel("Bản hiện tại đã thấp hơn mức tối thiểu cho phép. Bạn cần cập nhật để tiếp tục dùng an toàn.")
            forced_label.setWordWrap(True)
            forced_label.setStyleSheet("color: #a54b00; font-weight: 600;")
            layout.addWidget(forced_label)

        current_version = QLabel(f"Phiên bản hiện tại: {result.current_version}")
        latest_version = QLabel(f"Phiên bản mới: {result.latest_version or 'Không rõ'}")
        current_version.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        latest_version.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(current_version)
        layout.addWidget(latest_version)

        notes_title = QLabel("Ghi chú phát hành")
        notes_title.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(notes_title)

        notes_text = "\n".join(f"• {note}" for note in result.notes) if result.notes else "• Không có ghi chú phát hành."
        notes_label = QLabel(notes_text)
        notes_label.setWordWrap(True)
        notes_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(notes_label)
        layout.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()

        self._install_button = QPushButton("Cập nhật ngay" if result.is_forced_update else "Tải và cập nhật")
        self._install_button.clicked.connect(self._accept_update)
        button_row.addWidget(self._install_button)

        if result.is_forced_update:
            self._secondary_button = QPushButton("Thoát ứng dụng")
            self._secondary_button.clicked.connect(self._exit_application)
        else:
            self._secondary_button = QPushButton("Để sau")
            self._secondary_button.clicked.connect(self.reject)
        button_row.addWidget(self._secondary_button)

        layout.addLayout(button_row)

    def reject(self) -> None:
        if self._result.is_forced_update:
            return
        self.selected_action = "later"
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._result.is_forced_update:
            event.ignore()
            return
        super().closeEvent(event)

    def _accept_update(self) -> None:
        self.selected_action = "update"
        self.accept()

    def _exit_application(self) -> None:
        self.selected_action = "exit"
        self.done(QDialog.DialogCode.Rejected)
