"""Índices econômicos do Banco Central (SGS) com cache em memória e em disco.

* Se a API do BCB falhar, usa o último cache em disco e avisa o usuário.
* Se não houver nada, levanta IndiceIndisponivel (nunca inventa valores).
* O usuário pode informar/sobrescrever meses manualmente em qualquer cálculo.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx

from .erros import IndiceIndisponivel
from .numeros import UM, ZERO, D, pct

DATA_DIR = Path(os.environ.get("TOLARIS_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
CACHE_DIR = DATA_DIR / "cache"
TTL_SEGUNDOS = 6 * 3600
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=01/01/1994"


@dataclass(frozen=True)
class DefSerie:
    codigo: int
    nome: str
    descricao: str
    acumulo: str = "composto"  # "composto" (produto) ou "soma" (SELIC, prática forense)
    selecionavel: bool = True  # aparece nas listas de índices de correção das calculadoras
    unidade: str = "%"         # "%" (variação mensal), "R$" (valor vigente) ou "taxa" (taxa média, % a.m.)


# Códigos conferidos diretamente na API do BCB (IPCA-E = SGS 10764, que coincide com o IPCA-15).
SERIES: dict[str, DefSerie] = {
    "IPCA": DefSerie(433, "IPCA", "IPCA – IBGE, variação mensal"),
    "INPC": DefSerie(188, "INPC", "INPC – IBGE, variação mensal"),
    "IPCA-E": DefSerie(10764, "IPCA-E", "IPCA-E – IBGE, variação mensal"),
    "IGP-M": DefSerie(189, "IGP-M", "IGP-M – FGV, variação mensal"),
    "INCC": DefSerie(192, "INCC", "INCC – FGV, variação mensal"),
    "SELIC": DefSerie(4390, "SELIC", "Taxa Selic acumulada no mês", acumulo="soma"),
    # Taxa legal (art. 406 do CC; Res. CMN 5.171/2024): max(fator Selic ÷ fator IPCA-15 − 1; 0), divulgada pelo BCB
    "TAXA_LEGAL": DefSerie(29543, "TAXA_LEGAL", "Taxa Legal – art. 406 do Código Civil (juros, % ao mês)",
                           acumulo="soma", selecionavel=False),
    "SALARIO_MINIMO": DefSerie(1619, "SALARIO_MINIMO", "Salário mínimo vigente no mês (R$)", acumulo="soma",
                               selecionavel=False, unidade="R$"),
    # Taxa média de mercado: operações de crédito com recursos livres, pessoas físicas, cartão rotativo (% a.m.)
    "TAXA_MEDIA_ROTATIVO": DefSerie(25477, "TAXA_MEDIA_ROTATIVO",
                                    "Taxa média de mercado – cartão de crédito rotativo, pessoa física (% ao mês)",
                                    acumulo="soma", selecionavel=False, unidade="taxa"),
}

_lock = threading.Lock()
_memoria: dict[str, tuple[float, "Serie"]] = {}


@dataclass
class Serie:
    nome: str
    valores: dict[str, Decimal]  # "AAAA-MM" -> variação percentual do mês
    origem: str                  # "bcb" | "cache" | "manual"
    atualizado_em: str

    @property
    def ultimo_mes(self) -> str | None:
        return max(self.valores) if self.valores else None


def _arquivo(nome: str) -> Path:
    return CACHE_DIR / f"{nome.replace('/', '_')}.json"


def _baixar(defn: DefSerie) -> dict[str, Decimal]:
    ultimo_erro: Exception | None = None
    for tentativa in range(3):
        try:
            r = httpx.get(URL.format(codigo=defn.codigo), timeout=20, follow_redirects=True)
            r.raise_for_status()
            dados = r.json()
            valores: dict[str, Decimal] = {}
            for item in dados:
                dia, mes, ano = item["data"].split("/")
                valores[f"{ano}-{mes}"] = D(item["valor"])
            if not valores:
                raise ValueError("série vazia")
            return valores
        except Exception as exc:  # rede, JSON, HTTP...
            ultimo_erro = exc
            time.sleep(0.6 * (tentativa + 1))
    raise IndiceIndisponivel(str(ultimo_erro))


def _ler_disco(nome: str) -> Serie | None:
    try:
        bruto = json.loads(_arquivo(nome).read_text(encoding="utf-8"))
        return Serie(nome, {k: D(v) for k, v in bruto["valores"].items()}, "cache", bruto["atualizado_em"])
    except (OSError, ValueError, KeyError):
        return None


def _gravar_disco(serie: Serie) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _arquivo(serie.nome).write_text(json.dumps(
            {"atualizado_em": serie.atualizado_em, "valores": {k: str(v) for k, v in serie.valores.items()}}),
            encoding="utf-8")
    except OSError:
        pass  # disco somente leitura: segue só com memória


def obter_serie(nome: str, forcar: bool = False) -> Serie:
    if nome not in SERIES:
        raise IndiceIndisponivel(f"Índice desconhecido: {nome}")
    with _lock:
        em_memoria = _memoria.get(nome)
        if em_memoria and not forcar and time.time() - em_memoria[0] < TTL_SEGUNDOS:
            return em_memoria[1]
        try:
            valores = _baixar(SERIES[nome])
            serie = Serie(nome, valores, "bcb", datetime.now().strftime("%d/%m/%Y %H:%M"))
            _gravar_disco(serie)
        except IndiceIndisponivel:
            serie = _ler_disco(nome)
            if serie is None:
                raise IndiceIndisponivel(
                    f"Não foi possível consultar o índice {nome} no Banco Central e não há cópia salva. "
                    "Tente novamente em instantes ou informe os índices manualmente.")
        _memoria[nome] = (time.time(), serie)
        return serie


def resolver(nome: str, manuais: list[dict] | None = None) -> Serie:
    """Série oficial + meses informados manualmente (que prevalecem). Se o BCB estiver
    inacessível mas o usuário informou todos os meses necessários, o cálculo continua."""
    try:
        base = obter_serie(nome)
    except IndiceIndisponivel:
        if not manuais:
            raise
        base = Serie(nome, {}, "manual", datetime.now().strftime("%d/%m/%Y %H:%M"))
    if not manuais:
        return base
    valores = dict(base.valores)
    for m in manuais:
        if m.get("mes") and m.get("indice") is not None:
            valores[m["mes"].strftime("%Y-%m")] = m["indice"]
    return Serie(nome, valores, base.origem, base.atualizado_em)


# ---------------------------------------------------------------- acumulação

def ym(d: date) -> tuple[int, int]:
    return d.year, d.month


def ym_str(t: tuple[int, int]) -> str:
    return f"{t[0]:04d}-{t[1]:02d}"


def mes_seguinte(t: tuple[int, int]) -> tuple[int, int]:
    return (t[0] + 1, 1) if t[1] == 12 else (t[0], t[1] + 1)


def mes_anterior(t: tuple[int, int]) -> tuple[int, int]:
    return (t[0] - 1, 12) if t[1] == 1 else (t[0], t[1] - 1)


def meses_entre(ini: tuple[int, int], fim: tuple[int, int]):
    atual = ini
    while atual <= fim:
        yield atual
        atual = mes_seguinte(atual)


@dataclass
class Acumulado:
    fator: Decimal                 # multiplicador do principal (1 + acumulado)
    linhas: list[dict]             # memória mês a mês
    ausentes: list[str]            # meses sem índice (tratados como 0%)

    @property
    def percentual(self) -> Decimal:
        return (self.fator - UM) * 100


def acumular(serie: Serie, ini: tuple[int, int], fim: tuple[int, int], modo: str = "composto") -> Acumulado:
    """Acumula os índices de `ini` a `fim` (inclusive). modo: composto | soma."""
    if ini > fim:
        return Acumulado(UM, [], [])
    fator, soma = UM, ZERO
    linhas, ausentes = [], []
    for t in meses_entre(ini, fim):
        chave = ym_str(t)
        indice = serie.valores.get(chave)
        if indice is None:
            ausentes.append(f"{t[1]:02d}/{t[0]}")
            indice = ZERO
        fator *= UM + pct(indice)
        soma += pct(indice)
        acum = fator if modo == "composto" else UM + soma
        linhas.append({"mes": date(t[0], t[1], 1), "indice": indice, "fator": acum,
                       "acumulado": (acum - UM) * 100, "oficial": chave in serie.valores})
    final = fator if modo == "composto" else UM + soma
    return Acumulado(final, linhas, ausentes)
