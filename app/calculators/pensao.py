"""Débito de pensão alimentícia (execução de alimentos): parcelas vencidas, correção, juros e abatimentos."""
from __future__ import annotations

import calendar
from datetime import date

from dateutil.relativedelta import relativedelta

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.indices import acumular, mes_anterior, mes_seguinte, resolver, ym
from ..core.numeros import ZERO, arred, pct
from ..core.resultado import Resultado
from ._comuns import OPCOES_INDICES, avisar_serie
from .judicial_tjes import _periodo_meses
from .taxa_legal import atualizar

MAX_PARCELAS = 600
_FIXO = {"campo": "valor_tipo", "em": ["fixo"]}
_PCT = {"campo": "valor_tipo", "em": ["pct_sm"]}
_LEI = {"campo": "regime", "em": ["lei14905"]}

META = {
    "slug": "pensao-alimenticia",
    "titulo": "Pensão alimentícia",
    "categoria": "Família",
    "icone": "scale",
    "descricao": "Débito de pensão em atraso: gera as parcelas mensais, corrige e aplica juros parcela por parcela, "
                 "abate pagamentos e separa o débito que autoriza a prisão civil (Súmula 309 do STJ).",
    "campos": [
        campo("valor_tipo", "Como a pensão foi fixada", "selecao", "fixo", grupo="Pensão", opcoes=opcoes(
            ("fixo", "Valor fixo mensal (R$)"), ("pct_sm", "Percentual do salário mínimo"))),
        campo("valor_mensal", "Valor mensal (R$)", "dinheiro", obrigatorio=True, minimo=0.01, grupo="Pensão",
              mostrar_se=_FIXO),
        campo("pct_sm", "Percentual do salário mínimo (%)", "percentual", obrigatorio=True, minimo=0.01, maximo=1000,
              grupo="Pensão", mostrar_se=_PCT,
              ajuda="Usa o salário mínimo vigente no mês de cada vencimento (série do Banco Central)."),
        campo("primeiro_venc", "Primeiro vencimento em atraso", "data", obrigatorio=True, grupo="Parcelas",
              ajuda="O dia desta data é o dia de vencimento de todas as parcelas (ex.: dia 10)."),
        campo("ultimo_venc", "Último vencimento a cobrar", "data", grupo="Parcelas",
              ajuda="Opcional. Se vazio, vai até a data do cálculo."),
        campo("data_calculo", "Data do cálculo", "data", obrigatorio=True, grupo="Parcelas"),
        campo("extras", "Parcelas extras (13º, verbas pontuais…)", "tabela", [], grupo="Parcelas", colunas=[
            {"nome": "data", "rotulo": "Vencimento", "tipo": "data"},
            {"nome": "valor", "rotulo": "Valor (R$)", "tipo": "dinheiro"},
            {"nome": "descricao", "rotulo": "Descrição", "tipo": "texto", "obrigatorio": False}]),
        campo("pagamentos", "Pagamentos já realizados", "tabela", [], grupo="Pagamentos", colunas=[
            {"nome": "data", "rotulo": "Data", "tipo": "data"},
            {"nome": "valor", "rotulo": "Valor (R$)", "tipo": "dinheiro"}]),
        campo("abatimento", "Como abater os pagamentos", "selecao", "atualizado", grupo="Pagamentos", opcoes=opcoes(
            ("atualizado", "Pagamento corrigido até a data do cálculo"), ("nominal", "Valor nominal pago")),
            ajuda="Os pagamentos são deduzidos do total atualizado; não há imputação a parcelas específicas."),
        campo("regime", "Critério de juros e correção", "selecao", "indice_juros", grupo="Correção e juros", opcoes=opcoes(
            ("indice_juros", "Índice escolhido + juros simples fixos"),
            ("lei14905", "Lei 14.905/2024 (IPCA + Taxa Legal desde 30/08/2024)"))),
        campo("indice", "Índice de correção", "selecao", "INPC", grupo="Correção e juros",
              opcoes=opcoes(*[o for o in OPCOES_INDICES if o[0] != "SELIC"]),
              ajuda="No critério da Lei 14.905, vale até 08/2024; depois o IPCA."),
        campo("inicio", "Primeiro índice aplicado", "selecao", "mes_base", grupo="Correção e juros", opcoes=opcoes(
            ("mes_base", "Mês do vencimento"), ("mes_seguinte", "Mês seguinte ao do vencimento"))),
        campo("juros_taxa", "Juros de mora (% ao mês, simples)", "percentual", "1", minimo=0, maximo=100,
              grupo="Correção e juros",
              ajuda="Contados do vencimento de cada parcela, sobre o valor corrigido. No critério da Lei 14.905 "
                    "vale até 29/08/2024."),
        campo("data_ajuizamento", "Data do ajuizamento da execução", "data", grupo="Prisão civil e rito",
              ajuda="Opcional. Separa as 3 parcelas anteriores ao ajuizamento e as vencidas depois (Súmula 309/STJ) "
                    "das demais parcelas."),
        campo("multa_523", "Multa de 10% (art. 523, §1º, CPC)", "booleano", False, grupo="Prisão civil e rito"),
        campo("hon_523", "Honorários de 10% (art. 523, §1º, CPC)", "booleano", False, grupo="Prisão civil e rito"),
    ],
}


