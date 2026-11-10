"""Honorários advocatícios: contratuais (fixos + êxito), sucumbenciais (CPC art. 85), impostos e rateio."""
from __future__ import annotations

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.indices import resolver
from ..core.numeros import UM, ZERO, arred, brl, pct
from ..core.resultado import Resultado

_SUC_PCT = {"campo": "sucumbencia", "em": ["percentual"]}
_SUC_FAZ = {"campo": "sucumbencia", "em": ["fazenda"]}
_SUC_ALGUMA = {"campo": "sucumbencia", "em": ["percentual", "fazenda"]}

# CPC, art. 85, §3º: faixas em salários mínimos e percentuais (mínimo, máximo) quando a Fazenda Pública é parte
FAIXAS_FAZENDA = [
    (ZERO, 200, (10, 20)),
    (200, 2000, (8, 10)),
    (2000, 20000, (5, 8)),
    (20000, 100000, (3, 5)),
    (100000, None, (1, 3)),
]

META = {
    "slug": "honorarios",
    "titulo": "Honorários e êxito",
    "categoria": "Honorários",
    "icone": "percent",
    "descricao": "Honorários contratuais (fixos e de êxito), sucumbência do art. 85 do CPC (inclusive a escalonada "
                 "contra a Fazenda Pública), impostos, rateio entre advogados e valor líquido ao cliente.",
    "campos": [
        campo("valor_base", "Valor obtido pelo cliente (R$)", "dinheiro", obrigatorio=True, minimo=0.01, grupo="Base",
              ajuda="Condenação, acordo ou proveito econômico."),
        campo("despesas", "Custas e despesas reembolsáveis (R$)", "dinheiro", "0", minimo=0, grupo="Base",
              ajuda="Adiantadas pelo escritório e devolvidas pelo cliente. Não são honorários."),

        campo("fixos", "Honorários fixos / iniciais (R$)", "dinheiro", "0", minimo=0, grupo="Honorários contratuais"),
        campo("fixos_pagos", "Os honorários fixos já foram pagos pelo cliente", "booleano", True,
              grupo="Honorários contratuais", ajuda="Se desmarcado, são descontados do valor líquido do cliente."),
        campo("exito_pct", "Honorários de êxito (%)", "percentual", "0", minimo=0, maximo=100,
              grupo="Honorários contratuais"),
        campo("exito_base", "Base do êxito", "selecao", "total", grupo="Honorários contratuais", opcoes=opcoes(
            ("total", "Valor total obtido"), ("liquido", "Valor obtido menos custas e despesas"))),
        campo("fixos_abatem", "Abater os honorários fixos do êxito", "booleano", False, grupo="Honorários contratuais",
              ajuda="O êxito devido passa a ser o êxito calculado menos os honorários fixos (não fica negativo)."),

        campo("sucumbencia", "Honorários sucumbenciais", "selecao", "nenhuma", grupo="Sucumbência (CPC, art. 85)",
              opcoes=opcoes(("nenhuma", "Não calcular"), ("percentual", "Percentual sobre a base (10% a 20%)"),
                            ("fazenda", "Escalonada – Fazenda Pública (art. 85, §3º)"))),
        campo("suc_base", "Base da sucumbência (R$)", "dinheiro", minimo=0.01, grupo="Sucumbência (CPC, art. 85)",
              mostrar_se=_SUC_ALGUMA,
              ajuda="Condenação, proveito econômico ou valor atualizado da causa. Se vazio, usa o valor obtido pelo cliente."),
        campo("suc_pct", "Percentual de sucumbência (%)", "percentual", "10", obrigatorio=True, minimo=0, maximo=100,
              grupo="Sucumbência (CPC, art. 85)", mostrar_se=_SUC_PCT),
        campo("faz_posicao", "Percentual dentro de cada faixa", "selecao", "min", grupo="Sucumbência (CPC, art. 85)",
              mostrar_se=_SUC_FAZ, opcoes=opcoes(("min", "Mínimo de cada faixa"), ("med", "Ponto médio"),
                                                 ("max", "Máximo de cada faixa")),
              ajuda="O juiz fixa o percentual dentro do intervalo legal de cada faixa."),
        campo("sm", "Salário mínimo de referência (R$)", "dinheiro", minimo=0.01, grupo="Sucumbência (CPC, art. 85)",
              mostrar_se=_SUC_FAZ, ajuda="Vigente na data da sentença líquida ou do trânsito em julgado (art. 85, §4º, IV). "
                                          "Se vazio, usa o do mês da data abaixo."),
        campo("sm_data", "Data da sentença / trânsito em julgado", "data", grupo="Sucumbência (CPC, art. 85)",
              mostrar_se=_SUC_FAZ),

        campo("impostos", "Impostos e encargos sobre os honorários (%)", "percentual", "0", minimo=0, maximo=100,
              grupo="Impostos e rateio",
              ajuda="Percentual efetivo total (ISS, PIS/COFINS, IRPJ etc.) conforme o regime tributário do escritório."),
        campo("rateio", "Rateio entre advogados/sócios", "tabela", [], grupo="Impostos e rateio", colunas=[
            {"nome": "nome", "rotulo": "Nome", "tipo": "texto"},
            {"nome": "pct", "rotulo": "Participação (%)", "tipo": "percentual"}],
            ajuda="Aplicado sobre o líquido dos honorários. O que não for distribuído fica como saldo do escritório."),
    ],
}


