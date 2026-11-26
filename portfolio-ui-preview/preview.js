"use strict";

const demoFunds = {
  "110022": { name: "易方达消费行业", nav: 2.18 },
  "003095": { name: "中欧医疗健康", nav: 1.84 },
  "519674": { name: "银河创新成长", nav: 3.16 },
};
const sample = [
  { code: "110022", date: "2026-09-08", amount: 1000000, fee: 1000, units: 5000 },
  { code: "003095", date: "2026-09-21", amount: 800000, fee: 800, units: 4000 },
  { code: "519674", date: "2026-10-12", amount: 720000, fee: 720, units: 2400 },
  { code: "110022", date: "2026-10-19", amount: 420000, fee: 420, units: 2000 },
];
const get = (id) => document.getElementById(id);
const form = get("record-form");
const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 });
const rmb = new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" });
const money = (cents) => rmb.format(cents / 100);
let records = [];
let editing = -1;
let demo = false;
let analysed = false;
let active = "entry";
const pages = ["top", "entry", "records", "analysis", "guide"];
const pageLabels = ["首页", "录入", "购买记录", "基金分析", "使用说明"];
let page = "top";
let ignoreScrollUntil = 0;
let scrollFrame = 0;
const requests = {};

function element(tag, value, style) {
  const node = document.createElement(tag);
  if (value != null) node.textContent = value;
  if (style) node.className = style;
  return node;
}

function feedback(message, error = false) {
  const alert = get("feedback");
  alert.hidden = !message;
  alert.dataset.error = String(error);
  alert.textContent = message;
}

function chooseInput(mode) {
  form.hidden = mode !== "manual";
  get("upload-panel").hidden = mode !== "upload";
  document.querySelectorAll("[data-input]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.input === mode));
  });
}

function toMoney(raw, label) {
  if (!/^\d+(?:\.\d{1,2})?$/.test(raw) || Number(raw) > 100000000) {
    throw new Error(label + "须为 0 至 1 亿之间的金额，最多两位小数");
  }
  return Math.round(Number(raw) * 100);
}

function validate({ code, date, amount, fee = "", units = "" }) {
  if (!/^\d{6}$/.test(code)) throw new Error("基金代码须为六位数字");
  const day = new Date(date + "T00:00:00Z");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(+day)
      || day.toISOString().slice(0, 10) !== date) throw new Error("请填写有效的确认日期");
  const paid = toMoney(amount, "实付金额");
  const cost = toMoney(fee || "0", "手续费");
  if (paid <= cost) throw new Error("实付金额须大于手续费");
  if (units && (!/^\d+(?:\.\d{1,4})?$/.test(units) || Number(units) <= 0
    || Number(units) > 1000000000)) throw new Error("确认份额须为正数，最多四位小数");
  return { code, date, amount: paid, fee: cost, units: units ? Number(units) : null };
}

function readCsv(source) {
  const headers = {
    基金代码: "code", 确认日期: "date", 实付金额: "amount", 手续费: "fee", 确认份额: "units",
    code: "code", date: "date", amount: "amount", fee: "fee", units: "units",
  };
  const lines = source.replace(/^\uFEFF/, "").split(/\r?\n/);
  const fields = (line) => line.split(",").map((field) => field.trim().replace(/^"(.*)"$/, "$1").trim());
  const columns = fields(lines.shift() || "").map((name) => headers[name]);
  if (!["code", "date", "amount"].every((key) => columns.includes(key))
    || columns.some((key) => !key) || new Set(columns).size !== columns.length) {
    throw new Error("请使用示例表头，至少提供基金代码、确认日期和实付金额");
  }
  const entries = lines.flatMap((line, index) => {
    if (!line.trim()) return [];
    const values = fields(line);
    try {
      if (values.length !== columns.length) throw new Error("列数与表头不一致");
      return [validate(Object.fromEntries(columns.map((key, i) => [key, values[i]])))];
    } catch (error) {
      throw new Error(`第 ${index + 2} 行：${error.message}`);
    }
  });
  if (!entries.length) throw new Error("文件中没有购买记录");
  return entries;
}

function resetForm() {
  editing = -1;
  form.reset();
  get("save").textContent = "添加记录";
  get("cancel").hidden = true;
}

function setDemo(on) {
  demo = on;
  records = on ? sample.map((row) => ({ ...row })) : [];
  analysed = on;
  get("fund-filter").replaceChildren();
  get("weight-fields").replaceChildren();
  get("record-search").value = "";
  get("record-order").value = "date-desc";
  resetMarket();
  get("load-demo").textContent = on ? "清空示例，开始录入" : "载入示例";
  resetForm();
  chooseInput("manual");
  feedback("");
  render();
}

function fundLabel(code) {
  const wrap = element("span");
  wrap.append(element("span", demoFunds[code]?.name || "基金", "fund-name"),
    element("span", code, "fund-code"));
  return wrap;
}

function row(cells) {
  const tr = element("tr");
  cells.forEach((value) => {
    const td = element("td");
    td.append(value);
    tr.append(td);
  });
  return tr;
}

function updatePager(section) {
  page = section;
  const index = pages.indexOf(section);
  const previous = get("page-prev");
  const next = get("page-next");
  previous.disabled = index === 0;
  next.disabled = index === pages.length - 1;
  previous.title = previous.disabled ? "已到首页" : `上一页 · ${pageLabels[index - 1]}`;
  next.title = next.disabled ? "已到最后一页" : `下一页 · ${pageLabels[index + 1]}`;
  const indicator = get("page-number");
  indicator.textContent = `${String(index + 1).padStart(2, "0")} / 05`;
  indicator.setAttribute("aria-label", `第 ${index + 1} 页，共 5 页，${pageLabels[index]}`);
}

function scrollToPage(section, position = get(section)) {
  const direction = pages.indexOf(section) < pages.indexOf(page) ? "up" : "down";
  updatePager(section);
  ignoreScrollUntil = Date.now() + 560;
  position.scrollIntoView?.({ block: "start" });
  const element = section === "top" ? document.querySelector(".hero") : get(section);
  element.classList.remove("page-arrival");
  element.dataset.direction = direction;
  requestAnimationFrame(() => element.classList.add("page-arrival"));
}

