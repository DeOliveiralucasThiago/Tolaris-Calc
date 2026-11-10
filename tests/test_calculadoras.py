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


# ------------------------------------------------------ débitos judiciais (TJES)
from app.calculators import judicial_tjes  # noqa: E402


def linha(res, inicio):
    return next(Decimal(l["v"]) for l in res["tabelas"][-1]["linhas"] if l["d"].startswith(inicio))


def test_tjes_exemplo_oficial_fator_manual():
    """Cálculo real do TJES: principal 31.847,66 (19/03/2024) até 03/11/2026, fator 1,1167325072, custas 369,07.
    Principal corrigido e custas batem ao centavo. Os juros divergem em R$ 0,02 do TJES (11.203,06 oficial
    contra 11.203,08 aqui; o percentual de 31,50% é idêntico) — diferença de arredondamento ainda a calibrar."""
    r = rodar(judicial_tjes, usa_correcao=True, usa_juros=True, usa_custas=True, principal="31847,66",
              corr_data="2024-03-19", corr_fator="manual", corr_fator_manual="1,1167325072",
              juros_data="2024-03-19", custas_valor="369,07", custas_data="2024-03-20", data_final="2026-11-03")
    assert linha(r, "Principal corrigido") == Decimal("35565.32")
    assert linha(r, "Juros do Código Civil (31,50 %)") == Decimal("11203.08")
    assert linha(r, "Custas") == Decimal("412.15")
    assert abs(linha(r, "Total Geral") - Decimal("47180.53")) <= Decimal("0.02")


def test_tjes_juros_legais_viram_em_2003():
    r = rodar(judicial_tjes, usa_correcao=True, usa_juros=True, principal="1000", corr_data="2002-12-11",
              corr_fator="manual", corr_fator_manual="1", juros_data="2002-12-11", data_final="2003-02-11")
    # 1 mês a 0,5% (até 10/01/2003) + 1 mês a 1% = 1,5%
    assert linha(r, "Juros do Código Civil") == Decimal("15.00")


def test_tjes_estrutura_completa_e_totais():
    r = rodar(judicial_tjes, usa_correcao=True, usa_juros=False, usa_multa=True, usa_hon=True, usa_abater=True,
              principal="1000", corr_data="2025-01-10", corr_fator="manual", corr_fator_manual="1,10",
              multa_perc="10", abater_valor="100", hon_perc="10", data_final="2025-06-01")
    # corrigido 1.100 + multa 110 = 1.210; abatendo 100 = 1.110; honorários 10% = 111; geral = 1.221
    assert linha(r, "Subtotal 1") == Decimal("1210.00")
    assert linha(r, "Total 1") == Decimal("1110.00")
    assert linha(r, "Total 2") == Decimal("111.00")
    assert linha(r, "Total Geral") == Decimal("1221.00")


def test_tjes_indice_exige_fator_manual_antes_de_1999():
    with pytest.raises(ErroDeValidacao):
        rodar(judicial_tjes, usa_correcao=True, principal="1000", corr_data="1998-05-10", data_final="2025-01-10")


# ------------------------------------------------- Taxa Legal (Lei 14.905/2024)
from app.calculators import taxa_legal  # noqa: E402


def test_taxa_legal_debito_posterior_a_lei():
    # série sintética: 1% ao mês em tudo. Correção IPCA jan–mar/2025 = 1,01^3; Taxa Legal pro rata:
    # jan 21/31 + fev 28/28 + mar 31/31 + abr 10/30 = 3,010753%
    r = rodar(taxa_legal, valor="1000", data_base="2025-01-10", data_calculo="2025-04-10")
    assert kpi(r, "Valor corrigido") == Decimal("1030.30")
    assert kpi(r, "Juros – Taxa Legal") == Decimal("31.02")
    assert kpi(r, "Total atualizado") == Decimal("1061.32")


