"""Estrutura padrão de resultado devolvida por todas as calculadoras.

Tipos de valor: dinheiro, percentual, taxa, fator, data, inteiro, texto.
O mesmo objeto alimenta a tela, o PDF e o Excel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .numeros import arred

CASAS = {"dinheiro": 2, "percentual": 4, "taxa": 6, "fator": 8}


def _serializa(valor: Any, tipo: str) -> Any:
    if isinstance(valor, Decimal):
        return str(arred(valor, CASAS.get(tipo, 6)))
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


@dataclass
class Resultado:
    titulo: str
    resumo: list[dict] = field(default_factory=list)
    parametros: list[dict] = field(default_factory=list)
    tabelas: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    metodologia: list[str] = field(default_factory=list)

    def kpi(self, rotulo: str, valor: Any, tipo: str = "dinheiro", destaque: bool = False, nota: str = ""):
        self.resumo.append({"rotulo": rotulo, "valor": _serializa(valor, tipo), "tipo": tipo,
                            "destaque": destaque, "nota": nota})

    def param(self, rotulo: str, valor: Any, tipo: str = "texto"):
        self.parametros.append({"rotulo": rotulo, "valor": _serializa(valor, tipo), "tipo": tipo})

    def tabela(self, titulo: str, colunas: list[tuple[str, str, str]], linhas: list[dict],
               recolhida: bool = False, total: dict | None = None):
        """colunas: [(chave, rotulo, tipo)]"""
        tipos = {c[0]: c[2] for c in colunas}
        def ser(l):
            return {k: _serializa(v, tipos.get(k, "texto")) for k, v in l.items()}
        self.tabelas.append({
            "titulo": titulo,
            "colunas": [{"chave": k, "rotulo": r, "tipo": t} for k, r, t in colunas],
            "linhas": [ser(l) for l in linhas],
            "total": ser(total) if total else None,
            "recolhida": recolhida,
        })

    def aviso(self, texto: str):
        if texto not in self.avisos:
            self.avisos.append(texto)

    def nota(self, texto: str):
        self.metodologia.append(texto)

    def para_dict(self) -> dict:
        return {
            "titulo": self.titulo,
            "resumo": self.resumo,
            "parametros": self.parametros,
            "tabelas": self.tabelas,
            "avisos": self.avisos,
            "metodologia": self.metodologia,
            "gerado_em": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }
