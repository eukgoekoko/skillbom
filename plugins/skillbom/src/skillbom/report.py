"""Render a Skill BOM as a self-contained HTML audit report."""

from __future__ import annotations

from collections import Counter
from html import escape

from skillbom.spdx import CATEGORIES, category

SEVERITIES = ["critical", "high", "medium", "low", "info"]
CATEGORY_LABELS = {
    "permissive": "Permissive", "copyleft": "Copyleft", "source-available": "Source-available",
    "non-commercial": "Non-commercial", "proprietary": "Proprietary", "custom": "Custom terms",
    "other": "Commercial / other", "none": "No license found",
}
STATUS_LABELS = {"declared": "Declared", "inferred": "Inferred", "unknown": "Unknown"}


def _e(value) -> str:
    return escape("" if value is None else str(value))


def _sev(severity: str) -> str:
    return f'<span class="sev sev-{severity}"><span class="dot" aria-hidden="true"></span>{severity}</span>'


def _tile(value, label: str, note: str = "") -> str:
    note_html = f'<div class="tile-note">{_e(note)}</div>' if note else ""
    return f'<div class="tile"><div class="tile-value">{_e(value)}</div><div class="tile-label">{_e(label)}</div>{note_html}</div>'


def _category_chart(cats: Counter, total: int) -> str:
    rows = [(c, cats[c]) for c in CATEGORIES if cats.get(c)]
    if not rows:
        return '<p class="muted">No components.</p>'
    peak = max(n for _, n in rows)
    bars = []
    for c, n in rows:
        pct = 100 * n / total
        tip = f"{CATEGORY_LABELS[c]}: {n} of {total} components ({pct:.1f}%)"
        bars.append(
            f'<div class="bar-row" data-tip="{_e(tip)}" tabindex="0">'
            f'<div class="bar-label">{_e(CATEGORY_LABELS[c])}</div>'
            f'<div class="bar-track"><div class="bar" style="width:{max(100 * n / peak, 0.5):.2f}%"></div></div>'
            f'<div class="bar-value">{n}<span class="muted"> · {pct:.0f}%</span></div></div>')
    return '<div class="bars" role="img" aria-label="Components by license category">' + "".join(bars) + "</div>"


def _findings(bom: dict, names: dict[str, str]) -> str:
    licenses = {c["bomRef"]: c["license"]["expression"] for c in bom["components"]}
    findings = [f for f in bom.get("findings", []) if f["severity"] != "info"]
    info = len(bom.get("findings", [])) - len(findings)
    if not findings:
        body = '<p class="ok">No findings that need action.</p>'
    else:
        # One card per (severity, rule): a rule typically fires on many components at once.
        cards = []
        for sev in SEVERITIES:
            for rule in dict.fromkeys(f["rule"] for f in findings if f["severity"] == sev):
                group = [f for f in findings if f["severity"] == sev and f["rule"] == rule]
                fixes = list(dict.fromkeys(f["remediation"] for f in group if f.get("remediation")))
                fix = "".join(f'<div class="fix"><strong>Fix:</strong> {_e(x)}</div>' for x in fixes)
                if len(group) == 1:
                    body_html = f'<div>{_e(group[0]["message"])}</div>'
                else:
                    counts = Counter(names.get(r, r) for f in group for r in f["components"])
                    exprs = {names.get(r, r): licenses.get(r, "") for f in group for r in f["components"]}
                    items = "".join(f'<li>{_e(n)}{f" <span class=muted>×{k}</span>" if k > 1 else ""}'
                                    f'{f" <code>{_e(exprs[n])}</code>" if exprs[n] else ""}</li>'
                                    for n, k in sorted(counts.items()))
                    body_html = (f'<details{" open" if len(counts) <= 8 else ""}><summary>{len(counts)} '
                                 f'components</summary><ul class="affected">{items}</ul></details>')
                cards.append(f'<li class="finding"><div class="finding-head">{_sev(sev)}<code>{_e(rule)}</code>'
                             f'<span class="muted">{len(group)} finding{"s" if len(group) != 1 else ""}</span></div>'
                             f'{body_html}{fix}</li>')
        body = f'<ul class="findings">{"".join(cards)}</ul>'
    if info:
        body += (f'<p class="muted">{info} informational finding{"s are" if info != 1 else " is"} '
                 f'(e.g. modified copies) listed per component in the inventory.</p>')
    return body


