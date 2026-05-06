from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout, QWidget

from modules.attendance.models import Employee, Team


def team_to_label(team: Team) -> str:
    return "Tổ thổi" if team == Team.BLOW else "Tổ cắt"


def label_to_team(label: str) -> Team:
    return Team.CUT if label == "Tổ cắt" else Team.BLOW


def employee_status_label(is_active: bool) -> str:
    return "Đang sử dụng" if is_active else "Ngừng sử dụng"


class EmployeeDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, title: str, employee: Employee | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(380, 180)

        self.name_input = QLineEdit(employee.name if employee is not None else "")
        self.team_combo = QComboBox()
        self.team_combo.addItems(["Tổ thổi", "Tổ cắt"])
        if employee is not None:
            self.team_combo.setCurrentText(team_to_label(employee.team))
        self.active_checkbox = QCheckBox("Đang sử dụng")
        self.active_checkbox.setChecked(True if employee is None else employee.is_active)

        form = QFormLayout()
        form.addRow("Tên", self.name_input)
        form.addRow("Tổ", self.team_combo)
        form.addRow("", self.active_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name_input.text(),
            "team": label_to_team(self.team_combo.currentText()),
            "is_active": self.active_checkbox.isChecked(),
        }
