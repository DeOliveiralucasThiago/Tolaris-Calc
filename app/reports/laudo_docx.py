"""Laudo em Word (.docx) editável a partir do Resultado padrão."""
from __future__ import annotations

import io
from datetime import datetime

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .exportadores import formatar

AZUL = RGBColor(0x0F, 0x26, 0x47)
CINZA = RGBColor(0x6B, 0x72, 0x80)
FONTE = "Times New Roman"


def _fonte(estilo, tamanho=None, negrito=None, cor=None, nome=FONTE):
    f = estilo.font
    f.name = nome
    rfonts = estilo.element.rPr.rFonts
    rfonts.set(qn("w:eastAsia"), nome)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):  # fontes do tema sobrescrevem o nome
        if rfonts.get(qn(attr)) is not None:
            del rfonts.attrib[qn(attr)]
    if tamanho:
        f.size = Pt(tamanho)
    if negrito is not None:
        f.bold = negrito
    if cor is not None:
        f.color.rgb = cor


def _sombra(celula, hex_cor: str):
    tc = celula._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_cor)
    tc.append(shd)


def _repetir_cabecalho(linha):
    trPr = linha._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def _nao_quebrar(linha):
    trPr = linha._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))


def _campo(par, instrucao: str):
    """Insere um campo do Word (ex.: PAGE, NUMPAGES)."""
    run = par.add_run()
    for tipo, texto in (("begin", None), (None, instrucao), ("separate", None), (None, "1"), ("end", None)):
        if tipo:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tipo)
        elif texto == instrucao:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = f" {instrucao} "
        else:
            el = OxmlElement("w:t")
            el.text = texto
        run._r.append(el)
    return run


def _texto_celula(celula, texto, tamanho=10, negrito=False, alinhamento=WD_ALIGN_PARAGRAPH.LEFT, cor=None):
    p = celula.paragraphs[0]
    p.alignment = alinhamento
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    r = p.add_run(str(texto))
    r.font.size = Pt(tamanho)
    r.bold = negrito
    if cor is not None:
        r.font.color.rgb = cor


def _titulo_secao(doc, texto):
    p = doc.add_heading(texto, level=1)
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    return p


_PESOS = {"data": 2.2, "mes": 1.8, "dinheiro": 3.0, "percentual": 2.4, "taxa": 2.2, "fator": 2.6, "inteiro": 1.4,
          "texto": 5.0}


def _tabela_dados(doc, t, largura_cm: float):
    colunas = t["colunas"]
    tabela = doc.add_table(rows=1, cols=len(colunas))
    tabela.style = "Table Grid"
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabela.autofit = False
    pesos = [_PESOS.get(c["tipo"], 3.0) for c in colunas]
    larguras = [largura_cm * p / sum(pesos) for p in pesos]
    tamanho = 8 if len(colunas) > 6 else 9
    for i, c in enumerate(colunas):
        cel = tabela.rows[0].cells[i]
        _sombra(cel, "0F2647")
        _texto_celula(cel, c["rotulo"], tamanho, True, WD_ALIGN_PARAGRAPH.CENTER, RGBColor(255, 255, 255))
    _repetir_cabecalho(tabela.rows[0])

    def alinha(tipo):
        return (WD_ALIGN_PARAGRAPH.LEFT if tipo == "texto" else
                WD_ALIGN_PARAGRAPH.CENTER if tipo in ("data", "mes") else WD_ALIGN_PARAGRAPH.RIGHT)

    for n, linha in enumerate(t["linhas"]):
        cels = tabela.add_row().cells
        _nao_quebrar(tabela.rows[-1])
        for i, c in enumerate(colunas):
            txt = formatar(linha.get(c["chave"]), c["tipo"])
            if c["tipo"] == "dinheiro":
                txt = txt.replace("R$ ", "")
            _texto_celula(cels[i], txt, tamanho, False, alinha(c["tipo"]))
            if n % 2:
                _sombra(cels[i], "F3F5F9")
    if t.get("total"):
        cels = tabela.add_row().cells
        for i, c in enumerate(colunas):
            v = t["total"].get(c["chave"])
            txt = formatar(v, c["tipo"]).replace("R$ ", "") if v is not None else ""
            _texto_celula(cels[i], txt, tamanho, True, alinha(c["tipo"]))
            _sombra(cels[i], "EBEFF6")
    for linha in tabela.rows:
        for i, cel in enumerate(linha.cells):
            cel.width = Cm(larguras[i])
    return tabela


