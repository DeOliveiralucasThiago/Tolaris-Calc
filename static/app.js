/* Tolaris Calc – front-end (sem dependências). Os formulários são gerados a partir de /api/calculadoras. */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const el = (tag, attrs = {}, ...filhos) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "html") n.innerHTML = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) n.append(f.nodeType ? f : document.createTextNode(f));
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ICONES = {
  bank: '<path d="M3 10 12 4l9 6M5 10v8m4-8v8m6-8v8m4-8v8M3 20h18M3 10h18"/>',
  scale: '<path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0L5 7m14 0-3 7a3 3 0 0 0 6 0l-3-7"/>',
  building: '<path d="M4 21V5l8-2v18M12 9l8 2v10M2 21h20M8 9h.01M8 13h.01M8 17h.01M16 15h.01M16 18h.01"/>',
  home: '<path d="m3 11 9-8 9 8M5 9.5V21h14V9.5M10 21v-6h4v6"/>',
  percent: '<path d="M19 5 5 19M7 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm10 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/>',
  calendar: '<path d="M7 3v4m10-4v4M4 9h16M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm4 8 2 2 4-4"/>',
  chart: '<path d="M4 20V4M4 20h16M8 16v-4m4 4V8m4 8v-6"/>',
};
const icone = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONES[n] || ICONES.chart}</svg>`;

/* ------------------------------------------------------------ armazenamento (opcional) */
const guarda = {
  ler(k, pad) { try { const v = localStorage.getItem(k); return v == null ? pad : JSON.parse(v); } catch { return pad; } },
  gravar(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* modo privado */ } },
};

/* --------------------------------------------------------------------- formatação pt-BR */
const nf = (v, c) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c }).format(Number(v));
function fmt(v, tipo) {
  if (v == null || v === "") return "";
  switch (tipo) {
    case "dinheiro": return "R$ " + nf(v, 2);
    case "percentual": return nf(v, 4) + "%";
    case "taxa": return nf(v, 4);
    case "fator": return nf(v, 8);
    case "data": { if (!/^\d{4}-\d{2}-\d{2}/.test(v)) return String(v); const [a, m, d] = String(v).split("-"); return `${d}/${m}/${a}`; }
    case "mes": { if (!/^\d{4}-\d{2}/.test(v)) return String(v); const [a, m] = String(v).split("-"); return `${m}/${a}`; }
    case "inteiro": return /^-?\d+$/.test(String(v)) ? nf(v, 0) : String(v);
    default: return String(v);
  }
}
/* "1.234,56" -> "1234.56"; "1234.56" permanece; "1.234" (milhar) -> "1234" */
function normalizaNumero(s) {
  s = String(s ?? "").trim().replace(/\s|R\$|%/g, "");
  if (!s) return "";
  if (s.includes(",")) return s.replace(/\./g, "").replace(",", ".");
  if (/^-?\d{1,3}(\.\d{3})+$/.test(s)) return s.replace(/\./g, "");
  return s;
}
const hojeISO = () => { const d = new Date(); return new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); };

/* ------------------------------------------------------------------------- estado/API */
let catalogo = [];
async function api(url, opts) {
  let r;
  try { r = await fetch(url, opts); } catch { throw new Error("Sem conexão com o servidor. Verifique a internet e tente novamente."); }
  if (!r.ok) {
    let msg = "Não foi possível concluir a operação.", campo = null;
    try { const j = await r.json(); msg = j.erro || j.detail || msg; campo = j.campo || null; } catch { /* corpo não-JSON */ }
    const e = new Error(typeof msg === "string" ? msg : "Requisição inválida."); e.campo = campo; throw e;
  }
  return r;
}
const toast = (txt) => {
  const t = el("div", { class: "toast", role: "status" }, txt); document.body.append(t); setTimeout(() => t.remove(), 2600);
};

/* ------------------------------------------------------------------------ navegação */
function montaNav() {
  const nav = $("#nav"); nav.innerHTML = "";
  nav.append(el("a", { class: "nav-item", href: "#/", "data-rota": "/", html: icone("chart") + "<span>Início</span>" }));
  const grupos = {};
  catalogo.forEach((c) => (grupos[c.categoria] ||= []).push(c));
  for (const [g, itens] of Object.entries(grupos)) {
    nav.append(el("div", { class: "nav-grupo" }, g));
    itens.forEach((c) => nav.append(el("a", { class: "nav-item", href: `#/c/${c.slug}`, "data-rota": `/c/${c.slug}`, html: icone(c.icone) + `<span>${esc(c.titulo)}</span>` })));
  }
  nav.append(el("div", { class: "nav-grupo" }, "Referência"));
  nav.append(el("a", { class: "nav-item", href: "#/indices", "data-rota": "/indices", html: icone("chart") + "<span>Índices oficiais</span>" }));
}
function marcaNav(rota) {
  document.querySelectorAll(".nav-item").forEach((a) => { if (a.dataset.rota === rota) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
}
function fechaMenu() { $("#lateral").classList.remove("aberta"); $("#veu").hidden = true; $("#menu").setAttribute("aria-expanded", "false"); }
$("#menu").addEventListener("click", () => { const a = $("#lateral").classList.toggle("aberta"); $("#veu").hidden = !a; $("#menu").setAttribute("aria-expanded", String(a)); });
$("#veu").addEventListener("click", fechaMenu);
$("#tema").addEventListener("click", () => {
  const atual = document.documentElement.dataset.tema || (matchMedia("(prefers-color-scheme:dark)").matches ? "escuro" : "claro");
  const novo = atual === "escuro" ? "claro" : "escuro";
  document.documentElement.dataset.tema = novo; guarda.gravar("tolaris.tema", novo);
});
{ const t = guarda.ler("tolaris.tema", null); if (t) document.documentElement.dataset.tema = t; }

function rotear() {
  fechaMenu();
  const h = location.hash.replace(/^#/, "") || "/";
  const main = $("#conteudo"); main.innerHTML = "";
  let m;
  if ((m = h.match(/^\/c\/([\w-]+)/))) {
    const c = catalogo.find((x) => x.slug === m[1]);
    if (c) { telaCalculadora(main, c); marcaNav(`/c/${c.slug}`); document.title = `${c.titulo} · Tolaris Calc`; $("#topo-titulo").textContent = c.titulo; return; }
  }
  if (h.startsWith("/indices")) { telaIndices(main); marcaNav("/indices"); document.title = "Índices oficiais · Tolaris Calc"; $("#topo-titulo").textContent = "Índices oficiais"; return; }
  telaInicio(main); marcaNav("/"); document.title = "Tolaris Calc · Cálculos jurídicos e financeiros"; $("#topo-titulo").textContent = "Tolaris Calc";
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", rotear);

/* ---------------------------------------------------------------------------- início */
function telaInicio(main) {
  main.append(el("section", { class: "hero" },
    el("div", { class: "sobretitulo" }, "Escritório · Ferramentas de cálculo"),
    el("h1", {}, "Cálculos jurídicos e financeiros, com memória que você consegue conferir."),
    el("p", {}, "Cada resultado mostra os parâmetros, a metodologia e a memória linha a linha, e pode ser exportado em PDF ou Excel para juntar aos autos ou ao parecer.")));
  main.append(el("div", { class: "grade" }, catalogo.map((c) =>
    el("a", { class: "cartao", href: `#/c/${c.slug}` },
      el("div", { class: "ic", html: icone(c.icone) }), el("div", { class: "etq" }, c.categoria),
      el("h3", {}, c.titulo), el("p", {}, c.descricao)))));
  main.append(el("h2", { class: "secao-home" }, "Por que confiar"));
  main.append(el("div", { class: "confianca" },
    ...[["Aritmética decimal", "Sem erros de ponto flutuante: valores monetários calculados em precisão decimal."],
        ["Índices oficiais", "IPCA, INPC, IPCA-E, IGP-M, INCC e SELIC lidos do Banco Central, com aviso quando faltar mês."],
        ["Metodologia explícita", "Cada resultado lista as premissas adotadas, para você ajustar a tese e justificar o cálculo."],
        ["Testado", "Os motores de cálculo têm testes automatizados com resultados conferidos à mão."]]
      .map(([t, d]) => el("div", {}, el("b", {}, t), el("span", {}, d)))));
}

/* ------------------------------------------------------------------- calculadoras */
const visivel = (campo, valores) => !campo.mostrar_se || campo.mostrar_se.em.includes(valores[campo.mostrar_se.campo]);

function telaCalculadora(main, calc) {
  const chave = `tolaris.form.${calc.slug}`;
  const salvo = guarda.ler(chave, {});
  const valores = {};
  calc.campos.forEach((c) => {
    let v = salvo[c.nome] ?? c.padrao;
    if (c.nome === "data_calculo" && !salvo[c.nome]) v = hojeISO();
    valores[c.nome] = v ?? (c.tipo === "tabela" || c.tipo === "datas" ? [] : c.tipo === "booleano" ? false : "");
  });
  const nos = {}; // nome -> elemento .campo

  const form = el("form", { class: "painel form", novalidate: true, "aria-label": `Dados de ${calc.titulo}` });
  const grupos = new Map();
  calc.campos.forEach((c) => { const g = c.grupo || ""; if (!grupos.has(g)) grupos.set(g, []); grupos.get(g).push(c); });
  for (const [nome, campos] of grupos) {
    const avanc = nome === "avancado";
    const caixa = el("div", { class: "grupo" });
    if (nome && !avanc) caixa.append(el("h2", {}, nome));
    campos.forEach((c) => { const n = constroiCampo(c, valores, atualiza, calc); nos[c.nome] = n; caixa.append(n); });
    const comp = campos.filter((c) => c.composicao);
    if (comp.length > 1) {
      const alvo = () => !comp.every((c) => valores[c.nome]);
      const b = el("button", { class: "mini", type: "button" }, "Marcar todos");
      b.addEventListener("click", () => {
        const marcar = alvo();
        comp.forEach((c) => { valores[c.nome] = marcar; nos[c.nome].querySelector("input").checked = marcar; });
        b.textContent = marcar ? "Desmarcar todos" : "Marcar todos"; atualiza();
      });
      nos[comp[comp.length - 1].nome].after(b);
      b.textContent = comp.every((c) => valores[c.nome]) ? "Desmarcar todos" : "Marcar todos";
    }
    form.append(avanc ? el("details", { class: "avancado" }, el("summary", {}, "Opções avançadas"), caixa) : caixa);
  }
  const btn = el("button", { class: "btn btn-primario", type: "submit" }, "Calcular");
  form.append(el("div", { class: "acoes-form" }, btn,
    el("button", { class: "btn btn-sec", type: "button", onclick: () => { if (confirm("Limpar todos os campos?")) { guarda.gravar(chave, {}); rotear(); } } }, "Limpar")));

  const saida = el("section", { class: "painel resultado", "aria-live": "polite" });
  saida.append(vazio(calc));

  main.append(el("div", { class: "cab" }, el("div", { class: "etq" }, calc.categoria), el("h1", {}, calc.titulo), el("p", {}, calc.descricao)),
    el("div", { class: "duas" }, form, saida));

  function atualiza() {
    calc.campos.forEach((c) => nos[c.nome].hidden = !visivel(c, valores));
    guarda.gravar(chave, valores);
  }
  atualiza();

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    Object.values(nos).forEach((n) => n.classList.remove("invalido"));
    const parametros = {};
    calc.campos.forEach((c) => { if (visivel(c, valores)) parametros[c.nome] = paraEnvio(c, valores[c.nome]); });
    btn.disabled = true; btn.innerHTML = '<span class="carregando"></span> Calculando…';
    try {
      const r = await api(`/api/calcular/${calc.slug}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parametros }) });
      renderResultado(saida, await r.json(), calc);
      if (matchMedia("(max-width:1100px)").matches) saida.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      saida.innerHTML = ""; saida.append(el("div", { class: "corpo-res" }, el("div", { class: "erro", role: "alert" }, e.message)));
      if (e.campo && nos[e.campo]) { nos[e.campo].classList.add("invalido"); nos[e.campo].scrollIntoView({ block: "center", behavior: "smooth" }); }
    } finally { btn.disabled = false; btn.textContent = "Calcular"; }
  });
  form.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) form.requestSubmit(); });
}

function vazio(calc) {
  return el("div", { class: "estado-vazio", html: `${icone(calc.icone).replace("<svg", '<svg width="54" height="54"')}<h2>Preencha os dados e calcule</h2><p>O resultado, a memória de cálculo e as opções de exportação aparecem aqui.<br>Atalho: <kbd>Ctrl</kbd> + <kbd>Enter</kbd>.</p>` });
}

function paraEnvio(c, v) {
  if (["dinheiro", "percentual", "numero", "inteiro"].includes(c.tipo)) return normalizaNumero(v);
  if (c.tipo === "tabela") return (v || []).map((l) => Object.fromEntries(c.colunas.map((col) => [col.nome,
    ["dinheiro", "percentual", "numero"].includes(col.tipo) ? normalizaNumero(l[col.nome]) : l[col.nome] ?? ""])));
  return v;
}

function constroiCampo(c, valores, mudou, calc) {
  const id = `f-${c.nome}`;
  const caixa = el("div", { class: "campo" });
  const ajuda = c.ajuda ? el("div", { class: "ajuda", id: id + "-aj" }, c.ajuda) : null;
  const obrig = c.obrigatorio ? " *" : "";
  const set = (v) => { valores[c.nome] = v; mudou(); };

  if (c.tipo === "booleano") {
    const i = el("input", { type: "checkbox", id }); i.checked = !!valores[c.nome];
    i.addEventListener("change", () => set(i.checked));
    caixa.append(el("label", { class: "check", for: id }, i, el("span", {}, c.rotulo)));
  } else if (c.tipo === "selecao") {
    const s = el("select", { id, "aria-describedby": ajuda && id + "-aj" }, c.opcoes.map((o) => el("option", { value: o.valor }, o.rotulo)));
    s.value = valores[c.nome]; if (s.value !== String(valores[c.nome])) { s.selectedIndex = 0; valores[c.nome] = s.value; }
    s.addEventListener("change", () => set(s.value));
    caixa.append(el("label", { for: id }, c.rotulo + obrig), s);
  } else if (c.tipo === "tabela") {
    caixa.append(el("span", { class: "rot" }, c.rotulo + obrig), editorTabela(c, valores, set));
  } else if (c.tipo === "datas") {
    caixa.append(el("span", { class: "rot" }, c.rotulo), editorDatas(c, valores, set));
  } else {
    const data = c.tipo === "data";
    const i = el("input", { id, type: data ? "date" : "text", inputmode: data ? null : c.tipo === "inteiro" ? "numeric" : "decimal", autocomplete: "off", "aria-describedby": ajuda && id + "-aj" });
    i.value = formataEntrada(c, valores[c.nome]);
    i.addEventListener("input", () => set(i.value));
    if (!data) i.addEventListener("blur", () => { const n = normalizaNumero(i.value); if (n !== "" && !isNaN(n) && c.tipo !== "inteiro") { i.value = formataEntrada(c, n); } });
    const pre = c.tipo === "dinheiro", pos = c.tipo === "percentual";
    const w = el("div", { class: "entrada" + (pre ? " pre" : "") + (pos ? " pos" : "") }, pre && el("span", { class: "afixo" }, "R$"), i, pos && el("span", { class: "afixo d" }, "%"));
    caixa.append(el("label", { for: id }, c.rotulo + obrig), data || !pre && !pos ? i : w);
  }
  if (ajuda) caixa.append(ajuda);
  return caixa;
}
function formataEntrada(c, v) {
  if (v == null || v === "") return "";
  if (["dinheiro", "percentual", "numero"].includes(c.tipo)) {
    const n = normalizaNumero(v); if (n === "" || isNaN(n)) return String(v);
    const casas = (n.split(".")[1] || "").length;
    return nf(n, c.tipo === "dinheiro" ? 2 : Math.min(Math.max(casas, c.tipo === "percentual" ? 2 : 0), 6));
  }
  return String(v);
}

function editorTabela(c, valores, set) {
  const raiz = el("div", { class: "editor" });
  const corpo = el("div");
  const linhas = () => valores[c.nome];
  const cols = c.colunas;
  const grade = cols.length === 4 ? "1fr 1fr" : cols.length === 2 ? "1fr 1fr" : `repeat(${Math.min(cols.length, 2)},1fr)`;
  function desenha() {
    corpo.innerHTML = "";
    if (!linhas().length) corpo.append(el("div", { class: "vazio" }, "Nenhuma linha. Use “Adicionar” ou “Colar do Excel”."));
    linhas().forEach((l, idx) => {
      const row = el("div", { class: "linha", style: `grid-template-columns:${grade};padding-right:34px` });
      cols.forEach((col) => {
        let inp;
        if (col.tipo === "selecao") {
          inp = el("select", { "aria-label": col.rotulo }, col.opcoes.map((o) => el("option", { value: o.valor }, o.rotulo)));
          inp.value = l[col.nome] ?? col.opcoes[0].valor; l[col.nome] = inp.value;
          inp.addEventListener("change", () => { l[col.nome] = inp.value; set(linhas()); });
        } else {
          inp = el("input", { type: col.tipo === "data" ? "date" : "text", inputmode: ["dinheiro", "percentual", "numero"].includes(col.tipo) ? "decimal" : null, "aria-label": col.rotulo, autocomplete: "off", placeholder: col.tipo === "dinheiro" ? "0,00" : "" });
          inp.value = l[col.nome] ?? "";
          inp.addEventListener("input", () => { l[col.nome] = inp.value; set(linhas()); });
        }
        row.append(el("div", { class: "cel" }, el("span", { class: "cel-rot" }, col.rotulo), inp));
      });
      row.append(el("button", { class: "rm", type: "button", "aria-label": `Remover linha ${idx + 1}`, onclick: () => { linhas().splice(idx, 1); set(linhas()); desenha(); } }, "×"));
      corpo.append(row);
    });
  }
  const nova = () => Object.fromEntries(cols.map((col) => [col.nome, col.tipo === "selecao" ? col.opcoes[0].valor : ""]));
  const colar = el("div", { class: "colar", hidden: true });
  const ta = el("textarea", { placeholder: cols.map((x) => x.rotulo).join(" ; ") + "\n(uma linha por registro; separe por ; ou TAB. Datas dd/mm/aaaa. Para tipo use D ou C.)", "aria-label": "Colar linhas" });
  colar.append(ta, el("div", { class: "editor-acoes" },
    el("button", { class: "mini", type: "button", onclick: () => { const n = importa(ta.value); if (n) { ta.value = ""; colar.hidden = true; desenha(); toast(`${n} linha(s) importada(s).`); } else toast("Nenhuma linha válida encontrada."); } }, "Importar"),
    el("button", { class: "mini", type: "button", onclick: () => (colar.hidden = true) }, "Cancelar")));
  function importa(texto) {
    let n = 0;
    texto.split(/\r?\n/).forEach((ln) => {
      if (!ln.trim()) return;
      const p = ln.split(/\t|;/).map((x) => x.trim());
      const reg = nova(); let ok = true;
      cols.forEach((col, i) => {
        const bruto = p[i] ?? "";
        if (col.tipo === "data") { const m = bruto.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); if (m) reg[col.nome] = `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`; else if (/^\d{4}-\d{2}-\d{2}$/.test(bruto)) reg[col.nome] = bruto; else ok = false; }
        else if (col.tipo === "selecao") { const u = bruto.toUpperCase().charAt(0); const o = col.opcoes.find((x) => x.valor === u); if (o) reg[col.nome] = o.valor; else ok = false; }
        else reg[col.nome] = bruto;
      });
      if (ok) { linhas().push(reg); n++; }
    });
    set(linhas()); return n;
  }
  raiz.append(corpo, el("div", { class: "editor-acoes" },
    el("button", { class: "mini", type: "button", onclick: () => { linhas().push(nova()); set(linhas()); desenha(); } }, "+ Adicionar"),
    el("button", { class: "mini", type: "button", onclick: () => (colar.hidden = !colar.hidden) }, "Colar do Excel"),
    el("button", { class: "mini", type: "button", onclick: () => { if (linhas().length && confirm("Remover todas as linhas?")) { valores[c.nome] = []; set([]); desenha(); } } }, "Limpar")), colar);
  desenha();
  return raiz;
}

function editorDatas(c, valores, set) {
  const raiz = el("div", { class: "editor" }), corpo = el("div");
  const lista = () => valores[c.nome];
  function desenha() {
    corpo.innerHTML = "";
    if (!lista().length) corpo.append(el("div", { class: "vazio" }, "Nenhuma data adicional."));
    lista().forEach((d, i) => {
      const inp = el("input", { type: "date", "aria-label": `Data ${i + 1}` }); inp.value = d || "";
      inp.addEventListener("input", () => { lista()[i] = inp.value; set(lista()); });
      corpo.append(el("div", { class: "linha", style: "grid-template-columns:1fr;padding-right:34px" }, inp,
        el("button", { class: "rm", type: "button", "aria-label": "Remover data", onclick: () => { lista().splice(i, 1); set(lista()); desenha(); } }, "×")));
    });
  }
  raiz.append(corpo, el("div", { class: "editor-acoes" }, el("button", { class: "mini", type: "button", onclick: () => { lista().push(""); set(lista()); desenha(); } }, "+ Adicionar data")));
  desenha(); return raiz;
}

/* -------------------------------------------------------------------- resultados */
function tabelaHTML(t) {
  const cls = (tp) => (tp === "texto" ? "t" : tp === "data" || tp === "mes" ? "c" : "");
  const head = t.colunas.map((c) => `<th class="${cls(c.tipo)}" scope="col">${esc(c.rotulo)}</th>`).join("");
  const rows = t.linhas.map((l) => "<tr>" + t.colunas.map((c) => `<td class="${cls(c.tipo)}">${esc(fmt(l[c.chave], c.tipo))}</td>`).join("") + "</tr>").join("");
  const foot = t.total ? "<tfoot><tr>" + t.colunas.map((c) => `<td class="${cls(c.tipo)}">${t.total[c.chave] != null ? esc(fmt(t.total[c.chave], c.tipo)) : ""}</td>`).join("") + "</tr></tfoot>" : "";
  return `<div class="rolagem"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody>${foot}</table></div>`;
}

function renderResultado(box, r, calc) {
  box.innerHTML = "";
  const ident = guarda.ler("tolaris.ident", { Processo: "", Cliente: "", Responsável: "" });
  const exportar = async (fmtArq) => {
    try {
      const resp = await api(`/api/exportar/${fmtArq}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resultado: r, identificacao: ident }) });
      const blob = await resp.blob();
      const nome = /filename="([^"]+)"/.exec(resp.headers.get("Content-Disposition") || "")?.[1] || `Tolaris.${fmtArq}`;
      const a = el("a", { href: URL.createObjectURL(blob), download: nome }); document.body.append(a); a.click(); a.remove();
    } catch (e) { toast(e.message); }
  };
  const copiar = async () => {
    const txt = [r.titulo, ...r.resumo.map((k) => `${k.rotulo}: ${fmt(k.valor, k.tipo)}`)].join("\n");
    try { await navigator.clipboard.writeText(txt); toast("Resumo copiado."); } catch { toast("Não foi possível copiar."); }
  };
  box.append(el("div", { class: "res-topo" },
    el("div", {}, el("h2", {}, r.titulo), el("small", {}, "Emitido em " + new Date(r.gerado_em).toLocaleString("pt-BR"))),
    el("div", { class: "exportar" },
      el("button", { class: "btn btn-sec", type: "button", onclick: () => exportar("pdf") }, "PDF"),
      el("button", { class: "btn btn-sec", type: "button", onclick: () => exportar("docx") }, "Word"),
      el("button", { class: "btn btn-sec", type: "button", onclick: () => exportar("xlsx") }, "Excel"),
      el("button", { class: "btn btn-sec", type: "button", onclick: copiar }, "Copiar resumo"),
      el("button", { class: "btn btn-sec", type: "button", onclick: () => window.print() }, "Imprimir"))));
  const corpo = el("div", { class: "corpo-res" });
  r.avisos.forEach((a) => corpo.append(el("div", { class: "aviso", role: "note" }, a)));

  corpo.append(el("div", { class: "kpis" }, r.resumo.map((k) => el("div", { class: "kpi" + (k.destaque ? " destaque" : "") },
    el("div", { class: "r" }, k.rotulo), el("div", { class: "v" }, fmt(k.valor, k.tipo)), k.nota && el("div", { class: "n" }, k.nota)))));

  if (r.parametros.length) corpo.append(el("div", {}, el("h3", { class: "sub" }, "Parâmetros"),
    el("div", { class: "params" }, r.parametros.map((p) => el("div", {}, el("span", {}, p.rotulo), el("span", {}, fmt(p.valor, p.tipo)))))));

  r.tabelas.forEach((t) => {
    if (!t.linhas.length) return;
    const d = el("details", { class: "tabela-det" }, el("summary", {}, t.titulo, el("span", {}, `${t.linhas.length} linha(s)`)));
    const preenche = () => { if (!d.dataset.ok) { d.dataset.ok = "1"; d.insertAdjacentHTML("beforeend", tabelaHTML(t)); } };
    d.addEventListener("toggle", () => d.open && preenche());
    if (!t.recolhida) { d.open = true; preenche(); }
    window.addEventListener("beforeprint", () => { d.open = true; preenche(); }, { once: true });
    corpo.append(d);
  });

  if (r.metodologia.length) corpo.append(el("div", { class: "metodo" }, el("h3", { class: "sub" }, "Metodologia e premissas"),
    el("ul", {}, r.metodologia.map((m) => el("li", {}, m)))));

  const idBox = el("details", { class: "avancado" }, el("summary", {}, "Identificação para o PDF/Excel (processo, cliente…)"),
    el("div", { class: "grupo" }, Object.keys(ident).map((k) => {
      const i = el("input", { type: "text", value: ident[k], "aria-label": k, placeholder: k });
      i.addEventListener("input", () => { ident[k] = i.value; guarda.gravar("tolaris.ident", ident); });
      return el("div", { class: "campo" }, el("label", {}, k), i);
    })));
  corpo.append(idBox);
  box.append(corpo);
}

