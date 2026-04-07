from __future__ import annotations

from core.db import SessionFactory
from modules.reporting.repository import ReportingRepository
from modules.reporting.service import ReportingService
from modules.reporting.ui.page import ReportingPage

MODULE_KEY = "reporting"
MODULE_LABEL = "Bao cao"



def create_page() -> ReportingPage:
    repository = ReportingRepository(SessionFactory)
    service = ReportingService(repository)
    return ReportingPage(service)
