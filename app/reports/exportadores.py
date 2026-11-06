"""Exportação do Resultado padrão para Excel e PDF."""
from __future__ import annotations

import io
from datetime import date, datetime

from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..core.numeros import D, num_br

AZUL = (15, 38, 71)
MESES = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def formatar(valor, tipo: str) -> str:
    if valor is None or valor == "":
        return ""
    if tipo == "dinheiro":
        return "R$ " + num_br(valor, 2)
    if tipo == "percentual":
        return num_br(valor, 4) + "%"
    if tipo == "taxa":
        return num_br(valor, 4)
    if tipo == "fator":
        return num_br(valor, 8)
    if tipo == "data":
        return date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
    if tipo == "mes":
        d = date.fromisoformat(str(valor))
        return f"{d.month:02d}/{d.year}"
    if tipo == "inteiro":
        return str(valor) if isinstance(valor, str) and not valor.lstrip("-").isdigit() else f"{int(D(valor)):,}".replace(",", ".")
    return str(valor)


_TROCAS = {"–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "→": "->", "≥": ">=",
           "≤": "<=", "↔": "<->", "×": "x", "÷": "/", "−": "-", "²": "2", "•": "-"}


def latin1(texto) -> str:
    s = str(texto)
    for a, b in _TROCAS.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


# ------------------------------------------------------------------ Excel

def para_xlsx(res: dict, ident: dict | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo"
    negrito = Font(bold=True)
    cab = PatternFill("solid", fgColor="0F2647")
    ws["A1"] = "Tolaris Calc – " + res["titulo"]
    ws["A1"].font = Font(bold=True, size=14, color="0F2647")
    linha = 2
    ws.cell(linha, 1, "Emitido em " + datetime.fromisoformat(res["gerado_em"]).strftime("%d/%m/%Y %H:%M"))
    for k, v in (ident or {}).items():
        if v:
            linha += 1
            ws.cell(linha, 1, k).font = negrito
            ws.cell(linha, 2, v)
    linha += 2
    for secao, itens in (("Parâmetros", res["parametros"]), ("Resultado", res["resumo"])):
        ws.cell(linha, 1, secao).font = negrito
        linha += 1
        for it in itens:
            ws.cell(linha, 1, it["rotulo"])
            c = ws.cell(linha, 2, _num(it["valor"], it["tipo"]))
            _fmt_celula(c, it["tipo"])
            c.alignment = Alignment(horizontal="right")
            if it.get("destaque"):
                ws.cell(linha, 1).font = negrito
                c.font = negrito
            linha += 1
        linha += 1
    if res["avisos"]:
        ws.cell(linha, 1, "Avisos").font = negrito
        for a in res["avisos"]:
            linha += 1
            ws.cell(linha, 1, a)
        linha += 2
    if res["metodologia"]:
        ws.cell(linha, 1, "Metodologia").font = negrito
        for n in res["metodologia"]:
            linha += 1
            ws.cell(linha, 1, n)
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 28

    usados = {"Resumo"}
    for t in res["tabelas"]:
        nome = "".join(ch for ch in t["titulo"] if ch not in '[]:*?/\\')[:28] or "Tabela"
        base, i = nome, 2
        while nome in usados:
            nome, i = f"{base[:25]} {i}", i + 1
        usados.add(nome)
        w = wb.create_sheet(nome)
        for j, col in enumerate(t["colunas"], start=1):
            c = w.cell(1, j, col["rotulo"])
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = cab
            c.alignment = Alignment(horizontal="center", wrap_text=True)
            w.column_dimensions[get_column_letter(j)].width = max(14, len(col["rotulo"]) + 4)
        for r, l in enumerate(t["linhas"], start=2):
            for j, col in enumerate(t["colunas"], start=1):
                c = w.cell(r, j, _num(l.get(col["chave"]), col["tipo"]))
                _fmt_celula(c, col["tipo"])
        if t.get("total"):
            r = len(t["linhas"]) + 2
            for j, col in enumerate(t["colunas"], start=1):
                v = t["total"].get(col["chave"])
                c = w.cell(r, j, _num(v, col["tipo"]))
                c.font = negrito
                _fmt_celula(c, col["tipo"])
        w.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _num(valor, tipo):
    if valor is None or valor == "":
        return None
    if tipo in ("dinheiro", "percentual", "taxa", "fator"):
        return float(D(valor))
    if tipo == "inteiro" and str(valor).lstrip("-").isdigit():
        return int(valor)
    if tipo in ("data", "mes"):
        return date.fromisoformat(str(valor))
    return valor


def _fmt_celula(c, tipo):
    c.number_format = {"dinheiro": '"R$" #,##0.00', "percentual": '0.0000"%"', "taxa": "0.0000",
                       "fator": "0.00000000", "data": "DD/MM/YYYY", "mes": "MM/YYYY"}.get(tipo, "General")


# -------------------------------------------------------------------- PDF

class _Pdf(FPDF):
    def __init__(self, titulo: str, orientacao: str):
        super().__init__(orientation=orientacao, unit="mm", format="A4")
        self.titulo = titulo
        self.set_auto_page_break(True, margin=16)
        self.set_margins(14, 14, 14)

    def header(self):
        self.set_fill_color(*AZUL)
        self.rect(0, 0, self.w, 4, "F")

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, latin1("Tolaris Calc - memória de cálculo - confira os parâmetros antes de utilizar."),
                  align="L")
        self.cell(0, 5, f"Página {self.page_no()}/{{nb}}", align="R")


