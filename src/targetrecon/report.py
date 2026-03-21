"""Jinja2-based HTML report generator — matches preview layout."""
from __future__ import annotations

from jinja2 import Template

from targetrecon.models import TargetReport

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TargetRecon: {{ report.uniprot.gene_name or report.query }}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/3Dmol/2.1.0/3Dmol-min.js"></script>
<style>
:root {
  --bg:      #0d1117;
  --bg2:     #161b22;
  --bg3:     #1c2128;
  --border:  #30363d;
  --text:    #e6edf3;
  --muted:   #b1bac4;
  --dim:     #768390;
  --blue:    #58a6ff;
  --green:   #3fb950;
  --orange:  #d29922;
  --purple:  #bc8cff;
  --red:     #f85149;
  --mono:    'JetBrains Mono', 'Fira Code', monospace;
  --sans:    system-ui, -apple-system, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 14px; line-height: 1.6; -webkit-font-smoothing: antialiased; }
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
.wrap { max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }

/* ── Header card ── */
.hdr { background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem 1.75rem; margin-bottom: 1rem; }
.hdr-name { font-size: 24px; font-weight: 700; letter-spacing: -.02em; }
.hdr-protein { font-size: 14px; color: var(--muted); margin-top: .25rem; }
.hdr-meta { display: flex; gap: 1.5rem; margin-top: .75rem; flex-wrap: wrap; font-size: 12.5px; color: var(--dim); }
.hdr-meta a { font-family: var(--mono); font-size: 12px; }

/* ── Stats ── */
.stats { display: grid; grid-template-columns: repeat(5,1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; margin-bottom: 1rem; }
.stat { background: var(--bg2); padding: 1rem; text-align: center; }
.stat-n { font-size: 22px; font-weight: 700; font-family: var(--mono); letter-spacing: -.02em; }
.stat-l { font-size: 10px; color: var(--dim); text-transform: uppercase; letter-spacing: .07em; margin-top: .25rem; font-weight: 600; }

/* ── Section ── */
.sec { background: var(--bg2); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; }
.sec-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 1rem; }

/* ── Info grid ── */
.info-grid { display: grid; grid-template-columns: 110px 1fr; gap: .5rem 1.25rem; font-size: 13px; }
.ik { color: var(--dim); font-size: 11.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; padding-top: 2px; }
.iv { color: var(--text); line-height: 1.65; }

/* ── Tags ── */
.tag { display: inline-block; padding: 2px 9px; border-radius: 20px; font-size: 11.5px; font-weight: 500; margin: 2px 2px 2px 0; }
.t-blue   { background: rgba(88,166,255,.15); color: var(--blue); }
.t-green  { background: rgba(63,185,80,.12);  color: var(--green); }
.t-purple { background: rgba(188,140,255,.12);color: var(--purple); }
.t-gray   { background: rgba(139,148,158,.12);color: var(--muted); }

/* ── 3D Viewer ── */
.viewer-toolbar { display: flex; align-items: center; gap: .5rem; margin-bottom: .75rem; flex-wrap: wrap; }
.viewer-toolbar select, .viewer-toolbar button {
  background: var(--bg3); border: 1px solid var(--border); color: var(--text);
  font-size: 12px; padding: .35rem .65rem; border-radius: 5px; cursor: pointer; font-family: var(--sans);
}
.viewer-toolbar select { flex: 1; max-width: 340px; }
.viewer-toolbar button:hover, .viewer-toolbar button.active { border-color: var(--blue); color: var(--blue); }
#mol-viewer { width: 100%; height: 300px; background: #030508; border-radius: 8px; border: 1px solid var(--border); position: relative; }

/* ── Charts ── */
.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; margin-bottom: 0; }
.chart-wrap { position: relative; height: 200px; width: 100%; }
.chart-wrap canvas { position: absolute; top:0; left:0; width:100% !important; height:100% !important; }

/* ── Table ── */
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: .55rem .85rem; font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; border-bottom: 1px solid var(--border); background: var(--bg3); text-align: left; white-space: nowrap; }
th.r { text-align: right; }
td { padding: .55rem .85rem; border-bottom: 1px solid rgba(48,54,61,.6); color: var(--text); vertical-align: middle; }
td.r { text-align: right; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255,255,255,.02); }
.mono { font-family: var(--mono); font-size: 11.5px; }
.pc-hi { color: var(--green); font-weight: 600; font-family: var(--mono); }
.pc-md { color: var(--orange); font-weight: 600; font-family: var(--mono); }
.pc-lo { color: var(--red); font-family: var(--mono); }

