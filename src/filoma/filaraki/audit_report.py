"""Self-contained HTML rendering for dataset audit reports.

Kept separate from :func:`filoma.filaraki.tools.audit_dataset` so the (large)
presentation layer can be read, tested and changed without touching the audit
orchestration.
"""

import html
import json
from pathlib import Path
from typing import Any, Dict, Union


def render_html_report(consolidated_report: Dict[str, Any], target: Union[str, Path], mode: str) -> str:
    """Render a consolidated audit report as a single self-contained HTML page.

    Args:
        consolidated_report: The report dict assembled by ``audit_dataset``.
        target: The audited path, shown in the page header.
        mode: The audit mode (``"concise"`` or ``"verbose"``), shown in the page header.

    Returns:
        The HTML document as a string.

    """
    version = consolidated_report.get("version", "unknown")

    # ── Extra variables for the enhanced HTML report ───────────────────────────
    _sum = consolidated_report.get("summary", {})
    _hg = float(_sum.get("hygiene_score") or 0)
    _rd = float(_sum.get("migration_readiness") or 0)
    _n_files = _sum.get("total_files_checked", 0)
    _n_dups = _sum.get("duplicate_groups", 0)
    _n_corrupt = _sum.get("corrupted_files", 0)
    _space = _sum.get("estimated_space_waste_bytes", 0)
    _space_fmt = f"{_space / 1048576:.1f} MB" if _space >= 1048576 else f"{_space / 1024:.1f} KB" if _space >= 1024 else f"{_space} B"
    _circ = 238.8  # 2*pi*38
    _hg_arc = round(_circ * _hg / 100, 1)
    _rd_arc = round(_circ * _rd / 100, 1)
    _hg_col = "#10b981" if _hg >= 80 else "#f59e0b" if _hg >= 50 else "#ef4444"
    _rd_col = "#10b981" if _rd >= 80 else "#f59e0b" if _rd >= 50 else "#ef4444"
    _recon_st = consolidated_report.get("reconciliation", {}).get("status", "ok")
    _recon_class = "recon-warn" if _recon_st == "warn" else "recon-ok"
    _recon_msg = (
        "&#9888; File counts differ across pipeline stages — some file types may be excluded by the integrity check."
        if _recon_st == "warn"
        else "&#10003; File counts are consistent across all pipeline stages."
    )
    _kpi_dups_class = "kv-warn" if _n_dups > 0 else "kv-good"
    _kpi_corrupt_class = "kv-bad" if _n_corrupt > 0 else "kv-good"
    _kpi_space_class = "kv-warn" if _space > 0 else "kv-good"

    # Split pills
    _split_dict = consolidated_report.get("dataset_profile", {}).get("split_counts", {})
    _split_pills_html = (
        ('<div class="split-pills">' + "".join(f'<div class="split-pill">{html.escape(str(sk))}: <strong>{html.escape(str(sv))}</strong></div>' for sk, sv in _split_dict.items()) + "</div>")
        if _split_dict
        else ""
    )

    # Extension rows for profile card
    _ext_dict = consolidated_report.get("dataset_profile", {}).get("extension_counts", {})
    _ext_rows = "".join(f"<tr><td>{html.escape(str(k))}</td><td><strong>{html.escape(str(v))}</strong></td></tr>" for k, v in _ext_dict.items())

    # Summary rows (skip hygiene_score/migration_readiness — shown as gauges)
    _summary_rows = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in _sum.items() if k not in ("hygiene_score", "migration_readiness"))

    # Reconciliation rows
    _recon_rows = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in consolidated_report.get("reconciliation", {}).items() if k != "status")

    # Timing progress bars
    _timing_data = consolidated_report.get("stage_timings", {})
    _total_secs = max(float(_timing_data.get("total_seconds", 1)), 0.001)
    _timing_html = ""
    for _tk, _tv in _timing_data.items():
        if _tk == "total_seconds":
            continue
        _tpct = min(round(float(_tv) / _total_secs * 100, 1), 100)
        _tlbl = html.escape(str(_tk).replace("_seconds", "").replace("_", " ").title())
        _timing_html += (
            f'<div class="timing-row">'
            f'<span class="timing-name">{_tlbl}</span>'
            f'<div class="timing-bar-wrap"><div class="timing-bar" style="width:{_tpct}%"></div></div>'
            f'<span class="timing-val">{float(_tv):.2f}s</span>'
            f"</div>"
        )
    _timing_html += (
        f'<div class="timing-row timing-total">'
        f'<span class="timing-name">Total</span>'
        f'<div class="timing-bar-wrap"><div class="timing-bar" style="width:100%"></div></div>'
        f'<span class="timing-val">{_total_secs:.2f}s</span>'
        f"</div>"
    )

    # Priority-coloured action rows
    _actions_rich = ""
    for _a in consolidated_report.get("next_actions", []):
        _pri = html.escape(str(_a.get("priority", "")))
        _pcls = "badge-high" if _pri == "high" else "badge-med" if _pri == "medium" else "badge-low"
        _actions_rich += (
            f"<tr>"
            f'<td><span class="badge {_pcls}">{_pri}</span></td>'
            f"<td>{html.escape(str(_a.get('action', '')))}</td>"
            f'<td class="c-muted">{html.escape(str(_a.get("estimated_effort", "")))}</td>'
            f'<td class="c-muted fup">{html.escape(str(_a.get("auto_followup_prompt", "")))}</td>'
            f"</tr>"
        )
    _actions_or_empty = _actions_rich or '<tr><td colspan="4" class="c-muted" style="padding:12px 8px">No actions required.</td></tr>'

    # Structured duplicate evidence
    _ev_html = ""
    for _ev in consolidated_report.get("evidence", []):
        _evs = str(_ev)
        if _evs.startswith("- Group"):
            _parts = _evs[len("- ") :].split(": ", 1)
            _glabel = html.escape(_parts[0]) if len(_parts) == 2 else "Group"
            _gfiles = [html.escape(f.strip()) for f in (_parts[1] if len(_parts) == 2 else _evs).split(",")]
            _ev_html += f'<div class="dup-group"><div class="dup-label">{_glabel}</div>' + "".join(f'<div class="dup-path">{f}</div>' for f in _gfiles) + "</div>"
        else:
            _ev_html += f'<p class="c-muted ev-hdr">{html.escape(_evs)}</p>'
    _evidence_section = ('<div class="card-wide"><div class="ctitle"><div class="cicon" style="background:#eff6ff">&#128257;</div>Duplicate Evidence</div>' + _ev_html + "</div>") if _ev_html else ""

    # Hygiene metric chips
    _metrics_html = ""
    for _m in consolidated_report.get("reports", {}).get("hygiene", {}).get("metrics", []):
        _mn = html.escape(str(_m.get("name", "")).replace("_", " ").title())
        _mv = _m.get("value", 0)
        _ms = _m.get("status", "unknown")
        _mc = "metric-pass" if _ms == "pass" else "metric-fail"
        _mi = "&#10003;" if _ms == "pass" else "&#10007;"
        _metrics_html += f'<div class="metric-chip {_mc}"><span class="mi">{_mi}</span>{_mn}<strong>{_mv}</strong></div>'
    if not _metrics_html:
        _metrics_html = '<span class="c-muted">No hygiene metrics available.</span>'

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Filoma Dataset Audit</title>
  <style>
    *,::before,::after{{box-sizing:border-box}}
    body{{margin:0;padding:0;background:#eef2f7;color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}}
    .hero{{background:linear-gradient(135deg,#134e4a 0%,#0e7490 55%,#1e40af 100%);color:#fff;padding:32px 0 0;}}
    .wrap{{max-width:1160px;margin:0 auto;padding:0 24px;}}
    .hero-inner{{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;flex-wrap:wrap;padding-bottom:4px;}}
    .tag{{display:inline-block;background:rgba(255,255,255,.18);border-radius:999px;padding:3px 14px;font-size:.7rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;margin-bottom:10px;}}
    h1{{margin:0 0 7px;font-size:1.55rem;font-weight:800;line-height:1.2;}}
    .hero-meta{{font-size:.83rem;opacity:.72;margin:0;word-break:break-all;line-height:1.7;}}
    .hero-meta b{{opacity:1;margin-right:3px;}}
    .gauge-row{{display:flex;gap:20px;flex-shrink:0;}}
    .gauge{{text-align:center;}}
    .gauge-lbl{{font-size:.67rem;font-weight:700;opacity:.8;margin-top:5px;text-transform:uppercase;letter-spacing:.06em;}}
    .kpi-strip{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(0,0,0,.3);margin-top:26px;border-top:1px solid rgba(255,255,255,.1);}}
    .kpi{{padding:14px 16px;background:rgba(0,0,0,.18);text-align:center;}}
    .kpi-val{{font-size:1.6rem;font-weight:800;line-height:1;}}
    .kpi-lbl{{font-size:.67rem;opacity:.68;margin-top:4px;text-transform:uppercase;letter-spacing:.05em;}}
    .kv-good{{color:#6ee7b7;}}
    .kv-warn{{color:#fcd34d;}}
    .kv-bad{{color:#fca5a5;}}
    .content{{padding:28px 0 48px;}}
    .sec-hdr{{font-size:.7rem;font-weight:800;color:#94a3b8;text-transform:uppercase;letter-spacing:.09em;margin:28px 0 12px;display:flex;align-items:center;gap:8px;}}
    .sec-hdr::after{{content:'';flex:1;height:1px;background:#e2e8f0;}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;}}
    .card{{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:20px;}}
    .card-wide{{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:20px;margin-bottom:16px;}}
    .ctitle{{display:flex;align-items:center;gap:8px;margin:0 0 16px;font-size:.78rem;font-weight:800;color:#0f766e;text-transform:uppercase;letter-spacing:.06em;}}
    .cicon{{width:24px;height:24px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:.9rem;flex-shrink:0;}}
    table.dt{{width:100%;border-collapse:collapse;}}
    .dt th,.dt td{{border-bottom:1px solid #f1f5f9;padding:8px 7px;vertical-align:top;font-size:.865rem;}}
    .dt th{{color:#64748b;font-weight:600;width:52%;}}
    .dt tr:last-child th,.dt tr:last-child td{{border-bottom:none;}}
    .dt tr:hover td,.dt tr:hover th{{background:#f8fafc;}}
    table.sdt{{width:100%;border-collapse:collapse;}}
    .sdt th,.sdt td{{border-bottom:1px solid #f1f5f9;padding:6px 7px;font-size:.84rem;}}
    .sdt th{{color:#94a3b8;font-weight:700;font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;padding-bottom:8px;}}
    .sdt tr:last-child td{{border-bottom:none;}}
    .badge{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.7rem;font-weight:800;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap;}}
    .badge-high{{background:#fee2e2;color:#b91c1c;}}
    .badge-med{{background:#fef3c7;color:#92400e;}}
    .badge-low{{background:#e0f2fe;color:#0369a1;}}
    .metrics-row{{display:flex;flex-wrap:wrap;gap:8px;}}
    .metric-chip{{display:inline-flex;align-items:center;gap:6px;padding:6px 13px;border-radius:10px;font-size:.82rem;font-weight:600;}}
    .metric-pass{{background:#dcfce7;color:#166534;}}
    .metric-fail{{background:#fee2e2;color:#b91c1c;}}
    .mi{{font-size:.94rem;}}
    .dup-group{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 14px;margin-bottom:10px;}}
    .dup-group:last-child{{margin-bottom:0;}}
    .dup-label{{font-size:.7rem;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:.07em;margin-bottom:7px;}}
    .dup-path{{font-family:ui-monospace,'Cascadia Code','SF Mono',Consolas,monospace;font-size:.77rem;color:#1e40af;word-break:break-all;padding:2px 0;}}
    .dup-path+.dup-path{{border-top:1px dashed #e2e8f0;margin-top:4px;padding-top:4px;}}
    .timing-row{{display:grid;grid-template-columns:100px 1fr 52px;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #f1f5f9;}}
    .timing-row:last-child{{border-bottom:none;}}
    .timing-name{{font-size:.82rem;color:#475569;font-weight:600;}}
    .timing-bar-wrap{{background:#f1f5f9;border-radius:4px;height:7px;overflow:hidden;}}
    .timing-bar{{height:7px;border-radius:4px;background:linear-gradient(90deg,#0d9488,#0284c7);transition:width .3s;}}
    .timing-total .timing-bar{{background:linear-gradient(90deg,#6366f1,#8b5cf6);}}
    .timing-val{{font-size:.82rem;font-variant-numeric:tabular-nums;color:#475569;font-weight:600;text-align:right;}}
    table.at{{width:100%;border-collapse:collapse;}}
    .at th{{font-size:.7rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;padding:6px 9px 10px;border-bottom:2px solid #e2e8f0;}}
    .at td{{padding:10px 9px;border-bottom:1px solid #f1f5f9;vertical-align:top;font-size:.865rem;}}
    .at tr:last-child td{{border-bottom:none;}}
    .c-muted{{color:#64748b;}}
    .fup{{font-style:italic;font-size:.82rem;}}
    .recon-warn{{background:#fffbeb;border-left:4px solid #f59e0b;padding:10px 14px;border-radius:0 10px 10px 0;font-size:.86rem;margin-top:12px;color:#78350f;}}
    .recon-ok{{background:#f0fdf4;border-left:4px solid #10b981;padding:10px 14px;border-radius:0 10px 10px 0;font-size:.86rem;margin-top:12px;color:#14532d;}}
    details{{border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;margin-top:16px;}}
    details>summary{{cursor:pointer;background:#f8fafc;color:#0f766e;font-weight:700;font-size:.87rem;user-select:none;padding:13px 18px;list-style:none;display:flex;align-items:center;gap:8px;}}
    details>summary::marker,details>summary::-webkit-details-marker{{display:none;}}
    details>summary::before{{content:'›';font-size:1.1rem;font-weight:900;transition:transform .2s;display:inline-block;}}
    details[open]>summary::before{{transform:rotate(90deg);}}
    pre{{white-space:pre-wrap;word-break:break-word;background:#0f172a;color:#94a3b8;padding:20px;border-radius:0 0 14px 14px;font-size:.78rem;line-height:1.65;overflow:auto;margin:0;}}
    .split-pills{{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px;}}
    .split-pill{{background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af;border-radius:8px;padding:4px 13px;font-size:.82rem;}}
    .ev-hdr{{margin:0 0 8px;}}
    @media(max-width:640px){{
      .hero-inner{{flex-direction:column;}}
      .kpi-strip{{grid-template-columns:repeat(2,1fr);}}
      .gauge-row{{justify-content:center;width:100%;}}
    }}
  </style>
</head>
<body>
<header class="hero">
  <div class="wrap">
    <div class="hero-inner">
      <div>
        <div class="tag">Dataset Audit</div>
        <h1>Filoma Dataset Audit Report</h1>
        <p class="hero-meta">
          <b>Target:</b> {html.escape(str(target))}<br>
          <b>Mode:</b> {html.escape(mode)}&nbsp;&nbsp;&#183;&nbsp;&nbsp;<b>Version:</b> {html.escape(str(version))}
        </p>
      </div>
      <div class="gauge-row">
        <div class="gauge">
          <svg width="92" height="92" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="38" fill="none" stroke="rgba(255,255,255,.15)" stroke-width="9"/>
            <circle cx="50" cy="50" r="38" fill="none" stroke="{_hg_col}" stroke-width="9"
              stroke-dasharray="{_hg_arc} {_circ}" stroke-linecap="round"
              transform="rotate(-90 50 50)"/>
            <text x="50" y="46" dominant-baseline="middle" text-anchor="middle"
              font-size="20" font-weight="800" fill="white">{_hg:.0f}</text>
            <text x="50" y="64" dominant-baseline="middle" text-anchor="middle"
              font-size="8.5" fill="rgba(255,255,255,.55)">/ 100</text>
          </svg>
          <div class="gauge-lbl">Hygiene</div>
        </div>
        <div class="gauge">
          <svg width="92" height="92" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="38" fill="none" stroke="rgba(255,255,255,.15)" stroke-width="9"/>
            <circle cx="50" cy="50" r="38" fill="none" stroke="{_rd_col}" stroke-width="9"
              stroke-dasharray="{_rd_arc} {_circ}" stroke-linecap="round"
              transform="rotate(-90 50 50)"/>
            <text x="50" y="46" dominant-baseline="middle" text-anchor="middle"
              font-size="20" font-weight="800" fill="white">{_rd:.0f}</text>
            <text x="50" y="64" dominant-baseline="middle" text-anchor="middle"
              font-size="8.5" fill="rgba(255,255,255,.55)">/ 100</text>
          </svg>
          <div class="gauge-lbl">Readiness</div>
        </div>
      </div>
    </div>
    <div class="kpi-strip">
      <div class="kpi">
        <div class="kpi-val">{_n_files:,}</div>
        <div class="kpi-lbl">Files Checked</div>
      </div>
      <div class="kpi">
        <div class="kpi-val {_kpi_dups_class}">{_n_dups}</div>
        <div class="kpi-lbl">Duplicate Groups</div>
      </div>
      <div class="kpi">
        <div class="kpi-val {_kpi_corrupt_class}">{_n_corrupt}</div>
        <div class="kpi-lbl">Corrupted Files</div>
      </div>
      <div class="kpi">
        <div class="kpi-val {_kpi_space_class}">{_space_fmt}</div>
        <div class="kpi-lbl">Space Waste</div>
      </div>
    </div>
  </div>
</header>

<div class="content">
  <div class="wrap">

    <div class="sec-hdr">Dataset Overview</div>
    <div class="grid">

      <div class="card">
        <div class="ctitle"><div class="cicon" style="background:#f0fdf4">&#128194;</div>File Profile</div>
        <table class="sdt">
          <thead><tr><th>Extension</th><th>Count</th></tr></thead>
          <tbody>{_ext_rows}</tbody>
        </table>
        {_split_pills_html}
      </div>

      <div class="card">
        <div class="ctitle"><div class="cicon" style="background:#fef3c7">&#128269;</div>Summary</div>
        <table class="dt">{_summary_rows}</table>
      </div>

      <div class="card">
        <div class="ctitle"><div class="cicon" style="background:#eff6ff">&#9878;</div>Reconciliation</div>
        <table class="dt">{_recon_rows}</table>
        <div class="{_recon_class}">{_recon_msg}</div>
      </div>

      <div class="card">
        <div class="ctitle"><div class="cicon" style="background:#f5f3ff">&#9201;</div>Stage Timings</div>
        {_timing_html}
      </div>

    </div>

    <div class="sec-hdr" style="margin-top:32px">Quality</div>
    <div class="card-wide">
      <div class="ctitle"><div class="cicon" style="background:#fef3c7">&#129514;</div>Hygiene Metrics</div>
      <div class="metrics-row">{_metrics_html}</div>
    </div>

    <div class="card-wide">
      <div class="ctitle"><div class="cicon" style="background:#fee2e2">&#9889;</div>Next Actions</div>
      <table class="at">
        <thead><tr><th>Priority</th><th>Action</th><th>Effort</th><th>Follow-up Prompt</th></tr></thead>
        <tbody>{_actions_or_empty}</tbody>
      </table>
    </div>

    {_evidence_section}

    <details>
      <summary>Full JSON Payload</summary>
      <pre>{html.escape(json.dumps(consolidated_report, indent=2, default=str))}</pre>
    </details>

  </div>
</div>
</body>
</html>
"""
    return html_doc
