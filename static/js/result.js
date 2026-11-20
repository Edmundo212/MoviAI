const $ = (id) => document.getElementById(id);
const CLASS_LABELS = { auto: t("Cars"), moto: t("Motorcycles"), bus: t("Buses"), camion: t("Trucks"), bicicleta: t("Bicycles"), peaton: t("Pedestrians") };
const CLASS_COLORS = { auto: "#0aa5ff", moto: "#ffc400", bus: "#16a34a", camion: "#c026d3", bicicleta: "#06b6d4", peaton: "#ef4444" };

async function poll() {
  const res = await fetch(`/api/analisis/${window.ANALYSIS_ID}`);
  const doc = await res.json();
  if (doc.estado === "listo") return render(doc);
  if (doc.estado === "error") {
    $("progress-card").hidden = true;
    $("error-card").hidden = false;
    $("error-text").textContent = t("The file could not be analysed. Please try another video or photo.");
    return;
  }
  const total = doc.total_frames || 1, done = doc.frames_procesados || 0;
  const pct = Math.round((100 * done) / total);
  $("bar").style.width = `${pct}%`;
  $("status-text").textContent = doc.estado === "en cola" ? t("Queued…") : t("Analysing…");
  $("progress-text").textContent = t("{p}% complete", { p: pct });
  setTimeout(poll, 2000);
}

function render(doc) {
  $("progress-card").hidden = true;
  $("results").hidden = false;
  const p = doc.plan;
  const det = Object.values(doc.promedio_total).reduce((a, b) => a + b, 0);
  $("k-det").textContent = Math.round(det);
  $("k-det-sub").textContent = t("on average");

  if (!p.ok) {
    $("warn").hidden = false;
    $("warn").textContent = t(p.mensaje);
    ["k-person", "k-veh", "k-cycle"].forEach((k) => ($(k).textContent = "—"));
  } else {
    kpi("k-person", p.demora_persona);
    kpi("k-veh", p.demora_vehiculo);
    $("k-cycle").textContent = `${p.ciclo_recomendado} s`;
    $("k-cycle-sub").textContent = t("current: {n} s", { n: p.ciclo_actual });
    if (p.sobresaturado) {
      $("warn").hidden = false;
      $("warn").textContent = t("This intersection is very congested. Better timing helps, but bus lanes or other measures may also be needed.");
    }
    new SignalSim($("signals")).update(p, doc.promedio_por_acceso);
    renderGreenChart(p);
    renderDetails(p);
  }
  renderApproachChart(doc.promedio_por_acceso);
  renderFrames(doc.frames);
}

function kpi(id, d) {
  $(id).textContent = `${d.smartflow} s`;
  const sign = d.mejora_pct >= 0 ? "−" : "+";
  $(`${id}-sub`).innerHTML = `${t("now: {x} s", { x: d.fijo })} · <b class="${d.mejora_pct >= 0 ? "good" : "bad"}">${sign}${Math.abs(d.mejora_pct)}%</b>`;
}

function renderGreenChart(p) {
  const phases = Object.keys(p.verde_recomendado);
  new Chart($("chart-green"), {
    type: "bar",
    data: {
      labels: phases.map(tName),
      datasets: [
        { label: t("Current (s)"), data: phases.map((ph) => p.verde_actual[ph]), backgroundColor: "#94a3b8" },
        { label: t("SmartFlow (s)"), data: phases.map((ph) => p.verde_recomendado[ph]), backgroundColor: "#16a34a" },
      ],
    },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { beginAtZero: true, title: { display: true, text: t("seconds") } } } },
  });
}

function renderApproachChart(byApproach) {
  const approaches = Object.keys(byApproach);
  const classes = Object.keys(CLASS_LABELS);
  new Chart($("chart-approach"), {
    type: "bar",
    data: {
      labels: approaches.map(tName),
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
    $("frame-label").textContent = frames.length > 1
      ? t("Second {s} · {n} detected", { s: Math.round(f.segundo), n: f.detecciones })
      : t("{n} detected", { n: f.detecciones });
  };
  slider.oninput = () => show(+slider.value);
  show(0);
  // Reproduce las imágenes analizadas como un video
  const play = $("play");
  play.hidden = frames.length < 2;
  frames.forEach((f) => (new Image().src = window.STATIC_URL + f.imagen));   // precarga
  let timer = null;
  play.textContent = `▶ ${t("Play")}`;
  play.onclick = () => {
    if (timer) {
      clearInterval(timer);
      timer = null;
      play.textContent = `▶ ${t("Play")}`;
      return;
    }
    play.textContent = `❚❚ ${t("Pause")}`;
    timer = setInterval(() => {
      slider.value = (+slider.value + 1) % frames.length;
      show(+slider.value);
    }, 500);
  };
}

function renderDetails(p) {
  const approaches = Object.keys(p.flujos_pcu_h);
  $("details").innerHTML = `
    <tr><th>${t("Street")}</th>${approaches.map((a) => `<th>${tName(a)}</th>`).join("")}</tr>
    <tr><td>${t("Vehicles per hour")}</td>${approaches.map((a) => `<td>${Math.round(p.flujos_pcu_h[a])}</td>`).join("")}</tr>
    <tr><td>${t("People per hour")}</td>${approaches.map((a) => `<td>${Math.round(p.flujos_personas_h[a])}</td>`).join("")}</tr>
    <tr><td colspan="99">${t("Minimum green for pedestrians")}: ${p.verde_minimo_peatonal} s ·
      ${t("Priority")}: ${p.parametros.mode === "personas" ? t("People first") : t("Vehicles first")} ·
      ${t("Lanes per street")}: ${p.parametros.lanes}</td></tr>`;
}

poll();
