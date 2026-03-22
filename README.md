<p align="center">
  <img src="https://img.shields.io/badge/python-≥3.10-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/version-0.1.12-orange" alt="Version">
  <img src="https://img.shields.io/badge/databases-5-purple" alt="Databases">
  <img src="https://img.shields.io/pypi/v/targetrecon?color=blue" alt="PyPI">
  <a href="https://huggingface.co/spaces/hemantn/targetrecon"><img src="https://img.shields.io/badge/🤗%20HuggingFace-Spaces-yellow" alt="HuggingFace Spaces"></a>
</p>

<h1 align="center">TargetRecon</h1>
<p align="center"><b>Drug target intelligence aggregator — fetch, collate, and visualize public data for any protein target in one command.</b></p>
<p align="center">
  Aggregate UniProt · PDB · AlphaFold · ChEMBL · STRING-DB into a single interactive report — in seconds.
</p>
<p align="center">
  🚀 <strong><a href="https://huggingface.co/spaces/hemantn/targetrecon">Try it live on HuggingFace Spaces</a></strong>
</p>

---

## What is TargetRecon?

TargetRecon is a Python CLI, web app, and Jupyter-ready library for comprehensive drug target analysis. Given a gene name, UniProt accession, or ChEMBL ID, TargetRecon fetches and integrates data across **5 public databases** — protein annotations, 3D structures, predicted AlphaFold models, bioactivity profiles, and protein–protein interaction networks — into a single richly formatted interactive report.

Whether you are profiling a novel target, exploring known inhibitors, or mapping a compound to its protein targets, TargetRecon consolidates the full analysis workflow in one place. It also ships with an **Agentic AI assistant** so you can interrogate the data conversationally.

