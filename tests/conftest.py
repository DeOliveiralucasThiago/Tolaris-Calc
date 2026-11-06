from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core import indices
from app.main import app


@pytest.fixture(autouse=True)
def serie_sintetica(monkeypatch):
    """Nenhum teste acessa a internet: todos os índices valem 1,00% ao mês de 2024-01 a 2025-12."""
    def falsa(nome, forcar=False):
        valores = {f"{a}-{m:02d}": Decimal("1.00") for a in (2024, 2025) for m in range(1, 13)}
        return indices.Serie(nome, valores, "bcb", datetime(2026, 1, 1).strftime("%d/%m/%Y %H:%M"))
    monkeypatch.setattr(indices, "obter_serie", falsa)


@pytest.fixture
def api():
    return TestClient(app)