function moveTo(section, focusTitle = false) {
  const destination = get(section);
  if (section !== active) {
    get(active).hidden = true;
    get(active).classList.remove("page-arrival");
    active = section;
    destination.hidden = false;
  }
  document.querySelectorAll(".top-nav [data-step], .workflow [data-step]").forEach((button) => {
    if (button.dataset.step === section) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
  const title = destination.querySelector("h2");
  if (focusTitle && title) {
    title.tabIndex = -1;
    title.focus({ preventScroll: true });
  }
  scrollToPage(section, get("workspace"));
}

function openPage(section, focusTitle = false) {
  if (section === "top" || section === "guide") {
    if (section === "guide") get("guide").open = true;
    scrollToPage(section);
    return;
  }
  if (section === "analysis" && !analysed && records.length) {
    analysed = true;
    renderAnalysis();
  }
  moveTo(section, focusTitle);
}

function pageBy(delta) {
  const requested = pages[pages.indexOf(page) + delta];
  if (requested) openPage(requested);
}

function syncScrollPosition() {
  scrollFrame = 0;
  if (Date.now() < ignoreScrollUntil) return;
  const limit = Math.min(window.innerHeight * .42, 230);
  const guide = get("guide");
  const partlyInGuide = guide.open && guide.getBoundingClientRect().top <= limit;
  const inWorkspace = get("workspace").getBoundingClientRect().top <= limit;
  const visiblePage = partlyInGuide ? "guide" : inWorkspace ? active : "top";
  if (page !== visiblePage) updatePager(visiblePage);
}

function renderRecords() {
  const count = new Set(records.map((row) => row.code)).size;
  get("hero-funds").textContent = `${count} 只`;
  get("hero-count").textContent = `${records.length} 笔`;
  get("hero-paid").textContent = money(records.reduce((sum, item) => sum + item.amount, 0));
  get("hero-source").textContent = demo ? "示例数据" : records.length ? "本地录入" : "待录入";
  get("step-count").textContent = records.length ? `· ${records.length} 笔` : "";
  get("record-count").textContent = (demo ? "示例数据 · " : "") + `${records.length} 笔 / ${count} 只基金`;
  get("analyse").disabled = !records.length;
  get("record-empty").hidden = Boolean(records.length);
  get("record-tools").hidden = !records.length;
  const query = get("record-search").value.trim().toLowerCase();
  const matches = records.map((item, index) => ({ item, index }))
    .filter(({ item }) => !query || `${item.code} ${demoFunds[item.code]?.name || ""}`.toLowerCase().includes(query));
  const order = get("record-order").value;
  matches.sort((left, right) => {
    const a = left.item;
    const b = right.item;
    if (order === "amount-desc") return b.amount - a.amount || b.date.localeCompare(a.date);
    return order === "date-asc" ? a.date.localeCompare(b.date) : b.date.localeCompare(a.date);
  });
  get("record-table").hidden = !matches.length;
  get("clear-search").hidden = !query;
  const status = get("record-matches");
  status.hidden = !records.length || !query;
  status.textContent = matches.length ? `显示 ${matches.length} / ${records.length} 笔` : "没有匹配的购买记录。";
  get("record-body").replaceChildren(...matches.map(({ item, index }) => {
    const actions = element("span");
    for (const action of ["编辑", "移除"]) {
      const button = element("button", action);
      button.type = "button";
      button.setAttribute("aria-label", `${action} ${item.code} ${item.date} 的购买记录`);
      button.addEventListener("click", () => {
        if (action === "移除") {
          records.splice(index, 1);
          resetForm();
          analysed = false;
          resetMarket();
          render();
          return;
        }
        editing = index;
        chooseInput("manual");
        for (const [key, value] of Object.entries(item)) {
          form.elements.namedItem(key).value =
            value == null ? "" : key === "amount" || key === "fee" ? value / 100 : value;
        }
        get("save").textContent = "保存修改";
        get("cancel").hidden = false;
        moveTo("entry");
        form.elements.namedItem("code").focus();
      });
      actions.append(button);
    }
    return row([item.date, fundLabel(item.code), money(item.amount), money(item.fee),
      item.units == null ? "待确认" : number.format(item.units), actions]);
  }));
}

function renderAnalysis() {
  const filter = get("fund-filter");
  const selected = filter.value;
  get("analysis-result").hidden = !analysed;
  get("analysis-empty").hidden = analysed;
  get("filter-label").hidden = !analysed;
  get("analysis-context").textContent = analysed
    ? demo ? "示例数据 · 估值日 2026-10-30" : "本次录入 · 购买记录汇总"
    : "核对记录后生成组合概览。";
  if (!analysed) return;

  const byCode = new Map();
  for (const item of records) {
    if (!byCode.has(item.code)) {
      byCode.set(item.code, { code: item.code, amount: 0, fee: 0, units: 0, count: 0, complete: true });
    }
    const fund = byCode.get(item.code);
    fund.amount += item.amount;
    fund.fee += item.fee;
    fund.count++;
    fund.units += item.units ?? 0;
    fund.complete &&= item.units != null;
  }
  const funds = [...byCode.values()].sort((a, b) => b.amount - a.amount);
  filter.replaceChildren(
    new Option("全部基金", ""),
    ...funds.map(({ code }) => new Option(`${code} ${demoFunds[code]?.name || ""}`, code)),
  );
  if (byCode.has(selected)) filter.value = selected;
  get("market-review").disabled = !filter.value;
  get("market-review").textContent = filter.value
    ? `查看 ${filter.value} 月度回顾` : "先选择一只基金";
  get("sample-weights").hidden = !demo;
  renderWeightFields(funds);
  const shown = filter.value ? [byCode.get(filter.value)] : funds;
  const total = funds.reduce((sum, item) => sum + item.amount, 0);
  const paid = shown.reduce((sum, item) => sum + item.amount, 0);
  const fee = shown.reduce((sum, item) => sum + item.fee, 0);
  const estimatedValue = (fund) => demo && fund.complete && demoFunds[fund.code]
    ? Math.round(fund.units * demoFunds[fund.code].nav * 100) : null;
  const ready = shown.every((fund) => estimatedValue(fund) != null);
  const value = ready ? shown.reduce((sum, item) => sum + estimatedValue(item), 0) : null;
  get("valuation-head").textContent = demo ? "示例市值" : "真实市值";
  get("profit-head").textContent = demo ? "示例持有盈亏" : "个人持有盈亏";
  get("metrics").replaceChildren(...[
    ["基金数量", shown.length + " 只"],
    ["累计实付", money(paid)],
    ["申购手续费", money(fee)],
    [demo ? "示例市值" : "真实市值", value == null ? "待接入" : money(value)],
  ].map(([label, amount]) => {
    const metric = element("div", null, "metric");
    metric.append(element("span", label), element("strong", amount));
    return metric;
  }));
  get("show-all-funds").hidden = !filter.value;
  get("allocation").replaceChildren(...funds.map((fund) => {
    const portion = fund.amount / total;
    const wrap = element("button", null, "allocation-row");
    wrap.type = "button";
    wrap.dataset.fund = fund.code;
    wrap.setAttribute("aria-pressed", String(filter.value === fund.code));
    wrap.setAttribute("aria-label", `查看 ${fund.code}，占累计实付 ${(portion * 100).toFixed(1)}%`);
    const meter = element("meter");
    meter.value = portion;
    meter.setAttribute("aria-hidden", "true");
    wrap.append(element("span", fund.code), meter, element("span", `${(portion * 100).toFixed(1)}%`));
    wrap.addEventListener("click", () => {
      selectFund(filter.value === fund.code ? "" : fund.code);
      get("allocation").querySelector(`[data-fund="${fund.code}"]`)?.focus({ preventScroll: true });
    });
    return wrap;
  }));
  get("analysis-body").replaceChildren(...shown.map((fund) => {
    const estimate = estimatedValue(fund);
    return row([fundLabel(fund.code), String(fund.count), money(fund.amount),
      fund.complete ? number.format(fund.units) : "部分待确认",
      estimate == null ? "—" : money(estimate), estimate == null ? "—" : money(estimate - fund.amount)]);
  }));
  get("analysis-foot").textContent = demo
    ? "示例估值＝确认份额 × 虚构估值日净值。示例盈亏＝估值 − 累计实付。实付已含手续费。"
    : "当前可核对购买金额和费用。真实市值与收益需接入估值日净值，并补齐缺失份额及后续交易。";
}

const pct = (value, points = false) => typeof value === "number"
  ? `${(value * 100).toFixed(2)}${points ? " 个百分点" : "%"}` : "—";

function renderWeightFields(funds) {
  const holder = get("weight-fields");
  const signature = funds.map((item) => item.code).join(",");
  if (holder.dataset.signature === signature && holder.children.length) return;
  const saved = new Map([...holder.querySelectorAll("input")].map((input) => [input.name, input.value]));
  holder.dataset.signature = signature;
  holder.replaceChildren(...funds.map(({ code }) => {
    const label = element("label", `${code} 期初权重（%）`);
    const input = element("input");
    Object.assign(input, { name: code, type: "number", min: "0", max: "100", step: "0.01",
      placeholder: "0.00", value: saved.get(code) || "" });
    label.append(input);
    return label;
  }));
  updateWeightStatus();
}

function weightState() {
  const fields = [...get("weight-fields").querySelectorAll("input")];
  const weights = {};
  let total = 0;
  for (const input of fields) {
    if (!input.validity.valid) return { weights, total, invalid: true };
    const basisPoints = Math.round(Number(input.value) * 100);
    if (basisPoints > 0) {
      weights[input.name] = basisPoints / 10000;
      total += basisPoints;
    }
  }
  return { weights, total, invalid: false };
}

function updateWeightStatus() {
  const { invalid, total } = weightState();
  const status = get("weight-status");
  status.dataset.error = String(invalid || total > 10000);
  status.textContent = invalid ? "请输入 0 至 100 之间的百分比，最多两位小数。"
    : total > 10000 ? `合计 ${(total / 100).toFixed(2)}%，不能超过 100%。`
    : total ? `基金权重 ${(total / 100).toFixed(2)}% · 现金权重 ${((10000 - total) / 100).toFixed(2)}%`
    : "填写至少一只基金的期初权重，剩余部分按现金处理。";
  get("portfolio-review").disabled = invalid || total <= 0 || total > 10000 || Boolean(requests["portfolio-result"]);
}

function selectFund(code) {
  get("fund-filter").value = code;
  resetMarket("single-review");
  renderAnalysis();
}

function resetMarket(...ids) {
  for (const id of ids.length ? ids : ["single-review", "portfolio-result"]) {
    requests[id]?.abort();
    delete requests[id];
    const result = get(id);
    result.replaceChildren();
    delete result.dataset.error;
    if (id === "single-review") get("market-review").disabled = !get("fund-filter").value;
    else updateWeightStatus();
  }
}

function resultMetrics(rows) {
  const container = element("div", null, "metrics");
  for (const [label, value] of rows) {
    const card = element("div", null, "metric");
    card.append(element("span", label), element("strong", value));
    container.append(card);
  }
  return container;
}

function resultTable(headers, rows) {
  const scroll = element("div", null, "table-scroll");
  const table = element("table");
  const header = element("tr");
  header.append(...headers.map((text) => element("th", text)));
  const thead = element("thead");
  thead.append(header);
  const tbody = element("tbody");
  tbody.append(...rows.map(row));
  table.append(thead, tbody);
  scroll.append(table);
  return scroll;
}

function renderNotes(target, entries) {
  const notes = entries.filter(Boolean);
  if (!notes.length) return;
  const details = element("details");
  details.append(element("summary", `数据口径与提示（${notes.length}）`));
  const list = element("ul");
  list.append(...notes.map((note) => element("li", note)));
  details.append(list);
  target.append(details);
}

async function queryMarket(path, payload, id, button, show) {
  const month = get("review-month");
  if (!month.reportValidity()) return;
  resetMarket(id);
  const target = get(id);
  if (location.protocol === "file:") {
    target.textContent = "请在 http://127.0.0.1:5174/ 打开预览，以访问本机基金接口。";
    target.dataset.error = "true";
    return;
  }
  const controller = new AbortController();
  requests[id] = controller;
  button.disabled = true;
  target.textContent = "正在读取项目数据…";
  try {
    const response = await fetch(path, {
      method: "POST", signal: controller.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, month: month.value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message || data.detail || "项目接口暂不可用");
    if (requests[id] === controller) {
      target.replaceChildren();
      show(target, data);
    }
  } catch (error) {
    if (requests[id] === controller && !controller.signal.aborted) {
      target.textContent = error.message;
      target.dataset.error = "true";
    }
  } finally {
    if (requests[id] === controller) {
      delete requests[id];
      if (id === "single-review") button.disabled = !get("fund-filter").value;
      else updateWeightStatus();
    }
  }
}

function showSingle(target, data) {
  const interval = data.results?.["returns.interval"];
  const attrib = data.results?.["attribution.brinson"];
  const holdings = data.meta?.holdings;
  target.append(element("strong", `${data.fund.name} · ${data.month}`), resultMetrics([
    ["基金区间收益", pct(interval?.data?.period_return)],
    ["最大回撤", pct(interval?.data?.max_drawdown)],
    ["有效净值点", String(data.nav_series.length)],
    ["披露持仓", `${data.holdings.length} 只`],
  ]));
  target.append(element("p", `持仓披露期：${holdings?.quarter || holdings?.as_of || "未提供"}`, "muted"));
  if (attrib?.status === "ready") {
    const rows = [...(attrib.data.industries || [])]
      .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 6);
    if (rows.length) target.append(resultTable(["行业", "披露持仓权重", "贡献"], rows.map((item) =>
      [item.industry, pct(item.weight), pct(item.contribution, true)])));
    target.append(element("p", `归因未解释部分：${pct(attrib.data.residual_return, true)}`, "muted"));
  }
  renderNotes(target, [...(interval?.notes || []), ...(attrib?.notes || []), ...(data.errors || [])]);
}

function showPortfolio(target, data) {
  target.append(resultMetrics([
    ["组合区间收益", pct(data.total_return)],
    ["期初现金权重", pct(data.cash_weight)],
    ["对账残差", pct(data.residual_return, true)],
  ]));
  target.append(resultTable(["基金", "期初权重", "区间收益", "组合贡献"],
    data.contributions.map((item) => [fundLabel(item.fund_code), pct(item.weight),
      pct(item.period_return), pct(item.contribution, true)])));
  renderNotes(target, [...(data.notes || []), ...(data.errors || [])]);
}

function render() {
  renderRecords();
  renderAnalysis();
}

async function importFile(file) {
  if (!file) return;
  try {
    if (file.size > 1024 * 1024) throw new Error("请选择小于 1 MB 的 CSV 文件");
    const entries = readCsv(await file.text());
    if (demo) setDemo(false);
    records.push(...entries);
    analysed = false;
    resetMarket();
    resetForm();
    feedback(`已导入 ${entries.length} 笔，请核对下方记录。`);
    render();
  } catch (error) {
    feedback(error.message, true);
  } finally {
    get("file-input").value = "";
  }
}

document.querySelectorAll("[data-input]").forEach((button) =>
  button.addEventListener("click", () => { chooseInput(button.dataset.input); feedback(""); }));
document.querySelectorAll("[data-step]").forEach((button) =>
  button.addEventListener("click", () => {
    if (button.hasAttribute("data-upload")) chooseInput("upload");
    openPage(button.dataset.step, true);
  }));
document.querySelector('a[href="#guide"]').addEventListener("click", (event) => {
  event.preventDefault();
  openPage("guide");
});
document.querySelector('a[href="#top"]').addEventListener("click", (event) => {
  event.preventDefault();
  openPage("top");
});
get("page-prev").addEventListener("click", () => pageBy(-1));
get("page-next").addEventListener("click", () => pageBy(1));
window.addEventListener("scroll", () => {
  if (!scrollFrame) scrollFrame = requestAnimationFrame(syncScrollPosition);
}, { passive: true });
get("load-demo").addEventListener("click", () => {
  if (demo || !records.length || window.confirm("载入示例会替换当前页面的记录，继续吗？")) setDemo(!demo);
});
get("cancel").addEventListener("click", () => { resetForm(); feedback(""); });
form.addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    const record = validate(Object.fromEntries(new FormData(form)));
    if (demo && editing < 0) setDemo(false);
    if (editing < 0) records.push(record);
    else records[editing] = record;
    analysed = false;
    resetMarket();
    resetForm();
    feedback("已保存。请在购买记录中核对后开始分析。");
    render();
  } catch (error) {
    feedback(error.message, true);
  }
});
get("file-input").addEventListener("change", (event) => importFile(event.target.files[0]));
get("drop-zone").addEventListener("dragover", (event) => event.preventDefault());
get("drop-zone").addEventListener("drop", (event) => {
  event.preventDefault();
  importFile(event.dataTransfer.files[0]);
});
get("analyse").addEventListener("click", () => {
  analysed = records.length > 0;
  get("fund-filter").value = "";
  renderAnalysis();
  moveTo("analysis", true);
});
get("fund-filter").addEventListener("change", (event) => selectFund(event.target.value));
get("show-all-funds").addEventListener("click", () => {
  selectFund("");
  get("fund-filter").focus();
});
get("record-search").addEventListener("input", renderRecords);
get("record-order").addEventListener("change", renderRecords);
get("clear-search").addEventListener("click", () => {
  const search = get("record-search");
  search.value = "";
  renderRecords();
  search.focus();
});
get("review-month").addEventListener("change", () => {
  get("weight-fields").querySelectorAll("input").forEach((input) => { input.value = ""; });
  resetMarket();
});
get("weight-fields").addEventListener("input", () => resetMarket("portfolio-result"));
get("market-review").addEventListener("click", (event) => {
  const code = get("fund-filter").value;
  if (code) queryMarket("/api/review", { fund_code: code }, "single-review", event.currentTarget, showSingle);
});
get("sample-weights").addEventListener("click", () => {
  const fields = [...get("weight-fields").querySelectorAll("input")];
  const initialWeight = (Math.floor(10000 / fields.length) / 100).toFixed(2);
  fields.forEach((input) => { input.value = initialWeight; });
  resetMarket("portfolio-result");
});
get("portfolio-review").addEventListener("click", (event) => {
  const { weights, total, invalid } = weightState();
  if (invalid || total <= 0 || total > 10000) return;
  queryMarket("/api/portfolio/review", { weights }, "portfolio-result", event.currentTarget, showPortfolio);
});
setDemo(true);
if (location.hash === "#guide") openPage("guide");
else updatePager("top");
document.querySelectorAll(".top-nav [data-step='entry'], .workflow [data-step='entry']")
  .forEach((button) => button.setAttribute("aria-current", "step"));
