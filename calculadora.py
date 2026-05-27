import streamlit as st
import pandas as pd
import requests
import io
import json
import os
from datetime import datetime, timedelta, date
from decimal import Decimal
from fpdf import FPDF
from dateutil.relativedelta import relativedelta

# Configuração global da página
st.set_page_config(page_title="Tolaris Calc - Hub Pericial", layout="wide", initial_sidebar_state="expanded")

# --- GERENCIADOR DE ESTADO DE NAVEGAÇÃO (ROTEADOR SPA) ---
if 'menu_principal' not in st.session_state:
    st.session_state.menu_principal = "Início"
if 'ferramenta_ativa' not in st.session_state:
    st.session_state.ferramenta_ativa = "Painel"

def navegar_para(menu, ferramenta="Painel"):
    st.session_state.menu_principal = menu
    st.session_state.ferramenta_ativa = ferramenta

# --- ESTILIZAÇÃO COMPLEMENTAR (CSS INJETADO) ---
st.markdown("""
    <style>
    button[kind="primary"] {
        background-color: #004080 !important;
        border-color: #004080 !important;
        color: white !important;
    }
    button[kind="primary"]:hover {
        background-color: #00264d !important;
        border-color: #00264d !important;
    }
    .stApp {
        background-color: #f8f9fa;
    }
    .navbar-container {
        padding-bottom: 10px;
        border-bottom: 2px solid #e0e0e0;
        margin-bottom: 20px;
    }
    .tool-card {
        background-color: white; 
        padding: 20px; 
        border-radius: 8px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
        margin-bottom: 15px;
        border-left: 4px solid #004080;
    }
    .tool-card-trabalhista {
        border-left: 4px solid #28a745;
    }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# --- MENU DE NAVEGAÇÃO SUPERIOR FIXO ---
# =================================================================
st.markdown("<div class='navbar-container'>", unsafe_allow_html=True)
col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1, 1, 1, 3])
with col_nav1:
    st.button("🏠 INÍCIO", on_click=navegar_para, args=("Início", "Painel"), use_container_width=True, type="primary" if st.session_state.menu_principal == "Início" else "secondary")
with col_nav2:
    st.button("⚖️ CÍVEL", on_click=navegar_para, args=("Cível", "Painel"), use_container_width=True, type="primary" if st.session_state.menu_principal == "Cível" else "secondary")
with col_nav3:
    st.button("👷 TRABALHISTA", on_click=navegar_para, args=("Trabalhista", "Painel"), use_container_width=True, type="primary" if st.session_state.menu_principal == "Trabalhista" else "secondary")
st.markdown("</div>", unsafe_allow_html=True)

# =================================================================
# --- FUNÇÕES AUXILIARES GERAIS E INTEGRAÇÕES ---
# =================================================================
@st.cache_data
def buscar_indice_bcb(codigo_bcb):
    try:
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_bcb}/dados?formato=json"
        resposta = requests.get(url)
        df = pd.DataFrame(resposta.json())
        df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y')
        df['Mês/Ano'] = df['data'].dt.strftime('%Y-%m')
        df['Índice (%)'] = df['valor'].astype(float)
        return df[['Mês/Ano', 'Índice (%)']]
    except:
        return pd.DataFrame(columns=["Mês/Ano", "Índice (%)"])

@st.cache_data
def obter_historico_salario_minimo():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1619/dados?formato=json"
        resposta = requests.get(url)
        df = pd.DataFrame(resposta.json())
        df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y')
        df['Ano'] = df['data'].dt.year
        df['valor'] = df['valor'].astype(float)
        df_real = df[df['Ano'] >= 1995]
        df_ano = df_real.groupby('Ano').last().reset_index()
        dict_sm = {f"{int(row['Ano'])} - R$ {row['valor']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'): float(row['valor']) for _, row in df_ano.iterrows()}
        dict_sm["Outro (Digitar Manualmente)"] = 0.00
        dict_sm["2026 - R$ 1.621,00"] = 1621.00
        dict_ordenado = dict(sorted(dict_sm.items(), key=lambda item: item[1], reverse=True))
        if "Outro (Digitar Manualmente)" in dict_ordenado:
            dict_ordenado["Outro (Digitar Manualmente)"] = dict_ordenado.pop("Outro (Digitar Manualmente)")
        return dict_ordenado
    except:
        return {"2026 - R$ 1.621,00": 1621.00, "2025 - R$ 1.518,00": 1518.00, "2024 - R$ 1.412,00": 1412.00, "Outro (Digitar Manualmente)": 0.00}

# --- NOVO BANCO DE DADOS (JSON) PARA TRIBUTOS ---
@st.cache_data
def carregar_tributos_json():
    caminho_arquivo = 'tributos.json'
    if os.path.exists(caminho_arquivo):
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def calcular_imposto_dinamico(valor_base, ano_competencia, tipo_imposto):
    db_tributos = carregar_tributos_json()
    ano_str = str(ano_competencia)
    
    # Validação de segurança: se o ano não existir no JSON, usa o mais recente conhecido ou cai pro fallback
    if not db_tributos or ano_str not in db_tributos:
        ano_str = "2024" if db_tributos and "2024" in db_tributos else None

    # Fallback Hardcoded de segurança caso o arquivo tributos.json não exista na pasta
    if not ano_str:
        if tipo_imposto == "INSS":
            if valor_base <= 1412.00: return valor_base * 0.075
            elif valor_base <= 2666.68: return (valor_base * 0.09) - 21.18
            elif valor_base <= 4000.03: return (valor_base * 0.12) - 101.18
            elif valor_base <= 7786.02: return (valor_base * 0.14) - 181.18
            else: return 908.85
        elif tipo_imposto == "IRRF":
            if valor_base <= 2259.20: return 0.0
            elif valor_base <= 2826.65: return (valor_base * 0.075) - 169.44
            elif valor_base <= 3751.05: return (valor_base * 0.15) - 381.44
            elif valor_base <= 4664.68: return (valor_base * 0.225) - 662.77
            else: return (valor_base * 0.275) - 896.00

    # Lógica Dinâmica baseada no JSON
    dados_imposto = db_tributos[ano_str][tipo_imposto]
    tipo_calculo = dados_imposto.get("tipo", "progressivo")
    faixas = dados_imposto["faixas"]
    
    if tipo_imposto == "INSS":
        teto_inss = dados_imposto.get("teto_inss", 908.85)
        
        if tipo_calculo == "aliquota_unica":
            for faixa in faixas:
                if valor_base <= faixa["limite"]:
                    return valor_base * faixa["aliquota"]
            return teto_inss
        else:
            for faixa in faixas:
                if valor_base <= faixa["limite"]:
                    return (valor_base * faixa["aliquota"]) - faixa["deducao"]
            return teto_inss
            
    elif tipo_imposto == "IRRF":
        for faixa in faixas:
            if valor_base <= faixa["limite"]:
                imposto = (valor_base * faixa["aliquota"]) - faixa["deducao"]
                return max(imposto, 0.0)
        return 0.0

# =================================================================
# --- EXPORTADORES PDF/EXCEL ---
# =================================================================
def gerar_excel_bancario(df_resumo, df_detalhado):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_resumo.to_excel(writer, sheet_name='Resumo da Divida', index=False)
        df_detalhado.to_excel(writer, sheet_name='Memoria de Calculo', index=False)
    return output.getvalue()

def gerar_pdf_bancario(resumo_dados, df_detalhado, indice_nome, juros_tipo, taxa):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.set_font("Arial", style="B", size=16)
    pdf.set_text_color(0, 64, 128) 
    pdf.cell(0, 10, "TOLARIS CALC - AUDITORIA DE CONTRATOS", ln=True, align="C")
    pdf.set_text_color(0, 0, 0) 
    pdf.set_font("Arial", style="I", size=10)
    pdf.cell(0, 10, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(0, 8, "1. PARÂMETROS DO CONTRATO E ATUALIZAÇÃO", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 6, f"Índice: {indice_nome if indice_nome != 'Sem Atualização (Apenas Juros)' else 'Não Aplicado'}", ln=True)
    pdf.cell(0, 6, f"Método: Juros {juros_tipo} | Taxa: {taxa:.3f}% ao mês", ln=True)
    pdf.cell(0, 6, f"Período Analisado: {resumo_dados['Dias']} dias", ln=True)
    pdf.ln(8)
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(0, 8, "2. RESUMO DOS VALORES", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 6, f"Saldo Original (Sem Juros): R$ {resumo_dados['Original']:.2f}", ln=True)
    pdf.cell(0, 6, f"Total de Juros Computados: R$ {resumo_dados['Juros']:.2f}", ln=True)
    pdf.set_font("Arial", style="B", size=11)
    pdf.cell(0, 6, f"VALOR TOTAL RECALCULADO: R$ {resumo_dados['Final']:.2f}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(0, 8, "3. MEMÓRIA DE CÁLCULO DIÁRIA", ln=True)
    pdf.ln(2)
    pdf.set_font("Arial", style="B", size=9)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(25, 6, "Data", border=1, align="C", fill=True)
    pdf.cell(35, 6, "S. Anterior", border=1, align="R", fill=True)
    pdf.cell(20, 6, "Corr. (R$)", border=1, align="R", fill=True)
    pdf.cell(28, 6, "Débitos (-)", border=1, align="R", fill=True)
    pdf.cell(28, 6, "Créditos (+)", border=1, align="R", fill=True)
    pdf.cell(35, 6, "S. Final Dia", border=1, align="R", fill=True)
    pdf.ln()
    pdf.set_font("Arial", size=8)
    for _, row in df_detalhado.iterrows():
        pdf.cell(25, 5, str(row["Data"]), border=1, align="C")
        pdf.cell(35, 5, f"{row['Saldo Anterior']:.2f}", border=1, align="R")
        pdf.cell(20, 5, f"{row['Correção (R$)']:.2f}", border=1, align="R")
        pdf.cell(28, 5, f"{row['Débitos (R$)']:.2f}", border=1, align="R")
        pdf.cell(28, 5, f"{row['Créditos (R$)']:.2f}", border=1, align="R")
        pdf.cell(35, 5, f"{row['Saldo Final Dia']:.2f}", border=1, align="R")
        pdf.ln()
    return bytes(pdf.output())

def gerar_excel_trabalhista(df_rescisao, info_contrato, totais):
    output = io.BytesIO()
    df_info = pd.DataFrame([
        {"Parametro": "Admissao", "Valor": info_contrato['admissao']},
        {"Parametro": "Demissao", "Valor": info_contrato['demissao']},
        {"Parametro": "Ano Competencia Fiscal", "Valor": info_contrato['ano_competencia']},
        {"Parametro": "Motivo", "Valor": info_contrato['motivo']},
        {"Parametro": "Base Rescisao", "Valor": f"R$ {info_contrato['remun_rescisoria']:.2f}"},
        {"Parametro": "Total de Deducoes", "Valor": f"R$ {totais['deducoes']:.2f}"},
        {"Parametro": "Valores Ja Pagos", "Valor": f"R$ {info_contrato['valores_pagos']:.2f}"},
        {"Parametro": "Liquido a Receber", "Valor": f"R$ {totais['liquido']:.2f}"},
        {"Parametro": "Honorarios Contratuais", "Valor": f"R$ {totais['hon_contratuais']:.2f}"},
        {"Parametro": "Honorarios Sucumbenciais", "Valor": f"R$ {totais['hon_sucumbenciais']:.2f}"}
    ])
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_info.to_excel(writer, sheet_name='Parametros', index=False)
        df_rescisao.to_excel(writer, sheet_name='Rubricas', index=False)
    return output.getvalue()

def gerar_pdf_trabalhista(df_rescisao, info_contrato, totais):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.set_font("Arial", style="B", size=16)
    pdf.set_text_color(0, 64, 128) 
    pdf.cell(0, 10, "TOLARIS CALC - LIQUIDACAO TRABALHISTA", ln=True, align="C")
    pdf.set_text_color(0, 0, 0) 
    pdf.set_font("Arial", style="I", size=10)
    pdf.cell(0, 6, f"Emitido em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align="C")
    pdf.ln(8)
    
    pdf.set_font("Arial", style="B", size=12)
    pdf.set_text_color(0, 64, 128)
    pdf.cell(0, 8, "1. INFORMACOES DO CONTRATO", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=10)
    pdf.cell(95, 6, f"Data de Admissao: {info_contrato['admissao']}", border=0)
    pdf.cell(95, 6, f"Data de Demissao: {info_contrato['demissao']}", border=0, ln=True)
    pdf.cell(95, 6, f"Enquadramento da Extincao: {info_contrato['motivo']}", border=0)
    pdf.cell(95, 6, f"Tabela Fiscal (INSS/IRRF): Ano Base {info_contrato['ano_competencia']}", border=0, ln=True)
    pdf.ln(4)
    pdf.set_fill_color(235, 240, 245)
    pdf.cell(0, 8, f" Base de Calculo Rescisoria (Complexo Salarial): R$ {info_contrato['remun_rescisoria']:.2f}", border=1, ln=True, fill=True)
    pdf.ln(6)
    
    pdf.set_font("Arial", style="B", size=12)
    pdf.set_text_color(0, 64, 128)
    pdf.cell(0, 8, "2. DEMONSTRATIVO DE RUBRICAS", ln=True)
    
    pdf.set_font("Arial", style="B", size=10)
    pdf.set_fill_color(0, 64, 128)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(95, 7, "Verba / Descricao", border=1, align="L", fill=True)
    pdf.cell(30, 7, "Fluxo", border=1, align="C", fill=True)
    pdf.cell(35, 7, "Natureza", border=1, align="C", fill=True)
    pdf.cell(30, 7, "Valor (R$)", border=1, align="R", fill=True)
    pdf.ln()
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=9)
    for _, row in df_rescisao.iterrows():
        pdf.cell(95, 6, str(row['Verba']).replace('º', 'o').encode('latin-1', 'replace').decode('latin-1'), border=1)
        pdf.cell(30, 6, str(row['Tipo']), border=1, align="C")
        pdf.cell(35, 6, str(row['Natureza']), border=1, align="C")
        pdf.cell(30, 6, f"{row['Valor (R$)']:.2f}", border=1, align="R")
        pdf.ln()
        
    pdf.ln(4)
    pdf.set_font("Arial", style="B", size=10)
    pdf.cell(160, 6, "TOTAL BRUTO (PROVENTOS):", border=0, align="R")
    pdf.cell(30, 6, f"R$ {totais['bruto']:.2f}", border=0, align="R", ln=True)
    pdf.set_text_color(150, 0, 0)
    pdf.cell(160, 6, "TOTAL DE DESCONTOS LEGAIS:", border=0, align="R")
    pdf.cell(30, 6, f"R$ {totais['deducoes']:.2f}", border=0, align="R", ln=True)
    
    if info_contrato['valores_pagos'] > 0:
        pdf.cell(160, 6, "ABATIMENTO / VALORES JA PAGOS:", border=0, align="R")
        pdf.cell(30, 6, f"R$ {info_contrato['valores_pagos']:.2f}", border=0, align="R", ln=True)

    pdf.set_text_color(0, 100, 0)
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(160, 8, "CREDITO LIQUIDO DO TRABALHADOR:", border=0, align="R")
    pdf.cell(30, 8, f"R$ {totais['liquido']:.2f}", border=0, align="R", ln=True)
    pdf.set_text_color(0, 0, 0)
    
    pdf.ln(6)
    pdf.set_font("Arial", style="B", size=12)
    pdf.set_text_color(0, 64, 128)
    pdf.cell(0, 8, "3. MULTAS, CONTA VINCULADA E HONORARIOS", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=10)
    
    pdf.cell(0, 6, f"Saldo Estimado FGTS (8%): R$ {totais['fgts_deposito']:.2f}", border=0, ln=True)
    pdf.cell(0, 6, f"Multa Rescisoria (40% FGTS): R$ {totais['fgts_multa']:.2f}", border=0, ln=True)
    pdf.cell(0, 6, f"Multa do Art. 477 da CLT: R$ {totais['multa_477']:.2f}", border=0, ln=True)
    if info_contrato['multa_467']:
        pdf.cell(0, 6, f"Multa do Art. 467 da CLT (50% incontroversas): Aplicada no demonstrativo", border=0, ln=True)
    
    pdf.ln(4)
    if totais['hon_sucumbenciais'] > 0 or totais['hon_contratuais'] > 0:
        pdf.set_font("Arial", style="B", size=10)
        pdf.cell(0, 6, "Demonstrativo de Honorarios Advocaticios:", border=0, ln=True)
        pdf.set_font("Arial", size=10)
        if totais['hon_sucumbenciais'] > 0:
            pdf.cell(0, 6, f"- Honorarios Sucumbenciais (Base Bruta): R$ {totais['hon_sucumbenciais']:.2f}", border=0, ln=True)
        if totais['hon_contratuais'] > 0:
            pdf.cell(0, 6, f"- Honorarios Contratuais (Base Liquida): R$ {totais['hon_contratuais']:.2f}", border=0, ln=True)

    return bytes(pdf.output())

# =================================================================
# --- MÓDULOS CÍVEIS ---
# =================================================================
def modulo_cheque_especial():
    st.header("🕵️ Auditoria de Cheque Especial e Contratos")
    
    if 'reset_contador' not in st.session_state:
        st.session_state.reset_contador = 0
    def limpar_tabela():
        st.session_state.reset_contador += 1
    
    CODIGOS_BCB = {"IGP-M": 189, "IPCA": 433, "INPC": 188, "INCC": 192}

    with st.sidebar:
        data_inicial = st.date_input("Data Inicial", value=None, min_value=date(1980, 1, 1), format="DD/MM/YYYY")
        data_final = st.date_input("Data Final", value=None, min_value=date(1980, 1, 1), format="DD/MM/YYYY")
        saldo_inicial = st.number_input("Saldo Inicial Negativo (R$)", value=0.00, step=100.0)
        st.markdown("---")
        opcoes_indices = ["Sem Atualização (Apenas Juros)"] + list(CODIGOS_BCB.keys())
        indice_escolhido = st.selectbox("Índice de Atualização", opcoes_indices)
        tipo_juros = st.radio("Método de Juros", ["Compostos", "Simples"])
        taxa_juros = st.number_input("Taxa de Juros a.m. (%)", value=8.000, format="%.3f")

        if indice_escolhido == "Sem Atualização (Apenas Juros)":
            df_indices = pd.DataFrame(columns=["Mês/Ano", "Índice (%)"])
        else:
            codigo_atual = CODIGOS_BCB[indice_escolhido]
            df_historico_completo = buscar_indice_bcb(codigo_atual)
            if data_inicial:
                ano_inicio = str(data_inicial.year)
                df_filtrado = df_historico_completo[df_historico_completo['Mês/Ano'] >= f"{ano_inicio}-01"].copy() if not df_historico_completo.empty else pd.DataFrame(columns=["Mês/Ano", "Índice (%)"])
            else:
                df_filtrado = pd.DataFrame(columns=["Mês/Ano", "Índice (%)"])
            df_indices = st.data_editor(df_filtrado, num_rows="dynamic", hide_index=True)

    if not data_inicial or not data_final:
        st.info("👈 Defina os parâmetros no menu lateral para iniciar.")
        return
    if data_inicial > data_final:
        st.error("⚠️ A Data Inicial não pode ser posterior à Data Final.")
        return

    dias_totais = (data_final - data_inicial).days
    datas_iniciais = [(data_inicial + timedelta(days=i)) for i in range(dias_totais + 1)]
    df_lancamentos_iniciais = pd.DataFrame({"Data": datas_iniciais, "Débitos (-)": [0.00 for _ in range(len(datas_iniciais))], "Créditos (+)": [0.00 for _ in range(len(datas_iniciais))]})

    df_lancamentos = st.data_editor(
        df_lancamentos_iniciais, key=f"tabela_lancamentos_{st.session_state.reset_contador}", num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={"Data": st.column_config.DateColumn("Data", min_value=date(1980, 1, 1), format="DD/MM/YYYY"), "Débitos (-)": st.column_config.NumberColumn("Débitos (-)", format="R$ %.2f"), "Créditos (+)": st.column_config.NumberColumn("Créditos (+)", format="R$ %.2f")}
    )

    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        btn_processar = st.button("PROCESSAR REVISÃO BANCÁRIA", type="primary", use_container_width=True)
    with col_btn2:
        st.button("🧹 Limpar Tabela", on_click=limpar_tabela, use_container_width=True)

    if btn_processar:
        dic_indices = {row["Mês/Ano"]: Decimal(str(row["Índice (%)"] / 100)) for _, row in df_indices.iterrows()}
        dic_lancamentos = {}
        for _, row in df_lancamentos.iterrows():
            try:
                data_str = pd.to_datetime(row["Data"], format="%d/%m/%Y").strftime("%Y-%m-%d")
                dic_lancamentos[data_str] = {"debitos": Decimal(str(row["Débitos (-)"])), "creditos": Decimal(str(row["Créditos (+)"]))}
            except: pass

        memoria_calculo = []
        saldo_atual = Decimal(str(saldo_inicial))
        data_atual = data_inicial
        col_taxa_nome = "Taxa de Atualização (%)" if indice_escolhido == "Sem Atualização (Apenas Juros)" else f"Taxa {indice_escolhido} (%)"
        
        while data_atual <= data_final:
            str_data = data_atual.strftime("%Y-%m-%d")
            mes_ano_anterior = (data_atual.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            saldo_inicio_dia = saldo_atual
            valor_correcao, percentual_aplicado = Decimal('0.00'), Decimal('0.00')
            
            if data_atual.day == 1 and mes_ano_anterior in dic_indices:
                percentual_aplicado = dic_indices[mes_ano_anterior]
                valor_correcao = saldo_atual * percentual_aplicado
                saldo_atual += valor_correcao
                
            lancamentos_dia = dic_lancamentos.get(str_data, {"debitos": Decimal('0.00'), "creditos": Decimal('0.00')})
            saldo_atual = saldo_atual + lancamentos_dia["debitos"] - lancamentos_dia["creditos"]
            
            memoria_calculo.append({"Data": data_atual.strftime("%d/%m/%Y"), "Saldo Anterior": float(saldo_inicio_dia), col_taxa_nome: float(percentual_aplicado * 100), "Correção (R$)": float(valor_correcao), "Débitos (R$)": float(lancamentos_dia["debitos"]), "Créditos (R$)": float(lancamentos_dia["creditos"]), "Saldo Final Dia": float(saldo_atual)})
            data_atual += timedelta(days=1)
        
        taxa_mensal_dec = Decimal(str(taxa_juros / 100))
        taxa_periodo = (1 + taxa_mensal_dec) ** (Decimal(dias_totais) / Decimal(30)) - 1 if tipo_juros == "Compostos" else taxa_mensal_dec * (Decimal(dias_totais) / Decimal(30))
        valor_juros = saldo_atual * taxa_periodo
        saldo_final_absoluto = saldo_atual + valor_juros
        
        st.markdown("---")
        st.subheader("Resumo da Dívida Recalculada")
        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo Original Acumulado", f"R$ {float(saldo_atual):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        c2.metric(f"Juros ({tipo_juros})", f"R$ {float(valor_juros):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        c3.metric("Dívida Final", f"R$ {float(saldo_final_absoluto):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
        resumo_dict = {"Original": float(saldo_atual), "Juros": float(valor_juros), "Final": float(saldo_final_absoluto), "Dias": dias_totais}
        df_mem = pd.DataFrame(memoria_calculo)
        
        ex1, ex2 = st.columns(2)
        with ex1: st.download_button("📊 Baixar Planilha (Excel)", data=gerar_excel_bancario(pd.DataFrame([resumo_dict]), df_mem), file_name="Revisao_Bancaria.xlsx", use_container_width=True)
        with ex2: st.download_button("📄 Baixar PDF Pericial", data=gerar_pdf_bancario(resumo_dict, df_mem, indice_escolhido, tipo_juros, taxa_juros), file_name="Laudo_Bancario.pdf", use_container_width=True)

# =================================================================
# --- MÓDULOS TRABALHISTAS ---
# =================================================================
def modulo_trabalhista_rescisao():
    st.header("🧾 Liquidação Expressa (Rescisão e Sentença)")
    st.write("Motor pericial inteligente com integração de verbas, reflexos, multas e honorários.")
    
    historico_sm = obter_historico_salario_minimo()
    
    with st.sidebar:
        st.subheader("1. Parâmetros do Contrato")
        data_admissao = st.date_input("Data de Admissão", value=None, format="DD/MM/YYYY")
        data_demissao = st.date_input("Data de Demissão (Último dia)", value=None, format="DD/MM/YYYY")
        salario_base = st.number_input("Salário Base (R$)", value=0.00, step=100.0)
        
        selecao_sm = st.selectbox("S.M. (Base Insalubridade)", list(historico_sm.keys()))
        salario_minimo = st.number_input("Digite o S.M. (R$)", value=0.00, step=10.0) if selecao_sm == "Outro (Digitar Manualmente)" else historico_sm[selecao_sm]
        
        st.markdown("---")
        st.subheader("2. Adicionais e Jornada")
        adicional_ocupacional = st.selectbox("Adicionais Ocupacionais", ["Nenhum Adicional", "Insalubridade - Mínimo (10%)", "Insalubridade - Médio (20%)", "Insalubridade - Máximo (40%)", "Periculosidade (30%)"])
        he_50 = st.number_input("HE 50% (Média/mês)", value=0.0, step=1.0)
        he_100 = st.number_input("HE 100% (Média/mês)", value=0.0, step=1.0)
        he_noturna = st.number_input("H. Noturnas (Média/mês)", value=0.0, step=1.0)
        
        st.markdown("---")
        st.subheader("3. Deduções e Faltas")
        faltas_injustificadas = st.number_input("Faltas (Dias)", value=0, step=1)
        descontar_vt = st.checkbox("Descontar Vale Transporte", value=False)
        
        st.markdown("---")
        st.subheader("4. Enquadramento Jurídico")
        motivo_rescisao = st.selectbox("Motivo da Rescisão", ["Demissão Sem Justa Causa", "Pedido de Demissão", "Demissão por Justa Causa", "Demissão Indireta"])
        
        st.markdown("---")
        st.subheader("5. Adicionais de Sentença / Acordo")
        multa_467 = st.checkbox("Aplicar Multa do Art. 467 CLT (50%)", value=False)
        valores_pagos = st.number_input("Deduzir Valores Já Pagos (R$)", value=0.00, step=100.0)
        hon_sucumbenciais = st.number_input("Honorários Sucumbenciais (%)", value=0.0, step=1.0)
        hon_contratuais = st.number_input("Honorários Contratuais (%)", value=0.0, step=1.0)

    if not data_admissao or not data_demissao or salario_base <= 0 or (selecao_sm == "Outro (Digitar Manualmente)" and salario_minimo <= 0):
        st.info("👈 Preencha os campos essenciais na barra lateral para iniciar o cálculo.")
        return
    if data_admissao >= data_demissao:
        st.error("⚠️ A Admissão deve ser anterior à Demissão.")
        return

    ano_demissao = data_demissao.year

    valor_adicional_mensal = 0.0
    if "10%" in adicional_ocupacional: valor_adicional_mensal = salario_minimo * 0.10
    elif "20%" in adicional_ocupacional: valor_adicional_mensal = salario_minimo * 0.20
    elif "40%" in adicional_ocupacional: valor_adicional_mensal = salario_minimo * 0.40
    elif "Periculosidade" in adicional_ocupacional: valor_adicional_mensal = salario_base * 0.30

    remuneracao_base = salario_base + valor_adicional_mensal
    valor_hora_normal = remuneracao_base / 220
    total_medias = (he_50 * (valor_hora_normal * 1.5)) + (he_100 * (valor_hora_normal * 2.0)) + (he_noturna * (valor_hora_normal * 0.20))
    reflexo_dsr = total_medias / 6 if total_medias > 0 else 0.0

    remuneracao_rescisoria = remuneracao_base + total_medias + reflexo_dsr
    remuneracao_diaria = remuneracao_rescisoria / 30

    valor_desconto_faltas = faltas_injustificadas * remuneracao_diaria
    valor_desconto_vt = salario_base * 0.06 if descontar_vt else 0.0

    direito_aviso = motivo_rescisao in ["Demissão Sem Justa Causa", "Demissão Indireta"]
    direito_prop = motivo_rescisao != "Demissão por Justa Causa"

    dias_totais = (data_demissao - data_admissao).days
    valor_saldo = remuneracao_diaria * data_demissao.day
    
    dias_aviso = min(30 + ((dias_totais // 365) * 3), 90) if direito_aviso else 0
    data_projetada = data_demissao + timedelta(days=dias_aviso)
    valor_aviso = remuneracao_diaria * dias_aviso if direito_aviso else 0.0

    meses_13 = max(data_projetada.month - (1 if data_projetada.day < 15 else 0), 0) if direito_prop else 0
    valor_13 = (remuneracao_rescisoria / 12) * meses_13

    if direito_prop:
        ult_aniv = data_admissao.replace(year=data_projetada.year)
        if ult_aniv > data_projetada: ult_aniv = ult_aniv.replace(year=data_projetada.year - 1)
        dias_aquisitivo = (data_projetada - ult_aniv).days
        meses_ferias = min((dias_aquisitivo // 30) + (1 if (dias_aquisitivo % 30) >= 15 else 0), 12)
        valor_ferias = (remuneracao_rescisoria / 12) * meses_ferias
        valor_terco = valor_ferias / 3
    else:
        meses_ferias, valor_ferias, valor_terco = 0, 0.0, 0.0

    valor_multa_467 = 0.0
    if multa_467:
        verbas_incontroversas = valor_saldo + valor_aviso + valor_13 + valor_ferias + valor_terco
        valor_multa_467 = verbas_incontroversas * 0.50

    base_inss = valor_saldo + total_medias + reflexo_dsr
    desc_inss_salarial = calcular_imposto_dinamico(base_inss, ano_demissao, "INSS")
    desc_inss_13 = calcular_imposto_dinamico(valor_13, ano_demissao, "INSS") if valor_13 > 0 else 0.0
    desc_inss = desc_inss_salarial + desc_inss_13
    
    desc_irrf = calcular_imposto_dinamico(base_inss - desc_inss_salarial, ano_demissao, "IRRF")

    dados = [{"Verba": f"Saldo Salário ({data_demissao.day}d)", "Valor (R$)": valor_saldo, "Tipo": "Provento", "Natureza": "Salarial"}]
    if total_medias > 0: dados.extend([{"Verba": "Médias de HE/Noturno", "Valor (R$)": total_medias, "Tipo": "Provento", "Natureza": "Salarial"}, {"Verba": "Reflexos no DSR", "Valor (R$)": reflexo_dsr, "Tipo": "Provento", "Natureza": "Salarial"}])
    if direito_aviso: dados.append({"Verba": f"Aviso Prévio ({dias_aviso}d)", "Valor (R$)": valor_aviso, "Tipo": "Provento", "Natureza": "Indenizatória"})
    if meses_13 > 0: dados.append({"Verba": f"13º Prop. ({meses_13}/12)", "Valor (R$)": valor_13, "Tipo": "Provento", "Natureza": "Salarial"})
    if meses_ferias > 0: dados.extend([{"Verba": f"Férias Prop. ({meses_ferias}/12)", "Valor (R$)": valor_ferias, "Tipo": "Provento", "Natureza": "Indenizatória"}, {"Verba": "1/3 Férias", "Valor (R$)": valor_terco, "Tipo": "Provento", "Natureza": "Indenizatória"}])
    if valor_multa_467 > 0: dados.append({"Verba": "Multa Art. 467 CLT (50%)", "Valor (R$)": valor_multa_467, "Tipo": "Provento", "Natureza": "Penalidade"})
    
    if valor_desconto_faltas > 0: dados.append({"Verba": f"Faltas ({faltas_injustificadas}d)", "Valor (R$)": -valor_desconto_faltas, "Tipo": "Desconto", "Natureza": "Dedução"})
    if valor_desconto_vt > 0: dados.append({"Verba": "Vale Transporte (6%)", "Valor (R$)": -valor_desconto_vt, "Tipo": "Desconto", "Natureza": "Dedução"})
    if desc_inss > 0: dados.append({"Verba": f"INSS Progressivo (Tabela {ano_demissao})", "Valor (R$)": -desc_inss, "Tipo": "Desconto", "Natureza": "Tributária"})
    if desc_irrf > 0: dados.append({"Verba": f"IRRF (Tabela {ano_demissao})", "Valor (R$)": -desc_irrf, "Tipo": "Desconto", "Natureza": "Tributária"})

    df = pd.DataFrame(dados)
    tot_bruto = df[df["Tipo"] == "Provento"]["Valor (R$)"].sum()
    tot_deducoes = desc_inss + desc_irrf + valor_desconto_faltas + valor_desconto_vt
    tot_liquido = (tot_bruto - tot_deducoes) - valores_pagos
    
    valor_hon_sucumbenciais = tot_bruto * (hon_sucumbenciais / 100)
    valor_hon_contratuais = tot_liquido * (hon_contratuais / 100) if tot_liquido > 0 else 0.0

    st.subheader(f"Demonstrativo: {motivo_rescisao}")
    st.dataframe(df.style.format({"Valor (R$)": "R$ {:.2f}"}).map(lambda v: 'color: red' if v < 0 else '', subset=['Valor (R$)']), use_container_width=True, hide_index=True)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Proventos Brutos", f"R$ {tot_bruto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    c2.metric("Descontos Legais", f"R$ {tot_deducoes:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    if valores_pagos > 0: c3.metric("Valores Já Pagos", f"R$ -{valores_pagos:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    
    st.markdown(f"### 💰 LÍQUIDO A RECEBER: **R$ {tot_liquido:,.2f}**".replace(",", "X").replace(".", ",").replace("X", "."))
    
    if hon_sucumbenciais > 0 or hon_contratuais > 0:
        st.markdown("#### ⚖️ Honorários Calculados:")
        if hon_sucumbenciais > 0: st.write(f"- **Sucumbenciais ({hon_sucumbenciais}%):** R$ {valor_hon_sucumbenciais:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        if hon_contratuais > 0: st.write(f"- **Contratuais ({hon_contratuais}%):** R$ {valor_hon_contratuais:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    info_contrato = {"admissao": data_admissao.strftime("%d/%m/%Y"), "demissao": data_demissao.strftime("%d/%m/%Y"), "ano_competencia": ano_demissao, "motivo": motivo_rescisao, "salario_base": salario_base, "salario_minimo": salario_minimo, "adicional_nome": adicional_ocupacional, "he_50": he_50, "he_100": he_100, "he_noturna": he_noturna, "faltas": faltas_injustificadas, "vt_status": "Sim" if descontar_vt else "Não", "remun_rescisoria": float(remuneracao_rescisoria), "multa_467": multa_467, "valores_pagos": float(valores_pagos)}
    dic_totais = {"bruto": float(tot_bruto), "deducoes": float(tot_deducoes), "liquido": float(tot_liquido), "fgts_deposito": (remuneracao_rescisoria * (dias_totais / 30)) * 0.08, "fgts_multa": ((remuneracao_rescisoria * (dias_totais / 30)) * 0.08) * 0.40 if direito_aviso else 0, "multa_477": float(remuneracao_base), "hon_sucumbenciais": float(valor_hon_sucumbenciais), "hon_contratuais": float(valor_hon_contratuais)}
    
    st.markdown("<br>", unsafe_allow_html=True)
    ex1, ex2 = st.columns(2)
    with ex1: st.download_button("📊 Baixar Excel", data=gerar_excel_trabalhista(df, info_contrato, dic_totais), file_name="Rescisao.xlsx", use_container_width=True)
    with ex2: st.download_button("📄 Baixar Laudo PDF", data=gerar_pdf_trabalhista(df, info_contrato, dic_totais), file_name="Laudo_Rescisao.pdf", use_container_width=True)

def modulo_trabalhista_adc58():
    st.header("📈 Atualização Monetária (ADC 58 - STF)")
    st.write("Fatia automaticamente o período pré-judicial (IPCA-E) e o judicial (SELIC) conforme a jurisprudência vinculante.")
    
    with st.sidebar:
        st.subheader("Parâmetros da Condenação")
        valor_original = st.number_input("Valor Histórico (R$)", value=0.00, step=100.0)
        
        st.markdown("---")
        data_vencimento = st.date_input("Data de Vencimento da Verba", value=None, format="DD/MM/YYYY")
        data_ajuizamento = st.date_input("Data do Ajuizamento da Ação", value=None, format="DD/MM/YYYY")
        data_calculo = st.date_input("Data da Atualização (Hoje)", value=date.today(), format="DD/MM/YYYY")
        
        st.markdown("---")
        incluir_juros_pre = st.checkbox("Incluir Juros Pré-Judiciais (1% a.m.)", value=False)

    if not data_vencimento or not data_ajuizamento or valor_original <= 0:
        st.info("👈 Preencha o valor original e as datas essenciais no menu lateral para iniciar a atualização.")
        return
    if data_vencimento > data_ajuizamento:
        st.error("⚠️ Erro: A Data de Vencimento deve ser anterior ao Ajuizamento da Ação.")
        return
    if data_ajuizamento > data_calculo:
        st.error("⚠️ Erro: A Data do Cálculo não pode ser anterior ao Ajuizamento.")
        return

    with st.spinner("Puxando matrizes oficiais do Banco Central (IPCA-E e SELIC)..."):
        df_ipcae_completo = buscar_indice_bcb(10844)
        df_selic_completa = buscar_indice_bcb(4390)

    valor_atualizado_ipcae = valor_original
    percentual_acumulado_ipcae = 1.0
    
    str_vencimento = data_vencimento.strftime('%Y-%m')
    str_ajuizamento = data_ajuizamento.strftime('%Y-%m')
    
    if not df_ipcae_completo.empty:
        mask_ipcae = (df_ipcae_completo['Mês/Ano'] >= str_vencimento) & (df_ipcae_completo['Mês/Ano'] < str_ajuizamento)
        df_ipcae_fase = df_ipcae_completo[mask_ipcae]
        for _, row in df_ipcae_fase.iterrows():
            percentual_acumulado_ipcae *= (1 + (row['Índice (%)'] / 100))
            
    valor_atualizado_ipcae = valor_original * percentual_acumulado_ipcae
    
    juros_pre_judiciais = 0.0
    if incluir_juros_pre:
        dias_pre = (data_ajuizamento - data_vencimento).days
        juros_pre_judiciais = valor_atualizado_ipcae * ((dias_pre / 30) * 0.01)
        
    subtotal_fase_pre = valor_atualizado_ipcae + juros_pre_judiciais

    soma_selic_acumulada = 0.0
    str_calculo = data_calculo.strftime('%Y-%m')
    
    if not df_selic_completa.empty:
        mask_selic = (df_selic_completa['Mês/Ano'] >= str_ajuizamento) & (df_selic_completa['Mês/Ano'] <= str_calculo)
        df_selic_fase = df_selic_completa[mask_selic]
        soma_selic_acumulada = df_selic_fase['Índice (%)'].sum() / 100
        
    valor_juros_correcao_selic = subtotal_fase_pre * soma_selic_acumulada
    valor_final_absoluto = subtotal_fase_pre + valor_juros_correcao_selic

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #004080; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;">
            <h4 style="color: #004080; margin-top: 0;">Fase Pré-Judicial (IPCA-E)</h4>
            <p style="margin-bottom: 5px;">De <b>{data_vencimento.strftime('%m/%Y')}</b> até <b>{data_ajuizamento.strftime('%m/%Y')}</b></p>
            <p style="margin-bottom: 5px;">Valor Original: R$ {valor_original:,.2f}</p>
            <p style="margin-bottom: 5px;">IPCA-E Acumulado: {(percentual_acumulado_ipcae - 1)*100:.4f}%</p>
            <p style="margin-bottom: 5px;">Juros Adicionais: R$ {juros_pre_judiciais:,.2f}</p>
            <hr style="margin: 10px 0;">
            <h5 style="color: #333; margin: 0;">Subtotal Ajuizamento: R$ {subtotal_fase_pre:,.2f}</h5>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
        <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;">
            <h4 style="color: #28a745; margin-top: 0;">Fase Judicial (SELIC)</h4>
            <p style="margin-bottom: 5px;">De <b>{data_ajuizamento.strftime('%m/%Y')}</b> até <b>{data_calculo.strftime('%m/%Y')}</b></p>
            <p style="margin-bottom: 5px;">Base Judicial: R$ {subtotal_fase_pre:,.2f}</p>
            <p style="margin-bottom: 5px;">SELIC Acumulada (Simples): {soma_selic_acumulada*100:.4f}%</p>
            <p style="margin-bottom: 5px;">Rendimento SELIC: R$ {valor_juros_correcao_selic:,.2f}</p>
            <hr style="margin: 10px 0;">
            <h5 style="color: #333; margin: 0;">Valor Atualizado: R$ {valor_final_absoluto:,.2f}</h5>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"### 💰 Dívida Final Atualizada: **R$ {valor_final_absoluto:,.2f}**".replace(",", "X").replace(".", ",").replace("X", "."))


# =================================================================
# --- ROTEAMENTO DE PÁGINAS (SINGLE PAGE APPLICATION) ---
# =================================================================
menu = st.session_state.menu_principal
ferramenta = st.session_state.ferramenta_ativa

with st.sidebar:
    if menu != "Início":
        st.button("⬅️ VOLTAR AO INÍCIO", on_click=navegar_para, args=("Início", "Painel"), use_container_width=True)
        st.markdown("---")

# Lógica da Tela Principal
if menu == "Início":
    st.title("Bem-vindo ao Tolaris Calc")
    st.write("Sua plataforma definitiva de inteligência pericial e cálculos jurídicos automatizados. Selecione a área de atuação abaixo ou no menu superior.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<div style='background-color: white; padding: 25px; border-top: 5px solid #004080; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;'> <h2 style='color: #004080; margin-top:0;'>⚖️ Área Cível</h2> <p style='color: #555; font-size: 16px;'>Auditoria de contratos, expurgos inflacionários, revisões bancárias e atualização de débitos judiciais.</p> </div>", unsafe_allow_html=True)
        st.button("ACESSAR MÓDULO CÍVEL", on_click=navegar_para, args=("Cível", "Painel"), use_container_width=True)
    with col2:
        st.markdown("<div style='background-color: white; padding: 25px; border-top: 5px solid #28a745; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;'> <h2 style='color: #28a745; margin-top:0;'>👷 Área Trabalhista</h2> <p style='color: #555; font-size: 16px;'>Liquidação de sentenças, rescisões expressas, integração de reflexos e atualização monetária ADC 58.</p> </div>", unsafe_allow_html=True)
        st.button("ACESSAR MÓDULO TRABALHISTA", on_click=navegar_para, args=("Trabalhista", "Painel"), use_container_width=True)

elif menu == "Cível":
    if ferramenta == "Painel":
        st.title("⚖️ Painel da Área Cível")
        st.write("Escolha uma das calculadoras específicas clicando nos cartões abaixo para iniciar.")
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("""
        <div class="tool-card">
            <h4 style="color: #004080; margin-bottom: 5px;">💳 Revisão de Cheque Especial e Contratos</h4>
            <p style="color: #666; font-size: 14px;">Auditoria diária de extratos bancários. Isola a correção monetária, expurga juros abusivos e reconstrói o saldo devedor real utilizando as taxas do Banco Central.</p>
        </div>
        """, unsafe_allow_html=True)
        st.button("Acessar Calculadora", on_click=navegar_para, args=("Cível", "Revisão de Cheque Especial"), key="btn_civ_1")

    elif ferramenta == "Revisão de Cheque Especial":
        modulo_cheque_especial()
    else:
        st.info("🚧 Módulo em desenvolvimento.")

elif menu == "Trabalhista":
    if ferramenta == "Painel":
        st.title("👷 Painel da Área Trabalhista")
        st.write("Escolha uma das calculadoras específicas clicando nos cartões abaixo para iniciar.")
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("""
        <div class="tool-card tool-card-trabalhista">
            <h4 style="color: #28a745; margin-bottom: 5px;">🧾 Liquidação Expressa (Rescisão e Sentença)</h4>
            <p style="color: #666; font-size: 14px;">Cálculo automatizado de verbas rescisórias, integrando adicionais ocupacionais, médias de horas extras, DSR e aplicação progressiva de INSS e IRRF vigentes.</p>
        </div>
        """, unsafe_allow_html=True)
        st.button("Acessar Calculadora", on_click=navegar_para, args=("Trabalhista", "Liquidação Expressa (Rescisão)"), key="btn_trab_1")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        st.markdown("""
        <div class="tool-card tool-card-trabalhista">
            <h4 style="color: #28a745; margin-bottom: 5px;">📈 Atualização ADC 58 (IPCA-E + SELIC)</h4>
            <p style="color: #666; font-size: 14px;">Atualização monetária e juros de acordos ou condenações. Segmenta automaticamente as fases pré-judicial e judicial, consumindo os índices oficiais em tempo real.</p>
        </div>
        """, unsafe_allow_html=True)
        st.button("Acessar Calculadora", on_click=navegar_para, args=("Trabalhista", "Atualização ADC 58"), key="btn_trab_2")

    elif ferramenta == "Liquidação Expressa (Rescisão)":
        modulo_trabalhista_rescisao()
    elif ferramenta == "Atualização ADC 58":
        modulo_trabalhista_adc58()