def _largura_colunas(colunas, util):
    pesos = {"data": 22, "mes": 18, "dinheiro": 30, "percentual": 24, "taxa": 22, "fator": 24, "inteiro": 14,
             "texto": 50}
    p = [pesos.get(c["tipo"], 30) for c in colunas]
    f = util / sum(p)
    return [x * f for x in p]


def para_pdf(res: dict, ident: dict | None = None) -> bytes:
    larga = any(len(t["colunas"]) > 6 for t in res["tabelas"])
    pdf = _Pdf(res["titulo"], "L" if larga else "P")
    pdf.alias_nb_pages()
    pdf.add_page()
    util = pdf.w - 28

    pdf.set_font("Helvetica", "B", 17)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 9, latin1(res["titulo"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(110, 110, 110)
    emitido = datetime.fromisoformat(res["gerado_em"]).strftime("%d/%m/%Y às %H:%M")
    pdf.cell(0, 5, latin1(f"Tolaris Calc - emitido em {emitido}"), new_x="LMARGIN", new_y="NEXT")
    for k, v in (ident or {}).items():
        if v:
            pdf.cell(0, 5, latin1(f"{k}: {v}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    def secao(txt):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*AZUL)
        pdf.cell(0, 7, latin1(txt.upper()), new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(200, 205, 215)
        pdf.line(14, pdf.get_y(), 14 + util, pdf.get_y())
        pdf.ln(1.5)

    def par(rotulo, valor, destaque=False):
        pdf.set_font("Helvetica", "B" if destaque else "", 10 if not destaque else 11)
        pdf.set_text_color(25, 25, 25)
        pdf.cell(util * 0.62, 6, latin1(rotulo), border=0)
        pdf.cell(util * 0.38, 6, latin1(valor), align="R", new_x="LMARGIN", new_y="NEXT")

    if res["parametros"]:
        secao("Parâmetros")
        for it in res["parametros"]:
            par(it["rotulo"], formatar(it["valor"], it["tipo"]))
    secao("Resultado")
    for it in res["resumo"]:
        if it.get("destaque"):
            pdf.set_fill_color(235, 240, 248)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*AZUL)
            pdf.cell(util * 0.62, 8, latin1(" " + it["rotulo"]), fill=True)
            pdf.cell(util * 0.38, 8, latin1(formatar(it["valor"], it["tipo"]) + " "), fill=True, align="R",
                     new_x="LMARGIN", new_y="NEXT")
        else:
            par(it["rotulo"], formatar(it["valor"], it["tipo"]))
    if res["avisos"]:
        secao("Avisos")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(130, 70, 0)
        for a in res["avisos"]:
            pdf.multi_cell(util, 4.8, latin1("- " + a), new_x="LMARGIN", new_y="NEXT")

    for t in res["tabelas"]:
        if not t["linhas"]:
            continue
        pdf.add_page()
        secao(t["titulo"])
        larg = _largura_colunas(t["colunas"], util)
        def cabecalho():
            pdf.set_fill_color(*AZUL)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 7.5)
            for c, w in zip(t["colunas"], larg):
                pdf.cell(w, 6, latin1(c["rotulo"]), border=1, align="C", fill=True)
            pdf.ln()
        cabecalho()
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(25, 25, 25)
        for n, l in enumerate(t["linhas"]):
            if pdf.get_y() > pdf.h - 20:
                pdf.add_page()
                cabecalho()
                pdf.set_font("Helvetica", "", 7.5)
                pdf.set_text_color(25, 25, 25)
            pdf.set_fill_color(247, 248, 251)
            for c, w in zip(t["colunas"], larg):
                al = "L" if c["tipo"] == "texto" else ("C" if c["tipo"] in ("data", "mes") else "R")
                txt = formatar(l.get(c["chave"]), c["tipo"])
                if c["tipo"] == "dinheiro":
                    txt = txt.replace("R$ ", "")
                pdf.cell(w, 5, latin1(txt), border=1, align=al, fill=n % 2 == 1)
            pdf.ln()
        if t.get("total"):
            pdf.set_font("Helvetica", "B", 7.5)
            for c, w in zip(t["colunas"], larg):
                v = t["total"].get(c["chave"])
                txt = formatar(v, c["tipo"]).replace("R$ ", "") if v is not None else ""
                pdf.cell(w, 5.5, latin1(txt), border=1, align="R" if c["tipo"] != "texto" else "L")
            pdf.ln()

    if res["metodologia"]:
        if pdf.get_y() > pdf.h - 60:
            pdf.add_page()
        secao("Metodologia e premissas")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(60, 60, 60)
        for n in res["metodologia"]:
            pdf.multi_cell(util, 4.6, latin1("- " + n), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.8)
    return bytes(pdf.output())
