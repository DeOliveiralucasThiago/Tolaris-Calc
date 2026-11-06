"""Atualização monetária de débitos judiciais, no modelo da Corregedoria-Geral da Justiça do TJES.

Estrutura reproduzida do demonstrativo oficial (conferido contra um cálculo real do TJES):
  principal corrigido + juros = valor atualizado
  + custas corrigidas + multa sobre o principal corrigido = Subtotal 1
  - abatimento = Total 1 (débito atualizado)
  honorários sobre o Total 1 = Total 2        Total geral = Total 1 + Total 2
"""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.indices import acumular, mes_anterior, resolver, ym
from ..core.numeros import ZERO, arred, pct
from ..core.resultado import Resultado
from ._comuns import CAMPO_INDICES_MANUAIS, avisar_serie

INICIO_INPC = date(1999, 7, 1)   # a nota do TJES: de 07/99 em diante o índice é o INPC/IBGE
VIRADA_JUROS = date(2003, 1, 11)  # Lei 10.406/02: 0,5% a.m. até 10/01/2003; 1% a.m. a partir de 11/01/2003

comp = lambda nome, rot: campo(nome, rot, "booleano", False, grupo="Composição do cálculo", composicao=True)  # noqa: E731
_C = lambda n: {"campo": n, "em": [True]}  # noqa: E731

META = {
    "slug": "debitos-judiciais",
    "titulo": "Débitos judiciais (modelo TJES)",
    "categoria": "Judicial",
    "icone": "scale",
    "descricao": "Atualização de débitos judiciais no padrão da Corregedoria-Geral da Justiça do TJES: marque os "
                 "componentes do cálculo e informe só os dados necessários.",
    "campos": [
        comp("usa_correcao", "Correção monetária"),
        comp("usa_juros", "Juros moratórios"),
        comp("usa_custas", "Custas processuais"),
        comp("usa_hon", "Honorários advocatícios"),
        comp("usa_multa", "Multa"),
        comp("usa_523", "Multa de 10% prevista no art. 523, §1º, do CPC"),
        comp("usa_abater", "Abater valor"),

        campo("principal", "Principal – valor em moeda (R$)", "dinheiro", obrigatorio=True, minimo=0.01, grupo="Principal"),

        campo("corr_data", "Data inicial (dd/mm/aaaa)", "data", obrigatorio=True, grupo="Correção monetária",
              mostrar_se=_C("usa_correcao")),
        campo("corr_fator", "Fator de atualização", "selecao", "tjes", grupo="Correção monetária",
              mostrar_se=_C("usa_correcao"), opcoes=opcoes(
                  ("tjes", "Índice do TJES (INPC/IBGE desde 07/1999)"),
                  ("manual", "Fator informado manualmente (ex.: datas anteriores a 07/1999)")),
              ajuda="Para datas anteriores a 07/1999 a tabela do TJES usa índices históricos que este sistema ainda "
                    "não possui: informe o fator da tabela oficial."),
        campo("corr_fator_manual", "Fator de correção (ex.: 1,1167325072)", "numero", minimo=0.0000001,
              grupo="Correção monetária", obrigatorio=True,
              mostrar_se={"campo": "corr_fator", "em": ["manual"]}),

        campo("juros_tipo", "Tipo de juros", "selecao", "legais", grupo="Juros moratórios", mostrar_se=_C("usa_juros"),
              opcoes=opcoes(("legais", "Juros Legais (Código Civil: 0,5% até 10/01/2003; 1% desde 11/01/2003)"),
                            ("fixos", "Taxa fixa mensal simples (informada)"))),
        campo("juros_taxa", "Taxa de juros (% ao mês)", "percentual", minimo=0, maximo=100, obrigatorio=True,
              grupo="Juros moratórios", mostrar_se={"campo": "juros_tipo", "em": ["fixos"]}),
        campo("juros_data", "Data inicial (dd/mm/aaaa)", "data", obrigatorio=True, grupo="Juros moratórios",
              mostrar_se=_C("usa_juros")),

        campo("custas_valor", "Custas pagas – valor (R$)", "dinheiro", obrigatorio=True, minimo=0.01,
              grupo="Custas pagas", mostrar_se=_C("usa_custas")),
        campo("custas_data", "Data inicial (dd/mm/aaaa)", "data", obrigatorio=True, grupo="Custas pagas",
              mostrar_se=_C("usa_custas")),

        campo("multa_perc", "Multa sobre o principal corrigido (%)", "percentual", obrigatorio=True, minimo=0,
              maximo=100, grupo="Multa", mostrar_se=_C("usa_multa")),
        campo("abater_valor", "Valor a abater (R$)", "dinheiro", obrigatorio=True, minimo=0.01, grupo="Abatimento",
              mostrar_se=_C("usa_abater"),
              ajuda="Deduzido do Subtotal 1, no valor informado (sem correção)."),
        campo("hon_perc", "Honorários sobre o débito atualizado (%)", "percentual", obrigatorio=True, minimo=0,
              maximo=100, grupo="Honorários advocatícios", mostrar_se=_C("usa_hon")),

        campo("data_final", "Data final do cálculo (dd/mm/aaaa)", "data", grupo="Fechamento",
              ajuda="Opcional. Se vazia, usa a data de hoje."),
        CAMPO_INDICES_MANUAIS,
    ],
}


