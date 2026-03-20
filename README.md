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

Produces `EGFR_report.html` (interactive, self-contained), `EGFR_report.json`, and `EGFR_ligands.sdf` — ready for docking.

---

## What is TargetRecon?

TargetRecon is a Python CLI and web app that pulls data from **5 public databases** and compiles it into a single, richly formatted report for any protein drug target. No API keys. No account. No manual copy-pasting.

Think of it as [`gget`](https://github.com/pachterlab/gget) for drug discovery — or [TargetDB](https://github.com/sdecesco/targetDB) reimagined for the AlphaFold era.

---

## Features

### 🔍 Intelligent ID Resolution
Accepts gene names, UniProt accessions, or ChEMBL target IDs:
```bash
targetrecon EGFR          # Gene name
targetrecon P00533        # UniProt accession
targetrecon CHEMBL203     # ChEMBL target ID
```

### 📊 Five Data Sources, One Report
| Source | Data |
|---|---|
| **UniProt** | Function, subcellular location, GO terms, diseases, keywords |
| **RCSB PDB** | Experimental structures filtered by resolution, ligand extraction |
| **AlphaFold DB** | Predicted structure with pLDDT confidence coloring |
| **ChEMBL** | Bioactivity data (IC50, Ki, Kd, EC50) with pChEMBL values |
| **BindingDB** | Complementary binding affinity measurements |

### 🌐 Interactive Web UI
```bash
targetrecon serve              # Launch at http://localhost:5000
targetrecon serve --port 8080  # Custom port
```
- Dark-themed interface with animated molecular backdrop
- Structure search by gene name, UniProt ID, or ChEMBL ID
- **Molecule sketcher** (Ketcher) — draw a structure → find targets
- Full report with tabbed layout: Overview, 3D Viewer, Bioactivity, Ligands, PDB, AI Agent

### 🤖 AI Agent Chat Panel
Built-in AI assistant embedded in every report page:
- **Multi-provider**: Anthropic (claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5), OpenAI (gpt-4o, gpt-4o-mini), Groq (llama-3.3-70b, mixtral)
- Bring your own API key — keys are never stored, forgotten after each browser session
- Context-aware: agent already knows the target you're looking at
- Tools: search targets, fetch bioactivities, query PDB, protein interactions, compare targets
- Streaming responses with stop button, resizable/minimizable panel

### 🧬 Interactive HTML Report (self-contained)
- **3Dmol.js** embedded structure viewer — AlphaFold pLDDT coloring, PDB experimental structures
- **Chart.js** pChEMBL distribution histogram + method breakdown doughnut chart
- Collapsible sections: Ligands table, PDB structures, 3D viewer
- Sortable ligand table ranked by potency with SMILES, ChEMBL links, activity type, source
- Download as HTML — works fully offline, no server needed

### 💊 Docking-Ready Ligand Export
```bash
targetrecon EGFR --format sdf          # Top 20 ligands as SDF
targetrecon EGFR -f html -f json -f sdf  # All formats
```
- MMFF force field optimized 3D conformers via RDKit
- Properties embedded: pChEMBL, activity type, source database
- Ready for AutoDock Vina, Glide, GOLD, or any docking tool

### 📦 Batch Processing
```bash
# Multiple targets at once
targetrecon batch EGFR BRAF CDK2 ABL1

# From a file (one target per line, # = comment)
targetrecon batch --file targets.txt --format html sdf

# With filters
targetrecon batch --file targets.txt --min-pchembl 6.0 --skip-errors
```
Progress table printed after completion showing structures/bioactivities/ligands per target.

### 📤 Ligand Export with Filters
```bash
# Export top 50 potent ligands as SDF
targetrecon export EGFR --format sdf --min-pchembl 7.0 --top 50

# Multiple targets
targetrecon export EGFR BRAF CDK2 --format csv --min-pchembl 6.0

# From file, filter by activity type and max concentration
targetrecon export --file targets.txt --activity-type IC50 --max-nm 100
```
Exports SDF or CSV with SMILES, name, ChEMBL ID, activity values, pChEMBL, and source databases.

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

## CLI Reference

### `targetrecon` / `targetrecon run`
```
targetrecon EGFR
targetrecon BRAF --format html json sdf --output ./reports/
targetrecon CDK2 --max-resolution 2.5 --min-pchembl 7.0 -q

Options:
  -f, --format [json|html|sdf]   Output format, repeat for multiple: -f html -f sdf
  -o, --output PATH              Output directory (default: .)
  --max-resolution FLOAT         Max PDB resolution in Å (default: 4.0)
  --min-pchembl FLOAT            Minimum pChEMBL filter
  --top-ligands INT              Ligands for SDF export (default: 20)
  -q, --quiet                    Suppress progress messages
```

### `targetrecon serve`
```
targetrecon serve                  # http://localhost:5000
targetrecon serve --port 8080
targetrecon serve --host 0.0.0.0
```

### `targetrecon batch`
```
targetrecon batch EGFR BRAF CDK2
targetrecon batch -i targets.txt
targetrecon batch -i targets.txt -f html -f sdf --min-pchembl 6.0 --skip-errors

Options:
  -i, --input PATH               Text file, one target per line
  -o, --output PATH              Output directory (default: ./batch_reports)
  -f, --format [json|html|sdf]   Output formats (repeat for multiple)
  --max-resolution FLOAT         Max PDB resolution in Å (default: 4.0)
  --min-pchembl FLOAT            Minimum pChEMBL filter
  --skip-errors                  Continue if a single target fails
```

### `targetrecon export`
```
targetrecon export EGFR -f sdf --min-pchembl 7.0 --top 50
targetrecon export EGFR BRAF CDK2 -f csv
targetrecon export -i targets.txt --max-nm 100 --activity-type IC50

Options:
  -i, --input PATH               Text file, one target per line
  -f, --format [sdf|csv]         Export format (default: sdf)
  --min-pchembl FLOAT            Min pChEMBL filter
  --max-nm FLOAT                 Max activity value in nM
  --activity-type TEXT           Filter by type: IC50, Ki, Kd, EC50
  --top INT                      Max ligands per target (default: 50)
```

---

## Python API

```python
import targetrecon

# Single target
report = targetrecon.recon("EGFR")
print(report.uniprot.protein_name)      # "Epidermal growth factor receptor"
print(report.num_pdb_structures)         # 450+
print(report.best_ligand.best_pchembl)   # e.g., 10.52

# Export
from targetrecon.core import save_html, save_json, save_sdf
save_html(report, "EGFR_report.html")
save_json(report, "EGFR_report.json")
save_sdf(report, "EGFR_ligands.sdf", top_n=50)

# Async
import asyncio
report = asyncio.run(targetrecon.recon_async("BRAF"))
```

---

## Architecture

```
src/targetrecon/
├── cli.py           # Click CLI — run, serve, batch, export
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
