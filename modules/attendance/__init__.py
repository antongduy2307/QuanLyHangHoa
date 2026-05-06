from __future__ import annotations

from modules.attendance.db import init_attendance_db
from modules.attendance.ui.page import AttendancePage

MODULE_KEY = "attendance"
MODULE_LABEL = "Chấm công"


def create_page() -> AttendancePage:
    init_attendance_db()
    return AttendancePage()