def _inventory(bom: dict, by_ref: dict[str, list[dict]]) -> str:
    def worst_of(c):
        return min((SEVERITIES.index(f["severity"]) for f in by_ref.get(c["bomRef"], [])), default=9)

    rows = []
    # Components with the most severe findings first, then by name.
    for c in sorted(bom["components"], key=lambda c: (worst_of(c), c["name"].lower())):
        lic = c["license"]
        cat = category(lic["expression"])
        fs = by_ref.get(c["bomRef"], [])
        worst = min((SEVERITIES.index(f["severity"]) for f in fs), default=None)
        evidence = "".join(
            f'<li><code>{_e(e["source"])}</code> {_e(e.get("expression") or "—")}'
            f'{" · " + _e(e["confidence"]) if "confidence" in e else ""}'
            f'{" · “" + _e(e["value"]) + "”" if e.get("value") else ""}'
            f'<div class="path">{_e(e["path"])}</div></li>' for e in lic.get("evidence", []))
        installs = "".join(
            f'<li><code>{_e(i["installScope"])}</code> {_e(i.get("platform"))} on {_e(i["host"])}'
            f'{"" if i.get("enabled") is not False else " (disabled)"}<div class="path">{_e(i["path"])}</div></li>'
            for i in c["installations"])
        finding_list = "".join(f'<li>{_sev(f["severity"])} {_e(f["message"])}</li>' for f in fs)
        source = c["source"].get("marketplace") or c["source"].get("url") or c["source"]["type"]
        detail = (f'<details class="row-detail"><summary>Details</summary><div class="detail-grid">'
                  f'<div><h4>License evidence</h4><ul>{evidence or "<li>None found</li>"}</ul></div>'
                  f'<div><h4>Installations</h4><ul>{installs}</ul></div>'
                  f'{"<div><h4>Findings</h4><ul>" + finding_list + "</ul></div>" if fs else ""}'
                  f'<div><h4>Integrity</h4><p>{_e(c.get("integrity"))} · '
                  f'<code>{_e(c["contentHash"]["value"][:16])}…</code></p></div></div></details>')
        sev_cell = _sev(SEVERITIES[worst]) if worst is not None else '<span class="muted">—</span>'
        rows.append(
            f'<tr data-kind="{_e(c["kind"])}" data-cat="{cat}" data-sev="{worst if worst is not None else 9}">'
            f'<td><div class="name">{_e(c["name"])}</div>'
            f'<div class="muted small">{_e(c.get("id") or "")} {_e(c.get("version") or "")}</div>{detail}</td>'
            f'<td>{_e(c["kind"])}</td>'
            f'<td><code>{_e(lic["expression"])}</code><div class="muted small">{_e(CATEGORY_LABELS[cat])}</div></td>'
            f'<td>{_e(STATUS_LABELS.get(lic["status"], lic["status"]))}</td>'
            f'<td>{_e(c["entitlement"]["status"])}</td>'
            f'<td class="small">{_e(source)}</td>'
            f'<td class="num" title="{len(c["installations"])} installation(s)">'
            f'{len({i["host"] for i in c["installations"]})}</td>'
            f'<td data-sort="{worst if worst is not None else 9}">{sev_cell}</td></tr>')
    kinds = sorted({c["kind"] for c in bom["components"]})
    kind_opts = "".join(f'<option value="{_e(k)}">{_e(k)}</option>' for k in kinds)
    cats = [c for c in CATEGORIES if any(category(x["license"]["expression"]) == c for x in bom["components"])]
    cat_opts = "".join(f'<option value="{c}">{_e(CATEGORY_LABELS[c])}</option>' for c in cats)
    return f'''<div class="filters no-print">
  <input type="search" id="q" placeholder="Filter by name, license, source…" aria-label="Filter components">
  <select id="kind" aria-label="Kind"><option value="">All kinds</option>{kind_opts}</select>
  <select id="cat" aria-label="License category"><option value="">All licenses</option>{cat_opts}</select>
  <label><input type="checkbox" id="issues"> Only with findings</label>
  <span class="muted" id="count"></span>
</div>
<div class="table-wrap"><table id="inv">
<thead><tr><th data-col="0">Component</th><th data-col="1">Kind</th><th data-col="2">License</th>
<th data-col="3">Status</th><th data-col="4">Entitlement</th><th data-col="5">Source</th>
<th data-col="6" class="num">Hosts</th><th data-col="7">Worst finding</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>'''


