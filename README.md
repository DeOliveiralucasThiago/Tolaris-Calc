# Tolaris Calc

Calculadoras jurídicas e financeiras para o escritório, com **memória de cálculo auditável** e exportação em PDF, Excel e **laudo em Word (.docx)** editável.

| Calculadora | O que faz |
|---|---|
| **Débitos judiciais (modelo TJES)** | Atualização no padrão da Corregedoria do TJES: correção (INPC), Juros Legais, custas, multa, abatimento e honorários |
| **Taxa Legal (Lei 14.905/2024)** | Correção pelo IPCA e juros pela Taxa Legal do BCB, com a transição de 30/08/2024 |
| **Pensão alimentícia** | Parcelas em atraso (valor fixo ou % do salário mínimo), correção e juros por parcela, pagamentos e Súmula 309/STJ |
| **Honorários e êxito** | Fixos e êxito, sucumbência do art. 85 do CPC (inclusive escalonada contra a Fazenda), impostos e rateio |
| **Atualização monetária** | Índice à escolha (IPCA, INPC, IPCA-E, IGP-M, INCC, SELIC), juros, multa, custas e acréscimos do art. 523 |
| **Cartão de crédito (rotativo)** | Evolução diária do rotativo, multa e mora, limite de 100% (Lei 14.690/2023) e comparação com a taxa média do BCB |
| **Cheque especial** | Evolução diária do saldo devedor e comparação *taxa cobrada × taxa revisada* |
| **Financiamento e empréstimo** | Price/SAC, taxa efetivamente embutida na parcela cobrada, revisão e restituição (simples/dobro) |
| **Reajuste de aluguel/contratos** | Índice acumulado na janela contratual, teto e comparativo entre índices |
| **Juros e taxas** | Montante (simples/composto), conversão de taxas, taxa implícita |
| **Prazos e datas** | Dias úteis (CPC), corridos, meses e anos; feriados, recesso 20/12–20/01 e feriados locais |
| **Índices oficiais** | Consulta das séries do Banco Central usadas nos cálculos (inclui Taxa Legal e salário mínimo) |

## Como rodar

```bash
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload     # http://localhost:8000
python -m pytest -q                          # testes automatizados
```

## Publicar no Render

1. Em render.com: **New → Blueprint** e aponte para este repositório (o `render.yaml` já configura tudo).
2. O acesso é livre (sem login): quem tiver o link usa a ferramenta. Se um dia precisar de senha, defina `TOLARIS_USUARIO` e `TOLARIS_SENHA` no painel do Render.
3. No plano gratuito o serviço hiberna após inatividade (primeira consulta demora ~30 s). Use o plano *Starter* para uso diário.

O sistema não guarda dados dos cálculos no servidor; só o cache dos índices do BCB (`data/cache`, descartável).

## Arquitetura

```
app/
  main.py              API FastAPI + entrega do front-end
  core/                numeros (Decimal), campos (validação), indices (BCB + cache), calendario, resultado
  calculators/         uma calculadora por arquivo: META (campos) + calcular(params) -> Resultado
  reports/             exportadores PDF e Excel e laudo em Word (genéricos, servem a qualquer calculadora)
static/                interface (HTML/CSS/JS puro, sem build), formulários gerados a partir de META
tests/                 resultados conferidos à mão
```

**Nova calculadora** = um arquivo em `app/calculators/` com `META` (campos declarativos) e `calcular()`, registrado em
`app/calculators/__init__.py`. Formulário, validação, tela de resultado, PDF e Excel vêm de graça.

## Decisões de confiabilidade

- Toda a matemática usa `Decimal`; arredondamento só na apresentação.
- Índices vêm do SGS/Banco Central com cache em disco. Se o BCB cair, usa a última cópia **e avisa**. Mês sem índice divulgado
  é tratado como 0 % **com aviso explícito** (nunca silencioso) e pode ser informado manualmente em *Opções avançadas*.
- Cada resultado lista a **metodologia e as premissas** aplicadas; os parâmetros que variam por tribunal são escolhas do usuário.
- Códigos SGS conferidos na API: IPCA 433, INPC 188, IPCA-E 10764, IGP-M 189, INCC 192, SELIC mensal 4390, Taxa Legal 29543
  (fórmula conferida na Resolução CMN 5.171/2024) e salário mínimo 1619.
- Pendências de validação conhecidas: juros do modelo TJES divergem R$ 0,02 do exemplo oficial; multa do art. 523 no modelo TJES
  e pensão alimentícia ainda não foram comparadas com cálculos oficiais.

> Ferramenta de apoio ao cálculo. A parametrização jurídica (índice, marco inicial, taxa devida, calendário do tribunal)
> deve ser validada pelo advogado responsável.