/* ── Collapsible ── */
details.sec { padding: 0; }
details.sec summary {
  padding: 1.1rem 1.5rem; cursor: pointer; list-style: none;
  display: flex; justify-content: space-between; align-items: center;
  user-select: none;
}
details.sec summary::-webkit-details-marker { display: none; }
details.sec summary .arrow {
  font-size: 13px; color: var(--dim); transition: transform .2s;
  display: inline-block;
}
details.sec[open] summary .arrow { transform: rotate(90deg); }
details.sec .sec-body { padding: 0 0 0 0; }

/* ── AI ── */
.ai-box { background: rgba(88,166,255,.05); border: 1px solid rgba(88,166,255,.2); border-radius: 8px; padding: 1.25rem; white-space: pre-wrap; font-size: 13.5px; line-height: 1.8; color: var(--text); }

/* ── Footer ── */
.footer { text-align: center; color: var(--dim); font-size: 11.5px; margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px solid var(--border); }
</style>
</head>
<body>
<div class="wrap">

<!-- Header -->
<div class="hdr">
  <div class="hdr-name">{{ report.uniprot.gene_name or report.query }}</div>
  <div class="hdr-protein">{{ report.uniprot.protein_name }}</div>
  <div class="hdr-meta">
    <span>UniProt <a href="https://www.uniprot.org/uniprot/{{ report.uniprot.uniprot_id }}" target="_blank">{{ report.uniprot.uniprot_id }}</a></span>
    {% if report.uniprot.chembl_id %}<span>ChEMBL <a href="https://www.ebi.ac.uk/chembl/target_report_card/{{ report.uniprot.chembl_id }}" target="_blank">{{ report.uniprot.chembl_id }}</a></span>{% endif %}
    <span>Organism <strong style="color:var(--text);font-weight:500">{{ report.uniprot.organism }}</strong></span>
    <span>Length <strong style="color:var(--text);font-weight:500">{{ report.uniprot.sequence_length }} aa</strong></span>
  </div>
</div>

<!-- Stats -->
<div class="stats">
  <div class="stat"><div class="stat-n" style="color:var(--blue)">{{ report.num_pdb_structures }}</div><div class="stat-l">PDB Structures</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--green)">{{ report.num_bioactivities }}</div><div class="stat-l">Bioactivities</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--orange)">{{ report.num_unique_ligands }}</div><div class="stat-l">Unique Ligands</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--purple)">{% if report.best_ligand and report.best_ligand.best_pchembl %}{{ "%.2f"|format(report.best_ligand.best_pchembl) }}{% else %}—{% endif %}</div><div class="stat-l">Best pChEMBL</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--blue)">{% if report.alphafold %}1{% else %}0{% endif %}</div><div class="stat-l">AlphaFold Model</div></div>
</div>

<!-- Protein Information -->
<div class="sec">
  <div class="sec-title">Protein information</div>
  <div class="info-grid">
    {% if report.uniprot.function_description %}
    <span class="ik">Function</span>
    <span class="iv">{{ report.uniprot.function_description }}</span>
    {% endif %}
    {% if report.uniprot.subcellular_locations %}
    <span class="ik">Subcellular</span>
    <span class="iv">{% for loc in report.uniprot.subcellular_locations %}<span class="tag t-blue">{{ loc }}</span>{% endfor %}</span>
    {% endif %}
    {% if report.uniprot.disease_associations %}
    <span class="ik">Diseases</span>
    <span class="iv" style="color:var(--muted)">{{ report.uniprot.disease_associations[:5] | join(", ") }}</span>
    {% endif %}
    {% if report.uniprot.keywords %}
    <span class="ik">Keywords</span>
    <span class="iv">{% for kw in report.uniprot.keywords[:15] %}<span class="tag t-purple">{{ kw }}</span>{% endfor %}</span>
    {% endif %}
    {% if report.uniprot.go_terms %}
    <span class="ik">GO Terms</span>
    <span class="iv">
      {% set go_by_cat = {} %}
      {% for go in report.uniprot.go_terms %}{% if go.category not in go_by_cat %}{% set _ = go_by_cat.update({go.category: []}) %}{% endif %}{% set _ = go_by_cat[go.category].append(go.term) %}{% endfor %}
      {% for cat, terms in go_by_cat.items() %}
      <div style="margin-bottom:.4rem">
        <span style="font-size:10.5px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;font-weight:600;margin-right:.4rem">{{ cat.replace('_',' ') }}</span>
        {% set tcls = {"molecular_function":"t-green","biological_process":"t-blue","cellular_component":"t-purple"} %}
        {% for t in terms[:8] %}<span class="tag {{ tcls.get(cat,'t-gray') }}">{{ t }}</span>{% endfor %}
      </div>
      {% endfor %}
    </span>
    {% endif %}
  </div>