def test_taxa_legal_transicao_agosto_2024():
    # 20/08 a 05/09/2024: regime anterior 9 dias (0,3% a.m.→0,3 mês) + TL dias 30 e 31/08 (2/31) e 01–05/09 (5/30)
    r = rodar(taxa_legal, valor="1000", data_base="2024-08-20", data_calculo="2024-09-05", indice_anterior="INPC",
              juros_anterior="1")
    assert kpi(r, "Valor corrigido") == Decimal("1010.00")
    assert kpi(r, "Juros – regime anterior") == Decimal("3.03")
    assert kpi(r, "Juros – Taxa Legal") == Decimal("2.33")  # 1.010 x 0,231183% = 2,33495


def test_taxa_legal_modo_selic_nao_tem_juros_antigos():
    r = rodar(taxa_legal, valor="1000", data_base="2024-06-10", data_calculo="2024-09-30", regime_anterior="selic")
    assert not any(k["rotulo"] == "Juros – regime anterior" for k in r["resumo"])
    # SELIC (soma) jun+jul+ago = 3%, depois IPCA de setembro não entra (mês anterior ao do cálculo é set → só ago)
    assert kpi(r, "Valor corrigido") == Decimal("1030.00")


def test_taxa_legal_antes_da_vigencia_avisa():
    r = rodar(taxa_legal, valor="1000", data_base="2024-01-10", data_calculo="2024-06-10")
    assert any("anterior a 30/08/2024" in a for a in r["avisos"])
    assert not any(k["rotulo"] == "Juros – Taxa Legal" and Decimal(k["valor"]) != 0 for k in r["resumo"])


# ------------------------------------------------------------ pensão alimentícia
from datetime import datetime  # noqa: E402

from app.calculators import pensao  # noqa: E402
from app.core import indices as _indices  # noqa: E402


def test_pensao_parcelas_correcao_e_juros():
    # série sintética: 1%/mês. Jan: corr 1,01² = 1020,10 + juros 2 meses; Fev: 1010 + 1 mês; Mar: 1000 sem juros
    r = rodar(pensao, valor_mensal="1000", primeiro_venc="2025-01-10", data_calculo="2025-03-10")
    assert kpi(r, "Principal") == Decimal("3000.00")
    assert kpi(r, "Juros de mora") == Decimal("30.50")       # 20,40 + 10,10
    assert kpi(r, "Total atualizado") == Decimal("3060.60")
    assert len(r["tabelas"][0]["linhas"]) == 3


def test_pensao_vencimento_ajusta_fim_de_mes():
    r = rodar(pensao, valor_mensal="100", primeiro_venc="2025-01-31", data_calculo="2025-04-30")
    datas = [l["venc"] for l in r["tabelas"][0]["linhas"]]
    assert datas == ["2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"]


def test_pensao_sumula_309_separa_prisao_e_expropriatorio():
    r = rodar(pensao, valor_mensal="100", primeiro_venc="2025-01-10", data_calculo="2025-06-10",
              data_ajuizamento="2025-05-15")
    classes = [l["classe"] for l in r["tabelas"][0]["linhas"]]
    assert classes == ["Expropriatório", "Expropriatório", "Prisão", "Prisão", "Prisão", "Prisão"]
    assert kpi(r, "Parcelas que autorizam") + kpi(r, "Demais parcelas") == kpi(r, "Total atualizado")


def test_pensao_pagamento_nominal_multa_e_honorarios():
    r = rodar(pensao, valor_mensal="1000", primeiro_venc="2025-03-10", data_calculo="2025-03-10",
              pagamentos=[{"data": "2025-03-10", "valor": "400"}], abatimento="nominal", multa_523=True, hon_523=True)
    # 1000 - 400 = 600; multa 60; honorários 60
    assert kpi(r, "Total atualizado") == Decimal("720.00")


