"""Registro das calculadoras. Para criar uma nova: adicione um módulo com META e calcular() aqui."""
from . import atualizacao, cheque_especial, financiamento, judicial_tjes, juros_taxas, prazos, reajuste

MODULOS = [judicial_tjes, atualizacao, cheque_especial, financiamento, reajuste, juros_taxas, prazos]
POR_SLUG = {m.META["slug"]: m for m in MODULOS}
