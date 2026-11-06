"""Financiamentos e empréstimos (Price/SAC): tabela, taxa efetivamente cobrada e revisão."""
from __future__ import annotations

from decimal import Decimal

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.numeros import UM, ZERO, D, pct, potencia
from ..core.resultado import Resultado

META = {
    "slug": "financiamento",
    "titulo": "Financiamento e empréstimo",
    "categoria": "Bancário",
    "icone": "building",
    "descricao": "Tabela Price ou SAC, taxa efetivamente embutida na parcela cobrada e revisão contratual "
                 "com apuração de diferença e restituição.",
    "campos": [
        campo("valor", "Valor financiado (R$)", "dinheiro", obrigatorio=True, minimo=0.01, grupo="Contrato"),
        campo("parcelas", "Número de parcelas", "inteiro", obrigatorio=True, minimo=1, maximo=600, grupo="Contrato"),
        campo("sistema", "Sistema de amortização", "selecao", "price", grupo="Contrato",
              opcoes=opcoes(("price", "Tabela Price (parcelas fixas)"), ("sac", "SAC (amortização constante)"))),
        campo("taxa_contratada", "Taxa de juros contratada (% a.m.)", "percentual", obrigatorio=True, minimo=0,
              maximo=100, grupo="Contrato"),
        campo("parcela_cobrada", "Valor da 1ª parcela efetivamente cobrada (R$)", "dinheiro", minimo=0.01,
              grupo="Revisão (opcional)",
              ajuda="Se informada, calcula a taxa realmente embutida na parcela cobrada."),
        campo("taxa_revisada", "Taxa revisada (% a.m.)", "percentual", minimo=0, maximo=100, grupo="Revisão (opcional)",
              ajuda="Ex.: taxa média de mercado ou a que entende devida."),
        campo("pagas", "Parcelas já pagas", "inteiro", "0", minimo=0, grupo="Revisão (opcional)"),
        campo("restituicao", "Restituição do indébito", "selecao", "simples", grupo="Revisão (opcional)",
              opcoes=opcoes(("simples", "Simples"), ("dobro", "Em dobro (art. 42, parágrafo único, CDC)")),
              ajuda="O dobro depende de a cobrança indevida configurar má-fé/ausência de engano justificável."),
    ],
}


def pmt_price(pv, i: Decimal, n: int) -> Decimal:
    if i == 0:
        return pv / n
    return pv * i / (UM - potencia(UM + i, -n))


def tabela(pv: Decimal, i: Decimal, n: int, sistema: str) -> list[dict]:
    linhas, saldo = [], pv
    parcela_price = pmt_price(pv, i, n)
    amort_sac = pv / n
    for k in range(1, n + 1):
        juros = saldo * i
        amort = parcela_price - juros if sistema == "price" else amort_sac
        parcela = parcela_price if sistema == "price" else amort + juros
        saldo = saldo - amort
        if k == n:
            saldo = ZERO if abs(saldo) < Decimal("0.0000001") else saldo
        linhas.append({"n": k, "parcela": parcela, "juros": juros, "amortizacao": amort, "saldo": saldo})
    return linhas


def taxa_implicita(pv: Decimal, parcela: Decimal, n: int) -> Decimal:
    """Taxa mensal (fração) que faz a parcela Price de `n` meses amortizar `pv` (bissecção)."""
    if parcela * n < pv:
        raise ErroDeValidacao("A parcela informada é insuficiente para quitar o valor financiado "
                              "(implicaria taxa negativa).", "parcela_cobrada")
    lo, hi = ZERO, D(10)
    for _ in range(200):
        mid = (lo + hi) / 2
        if pmt_price(pv, mid, n) > parcela:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


COLS = [("n", "Nº", "inteiro"), ("parcela", "Parcela", "dinheiro"), ("juros", "Juros", "dinheiro"),
        ("amortizacao", "Amortização", "dinheiro"), ("saldo", "Saldo devedor", "dinheiro")]


def _tot(linhas):
    return {"n": "Total", "parcela": sum((l["parcela"] for l in linhas), ZERO),
            "juros": sum((l["juros"] for l in linhas), ZERO),
            "amortizacao": sum((l["amortizacao"] for l in linhas), ZERO)}