def _sucumbencia_fazenda(base, sm, posicao):
    """Soma faixa a faixa (art. 85, §5º): cada parcela da base usa o percentual da sua faixa."""
    linhas, total = [], ZERO
    for ini, fim, (mn, mx) in FAIXAS_FAZENDA:
        piso = ini * sm
        teto = fim * sm if fim is not None else None
        if base <= piso:
            break
        parte = (min(base, teto) if teto is not None else base) - piso
        aliq = {"min": UM * mn, "max": UM * mx, "med": UM * (mn + mx) / 2}[posicao]
        valor = parte * pct(aliq)
        total += valor
        faixa = f"até {fim:,} SM".replace(",", ".") if ini == 0 else (
            f"de {ini:,} a {fim:,} SM".replace(",", ".") if fim else f"acima de {ini:,} SM".replace(",", "."))
        linhas.append({"faixa": faixa, "parte": parte, "aliq": aliq, "valor": valor})
    return total, linhas


def calcular(p: dict) -> Resultado:
    res = Resultado("Honorários e êxito")
    base = p["valor_base"]
    despesas = p["despesas"] or ZERO
    fixos = p["fixos"] or ZERO
    if despesas > base:
        raise ErroDeValidacao("As despesas não podem exceder o valor obtido pelo cliente.", "despesas")

    # rateio
    soma_rateio = sum((r["pct"] for r in p["rateio"] if r["pct"] is not None), ZERO)
    if soma_rateio > 100:
        raise ErroDeValidacao(f"O rateio soma {soma_rateio}%: o máximo é 100%.", "rateio")

    # contratuais
    base_exito = base - despesas if p["exito_base"] == "liquido" else base
    exito_bruto = base_exito * pct(p["exito_pct"] or ZERO)
    exito = exito_bruto
    if p["fixos_abatem"]:
        exito = max(exito_bruto - fixos, ZERO)
        if exito_bruto < fixos:
            res.aviso("Os honorários fixos superam o êxito calculado: com o abatimento, não há êxito a pagar.")
    exito, fixos_r = arred(exito), arred(fixos)
    contratuais = exito + fixos_r

    # sucumbenciais
    sucumb, linhas_suc = ZERO, []
    if p["sucumbencia"] != "nenhuma":
        sb = p["suc_base"] or base
        if p["sucumbencia"] == "percentual":
            if not (10 <= p["suc_pct"] <= 20):
                res.aviso(f"O percentual de {p['suc_pct']}% está fora do intervalo de 10% a 20% do art. 85, §2º, do CPC "
                          "(admitido apenas nas hipóteses de fixação por apreciação equitativa, §8º).")
            sucumb = arred(sb * pct(p["suc_pct"]))
        else:
            sm = p["sm"]
            if sm is None:
                if not p["sm_data"]:
                    raise ErroDeValidacao("Informe o salário mínimo ou a data da sentença para buscá-lo.", "sm")
                serie = resolver("SALARIO_MINIMO")
                chave = p["sm_data"].strftime("%Y-%m")
                validos = [k for k in serie.valores if k <= chave]
                if not validos:
                    raise ErroDeValidacao("Salário mínimo não encontrado para essa data.", "sm_data")
                sm = serie.valores[max(validos)]
                res.param("Salário mínimo usado", sm, "dinheiro")
            total_f, linhas_suc = _sucumbencia_fazenda(sb, sm, p["faz_posicao"])
            sucumb = arred(total_f)
    total_bruto = contratuais + sucumb

    # impostos e rateio
    impostos = arred(total_bruto * pct(p["impostos"] or ZERO))
    liquido = total_bruto - impostos
    distrib = [{"nome": r["nome"] or "Participante", "pct": r["pct"], "valor": arred(liquido * pct(r["pct"]))}
               for r in p["rateio"] if r["pct"] is not None]
    if soma_rateio < 100 or not distrib:
        saldo = liquido - sum((d["valor"] for d in distrib), ZERO)
        distrib.append({"nome": "Escritório (saldo)", "pct": 100 - soma_rateio, "valor": saldo})

    cliente = base - exito - despesas - (ZERO if p["fixos_pagos"] else fixos_r)

    res.param("Valor obtido pelo cliente", base, "dinheiro")
    res.param("Honorários de êxito", f"{p['exito_pct']}% sobre {'o valor total' if p['exito_base'] == 'total' else 'o valor menos despesas'}"
              if p["exito_pct"] else "Não há")
    res.kpi("Total de honorários (bruto)", total_bruto, destaque=True)
    res.kpi("Honorários de êxito", exito, nota=f"Base {brl(base_exito)}" if exito else "")
    if fixos_r:
        res.kpi("Honorários fixos", fixos_r)
    res.kpi("Total contratual", contratuais)
    if p["sucumbencia"] != "nenhuma":
        res.kpi("Honorários sucumbenciais", sucumb, nota="Pagos pela parte contrária")
    if impostos:
        res.kpi("Impostos e encargos", -impostos)
    res.kpi("Líquido dos honorários", liquido, destaque=True)
    res.kpi("Líquido ao cliente", cliente, nota="Valor obtido − êxito − despesas"
            + ("" if p["fixos_pagos"] else " − fixos"))

    if linhas_suc:
        res.tabela("Sucumbência escalonada – art. 85, §3º do CPC", [
            ("faixa", "Faixa", "texto"), ("parte", "Valor na faixa", "dinheiro"), ("aliq", "Percentual", "percentual"),
            ("valor", "Honorários", "dinheiro")], linhas_suc, total={"faixa": "Total", "valor": sucumb})
    res.tabela("Distribuição do líquido", [("nome", "Beneficiário", "texto"), ("pct", "Participação", "percentual"),
               ("valor", "Valor", "dinheiro")], distrib, total={"nome": "Total", "valor": liquido})

    res.nota("Êxito = percentual × base escolhida. Total contratual = fixos + êxito (com o abatimento opcional dos fixos).")
    res.nota("Os honorários sucumbenciais são devidos pela parte contrária, em acréscimo ao valor obtido pelo cliente, e "
             "pertencem ao advogado (CPC, art. 85, §14; Lei 8.906/94, art. 23). O contrato pode dispor sobre o seu destino.")
    if p["sucumbencia"] == "fazenda":
        res.nota("Fazenda Pública (art. 85, §3º e §5º): cada faixa de valor, medida em salários mínimos, recebe o percentual da "
                 "sua faixa (1ª: 10–20%; 2ª: 8–10%; 3ª: 5–8%; 4ª: 3–5%; 5ª: 1–3%), e as parcelas são somadas.")
    res.nota("Impostos: percentual informado por você sobre o total bruto dos honorários; não é cálculo tributário. "
             "Confirme com a contabilidade o regime e as alíquotas aplicáveis.")
    return res
