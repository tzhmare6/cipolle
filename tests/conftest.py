from datetime import date

import pytest

from cipolle.book import Book
from cipolle.templates import KMU_CHART


@pytest.fixture
def book(tmp_path):
    instance = Book.create(tmp_path / "test.cipolle", "Muster GmbH", date(2026, 1, 1), date(2026, 12, 31), KMU_CHART)
    yield instance
    instance.close()


@pytest.fixture
def ids(book):
    return {account.number: account.id for account in book.accounts()}
