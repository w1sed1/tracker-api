const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];

const $ = (id) => document.getElementById(id);
let today = null; // server's today, "YYYY-MM-DD"
let openHabitId = null;

// Dates travel as "YYYY-MM-DD"; UTC keeps arithmetic free of timezone shifts.
const toDate = (iso) => new Date(iso + "T00:00:00Z");
const weekday = (iso) => (toDate(iso).getUTCDay() + 6) % 7;
const pct = (x) => Math.round(x * 100) + "%";

function addDays(iso, n) {
  const d = toDate(iso);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function fmt(iso, options = { day: "numeric", month: "short" }) {
  return toDate(iso).toLocaleDateString("uk-UA", { ...options, timeZone: "UTC" });
}

function days(n) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return n + " день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return n + " дні";
  return n + " днів";
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = Array.isArray(data.detail) ? "Перевірте назву і колір" : data.detail;
    throw new Error(detail || `Помилка сервера (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

// items: [{ value: 0..1, label?, title }]
function renderBars(container, items, color) {
  container.replaceChildren();
  for (const item of items) {
    const col = el("div", "bar-col");
    col.title = item.title;
    const track = el("div", "bar-track");
    const bar = el("div", "bar");
    bar.style.height = Math.max(item.value * 100, item.value > 0 ? 3 : 0) + "%";
    if (color) bar.style.background = color;
    track.append(bar);
    col.append(track);
    if (item.label) col.append(el("span", "bar-label", item.label));
    container.append(col);
  }
  container.setAttribute("role", "img");
  container.setAttribute("aria-label", items.map((i) => i.title).join("; "));
}

function renderOverview(o) {
  $("today").textContent = fmt(o.today, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  $("ov-today").textContent = `${o.done_today} / ${o.habits}`;
  $("ov-rate").textContent = pct(o.rate_30);
  $("ov-streak").textContent = days(o.best_current_streak);
  $("ov-longest").textContent = days(o.longest_streak);
  renderBars($("chart-daily"), o.daily.map((d) => ({
    value: d.total ? d.done / d.total : 0,
    title: `${fmt(d.day)}: ${d.done} з ${d.total}`,
  })));
  renderBars($("chart-weekdays"), o.weekdays.map((r, i) => ({
    value: r,
    label: WEEKDAYS[i],
    title: `${WEEKDAYS[i]}: ${pct(r)}`,
  })));
}

function renderHabits(habits) {
  $("empty").hidden = habits.length > 0;
  $("habits").replaceChildren(...habits.map((h) => {
    const row = el("li", "habit");
    row.style.setProperty("--c", h.color);

    const name = el("button", "habit-name", h.name);
    name.type = "button";
    name.title = "Статистика і налаштування";
    name.onclick = () => openDetails(h.id);

    const week = el("div", "week");
    h.stats.last_7.forEach((done, i) => {
      const day = addDays(today, i - 6);
      const btn = el("button", "day" + (done ? " done" : ""));
      btn.type = "button";
      btn.append(el("span", "day-wd", WEEKDAYS[weekday(day)]), el("span", "day-num", toDate(day).getUTCDate()));
      btn.setAttribute("aria-pressed", done);
      btn.setAttribute("aria-label", `${h.name}, ${fmt(day)}`);
      btn.onclick = () => toggle(h.id, day, done);
      week.append(btn);
    });

    const meta = el("div", "habit-meta");
    meta.append(
      el("span", null, "серія " + days(h.stats.current_streak)),
      el("span", null, "30 днів: " + pct(h.stats.rate_30)),
    );

    row.append(name, week, meta);
    return row;
  }));
}

function renderDetails(h) {
  const s = h.stats;
  $("details").style.setProperty("--c", h.color);
  $("d-name").textContent = h.name;
  $("d-since").textContent = `Відстежується з ${fmt(s.tracked_since, { day: "numeric", month: "long", year: "numeric" })} (${days(s.days_tracked)})`;
  $("d-streak").textContent = days(s.current_streak);
  $("d-longest").textContent = days(s.longest_streak);
  $("d-total").textContent = s.total;
  $("d-rate30").textContent = pct(s.rate_30);
  $("d-rate-all").textContent = pct(s.rate_all);
  renderBars($("d-weekly"), s.weekly.map((w) => ({
    value: w.count / 7,
    label: fmt(w.week_start, { day: "numeric" }),
    title: `Тиждень з ${fmt(w.week_start)}: ${w.count} з 7`,
  })), h.color);

  const cells = s.heatmap.map((d) => {
    const cell = el("span", "cell" + (d.done ? " done" : ""));
    cell.title = `${fmt(d.day)}: ${d.done ? "виконано" : "—"}`;
    return cell;
  });
  $("d-heatmap").replaceChildren(...cells);
  $("d-heatmap").setAttribute("role", "img");
  $("d-heatmap").setAttribute("aria-label", `${s.heatmap.filter((d) => d.done).length} відміток за ${s.heatmap.length} днів`);

  $("edit-name").value = h.name;
  $("edit-color").value = h.color;
}

async function refresh() {
  const [overview, habits] = await Promise.all([api("GET", "/api/overview"), api("GET", "/api/habits")]);
  today = overview.today;
  renderOverview(overview);
  renderHabits(habits);
  if (openHabitId !== null) renderDetails(await api("GET", `/api/habits/${openHabitId}/stats`));
}

// Runs an action, then reloads everything; errors go to the alert line.
async function run(action) {
  try {
    await action();
    showError("");
    await refresh();
  } catch (err) {
    showError(err.message);
  }
}

function toggle(id, day, done) {
  run(() => api(done ? "DELETE" : "PUT", `/api/habits/${id}/checkins/${day}`));
}

async function openDetails(id) {
  try {
    renderDetails(await api("GET", `/api/habits/${id}/stats`));
    openHabitId = id;
    $("details").showModal();
  } catch (err) {
    showError(err.message);
  }
}

$("add-form").onsubmit = (e) => {
  e.preventDefault();
  run(async () => {
    await api("POST", "/api/habits", { name: $("add-name").value, color: $("add-color").value });
    $("add-name").value = "";
  });
};

$("edit-form").onsubmit = (e) => {
  e.preventDefault();
  run(() => api("PUT", `/api/habits/${openHabitId}`, { name: $("edit-name").value, color: $("edit-color").value }));
};

$("d-delete").onclick = () => {
  if (!confirm(`Видалити звичку «${$("d-name").textContent}» разом з усією історією?`)) return;
  const id = openHabitId;
  openHabitId = null;
  $("details").close();
  run(() => api("DELETE", `/api/habits/${id}`));
};

$("d-close").onclick = () => $("details").close();
$("details").addEventListener("close", () => { openHabitId = null; });

run(() => {});
