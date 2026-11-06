"""Reajuste de aluguel e de contratos por índice acumulado (com comparação entre índices)."""
from __future__ import annotations

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.indices import acumular, mes_anterior, resolver, ym
from ..core.numeros import UM, ZERO, pct
from ..core.resultado import Resultado
from ._comuns import CAMPO_INDICES_MANUAIS, OPCOES_INDICES, avisar_serie

META = {
    "slug": "reajuste",
    "titulo": "Reajuste de aluguel e contratos",
    "categoria": "Contratos",
    "icone": "home",
    "descricao": "Acumula o índice dos últimos meses, aplica ao valor vigente e compara IGP-M, IPCA, INPC e INCC "
                 "lado a lado, com teto opcional.",
    "campos": [
        campo("valor", "Valor atual (R$)", "dinheiro", obrigatorio=True, minimo=0.01, grupo="Contrato"),
        campo("data_reajuste", "Data do reajuste (aniversário)", "data", obrigatorio=True, grupo="Contrato"),
        campo("indice", "Índice contratual", "selecao", "IGP-M", grupo="Contrato",
              opcoes=opcoes(*[o for o in OPCOES_INDICES if o[0] != "SELIC"])),
        campo("meses", "Meses acumulados", "inteiro", "12", minimo=1, maximo=60, grupo="Janela de índices"),
        campo("defasagem", "Defasagem (meses)", "inteiro", "1", minimo=0, maximo=6, grupo="Janela de índices",
              ajuda="1 = o último mês da janela é o mês anterior ao do reajuste; 2 = dois meses antes, e assim por diante."),
        campo("teto", "Teto de reajuste (%)", "percentual", minimo=0, grupo="Regras do contrato",
              ajuda="Opcional. Limita o percentual aplicado."),
        campo("permite_reducao", "Permitir redução se o índice for negativo", "booleano", False,
              grupo="Regras do contrato"),
        CAMPO_INDICES_MANUAIS,
    ],
}


def calcular(p: dict) -> Resultado:
    dr = p["data_reajuste"]
    fim_ym = ym(dr)
    for _ in range(p["defasagem"]):
        fim_ym = mes_anterior(fim_ym)
    ini_ym = fim_ym
    for _ in range(p["meses"] - 1):
        ini_ym = mes_anterior(ini_ym)

    res = Resultado("Reajuste de contrato")
    res.param("Valor atual", p["valor"], "dinheiro")
    res.param("Data do reajuste", dr, "data")
    res.param("Janela de índices", f"{ini_ym[1]:02d}/{ini_ym[0]} a {fim_ym[1]:02d}/{fim_ym[0]} ({p['meses']} meses)")

    comparativo = []
    escolhido = None
    for nome, _ in OPCOES_INDICES:
        if nome == "SELIC":
            continue
        try:
            serie = resolver(nome, p["indices_manuais"] if nome == p["indice"] else None)
        except Exception:
            if nome == p["indice"]:
                raise
            continue
        ac = acumular(serie, ini_ym, fim_ym)
        pc = ac.percentual
        aplicado = pc
        if p["teto"] is not None and aplicado > p["teto"]:
            aplicado = p["teto"]
        if aplicado < 0 and not p["permite_reducao"]:
            aplicado = ZERO
        novo = p["valor"] * (UM + pct(aplicado))
        comparativo.append({"indice": nome, "acumulado": pc, "aplicado": aplicado, "novo": novo,
                            "diferenca": novo - p["valor"], "completo": not ac.ausentes})
        if nome == p["indice"]:
            escolhido = (serie, ac, aplicado, novo)
            avisar_serie(res, serie, ac)

    serie, ac, aplicado, novo = escolhido
    res.kpi("Novo valor", novo, destaque=True)
    res.kpi(f"{p['indice']} acumulado", ac.percentual, "percentual", nota=f"{p['meses']} meses")
    res.kpi("Percentual aplicado", aplicado, "percentual",
            nota="Após teto/regra de redução" if aplicado != ac.percentual else "")
    res.kpi("Variação em R$", novo - p["valor"])
    if p["teto"] is not None and ac.percentual > p["teto"]:
        res.aviso(f"O índice acumulado ({ac.percentual:.2f}%) excede o teto de {p['teto']}%; aplicou-se o teto.")

    res.tabela("Comparativo entre índices (mesma janela)", [
        ("indice", "Índice", "texto"), ("acumulado", "Acumulado (%)", "percentual"),
        ("aplicado", "Aplicado (%)", "percentual"), ("novo", "Novo valor", "dinheiro"),
        ("diferenca", "Diferença", "dinheiro")], comparativo)
    res.tabela(f"Memória – {p['indice']}", [("mes", "Mês", "mes"), ("indice", "Índice do mês (%)", "taxa"),
                                             ("acumulado", "Acumulado (%)", "taxa")],
               [{k: l[k] for k in ("mes", "indice", "acumulado")} for l in ac.linhas], recolhida=True)
    res.nota("Os índices mensais são acumulados de forma composta na janela definida. Verifique no contrato o "
             "índice, a periodicidade e o mês de referência (a defasagem varia conforme a cláusula).")
    return res
