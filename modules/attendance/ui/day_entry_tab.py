from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from PyQt6.QtCore import QDate, QStringListModel, Qt
from PyQt6.QtWidgets import (
    QCompleter,
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import AppError
from modules.attendance.blow_work import BLOW_QUANTITY_WORK_QUOTA, calculate_blow_work_amount, is_blow_quantity_quota_work
from modules.attendance.cut_bonus import CutBonusItem, calculate_cut_employee_bonus
from modules.attendance.dto import AttendanceEmployeeRow, AttendanceSavePayload, BlowWorkInput, CutWorkInput, DayEntryDTO, ExtraCutWorkInput
from modules.attendance.models import Team, WorkInputType
from modules.attendance.service import AttendanceDayEntryService
from modules.attendance.ui.dialogs import team_to_label
from shared.widgets.message_box import MessageBox
from shared.widgets.numeric_inputs import SelectAllSpinBox
from shared.widgets.table_helpers import configure_table_cell_widget, configure_table_widget


class AttendanceDayEntryTab(QWidget):
    def __init__(self, service: AttendanceDayEntryService) -> None:
        super().__init__()
        self._service = service
        self._employees: list[AttendanceEmployeeRow] = []
        self._current_entry: DayEntryDTO | None = None
        self._blow_controls: dict[int, tuple[QCheckBox | None, SelectAllSpinBox | None]] = {}
        self._cut_controls: dict[int, SelectAllSpinBox] = {}
        self.cut_search_input: QLineEdit | None = None
        self.cut_add_button: QPushButton | None = None
        self.cut_table: QTableWidget | None = None
        self._cut_completion_ids_by_label: dict[str, int] = {}
        self.extra_cut_checkbox: QCheckBox | None = None
        self.extra_cut_group: QGroupBox | None = None
        self.extra_cut_search_input: QLineEdit | None = None
        self.extra_cut_add_button: QPushButton | None = None
        self.extra_cut_table: QTableWidget | None = None
        self._extra_cut_controls: dict[int, SelectAllSpinBox] = {}
        self._extra_cut_completion_ids_by_label: dict[str, int] = {}
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
        self.form_layout.setSpacing(8)
        self.form_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.form_scroll_area = QScrollArea()
        self.form_scroll_area.setWidgetResizable(True)
        self.form_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.form_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.form_scroll_area.setWidget(self.form_container)

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
        right_layout.addWidget(self.form_scroll_area, 1)
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
        self._extra_cut_controls.clear()
        self.cut_search_input = None
        self.cut_add_button = None
        self.cut_table = None
        self.extra_cut_checkbox = None
        self.extra_cut_group = None
        self.extra_cut_search_input = None
        self.extra_cut_add_button = None
        self.extra_cut_table = None
        self._extra_cut_completion_ids_by_label.clear()
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
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(4)
        log_by_work_type = {log.work_type_id: log for log in entry.work_logs}
        row = 0
        for work_type in entry.work_types:
            checkbox: QCheckBox | None = None
            spinbox: SelectAllSpinBox | None = None
            if work_type.input_type == WorkInputType.QUANTITY:
                quota_hint = f", khoán {BLOW_QUANTITY_WORK_QUOTA}" if is_blow_quantity_quota_work(work_type.name) else ""
                layout.addWidget(QLabel(f"{work_type.name} ({work_type.unit_price:,}{quota_hint})"), row, 0)
                spinbox = SelectAllSpinBox()
                spinbox.setRange(0, 100000)
                spinbox.setMinimumWidth(120)
                spinbox.setMaximumWidth(160)
                spinbox.setFixedHeight(34)
                spinbox.setValue(log_by_work_type.get(work_type.id).quantity if work_type.id in log_by_work_type else 0)
                spinbox.valueChanged.connect(lambda _value: self._update_total_preview())
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
        self._build_extra_cut_form(entry)
        self._update_total_preview()

    def _build_extra_cut_form(self, entry: DayEntryDTO) -> None:
        self.extra_cut_checkbox = QCheckBox("Có làm thêm việc cắt")
        self.extra_cut_checkbox.toggled.connect(self._toggle_extra_cut_section)
        self.form_layout.addWidget(self.extra_cut_checkbox)

        self.extra_cut_group = QGroupBox("Việc cắt làm thêm")
        self.extra_cut_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self.extra_cut_group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.extra_cut_search_input = QLineEdit()
        self.extra_cut_search_input.setPlaceholderText("Tìm loại bao")
        self.extra_cut_search_input.textEdited.connect(self._update_extra_cut_suggestions)
        self.extra_cut_search_input.returnPressed.connect(self._add_best_extra_cut_bag_match)
        completer = QCompleter(self.extra_cut_search_input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setModel(QStringListModel([], completer))
        completer.activated[str].connect(self._add_extra_cut_bag_by_label)
        self.extra_cut_search_input.setCompleter(completer)

        self.extra_cut_add_button = QPushButton("Thêm")
        self.extra_cut_add_button.clicked.connect(self._add_best_extra_cut_bag_match)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.extra_cut_search_input, 1)
        search_layout.addWidget(self.extra_cut_add_button)
        layout.addLayout(search_layout)

        self.extra_cut_table = QTableWidget(0, 3)
        self.extra_cut_table.setHorizontalHeaderLabels(["Loại bao", "Số lượng", ""])
        self.extra_cut_table.verticalHeader().setVisible(False)
        self.extra_cut_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.extra_cut_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.extra_cut_table.setAlternatingRowColors(True)
        self.extra_cut_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.extra_cut_table.verticalHeader().setDefaultSectionSize(max(self.extra_cut_table.verticalHeader().defaultSectionSize(), 56))
        self.extra_cut_table.verticalHeader().setMinimumSectionSize(max(self.extra_cut_table.verticalHeader().minimumSectionSize(), 56))
        header = self.extra_cut_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setStretchLastSection(False)
        self.extra_cut_table.setColumnWidth(1, 124)
        self.extra_cut_table.setColumnWidth(2, 82)
        layout.addWidget(self.extra_cut_table)

        for log in entry.extra_cut_work_logs:
            self._add_extra_cut_bag_row(log.bag_type_id, quantity=log.quantity)
        self._resize_extra_cut_table_to_contents()

        has_extra_cut = bool(entry.extra_cut_work_logs)
        self.extra_cut_checkbox.setChecked(has_extra_cut)
        self._sync_extra_cut_section_visibility()
        self.form_layout.addWidget(self.extra_cut_group)

    def _toggle_extra_cut_section(self, checked: bool) -> None:
        self._sync_extra_cut_section_visibility()
        if checked and self.extra_cut_group is not None:
            self.form_scroll_area.ensureWidgetVisible(self.extra_cut_group)
        self._update_total_preview()

    def _sync_extra_cut_section_visibility(self) -> None:
        if self.extra_cut_group is not None:
            checked = self.extra_cut_checkbox is not None and self.extra_cut_checkbox.isChecked()
            self.extra_cut_group.setVisible(checked and not self.absent_checkbox.isChecked())
            self.extra_cut_group.adjustSize()
        self.form_container.adjustSize()

    def _resize_extra_cut_table_to_contents(self) -> None:
        if self.extra_cut_table is None:
            return
        max_visible_rows = 8
        row_count = self.extra_cut_table.rowCount()
        visible_rows = max(1, min(row_count, max_visible_rows))
        header_height = self.extra_cut_table.horizontalHeader().height()
        row_height = self.extra_cut_table.verticalHeader().defaultSectionSize()
        frame_height = self.extra_cut_table.frameWidth() * 2
        height = header_height + (visible_rows * row_height) + frame_height + 4
        self.extra_cut_table.setFixedHeight(height)
        scrollbar_policy = (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if row_count <= max_visible_rows
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.extra_cut_table.setVerticalScrollBarPolicy(scrollbar_policy)
        if self.extra_cut_group is not None:
            self.extra_cut_group.adjustSize()
        self.form_container.adjustSize()

    def _update_extra_cut_suggestions(self, text: str) -> None:
        if self.extra_cut_search_input is None:
            return
        query = text.strip().casefold()
        if not query:
            self._set_extra_cut_suggestions([])
            return
        matches = [bag_type for bag_type in self._available_cut_bag_types() if query in bag_type.name.casefold()]
        self._set_extra_cut_suggestions([(self._extra_cut_bag_label(bag_type), bag_type.id) for bag_type in matches[:20]])

    def _set_extra_cut_suggestions(self, suggestions: list[tuple[str, int]]) -> None:
        if self.extra_cut_search_input is None:
            return
        self._extra_cut_completion_ids_by_label = dict(suggestions)
        completer = self.extra_cut_search_input.completer()
        if completer is None:
            return
        model = completer.model()
        if isinstance(model, QStringListModel):
            model.setStringList([label for label, _bag_type_id in suggestions])

    def _add_extra_cut_bag_by_label(self, label: str) -> None:
        bag_type_id = self._extra_cut_completion_ids_by_label.get(label)
        if bag_type_id is not None:
            self._add_extra_cut_bag_by_id(bag_type_id)

    def _add_best_extra_cut_bag_match(self) -> None:
        if self.extra_cut_search_input is None:
            return
        query = self.extra_cut_search_input.text().strip().casefold()
        if not query:
            return
        bag_type = next((candidate for candidate in self._available_cut_bag_types() if query in candidate.name.casefold()), None)
        if bag_type is None:
            return
        self._add_extra_cut_bag_by_id(bag_type.id)

    def _add_extra_cut_bag_by_id(self, bag_type_id: object) -> None:
        try:
            resolved_id = int(bag_type_id)
        except (TypeError, ValueError):
            return
        if resolved_id in self._extra_cut_controls:
            self._focus_extra_cut_bag_row(resolved_id)
            self._reset_extra_cut_search()
            return
        self._add_extra_cut_bag_row(resolved_id, quantity=1)
        self._focus_extra_cut_bag_row(resolved_id)
        self._reset_extra_cut_search()
        self._update_total_preview()

    def _add_extra_cut_bag_row(self, bag_type_id: int, *, quantity: int) -> None:
        entry = self._current_entry
        if entry is None or self.extra_cut_table is None:
            return
        bag_type = next((candidate for candidate in entry.bag_types if candidate.id == bag_type_id), None)
        if bag_type is None:
            return

        row = self.extra_cut_table.rowCount()
        self.extra_cut_table.insertRow(row)
        bag_item = QTableWidgetItem(self._extra_cut_bag_label(bag_type))
        bag_item.setData(Qt.ItemDataRole.UserRole, bag_type.id)
        self.extra_cut_table.setItem(row, 0, bag_item)

        quantity_input = SelectAllSpinBox()
        quantity_input.setRange(0, 100000)
        quantity_input.setValue(quantity)
        quantity_input.valueChanged.connect(lambda _value: self._update_total_preview())
        configure_table_cell_widget(quantity_input, height=34)
        self.extra_cut_table.setCellWidget(row, 1, quantity_input)
        self._extra_cut_controls[bag_type.id] = quantity_input

        delete_button = QPushButton("Xóa")
        delete_button.clicked.connect(lambda _checked=False, selected_id=bag_type.id: self._remove_extra_cut_bag_row(selected_id))
        configure_table_cell_widget(delete_button, compact=True, height=34)
        self.extra_cut_table.setCellWidget(row, 2, delete_button)
        self._resize_extra_cut_table_to_contents()

    def _remove_extra_cut_bag_row(self, bag_type_id: int) -> None:
        if self.extra_cut_table is None:
            return
        row = self._extra_cut_bag_row(bag_type_id)
        if row is None:
            return
        self._extra_cut_controls.pop(bag_type_id, None)
        self.extra_cut_table.removeRow(row)
        self._resize_extra_cut_table_to_contents()
        self._update_total_preview()

    def _focus_extra_cut_bag_row(self, bag_type_id: int) -> None:
        if self.extra_cut_table is None:
            return
        row = self._extra_cut_bag_row(bag_type_id)
        if row is None:
            return
        self.extra_cut_table.selectRow(row)
        self.extra_cut_table.scrollToItem(self.extra_cut_table.item(row, 0))
        quantity_input = self._extra_cut_controls.get(bag_type_id)
        if quantity_input is not None:
            quantity_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _extra_cut_bag_row(self, bag_type_id: int) -> int | None:
        if self.extra_cut_table is None:
            return None
        for row in range(self.extra_cut_table.rowCount()):
            item = self.extra_cut_table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == bag_type_id:
                return row
        return None

    def _reset_extra_cut_search(self) -> None:
        if self.extra_cut_search_input is None:
            return
        self.extra_cut_search_input.clear()
        self._set_extra_cut_suggestions([])

    def _extra_cut_bag_label(self, bag_type) -> str:
        return f"{bag_type.name} (Vượt: {self._format_money_decimal(bag_type.excess_unit_price)})"

    def _build_cut_form(self, entry: DayEntryDTO) -> None:
        group = QGroupBox("Sản lượng tổ cắt")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.cut_search_input = QLineEdit()
        self.cut_search_input.setPlaceholderText("Tìm loại bao")
        self.cut_search_input.textEdited.connect(self._update_cut_suggestions)
        self.cut_search_input.returnPressed.connect(self._add_best_cut_bag_match)
        completer = QCompleter(self.cut_search_input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setModel(QStringListModel([], completer))
        completer.activated[str].connect(self._add_cut_bag_by_label)
        self.cut_search_input.setCompleter(completer)

        self.cut_add_button = QPushButton("Thêm")
        self.cut_add_button.clicked.connect(self._add_best_cut_bag_match)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.cut_search_input, 1)
        search_layout.addWidget(self.cut_add_button)
        layout.addLayout(search_layout)

        self.cut_table = QTableWidget(0, 3)
        self.cut_table.setHorizontalHeaderLabels(["Loại bao", "Số lượng", ""])
        self.cut_table.verticalHeader().setVisible(False)
        self.cut_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cut_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cut_table.setAlternatingRowColors(True)
        self.cut_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.cut_table.setMinimumHeight(128)
        self.cut_table.setMaximumHeight(260)
        self.cut_table.verticalHeader().setDefaultSectionSize(max(self.cut_table.verticalHeader().defaultSectionSize(), 56))
        self.cut_table.verticalHeader().setMinimumSectionSize(max(self.cut_table.verticalHeader().minimumSectionSize(), 56))
        header = self.cut_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setStretchLastSection(False)
        self.cut_table.setColumnWidth(1, 124)
        self.cut_table.setColumnWidth(2, 82)
        layout.addWidget(self.cut_table)

        log_by_bag_type = {log.bag_type_id: log for log in entry.cut_logs}
        for bag_type in entry.bag_types:
            if bag_type.id in log_by_bag_type:
                self._add_cut_bag_row(bag_type.id, quantity=log_by_bag_type[bag_type.id].quantity)

        self.form_layout.addWidget(group)
        self.form_layout.addStretch(1)
        self._update_total_preview()

    def _update_cut_suggestions(self, text: str) -> None:
        if self.cut_search_input is None:
            return
        query = text.strip().casefold()
        if not query:
            self._set_cut_suggestions([])
            return
        matches = [bag_type for bag_type in self._available_cut_bag_types() if query in bag_type.name.casefold()]
        self._set_cut_suggestions([(self._cut_bag_label(bag_type), bag_type.id) for bag_type in matches[:20]])

    def _set_cut_suggestions(self, suggestions: list[tuple[str, int]]) -> None:
        if self.cut_search_input is None:
            return
        self._cut_completion_ids_by_label = dict(suggestions)
        completer = self.cut_search_input.completer()
        if completer is None:
            return
        model = completer.model()
        if isinstance(model, QStringListModel):
            model.setStringList([label for label, _bag_type_id in suggestions])

    def _add_cut_bag_by_label(self, label: str) -> None:
        bag_type_id = self._cut_completion_ids_by_label.get(label)
        if bag_type_id is not None:
            self._add_cut_bag_by_id(bag_type_id)

    def _add_best_cut_bag_match(self) -> None:
        if self.cut_search_input is None:
            return
        query = self.cut_search_input.text().strip().casefold()
        if not query:
            return
        bag_type = next((candidate for candidate in self._available_cut_bag_types() if query in candidate.name.casefold()), None)
        if bag_type is None:
            return
        self._add_cut_bag_by_id(bag_type.id)

    def _add_cut_bag_by_id(self, bag_type_id: object) -> None:
        try:
            resolved_id = int(bag_type_id)
        except (TypeError, ValueError):
            return
        if resolved_id in self._cut_controls:
            self._focus_cut_bag_row(resolved_id)
            self._reset_cut_search()
            return
        self._add_cut_bag_row(resolved_id, quantity=1)
        self._focus_cut_bag_row(resolved_id)
        self._reset_cut_search()
        self._update_total_preview()

    def _add_cut_bag_row(self, bag_type_id: int, *, quantity: int) -> None:
        entry = self._current_entry
        if entry is None or self.cut_table is None:
            return
        bag_type = next((candidate for candidate in entry.bag_types if candidate.id == bag_type_id), None)
        if bag_type is None:
            return

        row = self.cut_table.rowCount()
        self.cut_table.insertRow(row)
        bag_item = QTableWidgetItem(self._cut_bag_label(bag_type))
        bag_item.setData(Qt.ItemDataRole.UserRole, bag_type.id)
        self.cut_table.setItem(row, 0, bag_item)

        quantity_input = SelectAllSpinBox()
        quantity_input.setRange(0, 100000)
        quantity_input.setValue(quantity)
        quantity_input.valueChanged.connect(lambda _value: self._update_total_preview())
        configure_table_cell_widget(quantity_input, height=34)
        self.cut_table.setCellWidget(row, 1, quantity_input)
        self._cut_controls[bag_type.id] = quantity_input

        delete_button = QPushButton("Xóa")
        delete_button.clicked.connect(lambda _checked=False, selected_id=bag_type.id: self._remove_cut_bag_row(selected_id))
        configure_table_cell_widget(delete_button, compact=True, height=34)
        self.cut_table.setCellWidget(row, 2, delete_button)

    def _remove_cut_bag_row(self, bag_type_id: int) -> None:
        if self.cut_table is None:
            return
        row = self._cut_bag_row(bag_type_id)
        if row is None:
            return
        self._cut_controls.pop(bag_type_id, None)
        self.cut_table.removeRow(row)
        self._update_total_preview()

    def _focus_cut_bag_row(self, bag_type_id: int) -> None:
        if self.cut_table is None:
            return
        row = self._cut_bag_row(bag_type_id)
        if row is None:
            return
        self.cut_table.selectRow(row)
        self.cut_table.scrollToItem(self.cut_table.item(row, 0))
        spinbox = self._cut_controls.get(bag_type_id)
        if spinbox is not None:
            spinbox.setFocus(Qt.FocusReason.OtherFocusReason)

    def _cut_bag_row(self, bag_type_id: int) -> int | None:
        if self.cut_table is None:
            return None
        for row in range(self.cut_table.rowCount()):
            item = self.cut_table.item(row, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == bag_type_id:
                return row
        return None

    def _reset_cut_search(self) -> None:
        if self.cut_search_input is None:
            return
        self.cut_search_input.clear()
        self._set_cut_suggestions([])

    def _available_cut_bag_types(self):
        entry = self._current_entry
        if entry is None:
            return []
        return [bag_type for bag_type in entry.bag_types if bag_type.is_active]

    def _cut_bag_label(self, bag_type) -> str:
        return (
            f"{bag_type.name} (Khoán: {self._format_decimal(bag_type.quota_quantity)}, "
            f"Vượt: {self._format_money_decimal(bag_type.excess_unit_price)})"
        )

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
        for spinbox in self._extra_cut_controls.values():
            spinbox.setDisabled(is_absent)
        if self.extra_cut_checkbox is not None:
            self.extra_cut_checkbox.setDisabled(is_absent)
        if self.extra_cut_search_input is not None:
            self.extra_cut_search_input.setDisabled(is_absent)
            if is_absent:
                completer = self.extra_cut_search_input.completer()
                if completer is not None:
                    completer.popup().hide()
        if self.extra_cut_add_button is not None:
            self.extra_cut_add_button.setDisabled(is_absent)
        if self.extra_cut_table is not None:
            self.extra_cut_table.setDisabled(is_absent)
        self._sync_extra_cut_section_visibility()
        if self.cut_search_input is not None:
            self.cut_search_input.setDisabled(is_absent)
            if is_absent:
                completer = self.cut_search_input.completer()
                if completer is not None:
                    completer.popup().hide()
        if self.cut_add_button is not None:
            self.cut_add_button.setDisabled(is_absent)
        if self.cut_table is not None:
            self.cut_table.setDisabled(is_absent)
        self._update_total_preview()

    def _collect_payload(self) -> AttendanceSavePayload | None:
        entry = self._current_entry
        if entry is None:
            return None
        blow_work: list[BlowWorkInput] = []
        cut_work: list[CutWorkInput] = []
        extra_cut_work: list[ExtraCutWorkInput] = []
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
            if self.extra_cut_checkbox is not None and self.extra_cut_checkbox.isChecked():
                for bag_type_id, spinbox in self._extra_cut_controls.items():
                    if spinbox.value() > 0:
                        extra_cut_work.append(ExtraCutWorkInput(bag_type_id=bag_type_id, quantity=spinbox.value()))
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
            extra_cut_work=extra_cut_work,
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
                total += calculate_blow_work_amount(work_type.input_type, quantity, work_type.unit_price, work_type.name)
            if self.extra_cut_checkbox is not None and self.extra_cut_checkbox.isChecked():
                bag_type_by_id = {bag_type.id: bag_type for bag_type in entry.bag_types}
                extra_cut_total = Decimal("0")
                for bag_type_id, spinbox in self._extra_cut_controls.items():
                    quantity = spinbox.value()
                    if quantity <= 0:
                        continue
                    bag_type = bag_type_by_id[bag_type_id]
                    extra_cut_total += Decimal(quantity) * Decimal(str(bag_type.excess_unit_price))
                total += int(extra_cut_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            bag_type_by_id = {bag_type.id: bag_type for bag_type in entry.bag_types}
            active_items: list[CutBonusItem] = []
            for bag_type_id, spinbox in self._cut_controls.items():
                quantity = spinbox.value()
                if quantity <= 0:
                    continue
                bag_type = bag_type_by_id[bag_type_id]
                active_items.append(
                    CutBonusItem(
                        quantity=quantity,
                        quota_quantity=Decimal(str(bag_type.quota_quantity)),
                        excess_unit_price=Decimal(str(bag_type.excess_unit_price)),
                    )
                )
            if active_items:
                total = int(calculate_cut_employee_bonus(active_items).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        self.total_label.setText(f"{total:,}")

    def _format_decimal(self, value: Decimal) -> str:
        normalized = Decimal(str(value)).normalize()
        return format(normalized, "f")

    def _format_money_decimal(self, value: Decimal) -> str:
        amount = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return f"{amount:,}"

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
