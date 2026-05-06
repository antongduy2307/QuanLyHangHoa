from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import AppError
from modules.attendance.dto import AttendanceEmployeeRow, AttendanceSavePayload, BlowWorkInput, CutWorkInput, DayEntryDTO
from modules.attendance.models import Team, WorkInputType
from modules.attendance.service import AttendanceDayEntryService
from modules.attendance.ui.dialogs import team_to_label
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class AttendanceDayEntryTab(QWidget):
    def __init__(self, service: AttendanceDayEntryService) -> None:
        super().__init__()
        self._service = service
        self._employees: list[AttendanceEmployeeRow] = []
        self._current_entry: DayEntryDTO | None = None
        self._blow_controls: dict[int, tuple[QCheckBox | None, QSpinBox | None]] = {}
        self._cut_controls: dict[int, QSpinBox] = {}
        self._glove_work_ids_by_name: dict[str, int] = {}

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._handle_date_changed)

        self.employee_table = QTableWidget(0, 3)
        self.employee_table.setHorizontalHeaderLabels(["Tên", "Tổ", "Trạng thái"])
        configure_table_widget(self.employee_table, "attendance.day.employee_list")
        self.employee_table.itemSelectionChanged.connect(self._load_selected_employee)

        self.employee_name_label = QLabel("-")
        self.team_label = QLabel("-")
        self.selected_date_label = QLabel("-")
        self.status_label = QLabel("-")
        self.total_label = QLabel("0")

        summary_group = QGroupBox("Thông tin")
        summary_layout = QFormLayout(summary_group)
        summary_layout.addRow("Nhân viên", self.employee_name_label)
        summary_layout.addRow("Tổ", self.team_label)
        summary_layout.addRow("Ngày", self.selected_date_label)
        summary_layout.addRow("Trạng thái", self.status_label)
        summary_layout.addRow("Tổng tạm tính", self.total_label)

        self.absent_checkbox = QCheckBox("Nghỉ")
        self.absent_checkbox.toggled.connect(self._apply_absent_state)

        self.form_container = QWidget()
        self.form_layout = QVBoxLayout(self.form_container)
        self.form_layout.setContentsMargins(0, 0, 0, 0)

        self.save_draft_button = QPushButton("Lưu nháp")
        self.finalize_button = QPushButton("Chốt ngày")
        self.reload_button = QPushButton("Làm mới form")
        self.save_draft_button.clicked.connect(lambda: self._save_current(finalize=False))
        self.finalize_button.clicked.connect(lambda: self._save_current(finalize=True))
        self.reload_button.clicked.connect(self._load_selected_employee)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Ngày chấm công"))
        top_layout.addWidget(self.date_edit)
        top_layout.addStretch()

        left_layout = QVBoxLayout()
        left_layout.addLayout(top_layout)
        left_layout.addWidget(self.employee_table, 1)

        actions = QHBoxLayout()
        actions.addWidget(self.save_draft_button)
        actions.addWidget(self.finalize_button)
        actions.addWidget(self.reload_button)
        actions.addStretch()

        right_layout = QVBoxLayout()
        right_layout.addWidget(summary_group)
        right_layout.addWidget(self.absent_checkbox)
        right_layout.addWidget(self.form_container, 1)
        right_layout.addLayout(actions)

        root_layout = QHBoxLayout(self)
        left_panel = QWidget()
        left_panel.setLayout(left_layout)
        right_panel = QWidget()
        right_panel.setLayout(right_layout)
        root_layout.addWidget(left_panel, 2)
        root_layout.addWidget(right_panel, 3)

        self.reload_employees()
        self._update_action_state()

    def selected_date(self) -> date:
        return self.date_edit.date().toPyDate()

    def selected_employee_id(self) -> int | None:
        row = self.employee_table.currentRow()
        if row < 0:
            return None
        item = self.employee_table.item(row, 0)
        if item is None:
            return None
        employee_id = item.data(Qt.ItemDataRole.UserRole)
        return int(employee_id) if employee_id is not None else None

    def reload_for_current_date(self) -> None:
        selected_employee_id = self.selected_employee_id()
        had_selection = selected_employee_id is not None
        try:
            self._employees = self._service.list_attendance_employees_for_date(self.selected_date())
            self._render_employee_table()
            restored = self._restore_employee_selection(selected_employee_id)
            if selected_employee_id is None and self.employee_table.rowCount() > 0:
                self.employee_table.selectRow(0)
            elif had_selection and not restored:
                self.employee_table.clearSelection()
                self._clear_entry()
            else:
                self._load_selected_employee()
        except AppError as exc:
            MessageBox.error(self, "Không tải được chấm công", str(exc))

    def reload_employees(self) -> None:
        self.reload_for_current_date()

    def _handle_date_changed(self, _selected_date: QDate) -> None:
        self.reload_employees()

    def _render_employee_table(self) -> None:
        self.employee_table.setRowCount(len(self._employees))
        for row, employee in enumerate(self._employees):
            name_item = QTableWidgetItem(employee.name)
            name_item.setData(Qt.ItemDataRole.UserRole, employee.id)
            self.employee_table.setItem(row, 0, name_item)
            self.employee_table.setItem(row, 1, QTableWidgetItem(team_to_label(employee.team)))
            self.employee_table.setItem(row, 2, QTableWidgetItem(employee.status_label))

    def _restore_employee_selection(self, employee_id: int | None) -> bool:
        if employee_id is None:
            return False
        for row in range(self.employee_table.rowCount()):
            item = self.employee_table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == employee_id:
                self.employee_table.selectRow(row)
                return True
        return False

    def _load_selected_employee(self) -> None:
        employee_id = self.selected_employee_id()
        if employee_id is None:
            self._clear_entry()
            return
        try:
            entry = self._service.get_day_entry(employee_id, self.selected_date())
            self._set_entry(entry)
        except AppError as exc:
            MessageBox.error(self, "Không tải được form chấm công", str(exc))

    def _set_entry(self, entry: DayEntryDTO) -> None:
        self._current_entry = entry
        self.employee_name_label.setText(entry.employee_name)
        self.team_label.setText(team_to_label(entry.team))
        self.selected_date_label.setText(entry.selected_date.strftime("%d/%m/%Y"))
        self.status_label.setText(entry.status_label)
        self.total_label.setText(f"{entry.total_amount_snapshot:,}")

        self.absent_checkbox.blockSignals(True)
        self.absent_checkbox.setChecked(entry.is_absent)
        self.absent_checkbox.blockSignals(False)

        self._clear_form_layout()
        self._blow_controls.clear()
        self._cut_controls.clear()
        self._glove_work_ids_by_name.clear()
        if entry.team == Team.BLOW:
            self._build_blow_form(entry)
        else:
            self._build_cut_form(entry)
        self._apply_absent_state(entry.is_absent)
        self._update_action_state()

    def _clear_entry(self) -> None:
        self._current_entry = None
        self.employee_name_label.setText("-")
        self.team_label.setText("-")
        self.selected_date_label.setText("-")
        self.status_label.setText("-")
        self.total_label.setText("0")
        self.absent_checkbox.setChecked(False)
        self._clear_form_layout()
        self._update_action_state()

    def _build_blow_form(self, entry: DayEntryDTO) -> None:
        group = QGroupBox("Việc tổ thổi")
        layout = QGridLayout(group)
        log_by_work_type = {log.work_type_id: log for log in entry.work_logs}
        row = 0
        for work_type in entry.work_types:
            checkbox: QCheckBox | None = None
            spinbox: QSpinBox | None = None
            if work_type.input_type == WorkInputType.QUANTITY:
                layout.addWidget(QLabel(f"{work_type.name} ({work_type.unit_price:,})"), row, 0)
                spinbox = QSpinBox()
                spinbox.setRange(0, 100000)
                spinbox.setValue(log_by_work_type.get(work_type.id).quantity if work_type.id in log_by_work_type else 0)
                spinbox.valueChanged.connect(self._update_total_preview)
                layout.addWidget(spinbox, row, 1)
            else:
                checkbox = QCheckBox(f"{work_type.name} ({work_type.unit_price:,})")
                checkbox.setChecked(work_type.id in log_by_work_type)
                checkbox.toggled.connect(self._update_total_preview)
                layout.addWidget(checkbox, row, 0)
                if work_type.name in {"Phụ găng 1 máy", "Phụ găng 2 máy"}:
                    self._glove_work_ids_by_name[work_type.name] = work_type.id
                    checkbox.toggled.connect(lambda checked, name=work_type.name: self._handle_glove_toggled(name, checked))
                layout.addWidget(QLabel("tick"), row, 1)
            self._blow_controls[work_type.id] = (checkbox, spinbox)
            row += 1
        self.form_layout.addWidget(group)
        self._update_total_preview()

    def _build_cut_form(self, entry: DayEntryDTO) -> None:
        group = QGroupBox("Sản lượng tổ cắt")
        layout = QGridLayout(group)
        layout.addWidget(QLabel("Loại bao"), 0, 0)
        layout.addWidget(QLabel("Số lượng"), 0, 1)
        log_by_bag_type = {log.bag_type_id: log for log in entry.cut_logs}
        for row, bag_type in enumerate(entry.bag_types, start=1):
            layout.addWidget(QLabel(f"{bag_type.name} ({bag_type.unit_price:,})"), row, 0)
            spinbox = QSpinBox()
            spinbox.setRange(0, 100000)
            spinbox.setValue(log_by_bag_type.get(bag_type.id).quantity if bag_type.id in log_by_bag_type else 0)
            spinbox.valueChanged.connect(self._update_total_preview)
            layout.addWidget(spinbox, row, 1)
            self._cut_controls[bag_type.id] = spinbox
        self.form_layout.addWidget(group)
        self._update_total_preview()

    def _handle_glove_toggled(self, selected_name: str, checked: bool) -> None:
        if not checked:
            return
        for name, work_type_id in self._glove_work_ids_by_name.items():
            if name == selected_name:
                continue
            checkbox, _spinbox = self._blow_controls.get(work_type_id, (None, None))
            if checkbox is not None:
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)
        self._update_total_preview()

    def _apply_absent_state(self, is_absent: bool) -> None:
        for checkbox, spinbox in self._blow_controls.values():
            if checkbox is not None:
                checkbox.setDisabled(is_absent)
            if spinbox is not None:
                spinbox.setDisabled(is_absent)
        for spinbox in self._cut_controls.values():
            spinbox.setDisabled(is_absent)
        self._update_total_preview()

    def _collect_payload(self) -> AttendanceSavePayload | None:
        entry = self._current_entry
        if entry is None:
            return None
        blow_work: list[BlowWorkInput] = []
        cut_work: list[CutWorkInput] = []
        if entry.team == Team.BLOW and not self.absent_checkbox.isChecked():
            for work_type in entry.work_types:
                checkbox, spinbox = self._blow_controls[work_type.id]
                if work_type.input_type == WorkInputType.QUANTITY:
                    quantity = spinbox.value() if spinbox is not None else 0
                    if quantity > 0:
                        blow_work.append(BlowWorkInput(work_type_id=work_type.id, quantity=quantity))
                    continue
                if checkbox is not None and checkbox.isChecked():
                    blow_work.append(BlowWorkInput(work_type_id=work_type.id, quantity=None))
        if entry.team == Team.CUT and not self.absent_checkbox.isChecked():
            for bag_type_id, spinbox in self._cut_controls.items():
                if spinbox.value() > 0:
                    cut_work.append(CutWorkInput(bag_type_id=bag_type_id, quantity=spinbox.value()))
        return AttendanceSavePayload(
            employee_id=entry.employee_id,
            selected_date=entry.selected_date,
            is_absent=self.absent_checkbox.isChecked(),
            blow_work=blow_work,
            cut_work=cut_work,
        )

    def _save_current(self, *, finalize: bool) -> None:
        payload = self._collect_payload()
        if payload is None:
            MessageBox.warning(self, "Cảnh báo", "Vui lòng chọn nhân viên.")
            return
        try:
            self._service.save_attendance(payload, finalize=finalize)
            selected_employee_id = payload.employee_id
            self.reload_employees()
            self._restore_employee_selection(selected_employee_id)
            self._load_selected_employee()
            MessageBox.info(self, "Thành công", "Đã lưu chấm công.")
        except AppError as exc:
            MessageBox.warning(self, "Không lưu được chấm công", str(exc))

    def _update_total_preview(self) -> None:
        entry = self._current_entry
        if entry is None or self.absent_checkbox.isChecked():
            self.total_label.setText("0")
            return
        total = 0
        if entry.team == Team.BLOW:
            work_type_by_id = {work_type.id: work_type for work_type in entry.work_types}
            for work_type_id, (checkbox, spinbox) in self._blow_controls.items():
                work_type = work_type_by_id[work_type_id]
                if work_type.input_type == WorkInputType.TICK:
                    if checkbox is None or not checkbox.isChecked():
                        continue
                    quantity = 1
                else:
                    quantity = spinbox.value() if spinbox is not None else 0
                total += quantity * work_type.unit_price
        else:
            bag_type_by_id = {bag_type.id: bag_type for bag_type in entry.bag_types}
            for bag_type_id, spinbox in self._cut_controls.items():
                total += spinbox.value() * bag_type_by_id[bag_type_id].unit_price
        self.total_label.setText(f"{total:,}")

    def _update_action_state(self) -> None:
        enabled = self._current_entry is not None
        self.save_draft_button.setEnabled(enabled)
        self.finalize_button.setEnabled(enabled)
        self.reload_button.setEnabled(enabled)

    def _clear_form_layout(self) -> None:
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
