"""SCI for AI (Consumer) for AI coding: the Green Software Foundation's carbon
intensity score, computed from your agent logs.

    SCI = (O + M) / R      O = E × I (operational), M = embodied, R = functional unit

Spec: GSF "Software Carbon Intensity for AI" (ratified; extends ISO/IEC 21031:2024),
https://github.com/Green-Software-Foundation/sci-ai/blob/main/SPEC.md
  * Consumer boundary: the Operation and Monitoring stage (API and inference,
    orchestration, monitoring, ...). Provider training is the Provider SCI, not this.
  * Functional units: "Per Token" for LLMs and "Per Workflow Execution" for
    agentic AI. A coding agent's workflow ends in a commit, so aimpg reports
    per AI-assisted commit and, the unit that matters, per working change
    (a commit still standing after 30 days).
  * Offsets, RECs, PPAs and other market-based measures may not reduce the
    score, so I is a location-based grid average.

E is aimpg's serving-energy range (full stack: accelerators, host, idle
machines, data-centre overhead). M is amortized hardware emissions per kWh
served, from Google's measured Scope 1+3 per prompt. Every number is a
low–high range because model sizes and data-centre locations aren't disclosed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from aimpg.energy import load_factors, total_wh
from aimpg.equivalence import load as load_equivalences

SPEC_URL = "https://github.com/Green-Software-Foundation/sci-ai/blob/main/SPEC.md"
# Google, arXiv 2508.15734, Table 2 (median Gemini Apps prompt, May 2025):
# Scope 1+3 (accelerators + host CPU & DRAM, amortized) 0.010 g per 0.24 Wh
# (comprehensive) and 0.007 g per 0.10 Wh (narrow method) → ~42–70 g per kWh served.
EMBODIED_G_PER_KWH = (40.0, 70.0)
EMBODIED_CITATION = ("Google, 'Measuring the environmental impact of delivering AI at Google scale' (arXiv 2508.15734), "
                     "Table 2: Scope 1+3 emissions 0.010 gCO2e per 0.24 Wh median prompt (≈42 g/kWh) and 0.007 g per "
                     "0.10 Wh with the narrower method (≈70 g/kWh)")
INCLUDED = ["model inference via API (accelerators, host CPU and memory, idle provisioned capacity, data-centre overhead)",
            "every model request the agents made, including sub-agents, tool loops and retries",
            "embodied (manufacturing) emissions of the serving hardware, amortized per kWh served"]
EXCLUDED = ["the developer's own computer and network (client side): not in the agents' logs",
            "provider training (that is the Provider SCI, reported by the model provider)",
            "orchestration, monitoring and storage outside the model API, where the provider doesn't disclose them",
            "offsets, RECs, PPAs and other market-based measures (excluded by the spec)"]


def compute(requests, n_commits: int, judged, *, grid: float, period: tuple[float, float]) -> dict:
    """requests: in-window model requests; judged: durable.Judged (or None)."""
    e = total_wh(requests)  # Wh
    tokens = sum(r.usage.ctx_len + r.usage.output for r in requests)
    lo_g = e.low / 1000 * (grid + EMBODIED_G_PER_KWH[0])
    hi_g = e.high / 1000 * (grid + EMBODIED_G_PER_KWH[1])

    def per(r: float | None) -> list[float] | None:
        return [round(lo_g / r, 6), round(hi_g / r, 6)] if r else None

    working = None
    if judged is not None and judged.durable:
        wh_lo = sum(c.get("wh_low", 0) for c in judged.judged)
        wh_hi = sum(c.get("wh_high", 0) for c in judged.judged)
        n = len(judged.durable)
        working = {"value_g": [round(wh_lo / 1000 * (grid + EMBODIED_G_PER_KWH[0]) / n, 3),
                               round(wh_hi / 1000 * (grid + EMBODIED_G_PER_KWH[1]) / n, 3)],
                   "working_changes": n, "judged_commits": len(judged.judged),
                   "note": "carbon of all judged AI-assisted commits (kept or not) divided by the ones still standing after 30 days"}
    first = judged.first_judgeable() if judged is not None else None
    return {
        "standard": "Software Carbon Intensity for AI (GSF), Consumer SCI",
        "specification": SPEC_URL,
        "tool": "aimpg",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "period": {"from": _day(period[0]), "to": _day(period[1])},
        "formula": "SCI = (O + M) / R, O = E × I",
        "boundary": {"persona": "consumer", "lifecycle_stage": "Operation and Monitoring",
                     "included": INCLUDED, "excluded": EXCLUDED},
        "inputs": {
            "E_kwh": [round(e.low / 1000, 4), round(e.high / 1000, 4)],
            "E_method": f"aimpg energy model, factors version {load_factors().get('version')} (method: https://github.com/kumarganduri/aimpg#how-energy-is-estimated)",
            "I_g_per_kwh": grid,
            "I_method": "location-based grid average (no market-based measures)",
            "M_g_per_kwh_served": list(EMBODIED_G_PER_KWH),
            "M_method": EMBODIED_CITATION,
            "requests": len(requests),
            "tokens": tokens,
            "tokens_definition": "input (fresh, cache write and cache read) plus output tokens of every request",
        },
        "total_g": [round(lo_g, 1), round(hi_g, 1)],
        "sci": {
            "per_million_tokens_g": per(tokens / 1e6 if tokens else None),
            "per_ai_assisted_commit_g": per(n_commits),
            "per_working_change_g": working,
        },
        "functional_units": {
            "per_million_tokens": "the spec's suggested unit for LLMs (per token), scaled",
            "per_ai_assisted_commit": "per workflow execution (the spec's unit for agentic AI): one commit the agent helped make",
            "per_working_change": "per workflow execution that lasted: committed, on the main branch and not reverted or largely rewritten 30 days later",
        },
        "working_change_available_from": _day(first + 30 * 86400) if working is None and first is not None else None,
        "uncertainty": "Every value is a low–high range: model sizes and data-centre locations aren't disclosed, "
                       "so energy is bracketed by assumptions (aimpg/factors.json); the range is the result, not noise.",
    }


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _g(v: list[float] | None) -> str:
    if not v:
        return "—"
    lo, hi = v
    unit, k = ("kg", 1000) if hi >= 1000 else ("g", 1)
    return f"{lo / k:,.3g}–{hi / k:,.3g} {unit} CO₂e"


def render(s: dict) -> str:
    sci, inp = s["sci"], s["inputs"]
    lines = [
        f"SCI FOR AI (Consumer) · {s['period']['from']} → {s['period']['to']}",
        f"  Standard: GSF Software Carbon Intensity for AI ({s['specification']})",
        f"  SCI = (O + M) / R,  O = E × I",
        "",
        f"  E (serving energy)      {inp['E_kwh'][0]:,.2f}–{inp['E_kwh'][1]:,.2f} kWh over {inp['requests']:,} model requests",
        f"  I (grid, location-based) {inp['I_g_per_kwh']:.0f} g CO₂e/kWh",
        f"  M (embodied hardware)   {inp['M_g_per_kwh_served'][0]:.0f}–{inp['M_g_per_kwh_served'][1]:.0f} g CO₂e per kWh served",
        f"  Total (O + M)           {_g(s['total_g'])}",
        "",
        "  Per functional unit (R):",
        f"    per million tokens         {_g(sci['per_million_tokens_g'])}",
        f"    per AI-assisted commit     {_g(sci['per_ai_assisted_commit_g'])}",
    ]
    w = sci["per_working_change_g"]
    if w:
        lines.append(f"    per working change         {_g(w['value_g'])}  ({w['working_changes']} of {w['judged_commits']} judged commits lasted)")
    else:
        when = s.get("working_change_available_from")
        lines.append(f"    per working change         available from {when}" if when else "    per working change         not available yet")
    lines += ["", "  Not included: " + "; ".join(x.split(":")[0] for x in s["boundary"]["excluded"]) + ".",
              "  Offsets and renewable-energy certificates never reduce this score (the spec excludes them)."]
    return "\n".join(lines) + "\n"


def default_grid() -> float:
    return float(load_equivalences()["co2_g_per_kwh"]["value"])


def write(s: dict, path: Path) -> None:
    path.write_text(json.dumps(s, indent=2) + "\n")