</div>

<!-- Bioactivity Analysis (before 3D so it loads fast) -->
{% if report.bioactivities %}
<div class="sec">
  <div class="sec-title">Bioactivity analysis</div>
  <div class="chart-grid">
    <div>
      <div style="font-size:11.5px;color:var(--dim);margin-bottom:.5rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em">pChEMBL Distribution</div>
      <div class="chart-wrap"><canvas id="pchemblChart"></canvas></div>
    </div>
    <div>
      <div style="font-size:11.5px;color:var(--dim);margin-bottom:.5rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Experimental Methods</div>
      <div class="chart-wrap"><canvas id="methodChart"></canvas></div>
    </div>
  </div>
</div>
{% endif %}

<!-- 3D Structure (collapsed by default to keep ligands visible first) -->
<details class="sec" style="padding:0">
  <summary style="padding:1.25rem 1.5rem;cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center">
    <span class="sec-title" style="margin:0">3D structure viewer</span>
    <span style="font-size:11px;color:var(--dim)">Click to expand</span>
  </summary>
  <div style="padding:0 1.5rem 1.25rem">
    <div class="viewer-toolbar">
      <select id="structSel" onchange="loadSel()">
        {% if report.alphafold %}
        <option value="{{ report.alphafold.pdb_url or 'https://alphafold.ebi.ac.uk/files/AF-' + report.uniprot.uniprot_id + '-F1-model_v4.pdb' }}" data-af="1">
          AlphaFold prediction{% if report.alphafold.mean_plddt %} (pLDDT: {{ "%.0f"|format(report.alphafold.mean_plddt) }}){% endif %}
        </option>
        {% endif %}
        {% for s in report.pdb_structures[:15] %}
        <option value="https://files.rcsb.org/download/{{ s.pdb_id }}.pdb">
          {{ s.pdb_id }}{% if s.resolution %} — {{ s.method.value|title }} ({{ "%.1f"|format(s.resolution) }} Å){% endif %}
        </option>
        {% endfor %}
      </select>
      <button onclick="setStyle('cartoon')" id="btnCartoon" class="active">Cartoon</button>
      <button onclick="setStyle('stick')">Sticks</button>
      <button onclick="setStyle('surface')">Surface</button>
    </div>
    <div id="mol-viewer"></div>
  </div>
</details>

<!-- Top Ligands -->
{% if report.ligand_summary %}
<details class="sec" open>
  <summary>
    <span style="display:flex;align-items:center;gap:.75rem">
      <span class="sec-title" style="margin:0">Top ligands by potency</span>
      <span style="font-size:11px;color:var(--dim);background:var(--bg3);border:1px solid var(--border);padding:2px 10px;border-radius:20px">{{ report.ligand_summary|length }} total</span>
    </span>
    <span class="arrow">▶</span>
  </summary>
  <div class="sec-body" style="border-top:1px solid var(--border);overflow-x:auto">
  <table>
    <thead><tr>
      <th style="width:32px">#</th><th>Name</th><th>ChEMBL</th><th>Type</th>
      <th class="r">nM</th><th class="r">pChEMBL</th><th>Assays</th><th>Sources</th>
      <th>SMILES</th>
    </tr></thead>
    <tbody>
    {% for lig in report.ligand_summary[:50] %}
    {% set pc = lig.best_pchembl %}
    <tr>
      <td style="color:var(--dim);font-size:12px">{{ loop.index }}</td>
      <td>{{ lig.name or "—" }}</td>
      <td>{% if lig.chembl_id %}<a href="https://www.ebi.ac.uk/chembl/compound_report_card/{{ lig.chembl_id }}" target="_blank" class="mono" style="font-size:11px">{{ lig.chembl_id }}</a>{% else %}<span style="color:var(--dim)">—</span>{% endif %}</td>
      <td>{% if lig.best_activity_type %}<span class="tag t-blue" style="font-size:11px">{{ lig.best_activity_type }}</span>{% else %}<span style="color:var(--dim)">—</span>{% endif %}</td>
      <td class="r mono">{% if lig.best_activity_value_nM %}{{ "%.2f"|format(lig.best_activity_value_nM) }}{% else %}—{% endif %}</td>
      <td class="r {% if pc and pc >= 9 %}pc-hi{% elif pc and pc >= 7 %}pc-md{% elif pc %}pc-lo{% endif %}">{% if pc %}{{ "%.2f"|format(pc) }}{% else %}—{% endif %}</td>
      <td style="color:var(--muted)">{{ lig.num_assays }}</td>
      <td>{% for s in lig.sources %}<span class="tag t-green" style="font-size:10.5px">{{ s }}</span>{% endfor %}</td>
      <td class="mono" style="font-size:10px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{{ lig.smiles }}">{{ lig.smiles[:50] }}{% if lig.smiles|length > 50 %}…{% endif %}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</details>
{% endif %}