def test_pensao_percentual_do_salario_minimo(monkeypatch):
    def falsa(nome, forcar=False):
        if nome == "SALARIO_MINIMO":
            return _indices.Serie(nome, {"2025-01": Decimal("1518.00"), "2025-02": Decimal("1518.00")}, "bcb",
                                  datetime(2026, 1, 1).strftime("%d/%m/%Y %H:%M"))
        return _indices.Serie(nome, {}, "bcb", "x")
    monkeypatch.setattr(_indices, "obter_serie", falsa)
    r = rodar(pensao, valor_tipo="pct_sm", pct_sm="30", primeiro_venc="2025-01-10", data_calculo="2025-02-10",
              juros_taxa="0")
    assert [l["valor"] for l in r["tabelas"][0]["linhas"]] == ["455.40", "455.40"]


def test_pensao_criterio_lei_14905_roda():
    r = rodar(pensao, valor_mensal="1000", primeiro_venc="2025-01-10", data_calculo="2025-03-10", regime="lei14905")
    assert kpi(r, "Total atualizado") > kpi(r, "Principal")


def test_pensao_sem_parcela_vencida_e_erro():
    with pytest.raises(ErroDeValidacao):
        rodar(pensao, valor_mensal="100", primeiro_venc="2025-05-10", data_calculo="2025-03-10")


# ----------------------------------------------------------------- honorários
from app.calculators import honorarios  # noqa: E402


def test_honorarios_exito_e_sucumbencia_percentual():
    r = rodar(honorarios, valor_base="100000", exito_pct="20", sucumbencia="percentual", suc_pct="10")
    assert kpi(r, "Honorários de êxito") == Decimal("20000.00")
    assert kpi(r, "Honorários sucumbenciais") == Decimal("10000.00")
    assert kpi(r, "Total de honorários") == Decimal("30000.00")
    assert kpi(r, "Líquido ao cliente") == Decimal("80000.00")


def test_honorarios_fixos_abatem_do_exito():
    r = rodar(honorarios, valor_base="100000", exito_pct="20", fixos="5000", fixos_abatem=True)
    assert kpi(r, "Honorários de êxito") == Decimal("15000.00")
    assert kpi(r, "Total contratual") == Decimal("20000.00")


def test_honorarios_fixos_maiores_que_exito_nao_ficam_negativos():
    r = rodar(honorarios, valor_base="10000", exito_pct="10", fixos="3000", fixos_abatem=True)
    assert kpi(r, "Honorários de êxito") == 0
    assert any("superam o êxito" in a for a in r["avisos"])


def test_honorarios_base_liquida_de_despesas():
    r = rodar(honorarios, valor_base="100000", despesas="10000", exito_pct="20", exito_base="liquido")
    assert kpi(r, "Honorários de êxito") == Decimal("18000.00")
    assert kpi(r, "Líquido ao cliente") == Decimal("72000.00")      # 100.000 − 18.000 − 10.000


def test_honorarios_fazenda_escalonada():
    # SM = 1.000; base 300.000 = 300 SM: 200 SM a 10% + 100 SM a 8% (mínimos) = 28.000
    kw = dict(valor_base="300000", sucumbencia="fazenda", sm="1000")
    assert kpi(rodar(honorarios, **kw), "Honorários sucumbenciais") == Decimal("28000.00")
    assert kpi(rodar(honorarios, faz_posicao="max", **kw), "Honorários sucumbenciais") == Decimal("50000.00")
    assert kpi(rodar(honorarios, faz_posicao="med", **kw), "Honorários sucumbenciais") == Decimal("39000.00")


def test_honorarios_impostos_e_rateio():
    r = rodar(honorarios, valor_base="100000", exito_pct="10", impostos="10",
              rateio=[{"nome": "Ana", "pct": "60"}, {"nome": "Bruno", "pct": "30"}])
    assert kpi(r, "Líquido dos honorários") == Decimal("9000.00")
    dist = {l["nome"]: Decimal(l["valor"]) for l in r["tabelas"][-1]["linhas"]}
    assert dist == {"Ana": Decimal("5400.00"), "Bruno": Decimal("2700.00"), "Escritório (saldo)": Decimal("900.00")}


