"""Contagem de prazos processuais (CPC) e de prescrição/decadência."""
from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from ..core.calendario import em_recesso, feriados
from ..core.campos import campo, opcoes
from ..core.erros import ErroDeValidacao
from ..core.resultado import Resultado

SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
UNIDADES = {"uteis": "dias úteis", "corridos": "dias corridos", "meses": "meses", "anos": "anos"}

META = {
    "slug": "prazos",
    "titulo": "Prazos e datas",
    "categoria": "Prazos",
    "icone": "calendar",
    "descricao": "Contagem de prazos em dias úteis (CPC, art. 219) ou corridos, meses e anos, com feriados "
                 "nacionais, recesso forense e feriados locais.",
    "campos": [
        campo("origem", "Data informada é…", "selecao", "dje", grupo="Início", opcoes=opcoes(
            ("dje", "Disponibilização no DJe (publicação = 1º dia útil seguinte)"),
            ("ciencia", "Ciência/juntada/intimação (início no dia seguinte)"),
            ("livre", "Data livre (prescrição, decadência, prazo contratual)"))),
        campo("data", "Data", "data", obrigatorio=True, grupo="Início"),
        campo("prazo", "Prazo", "inteiro", obrigatorio=True, minimo=1, maximo=36500, grupo="Prazo"),
        campo("unidade", "Unidade", "selecao", "uteis", grupo="Prazo", opcoes=opcoes(
            ("uteis", "Dias úteis"), ("corridos", "Dias corridos"), ("meses", "Meses"), ("anos", "Anos"))),
        campo("prorrogar", "Prorrogar se vencer em dia sem expediente", "booleano", True, grupo="Prazo"),
        campo("recesso", "Suspender de 20/12 a 20/01 (CPC, art. 220)", "booleano", True, grupo="Calendário",
              mostrar_se={"campo": "unidade", "em": ["uteis"]}),
        campo("carnaval", "Carnaval (segunda e terça)", "booleano", True, grupo="Calendário"),
        campo("sexta_santa", "Sexta-feira Santa", "booleano", True, grupo="Calendário"),
        campo("semana_santa", "Semana Santa completa (Justiça Federal, Lei 5.010/66)", "booleano", False,
              grupo="Calendário"),
        campo("corpus", "Corpus Christi", "booleano", True, grupo="Calendário"),
        campo("extras", "Feriados locais/forenses adicionais", "datas", [], grupo="Calendário",
              ajuda="Feriados municipais/estaduais, suspensões de expediente, etc."),
    ],
}


def calcular(p: dict) -> Resultado:
    extras = set(p["extras"])

    def fer(ano):
        return feriados(ano, p["carnaval"], p["sexta_santa"], p["corpus"], p["semana_santa"])

    def motivo(d: date, recesso: bool) -> str | None:
        if d.weekday() >= 5:
            return "Fim de semana"
        if d in fer(d.year):
            return fer(d.year)[d]
        if d in extras:
            return "Feriado adicional"
        if recesso and em_recesso(d):
            return "Recesso forense (20/12–20/01)"
        return None

    recesso = bool(p["recesso"]) and p["unidade"] == "uteis"
    util = lambda d: motivo(d, recesso) is None  # noqa: E731
    res = Resultado("Contagem de prazo")
    data = p["data"]
    linhas: list[dict] = []

    inicio = data
    if p["origem"] == "dje":
        pub = data + timedelta(days=1)
        while not util(pub):
            pub += timedelta(days=1)
        res.param("Disponibilização", data, "data")
        res.kpi("Publicação (art. 224, §2º, CPC)", pub, "data", nota=SEMANA[pub.weekday()])
        inicio = pub
    else:
        res.param("Data de partida", data, "data")
    res.param("Prazo", f"{p['prazo']} {UNIDADES[p['unidade']]}")

    if p["unidade"] in ("uteis", "corridos"):
        atual, contados = inicio, 0
        while contados < p["prazo"]:
            atual += timedelta(days=1)
            m = motivo(atual, recesso)
            conta = (m is None) if p["unidade"] == "uteis" else True
            if conta:
                contados += 1
            if len(linhas) < 800:
                linhas.append({"n": contados if conta else None, "data": atual,
                               "dia": SEMANA[atual.weekday()], "obs": m or ("Contado" if conta else "")})
        final = atual
    else:
        final = inicio + (relativedelta(months=p["prazo"]) if p["unidade"] == "meses"
                          else relativedelta(years=p["prazo"]))
        linhas.append({"n": None, "data": final, "dia": SEMANA[final.weekday()], "obs": "Data nominal do vencimento"})

    nominal = final
    if p["prorrogar"]:
        while not util(final):
            final += timedelta(days=1)
            if len(linhas) < 800:
                linhas.append({"n": None, "data": final, "dia": SEMANA[final.weekday()],
                               "obs": "Prorrogação (art. 224, §1º, CPC)" if util(final) else
                               (motivo(final, recesso) or "")})
    if final != nominal:
        res.aviso(f"O prazo venceria em {nominal:%d/%m/%Y} ({SEMANA[nominal.weekday()]}), dia sem expediente; "
                  f"foi prorrogado para {final:%d/%m/%Y}.")

    res.kpi("Último dia do prazo", final, "data", destaque=True, nota=SEMANA[final.weekday()])
    res.kpi("Dias corridos entre a partida e o vencimento", (final - data).days, "inteiro")
    res.tabela("Memória da contagem", [("n", "Dia do prazo", "inteiro"), ("data", "Data", "data"),
                                       ("dia", "Dia da semana", "texto"), ("obs", "Observação", "texto")],
               linhas, recolhida=True)
    res.nota("Exclui-se o dia do começo e inclui-se o do vencimento (CPC, art. 224). "
             "Na disponibilização no DJe, a publicação é o primeiro dia útil seguinte e a contagem começa no dia seguinte.")
    res.nota("Dias úteis não incluem sábados, domingos, feriados nacionais, os feriados marcados e os adicionais informados.")
    res.aviso("Cada tribunal publica seu próprio calendário (feriados locais, suspensões, indisponibilidade do "
              "sistema). Confira o prazo final no calendário do juízo antes de confiar na data.")
    return res
