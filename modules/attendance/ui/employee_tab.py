from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QCheckBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.exceptions import AppError
from modules.attendance.models import Employee
from modules.attendance.service import AttendanceEmployeeService
from modules.attendance.ui.dialogs import EmployeeDialog, employee_status_label, team_to_label
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget
from shared.widgets.table_selection_mode import TableSelectionModeController


class EmployeeManagementTab(QWidget):
    employees_changed = pyqtSignal()

    def __init__(self, service: AttendanceEmployeeService) -> None:
        super().__init__()
        self._service = service
        self._employees: list[Employee] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm theo tên nhân viên")
        self.search_input.textChanged.connect(self._handle_filter_changed)

        self.include_inactive_checkbox = QCheckBox("Hiện nhân viên ngừng sử dụng")
        self.include_inactive_checkbox.toggled.connect(self._handle_filter_changed)

        self.add_button = QPushButton("Thêm")
        self.edit_button = QPushButton("Sửa")
        self.delete_button = QPushButton("Xóa")
        self.add_button.clicked.connect(self._open_add_dialog)
        self.edit_button.clicked.connect(self._open_edit_dialog)
        self.delete_button.clicked.connect(self._enter_delete_selection_mode)

        self.delete_selected_button = QPushButton("Xóa đã chọn")
        self.cancel_delete_button = QPushButton("Hủy")
        self.selected_count_label = QLabel("Đã chọn: 0")
        self.delete_selected_button.clicked.connect(self._delete_selected_employees)
        self.cancel_delete_button.clicked.connect(self._exit_delete_selection_mode)
        self.delete_selected_button.hide()
        self.cancel_delete_button.hide()
        self.selected_count_label.hide()

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tên", "Tổ", "Trạng thái"])
        configure_table_widget(self.table, "attendance.employee.list")
        self.table.itemSelectionChanged.connect(self._update_button_state)
        self.table.itemDoubleClicked.connect(lambda *_args: self._handle_table_double_clicked())
        self._selection_mode = TableSelectionModeController(
            self.table,
            id_source_column=0,
            on_selection_changed=self._handle_delete_selection_changed,
        )

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.search_input, 1)
        filter_layout.addWidget(self.include_inactive_checkbox)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.add_button)
        action_layout.addWidget(self.edit_button)
        action_layout.addWidget(self.delete_button)
        action_layout.addWidget(self.delete_selected_button)
        action_layout.addWidget(self.cancel_delete_button)
        action_layout.addWidget(self.selected_count_label)
        action_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(filter_layout)
        layout.addLayout(action_layout)
        layout.addWidget(self.table, 1)

        self.reload()

    def reload(self) -> None:
        if self._selection_mode.is_active:
            self._exit_delete_selection_mode()
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
        item = self.table.item(current_row, 1 if self._selection_mode.is_active else 0)
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
            item = self.table.item(row, 1 if self._selection_mode.is_active else 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == employee_id:
                self.table.selectRow(row)
                return

    def _selected_employee(self) -> Employee | None:
        employee_id = self.selected_employee_id()
        if employee_id is None:
            return None
        return next((employee for employee in self._employees if employee.id == employee_id), None)

    def _update_button_state(self) -> None:
        if self._selection_mode.is_active:
            self.edit_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            self.delete_selected_button.setEnabled(bool(self._selection_mode.selected_ids()))
            return
        has_selection = self.selected_employee_id() is not None
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(bool(self._employees))

    def _handle_filter_changed(self, *_args: object) -> None:
        if self._selection_mode.is_active:
            self._exit_delete_selection_mode()
        self.reload()

    def _handle_table_double_clicked(self) -> None:
        if self._selection_mode.is_active:
            return
        self._open_edit_dialog()

    def _enter_delete_selection_mode(self) -> None:
        if not self._employees:
            return
        self.table.clearSelection()
        self._selection_mode.enter()
        self.add_button.hide()
        self.edit_button.hide()
        self.delete_button.hide()
        self.delete_selected_button.show()
        self.cancel_delete_button.show()
        self.selected_count_label.show()
        self._handle_delete_selection_changed([])

    def _exit_delete_selection_mode(self) -> None:
        self._selection_mode.exit(clear=True)
        self.add_button.show()
        self.edit_button.show()
        self.delete_button.show()
        self.delete_selected_button.hide()
        self.cancel_delete_button.hide()
        self.selected_count_label.hide()
        self._update_button_state()

    def _handle_delete_selection_changed(self, selected_ids: list[int]) -> None:
        self.selected_count_label.setText(f"Đã chọn: {len(selected_ids)}")
        self.delete_selected_button.setEnabled(bool(selected_ids))

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
            self.employees_changed.emit()
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
            self.employees_changed.emit()
            MessageBox.info(self, "Thành công", "Đã cập nhật nhân viên.")
        except AppError as exc:
            MessageBox.warning(self, "Không cập nhật được nhân viên", str(exc))

    def _delete_selected_employees(self) -> None:
        selected_ids = self._selection_mode.selected_ids()
        if not selected_ids:
            MessageBox.info(self, "Chưa chọn nhân viên", "Vui lòng chọn ít nhất một nhân viên để xóa.")
            return

        employees_by_id = {employee.id: employee for employee in self._employees}
        selected_names = [employees_by_id[employee_id].name for employee_id in selected_ids if employee_id in employees_by_id]
        preview_names = "\n".join(f"- {name}" for name in selected_names[:5])
        remaining_count = len(selected_names) - 5
        if remaining_count > 0:
            preview_names = f"{preview_names}\n- ... và {remaining_count} nhân viên khác"
        message = f"Bạn có chắc muốn xóa {len(selected_ids)} nhân viên đã chọn không?"
        if preview_names:
            message = f"{message}\n\n{preview_names}"
        confirmed = QMessageBox.question(
            self,
            "Xác nhận xóa",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        hard_deleted = 0
        deactivated = 0
        failures: list[str] = []
        for employee_id in selected_ids:
            try:
                result = self._service.delete_or_deactivate_employee(employee_id)
                if result.deleted_without_history:
                    hard_deleted += 1
                else:
                    deactivated += 1
            except Exception as exc:  # noqa: BLE001 - batch delete should continue per employee.
                name = employees_by_id.get(employee_id).name if employee_id in employees_by_id else str(employee_id)
                failures.append(f"{name}: {exc}")

        self._exit_delete_selection_mode()
        self.reload()
        if hard_deleted or deactivated:
            self.employees_changed.emit()

        summary_parts: list[str] = []
        if hard_deleted:
            summary_parts.append(f"Đã xóa vĩnh viễn {hard_deleted} nhân viên.")
        if deactivated:
            summary_parts.append(f"Đã chuyển {deactivated} nhân viên sang ngừng sử dụng.")
        if failures:
            summary_parts.append(f"Có {len(failures)} nhân viên không xử lý được.")
            summary_parts.extend(failures[:3])
        summary = "\n".join(summary_parts) if summary_parts else "Không có nhân viên nào được xử lý."
        if failures:
            MessageBox.warning(self, "Kết quả xóa nhân viên", summary)
        else:
            MessageBox.info(self, "Kết quả xóa nhân viên", summary)

    def _delete_selected_employee(self) -> None:
        self._enter_delete_selection_mode()
