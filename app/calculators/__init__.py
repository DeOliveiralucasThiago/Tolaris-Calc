"""Registro das calculadoras. Para criar uma nova: adicione um módulo com META e calcular() aqui."""
from . import atualizacao, cheque_especial, financiamento, judicial_tjes, juros_taxas, pensao, prazos, reajuste, taxa_legal

MODULOS = [judicial_tjes, taxa_legal, pensao, atualizacao, cheque_especial, financiamento, reajuste, juros_taxas, prazos]
POR_SLUG = {m.META["slug"]: m for m in MODULOS}
