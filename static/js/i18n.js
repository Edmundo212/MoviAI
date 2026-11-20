/* SmartFlow i18n: English (default) <-> Spanish.
 * - Static text in templates is translated by exact match (ES dictionary below).
 * - Status/type values use data-state="value".
 * - Page scripts use t("English text", {vars}), tState(value) and tName(street/phase).
 * The chosen language is saved in localStorage; the toggle reloads so charts are redrawn. */
(function () {
  const ES = {
    // layout
    "Smarter traffic lights with artificial intelligence": "Semáforos más inteligentes con inteligencia artificial",
    "SmartFlow · WFEO Hackathon 2027 · Challenge 3: Smart, Digital and Data-Driven Transport":
      "SmartFlow · Hackathon WFEO 2027 · Reto 3: Transporte inteligente, digital y basado en datos",
    "Powered by Azure AI Vision and YOLOX": "Con tecnología de Azure AI Vision y YOLOX",
    "Home": "Inicio",

    // index
    "Make every green light count.": "Que cada luz verde cuente.",
    "SmartFlow uses artificial intelligence on existing traffic cameras to count vehicles and pedestrians and recommend better traffic light timings, putting people first, not just cars.":
      "SmartFlow usa inteligencia artificial en las cámaras de tránsito existentes para contar vehículos y peatones y recomendar mejores tiempos de semáforo, priorizando a las personas y no solo a los autos.",
    "Live traffic camera": "Cámara de tránsito en vivo",
    "Camera": "Cámara",
    "Other camera…": "Otra cámara…",
    "Camera link": "Enlace de la cámara",
    "Name": "Nombre",
    "My intersection": "Mi intersección",
    "Update every (s)": "Actualizar cada (s)",
    "Duration (min)": "Duración (min)",
    "Start live analysis": "Iniciar análisis en vivo",
    "Public cameras courtesy of Caltrans (California).": "Cámaras públicas cortesía de Caltrans (California).",
    "Analyse a video or photo": "Analizar un video o una foto",
    "Video or photo of the intersection": "Video o foto de la intersección",
    "Intersection name": "Nombre de la intersección",
    "e.g. Av. Javier Prado / Av. Arequipa": "ej. Av. Javier Prado / Av. Arequipa",
    "Analyse": "Analizar",
    "For privacy, the file is deleted after the analysis and faces are blurred.":
      "Por privacidad, el archivo se borra después del análisis y los rostros se difuminan.",
    "Current cycle (s)": "Ciclo actual (s)",
    "Lanes per street": "Carriles por calle",
    "Crosswalk width (m)": "Ancho del cruce peatonal (m)",
    "Priority": "Prioridad",
    "People first": "Primero las personas",
    "Vehicles first": "Primero los vehículos",
    "Recent analyses": "Análisis recientes",
    "Intersection": "Intersección",
    "Type": "Tipo",
    "Status": "Estado",
    "Time saved": "Tiempo ahorrado",
    "per person": "por persona",
    "No analyses yet. Start a live camera or upload a video.": "Aún no hay análisis. Inicia una cámara en vivo o sube un video.",
    "How it works": "Cómo funciona",
    "Capture": "Captura",
    "Detect": "Detección",
    "Count": "Conteo",
    "Optimise": "Optimización",
    "A traffic camera records the intersection.": "Una cámara de tránsito graba la intersección.",
    "Artificial intelligence recognises cars, motorcycles, buses, trucks, bicycles and pedestrians.":
      "La inteligencia artificial reconoce autos, motos, buses, camiones, bicicletas y peatones.",
    "Vehicles and people are counted on each street.": "Se cuentan los vehículos y las personas en cada calle.",
    "SmartFlow recommends how long each green light should last, with safe crossing time for pedestrians.":
      "SmartFlow recomienda cuánto debe durar cada luz verde, con tiempo seguro de cruce para los peatones.",
    "Starting…": "Iniciando…",
    "Please select an image or video.": "Selecciona una imagen o un video.",
    "This file type is not supported.": "Este tipo de archivo no es compatible.",
    "The camera URL must start with http://, https:// or rtsp://": "El enlace de la cámara debe empezar con http://, https:// o rtsp://",
    "Private or internal network addresses are not allowed.": "Ese enlace no está permitido.",

    // live
    "← Home": "← Inicio",
    "Stop": "Detener",
    "LIVE": "EN VIVO",
    "Live camera": "Cámara en vivo",
    "Connecting to the camera…": "Conectando con la cámara…",
    "Car": "Auto", "Motorcycle": "Moto", "Bus": "Bus", "Truck": "Camión", "Bicycle": "Bicicleta", "Pedestrian": "Peatón",
    "Recommended signal plan": "Plan de semáforo recomendado",
    "Waiting for data…": "Esperando datos…",
    "Wait per person": "Espera por persona",
    "Wait per vehicle": "Espera por vehículo",
    "Vehicles on screen": "Vehículos en pantalla",
    "Next update": "Próxima actualización",
    "Records saved": "Registros guardados",
    "Vehicles per approach over time": "Vehículos por calle en el tiempo",
    "{l} remaining": "quedan {l}",
    "Connection problem with the camera. Retrying…": "Problema de conexión con la cámara. Reintentando…",
    "updating…": "actualizando…",
    "in {n} s": "en {n} s",
    "every {n} s": "cada {n} s",
    "in the database": "en la base de datos",
    "average {v} · pedestrians {p}": "promedio {v} · peatones {p}",
    "amber": "ámbar",
    "Full cycle": "Ciclo completo",
    "Very heavy traffic right now.": "Tráfico muy intenso en este momento.",
    "now: {x} s": "ahora: {x} s",
    "Pedestrians": "Peatones",
    "No vehicles detected yet.": "Aún no se detectan vehículos.",
    "Traffic lights right now": "Semáforos en este momento",
    "Recommended traffic lights": "Semáforos recomendados",
    "Heavy traffic": "Tráfico alto",
    "Moderate traffic": "Tráfico moderado",
    "Light traffic": "Tráfico bajo",
    "{n} vehicles": "{n} vehículos",
    "Green {g} s per cycle (current {f} s)": "Verde {g} s por ciclo (actual {f} s)",
    "Each street keeps the minimum green so pedestrians can cross safely.": "Cada calle mantiene el verde mínimo para que los peatones crucen seguros.",
    "Traffic is balanced, so both streets get the same green time.": "El tráfico está equilibrado: ambas calles reciben el mismo tiempo en verde.",
    "{s} has more traffic, so it gets more green time.": "{s} tiene más tráfico, por eso recibe más tiempo en verde.",
    "Full cycle {c} s (current {f} s)": "Ciclo completo {c} s (actual {f} s)",
    "Green · {n} s left": "Verde · quedan {n} s",
    "Amber · {n} s": "Ámbar · {n} s",
    "Red · green in {n} s": "Rojo · verde en {n} s",

    // result
    "← New analysis": "← Nuevo análisis",
    "Processing…": "Procesando…",
    "Preparing the analysis…": "Preparando el análisis…",
    "Recommended cycle": "Ciclo recomendado",
    "Objects detected": "Objetos detectados",
    "Green time: current vs SmartFlow": "Tiempo en verde: actual vs SmartFlow",
    "Traffic by street": "Tráfico por calle",
    "Detections": "Detecciones",
    "Intersection photo": "Foto de la intersección",
    "More details": "Más detalles",
    "Something went wrong": "Algo salió mal",
    "The file could not be analysed. Please try another video or photo.":
      "No se pudo analizar el archivo. Prueba con otro video o foto.",
    "Play": "Reproducir", "Pause": "Pausa",
    "Queued…": "En cola…",
    "Analysing…": "Analizando…",
    "{p}% complete": "{p}% completado",
    "on average": "en promedio",
    "current: {n} s": "actual: {n} s",
    "This intersection is very congested. Better timing helps, but bus lanes or other measures may also be needed.":
      "Esta intersección está muy congestionada. Mejores tiempos ayudan, pero también podrían necesitarse carriles de bus u otras medidas.",
    "Green": "Verde",
    "Current (s)": "Actual (s)",
    "SmartFlow (s)": "SmartFlow (s)",
    "seconds": "segundos",
    "Second {s} · {n} detected": "Segundo {s} · {n} detectados",
    "{n} detected": "{n} detectados",
    "Street": "Calle",
    "Vehicles per hour": "Vehículos por hora",
    "People per hour": "Personas por hora",
    "Minimum green for pedestrians": "Verde mínimo para peatones",
    "Cars": "Autos", "Motorcycles": "Motos", "Buses": "Buses", "Trucks": "Camiones", "Bicycles": "Bicicletas",
  };

  // Nombres de calles / fases que vienen de los datos (en español o en inglés)
  const NAMES = {
    N: ["North", "Norte"], S: ["South", "Sur"], E: ["East", "Este"], O: ["West", "Oeste"],
    "Norte-Sur": ["North-South", "Norte-Sur"], "Este-Oeste": ["East-West", "Este-Oeste"],
    "North-South": ["North-South", "Norte-Sur"], "East-West": ["East-West", "Este-Oeste"],
  };

  const STATES = {
    en: { listo: "done", procesando: "processing", "en cola": "queued", error: "error", "en vivo": "live",
          live: "live", starting: "starting", finished: "finished", imagen: "photo", video: "video" },
    es: { listo: "listo", procesando: "procesando", "en cola": "en cola", error: "error", "en vivo": "en vivo",
          live: "en vivo", starting: "iniciando", finished: "finalizado", imagen: "foto", video: "video" },
  };

  const lang = localStorage.getItem("sf-lang") === "es" ? "es" : "en";
  const fill = (s, vars) => String(s).replace(/\{(\w+)\}/g, (m, k) => (vars && vars[k] != null ? vars[k] : m));
  const norm = (s) => s.replace(/\s+/g, " ").trim();

  window.LANG = lang;
  window.t = (en, vars) => fill(lang === "es" && ES[en] ? ES[en] : en, vars);
  window.tState = (s) => STATES[lang][s] || s;
  window.tName = (s) => (NAMES[s] ? NAMES[s][lang === "es" ? 1 : 0] : s);
  document.documentElement.lang = lang;

  function translate(root) {
    root.querySelectorAll("[data-state]").forEach((el) => (el.textContent = window.tState(el.dataset.state)));
    if (lang !== "es") return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.parentNode.closest("script,style") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((n) => {
      const k = norm(n.nodeValue);
      if (k && ES[k]) n.nodeValue = n.nodeValue.replace(/\S[\s\S]*\S|\S/, ES[k]);
    });
    root.querySelectorAll("[placeholder],[title],[alt]").forEach((el) => {
      ["placeholder", "title", "alt"].forEach((a) => {
        const v = el.getAttribute(a);
        if (v && ES[norm(v)]) el.setAttribute(a, ES[norm(v)]);
      });
    });
    const [page, site] = document.title.split(" · ");
    if (site && ES[page]) document.title = `${ES[page]} · ${site}`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    translate(document.body);
    const btn = document.getElementById("lang-toggle");
    if (btn) {
      btn.querySelectorAll("[data-lang]").forEach((s) => s.classList.toggle("on", s.dataset.lang === lang));
      btn.title = lang === "es" ? "Switch to English" : "Cambiar a español";
      btn.onclick = () => {
        localStorage.setItem("sf-lang", lang === "es" ? "en" : "es");
        location.reload();
      };
    }
  });
})();
