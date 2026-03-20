<p align="center">
  <img src="https://img.shields.io/badge/python-≥3.10-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/version-0.1.0-orange" alt="Version">
  <img src="https://img.shields.io/badge/databases-5-purple" alt="Databases">
</p>

<h1 align="center">TargetRecon</h1>
<p align="center"><b>Drug target intelligence in one command.</b></p>
<p align="center">
  Aggregate UniProt · PDB · AlphaFold · ChEMBL · BindingDB into a single interactive report — in seconds.
</p>

---

```bash
pip install targetrecon
targetrecon EGFR
```

Produces `EGFR_report.html` (interactive, self-contained), `EGFR_report.json`, and `EGFR_top_ligands.sdf` — ready for docking.

---

## What is TargetRecon?

TargetRecon is a Python CLI and web app that pulls data from **5 public databases** and compiles it into a single, richly formatted report for any protein drug target. No API keys. No account. No manual copy-pasting.

Think of it as [`gget`](https://github.com/pachterlab/gget) for drug discovery — or [TargetDB](https://github.com/sdecesco/targetDB) reimagined for the AlphaFold era.

---

## Five Data Sources, One Report

| Source | Data |
|---|---|
| **UniProt** | Function, subcellular location, GO terms, diseases, keywords |
| **RCSB PDB** | Experimental structures filtered by resolution |
| **AlphaFold DB** | Predicted structure with pLDDT confidence coloring |
| **ChEMBL** | Bioactivity data (IC50, Ki, Kd, EC50) sorted by pChEMBL descending |
| **BindingDB** | Binding affinity measurements converted to pChEMBL, sorted by potency |

### Intelligent ID Resolution

Accepts gene names, UniProt accessions, or ChEMBL target IDs:

```bash
targetrecon EGFR          # Gene name
targetrecon P00533        # UniProt accession
targetrecon CHEMBL203     # ChEMBL target ID
```

---

## Bioactivity Data

### Sorting
Both ChEMBL and BindingDB results are **sorted by pChEMBL descending** — most potent compounds always come first, regardless of the cap:

- **ChEMBL**: `order_by=-pchembl_value` sent directly to the API, so only the top-N most potent records are fetched (efficient, no wasted API calls).
- **BindingDB**: all records fetched in a single request, then sorted by pChEMBL descending client-side before applying the cap.

### BindingDB → pChEMBL conversion
BindingDB reports raw affinity values in nM. TargetRecon converts them to pChEMBL using the same formula as ChEMBL:

```
pChEMBL = -log₁₀(affinity_nM × 10⁻⁹) = -log₁₀(affinity_M)
```

This makes ChEMBL and BindingDB values directly comparable on the same scale.

### Configurable limit
The default cap is **1000 per source** (up to 1000 ChEMBL + up to 1000 BindingDB). Since results are sorted by potency, the default captures all practically relevant compounds for most targets.

| Interface | No-limit syntax |
|---|---|
| CLI | `--max-bioactivities all` |
| Web UI | Move the *Max bioactivities* slider to **All** |
| Python API | `max_bioactivities=None` |

---

## CLI

```bash
pip install targetrecon
```

### `targetrecon` / `targetrecon run` — Single target

```bash
targetrecon EGFR
targetrecon P00533 -f html -f json -f sdf -o ./reports/
targetrecon BRAF --min-pchembl 7.0 --max-resolution 2.5
targetrecon CDK2 --max-bioactivities 5000         # up to 5000 per source
targetrecon CDK2 --max-bioactivities all          # no limit
targetrecon CDK2 --no-bindingdb                   # ChEMBL only
targetrecon CDK2 --no-chembl                      # BindingDB only
```

| Option | Default | Description |
|---|---|---|
| `-f, --format [json\|html\|sdf]` | `html json sdf` | Output formats (repeat for multiple) |
| `-o, --output PATH` | `.` | Output directory |
| `--max-resolution FLOAT` | `4.0` | Max PDB resolution in Å |
| `--max-bioactivities INT\|all` | `1000` | Max records per source; `all` = no limit |
| `--min-pchembl FLOAT` | — | Minimum pChEMBL value filter |
| `--top-ligands INT` | `20` | Number of top ligands for SDF export |
| `--use-chembl / --no-chembl` | on | Include ChEMBL bioactivity data |
| `--use-bindingdb / --no-bindingdb` | on | Include BindingDB bioactivity data |
| `-q, --quiet` | off | Suppress progress messages |

### `targetrecon batch` — Multiple targets

```bash
# Pass targets directly
targetrecon batch EGFR BRAF CDK2 ABL1

# From a file (one target per line, # = comment)
targetrecon batch -i targets.txt

# With filters and format selection
targetrecon batch -i targets.txt -f html -f sdf --min-pchembl 6.0 --skip-errors

# ChEMBL only for all targets
targetrecon batch EGFR BRAF --no-bindingdb

# Unlimited bioactivities
targetrecon batch -i targets.txt --max-bioactivities all
```

| Option | Default | Description |
|---|---|---|
| `-i, --input PATH` | — | Text file, one target per line |
| `-o, --output PATH` | `./batch_reports` | Output directory |
| `-f, --format [json\|html\|sdf]` | `html json sdf` | Output formats (repeat for multiple) |
| `--max-resolution FLOAT` | `4.0` | Max PDB resolution in Å |
| `--max-bioactivities INT\|all` | `1000` | Max records per source; `all` = no limit |
| `--min-pchembl FLOAT` | — | Minimum pChEMBL value filter |
| `--top-ligands INT` | `20` | Ligands per SDF file |
| `--use-chembl / --no-chembl` | on | Include ChEMBL bioactivity data |
| `--use-bindingdb / --no-bindingdb` | on | Include BindingDB bioactivity data |
| `--skip-errors` | off | Continue if a single target fails |
| `-q, --quiet` | off | Suppress progress messages |

After completion, a summary table is printed showing structures / bioactivities / ligands per target.

### `targetrecon serve` — Launch web interface

```bash
targetrecon serve                  # http://localhost:5000
targetrecon serve --port 8080
targetrecon serve --host 0.0.0.0   # expose on all interfaces
```

| Option | Default | Description |
|---|---|---|
| `--port INT` | `5000` | Port to listen on |
| `--host TEXT` | `0.0.0.0` | Host to bind |
| `--debug` | off | Enable Flask debug mode |

---

## Web UI

```bash
targetrecon serve
# Open http://localhost:5000
```

- Dark-themed interface with animated molecular backdrop
- Search by gene name, UniProt accession, or ChEMBL target ID
- **Molecule sketcher** (Ketcher) — draw a structure to find matching targets
- Sidebar controls: max PDB resolution, min pChEMBL, ChEMBL/BindingDB toggles, **max bioactivities slider** (100–5000, or drag to **All** for no limit)

### Report tabs

| Tab | Contents |
|---|---|
| **Overview** | UniProt summary, GO terms, diseases, protein stats |
| **3D Viewer** | AlphaFold pLDDT coloring + PDB experimental structures (3Dmol.js) |
| **Bioactivity** | pChEMBL distribution histogram, method breakdown chart |
| **Ligands** | Sortable table ranked by potency — SMILES, ChEMBL links, activity type, source |
| **PDB** | All experimental structures with resolution, method, ligand count |
| **Interactions** | STRING protein–protein interaction network (Cytoscape.js) |

### Export from the UI
Every report page has one-click download buttons:
- **JSON** — full machine-readable report
- **HTML** — self-contained interactive report (works fully offline)
- **SDF** — top ligands with 3D conformers, ready for docking

---

## AI Agent

An AI chat panel is available on every report page. Click the **AI** button (bottom-right corner) to open it.

### Providers & models

| Provider | Models |
|---|---|
| **Anthropic** | claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5 |
| **OpenAI** | gpt-4o, gpt-4o-mini |
| **Groq** | llama-3.3-70b, mixtral |

- Bring your own API key — keys are never stored, forgotten after each browser session
- Context-aware: the agent already knows the target you're looking at
- **Tools**: search targets, fetch bioactivities, query PDB structures, protein interactions, compare targets
- Streaming responses with stop button
- Resizable and minimizable panel

### Example questions
```
What are the best scaffolds for covalent inhibition?
Which PDB structures are most suitable for docking?
Compare the selectivity profile of this target vs CDK4.
Summarize the druggability of this target.
```

---

## Python API

```python
import targetrecon

# Single target — works in scripts and Jupyter
report = targetrecon.recon("EGFR")
print(report.uniprot.protein_name)      # "Epidermal growth factor receptor"
print(report.num_pdb_structures)         # 50
print(report.num_bioactivities)          # up to 2000 (1000 ChEMBL + 1000 BindingDB)
print(report.best_ligand.best_pchembl)   # e.g. 10.52

# With options
report = targetrecon.recon(
    "BRAF",
    max_bioactivities=5000,   # up to 5000 per source
    min_pchembl=7.0,
    max_pdb_resolution=2.5,
)

# No limit — fetch all available records
report = targetrecon.recon("BRAF", max_bioactivities=None)

# Async (for use with asyncio.run or inside async functions)
import asyncio
report = asyncio.run(targetrecon.recon_async("BRAF"))

# Async with all options
report = asyncio.run(targetrecon.recon_async(
    "CDK2",
    use_chembl=True,
    use_bindingdb=False,      # ChEMBL only
    max_bioactivities=2000,
    # max_bioactivities=None  # no limit
))
```

### Accessing the data

```python
# UniProt info
report.uniprot.protein_name
report.uniprot.gene_name
report.uniprot.organism
report.uniprot.function
report.uniprot.subcellular_location
report.uniprot.diseases          # list[str]
report.uniprot.go_terms          # list[str]

# PDB structures
for pdb in report.pdb_structures[:5]:
    print(pdb.pdb_id, pdb.resolution, pdb.method, pdb.ligand_ids)

# AlphaFold
report.alphafold.pdb_url         # URL to AlphaFold structure
report.alphafold.confidence_url  # pLDDT scores

# Bioactivity records (sorted by pChEMBL descending)
for b in report.bioactivities[:10]:
    print(b.source, b.activity_type, b.value, b.pchembl_value, b.smiles)

# Ligand summary (deduplicated, sorted by best pChEMBL)
for lig in report.ligand_summary[:10]:
    print(lig.name, lig.chembl_id, lig.best_pchembl, lig.best_activity_type, lig.num_assays)

report.best_ligand               # most potent ligand overall
```

### Export

```python
from targetrecon.core import save_html, save_json, save_sdf

save_html(report, "EGFR_report.html")
save_json(report, "EGFR_report.json")

# SDF with filters
save_sdf(report, "EGFR_ligands.sdf",
         top_n=50,              # limit to top 50
         min_pchembl=7.0,       # only pChEMBL ≥ 7
         activity_type="IC50")  # only IC50 records
```

### Batch (async, concurrent)

```python
import asyncio, targetrecon

async def run_batch(targets):
    reports = await asyncio.gather(*[
        targetrecon.recon_async(t) for t in targets
    ])
    return reports

reports = asyncio.run(run_batch(["EGFR", "BRAF", "CDK2"]))
for r in reports:
    print(r.uniprot.gene_name, r.num_bioactivities, r.num_unique_ligands)
```

---

## Comparison

| Feature | TargetRecon | TargetDB (2020) | gget | Open Targets |
|---|:---:|:---:|:---:|:---:|
| AlphaFold integration | ✅ | ❌ | ✅ | ✅ (web) |
| ChEMBL bioactivity | ✅ | ✅ | ❌ | Partial |
| BindingDB binding constants | ✅ | ❌ | ❌ | ❌ |
| Interactive HTML report | ✅ | ❌ | ❌ | Web only |
| 3D structure viewer | ✅ | ❌ | ❌ | Web only |
| Molecule sketcher → targets | ✅ | ❌ | ❌ | ❌ |
| Docking-ready SDF export | ✅ | ❌ | ❌ | ❌ |
| AI agent chat | ✅ | ❌ | ❌ | ❌ |
| Batch CLI processing | ✅ | ❌ | ✅ | N/A |
| pip install + single command | ✅ | Partial | ✅ | N/A |

---

## Installation

```bash
pip install targetrecon
```

**Development:**
```bash
git clone https://github.com/nagarh/targetrecon.git
cd targetrecon
pip install -e ".[dev]"
```

---

## Architecture

```
src/targetrecon/
├── cli.py           # Click CLI — run, batch, serve
├── webapp.py        # Flask web app — UI, report pages, AI agent routes
├── core.py          # Orchestration, aggregation, export (HTML/JSON/SDF)
├── models.py        # Pydantic data models
├── resolver.py      # Gene → UniProt → ChEMBL ID resolution
├── report.py        # Jinja2 HTML report generator (standalone)
├── agent_chat.py    # AI agent — tool definitions, streaming, multi-provider
└── clients/
    ├── uniprot.py   # UniProt REST API
    ├── pdb_client.py# RCSB PDB REST + Search API
    ├── alphafold.py # AlphaFold Database API
    ├── chembl.py    # ChEMBL REST API
    └── bindingdb.py # BindingDB REST API
```

---

## Acknowledgments

Data from: [UniProt](https://www.uniprot.org/) · [RCSB PDB](https://www.rcsb.org/) · [AlphaFold DB](https://alphafold.ebi.ac.uk/) · [ChEMBL](https://www.ebi.ac.uk/chembl/) · [BindingDB](https://www.bindingdb.org/)

Visualization: [3Dmol.js](https://3dmol.csb.pitt.edu/) · [Chart.js](https://www.chartjs.org/) · [Cytoscape.js](https://js.cytoscape.org/)

Sketcher: [Ketcher](https://github.com/epam/ketcher)

Inspired by [TargetDB](https://github.com/sdecesco/targetDB) and [gget](https://github.com/pachterlab/gget).

---

## License

MIT License — see [LICENSE](LICENSE) for details.
