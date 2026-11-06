from datetime import date
from decimal import Decimal

import pytest

from app.calculators import atualizacao, cheque_especial, financiamento, juros_taxas, prazos, reajuste
from app.core.calendario import pascoa
from app.core.campos import converter
from app.core.erros import ErroDeValidacao


def rodar(modulo, **kw):
    return modulo.calcular(converter(modulo.META["campos"], kw)).para_dict()


def kpi(res, rotulo):
    return next(Decimal(k["valor"]) for k in res["resumo"] if k["rotulo"].startswith(rotulo))


# ---------------------------------------------------------------- financiamento
def test_price_parcela_conhecida():
    r = rodar(financiamento, valor="10000", parcelas=12, taxa_contratada="1", sistema="price")
    assert kpi(r, "1ª parcela") == Decimal("888.49")


def test_sac_primeira_parcela_e_saldo_zerado():
    r = rodar(financiamento, valor="12000", parcelas=12, taxa_contratada="1", sistema="sac")
    assert kpi(r, "1ª parcela") == Decimal("1120.00")
    assert r["tabelas"][0]["linhas"][-1]["saldo"] == "0.00"


def test_taxa_implicita_recupera_taxa():
    r = rodar(financiamento, valor="10000", parcelas=12, taxa_contratada="1", parcela_cobrada="888.49")
    assert abs(kpi(r, "Taxa efetivamente cobrada") - Decimal("1")) < Decimal("0.001")


def test_revisao_restituicao_dobro():
    simples = rodar(financiamento, valor="10000", parcelas=12, taxa_contratada="2", taxa_revisada="1", pagas=2)
    dobro = rodar(financiamento, valor="10000", parcelas=12, taxa_contratada="2", taxa_revisada="1", pagas=2,
                  restituicao="dobro")
    assert kpi(simples, "Restituição") > 0
    assert abs(kpi(dobro, "Restituição") - 2 * kpi(simples, "Restituição")) <= Decimal("0.01")


# ------------------------------------------------------------------ juros/taxas
def test_juros_compostos_e_equivalencia():
    r = rodar(juros_taxas, modo="montante", principal="1000", taxa="1", prazo="12")
    assert kpi(r, "Montante") == Decimal("1126.83")
    c = rodar(juros_taxas, modo="converter", taxa="1", para="ano")
    assert kpi(c, "Taxa equivalente") == Decimal("12.6825")
    assert kpi(c, "Taxa proporcional") == Decimal("12.0000")


def test_taxa_implicita():
    r = rodar(juros_taxas, modo="implicita", vp="1000", vf="1210", prazo="2")
    assert kpi(r, "Taxa composta ao") == Decimal("10.0000")


# --------------------------------------------------------------------- prazos
def test_pascoa():
    assert pascoa(2024) == date(2024, 3, 31)
    assert pascoa(2025) == date(2025, 4, 20)
    assert pascoa(2026) == date(2026, 4, 5)


def test_prazo_15_dias_uteis_com_corpus_christi():
    r = rodar(prazos, origem="dje", data="2025-06-02", prazo=15, unidade="uteis")
    assert kpi_data(r, "Último dia") == "2025-06-25"


def test_prazo_prorroga_para_dia_util():
    # 30 corridos a partir de 2025-01-02 vencem em sábado 01/02 -> segunda 03/02
    r = rodar(prazos, origem="livre", data="2025-01-02", prazo=30, unidade="corridos")
    assert kpi_data(r, "Último dia") == "2025-02-03"


def test_recesso_suspende_contagem():
    r = rodar(prazos, origem="ciencia", data="2025-12-19", prazo=5, unidade="uteis")
    assert kpi_data(r, "Último dia") == "2026-01-27"


def kpi_data(res, rotulo):
    return next(k["valor"] for k in res["resumo"] if k["rotulo"].startswith(rotulo))


# ------------------------------------------------------------ cheque especial
def test_cheque_juros_simples_30_dias():
    r = rodar(cheque_especial, data_inicial="2025-01-01", data_final="2025-01-31", saldo_inicial="1000",
              taxa_cobrada="3", regime="simples")
    assert kpi(r, "Dívida final") == Decimal("1030.00")


def test_cheque_capitalizacao_mensal():
    r = rodar(cheque_especial, data_inicial="2025-01-01", data_final="2025-03-01", saldo_inicial="1000",
              taxa_cobrada="3", regime="mensal")
    # jan: 30 dias → 1030; fev: 28 dias sobre 1030 → 1058,84; mar: 1 dia pendente
    assert kpi(r, "Dívida final") == Decimal("1059.90")