def calcular(p: dict) -> Resultado:
    pv, n, sis = p["valor"], p["parcelas"], p["sistema"]
    if p["pagas"] > n:
        raise ErroDeValidacao("Parcelas pagas não pode exceder o número de parcelas.", "pagas")
    if p["parcela_cobrada"] and sis != "price":
        raise ErroDeValidacao("A taxa implícita na parcela cobrada só se aplica à Tabela Price.", "parcela_cobrada")

    res = Resultado("Financiamento e empréstimo")
    i_c = pct(p["taxa_contratada"])
    base = tabela(pv, i_c, n, sis)
    res.param("Valor financiado", pv, "dinheiro")
    res.param("Parcelas", f"{n} ({'Price' if sis == 'price' else 'SAC'})")
    res.param("Taxa contratada", p["taxa_contratada"], "percentual")
    anual = (potencia(UM + i_c, 12) - UM) * 100

    res.kpi("1ª parcela (taxa contratada)", base[0]["parcela"], destaque=p["taxa_revisada"] is None
            and not p["parcela_cobrada"])
    res.kpi("Total a pagar (taxa contratada)", sum((l["parcela"] for l in base), ZERO))
    res.kpi("Total de juros (taxa contratada)", sum((l["juros"] for l in base), ZERO))
    res.kpi("Taxa anual equivalente", anual, "percentual")

    cobrada = base
    if p["parcela_cobrada"]:
        i_real = taxa_implicita(pv, p["parcela_cobrada"], n)
        cobrada = tabela(pv, i_real, n, "price")
        res.kpi("Taxa efetivamente cobrada", i_real * 100, "percentual", destaque=True,
                nota="Taxa embutida na parcela informada")
        res.kpi("Excesso sobre a taxa contratada", (i_real - i_c) * 100, "percentual",
                nota="Em pontos percentuais ao mês")
        if i_real - i_c > Decimal("0.0001"):
            res.aviso("A parcela cobrada embute taxa superior à contratada. Verifique tarifas, seguros e IOF "
                      "financiados, que também elevam a parcela e podem explicar parte da diferença.")

    if p["taxa_revisada"] is not None:
        i_r = pct(p["taxa_revisada"])
        rev = tabela(pv, i_r, n, sis)
        res.param("Taxa revisada", p["taxa_revisada"], "percentual")
        res.kpi("1ª parcela (taxa revisada)", rev[0]["parcela"])
        total_c, total_r = sum((l["parcela"] for l in cobrada), ZERO), sum((l["parcela"] for l in rev), ZERO)
        res.kpi("Total a pagar (taxa revisada)", total_r)
        res.kpi("Diferença total do contrato", total_c - total_r, destaque=True,
                nota="Cobrado menos revisado, em todas as parcelas")
        k = p["pagas"]
        if k:
            pago_a_mais = sum((cobrada[j]["parcela"] - rev[j]["parcela"] for j in range(k)), ZERO)
            fator = 2 if p["restituicao"] == "dobro" else 1
            res.kpi(f"Pago a maior nas {k} parcelas quitadas", pago_a_mais)
            res.kpi("Restituição" + (" em dobro" if fator == 2 else ""), pago_a_mais * fator, destaque=True)
            res.kpi("Saldo devedor revisado", rev[k - 1]["saldo"], nota=f"Após a parcela {k}")
        res.tabela("Tabela – taxa revisada", COLS, rev, recolhida=True, total=_tot(rev))

    titulo = "Tabela – taxa efetivamente cobrada" if p["parcela_cobrada"] else "Tabela – taxa contratada"
    res.tabela(titulo, COLS, cobrada, recolhida=p["taxa_revisada"] is not None, total=_tot(cobrada))
    res.nota("Price: PMT = PV × i ÷ (1 − (1 + i)^−n). SAC: amortização = PV ÷ n e juros = saldo × i. Juros mensais "
             "sobre o saldo devedor, sem tarifas, seguros ou IOF.")
    res.nota("A taxa implícita é obtida numericamente (bissecção) pela parcela informada, assumindo parcelas "
             "mensais, iguais e sem carência.")
    res.nota("A restituição apurada é nominal; correção monetária e juros sobre o indébito devem ser calculados à "
             "parte (calculadora “Atualização de débito”).")
    return res
