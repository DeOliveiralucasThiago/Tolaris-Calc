"""Calendário forense brasileiro: feriados nacionais e móveis (algoritmo de Páscoa)."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def pascoa(ano: int) -> date:
    """Algoritmo anônimo gregoriano (Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


@lru_cache(maxsize=64)
def feriados(ano: int, carnaval: bool = True, sexta_santa: bool = True, corpus_christi: bool = True,
             semana_santa_completa: bool = False, consciencia_negra: bool = True) -> dict[date, str]:
    f = {
        date(ano, 1, 1): "Confraternização Universal",
        date(ano, 4, 21): "Tiradentes",
        date(ano, 5, 1): "Dia do Trabalho",
        date(ano, 9, 7): "Independência",
        date(ano, 10, 12): "Nossa Sra. Aparecida",
        date(ano, 11, 2): "Finados",
        date(ano, 11, 15): "Proclamação da República",
        date(ano, 12, 25): "Natal",
    }
    if consciencia_negra and ano >= 2024:  # Lei 14.759/2023
        f[date(ano, 11, 20)] = "Consciência Negra"
    p = pascoa(ano)
    if carnaval:
        f[p - timedelta(days=48)] = "Carnaval (segunda)"
        f[p - timedelta(days=47)] = "Carnaval (terça)"
    if sexta_santa:
        f[p - timedelta(days=2)] = "Sexta-feira Santa"
    if semana_santa_completa:  # Lei 5.010/1966, art. 62 – Justiça Federal
        for delta, nome in ((-4, "Quarta-feira Santa"), (-3, "Quinta-feira Santa"), (-2, "Sexta-feira Santa"),
                            (-1, "Sábado de Aleluia")):
            f[p + timedelta(days=delta)] = nome
    if corpus_christi:
        f[p + timedelta(days=60)] = "Corpus Christi"
    return f


def em_recesso(d: date) -> bool:
    """Suspensão de prazos de 20/12 a 20/01 (CPC, art. 220)."""
    return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 20)
