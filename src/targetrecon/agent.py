"""AI agent support: use Claude to analyze TargetRecon reports."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from targetrecon.models import TargetReport


def _build_context(report: "TargetReport") -> str:
    """Build a concise text summary of the report for Claude."""
    lines = []

    if report.uniprot:
        u = report.uniprot
        lines.append(f"Target: {u.gene_name or report.query} ({u.protein_name})")
        lines.append(f"UniProt: {u.uniprot_id} | Organism: {u.organism} | Length: {u.sequence_length} aa")
        if u.chembl_id:
            lines.append(f"ChEMBL target: {u.chembl_id}")
        if u.function_description:
            lines.append(f"Function: {u.function_description[:500]}")
        if u.subcellular_locations:
            lines.append(f"Location: {', '.join(u.subcellular_locations)}")
        if u.disease_associations:
            lines.append(f"Diseases: {'; '.join(u.disease_associations[:5])}")
        if u.keywords:
            lines.append(f"Keywords: {', '.join(u.keywords[:15])}")

    lines.append(f"\nPDB structures: {report.num_pdb_structures}")
    if report.pdb_structures:
        methods: dict[str, int] = {}
        for s in report.pdb_structures:
            methods[s.method.value] = methods.get(s.method.value, 0) + 1
        lines.append(f"Methods: {', '.join(f'{m}: {c}' for m, c in methods.items())}")
        res_list = [s.resolution for s in report.pdb_structures if s.resolution]
        if res_list:
            lines.append(f"Resolution range: {min(res_list):.1f}-{max(res_list):.1f} A")

    if report.alphafold:
        af = report.alphafold
        lines.append(f"\nAlphaFold model: available (pLDDT: {af.mean_plddt:.1f})" if af.mean_plddt else "\nAlphaFold model: available")

    lines.append(f"\nBioactivities: {report.num_bioactivities}")
    lines.append(f"Unique ligands: {report.num_unique_ligands}")

    if report.best_ligand:
        bl = report.best_ligand
        lines.append(
            f"Best ligand: {bl.name or bl.chembl_id or 'unknown'} "
            f"(pChEMBL: {bl.best_pchembl:.2f}, {bl.best_activity_type})"
            if bl.best_pchembl
            else f"Best ligand: {bl.name or bl.chembl_id or 'unknown'}"
        )

    if report.ligand_summary:
        top5 = report.ligand_summary[:5]
        lines.append("\nTop 5 ligands by potency:")
        for i, lig in enumerate(top5, 1):
            lines.append(
                f"  {i}. {lig.name or lig.chembl_id or 'unknown'} "
                f"(pChEMBL: {lig.best_pchembl:.2f}, {lig.best_activity_type})"
                if lig.best_pchembl
                else f"  {i}. {lig.name or lig.chembl_id or 'unknown'}"
            )

    return "\n".join(lines)


async def analyze_async(
    report: "TargetReport",
    question: str | None = None,
    api_key: str | None = None,
    model: str = "claude-opus-4-6",
) -> str:
    """Analyze a TargetReport using Claude. Returns the analysis text."""
    try:
        import anthropic
    except ImportError:
        return (
            "AI analysis requires the anthropic package. "
            "Install it with: pip install anthropic"
        )

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return (
            "AI analysis requires an Anthropic API key. "
            "Set the ANTHROPIC_API_KEY environment variable or pass --api-key."
        )

    context = _build_context(report)

    if question:
        prompt = (
            f"You are a drug discovery expert analyzing public database data for a protein target.\n\n"
            f"Target data summary:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Provide a concise, expert answer based on the data above."
        )
    else:
        gene = (report.uniprot.gene_name if report.uniprot else None) or report.query
        prompt = (
            f"You are a drug discovery expert. Analyze the following public database data "
            f"for the protein target {gene} and provide:\n"
            f"1. A brief summary of the target's biological role and disease relevance\n"
            f"2. Assessment of druggability (structural coverage, binding pockets)\n"
            f"3. Key insights from the bioactivity data (potency range, activity types)\n"
            f"4. Notable ligands or scaffolds\n"
            f"5. Recommendations for drug discovery (which structures to prioritize, knowledge gaps)\n\n"
            f"Target data:\n{context}\n\n"
            f"Be concise and actionable. Use drug discovery terminology."
        )

    client = anthropic.AsyncAnthropic(api_key=key)
    message = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def analyze(
    report: "TargetReport",
    question: str | None = None,
    api_key: str | None = None,
    model: str = "claude-opus-4-6",
) -> str:
    """Synchronous wrapper for analyze_async."""
    import asyncio
    return asyncio.run(analyze_async(report, question=question, api_key=api_key, model=model))
