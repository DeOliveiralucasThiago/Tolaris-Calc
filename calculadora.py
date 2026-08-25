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

# =================================================================
# --- 1. CONFIGURAÇÃO DA PÁGINA E CSS CORPORATIVO ---
# =================================================================
st.set_page_config(
    page_title="Tolaris Calc | Hub Pericial", 
    layout="wide", 
    initial_sidebar_state="collapsed" # Oculta a barra lateral nativa
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
    }
    .stApp {
        background-color: #F8F9FA;
    }
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}

    /* Botões Primários Corporativos */
    button[kind="primary"] {
        background-color: #002B5B !important;
        border: 1px solid #002B5B !important;
        color: #FFFFFF !important;
        border-radius: 4px !important;
        font-weight: 500 !important;
        transition: all 0.3s ease !important;
    }
    button[kind="primary"]:hover {
        background-color: #004080 !important;
        border-color: #004080 !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
    }

    /* Navbar Customizada */
    .navbar-container {
        padding-bottom: 15px;
        border-bottom: 2px solid #E5E7EB;
        margin-bottom: 20px;
        margin-top: -40px;
    }
    button[kind="secondary"] {
        background-color: transparent !important;
        border: 1px solid transparent !important;
        color: #6B7280 !important;
        font-weight: 500 !important;
    }
    button[kind="secondary"]:hover {
        color: #002B5B !important;
        border-bottom: 2px solid #002B5B !important;
        border-radius: 0px !important;
    }
    
    /* Headers Customizados */
    h1, h2, h3, h4, h5 {
        color: #002B5B !important;
    }
    </style>
