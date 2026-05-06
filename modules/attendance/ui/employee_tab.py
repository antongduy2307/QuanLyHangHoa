from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.exceptions import AppError
from modules.attendance.models import Employee
from modules.attendance.service import AttendanceEmployeeService
from modules.attendance.ui.dialogs import EmployeeDialog, employee_status_label, team_to_label
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class EmployeeManagementTab(QWidget):
    def __init__(self, service: AttendanceEmployeeService) -> None:
        super().__init__()
        self._service = service
        self._employees: list[Employee] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm theo tên nhân viên")
        self.search_input.textChanged.connect(self.reload)

        self.include_inactive_checkbox = QCheckBox("Hiện nhân viên ngừng sử dụng")
        self.include_inactive_checkbox.toggled.connect(self.reload)

        self.add_button = QPushButton("Thêm")
        self.edit_button = QPushButton("Sửa")
        self.delete_button = QPushButton("Xóa")
        self.add_button.clicked.connect(self._open_add_dialog)
        self.edit_button.clicked.connect(self._open_edit_dialog)
        self.delete_button.clicked.connect(self._delete_selected_employee)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tên", "Tổ", "Trạng thái"])
        configure_table_widget(self.table, "attendance.employee.list")
        self.table.itemSelectionChanged.connect(self._update_button_state)
        self.table.itemDoubleClicked.connect(lambda *_args: self._open_edit_dialog())

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.search_input, 1)
        filter_layout.addWidget(self.include_inactive_checkbox)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.add_button)
        action_layout.addWidget(self.edit_button)
        action_layout.addWidget(self.delete_button)
        action_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(filter_layout)
        layout.addLayout(action_layout)
        layout.addWidget(self.table, 1)

        self.reload()

    def reload(self) -> None:
        selected_employee_id = self.selected_employee_id()
        try:
            self._employees = list(
                self._service.list_employees(
                    search_text=self.search_input.text(),
                    include_inactive=self.include_inactive_checkbox.isChecked(),
                )
            )
            self._render_table()
            self._restore_selection(selected_employee_id)
            self._update_button_state()
        except AppError as exc:
            MessageBox.error(self, "Không tải được danh sách nhân viên", str(exc))

    def selected_employee_id(self) -> int | None:
        current_row = self.table.currentRow()
        if current_row < 0:
            return None
        item = self.table.item(current_row, 0)
        if item is None:
            return None
        employee_id = item.data(Qt.ItemDataRole.UserRole)
        return int(employee_id) if employee_id is not None else None

    def _render_table(self) -> None:
        self.table.setRowCount(len(self._employees))
        for row, employee in enumerate(self._employees):
            name_item = QTableWidgetItem(employee.name)
            name_item.setData(Qt.ItemDataRole.UserRole, employee.id)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(team_to_label(employee.team)))
            self.table.setItem(row, 2, QTableWidgetItem(employee_status_label(employee.is_active)))
            if not employee.is_active:
                self._shade_inactive_row(row)

    def _shade_inactive_row(self, row: int) -> None:
        for column in range(self.table.columnCount()):
            item = self.table.item(row, column)
            if item is not None:
                item.setBackground(QColor("#f1f5f9"))
                item.setForeground(QColor("#64748b"))

    def _restore_selection(self, employee_id: int | None) -> None:
        if employee_id is None:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == employee_id:
                self.table.selectRow(row)
                return

    def _selected_employee(self) -> Employee | None:
        employee_id = self.selected_employee_id()
        if employee_id is None:
            return None
        return next((employee for employee in self._employees if employee.id == employee_id), None)

    def _update_button_state(self) -> None:
        has_selection = self.selected_employee_id() is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def _open_add_dialog(self) -> None:
        dialog = EmployeeDialog(self, title="Thêm nhân viên")
        if dialog.exec() != EmployeeDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        try:
            employee = self._service.create_employee(
                name=str(payload["name"]),
                team=payload["team"],
                is_active=bool(payload["is_active"]),
            )
            self.reload()
            self._restore_selection(employee.id)
            MessageBox.info(self, "Thành công", "Đã thêm nhân viên.")
        except AppError as exc:
            MessageBox.warning(self, "Không thêm được nhân viên", str(exc))

    def _open_edit_dialog(self) -> None:
        employee = self._selected_employee()
        if employee is None:
            return
        dialog = EmployeeDialog(self, title="Sửa nhân viên", employee=employee)
        if dialog.exec() != EmployeeDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        try:
            updated = self._service.update_employee(
                employee.id,
                name=str(payload["name"]),
                team=payload["team"],
                is_active=bool(payload["is_active"]),
            )
            self.reload()
            self._restore_selection(updated.id)
            MessageBox.info(self, "Thành công", "Đã cập nhật nhân viên.")
        except AppError as exc:
            MessageBox.warning(self, "Không cập nhật được nhân viên", str(exc))

    def _delete_selected_employee(self) -> None:
        employee = self._selected_employee()
        if employee is None:
            return
        confirmed = QMessageBox.question(
            self,
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa nhân viên '{employee.name}' không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self._service.delete_or_deactivate_employee(employee.id)
            self.reload()
            if result.deleted_without_history:
                MessageBox.info(self, "Thành công", "Đã xóa nhân viên.")
            else:
                MessageBox.info(
                    self,
                    "Đã ngừng sử dụng",
                    "Nhân viên đã có lịch sử chấm công nên hệ thống đã chuyển sang trạng thái ngừng sử dụng.",
                )
        except AppError as exc:
            MessageBox.warning(self, "Không xóa được nhân viên", str(exc))
