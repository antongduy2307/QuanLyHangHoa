from __future__ import annotations

import unittest

from PyQt6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService
from modules.sales.ui.page import SalesPage


class ReturnPageUiScaleTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.sales_page = SalesPage(SalesService(SalesRepository(self.Session)))

    def tearDown(self) -> None:
        self.sales_page.deleteLater()
        self.engine.dispose()

    def test_sales_page_forwards_ui_scale_to_return_tab(self) -> None:
        self.sales_page.apply_ui_scale_preset("standard")
        standard_stylesheet = self.sales_page._return_page_view.styleSheet()

        self.sales_page.apply_ui_scale_preset("xlarge")
        xlarge_stylesheet = self.sales_page._return_page_view.styleSheet()

        self.assertNotEqual(standard_stylesheet, xlarge_stylesheet)
        self.assertIn("font-size: 20px;", standard_stylesheet)
        self.assertIn("font-size: 22px;", xlarge_stylesheet)


if __name__ == "__main__":
    unittest.main()
