from __future__ import annotations

from ..core.campos import campo, opcoes
from ..core.indices import SERIES, Serie

OPCOES_INDICES = [(k, v.descricao) for k, v in SERIES.items()]

CAMPO_INDICES_MANUAIS = campo(
    "indices_manuais", "Índices informados manualmente (opcional)", "tabela", [],
    grupo="avancado",
    ajuda="Use para sobrescrever um mês da série oficial ou quando o Banco Central estiver indisponível.",
    colunas=[
        {"nome": "mes", "rotulo": "Mês", "tipo": "data"},
        {"nome": "indice", "rotulo": "Índice do mês (%)", "tipo": "percentual"},
    ],
)


def avisar_serie(res, serie: Serie, acumulado=None):
    if serie.origem == "cache":
        res.aviso(f"Índice {serie.nome}: o Banco Central não respondeu; usando cópia salva em {serie.atualizado_em}.")
    if acumulado is not None and acumulado.ausentes:
        meses = ", ".join(acumulado.ausentes[:12]) + ("…" if len(acumulado.ausentes) > 12 else "")
        res.aviso(f"Índice {serie.nome} sem valor divulgado para: {meses}. Esses meses foram considerados 0,00%. "
                  "Informe-os manualmente em “Opções avançadas” se já houver divulgação.")
