"""Juros simples/compostos, conversão de taxas e taxa implícita."""
from __future__ import annotations

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.numeros import UM, ZERO, D, pct, potencia
from ..core.resultado import Resultado

# Convenção: 1 mês = 30 dias; 1 ano = 12 meses.
DIAS = {"dia": D(1), "mes": D(30), "ano": D(360)}
ROT = {"dia": "dia", "mes": "mês", "ano": "ano"}
PER = opcoes(("dia", "Dia"), ("mes", "Mês"), ("ano", "Ano"))

META = {
    "slug": "juros-taxas",
    "titulo": "Juros e taxas",
    "categoria": "Matemática financeira",
    "icone": "percent",
    "descricao": "Montante com juros simples ou compostos, conversão entre taxas equivalentes e proporcionais "
                 "e descoberta da taxa implícita em uma operação.",
    "campos": [
        campo("modo", "O que deseja calcular?", "selecao", "montante", opcoes=opcoes(
            ("montante", "Montante (principal + juros)"),
            ("converter", "Converter taxa (mensal ↔ anual…)"),
            ("implicita", "Taxa implícita (valor presente e futuro)"))),
        campo("principal", "Principal (R$)", "dinheiro", mostrar_se={"campo": "modo", "em": ["montante"]},
              obrigatorio=True, minimo=0),
        campo("regime", "Regime", "selecao", "composto", opcoes=opcoes(("composto", "Compostos"), ("simples", "Simples")),
              mostrar_se={"campo": "modo", "em": ["montante"]}),
        campo("taxa", "Taxa (%)", "percentual", obrigatorio=True, minimo=0,
              mostrar_se={"campo": "modo", "em": ["montante", "converter"]}),
        campo("taxa_periodo", "Período da taxa", "selecao", "mes", opcoes=PER,
              mostrar_se={"campo": "modo", "em": ["montante", "converter"]}),
        campo("prazo", "Prazo", "numero", obrigatorio=True, minimo=0,
              mostrar_se={"campo": "modo", "em": ["montante", "implicita"]}),
        campo("prazo_periodo", "Unidade do prazo", "selecao", "mes", opcoes=PER,
              mostrar_se={"campo": "modo", "em": ["montante", "implicita"]}),
        campo("para", "Converter para taxa…", "selecao", "ano", opcoes=PER,
              mostrar_se={"campo": "modo", "em": ["converter"]}),
        campo("vp", "Valor presente (R$)", "dinheiro", obrigatorio=True, minimo=0.01,
              mostrar_se={"campo": "modo", "em": ["implicita"]}),
        campo("vf", "Valor futuro (R$)", "dinheiro", obrigatorio=True, minimo=0.01,
              mostrar_se={"campo": "modo", "em": ["implicita"]}),
    ],
}


def _taxa_equivalente(taxa, de: str, para: str) -> D:
    """Composta: (1+i)^(dias_para/dias_de) - 1"""
    return potencia(UM + pct(taxa), DIAS[para] / DIAS[de]) - UM


def _taxa_proporcional(taxa, de: str, para: str) -> D:
    return pct(taxa) * DIAS[para] / DIAS[de]