""", unsafe_allow_html=True)

# Cabeçalho da Marca
st.markdown("<h2 style='font-weight: 700; margin-bottom: 0px; margin-top: 10px; letter-spacing: 1px;'>TOLARIS</h2>", unsafe_allow_html=True)

# --- GERENCIADOR DE ESTADO DE NAVEGAÇÃO ---
if 'menu_principal' not in st.session_state:
    st.session_state.menu_principal = "Inicio"
if 'ferramenta_ativa' not in st.session_state:
    st.session_state.ferramenta_ativa = "Painel"

def navegar_para(menu, ferramenta="Painel"):
    st.session_state.menu_principal = menu
    st.session_state.ferramenta_ativa = ferramenta

# =================================================================
# --- MENU DE NAVEGAÇÃO SUPERIOR ---
# =================================================================
st.markdown("<div class='navbar-container'>", unsafe_allow_html=True)
col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1, 1, 1, 3])
with col_nav1:
    st.button("INÍCIO", on_click=navegar_para, args=("Inicio", "Painel"), use_container_width=True, type="primary" if st.session_state.menu_principal == "Inicio" else "secondary")
with col_nav2:
    st.button("ÁREA CÍVEL", on_click=navegar_para, args=("Cível", "Painel"), use_container_width=True, type="primary" if st.session_state.menu_principal == "Cível" else "secondary")
with col_nav3:
    st.button("ÁREA TRABALHISTA", on_click=navegar_para, args=("Trabalhista", "Painel"), use_container_width=True, type="primary" if st.session_state.menu_principal == "Trabalhista" else "secondary")
st.markdown("</div>", unsafe_allow_html=True)

# Função Botão Voltar Universal
def botao_voltar(area):
    if st.button("⬅️ Voltar ao Painel", key="voltar_painel"):
        navegar_para(area, "Painel")
    st.markdown("<br>", unsafe_allow_html=True)

# =================================================================
# --- FUNÇÕES DE BANCO DE DADOS E INTEGRAÇÕES ---
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
    if not db_tributos or ano_str not in db_tributos:
        ano_str = "2024" if db_tributos and "2024" in db_tributos else None

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

    dados_imposto = db_tributos[ano_str][tipo_imposto]
    tipo_calculo = dados_imposto.get("tipo", "progressivo")
    faixas = dados_imposto["faixas"]
    
    if tipo_imposto == "INSS":
        teto_inss = dados_imposto.get("teto_inss", 908.85)
        if tipo_calculo == "aliquota_unica":
            for faixa in faixas:
                if valor_base <= faixa["limite"]: return valor_base * faixa["aliquota"]
            return teto_inss
        else:
            for faixa in faixas:
                if valor_base <= faixa["limite"]: return (valor_base * faixa["aliquota"]) - faixa["deducao"]
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
        df_resumo.to_excel(writer, sheet_name='Resumo', index=False)
        df_detalhado.to_excel(writer, sheet_name='Memoria', index=False)
    return output.getvalue()

def gerar_pdf_bancario(resumo_dados, df_detalhado, indice_nome, juros_tipo, taxa):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.set_font("Arial", style="B", size=16)
    pdf.set_text_color(0, 43, 91)
    pdf.cell(0, 10, "TOLARIS CALC - AUDITORIA DE CONTRATOS", ln=True, align="C")
    pdf.set_text_color(0, 0, 0) 
    pdf.set_font("Arial", style="I", size=10)
    pdf.cell(0, 10, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", style="B", size=12)
    pdf.cell(0, 8, "1. PARAMETROS DO CONTRATO E ATUALIZACAO", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 6, f"Indice: {indice_nome}", ln=True)
    pdf.cell(0, 6, f"Metodo: Juros {juros_tipo} | Taxa: {taxa:.3f}% ao mes", ln=True)
    pdf.cell(0, 6, f"Periodo Analisado: {resumo_dados['Dias']} dias", ln=True)
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
    pdf.cell(0, 8, "3. EXTRATO DA MEMORIA DE CALCULO DIARIA", ln=True)
    pdf.ln(2)
    pdf.set_font("Arial", style="B", size=9)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(25, 6, "Data", border=1, align="C", fill=True)
    pdf.cell(35, 6, "S. Anterior", border=1, align="R", fill=True)
    pdf.cell(20, 6, "Corr. (R$)", border=1, align="R", fill=True)
    pdf.cell(28, 6, "Debitos (-)", border=1, align="R", fill=True)
    pdf.cell(28, 6, "Creditos (+)", border=1, align="R", fill=True)
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

def gerar_excel_civel(info_calculo):
    output = io.BytesIO()
    df_info = pd.DataFrame([{"Parametro": k, "Valor": v} for k, v in info_calculo.items()])
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_info.to_excel(writer, sheet_name='Memoria', index=False)
    return output.getvalue()

def gerar_pdf_civel(info):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", style="B", size=16)
    pdf.set_text_color(0, 43, 91)
    pdf.cell(0, 10, "TOLARIS CALC - MEMORIA DE ATUALIZACAO CIVEL", ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", style="I", size=10)
    pdf.cell(0, 6, f"Emitido em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align="C")
    pdf.ln(8)
    pdf.set_font("Arial", style="B", size=12)
    pdf.set_text_color(0, 43, 91)
    pdf.cell(0, 8, "1. PARAMETROS DO CALCULO", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=10)
    pdf.cell(95, 6, f"Valor Historico Base: {info['Valor Original']}", border=0)
    pdf.cell(95, 6, f"Indice de Correcao: {info['Indice']}", border=0, ln=True)
    pdf.cell(95, 6, f"Termo Inicial Correcao: {info['Data Vencimento']}", border=0)
    pdf.cell(95, 6, f"Termo Inicial Juros: {info['Data Juros']}", border=0, ln=True)
    pdf.cell(0, 6, f"Data do Fechamento do Calculo: {info['Data Calculo']}", border=0, ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", style="B", size=12)
    pdf.set_text_color(0, 43, 91)
    pdf.cell(0, 8, "2. DEMONSTRATIVO DA DIVIDA PRINCIPAL", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=11)
    pdf.cell(130, 6, "Principal Corrigido Monetariamente:", border=0)
    pdf.cell(50, 6, info['Principal Corrigido'], border=0, align="R", ln=True)
    pdf.cell(130, 6, "Juros de Mora Computados no Periodo:", border=0)
    pdf.cell(50, 6, info['Juros de Mora'], border=0, align="R", ln=True)
    pdf.cell(130, 6, f"Multa Contratual ({info['Perc_Multa_Contrato']}%):", border=0)
    pdf.cell(50, 6, info['Multa Contratual'], border=0, align="R", ln=True)
    pdf.set_font("Arial", style="B", size=11)
    pdf.set_fill_color(240, 245, 250)
    pdf.cell(130, 7, " BASE EXECUTADA (Principal + Juros + Multa):", border=1, fill=True)
    pdf.cell(50, 7, f"{info['Base Processual']} ", border=1, align="R", fill=True, ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", style="B", size=12)
    pdf.set_text_color(0, 43, 91)
    pdf.cell(0, 8, "3. DESPESAS E CUSTAS PROCESSUAIS", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=11)
    pdf.cell(130, 6, f"Custas Pagas em {info['Data Custas']} (Apenas Correcao):", border=0)
    pdf.cell(50, 6, info['Custas Corrigidas'], border=0, align="R", ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", style="B", size=12)
    pdf.set_text_color(0, 43, 91)
    pdf.cell(0, 8, "4. MULTAS E HONORARIOS (FASE DE CUMPRIMENTO)", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", size=11)
    pdf.cell(130, 6, "Multa por Inadimplemento Art. 523, CPC (10%):", border=0)
    pdf.cell(50, 6, info['Multa Art. 523'], border=0, align="R", ln=True)
    pdf.cell(130, 6, "Honorarios de Execucao Art. 523, CPC (10%):", border=0)
    pdf.cell(50, 6, info['Honorarios Art. 523'], border=0, align="R", ln=True)
    pdf.cell(130, 6, f"Honorarios Advocaticios Comuns/Contratuais ({info['Perc_Hon']}%):", border=0)
    pdf.cell(50, 6, info['Honorarios Comuns'], border=0, align="R", ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", style="B", size=13)
    pdf.set_fill_color(230, 240, 230)
    pdf.set_text_color(0, 100, 0)
    pdf.cell(130, 9, " TOTAL GERAL EXEQUENDO DEVIDO:", border=1, fill=True)
    pdf.cell(50, 9, f"{info['Total Devido']} ", border=1, align="R", fill=True, ln=True)
    return bytes(pdf.output())

def gerar_excel_trabalhista(df_rescisao, info_contrato, totais):
    output = io.BytesIO()
    df_info = pd.DataFrame([{"Parametro": k, "Valor": v} for k, v in info_contrato.items()])
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_info.to_excel(writer, sheet_name='Parametros', index=False)
        df_rescisao.to_excel(writer, sheet_name='Rubricas', index=False)
    return output.getvalue()

def gerar_pdf_trabalhista(df_rescisao, info_contrato, totais):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.set_font("Arial", style="B", size=16)
    pdf.set_text_color(0, 43, 91) 
    pdf.cell(0, 10, "TOLARIS CALC - LIQUIDACAO TRABALHISTA", ln=True, align="C")
    pdf.set_text_color(0, 0, 0) 
    pdf.set_font("Arial", style="I", size=10)
    pdf.cell(0, 6, f"Emitido em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align="C")
    pdf.ln(8)
    pdf.set_font("Arial", style="B", size=12)
    pdf.set_text_color(0, 43, 91)
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
    pdf.set_text_color(0, 43, 91)
    pdf.cell(0, 8, "2. DEMONSTRATIVO DE RUBRICAS", ln=True)
    pdf.set_font("Arial", style="B", size=10)
    pdf.set_fill_color(0, 43, 91)
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
    pdf.set_text_color(75, 85, 99)
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
    pdf.set_text_color(0, 43, 91)
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
# --- TELAS ESPECÍFICAS DAS FERRAMENTAS CÍVEIS --------------------
# =================================================================
def modulo_cheque_especial():
    botao_voltar("Cível")
    st.header("Revisão de Cheque Especial e Contratos Bancários")
    st.write("Auditoria diária de extratos bancários para descaracterizar juros abusivos e aplicar os índices do BCB.")
    
    df_indices = pd.DataFrame(columns=["Mês/Ano", "Índice (%)"])
    dic_lancamentos = {}
    if 'reset_contador' not in st.session_state:
        st.session_state.reset_contador = 0
    def limpar_tabela():
        st.session_state.reset_contador += 1
    
    CODIGOS_BCB = {"IGP-M": 189, "IPCA": 433, "INPC": 188, "INCC": 192}

    with st.container(border=True):
        st.markdown("<h5>1. Parâmetros do Contrato Base</h5>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        data_inicial = c1.date_input("Data Inicial", value=None, format="DD/MM/YYYY")
        data_final = c2.date_input("Data Final", value=None, format="DD/MM/YYYY")
        saldo_inicial = c3.number_input("Saldo Inicial Negativo (R$)", value=0.00, step=100.0)
        indice_escolhido = c4.selectbox("Índice de Atualização", ["Sem Atualização (Apenas Juros)"] + list(CODIGOS_BCB.keys()))

        c5, c6, c7, c8 = st.columns(4)
        tipo_juros = c5.radio("Método de Juros", ["Compostos", "Simples"])
        taxa_juros = c6.number_input("Taxa de Juros a.m. (%)", value=8.000, format="%.3f")

        if indice_escolhido != "Sem Atualização (Apenas Juros)":
            codigo_atual = CODIGOS_BCB[indice_escolhido]
            df_historico_completo = buscar_indice_bcb(codigo_atual)
            if data_inicial:
                ano_inicio = str(data_inicial.year)
                df_filtrado = df_historico_completo[df_historico_completo['Mês/Ano'] >= f"{ano_inicio}-01"].copy() if not df_historico_completo.empty else pd.DataFrame(columns=["Mês/Ano", "Índice (%)"])
            else:
                df_filtrado = pd.DataFrame(columns=["Mês/Ano", "Índice (%)"])
            df_indices = st.data_editor(df_filtrado, num_rows="dynamic", hide_index=True)

    if not data_inicial or not data_final:
        st.info("Preencha as datas para liberar a tabela de lançamentos.")
        return
    if data_inicial > data_final:
        st.warning("Atenção: A Data Inicial não pode ser posterior à Data Final.")
        return

    st.markdown("<h5>2. Tabela Diária de Lançamentos</h5>", unsafe_allow_html=True)
    dias_totais = (data_final - data_inicial).days
    datas_iniciais = [(data_inicial + timedelta(days=i)) for i in range(dias_totais + 1)]
    df_lancamentos_iniciais = pd.DataFrame({"Data": datas_iniciais, "Débitos (-)": [0.00 for _ in range(len(datas_iniciais))], "Créditos (+)": [0.00 for _ in range(len(datas_iniciais))]})

    df_lancamentos = st.data_editor(
        df_lancamentos_iniciais, key=f"tabela_lancamentos_{st.session_state.reset_contador}", num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"), "Débitos (-)": st.column_config.NumberColumn("Débitos (-)", format="R$ %.2f"), "Créditos (+)": st.column_config.NumberColumn("Créditos (+)", format="R$ %.2f")}
    )

    col_btn1, col_btn2 = st.columns([3, 1])
    with col_btn1:
        btn_processar = st.button("PROCESSAR REVISÃO BANCÁRIA", type="primary", use_container_width=True)
    with col_btn2:
        st.button("Limpar Tabela", on_click=limpar_tabela, use_container_width=True)

    if btn_processar:
        dic_indices = {row["Mês/Ano"]: Decimal(str(row["Índice (%)"] / 100)) for _, row in df_indices.iterrows()} if not df_indices.empty else {}
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
        with ex1: st.download_button("Baixar Planilha (Excel)", data=gerar_excel_bancario(pd.DataFrame([resumo_dict]), df_mem), file_name="Revisao_Bancaria.xlsx", use_container_width=True)
        with ex2: st.download_button("Baixar PDF Pericial", data=gerar_pdf_bancario(resumo_dict, df_mem, indice_escolhido, tipo_juros, taxa_juros), file_name="Laudo_Bancario.pdf", use_container_width=True)


def modulo_civel_atualizacao():
    botao_voltar("Cível")
    st.header("Atualização Monetária (TJ Padrão)")
    st.write("Cálculo processual para cumprimento de sentença cível, com juros, multas contratuais e honorários do Art. 523 CPC.")
    
    CODIGOS_BCB = {"INPC": 188, "IPCA-E": 10844, "IGP-M": 189, "SELIC": 4390}

    with st.container(border=True):
        st.markdown("<h5>1. Valores e Datas do Principal</h5>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        valor_original = c1.number_input("Valor Histórico (R$)", value=0.00, step=100.0)
        data_vencimento = c2.date_input("Data do Vencimento (Correção)", value=None, format="DD/MM/YYYY")
        data_juros = c3.date_input("Data da Citação (Juros)", value=None, format="DD/MM/YYYY")
        data_calculo = c4.date_input("Data do Cálculo (Hoje)", value=date.today(), format="DD/MM/YYYY")
        
    with st.container(border=True):
        st.markdown("<h5>2. Fatores de Atualização e Custas</h5>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        indice_escolhido = c1.selectbox("Índice de Correção", list(CODIGOS_BCB.keys()))
        
        aplicar_juros = False
        perc_juros = 0.0
        if indice_escolhido == "SELIC":
            c2.info("A SELIC embute juros de mora.")
        else:
            aplicar_juros = c2.checkbox("Aplicar Juros de Mora", value=True)
            perc_juros = c3.number_input("Juros ao Mês (%)", value=1.0, step=0.1) if aplicar_juros else 0.0
            
        custas_pagas = c4.number_input("Custas Pagas a Reembolsar (R$)", value=0.00, step=50.0)
        data_custas = None
        if custas_pagas > 0:
            data_custas = st.date_input("Data do Pagamento das Custas", value=None, format="DD/MM/YYYY")

    with st.container(border=True):
        st.markdown("<h5>3. Multas e Honorários</h5>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        multa_contratual = c1.number_input("Multa Contratual / Penal (%)", value=0.0, step=1.0)
        multa_523 = c2.checkbox("Multa do Art. 523 CPC (10%)", value=False)
        hon_523 = c3.checkbox("Honorários do Art. 523 CPC (10%)", value=False)
        hon_comum = c4.number_input("Honorários Advocatícios Comuns (%)", value=0.0, step=1.0)

    if not data_vencimento or not data_juros or valor_original <= 0:
        st.info("Preencha o valor histórico e as datas para iniciar.")
        return
    if data_vencimento > data_calculo or data_juros > data_calculo:
        st.warning("As datas devem ser anteriores à data do cálculo.")
        return
    if custas_pagas > 0 and not data_custas:
        st.warning("Informe a data de pagamento das custas para correção.")
        return

    with st.spinner(f"Processando matriz {indice_escolhido}..."):
        codigo_atual = CODIGOS_BCB[indice_escolhido]
        df_indice_completo = buscar_indice_bcb(codigo_atual)

    valor_corrigido = valor_original
    fator_acumulado = 1.0
    str_venc = data_vencimento.strftime('%Y-%m')
    str_calc = data_calculo.strftime('%Y-%m')
    
    valor_custas_corrigidas = custas_pagas
    fator_custas = 1.0
    str_custas = data_custas.strftime('%Y-%m') if custas_pagas > 0 and data_custas else None
    
    if not df_indice_completo.empty:
        mask = (df_indice_completo['Mês/Ano'] >= str_venc) & (df_indice_completo['Mês/Ano'] < str_calc)
        df_fase = df_indice_completo[mask]
        if indice_escolhido == "SELIC":
            soma_selic = df_fase['Índice (%)'].sum() / 100
            valor_corrigido = valor_original + (valor_original * soma_selic)
        else:
            for _, row in df_fase.iterrows(): fator_acumulado *= (1 + (row['Índice (%)'] / 100))
            valor_corrigido = valor_original * fator_acumulado
            
        if str_custas:
            mask_custas = (df_indice_completo['Mês/Ano'] >= str_custas) & (df_indice_completo['Mês/Ano'] < str_calc)
            df_fase_custas = df_indice_completo[mask_custas]
            if indice_escolhido == "SELIC":
                soma_selic_custas = df_fase_custas['Índice (%)'].sum() / 100
                valor_custas_corrigidas = custas_pagas + (custas_pagas * soma_selic_custas)
            else:
                for _, row in df_fase_custas.iterrows(): fator_custas *= (1 + (row['Índice (%)'] / 100))
                valor_custas_corrigidas = custas_pagas * fator_custas

    valor_juros_mora = 0.0
    if indice_escolhido != "SELIC" and aplicar_juros:
        dias_juros = (data_calculo - data_juros).days
        if dias_juros > 0:
            meses_juros = dias_juros / 30
            valor_juros_mora = valor_corrigido * (meses_juros * (perc_juros / 100))
            
    subtotal_atualizado = valor_corrigido + valor_juros_mora
    valor_multa_contratual = subtotal_atualizado * (multa_contratual / 100) if multa_contratual > 0 else 0.0
    base_processual = subtotal_atualizado + valor_multa_contratual

    valor_multa_523 = base_processual * 0.10 if multa_523 else 0.0
    valor_hon_523 = base_processual * 0.10 if hon_523 else 0.0
    valor_hon_comum = base_processual * (hon_comum / 100) if hon_comum > 0 else 0.0
    
    total_acrescimos_processuais = valor_multa_523 + valor_hon_523 + valor_hon_comum
    total_devido = base_processual + total_acrescimos_processuais + valor_custas_corrigidas

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.markdown(f"""
        <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #002B5B; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;">
            <h4 style="color: #002B5B; margin-top: 0;">Dívida Principal Atualizada</h4>
            <p style="margin-bottom: 5px;">Valor Histórico: R$ {valor_original:,.2f}</p>
            <p style="margin-bottom: 5px;">Principal Corrigido ({indice_escolhido}): R$ {valor_corrigido:,.2f}</p>
            <p style="margin-bottom: 5px;">Juros de Mora: R$ {valor_juros_mora:,.2f}</p>
            <p style="margin-bottom: 5px;">Multa Contratual ({multa_contratual}%): R$ {valor_multa_contratual:,.2f}</p>
            <hr style="margin: 10px 0;">
            <h5 style="color: #333; margin: 0;">Base Processual Executada: R$ {base_processual:,.2f}</h5>
        </div>
        """, unsafe_allow_html=True)
        
    with col_t2:
        st.markdown(f"""
        <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #4B5563; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;">
            <h4 style="color: #4B5563; margin-top: 0;">Custas e Honorários</h4>
            <p style="margin-bottom: 5px;">Custas Pagas Atualizadas: R$ {valor_custas_corrigidas:,.2f}</p>
            <p style="margin-bottom: 5px;">Multa Art. 523 (10%): R$ {valor_multa_523:,.2f}</p>
            <p style="margin-bottom: 5px;">Honorários Art. 523 (10%): R$ {valor_hon_523:,.2f}</p>
            <p style="margin-bottom: 5px;">Honorários Comuns ({hon_comum}%): R$ {valor_hon_comum:,.2f}</p>
            <hr style="margin: 10px 0;">
            <h5 style="color: #333; margin: 0;">Total Despesas/Acréscimos: R$ {(total_acrescimos_processuais + valor_custas_corrigidas):,.2f}</h5>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"### TOTAL GERAL EXEQUENDO: R$ {total_devido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.subheader("Exportar Relatório de Atualização Monetária")
    dic_dados_civel = {
        "Valor Original": f"R$ {valor_original:,.2f}",
        "Data Vencimento": data_vencimento.strftime("%d/%m/%Y"),
        "Data Juros": data_juros.strftime("%d/%m/%Y"),
        "Data Calculo": data_calculo.strftime("%d/%m/%Y"),
        "Indice": indice_escolhido,
        "Principal Corrigido": f"R$ {valor_corrigido:,.2f}",
        "Juros de Mora": f"R$ {valor_juros_mora:,.2f}",
        "Subtotal": f"R$ {subtotal_atualizado:,.2f}",
        "Perc_Multa_Contrato": str(multa_contratual),
        "Multa Contratual": f"R$ {valor_multa_contratual:,.2f}",
        "Base Processual": f"R$ {base_processual:,.2f}",
        "Data Custas": data_custas.strftime("%d/%m/%Y") if data_custas else "Não informada",
        "Custas Corrigidas": f"R$ {valor_custas_corrigidas:,.2f}",
        "Multa Art. 523": f"R$ {valor_multa_523:,.2f}",
        "Honorarios Art. 523": f"R$ {valor_hon_523:,.2f}",
        "Perc_Hon": str(hon_comum),
        "Honorarios Comuns": f"R$ {valor_hon_comum:,.2f}",
        "Total Devido": f"R$ {total_devido:,.2f}"
    }
    
    cx1, cx2 = st.columns(2)
    with cx1: st.download_button("Baixar Memória de Cálculo (Excel)", data=gerar_excel_civel(dic_dados_civel), file_name="Atualizacao_Civel.xlsx", use_container_width=True)
    with cx2: st.download_button("Baixar Relatório de Atualização (PDF)", data=gerar_pdf_civel(dic_dados_civel), file_name="Laudo_Atualizacao_Civel.pdf", use_container_width=True)

