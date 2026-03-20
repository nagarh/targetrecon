"""Core orchestration: async recon, ligand aggregation, file export."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path

from targetrecon.models import (
    BioactivityRecord,
    LigandSummary,
    PDBStructure,
    TargetReport,
)


async def recon_async(
    query: str,
    max_pdb_resolution: float = 4.0,
    max_pdb_structures: int = 10_000,
    max_bioactivities: int = 10_000,
    min_pchembl: float | None = None,
    use_chembl: bool = True,
    use_bindingdb: bool = True,
    verbose: bool = True,
) -> TargetReport:
    from targetrecon.clients.alphafold import fetch_alphafold
    from targetrecon.clients.bindingdb import fetch_bioactivities_by_uniprot
    from targetrecon.clients.chembl import fetch_bioactivities_by_target
    from targetrecon.clients.pdb_client import fetch_structures_for_uniprot
    from targetrecon.clients.string_db import fetch_interactions
    from targetrecon.clients.uniprot import fetch_uniprot
    from targetrecon.resolver import resolve_ids

    if verbose:
        from rich.console import Console
        console = Console(stderr=True)
        console.print(f"[cyan]Resolving identifiers for '{query}'...[/cyan]")

    uniprot_id, chembl_id = await resolve_ids(query)

    if not uniprot_id:
        return TargetReport(query=query)

    # Fetch UniProt first so we get the canonical accession (merged/inactive entries
    # redirect to the canonical entry; PDB/AlphaFold/BindingDB only know the canonical ID)
    uniprot_info = await fetch_uniprot(uniprot_id)
    canonical_id = (uniprot_info.uniprot_id if uniprot_info else None) or uniprot_id

    # Prefer the ChEMBL target ID from UniProt cross-references over whatever the
    # resolver returned (which may be a compound/molecule ID when input was a compound)
    if uniprot_info and uniprot_info.chembl_id:
        chembl_id = uniprot_info.chembl_id

    if verbose:
        console.print(
            f"[cyan]UniProt: {canonical_id}  |  ChEMBL: {chembl_id or 'not found'}[/cyan]"
        )
        console.print("[cyan]Fetching data from 5 sources in parallel...[/cyan]")

    # Parallel fetch via TaskGroup (using canonical_id so PDB/AlphaFold/BindingDB resolve correctly)
    async with asyncio.TaskGroup() as tg:
        pdb_task = tg.create_task(
            fetch_structures_for_uniprot(
                canonical_id,
                max_results=max_pdb_structures,
                max_resolution=max_pdb_resolution,
            )
        )
        af_task = tg.create_task(fetch_alphafold(canonical_id))

        if chembl_id and use_chembl:
            chembl_task: asyncio.Task | None = tg.create_task(
                fetch_bioactivities_by_target(
                    chembl_id,
                    limit=max_bioactivities,
                    min_pchembl=min_pchembl,
                )
            )
        else:
            chembl_task = None

        if use_bindingdb:
            bindingdb_task: asyncio.Task | None = tg.create_task(
                fetch_bioactivities_by_uniprot(canonical_id, limit=min(max_bioactivities, 200))
            )
        else:
            bindingdb_task = None
        string_task = tg.create_task(fetch_interactions(canonical_id, limit=30))

    pdb_structures: list[PDBStructure] = pdb_task.result() or []
    alphafold = af_task.result()
    chembl_activities: list[BioactivityRecord] = (
        chembl_task.result() if chembl_task else []
    ) or []
    bindingdb_activities: list[BioactivityRecord] = (bindingdb_task.result() if bindingdb_task else []) or []
    from targetrecon.models import ProteinInteraction
    raw_interactions = string_task.result() or []
    interactions = [ProteinInteraction(**i) for i in raw_interactions]

    all_bioactivities = chembl_activities + bindingdb_activities
    if min_pchembl is not None:
        all_bioactivities = [
            r for r in all_bioactivities
            if r.pchembl_value is not None and r.pchembl_value >= min_pchembl
        ]

    ligand_summary = _aggregate_ligands(all_bioactivities, pdb_structures)

    best_ligand = max(
        (lig for lig in ligand_summary if lig.best_pchembl is not None),
        key=lambda l: l.best_pchembl or 0.0,
        default=None,
    )

    if verbose:
        console.print(
            f"[green]Done!  {len(pdb_structures)} structures · "
            f"{len(all_bioactivities)} bioactivities · "
            f"{len(ligand_summary)} unique ligands[/green]"
        )

    return TargetReport(
        query=query,
        uniprot=uniprot_info,
        pdb_structures=pdb_structures,
        alphafold=alphafold,
        bioactivities=all_bioactivities,
        ligand_summary=ligand_summary,
        interactions=interactions,
        num_pdb_structures=len(pdb_structures),
        num_bioactivities=len(all_bioactivities),
        num_unique_ligands=len(ligand_summary),
        best_ligand=best_ligand,
    )


def recon(
    query: str,
    max_pdb_resolution: float = 4.0,
    min_pchembl: float | None = None,
) -> TargetReport:
    return asyncio.run(
        recon_async(
            query,
            max_pdb_resolution=max_pdb_resolution,
            min_pchembl=min_pchembl,
        )
    )


def _canonical_smiles(smiles: str) -> str:
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            return Chem.MolToSmiles(mol)
    except Exception:
        pass
    return smiles


def _aggregate_ligands(
    bioactivities: list[BioactivityRecord],
    pdb_structures: list[PDBStructure],
) -> list[LigandSummary]:
    groups: dict[str, list[BioactivityRecord]] = defaultdict(list)
    smiles_map: dict[str, str] = {}

    for rec in bioactivities:
        if not rec.smiles:
            continue
        key = _canonical_smiles(rec.smiles)
        groups[key].append(rec)
        smiles_map.setdefault(key, rec.smiles)

    summaries: list[LigandSummary] = []
    for key, records in groups.items():
        best = max(records, key=lambda r: r.pchembl_value or 0.0)
        sources = list({r.source for r in records})
        chembl_id = next((r.molecule_chembl_id for r in records if r.molecule_chembl_id), None)
        name = next((r.name for r in records if r.name), None)

        summaries.append(
            LigandSummary(
                smiles=smiles_map[key],
                name=name,
                chembl_id=chembl_id,
                best_activity_type=best.activity_type or "",
                best_activity_value_nM=best.value,
                best_pchembl=best.pchembl_value,
                num_assays=len(records),
                sources=sources,
                pdb_ids=[],
            )
        )

    summaries.sort(key=lambda l: l.best_pchembl or 0.0, reverse=True)
    return summaries


def save_json(report: TargetReport, path: "Path | str") -> Path:
    p = Path(path)
    p.write_text(report.model_dump_json(indent=2))
    return p


def save_html(report: TargetReport, path: "Path | str") -> Path:
    from targetrecon.report import render_html
    p = Path(path)
    p.write_text(render_html(report))
    return p


def save_sdf(
    report: TargetReport,
    path: "Path | str",
    top_n: int = 0,
    min_pchembl: float | None = None,
    max_nm: float | None = None,
    activity_type: str | None = None,
) -> Path:
    p = Path(path)
    ligands = [lig for lig in report.ligand_summary if lig.smiles]

    # Apply filters
    if min_pchembl is not None:
        ligands = [l for l in ligands if l.best_pchembl and l.best_pchembl >= min_pchembl]
    if max_nm is not None:
        ligands = [l for l in ligands if l.best_activity_value_nM and l.best_activity_value_nM <= max_nm]
    if activity_type:
        ligands = [l for l in ligands if l.best_activity_type.upper() == activity_type.upper()]
    if top_n and top_n > 0:
        ligands = ligands[:top_n]

    top_ligands = ligands

    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem

        with Chem.SDWriter(str(p)) as writer:
            for lig in top_ligands:
                mol = Chem.MolFromSmiles(lig.smiles)
                if mol is None:
                    continue
                mol = Chem.AddHs(mol)
                result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
                if result == 0:
                    AllChem.MMFFOptimizeMolecule(mol)
                mol = Chem.RemoveHs(mol)
                mol.SetProp("_Name", lig.name or lig.chembl_id or "")
                mol.SetProp("ChEMBL_ID", lig.chembl_id or "")
                mol.SetProp("pChEMBL", str(lig.best_pchembl or ""))
                mol.SetProp("Activity_Type", lig.best_activity_type or "")
                mol.SetProp("Source", ",".join(lig.sources))
                writer.write(mol)
    except ImportError:
        with open(p, "w") as f:
            for lig in top_ligands:
                f.write(f"{lig.smiles}\n  TargetRecon 0.1.0\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n> <SMILES>\n{lig.smiles}\n\n$$$$\n")

    return p