<!-- PDB Structures -->
{% if report.pdb_structures %}
<details class="sec" open>
  <summary>
    <span style="display:flex;align-items:center;gap:.75rem">
      <span class="sec-title" style="margin:0">PDB structures</span>
      <span style="font-size:11px;color:var(--dim);background:var(--bg3);border:1px solid var(--border);padding:2px 10px;border-radius:20px">{{ report.num_pdb_structures }} total</span>
    </span>
    <span class="arrow">▶</span>
  </summary>
  <div class="sec-body" style="border-top:1px solid var(--border);overflow-x:auto">
  <table>
    <thead><tr><th>PDB ID</th><th>Method</th><th class="r">Resolution</th><th>Date</th><th>Ligands</th><th>Title</th></tr></thead>
    <tbody>
    {% for s in report.pdb_structures %}
    {% set mcls = {"X-RAY DIFFRACTION":"t-blue","ELECTRON MICROSCOPY":"t-purple","SOLUTION NMR":"t-green"} %}
    <tr>
      <td><a href="https://www.rcsb.org/structure/{{ s.pdb_id }}" target="_blank" class="mono" style="font-weight:600">{{ s.pdb_id }}</a></td>
      <td><span class="tag {{ mcls.get(s.method.value,'t-gray') }}" style="font-size:11px">{{ s.method.value }}</span></td>
      <td class="r mono">{% if s.resolution %}{{ "%.2f"|format(s.resolution) }} Å{% else %}—{% endif %}</td>
      <td style="color:var(--muted)">{{ s.release_date or "—" }}</td>
      <td>{% for l in s.ligands %}<span class="tag t-gray" style="font-size:10.5px">{{ l.ligand_id }}</span>{% else %}<span style="color:var(--dim)">—</span>{% endfor %}</td>
      <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)">{{ s.title[:100] }}{% if s.title|length > 100 %}…{% endif %}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</details>
{% endif %}

<!-- AI Analysis -->
{% if report.ai_analysis %}
<div class="sec">
  <div class="sec-title">AI Analysis</div>
  <div class="ai-box">{{ report.ai_analysis }}</div>
</div>
{% endif %}

<div class="footer">
  Generated by <strong>TargetRecon v{{ report.targetrecon_version }}</strong>
  on {{ report.generated_at.strftime('%Y-%m-%d %H:%M UTC') }}
  &nbsp;&middot;&nbsp; Data from UniProt &middot; RCSB PDB &middot; AlphaFold DB &middot; ChEMBL &middot; STRING-DB
</div>
</div><!-- /wrap -->

<script>
// ── Charts ─────────────────────────────────────────────────────────────────
var PCHEMBL = {{ pchembl_json }};
var METHODS = {{ method_json }};

