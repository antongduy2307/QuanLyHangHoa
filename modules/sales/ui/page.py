from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QMenu, QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget

from modules.returns.controller import ReturnController
from modules.returns.ui.return_page import ReturnPage as ReturnPageView
from modules.sales.controller import SalesController
from modules.sales.service import SalesService
from modules.sales.ui.sales_page import SalesPage as SalesPageView
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit


class SalesPage(QWidget):
    transaction_changed = pyqtSignal()

    def __init__(self, service: SalesService) -> None:
        super().__init__()
        self._session_factory = service._repository._session_factory
        self._return_page_view: QWidget | None = None

        self._shared_search_input = AutocompleteLineEdit(self)
        self._shared_search_input.setMinimumWidth(320)
        self._shared_search_input.setMaximumWidth(420)
        self._shared_search_input.textEdited.connect(self._update_shared_search_suggestions)
        self._shared_search_input.suggestion_selected.connect(self._activate_shared_search_selection)
        self._shared_search_input.returnPressed.connect(self._activate_shared_search_best_match)

        self._workspace_tab_bar = QTabBar()
        self._workspace_tab_bar.setMovable(False)
        self._workspace_tab_bar.setTabsClosable(True)
        self._workspace_tab_bar.setDocumentMode(True)
        self._workspace_tab_bar.setExpanding(False)
        self._workspace_tab_bar.setUsesScrollButtons(True)
        self._workspace_tab_bar.currentChanged.connect(self._handle_tab_changed)
        self._workspace_tab_bar.tabCloseRequested.connect(self._close_workspace_tab)

        self._new_tab_button = QToolButton()
        self._new_tab_button.setText("+")
        self._new_tab_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._new_tab_button.setAutoRaise(False)

        new_tab_menu = QMenu(self._new_tab_button)
        new_sale_action = new_tab_menu.addAction("Bán hàng mới")
        return_menu = new_tab_menu.addMenu("Trả hàng mới")
        new_return_invoice_action = return_menu.addAction("Trả theo hóa đơn")
        new_return_quick_action = return_menu.addAction("Trả nhanh")
        new_sale_action.triggered.connect(lambda: self._add_sales_tab(make_current=True))
        new_return_invoice_action.triggered.connect(lambda: self._add_return_tab(make_current=True, mode="invoice"))
        new_return_quick_action.triggered.connect(lambda: self._add_return_tab(make_current=True, mode="quick"))
        self._new_tab_button.setMenu(new_tab_menu)

        self._workspace_tabs = QStackedWidget()
        self._workspace_tabs.currentChanged.connect(self._sync_top_row_state)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)
        top_row.addWidget(self._shared_search_input, 0, Qt.AlignmentFlag.AlignLeft)
        top_row.addWidget(self._workspace_tab_bar, 1)
        top_row.addWidget(self._new_tab_button, 0, Qt.AlignmentFlag.AlignRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(top_row)
        layout.addWidget(self._workspace_tabs, 1)

        self._add_sales_tab(make_current=True)
        self._add_return_tab(make_current=False, mode="invoice")
        self._sync_top_row_state()

    def apply_ui_scale_preset(self, preset: str) -> None:
        for index in range(self._workspace_tabs.count()):
            widget = self._workspace_tabs.widget(index)
            if widget is not None and hasattr(widget, "apply_ui_scale_preset"):
                widget.apply_ui_scale_preset(preset)

    def _add_sales_tab(self, *, make_current: bool, invoice=None, custom_label: str | None = None) -> None:
        controller = SalesController(self._session_factory)
        page = SalesPageView(controller, invoice=invoice, on_edit_completed=lambda: self._close_workspace_widget(page))
        page.setProperty("workspace_mode", "sales")
        page.setProperty("workspace_custom_label", custom_label)
        page.transaction_changed.connect(self._emit_transaction_changed)
        self._add_workspace_tab(page, mode="sales", make_current=make_current)

    def _add_return_tab(
        self,
        *,
        make_current: bool,
        mode: str,
        edit_return=None,
        edit_detail=None,
        custom_label: str | None = None,
    ) -> None:
        controller = ReturnController(self._session_factory)
        page = ReturnPageView(
            controller,
            mode=mode,
            edit_return=edit_return,
            edit_detail=edit_detail,
            on_edit_completed=lambda: self._close_workspace_widget(page),
        )
        page.setProperty("workspace_mode", "return")
        page.setProperty("return_mode", mode)
        page.setProperty("workspace_custom_label", custom_label)
        if hasattr(page, "transaction_changed"):
            page.transaction_changed.connect(self._emit_transaction_changed)
        self._return_page_view = page
        self._add_workspace_tab(page, mode="return", make_current=make_current)

    def _add_workspace_tab(self, widget: QWidget, *, mode: str, make_current: bool) -> None:
        index = self._workspace_tabs.addWidget(widget)
        self._workspace_tab_bar.addTab("")
        self._workspace_tab_bar.setTabData(index, mode)
        self._renumber_tabs()
        if make_current:
            self._workspace_tab_bar.setCurrentIndex(index)
            self._workspace_tabs.setCurrentIndex(index)

    def _close_workspace_tab(self, index: int) -> None:
        if self._workspace_tabs.count() == 1 or not (0 <= index < self._workspace_tabs.count()):
            return
        widget = self._workspace_tabs.widget(index)
        self._workspace_tabs.removeWidget(widget)
        self._workspace_tab_bar.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        if self._workspace_tab_bar.count():
            self._workspace_tab_bar.setCurrentIndex(min(index, self._workspace_tab_bar.count() - 1))
            self._workspace_tabs.setCurrentIndex(self._workspace_tab_bar.currentIndex())
        self._renumber_tabs()
        self._sync_top_row_state()

    def _handle_tab_changed(self, index: int) -> None:
        if 0 <= index < self._workspace_tabs.count():
            self._workspace_tabs.setCurrentIndex(index)
        self._sync_top_row_state()

    def _renumber_tabs(self) -> None:
        sales_counter = 0
        return_counter = 0
        for index in range(self._workspace_tabs.count()):
            widget = self._workspace_tabs.widget(index)
            custom_label = widget.property("workspace_custom_label") if widget is not None else None
            if custom_label:
                self._workspace_tab_bar.setTabText(index, str(custom_label))
                continue

            mode = self._workspace_mode_at(index)
            if mode == "sales":
                sales_counter += 1
                label = f"Bán hàng {sales_counter}"
            else:
                return_counter += 1
                label = f"Trả hàng {return_counter}"
            self._workspace_tab_bar.setTabText(index, label)

    def _workspace_mode_at(self, index: int) -> str:
        widget = self._workspace_tabs.widget(index)
        mode = widget.property("workspace_mode") if widget is not None else None
        return "return" if mode == "return" else "sales"

    def _current_workspace(self) -> QWidget | None:
        return self._workspace_tabs.currentWidget()

    def _update_shared_search_suggestions(self, text: str) -> None:
        widget = self._current_workspace()
        if widget is None or not hasattr(widget, "shared_search_suggestions"):
            self._shared_search_input.hide_suggestions()
            return
        suggestions = widget.shared_search_suggestions(text)
        self._shared_search_input.set_suggestions(suggestions)

    def _activate_shared_search_selection(self, payload: object) -> None:
        widget = self._current_workspace()
        if widget is not None and hasattr(widget, "activate_shared_search_selection"):
            widget.activate_shared_search_selection(payload)
            self._shared_search_input.clear()
            self._shared_search_input.hide_suggestions()

    def _activate_shared_search_best_match(self) -> None:
        widget = self._current_workspace()
        if widget is not None and hasattr(widget, "activate_shared_search_best_match"):
            widget.activate_shared_search_best_match(self._shared_search_input.text())
            self._shared_search_input.clear()
            self._shared_search_input.hide_suggestions()

    def _emit_transaction_changed(self) -> None:
        self.transaction_changed.emit()

    def open_invoice_edit_tab(self, invoice_id: int) -> None:
        controller = SalesController(self._session_factory)
        invoice = controller.get_invoice_detail(invoice_id)
        self._add_sales_tab(
            make_current=True,
            invoice=invoice,
            custom_label=self._truncate_tab_label("Sửa bán hàng", invoice.invoice_code),
        )

    def open_return_edit_tab(self, return_id: int) -> None:
        controller = ReturnController(self._session_factory)
        return_invoice = controller.get_return_invoice_detail(return_id)
        detail = controller.get_return_edit_detail(return_id) if return_invoice.source_invoice_id is not None else None
        mode = "invoice" if return_invoice.source_invoice_id is not None else "quick"
        self._add_return_tab(
            make_current=True,
            mode=mode,
            edit_return=return_invoice,
            edit_detail=detail,
            custom_label=self._truncate_tab_label("Sửa trả hàng", return_invoice.return_code),
        )

    def _sync_top_row_state(self) -> None:
        widget = self._current_workspace()
        if widget is not None and hasattr(widget, "shared_search_placeholder"):
            placeholder = widget.shared_search_placeholder()
            self._shared_search_input.setEnabled(bool(placeholder))
            self._shared_search_input.setPlaceholderText(placeholder)
        else:
            self._shared_search_input.setEnabled(False)
            self._shared_search_input.setPlaceholderText("")
        self._shared_search_input.clear()
        self._shared_search_input.hide_suggestions()

    def _close_workspace_widget(self, widget: QWidget) -> None:
        for index in range(self._workspace_tabs.count()):
            if self._workspace_tabs.widget(index) is widget:
                self._close_workspace_tab(index)
                break

    @staticmethod
    def _truncate_tab_label(prefix: str, code: str, max_length: int = 26) -> str:
        label = f"{prefix} {code}"
        if len(label) <= max_length:
            return label
        return f"{label[:max_length - 1]}…"
