"""Cartão de crédito – crédito rotativo: evolução do saldo, encargos, limite de 100% e comparação com a taxa média."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.indices import resolver
from ..core.numeros import UM, ZERO, arred, brl, pct, potencia
from ..core.resultado import Resultado
from .cheque_especial import MAX_DIAS, REGIMES, _simular

VIGENCIA_LIMITE = date(2024, 1, 3)  # Lei 14.690/2023, art. 28: limite de juros e encargos de 100% do valor original

_REV_INF = {"campo": "revisada_origem", "em": ["informada"]}

META = {
    "slug": "cartao-credito",
    "titulo": "Cartão de crédito (rotativo)",
    "categoria": "Bancário",
    "icone": "bank",
    "descricao": "Evolução diária do saldo no rotativo, com multa, juros de mora, limite de 100% do valor original "
                 "e comparação com a taxa cobrada, uma taxa revisada ou a taxa média do Banco Central.",
    "campos": [
        campo("data_inicial", "Início do rotativo (vencimento da fatura)", "data", obrigatorio=True, grupo="Dívida"),
        campo("data_final", "Data final do cálculo", "data", obrigatorio=True, grupo="Dívida"),
        campo("saldo_inicial", "Valor financiado no rotativo (R$)", "dinheiro", obrigatorio=True, minimo=0.01,
              grupo="Dívida", ajuda="Valor da fatura não pago ou saldo que entrou no rotativo."),
        campo("taxa_cobrada", "Taxa de juros do rotativo cobrada (% a.m.)", "percentual", obrigatorio=True, minimo=0,
              maximo=100, grupo="Juros remuneratórios"),
        campo("regime", "Regime de juros", "selecao", "mensal", grupo="Juros remuneratórios", opcoes=opcoes(
            ("mensal", "Capitalização mensal (juros diários incorporados ao fim de cada mês)"),
            ("simples", "Juros simples (sem capitalização)"),
            ("diaria", "Capitalização diária (taxa diária equivalente)"))),
        campo("revisada_origem", "Taxa para comparação (revisão)", "selecao", "media_bcb", grupo="Juros remuneratórios",
              opcoes=opcoes(("nenhuma", "Não comparar"), ("media_bcb", "Taxa média de mercado do BCB (mês do início)"),
                            ("informada", "Taxa informada por mim")),
              ajuda="Série 25477 do BCB: taxa média do rotativo para pessoa física."),
        campo("taxa_revisada", "Taxa revisada (% a.m.)", "percentual", obrigatorio=True, minimo=0, maximo=100,
              grupo="Juros remuneratórios", mostrar_se=_REV_INF),
        campo("multa", "Multa por atraso (%)", "percentual", "0", minimo=0, maximo=100, grupo="Encargos de mora",
              ajuda="Cobrada uma vez sobre o valor em atraso. Limite de 2% no CDC (art. 52, §1º)."),
        campo("mora", "Juros de mora (% ao mês, simples)", "percentual", "0", minimo=0, maximo=100,
              grupo="Encargos de mora", ajuda="Pro rata por dia sobre o valor em atraso. Comum: 1% ao mês."),
        campo("limitar", "Aplicar o limite de 100% do valor original", "booleano", True, grupo="Limite legal",
              ajuda="Lei 14.690/2023, art. 28: juros e encargos do rotativo e do parcelamento da fatura não podem "
                    "superar o valor original da dívida (em vigor desde 03/01/2024)."),
        campo("lancamentos", "Pagamentos e novos débitos", "tabela", [], grupo="Lançamentos", colunas=[
            {"nome": "data", "rotulo": "Data", "tipo": "data"},
            {"nome": "tipo", "rotulo": "Tipo", "tipo": "selecao",
             "opcoes": opcoes(("C", "Pagamento (abate a dívida)"), ("D", "Débito (aumenta a dívida)"))},
            {"nome": "valor", "rotulo": "Valor (R$)", "tipo": "dinheiro"},
            {"nome": "descricao", "rotulo": "Descrição", "tipo": "texto", "obrigatorio": False}],
            ajuda="IOF e tarifas, se cobrados, podem ser lançados aqui como débitos."),
    ],
}


def _cenario(p: dict, taxa: Decimal, mora_total: Decimal, multa: Decimal, original: Decimal) -> dict:
    r = _simular(p, taxa, None)
    juros = r["tot"]["juros"]
    principal = r["total"] - juros                       # saldo sem juros remuneratórios
    encargos = juros + mora_total + multa
    cap = original if p["limitar"] else None
    limitados = min(encargos, cap) if cap is not None else encargos
    return {"sim": r, "juros": juros, "principal": principal, "encargos": encargos, "limitados": limitados,
            "cortado": encargos - limitados, "total": principal + limitados}


def calcular(p: dict) -> Resultado:
    ini, fim = p["data_inicial"], p["data_final"]
    if fim < ini:
        raise ErroDeValidacao("A data final não pode ser anterior à data inicial.", "data_final")
    if (fim - ini).days > MAX_DIAS:
        raise ErroDeValidacao("O período máximo é de 10 anos por cálculo.", "data_final")
    for l in p["lancamentos"]:
        if l["data"] < ini or l["data"] > fim:
            raise ErroDeValidacao(f"Lançamento em {l['data']:%d/%m/%Y} está fora do período do cálculo.", "lancamentos")
        if l["valor"] is None or l["valor"] <= 0:
            raise ErroDeValidacao("Os valores dos lançamentos devem ser positivos.", "lancamentos")

    res = Resultado("Cartão de crédito – rotativo")
    saldo = p["saldo_inicial"]
    sim_p = {**p, "saldo_inicial": saldo}
    original = saldo + sum((l["valor"] for l in p["lancamentos"] if l["tipo"] == "D"), ZERO)
    dias = (fim - ini).days
    multa = saldo * pct(p["multa"] or ZERO) if dias > 0 else ZERO
    mora = saldo * pct(p["mora"] or ZERO) / 30 * dias

    taxa_rev, media_txt = None, None
    if p["revisada_origem"] == "informada":
        taxa_rev = p["taxa_revisada"]
    elif p["revisada_origem"] == "media_bcb":
        serie = resolver("TAXA_MEDIA_ROTATIVO")
        if serie.origem == "cache":
            res.aviso(f"Taxa média do BCB: o Banco Central não respondeu; usando cópia salva em {serie.atualizado_em}.")
        chave = f"{ini.year:04d}-{ini.month:02d}"
        validos = [k for k in serie.valores if k <= chave]
        if not validos:
            raise ErroDeValidacao("Taxa média do BCB indisponível para essa data; use “Taxa informada por mim”.",
                                  "revisada_origem")
        mes = max(validos)
        taxa_rev = serie.valores[mes]
        media_txt = f"{mes[5:]}/{mes[:4]}"
        if mes != chave:
            res.aviso(f"A taxa média de {ini.month:02d}/{ini.year} ainda não foi divulgada; usada a de {media_txt}.")

    cob = _cenario(sim_p, p["taxa_cobrada"], mora, multa, original)
    rev = _cenario(sim_p, taxa_rev, mora, multa, original) if taxa_rev is not None else None

    if p["limitar"] and ini < VIGENCIA_LIMITE:
        res.aviso("O limite de 100% está em vigor desde 03/01/2024 (Lei 14.690/2023). Como o rotativo começou antes, "
                  "aplicá-lo ou não é tese sua; desmarque a opção para ver o cálculo sem o limite.")
    if cob["cortado"] > 0:
        res.aviso(f"Os juros e encargos ({brl(cob['encargos'])}) excederam o limite de 100% do valor original "
                  f"({brl(original)}); a taxa cobrada foi limitada.")
    if rev is not None and cob["cortado"] > 0 and rev["cortado"] > 0:
        res.aviso("O limite de 100% foi atingido também no cenário de comparação: por isso as dívidas coincidem. "
                  "Para ver o efeito da taxa isoladamente, desmarque o limite.")

    anual = lambda t: (potencia(UM + pct(t), 12) - UM) * 100  # noqa: E731
    res.param("Período", f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y} ({dias} dias)")
    res.param("Valor financiado no rotativo", saldo, "dinheiro")
    res.param("Taxa cobrada", p["taxa_cobrada"], "percentual")
    res.param("Taxa cobrada, equivalente anual", anual(p["taxa_cobrada"]), "percentual")
    res.param("Regime", REGIMES[p["regime"]])
    if p["multa"] or p["mora"]:
        res.param("Multa / mora", f"{p['multa']}% / {p['mora']}% a.m.")
    if taxa_rev is not None:
        res.param("Taxa de comparação" + (f" (média BCB {media_txt})" if media_txt else ""), taxa_rev, "percentual")

    res.kpi("Dívida final (taxa cobrada)", cob["total"], destaque=rev is None)
    res.kpi("Juros remuneratórios", cob["juros"])
    if multa or mora:
        res.kpi("Multa e juros de mora", multa + mora)
    if cob["cortado"] > 0:
        res.kpi("Excesso cortado pelo limite de 100%", -cob["cortado"], nota="Lei 14.690/2023")
    if rev is not None:
        res.kpi("Dívida final (taxa de comparação)", rev["total"], destaque=True)
        res.kpi("Diferença a favor do consumidor", cob["total"] - rev["total"], destaque=True,
                nota="Dívida cobrada menos dívida na taxa de comparação")
        if taxa_rev and taxa_rev > 0:
            res.kpi("Taxa cobrada ÷ taxa de comparação", p["taxa_cobrada"] / taxa_rev, "fator",
                    nota="Quantas vezes a taxa cobrada supera a de comparação")

    cols = [("data", "Data", "data"), ("anterior", "Saldo anterior", "dinheiro"), ("debitos", "Débitos", "dinheiro"),
            ("creditos", "Pagamentos", "dinheiro"), ("juros", "Juros do dia", "dinheiro"),
            ("incorporado", "Juros incorporados", "dinheiro"), ("saldo", "Saldo", "dinheiro"),
            ("pendente", "Juros a incorporar", "dinheiro"), ("total", "Dívida (sem mora/multa)", "dinheiro")]
    res.tabela("Memória diária – taxa cobrada", cols, cob["sim"]["linhas"], recolhida=True)
    if rev is not None:
        res.tabela("Memória diária – taxa de comparação", cols, rev["sim"]["linhas"], recolhida=True)

    res.nota("Juros remuneratórios sobre o saldo ao fim de cada dia após a data inicial (mês comercial de 30 dias; taxa "
             "diária = taxa mensal ÷ 30, ou equivalente composta no regime diário). Capitalização mensal: incorporação "
             "no último dia de cada mês.")
    res.nota("Multa: percentual único sobre o valor financiado. Juros de mora: simples, pro rata por dia, sobre o valor "
             "financiado. Pagamentos abatem o saldo.")
    res.nota("Limite de 100% (Lei 14.690/2023, art. 28): a soma de juros remuneratórios, multa e juros de mora é limitada "
             "ao valor original da dívida (valor financiado + novos débitos). Confira a regulamentação e a data de vigência "
             "aplicáveis ao seu caso.")
    res.nota("Taxa média do BCB (série 25477, rotativo pessoa física): é referência de mercado, não limite legal. A "
             "abusividade pela comparação com a média é tema de jurisprudência; o múltiplo aceito varia entre os tribunais.")
    res.nota("IOF e tarifas não são calculados; lance-os como débitos se cobrados.")
    return res