def calcular(p: dict) -> Resultado:
    modo = p["modo"]
    res = Resultado({"montante": "Juros e montante", "converter": "Conversão de taxas",
                     "implicita": "Taxa implícita"}[modo])
    res.nota("Convenção de calendário: 1 mês = 30 dias e 1 ano = 12 meses (360 dias).")

    if modo == "montante":
        pr, taxa_p, prazo_p = p["principal"], p["taxa_periodo"], p["prazo_periodo"]
        prazo = p["prazo"]
        n_dias = prazo * DIAS[prazo_p]
        if p["regime"] == "simples":
            i_dia = pct(p["taxa"]) / DIAS[taxa_p]
            juros = pr * i_dia * n_dias
        else:
            i = _taxa_equivalente(p["taxa"], taxa_p, "dia")
            juros = pr * (potencia(UM + i, n_dias) - UM)
        montante = pr + juros
        res.param("Principal", pr, "dinheiro")
        res.param("Taxa", f"{p['taxa']}% ao {ROT[taxa_p]}")
        res.param("Prazo", f"{prazo} {ROT[prazo_p]}(s)")
        res.param("Regime", "Compostos" if p["regime"] == "composto" else "Simples")
        res.kpi("Montante", montante, destaque=True)
        res.kpi("Juros", juros)
        res.kpi("Rentabilidade no prazo", juros / pr * 100 if pr else ZERO, "percentual")
        res.kpi("Taxa mensal equivalente", _taxa_equivalente(p["taxa"], taxa_p, "mes") * 100, "percentual")
        res.kpi("Taxa anual equivalente", _taxa_equivalente(p["taxa"], taxa_p, "ano") * 100, "percentual")
        # evolução, na unidade do prazo (até 360 linhas)
        passos = int(prazo) if prazo == prazo.to_integral_value() else 0
        if 0 < passos <= 360:
            linhas = []
            for k in range(1, passos + 1):
                nd = D(k) * DIAS[prazo_p]
                if p["regime"] == "simples":
                    j = pr * (pct(p["taxa"]) / DIAS[taxa_p]) * nd
                else:
                    j = pr * (potencia(UM + _taxa_equivalente(p["taxa"], taxa_p, "dia"), nd) - UM)
                linhas.append({"n": k, "juros": j, "montante": pr + j})
            res.tabela(f"Evolução por {ROT[prazo_p]}", [("n", ROT[prazo_p].capitalize(), "inteiro"),
                       ("juros", "Juros acumulados", "dinheiro"), ("montante", "Montante", "dinheiro")], linhas,
                       recolhida=passos > 24)
        res.nota("Simples: J = P × i × n. Compostos: M = P × (1 + i)^n, com a taxa convertida de forma equivalente "
                 "para a unidade do prazo.")

    elif modo == "converter":
        de, para = p["taxa_periodo"], p["para"]
        eq = _taxa_equivalente(p["taxa"], de, para) * 100
        prop = _taxa_proporcional(p["taxa"], de, para) * 100
        res.param("Taxa informada", f"{p['taxa']}% ao {ROT[de]}")
        res.param("Converter para", f"ao {ROT[para]}")
        res.kpi(f"Taxa equivalente (composta) ao {ROT[para]}", eq, "percentual", destaque=True,
                nota="Gera o mesmo montante no mesmo prazo")
        res.kpi(f"Taxa proporcional (linear) ao {ROT[para]}", prop, "percentual",
                nota="Divisão/multiplicação simples; usada em juros simples e taxas nominais")
        res.nota("Equivalente: (1 + i)^(n) − 1. Proporcional: i × n. A diferença entre as duas é o efeito da "
                 "capitalização (juros sobre juros).")

    else:
        vp, vf, n, per = p["vp"], p["vf"], p["prazo"], p["prazo_periodo"]
        if n <= 0:
            raise ErroDeValidacao("O prazo deve ser maior que zero.", "prazo")
        razao = vf / vp
        comp = (potencia(razao, UM / n) - UM) * 100
        simples = (razao - UM) / n * 100
        res.param("Valor presente", vp, "dinheiro")
        res.param("Valor futuro", vf, "dinheiro")
        res.param("Prazo", f"{n} {ROT[per]}(s)")
        res.kpi(f"Taxa composta ao {ROT[per]}", comp, "percentual", destaque=True)
        res.kpi(f"Taxa simples ao {ROT[per]}", simples, "percentual")
        dias = n * DIAS[per]
        res.kpi("Taxa composta mensal equivalente", (potencia(razao, DIAS["mes"] / dias) - UM) * 100, "percentual")
        res.kpi("Taxa composta anual equivalente", (potencia(razao, DIAS["ano"] / dias) - UM) * 100, "percentual")
        res.kpi("Variação total", (razao - UM) * 100, "percentual")
        res.nota("Composta: (VF ÷ VP)^(1/n) − 1. Simples: (VF ÷ VP − 1) ÷ n.")
    return res