def test_cheque_revisao_e_lancamentos():
    r = rodar(cheque_especial, data_inicial="2025-01-01", data_final="2025-01-31", saldo_inicial="0",
              taxa_cobrada="8", taxa_revisada="4", regime="simples",
              lancamentos=[{"data": "2025-01-01", "tipo": "D", "valor": "1000"}])
    assert kpi(r, "Dívida final (taxa cobrada)") == Decimal("1080.00")
    assert kpi(r, "Dívida final (taxa revisada)") == Decimal("1040.00")
    assert kpi(r, "Diferença") == Decimal("40.00")


def test_cheque_saldo_credor_nao_gera_juros():
    r = rodar(cheque_especial, data_inicial="2025-01-01", data_final="2025-01-31", saldo_inicial="100",
              taxa_cobrada="8", lancamentos=[{"data": "2025-01-01", "tipo": "C", "valor": "500"}])
    assert kpi(r, "Juros do período") == 0


def test_cheque_com_correcao_monetaria():
    r = rodar(cheque_especial, data_inicial="2025-01-15", data_final="2025-02-15", saldo_inicial="1000",
              taxa_cobrada="0", indice="IPCA")
    assert kpi(r, "Correção monetária") == Decimal("10.00")  # 1% em 01/02


def test_cheque_lancamento_fora_do_periodo():
    with pytest.raises(ErroDeValidacao):
        rodar(cheque_especial, data_inicial="2025-01-01", data_final="2025-01-31", taxa_cobrada="8",
              lancamentos=[{"data": "2025-02-10", "tipo": "D", "valor": "10"}])


# ----------------------------------------------------------------- atualização
def test_atualizacao_correcao_composta():
    r = rodar(atualizacao, valor="1000", data_base="2025-01-15", data_calculo="2025-05-10", indice="IPCA",
              juros_tipo="nenhum")
    # jan, fev, mar, abr = 4 meses a 1%
    assert kpi(r, "Total atualizado") == Decimal("1040.60")


def test_atualizacao_juros_simples_prorata():
    r = rodar(atualizacao, valor="1000", data_base="2025-01-01", data_calculo="2025-04-16", indice="IPCA",
              juros_tipo="simples", juros_taxa="1", juros_base="historico")
    # 3 meses + 15 dias = 3,5 meses * 1% * 1000
    assert kpi(r, "Juros de mora") == Decimal("35.00")


def test_atualizacao_selic_soma_simples_sem_juros():
    r = rodar(atualizacao, valor="1000", data_base="2025-01-01", data_calculo="2025-04-01", indice="SELIC",
              juros_tipo="simples", juros_taxa="1")
    assert kpi(r, "Total atualizado") == Decimal("1030.00")
    assert not any(k["rotulo"] == "Juros de mora" for k in r["resumo"])


def test_atualizacao_art_523_e_custas():
    r = rodar(atualizacao, valor="1000", data_base="2025-01-01", data_calculo="2025-01-20", indice="IPCA",
              juros_tipo="nenhum", multa_523=True, hon_523=True, custas="100", custas_data="2025-01-05")
    assert kpi(r, "Total atualizado") == Decimal("1300.00")


def test_atualizacao_exige_data_das_custas():
    with pytest.raises(ErroDeValidacao):
        rodar(atualizacao, valor="1000", data_base="2025-01-01", data_calculo="2025-02-20", custas="100")


def test_meses_sem_indice_geram_aviso():
    r = rodar(atualizacao, valor="1000", data_base="2025-11-01", data_calculo="2026-03-10", indice="IPCA",
              juros_tipo="nenhum")
    assert any("sem valor divulgado" in a for a in r["avisos"])


# --------------------------------------------------------------------- reajuste
def test_reajuste_12_meses_com_teto():
    r = rodar(reajuste, valor="2000", data_reajuste="2026-01-10", indice="IGP-M")
    # janela jan/2025 a dez/2025 = 1,01^12 - 1 = 12,6825%
    assert kpi(r, "IGP-M acumulado") == Decimal("12.6825")
    assert kpi(r, "Novo valor") == Decimal("2253.65")
    t = rodar(reajuste, valor="2000", data_reajuste="2026-01-10", indice="IGP-M", teto="10")
    assert kpi(t, "Novo valor") == Decimal("2200.00")


# ------------------------------------------------------------------ validação
def test_entrada_virgula_brasileira_e_campo_obrigatorio():
    p = converter(juros_taxas.META["campos"], {"modo": "montante", "principal": "1.234,56", "taxa": "1,5", "prazo": "3"})
    assert p["principal"] == Decimal("1234.56") and p["taxa"] == Decimal("1.5")
    with pytest.raises(ErroDeValidacao):
        converter(juros_taxas.META["campos"], {"modo": "montante", "taxa": "1", "prazo": "3"})