/* ------------------------------------------------------------------------- índices */
async function telaIndices(main) {
  main.append(el("div", { class: "cab" }, el("div", { class: "etq" }, "Referência"), el("h1", {}, "Índices oficiais"),
    el("p", {}, "Séries mensais do Banco Central (SGS) usadas pelas calculadoras. Consulte aqui o que está sendo aplicado.")));
  let lista;
  try { lista = await (await api("/api/indices")).json(); } catch (e) { main.append(el("div", { class: "erro" }, e.message)); return; }
  const sel = el("select", { id: "ind-sel" }, lista.map((i) => el("option", { value: i.nome }, `${i.nome} – ${i.descricao}`)));
  const caixa = el("div", { class: "painel" });
  const carrega = async (forcar) => {
    caixa.innerHTML = '<div class="estado-vazio"><span class="carregando"></span></div>';
    try {
      const d = await (await api(`/api/indices/${encodeURIComponent(sel.value)}${forcar ? "?atualizar=true" : ""}`)).json();
      caixa.innerHTML = ""; const corpo = el("div", { class: "corpo-res" });
      if (d.origem === "cache") corpo.append(el("div", { class: "aviso" }, `Banco Central indisponível; exibindo cópia salva em ${d.atualizado_em}.`));
      corpo.append(el("p", {}, el("span", { class: "pill" }, d.origem === "bcb" ? "Banco Central" : "Cópia salva"), ` Consulta em ${d.atualizado_em} · último mês: ${fmt(d.ultimo_mes + "-01", "mes")}${d.unidade !== "%" ? "" : " · acumulação: " + (d.acumulo === "soma" ? "soma simples" : "composta")}`));
      corpo.insertAdjacentHTML("beforeend", tabelaHTML({ colunas: [{ chave: "mes", rotulo: "Mês", tipo: "mes" }, { chave: "indice", rotulo: d.unidade === "R$" ? "Valor vigente (R$)" : d.unidade === "taxa" ? "Taxa média (% ao mês)" : "Variação no mês (%)", tipo: d.unidade === "R$" ? "dinheiro" : "taxa" }], linhas: d.valores.map((v) => ({ mes: v.mes + "-01", indice: v.indice })) }));
      caixa.append(corpo);
    } catch (e) { caixa.innerHTML = ""; caixa.append(el("div", { class: "corpo-res" }, el("div", { class: "erro" }, e.message))); }
  };
  sel.addEventListener("change", () => carrega(false));
  main.append(el("div", { class: "indices-barra" }, el("div", { class: "campo" }, el("label", { for: "ind-sel" }, "Índice"), sel),
    el("button", { class: "btn btn-sec", type: "button", onclick: () => carrega(true) }, "Atualizar agora")), caixa);
  carrega(false);
}

/* ---------------------------------------------------------------------------- boot */
(async function () {
  const main = $("#conteudo");
  main.innerHTML = '<div class="estado-vazio"><span class="carregando"></span></div>';
  try { catalogo = await (await api("/api/calculadoras")).json(); }
  catch (e) { main.innerHTML = ""; main.append(el("div", { class: "erro", role: "alert" }, e.message)); return; }
  montaNav(); rotear();
})();