window.addEventListener('load', function() {
  Chart.defaults.color = '#768390';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';

  // pChEMBL histogram
  var pEl = document.getElementById('pchemblChart');
  if (pEl && PCHEMBL.length) {
    var bins = {};
    PCHEMBL.forEach(function(v) {
      var b = (Math.floor(v * 2) / 2).toFixed(1);
      bins[b] = (bins[b] || 0) + 1;
    });
    var bL = Object.keys(bins).sort(function(a,b){ return +a - +b; });
    new Chart(pEl, {
      type: 'bar',
      data: { labels: bL, datasets: [{ data: bL.map(function(k){ return bins[k]; }),
        backgroundColor: bL.map(function(v){ return +v>=9?'#3fb950':+v>=7?'#d29922':'#58a6ff'; }),
        borderRadius: 3, barPercentage: .88 }] },
      options: { responsive:true, maintainAspectRatio:false,
        plugins: { legend:{display:false}, tooltip:{backgroundColor:'#1c2128',titleColor:'#e6edf3',bodyColor:'#b1bac4',borderColor:'#30363d',borderWidth:1} },
        scales: {
          x: { grid:{display:false}, border:{color:'#30363d'}, ticks:{font:{size:10},color:'#768390'} },
          y: { border:{color:'#30363d'}, ticks:{font:{size:10},color:'#768390'} }
        }
      }
    });
  }

  // Method doughnut
  var mEl = document.getElementById('methodChart');
  var mKeys = Object.keys(METHODS);
  if (mEl && mKeys.length) {
    new Chart(mEl, {
      type: 'doughnut',
      data: { labels: mKeys, datasets: [{ data: Object.values(METHODS),
        backgroundColor: ['#58a6ff','#bc8cff','#3fb950','#d29922','#f85149'],
        borderWidth: 0, hoverOffset: 4 }] },
      options: { responsive:true, maintainAspectRatio:false, cutout:'58%',
        plugins: {
          legend: { position:'right', labels:{color:'#b1bac4',font:{size:11},boxWidth:12,padding:10} },
          tooltip: {backgroundColor:'#1c2128',titleColor:'#e6edf3',bodyColor:'#b1bac4',borderColor:'#30363d',borderWidth:1}
        }
      }
    });
  }
});

// ── 3D Viewer ──────────────────────────────────────────────────────────────
var viewer = null, currentStyle = 'cartoon';

document.querySelector('details.sec')?.addEventListener('toggle', function(e) {
  if (e.target.open && !viewer) initViewer();
});

function initViewer() {
  if (typeof $3Dmol === 'undefined') { setTimeout(initViewer, 300); return; }
  viewer = $3Dmol.createViewer(document.getElementById('mol-viewer'), { backgroundColor: '#030508', antialias: true });
  loadSel();
}

function loadSel() {
  if (!viewer) return;
  var sel = document.getElementById('structSel');
  var url = sel.value;
  var isAF = sel.options[sel.selectedIndex]?.dataset.af === '1';
  viewer.clear();
  fetch(url).then(function(r){ return r.text(); }).then(function(pdb){
    viewer.addModel(pdb, 'pdb');
    applyStyle(isAF);
    viewer.zoomTo();
    viewer.render();
  }).catch(function(e){ console.warn('Load failed:', url, e); });
}

function applyStyle(isAF) {
  viewer.setStyle({}, {});
  if (currentStyle === 'surface') {
    viewer.addSurface($3Dmol.SurfaceType.VDW, { opacity: 0.75, colorscheme: isAF ? 'bfactor' : 'spectrum' });
    return;
  }
  if (currentStyle === 'stick') {
    viewer.setStyle({}, { stick: { radius: 0.15 } });
  } else {
    if (isAF) {
      viewer.setStyle({}, { cartoon: { colorfunc: function(a) {
        return a.b > 90 ? '#0053d6' : a.b > 70 ? '#65cbf3' : a.b > 50 ? '#ffdb13' : '#ff7d45';
      }}});
    } else {
      viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
      viewer.setStyle({ hetflag: true }, { stick: { colorscheme: 'greenCarbon', radius: 0.15 } });
    }
  }
}

function setStyle(s) {
  currentStyle = s;
  document.querySelectorAll('.viewer-toolbar button').forEach(function(b){ b.classList.remove('active'); });
  var btnMap = { cartoon: 'btnCartoon', stick: 'btnStick', surface: 'btnSurface' };
  // just mark all active state by matching text
  document.querySelectorAll('.viewer-toolbar button').forEach(function(b){
    if (b.textContent.toLowerCase().includes(s.slice(0,4))) b.classList.add('active');
  });
  if (!viewer) return;
  var sel = document.getElementById('structSel');
  var isAF = sel?.options[sel.selectedIndex]?.dataset.af === '1';
  applyStyle(isAF);
  viewer.render();
}
</script>
</body>
</html>"""


def render_html(report: TargetReport) -> str:
    import json
    from jinja2 import Environment

    env = Environment(autoescape=False)
    env.filters["tojson"] = lambda x: json.dumps(x)

    pchembl_vals = [r.pchembl_value for r in report.bioactivities if r.pchembl_value]
    method_counts: dict[str, int] = {}
    for s in report.pdb_structures:
        method_counts[s.method.value] = method_counts.get(s.method.value, 0) + 1

    template = env.from_string(_TEMPLATE)
    return template.render(
        report=report,
        pchembl_json=json.dumps(pchembl_vals[:3000]),
        method_json=json.dumps(method_counts),
    )
