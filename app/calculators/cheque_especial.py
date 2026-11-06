"""Revisão de cheque especial / conta garantida: evolução diária do saldo devedor."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.indices import acumular, mes_anterior, resolver, ym
from ..core.numeros import UM, ZERO, arred, pct, potencia
from ..core.resultado import Resultado
from ._comuns import CAMPO_INDICES_MANUAIS, OPCOES_INDICES, avisar_serie

META = {
    "slug": "cheque-especial",
    "titulo": "Cheque especial",
    "categoria": "Bancário",
    "icone": "bank",
    "descricao": "Evolução diária do saldo devedor com juros, correção monetária e lançamentos. "
                 "Compara a taxa cobrada pelo banco com a taxa revisada.",
    "campos": [
        campo("data_inicial", "Data inicial", "data", obrigatorio=True, grupo="Período e saldo"),
        campo("data_final", "Data final", "data", obrigatorio=True, grupo="Período e saldo"),
        campo("saldo_inicial", "Saldo devedor na data inicial (R$)", "dinheiro", "0", minimo=0, grupo="Período e saldo",
              ajuda="Valor positivo = devedor. Os lançamentos feitos na data inicial já entram neste saldo."),
        campo("taxa_cobrada", "Taxa de juros cobrada (% a.m.)", "percentual", "8", obrigatorio=True, minimo=0,
              maximo=100, grupo="Juros"),
        campo("taxa_revisada", "Taxa de juros revisada (% a.m.)", "percentual", None, minimo=0, maximo=100,
              grupo="Juros", ajuda="Opcional. Informe a taxa que entende devida (ex.: média de mercado do BCB) "
                                   "para ver a diferença."),
        campo("regime", "Regime de juros", "selecao", "mensal", grupo="Juros", opcoes=opcoes(
            ("mensal", "Capitalização mensal (juros diários incorporados ao fim de cada mês)"),
            ("simples", "Juros simples (sem capitalização)"),
            ("diaria", "Capitalização diária (taxa diária equivalente)"))),
        campo("indice", "Correção monetária", "selecao", "NENHUM", grupo="Juros", opcoes=opcoes(("NENHUM", "Sem correção monetária"), *OPCOES_INDICES[:5])),
        campo("lancamentos", "Lançamentos", "tabela", [], grupo="Lançamentos", colunas=[
            {"nome": "data", "rotulo": "Data", "tipo": "data"},
            {"nome": "tipo", "rotulo": "Tipo", "tipo": "selecao",
             "opcoes": opcoes(("D", "Débito (aumenta a dívida)"), ("C", "Crédito (abate a dívida)"))},
            {"nome": "valor", "rotulo": "Valor (R$)", "tipo": "dinheiro"},
            {"nome": "descricao", "rotulo": "Descrição", "tipo": "texto", "obrigatorio": False},
        ], ajuda="Débitos aumentam o saldo devedor; créditos (depósitos, estornos) o reduzem. "
                 "Dica: cole linhas do Excel no formato data;D ou C;valor;descrição."),
        CAMPO_INDICES_MANUAIS,
    ],
}

MAX_DIAS = 3660
REGIMES = {"mensal": "Capitalização mensal", "simples": "Juros simples", "diaria": "Capitalização diária"}


def _simular(p: dict, taxa_mensal: Decimal, serie) -> dict:
    taxa = pct(taxa_mensal)
    regime = p["regime"]
    diaria = potencia(UM + taxa, UM / 30) - UM if regime == "diaria" else taxa / 30

    mov: dict[date, list] = {}
    for l in p["lancamentos"]:
        mov.setdefault(l["data"], []).append(l)

    ini, fim = p["data_inicial"], p["data_final"]
    saldo = p["saldo_inicial"]
    pendente = ZERO      # juros acumulados ainda não incorporados
    linhas = []
    tot = {"juros": ZERO, "correcao": ZERO, "debitos": ZERO, "creditos": ZERO}
    ausentes: list[str] = []

    dia = ini
    while dia <= fim:
        anterior = saldo
        correcao = ZERO
        if dia != ini and dia.day == 1 and serie is not None and saldo > 0:
            mes_ref = mes_anterior(ym(dia))
            ac = acumular(serie, mes_ref, mes_ref)
            ausentes += ac.ausentes
            correcao = saldo * (ac.fator - UM)
            saldo += correcao
        deb = sum((l["valor"] for l in mov.get(dia, []) if l["tipo"] == "D"), ZERO)
        cre = sum((l["valor"] for l in mov.get(dia, []) if l["tipo"] == "C"), ZERO)
        saldo = saldo + deb - cre

        juros = ZERO
        if dia != ini and saldo > 0:
            juros = saldo * diaria
        pendente += juros

        incorporado = ZERO
        ultimo_do_mes = (dia + timedelta(days=1)).day == 1
        if regime == "diaria" or (regime == "mensal" and ultimo_do_mes and dia != fim):
            incorporado, saldo, pendente = pendente, saldo + pendente, ZERO

        tot["juros"] += juros
        tot["correcao"] += correcao
        tot["debitos"] += deb
        tot["creditos"] += cre
        linhas.append({"data": dia, "anterior": anterior, "correcao": correcao, "debitos": deb, "creditos": cre,
                       "juros": juros, "incorporado": incorporado, "saldo": saldo, "pendente": pendente,
                       "total": saldo + pendente})
        dia += timedelta(days=1)

    return {"linhas": linhas, "saldo": saldo, "pendente": pendente, "total": saldo + pendente, "tot": tot,
            "ausentes": sorted(set(ausentes))}


def calcular(p: dict) -> Resultado:
    ini, fim = p["data_inicial"], p["data_final"]
    if fim < ini:
        raise ErroDeValidacao("A data final não pode ser anterior à data inicial.", "data_final")
    if (fim - ini).days > MAX_DIAS:
        raise ErroDeValidacao("O período máximo é de 10 anos por cálculo.", "data_final")
    for l in p["lancamentos"]:
        if l["data"] < ini or l["data"] > fim:
            raise ErroDeValidacao(f"Lançamento em {l['data']:%d/%m/%Y} está fora do período do cálculo.", "lancamentos")
        if l["valor"] is None or l["valor"] < 0:
            raise ErroDeValidacao("Os valores dos lançamentos devem ser positivos; use o tipo para débito/crédito.",
                                  "lancamentos")

    serie = None
    res = Resultado("Revisão de cheque especial")
    if p["indice"] != "NENHUM":
        serie = resolver(p["indice"], p["indices_manuais"])
        avisar_serie(res, serie)

    cobr = _simular(p, p["taxa_cobrada"], serie)
    rev = _simular(p, p["taxa_revisada"], serie) if p["taxa_revisada"] is not None else None
    if serie is not None:
        ausentes = sorted(set(cobr["ausentes"]))
        if ausentes:
            res.aviso(f"Índice {serie.nome} sem valor para {', '.join(ausentes)}; considerado 0,00%.")

    dias = (fim - ini).days
    res.param("Período", f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y} ({dias} dias de incidência)")
    res.param("Saldo devedor inicial", p["saldo_inicial"], "dinheiro")
    res.param("Taxa cobrada", p["taxa_cobrada"], "percentual")
    if rev:
        res.param("Taxa revisada", p["taxa_revisada"], "percentual")
    res.param("Regime", REGIMES[p["regime"]])
    res.param("Correção monetária", p["indice"] if serie else "Não aplicada")

    t = cobr["tot"]
    res.kpi("Dívida final (taxa cobrada)", cobr["total"], destaque=rev is None)
    res.kpi("Juros do período (taxa cobrada)", t["juros"])
    if t["correcao"]:
        res.kpi("Correção monetária", t["correcao"])
    if rev:
        res.kpi("Dívida final (taxa revisada)", rev["total"], destaque=True)
        res.kpi("Diferença a favor do correntista", cobr["total"] - rev["total"], destaque=True,
                nota="Dívida cobrada menos dívida revisada")
    res.kpi("Débitos / créditos no período", t["debitos"] - t["creditos"], nota="Líquido de movimentações")

    cols = [("data", "Data", "data"), ("anterior", "Saldo anterior", "dinheiro"), ("correcao", "Correção", "dinheiro"),
            ("debitos", "Débitos", "dinheiro"), ("creditos", "Créditos", "dinheiro"),
            ("juros", "Juros do dia", "dinheiro"), ("incorporado", "Juros incorporados", "dinheiro"),
            ("saldo", "Saldo", "dinheiro"), ("pendente", "Juros a incorporar", "dinheiro"),
            ("total", "Dívida total", "dinheiro")]
    res.tabela("Memória diária – taxa cobrada", cols, cobr["linhas"], recolhida=True)
    if rev:
        res.tabela("Memória diária – taxa revisada", cols, rev["linhas"], recolhida=True)

    res.nota("Os juros incidem sobre o saldo devedor ao fim de cada dia após a data inicial; movimentações da data "
             "inicial compõem o saldo de abertura. Dias com saldo credor não geram juros nem correção.")
    res.nota("Mês comercial de 30 dias: taxa diária = taxa mensal ÷ 30 (regimes mensal e simples) ou "
             "(1 + taxa)^(1/30) − 1 (capitalização diária). Em 30 dias, ambas reproduzem exatamente a taxa mensal.")
    res.nota("Capitalização mensal: os juros diários são somados e incorporados ao saldo no último dia de cada mês. "
             "Os juros do último mês ficam “a incorporar” e entram na dívida total.")
    res.nota("A correção monetária é aplicada no dia 1º de cada mês sobre o saldo devedor, com o índice do mês anterior.")
    res.nota("Créditos abatem primeiro o saldo; os juros pendentes permanecem até serem incorporados.")
    res.nota("Confirme a taxa e o regime aplicáveis ao seu caso (contrato, normas do CMN e jurisprudência). "
             "A ferramenta executa o cálculo; a tese jurídica é do advogado.")
    return res
