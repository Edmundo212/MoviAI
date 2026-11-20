"""Cálculo de tiempos de semáforo con el método de Webster y estimación de demoras.

Fórmulas:
    Ciclo óptimo      C0 = (1.5·L + 5) / (1 − Y)
    Verde efectivo    g_i = (y_i / Y) · (C0 − L)
    Demora de Webster d = C(1−λ)² / [2(1−λx)] + x² / [2q(1−x)]
donde L = tiempo perdido total, y_i = flujo/saturación de la fase crítica, Y = Σ y_i,
λ = g/C, x = grado de saturación, q = flujo (veh/s).
"""
from dataclasses import dataclass, asdict


@dataclass
class SignalParams:
    current_cycle: float = 90.0          # ciclo actual del semáforo de tiempo fijo (s)
    lanes: int = 2                       # carriles por acceso
    saturation_per_lane: float = 1800.0  # flujo de saturación (PCU/h/carril)
    lost_time_per_phase: float = 4.0     # ámbar + todo rojo perdido por fase (s)
    min_cycle: float = 40.0
    max_cycle: float = 120.0
    crossing_width: float = 12.0         # ancho de cruce peatonal (m)
    pedestrian_speed: float = 1.2        # velocidad peatonal de diseño (m/s)
    mode: str = "personas"               # "personas" (prioriza transporte público) o "pcu"

    @classmethod
    def from_form(cls, form) -> "SignalParams":
        p = cls()
        for field, typ in (("current_cycle", float), ("lanes", int), ("crossing_width", float)):
            if form.get(field):
                setattr(p, field, max(typ(form.get(field)), 1))
        if form.get("mode") in ("personas", "pcu"):
            p.mode = form.get("mode")
        return p


def _webster_delay(cycle: float, green: float, q_vps: float, s_vps: float) -> float:
    """Demora promedio por vehículo (s). q y s en vehículos por segundo."""
    if q_vps <= 0:
        return 0.0
    lam = green / cycle
    x = min(q_vps / (lam * s_vps), 0.95)         # limitamos para evitar división por cero
    uniform = cycle * (1 - lam) ** 2 / (2 * (1 - lam * x))
    random_ = x ** 2 / (2 * q_vps * (1 - x))
    return uniform + random_


def compute_plan(approach_stats: dict, phases: dict, p: SignalParams, pedestrians: float) -> dict:
    """approach_stats: {acceso: {"pcu": promedio por frame, "personas": promedio por frame}}"""
    capacity = p.saturation_per_lane * p.lanes            # PCU/h por acceso
    turnover = 3600.0 / p.current_cycle                   # la cola observada se renueva cada ciclo

    flows = {a: s["pcu"] * turnover for a, s in approach_stats.items()}          # PCU/h
    people_flows = {a: s["personas"] * turnover for a, s in approach_stats.items()}  # personas/h

    phase_y, phase_w, critical = {}, {}, {}
    for ph, approaches in phases.items():
        crit = max(approaches, key=lambda a: flows.get(a, 0))
        critical[ph] = crit
        phase_y[ph] = flows.get(crit, 0) / capacity
        # peso para repartir el verde: PCU o personas en el acceso crítico
        phase_w[ph] = (max(people_flows.get(a, 0) for a in approaches) if p.mode == "personas"
                       else phase_y[ph])

    Y = sum(phase_y.values())
    L = p.lost_time_per_phase * len(phases)
    if Y <= 0:
        return {"ok": False, "mensaje": "No vehicles detected yet."}

    oversaturated = Y >= 0.9
    cycle = (1.5 * L + 5) / (1 - min(Y, 0.9))
    cycle = max(p.min_cycle, min(p.max_cycle, cycle))

    # verde mínimo: si hay peatones, debe alcanzar para cruzar la vía
    min_green = 7.0 + (p.crossing_width / p.pedestrian_speed if pedestrians > 0 else 0)
    if min_green * len(phases) > cycle - L:
        cycle = min(p.max_cycle, min_green * len(phases) + L)

    total_green = cycle - L
    total_w = sum(phase_w.values()) or 1
    greens = {ph: total_green * phase_w[ph] / total_w for ph in phases}
    # aplica verde mínimo y reajusta el resto proporcionalmente
    short = {ph for ph, g in greens.items() if g < min_green}
    if short and len(short) < len(phases):
        remaining = total_green - min_green * len(short)
        rest_w = sum(phase_w[ph] for ph in phases if ph not in short) or 1
        greens = {ph: (min_green if ph in short else remaining * phase_w[ph] / rest_w) for ph in phases}
    elif short:
        greens = {ph: total_green / len(phases) for ph in phases}

    # --- comparación: tiempo fijo (verde igual) vs SmartFlow ---
    fixed_green = (p.current_cycle - L) / len(phases)
    s_vps = capacity / 3600
    approach_phase = {a: ph for ph, aps in phases.items() for a in aps}

    def avg_delay(cyc, green_by_phase, weights):
        num = den = 0.0
        for a, q in flows.items():
            ph = approach_phase.get(a)
            if ph is None or q <= 0:
                continue
            d = _webster_delay(cyc, green_by_phase[ph], q / 3600, s_vps)
            num += d * weights[a]
            den += weights[a]
        return num / den if den else 0.0

    fixed = {ph: fixed_green for ph in phases}
    delay_fixed_veh = avg_delay(p.current_cycle, fixed, flows)
    delay_smart_veh = avg_delay(cycle, greens, flows)
    delay_fixed_per = avg_delay(p.current_cycle, fixed, people_flows)
    delay_smart_per = avg_delay(cycle, greens, people_flows)

    def pct(before, after):
        return round(100 * (before - after) / before, 1) if before > 0 else 0.0

    return {
        "ok": True,
        "parametros": asdict(p),
        "flujos_pcu_h": {a: round(v) for a, v in flows.items()},
        "flujos_personas_h": {a: round(v) for a, v in people_flows.items()},
        "acceso_critico": critical,
        "y_fase": {ph: round(v, 3) for ph, v in phase_y.items()},
        "Y": round(Y, 3),
        "sobresaturado": oversaturated,
        "ciclo_actual": p.current_cycle,
        "verde_actual": {ph: round(fixed_green, 1) for ph in phases},
        "ciclo_recomendado": round(cycle, 1),
        "verde_recomendado": {ph: round(g, 1) for ph, g in greens.items()},
        "verde_minimo_peatonal": round(min_green, 1),
        "demora_vehiculo": {"fijo": round(delay_fixed_veh, 1), "smartflow": round(delay_smart_veh, 1),
                            "mejora_pct": pct(delay_fixed_veh, delay_smart_veh)},
        "demora_persona": {"fijo": round(delay_fixed_per, 1), "smartflow": round(delay_smart_per, 1),
                           "mejora_pct": pct(delay_fixed_per, delay_smart_per)},
    }
