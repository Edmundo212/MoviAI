const $ = (id) => document.getElementById(id);
const PALETTE = ["#0aa5ff", "#16a34a", "#f59e0b", "#c026d3", "#ef4444", "#06b6d4"];
let chart = null;
let lastFrames = -1;

const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

async function poll() {
  let d;
  try {
    d = await (await fetch(`/api/live/${window.SESSION_ID}`)).json();
  } catch (e) {
    return setTimeout(poll, 3000);
  }
  render(d);
  if (d.estado === "starting" || d.estado === "live") setTimeout(poll, 2000);
}

function render(d) {
  const live = d.estado === "live" || d.estado === "starting";
  $("state").textContent = d.estado;
  $("state").className = `badge ${d.estado}`;
  $("live-dot").classList.toggle("off", !live);
  $("stop").hidden = !live;
  $("meta").textContent = live
    ? `${d.frames ?? 0} frames · ${d.llamadas_api ?? 0} API calls · ${fmt(d.restante ?? 0)} left`
    : `${d.frames_procesados ?? d.frames ?? 0} frames · ${d.llamadas_api ?? 0} API calls`;
  $("err").hidden = !d.error;
  if (d.error) $("err").textContent = `Camera / API issue: ${d.error}`;

  if (d.imagen) {
    const n = d.frames ?? d.frames_procesados;
    if (n !== lastFrames) {
      $("live-img").src = `${window.STATIC_URL}${d.imagen}?v=${Date.now()}`;
      lastFrames = n;
    }
    $("waiting").hidden = true;
  }
  if (d.plan) renderPlan(d.plan);
  if (d.promedio_total) {
    const t = d.promedio_total;
    const veh = (t.auto || 0) + (t.moto || 0) + (t.bus || 0) + (t.camion || 0) + (t.bicicleta || 0);
    $("k-veh").textContent = d.ultimo_frame ? vehiclesIn(d.ultimo_frame.totales) : veh.toFixed(1);
    $("k-veh-sub").textContent = `avg ${veh.toFixed(1)} · pedestrians ${(t.peaton || 0).toFixed(1)}`;
  }
  if (d.timeline && d.timeline.length) renderTimeline(d.timeline);
}

const vehiclesIn = (t) => Object.entries(t || {}).filter(([k]) => k !== "peaton").reduce((a, [, v]) => a + v, 0);

function renderPlan(p) {
  if (!p.ok) {
    $("plan").innerHTML = `<p class="muted">${p.mensaje}</p>`;
    return;
  }
  const phases = Object.keys(p.verde_recomendado);
  const cycle = p.ciclo_recomendado;
  $("plan").innerHTML = `
    <div class="cycle-bar">${phases.map((ph, i) => `
      <div style="flex:${p.verde_recomendado[ph]};background:${PALETTE[i % PALETTE.length]}" title="${ph}">${ph}<br><b>${p.verde_recomendado[ph]} s</b></div>`).join("")}
      <div class="lost" style="flex:${cycle - phases.reduce((a, ph) => a + p.verde_recomendado[ph], 0)}">amber</div>
    </div>
    <p>Cycle <b>${cycle} s</b> <span class="muted">(fixed: ${p.ciclo_actual} s, ${phases.map((ph) => p.verde_actual[ph] + " s").join(" / ")} green)</span></p>
    ${p.sobresaturado ? `<p class="alert">Near saturation (Y = ${p.Y}).</p>` : ""}`;
  const dp = p.demora_persona;
  $("k-person").textContent = `${dp.smartflow} s`;
  $("k-person-sub").innerHTML = `fixed ${dp.fijo} s · <b class="${dp.mejora_pct >= 0 ? "good" : "bad"}">${dp.mejora_pct >= 0 ? "−" : "+"}${Math.abs(dp.mejora_pct)}%</b>`;
}

function renderTimeline(tl) {
  const approaches = Object.keys(tl[0].por_acceso);
  const labels = tl.map((x) => x.hora);
  const datasets = approaches.map((a, i) => ({
    label: a, data: tl.map((x) => x.por_acceso[a]), borderColor: PALETTE[i % PALETTE.length],
    backgroundColor: PALETTE[i % PALETTE.length], tension: 0.3,
  }));
  datasets.push({ label: "Pedestrians", data: tl.map((x) => x.peatones), borderColor: "#ef4444", borderDash: [4, 4], tension: 0.3 });
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
