"""Terminal table, JSON and Markdown output for a Heat Shift Audit."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

from . import __version__, config

CATEGORY_STYLE = {"OK": "green", "Caution": "yellow", "Extreme Caution": "dark_orange",
                  "Danger": "red", "Extreme Danger": "bold white on red", "Unknown": "dim"}


def f1(v, unit: str = "") -> str:
    return "—" if v is None else f"{v:.1f}{unit}"


def temp_cell(c) -> str:
    return "—" if c is None else f"{c:.1f} / {c * 9 / 5 + 32:.1f}"


def hi_cell(row) -> str:
    return f"{f1(row['heat_index_local_c'])} / {f1(row['heat_index_api_c'])}"


def aqi_cell(row) -> str:
    if row["aqi"] is None:
        return "—"
    return f"{row['aqi']:.0f}" + (" ⚠" if row["aqi_flag"] else "")


def wb_cell(row) -> str:
    return f1(row["wet_bulb_c"]) + (" ⚠" if row["wet_bulb_flag"] else "")


COLUMNS = ["Hour", "Site temp °C / °F", "Heat index °C (local / API)", "Apparent °C",
           "Wet-bulb °C", "RH %", "AQI", "Category"]


def row_cells(row) -> list[str]:
    return [row["hour"], temp_cell(row["site_temp_c"]), hi_cell(row), f1(row["apparent_c"]),
            wb_cell(row), f1(row["rh"]), aqi_cell(row), row["category"]]


def credits_used(res) -> dict | None:
    b, a = res.credits_before, res.credits_after
    if not (b and a):
        return None
    out = {}
    for key in ("total_remaining_credits", "cycle_remaining_credits"):
        if key in b and key in a:
            out[key.replace("_remaining_credits", "")] = b[key] - a[key]
    out["remaining"] = a.get("total_remaining_credits")
    return out


def expected_credits(res) -> int:
    return sum(config.CREDIT_COST[c["endpoint"]] for c in res.calls
               if c.get("status") == "Completed" and not c.get("cached"))


def print_report(res, console=None) -> None:
    inp = res.inputs
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:  # plain fallback
        print(f"\nHeat Shift Audit — {inp.site_name} — {inp.date} ({res.timezone or 'local time'})")
        print(" | ".join(COLUMNS))
        for r in res.rows:
            print(" | ".join(row_cells(r)))
        print("\n" + res.summary)
        for n in res.notes:
            print(" - " + n)
        return
    console = console or Console()
    table = Table(title=f"Heat Shift Audit — {inp.site_name} — {inp.date}",
                  caption=f"Times are local ({res.timezone or 'site local time'}). Category = NWS heat index "
                          f"from the local calculation. ⚠ = AQI ≥ {config.AQI_FLAG_AT} or wet-bulb ≥ "
                          f"{inp.wet_bulb_warn_c:g} °C (illustrative).", caption_justify="left")
    for c in COLUMNS:
        table.add_column(c, justify="left" if c in ("Hour", "Category") else "right")
    for r in res.rows:
        cells = row_cells(r)
        cells[-1] = f"[{CATEGORY_STYLE.get(r['category'], '')}]{r['category']}[/]"
        table.add_row(*cells)
    console.print(table)
    from rich.markup import escape as _esc
    console.print(f"[bold]{_esc(res.summary)}[/bold]")
    if res.notes:
        from rich.markup import escape
        console.print("\n[bold]Data-quality notes[/bold]")
        for n in res.notes:
            console.print(f" • {escape(n)}", highlight=False)
    used = credits_used(res)
    cached = sum(1 for c in res.calls if c.get("cached"))
    console.print(f"\nCalls: {len(res.calls)} ({cached} from cache). Expected credits: {expected_credits(res):,}."
                  + (f" Credits used (usage endpoint, before→after): {used.get('total', 0):,} total, "
                     f"{used.get('cycle', 0):,} cycle; {used.get('remaining', 0):,} remaining." if used else ""))


def _jsonable(obj):
    if dataclasses.is_dataclass(obj):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def to_json(res) -> dict:
    return {
        "tool": f"heatshift {__version__}",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": _jsonable(res.inputs),
        "timezone": res.timezone,
        "sampled_hours": res.hours,
        "summary": res.summary,
        "safest_window": res.window.label() if res.window else None,
        "avoid": [w.label() for w in res.avoid],
        "table": res.rows,
        "data_quality_notes": res.notes,
        "credits": {"before": res.credits_before, "after": res.credits_after,
                    "used": credits_used(res), "expected": expected_credits(res)},
        "latency_s": {c["label"]: c.get("latency_s") for c in res.calls},
        "calls": res.calls,  # raw responses, incl. heatmap map_data and env_params arrays
    }


def to_markdown(res) -> str:
    inp = res.inputs
    lines = [
        f"# Heat Shift Audit — {inp.site_name}",
        "",
        f"- **Site:** {inp.lat}, {inp.lon}  ",
        f"- **Date:** {inp.date}, {inp.start}–{inp.end} local ({res.timezone or 'site local time'}), "
        f"sampled every {inp.every} h  ",
        f"- **Data:** FortyGuard Temperature API — `/v1/heatmap` ({inp.granularity} m, "
        f"{inp.aoi_side_m:g} m × {inp.aoi_side_m:g} m AOI) → `/v1/env_params` ({inp.env_mode} mode)  ",
        "",
        f"**{res.summary}**",
        "",
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "|".join(["---"] * len(COLUMNS)) + "|",
    ]
    for r in res.rows:
        lines.append("| " + " | ".join(row_cells(r)) + " |")
    lines += [
        "",
        f"Category = NWS heat index category (°F bands: <80 OK, 80–90 Caution, 90–103 Extreme Caution, "
        f"103–124 Danger, ≥125 Extreme Danger) from the locally computed heat index (NWS Rothfusz regression) "
        f"using the FortyGuard heatmap temperature and FortyGuard relative humidity. ⚠ on AQI = EPA AQI ≥ "
        f"{config.AQI_FLAG_AT}. ⚠ on wet-bulb = ≥ {inp.wet_bulb_warn_c:g} °C, an **illustrative** threshold, "
        f"not official guidance. The safe window is based on the sampled hours only.",
        "",
        "## Site temperature detail",
        "",
        "| Hour | Site tile °C | AOI min | AOI mean | AOI max | AOI range | Tiles | Cloud (octas) | Precip mm |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in res.rows:
        rng = "—" if r["aoi_range_c"] is None else f"{r['aoi_range_c']:.3f}"
        lines.append(f"| {r['hour']} | {f1(r['site_temp_c'])} | {f1(r['aoi_min_c'])} | {f1(r['aoi_mean_c'])} | "
                     f"{f1(r['aoi_max_c'])} | {rng} | {r['tiles'] or '—'} | {r['cloud_octas'] if r['cloud_octas'] is not None else '—'} | "
                     f"{f1(r['precip_mm'])} |")
    lines += ["", "## Data-quality notes", ""]
    lines += [f"- {n}" for n in res.notes] or ["- None."]
    used = credits_used(res)
    lines += ["", "## API calls", "", "| Call | Status | Latency (s) | Cached | activity_id |", "|---|---|---|---|---|"]
    for c in res.calls:
        lines.append(f"| {c['label']} | {c.get('status')} | {c.get('latency_s') or '—'} | "
                     f"{'yes' if c.get('cached') else 'no'} | `{c.get('activity_id') or '—'}` |")
    lines += ["", f"Expected credits for this run: {expected_credits(res):,}."]
    if used:
        lines.append(f"Credits used according to `/v1/system/fetch-api-key-usage` (before → after): "
                     f"{used.get('total', 0):,} (total), {used.get('cycle', 0):,} (cycle).")
    lines += ["", "_Not medical or legal advice. For shift-planning review of a past day only._", ""]
    return "\n".join(lines)


def save(res, out_dir: str | Path = "runs") -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{res.inputs.slug}_{res.inputs.date}"
    jp, mp = out / f"{stem}.json", out / f"{stem}.md"
    jp.write_text(json.dumps(to_json(res), indent=1, ensure_ascii=False), encoding="utf-8")
    mp.write_text(to_markdown(res), encoding="utf-8")
    return jp, mp