def para_docx(res: dict, ident: dict | None = None) -> bytes:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
    util = 21 - 4.4

    _fonte(doc.styles["Normal"], 11)
    doc.styles["Normal"].paragraph_format.space_after = Pt(4)
    _fonte(doc.styles["Title"], 20, True, AZUL)
    for nome, tam in (("Heading 1", 12.5), ("Heading 2", 11)):
        _fonte(doc.styles[nome], tam, True, AZUL)
    _fonte(doc.styles["List Bullet"], 10.5)
    _fonte(doc.styles["Header"], 8.5, cor=CINZA)
    _fonte(doc.styles["Footer"], 8.5, cor=CINZA)
    # remove a linha decorativa que o estilo Title traz por padrão
    ppr = doc.styles["Title"].element.get_or_add_pPr()
    for b in ppr.findall(qn("w:pBdr")):
        ppr.remove(b)

    # cabeçalho e rodapé
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = hp.add_run("Tolaris Calc · memória de cálculo")
    r.font.size, r.font.color.rgb = Pt(8.5), CINZA
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for parte in ("Página ", None, " de ", "NUMPAGES"):
        if parte is None:
            run = _campo(fp, "PAGE")
        elif parte == "NUMPAGES":
            run = _campo(fp, "NUMPAGES")
        else:
            run = fp.add_run(parte)
        run.font.size, run.font.color.rgb = Pt(8.5), CINZA

    # título
    doc.add_paragraph(res["titulo"], style="Title")
    emitido = datetime.fromisoformat(res["gerado_em"]).strftime("%d/%m/%Y às %H:%M")
    p = doc.add_paragraph()
    r = p.add_run(f"Emitido em {emitido}")
    r.font.size, r.font.color.rgb = Pt(9.5), CINZA

    ident = {k: v for k, v in (ident or {}).items() if v}
    if ident:
        t = doc.add_table(rows=0, cols=2)
        t.style = "Table Grid"
        for k, v in ident.items():
            c = t.add_row().cells
            _texto_celula(c[0], k, 10, True)
            _sombra(c[0], "F3F5F9")
            _texto_celula(c[1], v, 10)
            c[0].width, c[1].width = Cm(4), Cm(util - 4)

    # parâmetros
    if res["parametros"]:
        _titulo_secao(doc, "1. Parâmetros do cálculo")
        t = doc.add_table(rows=0, cols=2)
        t.style = "Table Grid"
        for it in res["parametros"]:
            c = t.add_row().cells
            _texto_celula(c[0], it["rotulo"], 10)
            _texto_celula(c[1], formatar(it["valor"], it["tipo"]), 10, False, WD_ALIGN_PARAGRAPH.RIGHT)
            c[0].width, c[1].width = Cm(util * 0.58), Cm(util * 0.42)

    # resultado
    _titulo_secao(doc, "2. Resultado")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for it in res["resumo"]:
        c = t.add_row().cells
        dest = bool(it.get("destaque"))
        rot = it["rotulo"] + (f" ({it['nota']})" if it.get("nota") and not dest else "")
        _texto_celula(c[0], rot, 10.5 if dest else 10, dest)
        _texto_celula(c[1], formatar(it["valor"], it["tipo"]), 10.5 if dest else 10, dest, WD_ALIGN_PARAGRAPH.RIGHT)
        if dest:
            _sombra(c[0], "DCE6F5")
            _sombra(c[1], "DCE6F5")
        c[0].width, c[1].width = Cm(util * 0.66), Cm(util * 0.34)

    n_sec = 3
    if res["avisos"]:
        _titulo_secao(doc, f"{n_sec}. Avisos e ressalvas")
        for a in res["avisos"]:
            doc.add_paragraph(a, style="List Bullet")
        n_sec += 1
    if res["metodologia"]:
        _titulo_secao(doc, f"{n_sec}. Metodologia e premissas")
        for m in res["metodologia"]:
            doc.add_paragraph(m, style="List Bullet")
        n_sec += 1

    # fecho para assinatura (editável)
    _titulo_secao(doc, f"{n_sec}. Conclusão")
    doc.add_paragraph("Os valores acima foram apurados conforme os parâmetros e premissas descritos neste documento. "
                      "[Complemente ou ajuste este texto antes de juntar aos autos.]")
    doc.add_paragraph("\nLocal e data: ______________________________")
    resp = ident.get("Responsável")
    doc.add_paragraph("\n______________________________________\n" + (resp or "Responsável pelo cálculo"))

    # anexos: memória de cálculo
    tabelas = [t for t in res["tabelas"] if t["linhas"]]
    if tabelas:
        larga = any(len(t["colunas"]) > 6 for t in tabelas)
        nova = doc.add_section(WD_SECTION.NEW_PAGE)
        if larga:
            nova.orientation = WD_ORIENT.LANDSCAPE
            nova.page_width, nova.page_height = Cm(29.7), Cm(21)
        largura = (29.7 if larga else 21) - 4.4
        nova.left_margin = nova.right_margin = Cm(2.2)
        _titulo_secao(doc, "Anexo – Memória de cálculo")
        for t in tabelas:
            h = doc.add_heading(t["titulo"], level=2)
            h.paragraph_format.keep_with_next = True
            _tabela_dados(doc, t, largura)
            doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
