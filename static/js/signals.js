/* Semáforos animados: muestra en tiempo real de qué color debería estar cada semáforo
 * según el plan recomendado (verde de cada fase + ámbar + todo rojo), con cuenta regresiva.
 * Uso: const sim = new SignalSim(elemento); sim.update(plan, promedioPorAcceso); */
(function () {
  const AMBER = 3;          // s de ámbar por fase
  const VEHICLES = ["auto", "moto", "bus", "camion", "bicicleta"];

  class SignalSim {
    constructor(el) {
      this.el = el;
      this.plan = null;
      this.next = null;          // plan nuevo: se aplica al empezar el siguiente ciclo
      this.counts = {};
      this.cycleStart = Date.now() / 1000;
      this.timer = setInterval(() => this.tick(), 250);
    }

    update(plan, counts) {
      if (!plan || !plan.ok) return;
      this.counts = counts || {};
      if (!this.plan) {
        this.plan = plan;
        this.build();
      } else {
        this.next = plan;
      }
    }

    // fases con su verde, ámbar y todo rojo, en orden
    segments(plan) {
      const lost = (plan.parametros && plan.parametros.lost_time_per_phase) || 4;
      return Object.keys(plan.verde_recomendado).map((ph) => ({
        ph, green: plan.verde_recomendado[ph], amber: Math.min(AMBER, lost), red: Math.max(lost - AMBER, 0),
      }));
    }

    vehiclesOn(ph) {
      const a = this.plan.acceso_critico && this.plan.acceso_critico[ph];
      const c = this.counts[a] || {};
      return Math.round(VEHICLES.reduce((s, k) => s + (c[k] || 0), 0));
    }

    level(ph) {
      const n = this.vehiclesOn(ph);
      if (n >= 10) return ["high", t("Heavy traffic")];
      if (n >= 4) return ["mid", t("Moderate traffic")];
      return ["low", t("Light traffic")];
    }

    build() {
      const segs = this.segments(this.plan);
      this.el.innerHTML = `
        <p class="tl-reason" data-role="reason"></p>
        <div class="tl-list">${segs.map((s, i) => `
          <div class="tl-card" data-i="${i}">
            <div class="tl"><i class="r"></i><i class="y"></i><i class="g"></i></div>
            <div class="tl-info">
              <b class="tl-name">${tName(s.ph)}</b>
              <span class="tl-level" data-role="level"></span>
              <span class="tl-state" data-role="state"></span>
              <small class="muted" data-role="green"></small>
            </div>
          </div>`).join("")}
        </div>
        <p class="muted tl-cycle" data-role="cycle"></p>`;
      this.refreshText();
      this.tick();
    }

    refreshText() {
      const p = this.plan;
      const segs = this.segments(p);
      segs.forEach((s, i) => {
        const card = this.el.querySelector(`.tl-card[data-i="${i}"]`);
        if (!card) return;
        const [cls, label] = this.level(s.ph);
        const n = this.vehiclesOn(s.ph);
        const lv = card.querySelector('[data-role="level"]');
        lv.className = `tl-level ${cls}`;
        lv.textContent = `${label} · ${t("{n} vehicles", { n })}`;
        card.querySelector('[data-role="green"]').textContent =
          t("Green {g} s per cycle (current {f} s)", { g: Math.round(s.green), f: Math.round(p.verde_actual[s.ph]) });
      });
      const busiest = segs.reduce((a, b) => (b.green > a.green ? b : a), segs[0]);
      const equal = segs.every((s) => Math.abs(s.green - busiest.green) < 1);
      this.el.querySelector('[data-role="reason"]').textContent = equal
        ? t("Traffic is balanced, so both streets get the same green time.")
        : t("{s} has more traffic, so it gets more green time.", { s: tName(busiest.ph) });
      this.el.querySelector('[data-role="cycle"]').textContent =
        t("Full cycle {c} s (current {f} s)", { c: Math.round(p.ciclo_recomendado), f: Math.round(p.ciclo_actual) });
    }

    tick() {
      if (!this.plan) return;
      const now = Date.now() / 1000;
      let segs = this.segments(this.plan);
      let cycle = segs.reduce((a, s) => a + s.green + s.amber + s.red, 0);
      if (now - this.cycleStart >= cycle) {
        this.cycleStart += cycle * Math.floor((now - this.cycleStart) / cycle);
        if (this.next) {                   // aplica el plan nuevo al empezar un ciclo
          const old = this.segments(this.plan).length;
          this.plan = this.next;
          this.next = null;
          if (this.segments(this.plan).length !== old) return this.build();
          this.refreshText();
          segs = this.segments(this.plan);
          cycle = segs.reduce((a, s) => a + s.green + s.amber + s.red, 0);
        }
      }
      const pos = now - this.cycleStart;

      // fase activa y su color
      let start = 0, active = -1, color = "r", left = 0;
      const starts = [];
      segs.forEach((s, i) => {
        starts.push(start);
        const g = start + s.green, y = g + s.amber, end = y + s.red;
        if (active < 0 && pos < end) {
          active = i;
          if (pos < g) { color = "g"; left = g - pos; }
          else if (pos < y) { color = "y"; left = y - pos; }
          else { color = "r"; left = end - pos; }
        }
        start = end;
      });

      segs.forEach((s, i) => {
        const card = this.el.querySelector(`.tl-card[data-i="${i}"]`);
        if (!card) return;
        const c = i === active ? color : "r";
        card.classList.toggle("on", i === active && c !== "r");
        ["r", "y", "g"].forEach((k) => card.querySelector(`.tl .${k}`).classList.toggle("lit", k === c));
        let wait;                                   // segundos hasta su próximo verde
        if (i === active && c !== "r") wait = Math.ceil(left);
        else wait = Math.ceil(((starts[i] - pos) % cycle + cycle) % cycle);
        const st = card.querySelector('[data-role="state"]');
        st.className = `tl-state ${c}`;
        st.textContent = c === "g" ? t("Green · {n} s left", { n: wait })
          : c === "y" ? t("Amber · {n} s", { n: wait })
          : t("Red · green in {n} s", { n: wait });
      });
    }
  }

  window.SignalSim = SignalSim;
})();
