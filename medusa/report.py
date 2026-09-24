"""Weekly HTML research report and the archive index (``outputs/index.html``).

Charts are server-rendered inline SVG line charts drawn from the simulation's
data tables: thin 2px lines, 95% CI bands as a 10% wash, recessive hairline grid,
a legend for multi-series charts, a crosshair tooltip on hover/focus and a table
view under every chart. Colours follow a validated categorical palette with
separate light/dark steps.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path
from typing import Any

from .models import CycleRecord, FigureSpec
from .utils import read_json

GREEK = {"varepsilon": "ε", "epsilon": "ε", "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "tau": "τ",
         "sigma": "σ", "mu": "μ", "theta": "θ", "omega": "ω", "psi": "ψ", "lambda": "λ", "rho": "ρ", "pi": "π",
         "langle": "⟨", "rangle": "⟩", "infty": "∞", "leq": "≤", "geq": "≥", "approx": "≈", "cdot": "·"}


def plain_label(text: str) -> str:
    """Turn a LaTeX-ish axis label into readable plain text."""
    text = re.sub(r"\\([A-Za-z]+)", lambda m: GREEK.get(m.group(1), ""), text or "")
    text = text.replace("$", "").replace("{", "").replace("}", "").replace("\\", "")
    text = re.sub(r"_(\w+)", r"_\1", text)
    return " ".join(text.split())


def latex_to_text(text: str) -> str:
    """Readable plain text from the paper's LaTeX-lite prose (for HTML pages)."""
    text = re.sub(r"\\cite[tp]?\{([^}]*)\}", lambda m: "[" + m.group(1).replace(",", ", ") + "]", text or "")
    text = re.sub(r"(Figure|Table|Equation)~?\\(?:auto)?ref\{[^}]*\}", r"\1", text)
    text = re.sub(r"\\(?:auto|eq)?ref\{[^}]*\}", "", text)
    text = re.sub(r"\\(?:textbf|emph|textit|texttt|mathrm|text)\{([^{}]*)\}", r"\1", text)
    text = text.replace("\\%", "%").replace("\\&", "&").replace("\\_", "_").replace("~", " ")
    text = re.sub(r"\\([A-Za-z]+)", lambda m: GREEK.get(m.group(1), ""), text)
    text = text.replace("$", "").replace("{", "").replace("}", "")
    return " ".join(text.split())


def rich(text: str) -> str:
    """HTML-escape and render simple powers (N^1.75) as superscripts."""
    out = html.escape(text or "")
    return re.sub(r"(?<=[A-Za-z0-9)])\^(-?[A-Za-z0-9.]+)", r"<sup>\1</sup>", out)


_HTTP_URL = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)


def safe_url(url: str | None) -> str:
    """Escaped href for an http(s) URL only. Retrieved-literature URLs are untrusted, so a
    ``javascript:`` / ``data:`` scheme (which ``html.escape`` does not neutralise) is dropped."""
    return html.escape(url) if url and _HTTP_URL.match(url) else ""


def read_table(path: Path) -> tuple[list[str], list[list[float]]]:
    lines = [ln.split() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return [], []
    header, rows = lines[0], []
    for parts in lines[1:]:
        row = []
        for p in parts:
            try:
                row.append(float(p))
            except ValueError:
                row.append(float("nan"))
        rows.append(row)
    return header, rows


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if not math.isfinite(lo) or not math.isfinite(hi):
        return []
    if hi == lo:
        hi = lo + 1
    span = hi - lo
    raw = span / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 1e-9:
        ticks.append(round(v, 12))
        v += step
    return ticks


def _log_ticks(lo: float, hi: float) -> list[float]:
    ticks = []
    for e in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1):
        for m in (1, 2, 5):
            v = m * 10 ** e
            if lo <= v <= hi:
                ticks.append(v)
    return ticks if len(ticks) >= 2 else [lo, hi]


def _fmt(v: float) -> str:
    if v == 0:
        return "0"
    if abs(v) >= 1000 or abs(v) < 0.01:
        return f"{v:.3g}"
    return f"{v:.3g}".rstrip("0").rstrip(".") if "." in f"{v:.3g}" else f"{v:.3g}"