# =================================================================
# --- TELAS ESPECÍFICAS DAS FERRAMENTAS TRABALHISTAS --------------
# =================================================================
def modulo_trabalhista_rescisao():
    botao_voltar("Trabalhista")
    st.header("Liquidação Expressa (Rescisão e Sentença)")
    st.write("Motor pericial inteligente com integração de verbas, reflexos, multas e deduções legais.")
    
    historico_sm = obter_historico_salario_minimo()
    
    with st.container(border=True):
        st.markdown("<h5>1. Parâmetros do Contrato Base</h5>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        data_admissao = c1.date_input("Data de Admissão", value=None, format="DD/MM/YYYY")
        data_demissao = c2.date_input("Data de Demissão", value=None, format="DD/MM/YYYY")
        salario_base = c3.number_input("Salário Base (R$)", value=0.00, step=100.0)
        motivo_rescisao = c4.selectbox("Motivo da Rescisão", ["Demissão Sem Justa Causa", "Pedido de Demissão", "Demissão por Justa Causa", "Demissão Indireta"])

    with st.container(border=True):
        st.markdown("<h5>2. Adicionais e Jornada (Médias)</h5>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        adicional_ocupacional = c1.selectbox("Adicionais Ocupacionais", ["Nenhum Adicional", "Insalubridade - Mínimo (10%)", "Insalubridade - Médio (20%)", "Insalubridade - Máximo (40%)", "Periculosidade (30%)"])
        he_50 = c2.number_input("HE 50% (Média/mês)", value=0.0, step=1.0)
        he_100 = c3.number_input("HE 100% (Média/mês)", value=0.0, step=1.0)
        he_noturna = c4.number_input("H. Noturnas (Média)", value=0.0, step=1.0)
        
        salario_minimo = 0.0
        if "Insalubridade" in adicional_ocupacional:
            cc1, cc2 = st.columns([1, 3])
            selecao_sm = cc1.selectbox("Ano do S.M.", list(historico_sm.keys()))
            if selecao_sm == "Outro (Digitar Manualmente)":
                salario_minimo = cc2.number_input("Digite o S.M. (R$)", value=0.00, step=10.0)
            else:
                salario_minimo = historico_sm[selecao_sm]
                cc2.info(f"Salário Mínimo base: R$ {salario_minimo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
    with st.container(border=True):
        st.markdown("<h5>3. Deduções, Multas e Honorários</h5>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        faltas_injustificadas = c1.number_input("Faltas (Dias)", value=0, step=1)
        descontar_vt = c2.checkbox("Descontar Vale Transporte", value=False)
        multa_467 = c3.checkbox("Multa Art. 467 CLT (50%)", value=False)
        valores_pagos = c4.number_input("Deduzir Valores Já Pagos (R$)", value=0.00, step=100.0)

        c5, c6, c7, c8 = st.columns(4)
        hon_sucumbenciais = c5.number_input("Honorários Sucumbenciais (%)", value=0.0, step=1.0)
        hon_contratuais = c6.number_input("Honorários Contratuais (%)", value=0.0, step=1.0)

    if not data_admissao or not data_demissao or salario_base <= 0 or ("Insalubridade" in adicional_ocupacional and salario_minimo <= 0):
        st.info("Preencha os campos essenciais acima para iniciar a liquidação.")
        return
    if data_admissao >= data_demissao:
        st.warning("Atenção: A Admissão deve ser anterior à Demissão.")
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
    
    st.markdown(f"### LÍQUIDO A RECEBER: R$ {tot_liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    info_contrato = {"admissao": data_admissao.strftime("%d/%m/%Y"), "demissao": data_demissao.strftime("%d/%m/%Y"), "ano_competencia": ano_demissao, "motivo": motivo_rescisao, "salario_base": salario_base, "salario_minimo": salario_minimo, "adicional_nome": adicional_ocupacional, "he_50": he_50, "he_100": he_100, "he_noturna": he_noturna, "faltas": faltas_injustificadas, "vt_status": "Sim" if descontar_vt else "Não", "remun_rescisoria": float(remuneracao_rescisoria), "multa_467": multa_467, "valores_pagos": float(valores_pagos)}
    dic_totais = {"bruto": float(tot_bruto), "deducoes": float(tot_deducoes), "liquido": float(tot_liquido), "fgts_deposito": (remuneracao_rescisoria * (dias_totais / 30)) * 0.08, "fgts_multa": ((remuneracao_rescisoria * (dias_totais / 30)) * 0.08) * 0.40 if direito_aviso else 0, "multa_477": float(remuneracao_base), "hon_sucumbenciais": float(valor_hon_sucumbenciais), "hon_contratuais": float(valor_hon_contratuais)}
    
    st.markdown("<br>", unsafe_allow_html=True)
    ex1, ex2 = st.columns(2)
    with ex1: st.download_button("Baixar Excel", data=gerar_excel_trabalhista(df, info_contrato, dic_totais), file_name="Rescisao.xlsx", use_container_width=True)
    with ex2: st.download_button("Baixar Laudo PDF", data=gerar_pdf_trabalhista(df, info_contrato, dic_totais), file_name="Laudo_Rescisao.pdf", use_container_width=True)

def modulo_trabalhista_adc58():
    botao_voltar("Trabalhista")
    st.header("Atualização Monetária (ADC 58 - STF)")
    st.write("Fatia automaticamente o período pré-judicial (IPCA-E) e o judicial (SELIC) conforme a jurisprudência vinculante.")
    
    with st.container(border=True):
        st.markdown("<h5>Parâmetros da Condenação</h5>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        valor_original = c1.number_input("Valor Histórico (R$)", value=0.00, step=100.0)
        data_vencimento = c2.date_input("Vencimento da Verba", value=None, format="DD/MM/YYYY")
        data_ajuizamento = c3.date_input("Ajuizamento da Ação", value=None, format="DD/MM/YYYY")

        c4, c5, c6 = st.columns(3)
        data_calculo = c4.date_input("Data da Atualização", value=date.today(), format="DD/MM/YYYY")
        incluir_juros_pre = c5.checkbox("Juros Pré-Judiciais (1% a.m.)", value=False)

    if not data_vencimento or not data_ajuizamento or valor_original <= 0:
        st.info("Preencha o valor original e as datas para iniciar a atualização.")
        return
    if data_vencimento > data_ajuizamento:
        st.warning("A Data de Vencimento deve ser anterior ao Ajuizamento.")
        return
    if data_ajuizamento > data_calculo:
        st.warning("A Data de Cálculo não pode ser anterior ao Ajuizamento.")
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
        for _, row in df_ipcae_fase.iterrows(): percentual_acumulado_ipcae *= (1 + (row['Índice (%)'] / 100))
            
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
        <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #002B5B; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;">
            <h4 style="color: #002B5B; margin-top: 0;">Fase Pré-Judicial (IPCA-E)</h4>
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
        <div style="background-color: white; padding: 20px; border-radius: 8px; border-left: 4px solid #4B5563; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;">
            <h4 style="color: #4B5563; margin-top: 0;">Fase Judicial (SELIC)</h4>
            <p style="margin-bottom: 5px;">De <b>{data_ajuizamento.strftime('%m/%Y')}</b> até <b>{data_calculo.strftime('%m/%Y')}</b></p>
            <p style="margin-bottom: 5px;">Base Judicial: R$ {subtotal_fase_pre:,.2f}</p>
            <p style="margin-bottom: 5px;">SELIC Acumulada (Simples): {soma_selic_acumulada*100:.4f}%</p>
            <p style="margin-bottom: 5px;">Rendimento SELIC: R$ {valor_juros_correcao_selic:,.2f}</p>
            <hr style="margin: 10px 0;">
            <h5 style="color: #333; margin: 0;">Valor Atualizado: R$ {valor_final_absoluto:,.2f}</h5>
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"### DÍVIDA FINAL ATUALIZADA: R$ {valor_final_absoluto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))


# =================================================================
# --- ROTEAMENTO DE PÁGINAS (SINGLE PAGE APPLICATION) ---
# =================================================================
menu = st.session_state.menu_principal
ferramenta = st.session_state.ferramenta_ativa

if menu == "Inicio":
    st.title("Hub de Inteligência Pericial")
    st.write("Plataforma definitiva de cálculos jurídicos automatizados.")
    
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("<div class='tool-card-title'>Área Cível</div>", unsafe_allow_html=True)
            st.markdown("<div class='tool-card-desc'>Auditoria de contratos, expurgos inflacionários, revisões bancárias e atualização de débitos judiciais.</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("ACESSAR MÓDULO CÍVEL", on_click=navegar_para, args=("Cível", "Painel"), type="primary", use_container_width=True)
    with col2:
        with st.container(border=True):
            st.markdown("<div class='tool-card-title'>Área Trabalhista</div>", unsafe_allow_html=True)
            st.markdown("<div class='tool-card-desc'>Liquidação de sentenças, rescisões expressas, integração de reflexos e atualização monetária ADC 58.</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("ACESSAR MÓDULO TRABALHISTA", on_click=navegar_para, args=("Trabalhista", "Painel"), type="primary", use_container_width=True)

elif menu == "Cível":
    if ferramenta == "Painel":
        st.title("Painel da Área Cível")
        st.write("Escolha uma das calculadoras específicas para iniciar.")
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("<div class='tool-card-title'>Revisão de Cheque Especial e Contratos</div>", unsafe_allow_html=True)
            st.markdown("<div class='tool-card-desc'>Auditoria diária de extratos bancários. Isola a correção monetária, expurga juros abusivos e reconstrói o saldo devedor real utilizando as taxas do Banco Central.</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("Acessar Calculadora", on_click=navegar_para, args=("Cível", "Revisão de Cheque Especial"), key="btn_civ_1", type="primary")
        
        with st.container(border=True):
            st.markdown("<div class='tool-card-title'>Atualização Monetária (TJ Padrão)</div>", unsafe_allow_html=True)
            st.markdown("<div class='tool-card-desc'>Módulo para cumprimento de sentença cível. Aplica os índices inflacionários do Banco Central, juros de mora e honorários sucumbenciais ou contratuais automaticamente.</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("Acessar Calculadora", on_click=navegar_para, args=("Cível", "Atualização Monetária (TJ Padrão)"), key="btn_civ_2", type="primary")

    elif ferramenta == "Revisão de Cheque Especial":
        modulo_cheque_especial()
    elif ferramenta == "Atualização Monetária (TJ Padrão)":
        modulo_civel_atualizacao()

elif menu == "Trabalhista":
    if ferramenta == "Painel":
        st.title("Painel da Área Trabalhista")
        st.write("Escolha uma das calculadoras específicas para iniciar.")
        st.markdown("<br>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("<div class='tool-card-title'>Liquidação Expressa (Rescisão e Sentença)</div>", unsafe_allow_html=True)
            st.markdown("<div class='tool-card-desc'>Cálculo automatizado de verbas rescisórias, integrando adicionais ocupacionais, médias de horas extras, DSR e aplicação progressiva de INSS e IRRF vigentes.</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("Acessar Calculadora", on_click=navegar_para, args=("Trabalhista", "Liquidação Expressa (Rescisão)"), key="btn_trab_1", type="primary")
        
        with st.container(border=True):
            st.markdown("<div class='tool-card-title'>Atualização ADC 58 (IPCA-E + SELIC)</div>", unsafe_allow_html=True)
            st.markdown("<div class='tool-card-desc'>Atualização monetária e juros de acordos ou condenações. Segmenta automaticamente as fases pré-judicial e judicial, consumindo os índices oficiais em tempo real.</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.button("Acessar Calculadora", on_click=navegar_para, args=("Trabalhista", "Atualização ADC 58"), key="btn_trab_2", type="primary")

    elif ferramenta == "Liquidação Expressa (Rescisão)":
        modulo_trabalhista_rescisao()
    elif ferramenta == "Atualização ADC 58":
        modulo_trabalhista_adc58()
