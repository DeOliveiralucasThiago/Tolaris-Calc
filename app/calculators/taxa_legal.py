"""Atualização pela Lei 14.905/2024: correção pelo IPCA e juros pela Taxa Legal (arts. 389 e 406 do CC).

Regras (Resolução CMN 5.171/2024, conferida no texto oficial):
  * Taxa legal mensal = max(fator Selic ÷ fator IPCA-15 − 1; 0), divulgada pelo BCB (SGS 29543).
  * Juros simples: taxas mensais somadas; fração pro rata = taxa do mês ÷ dias corridos do mês × dias apropriados.
  * Dias 30 e 31/08/2024 usam a taxa legal de agosto/2024 (art. 8º, parágrafo único).
  * Os juros incidem sobre o valor atualizado monetariamente (art. 7º).
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.indices import acumular, mes_anterior, mes_seguinte, resolver, ym
from ..core.numeros import UM, ZERO, arred, pct
from ..core.resultado import Resultado
from ._comuns import OPCOES_INDICES, avisar_serie
from .judicial_tjes import _periodo_meses

VIGENCIA = date(2024, 8, 30)          # Lei 14.905/2024: arts. 389 e 406 do CC valem a partir de 30/08/2024
ULTIMO_DIA_ANTIGO = date(2024, 8, 29)
MES_TRANSICAO = (2024, 8)             # meses até 08/2024: regime anterior; de 09/2024 em diante: IPCA

_ANTES = {"campo": "regime_anterior", "em": ["indice_juros"]}

META = {
    "slug": "taxa-legal",
    "titulo": "Taxa Legal (Lei 14.905/2024)",
    "categoria": "Cível",
    "icone": "percent",
    "descricao": "Correção pelo IPCA e juros pela Taxa Legal do art. 406 do Código Civil, com a transição do "
                 "regime anterior em 30/08/2024. Usa a série oficial do Banco Central.",
    "campos": [
        campo("valor", "Valor original (R$)", "dinheiro", obrigatorio=True, minimo=0.01, grupo="Débito"),
        campo("data_base", "Data-base da correção (vencimento)", "data", obrigatorio=True, grupo="Débito"),
        campo("data_juros", "Termo inicial dos juros de mora", "data", grupo="Débito",
              ajuda="Citação, vencimento ou outro marco. Se vazio, usa a data-base."),
        campo("data_calculo", "Data do cálculo", "data", obrigatorio=True, grupo="Débito"),
        campo("inicio", "Primeiro índice aplicado", "selecao", "mes_base", grupo="Correção monetária",
              opcoes=opcoes(("mes_base", "Mês da data-base"), ("mes_seguinte", "Mês seguinte ao da data-base"))),
        campo("regime_anterior", "Período até 29/08/2024 (regime anterior)", "selecao", "indice_juros",
              grupo="Regime anterior à lei", opcoes=opcoes(
                  ("indice_juros", "Índice de correção + juros simples (escolha abaixo)"),
                  ("selic", "SELIC (soma simples; já engloba correção e juros)")),
              ajuda="Só importa se o débito é anterior a 30/08/2024. O regime aplicável é tese do advogado."),
        campo("indice_anterior", "Índice de correção até 08/2024", "selecao", "INPC", grupo="Regime anterior à lei",
              mostrar_se=_ANTES, opcoes=opcoes(*[o for o in OPCOES_INDICES if o[0] != "SELIC"])),
        campo("juros_anterior", "Juros de mora até 29/08/2024 (% ao mês, simples)", "percentual", "1", minimo=0,
              maximo=100, grupo="Regime anterior à lei", mostrar_se=_ANTES),
        campo("multa", "Multa (%)", "percentual", "0", minimo=0, maximo=100, grupo="Multa e honorários",
              ajuda="Calculada sobre o valor corrigido + juros."),
        campo("hon_percentual", "Honorários advocatícios (%)", "percentual", "0", minimo=0, maximo=100,
              grupo="Multa e honorários", ajuda="Calculados sobre o débito atualizado (inclui a multa)."),
    ],
}


def _dias_no_mes(a: int, m: int) -> int:
    return calendar.monthrange(a, m)[1]


def _taxa_legal(serie_tl, inicio_excl: date, fim: date, res: Resultado):
    """Percentual acumulado (soma simples) de inicio_excl (exclusive) até fim (inclusive), pro rata por dia."""
    linhas, total, ausentes = [], ZERO, []
    dia = inicio_excl + timedelta(days=1)
    while dia <= fim:
        a, m = dia.year, dia.month
        ult = min(fim, date(a, m, _dias_no_mes(a, m)))
        dias = (ult - dia).days + 1
        tl = serie_tl.valores.get(f"{a:04d}-{m:02d}")
        if tl is None:
            ausentes.append(f"{m:02d}/{a}")
            tl = ZERO
        parte = tl * dias / _dias_no_mes(a, m)
        total += parte
        linhas.append({"mes": date(a, m, 1), "tl": tl, "dias": dias, "dim": _dias_no_mes(a, m), "parte": parte})
        dia = ult + timedelta(days=1)
    if ausentes:
        res.aviso("Taxa Legal sem valor divulgado para: " + ", ".join(ausentes) + ". Considerada 0,00% nesses meses.")
    return total, linhas


def atualizar(valor, base_dt: date, juros_dt: date, final: date, *, inicio: str, selic_modo: bool,
              indice_anterior: str, juros_anterior, res: Resultado) -> dict:
    """Motor reutilizável: corrige `valor` e apura os juros de uma obrigação, com a transição de 30/08/2024.
    Devolve os componentes sem arredondar, mais as memórias (para quem quiser exibi-las)."""
    primeiro = ym(base_dt) if inicio == "mes_base" else mes_seguinte(ym(base_dt))
    ultimo = mes_anterior(ym(final))
    fim_a = min(ultimo, MES_TRANSICAO)
    ini_b = max(primeiro, mes_seguinte(MES_TRANSICAO))

    fator_a, ac_a = UM, None
    if primeiro <= fim_a:
        nome_a = "SELIC" if selic_modo else indice_anterior
        s_a = resolver(nome_a)
        ac_a = acumular(s_a, primeiro, fim_a, "soma" if selic_modo else "composto")
        avisar_serie(res, s_a, ac_a)
        fator_a = ac_a.fator
    ac_b = None
    fator_b = UM
    if ini_b <= ultimo:
        s_b = resolver("IPCA")
        ac_b = acumular(s_b, ini_b, ultimo, "composto")
        avisar_serie(res, s_b, ac_b)
        fator_b = ac_b.fator
    corrigido = valor * fator_a * fator_b

    perc_antigo = ZERO
    if not selic_modo and juros_dt <= ULTIMO_DIA_ANTIGO:
        perc_antigo = _periodo_meses(juros_dt, min(final, ULTIMO_DIA_ANTIGO)) * pct(juros_anterior or ZERO)
    perc_tl, linhas_tl = ZERO, []
    if final >= VIGENCIA:
        serie_tl = resolver("TAXA_LEGAL")
        avisar_serie(res, serie_tl)
        pct_tl, linhas_tl = _taxa_legal(serie_tl, max(juros_dt, ULTIMO_DIA_ANTIGO), final, res)
        perc_tl = pct_tl / 100
    return {"corrigido": corrigido, "fator": fator_a * fator_b, "perc_antigo": perc_antigo, "perc_tl": perc_tl,
            "ac_a": ac_a, "ac_b": ac_b, "linhas_tl": linhas_tl,
            "juros_antigo": corrigido * perc_antigo, "juros_tl": corrigido * perc_tl}


def calcular(p: dict) -> Resultado:
    base_dt, final = p["data_base"], p["data_calculo"]
    juros_dt = p["data_juros"] or base_dt
    if base_dt > final:
        raise ErroDeValidacao("A data-base não pode ser posterior à data do cálculo.", "data_base")
    if juros_dt > final:
        raise ErroDeValidacao("O termo inicial dos juros não pode ser posterior à data do cálculo.", "data_juros")

    res = Resultado("Taxa Legal – Lei 14.905/2024")
    valor = p["valor"]
    selic_modo = p["regime_anterior"] == "selic"
    r = atualizar(valor, base_dt, juros_dt, final, inicio=p["inicio"], selic_modo=selic_modo,
                  indice_anterior=p["indice_anterior"], juros_anterior=p["juros_anterior"], res=res)
    ac_a, ac_b, linhas_tl = r["ac_a"], r["ac_b"], r["linhas_tl"]
    perc_antigo, perc_tl, fator = r["perc_antigo"], r["perc_tl"], r["fator"]
    if final < VIGENCIA:
        res.aviso("A data do cálculo é anterior a 30/08/2024: a Lei 14.905/2024 ainda não era aplicável e só o "
                  "regime anterior foi calculado.")
    corrigido = arred(r["corrigido"])
    juros_antigo = arred(corrigido * perc_antigo)
    juros_tl = arred(corrigido * perc_tl)
    juros = juros_antigo + juros_tl
    multa = arred((corrigido + juros) * pct(p["multa"] or ZERO))
    atualizado = corrigido + juros + multa
    hon = arred(atualizado * pct(p["hon_percentual"] or ZERO))
    total = atualizado + hon

    res.param("Valor original", valor, "dinheiro")
    res.param("Data-base", base_dt, "data")
    res.param("Juros a partir de", juros_dt, "data")
    res.param("Data do cálculo", final, "data")
    res.param("Regime até 29/08/2024", "SELIC (soma simples)" if selic_modo else
              f"{p['indice_anterior']} + juros simples de {p['juros_anterior']}% a.m.")

    res.kpi("Total atualizado", total, destaque=True)
    res.kpi("Valor corrigido", corrigido, nota=f"Fator {fator:.8f}")
    res.kpi("Juros – Taxa Legal", juros_tl, nota=f"{arred(perc_tl * 100, 6)}% acumulado (simples)".replace(".", ","))
    if juros_antigo or (not selic_modo and juros_dt <= ULTIMO_DIA_ANTIGO):
        res.kpi("Juros – regime anterior", juros_antigo, nota=f"{arred(perc_antigo * 100, 4)}%".replace(".", ","))
    if multa:
        res.kpi("Multa", multa)
    if hon:
        res.kpi("Honorários advocatícios", hon)

    if ac_a and ac_a.linhas:
        res.tabela("Memória da correção – regime anterior (até 08/2024)", [("mes", "Mês", "mes"),
                   ("indice", "Índice (%)", "taxa"), ("acumulado", "Acumulado (%)", "taxa")],
                   [{k: l[k] for k in ("mes", "indice", "acumulado")} for l in ac_a.linhas], recolhida=True)
    if ac_b and ac_b.linhas:
        res.tabela("Memória da correção – IPCA (de 09/2024)", [("mes", "Mês", "mes"), ("indice", "IPCA (%)", "taxa"),
                   ("acumulado", "Acumulado (%)", "taxa")],
                   [{k: l[k] for k in ("mes", "indice", "acumulado")} for l in ac_b.linhas], recolhida=True)
    if linhas_tl:
        res.tabela("Memória da Taxa Legal (juros simples, pro rata por dia)", [
            ("mes", "Mês", "mes"), ("tl", "Taxa legal do mês (%)", "taxa"), ("dias", "Dias apropriados", "inteiro"),
            ("dim", "Dias do mês", "inteiro"), ("parte", "Juros apropriados (%)", "taxa")], linhas_tl,
            recolhida=len(linhas_tl) > 18,
            total={"mes": "Total", "parte": perc_tl * 100})

    res.nota("Taxa legal mensal (Res. CMN 5.171/2024): max(fator Selic do mês anterior ÷ fator IPCA-15 do mês anterior − 1; 0). "
             "Valores oficiais divulgados pelo Banco Central (SGS 29543).")
    res.nota("Juros simples: taxas mensais somadas; fração do mês = taxa do mês ÷ dias corridos do mês × dias apropriados. "
             "A contagem exclui o dia do termo inicial e inclui o da data do cálculo; dias 30 e 31/08/2024 usam a taxa de agosto/2024.")
    res.nota("Os juros incidem sobre o valor atualizado monetariamente (art. 7º da Resolução), isto é, sobre o valor corrigido até a data do cálculo.")
    res.nota("Correção monetária: regime anterior até 08/2024 e IPCA (art. 389, parágrafo único, do CC) de 09/2024 em diante, "
             "em base mensal. Agosto/2024 é tratado integralmente no regime anterior; o mês em que a lei passou a valer (30/08) "
             "é uma escolha de calendário a conferir com o juízo.")
    res.nota("Antes de 30/08/2024 a taxa de juros e o índice aplicáveis (Selic, 1% a.m., INPC etc.) dependem da natureza do débito e "
             "do entendimento do juízo; por isso são escolhas suas.")
    return res
