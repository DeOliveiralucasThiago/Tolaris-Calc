"""Definição declarativa de campos e validação/conversão dos parâmetros.

Cada calculadora descreve seus campos; o front-end monta o formulário a partir
dessa descrição e o back-end valida com a mesma fonte de verdade.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .erros import ErroDeValidacao


def campo(nome, rotulo, tipo, padrao=None, **extra) -> dict:
    """tipo: dinheiro | percentual | numero | inteiro | data | selecao | booleano | tabela | datas"""
    c = {"nome": nome, "rotulo": rotulo, "tipo": tipo, "padrao": padrao}
    c.update(extra)  # obrigatorio, ajuda, opcoes, minimo, maximo, mostrar_se, grupo, colunas
    return c


def opcoes(*pares) -> list[dict]:
    return [{"valor": v, "rotulo": r} for v, r in pares]


def _decimal(valor, c) -> Decimal:
    if isinstance(valor, str):
        valor = valor.strip().replace(" ", "")
        if "," in valor:  # aceita 1.234,56
            valor = valor.replace(".", "").replace(",", ".")
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        raise ErroDeValidacao(f"“{c['rotulo']}”: valor numérico inválido.", c["nome"])
    if not d.is_finite():
        raise ErroDeValidacao(f"“{c['rotulo']}”: valor inválido.", c["nome"])
    return d


def _data(valor, c) -> date:
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        raise ErroDeValidacao(f"“{c['rotulo']}”: data inválida.", c["nome"])


def _vazio(v) -> bool:
    return v is None or v == "" or v == []


def _visivel(c, bruto, convertido) -> bool:
    cond = c.get("mostrar_se")
    if not cond:
        return True
    atual = convertido.get(cond["campo"], bruto.get(cond["campo"]))
    return atual in cond["em"]


def converter(campos: list[dict], bruto: dict) -> dict[str, Any]:
    """Valida e converte. Campos ocultos pela condição `mostrar_se` são ignorados."""
    out: dict[str, Any] = {}
    for c in campos:
        nome, tipo = c["nome"], c["tipo"]
        if not _visivel(c, bruto, out):
            out[nome] = None
            continue
        v = bruto.get(nome, c.get("padrao"))
        if tipo == "booleano":
            out[nome] = bool(v)
            continue
        if tipo == "tabela":
            out[nome] = _tabela(c, v or [])
            if c.get("obrigatorio") and not out[nome]:
                raise ErroDeValidacao(f"“{c['rotulo']}”: informe ao menos uma linha.", nome)
            continue
        if tipo == "datas":
            out[nome] = [_data(x, c) for x in (v or []) if not _vazio(x)]
            continue
        if _vazio(v):
            if c.get("obrigatorio"):
                raise ErroDeValidacao(f"Preencha o campo “{c['rotulo']}”.", nome)
            out[nome] = None
            continue
        if tipo in ("dinheiro", "percentual", "numero"):
            d = _decimal(v, c)
            _limites(d, c)
            out[nome] = d
        elif tipo == "inteiro":
            d = _decimal(v, c)
            if d != d.to_integral_value():
                raise ErroDeValidacao(f"“{c['rotulo']}”: informe um número inteiro.", nome)
            _limites(d, c)
            out[nome] = int(d)
        elif tipo == "data":
            out[nome] = _data(v, c)
        elif tipo == "selecao":
            validos = {o["valor"] for o in c["opcoes"]}
            if v not in validos:
                raise ErroDeValidacao(f"“{c['rotulo']}”: opção inválida.", nome)
            out[nome] = v
        else:
            out[nome] = v
    return out


def _limites(d: Decimal, c: dict):
    mn, mx = c.get("minimo"), c.get("maximo")
    if mn is not None and d < Decimal(str(mn)):
        raise ErroDeValidacao(f"“{c['rotulo']}” deve ser no mínimo {mn}.".replace(".", ","), c["nome"])
    if mx is not None and d > Decimal(str(mx)):
        raise ErroDeValidacao(f"“{c['rotulo']}” deve ser no máximo {mx}.".replace(".", ","), c["nome"])


def _tabela(c: dict, linhas: list) -> list[dict]:
    colunas = c["colunas"]
    saida = []
    for i, linha in enumerate(linhas, start=1):
        if all(_vazio(linha.get(col["nome"])) for col in colunas):
            continue  # linha totalmente em branco
        item = {}
        for col in colunas:
            v = linha.get(col["nome"])
            rot = f"{c['rotulo']}, linha {i}, “{col['rotulo']}”"
            if _vazio(v):
                if col.get("obrigatorio", True) and col["tipo"] != "texto":
                    raise ErroDeValidacao(f"{rot}: preencha o valor.", c["nome"])
                item[col["nome"]] = None
            elif col["tipo"] == "data":
                item[col["nome"]] = _data(v, {"rotulo": rot, "nome": c["nome"]})
            elif col["tipo"] in ("dinheiro", "percentual", "numero"):
                item[col["nome"]] = _decimal(v, {"rotulo": rot, "nome": c["nome"]})
            elif col["tipo"] == "selecao":
                validos = {o["valor"] for o in col["opcoes"]}
                if v not in validos:
                    raise ErroDeValidacao(f"{rot}: opção inválida.", c["nome"])
                item[col["nome"]] = v
            else:
                item[col["nome"]] = str(v)[:200]
        saida.append(item)
    if len(saida) > 5000:
        raise ErroDeValidacao(f"“{c['rotulo']}”: no máximo 5.000 linhas.", c["nome"])
    return saida
