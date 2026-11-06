"""Atualização monetária de débitos judiciais e contratuais (cumprimento de sentença)."""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.indices import SERIES, acumular, mes_anterior, mes_seguinte, resolver, ym
from ..core.numeros import UM, ZERO, pct, potencia
from ..core.resultado import Resultado
from ._comuns import CAMPO_INDICES_MANUAIS, OPCOES_INDICES, avisar_serie

META = {
    "slug": "atualizacao-monetaria",
    "titulo": "Atualização monetária",
    "categoria": "Cálculos gerais",
    "icone": "scale",
    "descricao": "Atualização com o índice que você escolher (IPCA, INPC, SELIC…): juros de mora, multa, custas e os acréscimos do "
                 "art. 523 do CPC, com memória mês a mês.",
    "campos": [
        campo("valor", "Valor original (R$)", "dinheiro", obrigatorio=True, minimo=0.01, grupo="Débito principal"),
        campo("data_base", "Data-base da correção (vencimento)", "data", obrigatorio=True, grupo="Débito principal"),
        campo("data_calculo", "Data do cálculo", "data", obrigatorio=True, grupo="Débito principal"),
        campo("indice", "Índice de correção", "selecao", "INPC", grupo="Correção monetária",
              opcoes=opcoes(*OPCOES_INDICES)),
        campo("inicio", "Primeiro índice aplicado", "selecao", "mes_base", grupo="Correção monetária",
              opcoes=opcoes(("mes_base", "Mês da data-base"), ("mes_seguinte", "Mês seguinte ao da data-base")),
              ajuda="Varia conforme a tabela do tribunal; confira a prática do seu juízo."),
        campo("juros_tipo", "Juros de mora", "selecao", "simples", grupo="Juros de mora",
              opcoes=opcoes(("nenhum", "Não aplicar"), ("simples", "Simples (pro rata die)"),
                            ("composto", "Compostos")),
              ajuda="Com a SELIC como índice os juros já estão embutidos e não são somados."),
        campo("juros_taxa", "Taxa de juros (% a.m.)", "percentual", "1", minimo=0, maximo=100, grupo="Juros de mora",
              mostrar_se={"campo": "juros_tipo", "em": ["simples", "composto"]}),
        campo("juros_inicio", "Termo inicial dos juros", "data", grupo="Juros de mora",
              mostrar_se={"campo": "juros_tipo", "em": ["simples", "composto"]},
              ajuda="Citação, vencimento ou outro marco. Se vazio, usa a data-base."),
        campo("juros_base", "Base de cálculo dos juros", "selecao", "corrigido", grupo="Juros de mora",
              mostrar_se={"campo": "juros_tipo", "em": ["simples", "composto"]},
              opcoes=opcoes(("corrigido", "Valor corrigido"), ("historico", "Valor original"))),
        campo("multa", "Multa contratual/penal (%)", "percentual", "0", minimo=0, maximo=100, grupo="Multa e honorários"),
        campo("multa_base", "Base da multa", "selecao", "corrigido_juros", grupo="Multa e honorários",
              opcoes=opcoes(("corrigido_juros", "Corrigido + juros"), ("corrigido", "Valor corrigido"),
                            ("historico", "Valor original"))),
        campo("multa_523", "Multa de 10% do art. 523, §1º, CPC", "booleano", False, grupo="Multa e honorários"),
        campo("hon_523", "Honorários de 10% do art. 523, §1º, CPC", "booleano", False, grupo="Multa e honorários"),
        campo("hon_percentual", "Outros honorários advocatícios (%)", "percentual", "0", minimo=0, maximo=100,
              grupo="Multa e honorários"),
        campo("custas", "Custas a reembolsar (R$)", "dinheiro", "0", minimo=0, grupo="Custas",
              ajuda="Atualizadas apenas por correção monetária."),
        campo("custas_data", "Data do pagamento das custas", "data", grupo="Custas"),
        CAMPO_INDICES_MANUAIS,
    ],
}


def _correcao(serie, ini_data, ate_data, inicio, modo):
    primeiro = ym(ini_data) if inicio == "mes_base" else mes_seguinte(ym(ini_data))
    ultimo = mes_anterior(ym(ate_data))  # só meses fechados
    return acumular(serie, primeiro, ultimo, modo)


def _juros(base, taxa_mensal, ini, fim, tipo):
    """Prazo = meses completos + dias restantes/30 (mês comercial)."""
    if tipo == "nenhum" or fim <= ini:
        return ZERO, ZERO
    delta = relativedelta(fim, ini)
    meses = delta.years * 12 + delta.months
    ancora = ini + relativedelta(months=meses)
    dias = (fim - ancora).days
    periodo = meses + UM * dias / 30
    if tipo == "simples":
        return base * pct(taxa_mensal) * periodo, periodo
    return base * (potencia(UM + pct(taxa_mensal), periodo) - UM), periodo


