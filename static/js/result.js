const $ = (id) => document.getElementById(id);
const CLASS_LABELS = { auto: "Cars", moto: "Motorcycles", bus: "Buses / vans", camion: "Trucks", bicicleta: "Bicycles", peaton: "Pedestrians" };
const CLASS_COLORS = { auto: "#0aa5ff", moto: "#ffc400", bus: "#16a34a", camion: "#c026d3", bicicleta: "#06b6d4", peaton: "#ef4444" };
const APPROACH_LABELS = { N: "North", S: "South", E: "East", O: "West" };

async function poll() {
  const res = await fetch(`/api/analisis/${window.ANALYSIS_ID}`);
  const doc = await res.json();
  if (doc.estado === "listo") return render(doc);
  if (doc.estado === "error") {
    $("progress-card").hidden = true;
    $("error-card").hidden = false;
    $("error-text").textContent = doc.error;
    return;
  }
  const total = doc.total_frames || 1, done = doc.frames_procesados || 0;
  $("bar").style.width = `${Math.round((100 * done) / total)}%`;
  $("status-text").textContent = doc.estado === "en cola" ? "Queued…" : "Analysing with Azure AI Vision…";
  $("progress-text").textContent = `Frame ${done} of ${total}`;
  setTimeout(poll, 2000);
}

function render(doc) {
  $("progress-card").hidden = true;
  $("results").hidden = false;
  const p = doc.plan;
  const det = Object.values(doc.promedio_total).reduce((a, b) => a + b, 0);
  $("k-det").textContent = det.toFixed(1);
  $("k-det-sub").textContent = `${doc.frames.length} frame(s) analysed`;

  if (!p.ok) {
    $("warn").hidden = false;
    $("warn").textContent = p.mensaje;
    ["k-person", "k-veh", "k-cycle"].forEach((k) => ($(k).textContent = "—"));
  } else {
    kpi("k-person", p.demora_persona);
    kpi("k-veh", p.demora_vehiculo);
    $("k-cycle").textContent = `${p.ciclo_recomendado} s`;
    $("k-cycle-sub").textContent = `current: ${p.ciclo_actual} s`;
    if (p.sobresaturado) {
      $("warn").hidden = false;
      $("warn").textContent = `Intersection is near saturation (Y = ${p.Y}). Signal timing alone cannot solve it — consider bus lanes or demand management.`;
    }
    renderSignals(p);
    renderDetails(p);
  }
  renderApproachChart(doc.promedio_por_acceso);
  renderFrames(doc.frames);
}

function kpi(id, d) {
  $(id).textContent = `${d.smartflow} s`;
  const sign = d.mejora_pct >= 0 ? "−" : "+";
  $(`${id}-sub`).innerHTML = `fixed: ${d.fijo} s · <b class="${d.mejora_pct >= 0 ? "good" : "bad"}">${sign}${Math.abs(d.mejora_pct)}%</b>`;
}

function renderSignals(p) {
  const phases = Object.keys(p.verde_recomendado);
  $("signals").innerHTML = phases.map((ph) => `
    <div class="signal">
      <div class="lights"><i class="r"></i><i class="y"></i><i class="g on"></i></div>
      <div><b>${ph}</b><br>Green: <s>${p.verde_actual[ph]} s</s> → <b class="good">${p.verde_recomendado[ph]} s</b>
      <br><small>critical approach: ${APPROACH_LABELS[p.acceso_critico[ph]] || p.acceso_critico[ph]}</small></div>
    </div>`).join("");
  new Chart($("chart-green"), {
    type: "bar",
    data: {
      labels: phases,
      datasets: [
        { label: "Fixed-time green (s)", data: phases.map((ph) => p.verde_actual[ph]), backgroundColor: "#94a3b8" },
        { label: "SmartFlow green (s)", data: phases.map((ph) => p.verde_recomendado[ph]), backgroundColor: "#16a34a" },
      ],
    },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { beginAtZero: true, title: { display: true, text: "seconds" } } } },
  });
}

function renderApproachChart(byApproach) {
  const approaches = Object.keys(byApproach);
  const classes = Object.keys(CLASS_LABELS);
  new Chart($("chart-approach"), {
    type: "bar",
    data: {
      labels: approaches.map((a) => APPROACH_LABELS[a] || a),
      datasets: classes.map((c) => ({
        label: CLASS_LABELS[c], backgroundColor: CLASS_COLORS[c],
        data: approaches.map((a) => byApproach[a][c] || 0),
      })),
    },
    options: { plugins: { legend: { position: "bottom" } }, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } },
  });
}

function renderFrames(frames) {
  const slider = $("frame-slider");
  slider.max = frames.length - 1;
  slider.hidden = frames.length < 2;
  const show = (i) => {
    const f = frames[i];
    $("frame-img").src = window.STATIC_URL + f.imagen;
    $("frame-label").textContent = `t = ${f.segundo} s · ${f.detecciones} detections`;
  };
  slider.oninput = () => show(+slider.value);
  show(0);
}

function renderDetails(p) {
  const approaches = Object.keys(p.flujos_pcu_h);
  const phases = Object.keys(p.y_fase);
  $("details").innerHTML = `
    <tr><th>Approach</th>${approaches.map((a) => `<th>${APPROACH_LABELS[a] || a}</th>`).join("")}</tr>
    <tr><td>Flow (PCU/h)</td>${approaches.map((a) => `<td>${p.flujos_pcu_h[a]}</td>`).join("")}</tr>
    <tr><td>Flow (people/h)</td>${approaches.map((a) => `<td>${p.flujos_personas_h[a]}</td>`).join("")}</tr>
    <tr><th>Phase</th>${phases.map((ph) => `<th>${ph}</th>`).join("")}</tr>
    <tr><td>Flow ratio y</td>${phases.map((ph) => `<td>${p.y_fase[ph]}</td>`).join("")}</tr>
    <tr><td colspan="99">Y = ${p.Y} · Lost time L = ${p.parametros.lost_time_per_phase * phases.length} s ·
      Pedestrian min. green = ${p.verde_minimo_peatonal} s · Mode: ${p.parametros.mode === "personas" ? "people-first" : "vehicle-based"} ·
      Lanes/approach = ${p.parametros.lanes}</td></tr>`;
}

poll();