CSS = """
:root{--surface:#fcfcfb;--panel:#ffffff;--border:#e4e2dc;--text:#0b0b0b;--text-2:#52514e;--muted:#6f6d68;
--accent:#2a78d6;--track:#f0efec;--good:#0ca30c;--critical:#d03b3b;--serious:#ec835a;--warning:#fab219;--neutral:#8a8882;
color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--surface:#1a1a19;--panel:#222220;--border:#3a3936;
--text:#ffffff;--text-2:#c3c2b7;--muted:#9c9a92;--accent:#3987e5;--track:#383835;--neutral:#8f8d86;color-scheme:dark}}
:root[data-theme="dark"]{--surface:#1a1a19;--panel:#222220;--border:#3a3936;--text:#ffffff;--text-2:#c3c2b7;
--muted:#9c9a92;--accent:#3987e5;--track:#383835;--neutral:#8f8d86;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:40px 0 12px}h3{font-size:15px;margin:20px 0 8px}
h4{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--text-2);margin:0 0 6px}
.muted{color:var(--muted)}.small{font-size:12px}.ok{color:var(--text-2)}
code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--track);padding:1px 5px;border-radius:4px}
.meta{color:var(--text-2);margin:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:24px}
.tile{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.tile-value{font-size:28px;font-weight:600;line-height:1.1}.tile-label{color:var(--text-2)}.tile-note{color:var(--muted);font-size:12px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px 18px}
.bars{display:grid;gap:6px}
.bar-row{display:grid;grid-template-columns:150px 1fr 110px;align-items:center;gap:12px;padding:3px 4px;border-radius:6px}
.bar-row:hover,.bar-row:focus{background:var(--track);outline:none}
.bar-track{height:14px}.bar{height:14px;background:var(--accent);border-radius:0 4px 4px 0;min-width:2px}
.bar-label{color:var(--text-2)}.bar-value{font-variant-numeric:tabular-nums}
.sev{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;text-transform:capitalize;margin-right:8px;white-space:nowrap}
.sev .dot{width:9px;height:9px;border-radius:50%;background:var(--neutral)}
.sev-critical .dot{background:var(--critical)}.sev-high .dot{background:var(--serious)}.sev-medium .dot{background:var(--warning)}
.sev-critical .dot{border-radius:2px}
.findings{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.finding{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:10px 14px}
.finding-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:2px}
.fix{color:var(--text-2);margin-top:4px}
.affected{columns:3 220px;margin:6px 0 0;padding-left:18px}.affected li{break-inside:avoid}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px}
.filters input[type=search]{flex:1 1 240px;padding:7px 10px;border:1px solid var(--border);border-radius:6px;background:var(--panel);color:var(--text)}
.filters select{padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--panel);color:var(--text)}
.table-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:var(--panel)}
table{border-collapse:collapse;width:100%;min-width:860px}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:top}
th{font-size:12px;color:var(--text-2);font-weight:600;cursor:pointer;user-select:none;position:sticky;top:0;background:var(--panel)}
th[aria-sort=ascending]::after{content:" ▲"}th[aria-sort=descending]::after{content:" ▼"}
tr:last-child td{border-bottom:0}.num{text-align:right;font-variant-numeric:tabular-nums}
.name{font-weight:600}
details summary{cursor:pointer;color:var(--accent);font-size:12px;margin-top:4px}
.detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:8px 0 4px}
.detail-grid ul{margin:0;padding-left:16px}.detail-grid p{margin:0}
.path{font:11px ui-monospace,Menlo,monospace;color:var(--muted);word-break:break-all}
#tip{position:fixed;pointer-events:none;background:var(--text);color:var(--surface);padding:5px 9px;border-radius:6px;font-size:12px;opacity:0;transition:opacity .1s}
footer{margin-top:48px;color:var(--muted);font-size:12px}
.sig{font:600 12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--text-2);margin-right:8px}
::selection{background:#b7d3f6;color:#0b0b0b}
@media (max-width:640px){.bar-row{grid-template-columns:110px 1fr 70px}}
@media print{
:root,:root:not([data-theme="light"]),:root[data-theme="dark"]{--surface:#ffffff;--panel:#ffffff;--border:#d9d7d0;
--text:#0b0b0b;--text-2:#52514e;--muted:#6f6d68;--accent:#2a78d6;--track:#f0efec;--neutral:#8a8882;color-scheme:light}
body{background:#ffffff}
.bar,.sev .dot,code{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.no-print,#tip{display:none}main{max-width:none;padding:0}.table-wrap{overflow:visible;border:0}table{min-width:0}
th{position:static}.finding,.tile,.panel,tr{break-inside:avoid}h2,h3{break-after:avoid}}
"""