def _periodo_meses(ini: date, fim: date) -> "Decimal":  # noqa: F821
    """Meses completos + dias restantes ÷ 30."""
    if fim <= ini:
        return ZERO
    d = relativedelta(fim, ini)
    meses = d.years * 12 + d.months
    dias = (fim - (ini + relativedelta(months=meses))).days
    return meses + arred(dias, 10) / 30


def _fator(serie, desde: date, ate: date):
    return acumular(serie, ym(desde), mes_anterior(ym(ate)))


def calcular(p: dict) -> Resultado:
    final = p["data_final"] or date.today()
    res = Resultado("Atualização monetária de débitos judiciais")
    principal = p["principal"]
    linhas: list[dict] = []
    add = lambda d, v=None, negrito=False: linhas.append({"d": d, "v": v, "n": negrito})  # noqa: E731

    # ---- correção
    fator = None
    corrigido = principal
    serie = None
    if p["usa_correcao"]:
        if p["corr_data"] > final:
            raise ErroDeValidacao("A data inicial da correção não pode ser posterior à data final.", "corr_data")
        if p["corr_fator"] == "manual":
            fator = p["corr_fator_manual"]
        else:
            if p["corr_data"] < INICIO_INPC:
                raise ErroDeValidacao("Para datas anteriores a 07/1999 informe o fator da tabela do TJES "
                                      "(opção “Fator informado manualmente”).", "corr_fator")
            serie = resolver("INPC", p["indices_manuais"])
            avisar_serie(res, serie)
            ac = _fator(serie, p["corr_data"], final)
            avisar_serie(res, serie, ac)
            fator = ac.fator
            res.tabela("Memória da correção – INPC/IBGE", [("mes", "Mês", "mes"), ("indice", "INPC do mês (%)", "taxa"),
                       ("acumulado", "Acumulado (%)", "taxa"), ("fator", "Fator", "fator")],
                       [{k: l[k] for k in ("mes", "indice", "acumulado", "fator")} for l in ac.linhas], recolhida=True)
        corrigido = arred(principal * fator)

    # ---- juros sobre o principal corrigido
    juros = ZERO
    rot_juros = ""
    if p["usa_juros"]:
        j0 = p["juros_data"]
        if j0 > final:
            raise ErroDeValidacao("A data inicial dos juros não pode ser posterior à data final.", "juros_data")
        if p["juros_tipo"] == "legais":
            corte = min(max(VIRADA_JUROS, j0), final)
            m1 = _periodo_meses(j0, corte) if j0 < VIRADA_JUROS else ZERO
            m2 = _periodo_meses(max(j0, VIRADA_JUROS), final)
            perc = m1 * pct("0.5") + m2 * pct(1)
            rot_juros = "Juros do Código Civil"
        else:
            m = _periodo_meses(j0, final)
            perc = m * pct(p["juros_taxa"])
            rot_juros = f"Juros de {p['juros_taxa']}% a.m."
        juros = arred(corrigido * perc)
        rot_juros += f" ({str(arred(perc * 100)).replace('.', ',')} %) do período"
    valor_atualizado = corrigido + juros

    # ---- custas
    custas = custas_corr = ZERO
    if p["usa_custas"]:
        custas = p["custas_valor"]
        if p["custas_data"] > final:
            raise ErroDeValidacao("A data das custas não pode ser posterior à data final.", "custas_data")
        if p["usa_correcao"]:
            if p["corr_fator"] == "manual":
                custas_corr = arred(custas * fator)
            else:
                custas_corr = arred(custas * _fator(serie, p["custas_data"], final).fator)
        else:
            custas_corr = custas

    multa = arred(corrigido * pct(p["multa_perc"])) if p["usa_multa"] else ZERO
    subtotal1 = valor_atualizado + custas_corr + multa
    abatimento = p["abater_valor"] if p["usa_abater"] else ZERO
    total1 = subtotal1 - abatimento
    multa523 = arred(total1 * pct(10)) if p["usa_523"] else ZERO
    hon = arred(total1 * pct(p["hon_perc"])) if p["usa_hon"] else ZERO
    total2 = hon
    geral = total1 + total2 + multa523

    # ---- demonstrativo (mesma ordem do TJES)
    d = lambda v: v if v else None  # noqa: E731
    add("Operações aritméticas", None, True)
    add("Principal" + (" corrigido" if p["usa_correcao"] else ""), corrigido)
    if p["usa_juros"]:
        add(rot_juros, juros)
    add(f"Valor atualizado até {final:%d/%m/%Y}", valor_atualizado)
    if p["usa_custas"]:
        add("Custas pagas corrigidas a serem ressarcidas" + (f" (índice {fator:.10f})".replace(".", ",") if p["usa_correcao"] else ""), custas_corr)
    if p["usa_multa"]:
        add(f"Multa sobre o principal corrigido ({p['multa_perc']}%)", multa)
    add("Subtotal 1", subtotal1, True)
    if p["usa_abater"]:
        add("(–) Valor abatido", -abatimento)
    add("Total 1 (DÉBITO ATUALIZADO)", total1, True)
    if p["usa_hon"]:
        add(f"Honorários sobre o débito atualizado ({p['hon_perc']}%)", hon)
        add("Total 2 (HONORÁRIOS ADVOCATÍCIOS)", total2, True)
    if p["usa_523"]:
        add("Multa de 10% sobre o débito atualizado (art. 523, §1º, CPC)", multa523)
    add("Total Geral", geral, True)

    res.param("Valor do principal", principal, "dinheiro")
    if p["usa_correcao"]:
        res.param(f"Fator de correção monetária desde {p['corr_data']:%d/%m/%Y}", f"{fator:.10f}".replace(".", ","))
    if p["usa_juros"]:
        res.param("Juros a partir de", p["juros_data"], "data")
    if p["usa_custas"]:
        res.param(f"Custas pagas em {p['custas_data']:%d/%m/%Y}", custas, "dinheiro")
    res.param("Valores atualizados até", final, "data")

    res.kpi("Total geral", geral, destaque=True)
    res.kpi("Débito atualizado (Total 1)", total1)
    if p["usa_correcao"]:
        res.kpi("Principal corrigido", corrigido, nota=f"Fator {fator:.10f}".replace(".", ","))
    if p["usa_juros"]:
        res.kpi("Juros moratórios", juros)
    if p["usa_hon"]:
        res.kpi("Honorários advocatícios (Total 2)", total2)

    res.tabela("Demonstrativo", [("d", "Descrição", "texto"), ("v", "Valor", "dinheiro")],
               [{"d": l["d"], "v": l["v"]} for l in linhas])

    if p["usa_523"]:
        res.aviso("Multa do art. 523 aplicada sobre o Total 1: a posição dessa linha no demonstrativo do TJES "
                  "ainda não foi conferida. Verifique antes de usar.")
    if p["usa_abater"]:
        res.aviso("O abatimento é deduzido do Subtotal 1 no valor informado, sem correção: regra ainda não "
                  "conferida contra a calculadora do TJES.")
    res.nota("Fator de correção: encadeamento de índices da Tabela de Atualização Monetária de Débitos Judiciais do "
             "TJES; a partir de 07/1999 o índice é o INPC/IBGE, acumulado de forma composta do mês da data inicial "
             "até o último mês fechado anterior à data final.")
    res.nota("Juros Legais: 0,5% ao mês até 10/01/2003 e 1% ao mês de 11/01/2003 em diante (Lei 10.406/02), simples, "
             "pro rata (meses completos + dias ÷ 30), sobre o principal corrigido.")
    res.nota("Cada linha é arredondada ao centavo e os totais somam as linhas exibidas, como no demonstrativo oficial.")
    return res
