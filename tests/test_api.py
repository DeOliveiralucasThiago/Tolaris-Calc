def test_catalogo_e_saude(api):
    assert api.get("/healthz").json() == {"status": "ok"}
    cat = api.get("/api/calculadoras").json()
    assert {c["slug"] for c in cat} >= {"cheque-especial", "atualizacao-monetaria", "financiamento", "prazos"}


def test_erro_de_validacao_422_em_portugues(api):
    r = api.post("/api/calcular/cheque-especial", json={"parametros": {
        "data_inicial": "2025-02-01", "data_final": "2025-01-01", "taxa_cobrada": "8"}})
    assert r.status_code == 422 and "data final" in r.json()["erro"].lower()


def test_calculadora_inexistente(api):
    assert api.post("/api/calcular/nada", json={}).status_code == 404


def test_exportacoes(api):
    res = api.post("/api/calcular/cheque-especial", json={"parametros": {
        "data_inicial": "2025-01-01", "data_final": "2025-03-01", "saldo_inicial": "1000", "taxa_cobrada": "8",
        "taxa_revisada": "4"}}).json()
    corpo = {"resultado": res, "identificacao": {"Processo": "0001234-56.2025.8.26.0100"}}
    pdf = api.post("/api/exportar/pdf", json=corpo)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    xlsx = api.post("/api/exportar/xlsx", json=corpo)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"


def test_todas_as_calculadoras_geram_pdf(api):
    entradas = {
        "financiamento": {"valor": "5000", "parcelas": 6, "taxa_contratada": "2", "taxa_revisada": "1"},
        "prazos": {"data": "2025-03-03", "prazo": 10},
        "reajuste": {"valor": "1000", "data_reajuste": "2026-01-01"},
        "juros-taxas": {"modo": "montante", "principal": "100", "taxa": "1", "prazo": "6"},
        "atualizacao-monetaria": {"valor": "100", "data_base": "2025-01-01", "data_calculo": "2025-08-01"},
    }
    for slug, params in entradas.items():
        r = api.post(f"/api/calcular/{slug}", json={"parametros": params})
        assert r.status_code == 200, (slug, r.text)
        assert api.post("/api/exportar/pdf", json={"resultado": r.json()}).content[:4] == b"%PDF"


def test_autenticacao_basic_opcional(api, monkeypatch):
    import base64
    from app import main
    monkeypatch.setattr(main, "USUARIO", "escritorio")
    monkeypatch.setattr(main, "SENHA", "s3nha-çã")
    assert api.get("/api/calculadoras").status_code == 401
    assert api.get("/healthz").status_code == 200  # health check do Render não exige login
    bom = base64.b64encode("escritorio:s3nha-çã".encode()).decode()
    ruim = base64.b64encode(b"escritorio:errada").decode()
    assert api.get("/api/calculadoras", headers={"Authorization": f"Basic {bom}"}).status_code == 200
    assert api.get("/api/calculadoras", headers={"Authorization": f"Basic {ruim}"}).status_code == 401
