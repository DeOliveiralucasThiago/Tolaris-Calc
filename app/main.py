"""Tolaris Calc – API e entrega do front-end estático."""
from __future__ import annotations

import base64
import logging
import os
import secrets
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .calculators import MODULOS, POR_SLUG
from .core.campos import converter
from .core.erros import ErroDeValidacao, IndiceIndisponivel
from .core.indices import SERIES, obter_serie
from .reports.exportadores import para_pdf, para_xlsx

log = logging.getLogger("tolaris")
RAIZ = Path(__file__).resolve().parents[1]
ESTATICO = RAIZ / "static"

app = FastAPI(title="Tolaris Calc", version="2.0.0", docs_url="/api/docs", redoc_url=None)


USUARIO = os.environ.get("TOLARIS_USUARIO")
SENHA = os.environ.get("TOLARIS_SENHA")


@app.middleware("http")
async def autenticacao(request: Request, call_next):
    """Autenticação HTTP Basic opcional: ativa quando TOLARIS_USUARIO e TOLARIS_SENHA estão definidos."""
    if USUARIO and SENHA and request.url.path != "/healthz":
        ok = False
        cab = request.headers.get("authorization", "")
        if cab.lower().startswith("basic "):
            try:
                usr, _, pwd = base64.b64decode(cab[6:]).decode("utf-8").partition(":")
                ok = (secrets.compare_digest(usr.encode(), USUARIO.encode())
                      & secrets.compare_digest(pwd.encode(), SENHA.encode()))
            except Exception:
                ok = False
        if not ok:
            return Response("Autenticação necessária.", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Tolaris Calc", charset="UTF-8"'})
    return await call_next(request)


@app.middleware("http")
async def cabecalhos(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")  # uso interno: fora dos buscadores
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(ErroDeValidacao)
async def _validacao(_: Request, exc: ErroDeValidacao):
    return JSONResponse({"erro": str(exc), "campo": exc.campo}, status_code=422)


@app.exception_handler(IndiceIndisponivel)
async def _indice(_: Request, exc: IndiceIndisponivel):
    return JSONResponse({"erro": str(exc), "campo": None}, status_code=503)


@app.get("/healthz")
def saude():
    return {"status": "ok"}


@app.get("/api/calculadoras")
def listar():
    return [{k: m.META[k] for k in ("slug", "titulo", "categoria", "icone", "descricao", "campos")} for m in MODULOS]


@app.post("/api/calcular/{slug}")
def calcular(slug: str, corpo: dict[str, Any]):
    modulo = POR_SLUG.get(slug)
    if modulo is None:
        raise HTTPException(404, "Calculadora não encontrada.")
    params = converter(modulo.META["campos"], corpo.get("parametros", corpo))
    try:
        return modulo.calcular(params).para_dict()
    except (ErroDeValidacao, IndiceIndisponivel):
        raise
    except ArithmeticError as exc:
        raise ErroDeValidacao("Os valores informados geram um resultado fora do intervalo calculável.") from exc


class Exportacao(BaseModel):
    resultado: dict
    identificacao: dict[str, str] = {}


def _nome(res: dict, ext: str) -> str:
    """Nome de arquivo ASCII (cabeçalhos HTTP não aceitam acentos)."""
    sem_acento = unicodedata.normalize("NFKD", res.get("titulo", "calculo")).encode("ascii", "ignore").decode()
    base = "".join(c if c.isalnum() else "_" for c in sem_acento).strip("_") or "calculo"
    return f"Tolaris_{base}.{ext}"


@app.post("/api/exportar/pdf")
def exportar_pdf(e: Exportacao):
    return Response(para_pdf(e.resultado, e.identificacao), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_nome(e.resultado, "pdf")}"'})


@app.post("/api/exportar/xlsx")
def exportar_xlsx(e: Exportacao):
    return Response(para_xlsx(e.resultado, e.identificacao),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_nome(e.resultado, "xlsx")}"'})


@app.get("/api/indices")
def indices_catalogo():
    return [{"nome": k, "descricao": v.descricao, "codigo_sgs": v.codigo} for k, v in SERIES.items()]


@app.get("/api/indices/{nome}")
def indice(nome: str, atualizar: bool = False):
    if nome not in SERIES:
        raise HTTPException(404, "Índice não encontrado.")
    s = obter_serie(nome, forcar=atualizar)
    meses = sorted(s.valores, reverse=True)[:240]
    return {"nome": nome, "origem": s.origem, "atualizado_em": s.atualizado_em, "ultimo_mes": s.ultimo_mes,
            "acumulo": SERIES[nome].acumulo, "valores": [{"mes": m, "indice": str(s.valores[m])} for m in meses]}


@app.get("/")
def raiz():
    return FileResponse(ESTATICO / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=ESTATICO), name="static")