JS = """
(() => {
  const rows = [...document.querySelectorAll('#inv tbody tr')];
  const q = document.getElementById('q'), kind = document.getElementById('kind'),
        cat = document.getElementById('cat'), issues = document.getElementById('issues'),
        count = document.getElementById('count');
  function apply() {
    const term = q.value.trim().toLowerCase(); let shown = 0;
    for (const r of rows) {
      const ok = (!term || r.textContent.toLowerCase().includes(term)) &&
        (!kind.value || r.dataset.kind === kind.value) && (!cat.value || r.dataset.cat === cat.value) &&
        (!issues.checked || r.dataset.sev !== '9');
      r.hidden = !ok; if (ok) shown++;
    }
    count.textContent = shown + ' of ' + rows.length + ' shown';
  }
  [q, kind, cat, issues].forEach(el => el.addEventListener('input', apply)); apply();
  const tbody = document.querySelector('#inv tbody');
  document.querySelectorAll('#inv th').forEach(th => th.addEventListener('click', () => {
    const col = +th.dataset.col, dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
    document.querySelectorAll('#inv th').forEach(h => h.removeAttribute('aria-sort'));
    th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
    const key = r => { const c = r.children[col]; return c.dataset.sort ?? c.textContent.trim().toLowerCase(); };
    rows.sort((a, b) => { const x = key(a), y = key(b);
      const n = !isNaN(x) && !isNaN(y) ? x - y : x.localeCompare(y); return n * dir; });
    rows.forEach(r => tbody.appendChild(r));
  }));
  // Print: expand finding lists (closed <details> content never prints), hide per-row details.
  let opened = [];
  addEventListener('beforeprint', () => {
    opened = [...document.querySelectorAll('.finding details:not([open])')];
    opened.forEach(d => d.open = true);
    document.querySelectorAll('.row-detail').forEach(d => d.hidden = true);
  });
  addEventListener('afterprint', () => {
    opened.forEach(d => d.open = false);
    document.querySelectorAll('.row-detail').forEach(d => d.hidden = false);
  });
  const tip = document.getElementById('tip');
  document.querySelectorAll('[data-tip]').forEach(el => {
    const show = e => { tip.textContent = el.dataset.tip; tip.style.opacity = 1;
      const r = el.getBoundingClientRect(), x = e && e.clientX ? e.clientX : r.left + r.width / 2;
      tip.style.left = Math.min(x + 12, innerWidth - tip.offsetWidth - 8) + 'px';
      tip.style.top = ((e && e.clientY) ? e.clientY + 14 : r.bottom + 6) + 'px'; };
    el.addEventListener('mousemove', show); el.addEventListener('focus', () => show());
    el.addEventListener('mouseleave', () => tip.style.opacity = 0); el.addEventListener('blur', () => tip.style.opacity = 0);
  });
})();
"""


def render(bom: dict, title: str | None = None) -> str:
    meta, summary = bom["metadata"], bom["summary"]
    names = {c["bomRef"]: f'{c["name"]} ({c["kind"]})' for c in bom["components"]}
    by_ref: dict[str, list[dict]] = {}
    for f in bom.get("findings", []):
        for ref in f["components"]:
            by_ref.setdefault(ref, []).append(f)

    org = meta["scope"].get("organization")
    title = title or (f"Skill license audit — {org}" if org else "Skill license audit")
    hosts = meta["scope"]["hosts"]
    total = summary["components"]
    cats = Counter(category(c["license"]["expression"]) for c in bom["components"])
    sev = summary["findingsBySeverity"]
    action = sev.get("critical", 0) + sev.get("high", 0)
    unknown = summary["byLicenseStatus"].get("unknown", 0)
    restricted = cats.get("non-commercial", 0) + cats.get("proprietary", 0) + cats.get("custom", 0)
    policy = meta.get("policy")
    policy_text = (f'Policy <code>{_e(policy.get("id", "custom"))}</code>'
                   f'{" " + _e(policy["version"]) if policy.get("version") else ""}') if policy else "No policy applied"

    tiles = "".join([
        _tile(total, "components", f'{summary.get("installations", 0)} installations on '
                                   f'{summary.get("hosts", len(hosts))} host{"s" if summary.get("hosts", len(hosts)) != 1 else ""}'),
        _tile(action, "critical / high findings", f'{sum(sev.values())} findings in total'),
        _tile(unknown, "without any license", f"{100 * unknown / total:.0f}% of components" if total else ""),
        _tile(restricted, "restricted or custom terms", "non-commercial, proprietary, custom"),
    ])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>{CSS}</style></head>
<body><main>
<header><h1>{_e(title)}</h1>
<p class="meta">{"Merged from " + str(len(meta["mergedFrom"])) + " scans at " if meta.get("mergedFrom") else "Scanned "}{_e(meta["timestamp"])} · {len(hosts)} host{"s" if len(hosts) != 1 else ""} · {policy_text}
· {_e(meta["tool"]["name"])} {_e(meta["tool"]["version"])} · <code>{_e(bom["serialNumber"])}</code></p></header>
<section class="tiles">{tiles}</section>
<h2>Findings</h2>{_findings(bom, names)}
<h2>License categories</h2><div class="panel">{_category_chart(cats, total)}
<p class="muted small">Category of the most permissive license choice available. “Inferred” licenses come from manifests, frontmatter or LICENSE texts rather than a skill-license file; the inventory shows the evidence for each.</p></div>
<h2>Inventory</h2>{_inventory(bom, by_ref)}
<footer><span class="sig">✓ skillbom — every skill accounted for.</span> Generated from Skill BOM {_e(bom["specVersion"])}. License categories are a summary of the license texts, not legal advice.</footer>
</main><div id="tip" role="tooltip"></div><script>{JS}</script></body></html>
"""
