"""Utilitários numéricos: toda a matemática financeira usa Decimal."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, getcontext

getcontext().prec = 40

ZERO = Decimal("0")
UM = Decimal("1")
CEM = Decimal("100")
CENTAVO = Decimal("0.01")


def D(valor) -> Decimal:
    """Converte qualquer entrada em Decimal sem passar por float."""
    if isinstance(valor, Decimal):
        return valor
    if valor is None or valor == "":
        return ZERO
    return Decimal(str(valor))


def arred(valor: Decimal, casas: int = 2) -> Decimal:
    """Arredondamento comercial (meio para cima), padrão de cálculo judicial."""
    return D(valor).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)


def pct(valor: Decimal) -> Decimal:
    """5 (%) -> 0.05"""
    return D(valor) / CEM


def potencia(base: Decimal, expoente: Decimal) -> Decimal:
    """base ** expoente para expoente fracionário, em Decimal."""
    base, expoente = D(base), D(expoente)
    if expoente == expoente.to_integral_value():
        return base ** int(expoente)
    return (expoente * base.ln()).exp()


def brl(valor, casas: int = 2) -> str:
    v = arred(D(valor), casas)
    s = f"{abs(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


def num_br(valor, casas: int = 2) -> str:
    v = arred(D(valor), casas)
    s = f"{abs(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{s}" if v < 0 else s
