from __future__ import annotations

from core.db import SessionFactory
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.customer.ui.page import CustomerPage

MODULE_KEY = "customer"
MODULE_LABEL = "Khách hàng"



def create_page() -> CustomerPage:
    repository = CustomerRepository(SessionFactory)
    service = CustomerService(repository)
    return CustomerPage(service)