def svg_line_chart(fig: FigureSpec, header: list[str], rows: list[list[float]], *, chart_id: str) -> str:
    """Inline SVG chart + table view; hover behaviour is attached by the page script."""
    W, H = 640, 340
    ml, mr, mt, mb = 60, 20, 16, 46
    col = {name: i for i, name in enumerate(header)}
    if fig.x not in col or not all(y in col for y in fig.y):
        return ""
    series_cols = fig.y[:3]
    pts = [r for r in rows if len(r) == len(header) and math.isfinite(r[col[fig.x]])]
    if fig.logx:
        pts = [r for r in pts if r[col[fig.x]] > 0]
    pts.sort(key=lambda r: r[col[fig.x]])
    if not pts:
        return ""
    xs = [r[col[fig.x]] for r in pts]
    yvals = []
    for i, y in enumerate(series_cols):
        yvals += [r[col[y]] for r in pts if math.isfinite(r[col[y]])]
        lo_i = fig.lower[i] if i < len(fig.lower) and fig.lower[i] in col else None
        hi_i = fig.upper[i] if i < len(fig.upper) and fig.upper[i] in col else None
        if lo_i and hi_i and (not fig.logy or all(r[col[lo_i]] > 0 and r[col[hi_i]] > 0 for r in pts)):
            yvals += [r[col[c]] for c in (lo_i, hi_i) for r in pts if math.isfinite(r[col[c]])]
    if fig.logy:
        yvals = [v for v in yvals if v > 0]
    if not yvals:
        return ""
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(yvals), max(yvals)
    if not fig.logy:
        y0 = min(0.0, y0) if y0 >= 0 and y0 < 0.25 * (y1 - y0 + 1e-12) else y0
        pad = (y1 - y0) * 0.06 or 1
        y1 += pad
        y0 = y0 - pad if y0 < 0 else y0
    if x1 == x0:
        x1 = x0 + 1

    def sy(v: float) -> float:
        if fig.logy:
            return mt + (1 - (math.log10(v) - math.log10(y0)) / (math.log10(y1) - math.log10(y0) or 1)) * (H - mt - mb)
        return mt + (1 - (v - y0) / (y1 - y0 or 1)) * (H - mt - mb)

    # Direct end-labels for multi-series charts, unless they would collide (then legend + tooltip carry identity).
    labels = [fig.labels[i] if i < len(fig.labels) else y for i, y in enumerate(series_cols)]
    ends = []
    for y in series_cols:
        last = next((r[col[y]] for r in reversed(pts) if math.isfinite(r[col[y]]) and (not fig.logy or r[col[y]] > 0)),
                    None)
        ends.append(sy(last) if last is not None else None)
    direct = len(series_cols) > 1 and all(e is not None for e in ends)
    if direct:
        ordered = sorted(e for e in ends if e is not None)
        direct = all(b - a >= 14 for a, b in zip(ordered, ordered[1:], strict=False))
    if direct:
        mr = int(min(150, 16 + 6.6 * max(len(label) for label in labels)))

    def sx(v: float) -> float:
        if fig.logx:
            return ml + (math.log10(v) - math.log10(x0)) / (math.log10(x1) - math.log10(x0) or 1) * (W - ml - mr)
        return ml + (v - x0) / (x1 - x0) * (W - ml - mr)

    xticks = _log_ticks(x0, x1) if fig.logx else _nice_ticks(x0, x1)
    yticks = _log_ticks(y0, y1) if fig.logy else _nice_ticks(y0, y1)
    xticks = [t for t in xticks if x0 <= t <= x1] or [x0, x1]
    yticks = [t for t in yticks if y0 <= t <= y1] or [y0, y1]
    out = [f'<svg class="chart" id="{chart_id}" viewBox="0 0 {W} {H}" role="img" tabindex="0" '
           f'aria-label="{html.escape(fig.title or fig.caption or fig.id)}">']
    for t in yticks:
        y = sy(t)
        out.append(f'<line class="grid" x1="{ml}" x2="{W - mr}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="tick" x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end">{_fmt(t)}</text>')
    for t in xticks:
        x = sx(t)
        out.append(f'<text class="tick" x="{x:.1f}" y="{H - mb + 18}" text-anchor="middle">{_fmt(t)}</text>')
    out.append(f'<line class="axis" x1="{ml}" x2="{W - mr}" y1="{H - mb}" y2="{H - mb}"/>')
    out.append(f'<text class="axis-label" x="{(ml + W - mr) / 2:.0f}" y="{H - 6}" text-anchor="middle">'
               f'{html.escape(plain_label(fig.xlabel or fig.x))}</text>')
    out.append(f'<text class="axis-label" transform="translate(14 {(mt + H - mb) / 2:.0f}) rotate(-90)" '
               f'text-anchor="middle">{html.escape(plain_label(fig.ylabel))}</text>')
    data_series = []
    for i, y in enumerate(series_cols):
        cls = f"s{i + 1}"
        lo_col = fig.lower[i] if i < len(fig.lower) and fig.lower[i] in col else None
        hi_col = fig.upper[i] if i < len(fig.upper) and fig.upper[i] in col else None
        if lo_col and hi_col and fig.logy and not all(r[col[lo_col]] > 0 and r[col[hi_col]] > 0 for r in pts):
            lo_col = hi_col = None  # a CI band that crosses zero cannot be drawn on a log axis
        if lo_col and hi_col:
            band = [(sx(r[col[fig.x]]), sy(r[col[hi_col]])) for r in pts
                    if math.isfinite(r[col[hi_col]]) and (not fig.logy or r[col[hi_col]] > 0)]
            band += [(sx(r[col[fig.x]]), sy(r[col[lo_col]])) for r in reversed(pts)
                     if math.isfinite(r[col[lo_col]]) and (not fig.logy or r[col[lo_col]] > 0)]
            if len(band) > 2:
                out.append(f'<polygon class="band {cls}" points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in band) + '"/>')
        line = [(sx(r[col[fig.x]]), sy(r[col[y]])) for r in pts
                if math.isfinite(r[col[y]]) and (not fig.logy or r[col[y]] > 0)]
        if line:
            out.append(f'<polyline class="line {cls}" points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in line) + '"/>')
            if len(line) <= 40:
                out += [f'<circle class="dot {cls}" cx="{a:.1f}" cy="{b:.1f}" r="4"/>' for a, b in line]
        label = labels[i]
        if direct and line:
            out.append(f'<text class="endlabel" x="{line[-1][0] + 8:.1f}" y="{line[-1][1] + 4:.1f}">'
                       f'{html.escape(label)}</text>')
        data_series.append({"label": label, "cls": cls,
                            "values": [r[col[y]] if math.isfinite(r[col[y]]) else None for r in pts],
                            "ys": [sy(r[col[y]]) if math.isfinite(r[col[y]]) and (not fig.logy or r[col[y]] > 0)
                                   else None for r in pts]})
    out.append(f'<line class="crosshair" x1="0" x2="0" y1="{mt}" y2="{H - mb}" visibility="hidden"/>')
    out.append(f'<rect class="hit" x="{ml}" y="{mt}" width="{W - ml - mr}" height="{H - mt - mb}"/>')
    out.append("</svg>")
    payload = {"xs": xs, "px": [sx(v) for v in xs], "series": data_series, "xlabel": plain_label(fig.xlabel or fig.x)}
    legend = ""
    if len(series_cols) > 1:
        legend = '<div class="legend">' + "".join(
            f'<span><i class="key {s["cls"]}"></i>{html.escape(s["label"])}</span>' for s in data_series) + "</div>"
    table = ["<details><summary>Table view</summary><table class=\"data\"><thead><tr>",
             f"<th>{html.escape(plain_label(fig.xlabel or fig.x))}</th>"]
    table += [f"<th>{html.escape(s['label'])}</th>" for s in data_series]
    table.append("</tr></thead><tbody>")
    for j, xv in enumerate(xs):
        cells = "".join(f"<td>{'' if s['values'][j] is None else _fmt(s['values'][j])}</td>" for s in data_series)
        table.append(f"<tr><td>{_fmt(xv)}</td>{cells}</tr>")
    table.append("</tbody></table></details>")
    data = json.dumps(payload).replace("</", "<\\/")
    return (f'<figure class="chart-card">{legend}<div class="plot">{"".join(out)}'
            f'<div class="tooltip" role="status" hidden></div></div>'
            f'<figcaption>{html.escape(plain_label(fig.caption or fig.title))}</figcaption>{"".join(table)}'
            f'<script type="application/json" data-chart="{chart_id}">{data}</script></figure>')


CSS = """
:root{color-scheme:light;--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;
--good:#006300;--warn:#8a5a00;--bad:#d03b3b;--accent:#6a4fd6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#1a1a19;--page:#0d0d0d;
--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;
--s2:#d95926;--s3:#199e70;--good:#0ca30c;--warn:#fab219;--bad:#e66767;--accent:#9085e9}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--page:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s3:#199e70;--good:#0ca30c;
--warn:#fab219;--bad:#e66767;--accent:#9085e9}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI","Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:920px;margin:0 auto;padding:32px 16px 64px}
a{color:var(--s1)}
h1{font-size:28px;line-height:1.25;margin:4px 0 8px}
h2{font-size:20px;margin:40px 0 12px;padding-top:8px;border-top:1px solid var(--border)}
.eyebrow{color:var(--ink2);font-size:14px;margin:0}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0}
.chip{border:1px solid var(--border);border-radius:999px;padding:2px 10px;font-size:13px;color:var(--ink2);background:var(--surface)}
.chip b{color:var(--ink)}
.pixel{width:100%;height:auto;image-rendering:pixelated;border-radius:10px;border:1px solid var(--border);margin:20px 0 4px;background:#141220}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.tile .label{font-size:13px;color:var(--ink2)}
.tile .value{font-size:26px;font-weight:600;line-height:1.2}
.abstract{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px}
.note{font-size:14px;color:var(--ink2);border-left:3px solid var(--accent);padding:4px 12px;margin:16px 0}
table{border-collapse:collapse;width:100%;font-size:14px;background:var(--surface)}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--ink2);font-weight:600}
td.num,table.data td{font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:12px;font-weight:600;border-radius:6px;padding:0 6px;color:var(--ink2);
border:1px solid var(--border);border-left:4px solid var(--muted)}
.tag.in_silico{border-left-color:var(--s1)}.tag.human{border-left-color:var(--s2)}
.ok{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.chart-card{margin:20px 0;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 12px 8px}
.plot{position:relative}
svg.chart{width:100%;height:auto;display:block;font:12px system-ui,sans-serif;outline:none}
svg.chart:focus-visible{box-shadow:0 0 0 2px var(--s1);border-radius:6px}
.grid{stroke:var(--grid);stroke-width:1}.axis{stroke:var(--axis);stroke-width:1}
.tick{fill:var(--muted);font-variant-numeric:tabular-nums}.axis-label{fill:var(--ink2);font-size:13px}
.endlabel{fill:var(--ink2);font-size:12px}
.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.dot{stroke:var(--surface);stroke-width:2}
.band{stroke:none;opacity:.12}
.s1{stroke:var(--s1);fill:var(--s1)}.s2{stroke:var(--s2);fill:var(--s2)}.s3{stroke:var(--s3);fill:var(--s3)}
polyline.s1,polyline.s2,polyline.s3{fill:none}
.crosshair{stroke:var(--axis);stroke-width:1}
.hit{fill:transparent;cursor:crosshair}
.tooltip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:8px;
padding:6px 10px;font-size:13px;box-shadow:0 4px 16px rgba(0,0,0,.12);min-width:140px}
.tooltip .x{color:var(--ink2);font-size:12px}.tooltip .row{display:flex;align-items:center;gap:8px}
.tooltip .row b{font-variant-numeric:tabular-nums}
.key{display:inline-block;width:14px;height:0;border-top:2px solid;vertical-align:middle;margin-right:6px}
.key.s1{border-color:var(--s1)}.key.s2{border-color:var(--s2)}.key.s3{border-color:var(--s3)}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--ink2);margin:0 0 4px 8px}
figcaption{font-size:14px;color:var(--ink2);margin:6px 8px}
details{margin:4px 8px 6px;font-size:14px}summary{cursor:pointer;color:var(--ink2)}
ul.refs{padding-left:18px;font-size:14px}ul.refs li{margin:4px 0}
.muted{color:var(--muted)}
@media (max-width:600px){h1{font-size:22px}.tile .value{font-size:22px}}
"""

SCRIPT = """
document.querySelectorAll('script[data-chart]').forEach(function(tag){
  var d = JSON.parse(tag.textContent), svg = document.getElementById(tag.dataset.chart);
  if(!svg) return;
  var tip = svg.parentNode.querySelector('.tooltip'), cross = svg.querySelector('.crosshair'), hit = svg.querySelector('.hit');
  var idx = -1;
  function show(i){
    if(i<0||i>=d.px.length) return; idx=i;
    cross.setAttribute('x1', d.px[i]); cross.setAttribute('x2', d.px[i]); cross.setAttribute('visibility','visible');
    tip.replaceChildren();
    var x = document.createElement('div'); x.className='x'; x.textContent = d.xlabel + ' = ' + (+d.xs[i].toPrecision(4)); tip.appendChild(x);
    d.series.forEach(function(s){
      var row=document.createElement('div'); row.className='row';
      var key=document.createElement('i'); key.className='key '+s.cls; row.appendChild(key);
      var b=document.createElement('b'); var v=s.values[i]; b.textContent = v===null?'–':(+v.toPrecision(4)); row.appendChild(b);
      var l=document.createElement('span'); l.className='muted'; l.textContent=s.label; row.appendChild(l);
      tip.appendChild(row);
    });
    var box = svg.getBoundingClientRect(), scale = box.width/640;
    tip.hidden=false; var left = d.px[i]*scale + 12; if(left + 180 > box.width) left = d.px[i]*scale - 190;
    tip.style.left = Math.max(0,left)+'px'; tip.style.top = '12px';
  }
  function nearest(evt){
    var box = svg.getBoundingClientRect(), x = (evt.clientX - box.left) * 640 / box.width, best=0;
    d.px.forEach(function(p,i){ if(Math.abs(p-x) < Math.abs(d.px[best]-x)) best=i; }); return best;
  }
  hit.addEventListener('pointermove', function(e){ show(nearest(e)); });
  hit.addEventListener('pointerleave', function(){ tip.hidden=true; cross.setAttribute('visibility','hidden'); });
  svg.addEventListener('focus', function(){ show(idx<0?0:idx); });
  svg.addEventListener('blur', function(){ tip.hidden=true; cross.setAttribute('visibility','hidden'); });
  svg.addEventListener('keydown', function(e){
    if(e.key==='ArrowRight'){ show(Math.min(d.px.length-1, idx+1)); e.preventDefault(); }
    if(e.key==='ArrowLeft'){ show(Math.max(0, idx-1)); e.preventDefault(); }
  });
});
"""


def _page(title: str, body: str, lang: str) -> str:
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body><main>{body}</main><script>{SCRIPT}</script></body></html>\n")


def _e(text: Any) -> str:
    return html.escape(str(text if text is not None else ""))


def render_cycle_report(cycle_dir: Path, record: CycleRecord, *, lang: str = "ja") -> str:
    """Self-contained weekly report (links are relative to the cycle directory)."""
    ja = lang == "ja"
    scout = read_json(cycle_dir / "scout" / "literature.json", {}) or {}
    analysis = read_json(cycle_dir / "analyst" / "analysis.json", {}) or {}
    routing = read_json(cycle_dir / "routing.json", {}) or {}
    sim = read_json(cycle_dir / "coder" / "simulation.json", {}) or {}
    review = read_json(cycle_dir / "review" / "latest.json", {}) or {}
    draft = read_json(cycle_dir / "paper" / "draft.json", {}) or {}
    t = record.theme
    parts = [f'<p class="eyebrow">🐍 Medusa Lab · {_e(record.cycle_id)}</p>',
             f"<h1>{_e(t.title)}</h1>",
             '<div class="chips">'
             f'<span class="chip">{"モード" if ja else "Mode"} <b>{_e(t.mode.value)}</b></span>'
             f'<span class="chip">{"状態" if ja else "Status"} <b>{_e(record.status)}</b></span>'
             f'<span class="chip">LLM <b>{_e(record.model or record.llm_mode)}</b></span>'
             + (f'<span class="chip">{"査読判定" if ja else "Decision"} <b>{_e(record.decision)}</b></span>'
                if record.decision else "") + "</div>"]
    if (cycle_dir / "dashboard.svg").exists():
        parts.append('<img class="pixel" src="dashboard.svg" alt="pixel-art lab status at the end of the cycle">')
    tiles = [("文献" if ja else "Papers", len(scout.get("literature", []))),
             ("仮説（計算/人間）" if ja else "Hypotheses (sim/human)",
              f"{len(routing.get('in_silico', []))} / {len(routing.get('human', []))}"),
             ("図" if ja else "Figures", len(sim.get("figures", []))),
             ("査読スコア" if ja else "Review score", f"{record.review_score:.2f}" if record.review_score else "–"),
             ("計算時間" if ja else "Runtime", f"{sim.get('runtime_sec', 0):.1f}s" if sim else "–")]
    parts.append('<div class="tiles">' + "".join(
        f'<div class="tile"><div class="label">{_e(label)}</div><div class="value">{_e(value)}</div></div>'
        for label, value in tiles) + "</div>")
    links = []
    if record.paper_pdf:
        links.append(f'<a href="{_e(record.paper_pdf)}">📄 {"論文PDF" if ja else "Paper (PDF)"}</a>')
    if record.paper_tex:
        links.append(f'<a href="{_e(record.paper_tex)}">LaTeX</a>')
    for p in record.proposals:
        links.append(f'<a href="{_e(p.path)}">🧪 {_e(p.idea_id)}: {_e(p.title)}</a>')
    if record.pr_url:
        links.append(f'<a href="{_e(record.pr_url)}">Pull Request</a>')
    if links:
        parts.append("<p>" + " · ".join(links) + "</p>")
    if draft:
        parts.append(f'<h2>{"論文" if ja else "Paper"}: {_e(draft.get("title"))}</h2>'
                     f'<div class="abstract">{rich(latex_to_text(draft.get("abstract", "")))}</div>')
    parts.append(f'<p class="note">{"この研究はAIエージェントが自律的に実施したもので、人間による査読を経ていません。" if ja else "This study was carried out autonomously by AI agents and has not been reviewed by humans."}</p>')
    # hypotheses & routing
    hyps = analysis.get("hypotheses", [])
    if hyps:
        parts.append(f'<h2>{"仮説と振り分け" if ja else "Hypotheses and routing"}</h2><table><thead><tr><th>ID</th>'
                     f'<th>{"トラック" if ja else "Track"}</th><th>{"仮説" if ja else "Hypothesis"}</th>'
                     f'<th>{"理由" if ja else "Reason"}</th></tr></thead><tbody>')
        deferred = set(routing.get("deferred", []))
        for h in hyps:
            track = "deferred" if h["id"] in deferred else h.get("track", "")
            parts.append(f'<tr><td>{_e(h["id"])}</td><td><span class="tag {_e(track)}">{_e(track)}</span></td>'
                         f'<td>{_e(h.get("statement"))}</td><td class="muted">{_e(routing.get("reasons", {}).get(h["id"], h.get("routing_reason", "")))}</td></tr>')
        parts.append("</tbody></table>")
    # results
    if sim.get("status") == "success":
        parts.append(f'<h2>{"シミュレーション結果" if ja else "Simulation results"}</h2>')
        for f in sim.get("findings", []):
            parts.append(f"<p>• {rich(f)}</p>")
        for i, fdict in enumerate(sim.get("figures", [])):
            fig = FigureSpec.from_dict(fdict)
            data_file = cycle_dir / "coder" / "data" / f"{fig.table}.dat"
            if data_file.is_file():
                header, rows = read_table(data_file)
                parts.append(svg_line_chart(fig, header, rows, chart_id=f"chart{i}"))
        metrics = sim.get("metrics", {})
        if metrics:
            notes = sim.get("metric_notes", {})
            parts.append(f'<table><thead><tr><th>{"指標" if ja else "Metric"}</th><th>{"値" if ja else "Value"}</th>'
                         f'<th>{"説明" if ja else "Description"}</th></tr></thead><tbody>')
            parts += [f'<tr><td><code>{_e(k)}</code></td><td class="num">{_e(v)}</td><td class="muted">{rich(notes.get(k, ""))}</td></tr>'
                      for k, v in metrics.items()]
            parts.append("</tbody></table>")
    elif sim.get("status") == "failed":
        parts.append(f'<h2>{"シミュレーション" if ja else "Simulation"}</h2><p class="bad">{_e(sim.get("error", "")[:500])}</p>')
    # review
    meta = review.get("meta")
    if meta:
        parts.append(f'<h2>{"ピアレビュー" if ja else "Peer review"}</h2><p><b>{_e(meta.get("decision"))}</b> — {_e(meta.get("summary"))}</p>')
        parts.append("<table><thead><tr><th>Reviewer</th><th>Decision</th><th>Novelty</th><th>Rigor</th><th>Clarity</th>"
                     "<th>Reprod.</th><th>Signif.</th></tr></thead><tbody>")
        for r in review.get("reviews", []):
            sc = r.get("scores", {})
            parts.append(f'<tr><td>{_e(r.get("reviewer"))}</td><td>{_e(r.get("decision"))}</td>' + "".join(
                f'<td class="num">{sc.get(c, 0):.1f}</td>' for c in ("novelty", "rigor", "clarity", "reproducibility",
                                                                     "significance")) + "</tr>")
        parts.append("</tbody></table><ul>")
        for c in meta.get("checks", []):
            cls = "ok" if c["passed"] else ("bad" if c.get("severity") == "major" else "warn")
            mark = "✓" if c["passed"] else ("✗" if c.get("severity") == "major" else "!")
            parts.append(f'<li><span class="{cls}">{mark}</span> {_e(c["label"])} <span class="muted">— {_e(c.get("detail"))}</span></li>')
        parts.append("</ul>")
    # literature
    lit = scout.get("literature", [])
    if lit:
        parts.append(f'<h2>{"文献" if ja else "Literature"}</h2><ul class="refs">')
        for it in lit:
            title = _e(it.get("title"))
            href = safe_url(it.get("url"))
            if href:
                title = f'<a href="{href}" rel="noopener nofollow">{title}</a>'
            tag = ' <span class="muted">(foundational)</span>' if it.get("foundational") else ""
            parts.append(f'<li>{_e(", ".join(it.get("authors", [])[:3]))} ({_e(it.get("year"))}). {title}. '
                         f'<span class="muted">{_e(it.get("venue"))}</span>{tag}</li>')
        parts.append("</ul>")
    return _page(f"Medusa Lab {record.cycle_id} — {t.title}", "".join(parts), lang)


def render_index(history: list[dict[str, Any]], *, lab_name: str, lang: str = "ja") -> str:
    ja = lang == "ja"
    parts = [f'<p class="eyebrow">🐍 {_e(lab_name)}</p><h1>{"研究アーカイブ" if ja else "Research archive"}</h1>',
             '<img class="pixel" src="dashboard/lab.svg" alt="pixel-art lab dashboard">',
             f'<p><a href="dashboard/index.html">{"ライブ・ダッシュボード" if ja else "Live dashboard"}</a></p>']
    if not history:
        parts.append(f'<p class="muted">{"まだ研究サイクルはありません。" if ja else "No research cycles yet."}</p>')
    else:
        parts.append(f'<table><thead><tr><th>{"週" if ja else "Week"}</th><th>{"テーマ" if ja else "Theme"}</th>'
                     f'<th>{"モード" if ja else "Mode"}</th><th>{"判定" if ja else "Decision"}</th><th></th></tr></thead><tbody>')
        for h in sorted(history, key=lambda r: r.get("cycle_id", ""), reverse=True):
            base = f"weeks/{h.get('cycle_id')}"
            links = [f'<a href="{_e(base)}/report.html">{"レポート" if ja else "Report"}</a>']
            if h.get("paper_pdf"):
                links.append(f'<a href="{_e(base)}/{_e(h["paper_pdf"])}">PDF</a>')
            if h.get("proposals"):
                links.append(f'<a href="{_e(base)}/proposals/README.md">{"実験提案" if ja else "Proposals"}</a>')
            parts.append(f'<tr><td>{_e(h.get("cycle_id"))}</td><td>{_e(h.get("theme"))}</td><td>{_e(h.get("mode"))}</td>'
                         f'<td>{_e(h.get("decision") or h.get("status"))}</td><td>{" · ".join(links)}</td></tr>')
        parts.append("</tbody></table>")
    return _page(f"{lab_name} — archive", "".join(parts), lang)
