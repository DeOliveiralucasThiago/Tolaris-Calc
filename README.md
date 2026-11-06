# Tolaris Calc

Calculadoras jurídicas e financeiras para o escritório, com **memória de cálculo auditável** e exportação em PDF/Excel.

| Calculadora | O que faz |
|---|---|
| **Cheque especial** | Evolução diária do saldo devedor (juros, correção, lançamentos) e comparação *taxa cobrada × taxa revisada* |
| **Atualização de débito** | Correção por IPCA/INPC/IPCA-E/IGP-M/INCC/SELIC, juros de mora, multa, custas e acréscimos do art. 523 CPC |
| **Financiamento e empréstimo** | Price/SAC, taxa efetivamente embutida na parcela cobrada, revisão e restituição (simples/dobro) |
| **Reajuste de aluguel/contratos** | Índice acumulado na janela contratual, teto e comparativo entre índices |
| **Juros e taxas** | Montante (simples/composto), conversão de taxas, taxa implícita |
| **Prazos e datas** | Dias úteis (CPC), corridos, meses e anos; feriados, recesso 20/12–20/01 e feriados locais |
| **Índices oficiais** | Consulta das séries do Banco Central usadas nos cálculos |

## Como rodar

```bash
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload     # http://localhost:8000
python -m pytest -q                          # testes automatizados
```

## Publicar no Render

1. Em render.com: **New → Blueprint** e aponte para este repositório (o `render.yaml` já configura tudo).
2. Defina `TOLARIS_USUARIO` e `TOLARIS_SENHA` para exigir login (HTTP Basic). **Recomendado**: sem isso, qualquer pessoa com o link acessa a ferramenta.
3. No plano gratuito o serviço hiberna após inatividade (primeira consulta demora ~30 s). Use o plano *Starter* para uso diário.

O sistema não guarda dados dos cálculos no servidor; só o cache dos índices do BCB (`data/cache`, descartável).

## Arquitetura

```
app/
  main.py              API FastAPI + entrega do front-end
  core/                numeros (Decimal), campos (validação), indices (BCB + cache), calendario, resultado
  calculators/         uma calculadora por arquivo: META (campos) + calcular(params) -> Resultado
  reports/             exportadores PDF e Excel (genéricos, servem a qualquer calculadora)
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
- Códigos SGS conferidos na API: IPCA 433, INPC 188, IPCA-E 10764, IGP-M 189, INCC 192, SELIC mensal 4390.

> Ferramenta de apoio ao cálculo. A parametrização jurídica (índice, marco inicial, taxa devida, calendário do tribunal)
> deve ser validada pelo advogado responsável.
