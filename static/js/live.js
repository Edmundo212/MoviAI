const $ = (id) => document.getElementById(id);
const PALETTE = ["#0aa5ff", "#16a34a", "#f59e0b", "#c026d3", "#ef4444", "#06b6d4"];
let chart = null;
let lastFrames = -1;
let streaming = false;
let lastTimelineLen = -1;

const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

// Video fluido: stream MJPEG del servidor (~15 fps). Si se corta, se reconecta solo.
function startStream() {
  if (streaming) return;
  streaming = true;
  const img = $("live-img");
  img.onload = () => {
    $("waiting").hidden = true;
    $("hud").hidden = false;
  };
  img.onerror = () => {
    streaming = false;
    setTimeout(() => window.SESSION_ACTIVE && startStream(), 2000);
  };
  img.src = `/live/${window.SESSION_ID}/stream.mjpg?v=${Date.now()}`;
}

function stopStream(d) {
  window.SESSION_ACTIVE = false;
  streaming = false;
  $("hud").hidden = true;
  if (d.imagen) $("live-img").src = `${window.STATIC_URL}${d.imagen}?v=${Date.now()}`;  // último frame analizado
}

async function poll() {
  let d;
  try {
    d = await (await fetch(`/api/live/${window.SESSION_ID}`)).json();
  } catch (e) {
    return setTimeout(poll, 3000);
  }
  render(d);
  if (d.estado === "starting" || d.estado === "live") setTimeout(poll, 1000);
}

function render(d) {
  const live = d.estado === "live" || d.estado === "starting";
  $("state").textContent = tState(d.estado);
  $("state").className = `badge ${d.estado}`;
  $("live-dot").classList.toggle("off", !live);
  $("stop").hidden = !live;
  $("meta").textContent = live ? t("{l} remaining", { l: fmt(d.restante ?? 0) }) : "";
  $("err").hidden = !d.error;
  if (d.error) $("err").textContent = t("Connection problem with the camera. Retrying…");

  if (live && d.stream) {
    window.SESSION_ACTIVE = true;
    startStream();
  } else if (!live) {
    stopStream(d);
    if (d.imagen) $("waiting").hidden = true;
  }

  $("k-next").textContent = !live ? "—" : d.proximo_analisis == null || d.proximo_analisis === 0
    ? t("updating…") : t("in {n} s", { n: d.proximo_analisis });
  $("k-next-sub").textContent = d.intervalo ? t("every {n} s", { n: Math.round(d.intervalo) }) : "";
  if (d.mediciones_guardadas != null) {
    $("k-db").textContent = d.mediciones_guardadas;
    $("k-db-sub").textContent = t("in the database");
  }
  if (d.plan) renderPlan(d.plan, d.promedio_por_acceso);
  if (d.promedio_total) {
    const tt = d.promedio_total;
    const veh = (tt.auto || 0) + (tt.moto || 0) + (tt.bus || 0) + (tt.camion || 0) + (tt.bicicleta || 0);
    $("k-veh").textContent = d.ultimo_frame ? vehiclesIn(d.ultimo_frame.totales) : veh.toFixed(1);
    $("k-veh-sub").textContent = t("average {v} · pedestrians {p}", { v: Math.round(veh), p: Math.round(tt.peaton || 0) });
  }
  const n = d.frames ?? d.frames_procesados;
  if (d.timeline && d.timeline.length && (d.timeline.length !== lastTimelineLen || n !== lastFrames)) {
    renderTimeline(d.timeline);
    lastTimelineLen = d.timeline.length;
    lastFrames = n;
  }
}

const vehiclesIn = (tt) => Object.entries(tt || {}).filter(([k]) => k !== "peaton").reduce((a, [, v]) => a + v, 0);

let sim = null;

function renderPlan(p, counts) {
  if (!p.ok) {
    if (!sim) $("plan").innerHTML = `<p class="muted">${t(p.mensaje)}</p>`;
    return;
  }
  if (!sim) {
    $("plan").classList.remove("muted");
    sim = new SignalSim($("plan"));
  }
  sim.update(p, counts);
  const dp = p.demora_persona;
  $("k-person").textContent = `${dp.smartflow} s`;
  $("k-person-sub").innerHTML = `${t("now: {x} s", { x: dp.fijo })} · <b class="${dp.mejora_pct >= 0 ? "good" : "bad"}">${dp.mejora_pct >= 0 ? "−" : "+"}${Math.abs(dp.mejora_pct)}%</b>`;
}

function renderTimeline(tl) {
  const approaches = Object.keys(tl[0].por_acceso);
  const labels = tl.map((x) => x.hora);
  const datasets = approaches.map((a, i) => ({
    label: tName(a), data: tl.map((x) => x.por_acceso[a]), borderColor: PALETTE[i % PALETTE.length],
    backgroundColor: PALETTE[i % PALETTE.length], tension: 0.3,
  }));
  datasets.push({ label: t("Pedestrians"), data: tl.map((x) => x.peatones), borderColor: "#ef4444", borderDash: [4, 4], tension: 0.3 });
  if (!chart) {
    chart = new Chart($("chart-timeline"), {
      type: "line", data: { labels, datasets },
      options: { animation: false, plugins: { legend: { position: "bottom" } }, scales: { y: { beginAtZero: true } } },
    });
  } else {
    chart.data.labels = labels;
    chart.data.datasets.forEach((ds, i) => (ds.data = datasets[i].data));
    chart.update();
  }
}

$("stop").onclick = async () => {
  $("stop").disabled = true;
  await fetch(`/api/live/${window.SESSION_ID}/stop`, { method: "POST" });
};

poll();