Think of it as [`gget`](https://github.com/pachterlab/gget) for drug discovery — or [TargetDB](https://github.com/sdecesco/targetDB) reimagined for the AlphaFold era.

---

## Five Data Sources, One Report

| Source | Data |
|---|---|
| **UniProt** | Function, subcellular location, GO terms, diseases, keywords |
| **RCSB PDB** | Up to 50 experimental structures, filtered by resolution (default ≤ 4.0 Å), sorted by resolution ascending |
| **AlphaFold DB** | Predicted structure with pLDDT confidence coloring |
| **ChEMBL** | Bioactivity data (IC50, Ki, Kd, EC50) sorted by pChEMBL descending |
| **STRING-DB** | Protein–protein interaction network |

### Intelligent ID Resolution

Accepts gene names, UniProt accessions, or ChEMBL target IDs:

```bash
targetrecon EGFR          # Gene name
targetrecon P00533        # UniProt accession
targetrecon CHEMBL203     # ChEMBL target ID
```

---

## Bioactivity Data

### What is pChEMBL?

pChEMBL is a unified potency scale — the negative log₁₀ of the molar affinity. Higher = more potent.

```
pChEMBL = -log₁₀(affinity_M)
```

| pChEMBL | Affinity | Interpretation |
|---|---|---|
| 9 | 1 nM | Very potent |
| 7 | 100 nM | Potent |
| 6 | 1 µM | Moderate |
| < 5 | > 10 µM | Weak |

ChEMBL natively reports pChEMBL values. TargetRecon uses this scale directly.

### Full pipeline — what happens when you run a query

```
1. Resolve query → UniProt ID / ChEMBL target ID
         │
         ▼
2. Fetch in parallel (async):
   ├── ChEMBL API  → top-N bioactivity records, sorted by pChEMBL desc (server-side)
   ├── RCSB PDB    → experimental structures
   ├── AlphaFold   → predicted structure
   └── STRING DB   → protein interactions
         │
         ▼
3. Apply min_pchembl filter (if set) to ChEMBL records
         │
         ▼
4. Deduplicate by canonical SMILES → Ligand Summary
         │
         ▼
5. Sort Ligand Summary by best pChEMBL descending
         │
         ▼
6. Output: TargetReport (bioactivities + ligand_summary + structures + ...)
```

### Fetching strategy

**ChEMBL** — server-side sort + pagination:
- Sends `order_by=-pchembl_value` to the API
- Only the top-N most potent records are fetched — no wasted API calls
- Records with no pChEMBL value are excluded at the API level

### Cap behavior

The default is **1000 records**:

| Setting | ChEMBL | Total |
|---|---|---|
| Default (1000) | top 1000 most potent | up to 1000 |
| `--max-bioactivities 500` | top 500 most potent | up to 500 |
| `--max-bioactivities all` | all records | all available |

Because sorting happens **before** the cap, you always get the most potent compounds — never a random subset.

| Interface | No-limit syntax |
|---|---|
| CLI | `--max-bioactivities all` |
| Web UI | Drag the *Max bioactivities* slider to **All** |
| Python API | `max_bioactivities=None` |

### Ligand deduplication

ChEMBL records are grouped by **canonical SMILES** (via RDKit). If the same molecule appears in multiple assays:
- It becomes **one entry** in the Ligand Summary
- The **best pChEMBL** across all assays is kept
- `num_assays` counts the total assay measurements

The final Ligand Summary is sorted by best pChEMBL descending — the most potent unique compound is always first.

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
targetrecon CDK2 --max-bioactivities 5000         # up to 5000 records
targetrecon CDK2 --max-bioactivities all          # no limit
```

| Option | Default | Description |
|---|---|---|
| `-f, --format [json\|html\|sdf]` | `html json sdf` | Output formats (repeat for multiple) |
| `-o, --output PATH` | `.` | Output directory |
| `--max-resolution FLOAT` | `4.0` | Max PDB resolution in Å (up to 50 structures returned, sorted by resolution) |
| `--max-bioactivities INT\|all` | `1000` | Max ChEMBL bioactivity records; `all` = no limit |
| `--min-pchembl FLOAT` | — | Minimum pChEMBL value filter |
| `--top-ligands INT` | `20` | Number of top ligands for SDF export |
| `-q, --quiet` | off | Suppress progress messages |

### `targetrecon batch` — Multiple targets

```bash
# Pass targets directly
targetrecon batch EGFR BRAF CDK2 ABL1

# From a file (one target per line, # = comment)
targetrecon batch -i targets.txt

# With filters and format selection
targetrecon batch -i targets.txt -f html -f sdf --min-pchembl 6.0 --skip-errors

# Unlimited bioactivities
targetrecon batch -i targets.txt --max-bioactivities all
```

| Option | Default | Description |
|---|---|---|
| `-i, --input PATH` | — | Text file, one target per line |
| `-o, --output PATH` | `./batch_reports` | Output directory |
| `-f, --format [json\|html\|sdf]` | `html json sdf` | Output formats (repeat for multiple) |
| `--max-resolution FLOAT` | `4.0` | Max PDB resolution in Å (up to 50 structures returned, sorted by resolution) |
| `--max-bioactivities INT\|all` | `1000` | Max ChEMBL bioactivity records; `all` = no limit |
| `--min-pchembl FLOAT` | — | Minimum pChEMBL value filter |
| `--top-ligands INT` | `20` | Ligands per SDF file |
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
- Sidebar controls: max PDB resolution, min pChEMBL, ChEMBL toggle, **max bioactivities slider** (100–5000, or drag to **All** for no limit)

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
print(report.num_bioactivities)          # up to 1000 (default ChEMBL cap)
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
    max_bioactivities=2000,
    # max_bioactivities=None  # no limit
))
```

### Accessing the data

```python
# UniProt info
report.uniprot.protein_name           # e.g. "Epidermal growth factor receptor"
report.uniprot.gene_name              # e.g. "EGFR"
report.uniprot.organism               # e.g. "Homo sapiens"
report.uniprot.function_description   # functional annotation text
report.uniprot.subcellular_locations  # list[str]
report.uniprot.disease_associations   # list[str]
report.uniprot.keywords               # list[str]
report.uniprot.go_terms               # list[GoTerm] — each has .go_id, .term, .category
report.uniprot.sequence_length        # int

# PDB structures
for pdb in report.pdb_structures[:5]:
    print(pdb.pdb_id, pdb.resolution, pdb.method)
    for lig in pdb.ligands:           # list[PDBLigand] — each has .ligand_id, .smiles, .name
        print(lig.ligand_id, lig.name)

# AlphaFold
report.alphafold.pdb_url        # URL to AlphaFold PDB structure
report.alphafold.model_url      # URL to AlphaFold CIF model

# Bioactivity records (sorted by pChEMBL descending)
for b in report.bioactivities[:10]:
    print(b.source, b.activity_type, b.value, b.pchembl_value, b.smiles)

# Ligand summary (deduplicated by canonical SMILES, sorted by best pChEMBL)
for lig in report.ligand_summary[:10]:
    print(lig.name, lig.chembl_id, lig.best_pchembl, lig.best_activity_type, lig.num_assays)
    print(lig.sources)                # e.g. ["ChEMBL"]

report.best_ligand               # most potent unique ligand overall
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

**Quick start:**
```bash
targetrecon EGFR
```
Produces `EGFR_report.html` (interactive, self-contained), `EGFR_report.json`, and `EGFR_top_ligands.sdf` — ready for docking.

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
    └── string_db.py # STRING-DB REST API
```

---

## Author

**Hemantn Nagar**
📧 [hn533621@ohio.edu](mailto:hn533621@ohio.edu)
🔗 [github.com/nagarh](https://github.com/nagarh)

---

## References

Data from: [UniProt](https://www.uniprot.org/) · [RCSB PDB](https://www.rcsb.org/) · [AlphaFold DB](https://alphafold.ebi.ac.uk/) · [ChEMBL](https://www.ebi.ac.uk/chembl/) · [STRING-DB](https://string-db.org/)

Visualization: [3Dmol.js](https://3dmol.csb.pitt.edu/) · [Chart.js](https://www.chartjs.org/) · [Cytoscape.js](https://js.cytoscape.org/)

Sketcher: [Ketcher](https://github.com/epam/ketcher)

Inspired by [TargetDB](https://github.com/sdecesco/targetDB) and [gget](https://github.com/pachterlab/gget).

---

## License

MIT License — see [LICENSE](LICENSE) for details.