def test_honorarios_rateio_acima_de_100_e_erro_e_percentual_fora_da_faixa_avisa():
    with pytest.raises(ErroDeValidacao):
        rodar(honorarios, valor_base="1000", rateio=[{"nome": "A", "pct": "70"}, {"nome": "B", "pct": "40"}])
    r = rodar(honorarios, valor_base="1000", sucumbencia="percentual", suc_pct="25")
    assert any("10% a 20%" in a for a in r["avisos"])


# ------------------------------------------------------ cartão de crédito (rotativo)
from app.calculators import cartao  # noqa: E402


def test_cartao_juros_simples_30_dias():
    r = rodar(cartao, data_inicial="2025-01-01", data_final="2025-01-31", saldo_inicial="1000", taxa_cobrada="10",
              regime="simples", revisada_origem="nenhuma")
    assert kpi(r, "Dívida final (taxa cobrada)") == Decimal("1100.00")


def test_cartao_multa_e_mora():
    r = rodar(cartao, data_inicial="2025-01-01", data_final="2025-01-31", saldo_inicial="1000", taxa_cobrada="10",
              regime="simples", multa="2", mora="1", revisada_origem="nenhuma")
    # 1000 + juros 100 + multa 20 + mora (1% a.m. x 30 dias) 10
    assert kpi(r, "Dívida final (taxa cobrada)") == Decimal("1130.00")
    assert kpi(r, "Multa e juros de mora") == Decimal("30.00")


def test_cartao_limite_de_100_por_cento():
    r = rodar(cartao, data_inicial="2025-01-01", data_final="2025-12-27", saldo_inicial="1000", taxa_cobrada="10",
              regime="simples", revisada_origem="nenhuma")       # 360 dias: 120% de juros
    assert kpi(r, "Juros remuneratórios") == Decimal("1200.00")
    assert kpi(r, "Dívida final (taxa cobrada)") == Decimal("2000.00")
    assert kpi(r, "Excesso cortado") == Decimal("-200.00")
    sem = rodar(cartao, data_inicial="2025-01-01", data_final="2025-12-27", saldo_inicial="1000", taxa_cobrada="10",
                regime="simples", revisada_origem="nenhuma", limitar=False)
    assert kpi(sem, "Dívida final (taxa cobrada)") == Decimal("2200.00")


def test_cartao_comparacao_com_taxa_media_do_bcb():
    # série sintética: média = 1,00% a.m.
    r = rodar(cartao, data_inicial="2025-01-01", data_final="2025-01-31", saldo_inicial="1000", taxa_cobrada="10",
              regime="simples", revisada_origem="media_bcb")
    assert kpi(r, "Dívida final (taxa de comparação)") == Decimal("1010.00")
    assert kpi(r, "Diferença") == Decimal("90.00")
    assert kpi(r, "Taxa cobrada ÷") == Decimal("10.00000000")


def test_cartao_pagamento_abate_e_aviso_de_vigencia():
    r = rodar(cartao, data_inicial="2023-06-01", data_final="2023-06-11", saldo_inicial="1000", taxa_cobrada="3",
              regime="simples", revisada_origem="nenhuma",
              lancamentos=[{"data": "2023-06-01", "tipo": "C", "valor": "400"}])
    assert kpi(r, "Juros remuneratórios") == Decimal("6.00")     # 600 x 0,1%/dia x 10 dias
    assert any("03/01/2024" in a for a in r["avisos"])


def test_cartao_aviso_quando_limite_atinge_os_dois_cenarios():
    r = rodar(cartao, data_inicial="2025-01-01", data_final="2025-12-27", saldo_inicial="1000", taxa_cobrada="10",
              regime="simples", revisada_origem="informada", taxa_revisada="9")
    assert any("também no cenário de comparação" in a for a in r["avisos"])
    assert any(a.startswith("Os juros e encargos (R$ 1.200,00)") for a in r["avisos"])