def calcular(p: dict) -> Resultado:
    base_dt, calc = p["data_base"], p["data_calculo"]
    if base_dt > calc:
        raise ErroDeValidacao("A data-base não pode ser posterior à data do cálculo.", "data_base")
    if p["custas"] and p["custas"] > 0:
        if not p["custas_data"]:
            raise ErroDeValidacao("Informe a data do pagamento das custas.", "custas_data")
        if p["custas_data"] > calc:
            raise ErroDeValidacao("A data das custas não pode ser posterior à data do cálculo.", "custas_data")
    juros_ini = p["juros_inicio"] or base_dt
    if juros_ini > calc:
        raise ErroDeValidacao("O termo inicial dos juros não pode ser posterior à data do cálculo.", "juros_inicio")

    indice = p["indice"]
    serie = resolver(indice, p["indices_manuais"])
    modo = SERIES[indice].acumulo
    res = Resultado("Atualização monetária de débito")
    avisar_serie(res, serie)

    ac = _correcao(serie, base_dt, calc, p["inicio"], modo)
    avisar_serie(res, serie, ac)
    valor = p["valor"]
    corrigido = valor * ac.fator

    selic = indice == "SELIC"
    tipo_juros = "nenhum" if selic else p["juros_tipo"]
    base_juros = corrigido if p["juros_base"] == "corrigido" else valor
    juros, periodo = _juros(base_juros, p["juros_taxa"] or ZERO, juros_ini, calc, tipo_juros)

    base_multa = {"corrigido_juros": corrigido + juros, "corrigido": corrigido, "historico": valor}[p["multa_base"]]
    multa = base_multa * pct(p["multa"] or ZERO)
    base_exec = corrigido + juros + multa

    multa523 = base_exec * pct(10) if p["multa_523"] else ZERO
    hon523 = base_exec * pct(10) if p["hon_523"] else ZERO
    hon = base_exec * pct(p["hon_percentual"] or ZERO)

    custas = custas_corr = ZERO
    if p["custas"] and p["custas"] > 0:
        custas = p["custas"]
        ac_c = _correcao(serie, p["custas_data"], calc, p["inicio"], modo)
        custas_corr = custas * ac_c.fator

    total = base_exec + multa523 + hon523 + hon + custas_corr

    res.param("Valor original", valor, "dinheiro")
    res.param("Data-base", base_dt, "data")
    res.param("Data do cálculo", calc, "data")
    res.param("Índice", f"{indice} ({'soma simples' if modo == 'soma' else 'acumulado composto'})")
    if tipo_juros != "nenhum":
        res.param("Juros", f"{'Simples' if tipo_juros == 'simples' else 'Compostos'} de {str(p['juros_taxa']).rstrip('0').rstrip('.')}% a.m. desde {juros_ini:%d/%m/%Y}")

    res.kpi("Total atualizado", total, destaque=True)
    res.kpi("Valor original", valor)
    res.kpi(f"Correção monetária ({indice})", corrigido - valor, nota=f"Fator {ac.fator:.8f} · {ac.percentual:.4f}%")
    if tipo_juros != "nenhum":
        res.kpi("Juros de mora", juros, nota=f"{periodo:.4f} meses")
    if multa:
        res.kpi("Multa contratual", multa)
    res.kpi("Base de execução", base_exec, nota="Principal corrigido + juros + multa")
    if multa523 or hon523:
        res.kpi("Multa e honorários – art. 523 CPC", multa523 + hon523)
    if hon:
        res.kpi("Honorários advocatícios", hon)
    if custas_corr:
        res.kpi("Custas atualizadas", custas_corr, nota=f"Original {custas:.2f}".replace(".", ","))

    res.tabela(f"Memória da correção – {indice}", [
        ("mes", "Mês", "mes"), ("indice", "Índice do mês (%)", "taxa"), ("acumulado", "Acumulado (%)", "taxa"),
        ("fator", "Fator", "fator")], [{"mes": l["mes"], "indice": l["indice"], "acumulado": l["acumulado"],
                                         "fator": l["fator"]} for l in ac.linhas], recolhida=len(ac.linhas) > 24)

    res.nota("Correção: índices mensais oficiais do Banco Central (SGS), do primeiro mês escolhido até o último mês "
             "fechado anterior ao da data do cálculo. Não há rateio pro rata do mês parcial.")
    res.nota("Índices comuns (IPCA, INPC, IPCA-E, IGP-M, INCC) são acumulados de forma composta; a SELIC é "
             "acumulada por soma simples das taxas mensais e já engloba juros de mora.")
    res.nota("Juros de mora: prazo em meses completos mais dias restantes ÷ 30, desde o termo inicial até a data do cálculo.")
    res.nota("Ordem: principal corrigido → juros → multa contratual (= base de execução) → multa e honorários do "
             "art. 523 e honorários sobre a base de execução → custas corrigidas somadas ao final.")
    res.nota("Conferir a tabela e o marco inicial adotados pelo juízo; a parametrização deste cálculo é do usuário.")
    return res