def _vencimentos(primeiro: date, limite: date) -> list[date]:
    """Um vencimento por mês, no mesmo dia do primeiro (ajustado ao último dia em meses mais curtos)."""
    datas = []
    for k in range(MAX_PARCELAS + 1):
        ref = date(primeiro.year, primeiro.month, 1) + relativedelta(months=k)
        d = date(ref.year, ref.month, min(primeiro.day, calendar.monthrange(ref.year, ref.month)[1]))
        if d > limite:
            return datas
        datas.append(d)
    raise ErroDeValidacao(f"No máximo {MAX_PARCELAS} parcelas por cálculo.", "primeiro_venc")


def calcular(p: dict) -> Resultado:
    final = p["data_calculo"]
    primeiro = p["primeiro_venc"]
    limite = min(p["ultimo_venc"] or final, final)
    if primeiro > limite:
        raise ErroDeValidacao("O primeiro vencimento não pode ser posterior ao último vencimento / data do cálculo.",
                              "primeiro_venc")
    if p["valor_tipo"] == "pct_sm" and primeiro < date(1994, 7, 1):
        raise ErroDeValidacao("O cálculo por % do salário mínimo vale a partir de 07/1994 (Plano Real).", "primeiro_venc")

    res = Resultado("Débito de pensão alimentícia")
    lei = p["regime"] == "lei14905"
    taxa = p["juros_taxa"] or ZERO

    serie_idx = None
    if not lei:
        serie_idx = resolver(p["indice"])
        avisar_serie(res, serie_idx)

    def atualiza(valor, venc):
        """(corrigido, juros, fator) sem arredondar."""
        if lei:
            r = atualizar(valor, venc, venc, final, inicio=p["inicio"], selic_modo=False,
                          indice_anterior=p["indice"], juros_anterior=taxa, res=res)
            return r["corrigido"], r["juros_antigo"] + r["juros_tl"], r["fator"]
        ini = ym(venc) if p["inicio"] == "mes_base" else mes_seguinte(ym(venc))
        ac = acumular(serie_idx, ini, mes_anterior(ym(final)))
        avisar_serie(res, serie_idx, ac)
        corrigido = valor * ac.fator
        return corrigido, corrigido * _periodo_meses(venc, final) * pct(taxa), ac.fator

    # salário mínimo
    sm = None
    if p["valor_tipo"] == "pct_sm":
        sm = resolver("SALARIO_MINIMO")
        avisar_serie(res, sm)

    def valor_do_mes(venc: date):
        if p["valor_tipo"] == "fixo":
            return p["valor_mensal"]
        chave = f"{venc.year:04d}-{venc.month:02d}"
        validos = [k for k in sm.valores if k <= chave]
        if not validos:
            raise ErroDeValidacao(f"Salário mínimo não encontrado para {venc.month:02d}/{venc.year}.", "primeiro_venc")
        if chave not in sm.valores:
            res.aviso(f"Salário mínimo de {venc.month:02d}/{venc.year} ainda não divulgado; usado o último disponível "
                      f"({validos and max(validos)}).")
        return arred(pct(p["pct_sm"]) * sm.valores[max(validos)])

    itens = [(d, valor_do_mes(d), "Mensal") for d in _vencimentos(primeiro, limite)]
    for e in p["extras"]:
        if e["data"] <= final:
            itens.append((e["data"], e["valor"], e.get("descricao") or "Extra"))
    itens.sort(key=lambda t: t[0])
    if not itens:
        raise ErroDeValidacao("Nenhuma parcela vencida até a data do cálculo.", "primeiro_venc")

    # classificação pela Súmula 309/STJ
    classe = {}
    if p["data_ajuizamento"]:
        aj = p["data_ajuizamento"]
        antes = [i for i, t in enumerate(itens) if t[0] < aj]
        tres = set(antes[-3:])
        for i, t in enumerate(itens):
            classe[i] = "Prisão" if (t[0] >= aj or i in tres) else "Expropriatório"

    linhas = []
    tot = {"valor": ZERO, "corrigido": ZERO, "juros": ZERO, "total": ZERO}
    por_classe = {"Prisão": ZERO, "Expropriatório": ZERO}
    for i, (venc, valor, desc) in enumerate(itens):
        corr, jur, fator = atualiza(valor, venc)
        corr, jur = arred(corr), arred(jur)
        linha = {"n": i + 1, "venc": venc, "desc": desc, "valor": valor, "fator": fator, "corrigido": corr,
                 "juros": jur, "total": corr + jur, "classe": classe.get(i, "")}
        linhas.append(linha)
        for k, v in (("valor", valor), ("corrigido", corr), ("juros", jur), ("total", corr + jur)):
            tot[k] += v
        if i in classe:
            por_classe[classe[i]] += corr + jur

    # pagamentos
    abatido = ZERO
    pag_linhas = []
    for pg in p["pagamentos"]:
        if pg["data"] > final:
            raise ErroDeValidacao(f"Pagamento de {pg['data']:%d/%m/%Y} é posterior à data do cálculo.", "pagamentos")
        if pg["valor"] is None or pg["valor"] <= 0:
            raise ErroDeValidacao("Os valores dos pagamentos devem ser positivos.", "pagamentos")
        if p["abatimento"] == "atualizado":
            if lei:
                v = atualizar(pg["valor"], pg["data"], pg["data"], final, inicio=p["inicio"], selic_modo=False,
                              indice_anterior=p["indice"], juros_anterior=taxa, res=res)["corrigido"]
            else:
                ini = ym(pg["data"]) if p["inicio"] == "mes_base" else mes_seguinte(ym(pg["data"]))
                v = pg["valor"] * acumular(serie_idx, ini, mes_anterior(ym(final))).fator
        else:
            v = pg["valor"]
        v = arred(v)
        abatido += v
        pag_linhas.append({"data": pg["data"], "nominal": pg["valor"], "abatido": v})

    liquido = tot["total"] - abatido
    multa = arred(liquido * pct(10)) if p["multa_523"] and liquido > 0 else ZERO
    hon = arred(liquido * pct(10)) if p["hon_523"] and liquido > 0 else ZERO
    total = liquido + multa + hon

    res.param("Parcelas", f"{len(itens)} (de {itens[0][0]:%d/%m/%Y} a {itens[-1][0]:%d/%m/%Y})")
    res.param("Pensão", f"R$ {p['valor_mensal']} por mês" if p["valor_tipo"] == "fixo" else f"{p['pct_sm']}% do salário mínimo")
    res.param("Data do cálculo", final, "data")
    res.param("Critério", "Lei 14.905/2024 (IPCA + Taxa Legal)" if lei else
              f"{p['indice']} + juros simples de {taxa}% a.m.")

    res.kpi("Total atualizado", total, destaque=True)
    res.kpi("Principal (parcelas vencidas)", tot["valor"])
    res.kpi("Correção monetária", tot["corrigido"] - tot["valor"])
    res.kpi("Juros de mora", tot["juros"])
    if abatido:
        res.kpi("Pagamentos abatidos", -abatido)
    if multa:
        res.kpi("Multa de 10% (art. 523)", multa)
    if hon:
        res.kpi("Honorários de 10% (art. 523)", hon)
    if classe:
        res.kpi("Parcelas que autorizam a prisão civil", por_classe["Prisão"],
                nota="3 parcelas anteriores ao ajuizamento + vencidas depois (Súm. 309/STJ), antes dos pagamentos")
        res.kpi("Demais parcelas (rito expropriatório)", por_classe["Expropriatório"], nota="Antes dos pagamentos")

    cols = [("n", "Nº", "inteiro"), ("venc", "Vencimento", "data"), ("desc", "Parcela", "texto"),
            ("valor", "Valor", "dinheiro"), ("fator", "Fator", "fator"), ("corrigido", "Corrigido", "dinheiro"),
            ("juros", "Juros", "dinheiro"), ("total", "Total", "dinheiro")]
    if classe:
        cols.append(("classe", "Rito", "texto"))
    res.tabela("Parcelas", cols, linhas, recolhida=len(linhas) > 24,
               total={"n": "Total", "valor": tot["valor"], "corrigido": tot["corrigido"], "juros": tot["juros"],
                      "total": tot["total"]})
    if pag_linhas:
        res.tabela("Pagamentos abatidos", [("data", "Data", "data"), ("nominal", "Valor pago", "dinheiro"),
                   ("abatido", "Valor abatido", "dinheiro")], pag_linhas)

    if p["multa_523"] or p["hon_523"]:
        res.aviso("Multa e honorários de 10% aplicados sobre o total atualizado, já com os pagamentos abatidos. "
                  "Incidem apenas no rito expropriatório (CPC, art. 528, §8º): confira se cabem à sua execução.")
    if classe:
        res.aviso("A separação pela Súmula 309/STJ considera todas as parcelas (inclusive extras) pela data de vencimento; "
                  "os pagamentos não são imputados a um ou outro grupo.")
    res.nota("Cada parcela é corrigida desde o mês do seu vencimento até o último mês fechado anterior ao da data do cálculo, "
             "e recebe juros de mora simples (meses completos + dias ÷ 30) desde o seu próprio vencimento.")
    if lei:
        res.nota("Critério da Lei 14.905/2024: até 29/08/2024, índice escolhido e juros simples fixos; a partir de 30/08/2024, "
                 "correção pelo IPCA e juros pela Taxa Legal do Banco Central (juros simples, pro rata por dias).")
    res.nota("Pagamentos: deduzidos do total atualizado" + (", cada um corrigido pelo mesmo critério até a data do cálculo."
             if p["abatimento"] == "atualizado" else ", pelo valor nominal.") + " Não há imputação por parcela nem "
             "amortização em conta corrente; se o juízo determinar, o cálculo deve ser feito à parte.")
    res.nota("Alimentos vincendos não entram no cálculo. Revisões do valor da pensão ao longo do tempo devem ser calculadas "
             "separadamente por período.")
    return res
