"""Open Targets Platform GraphQL client."""
from __future__ import annotations

from typing import Any

from targetrecon.clients.http import build_client, safe_post
from targetrecon.models import (
    DiseaseAssociation,
    GeneticConstraint,
    KnownDrug,
    OpenTargetsData,
    OTReactomePathway,
    OTSafetyLiability,
    PharmacogenomicsEntry,
    TissueExpression,
    TractabilityAssessment,
)

OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"


async def _query(query: str, variables: dict[str, Any] | None = None) -> dict | None:
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    async with build_client(timeout=30.0) as client:
        data = await safe_post(client, OT_GRAPHQL, json_body=payload)
    if not data or "data" not in data:
        return None
    return data["data"]


async def resolve_ensembl_id(gene_symbol: str) -> str | None:
    q = """
    query mapGene($terms: [String!]!) {
      mapIds(queryTerms: $terms, entityNames: ["target"]) {
        mappings { hits { id } }
      }
    }
    """
    data = await _query(q, {"terms": [gene_symbol]})
    if not data:
        return None
    mappings = data.get("mapIds", {}).get("mappings", [])
    if mappings and mappings[0].get("hits"):
        return mappings[0]["hits"][0]["id"]
    return None


_PROFILE_QUERY = """
query profile($id: String!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    approvedName
    tractability { label modality value }
    safetyLiabilities {
      datasource event eventId
      effects { direction dosing }
      biosamples { tissueLabel tissueId }
    }
    pathways { pathwayId pathway topLevelTerm }
    geneticConstraint { constraintType score oe oeLower oeUpper }
    isEssential
  }
}
"""


async def fetch_target_profile(ensembl_id: str) -> dict | None:
    data = await _query(_PROFILE_QUERY, {"id": ensembl_id})
    return data.get("target") if data else None


_DISEASES_QUERY = """
query diseases($id: String!, $size: Int!, $index: Int!) {
  target(ensemblId: $id) {
    associatedDiseases(page: { index: $index, size: $size }) {
      count
      rows {
        score
        datatypeScores { id score }
        disease { id name therapeuticAreas { id name } }
      }
    }
  }
}
"""


async def fetch_associated_diseases(
    ensembl_id: str, limit: int = 50
) -> tuple[list[dict], int]:
    all_rows: list[dict] = []
    total = 0
    index = 0
    page_size = min(limit, 500)
    while len(all_rows) < limit:
        data = await _query(
            _DISEASES_QUERY,
            {"id": ensembl_id, "size": page_size, "index": index},
        )
        if not data or not data.get("target"):
            break
        assoc = data["target"]["associatedDiseases"]
        total = assoc["count"]
        rows = assoc["rows"]
        all_rows.extend(rows)
        if len(all_rows) >= total or not rows:
            break
        index += 1
    return all_rows[:limit], total


_DRUGS_QUERY = """
query drugs($id: String!) {
  target(ensemblId: $id) {
    drugAndClinicalCandidates {
      count
      rows {
        maxClinicalStage
        drug {
          id name drugType maximumClinicalStage
          mechanismsOfAction { rows { mechanismOfAction actionType } }
        }
        diseases { disease { id name } }
      }
    }
  }
}
"""


async def fetch_known_drugs(ensembl_id: str) -> list[dict]:
    data = await _query(_DRUGS_QUERY, {"id": ensembl_id})
    if not data or not data.get("target"):
        return []
    cands = data["target"].get("drugAndClinicalCandidates")
    if not cands:
        return []
    return cands.get("rows", [])


_EXPRESSION_QUERY = """
query expr($id: String!) {
  target(ensemblId: $id) {
    expressions {
      tissue { id label organs }
      rna { zscore value unit level }
      protein { level reliability }
    }
  }
}
"""


async def fetch_expressions(ensembl_id: str) -> list[dict]:
    data = await _query(_EXPRESSION_QUERY, {"id": ensembl_id})
    if not data or not data.get("target"):
        return []
    return data["target"].get("expressions", [])


_PGX_QUERY = """
query pgx($id: String!) {
  target(ensemblId: $id) {
    pharmacogenomics {
      variantRsId genotype pgxCategory phenotypeText
      evidenceLevel isDirectTarget datasourceId
      drugs { drugFromSource drug { id name } }
    }
  }
}
"""


async def fetch_pharmacogenomics(ensembl_id: str) -> list[dict]:
    data = await _query(_PGX_QUERY, {"id": ensembl_id})
    if not data or not data.get("target"):
        return []
    return data["target"].get("pharmacogenomics", [])


def _parse_profile(raw: dict, ensembl_id: str) -> OpenTargetsData:
    tract = [
        TractabilityAssessment(
            modality=t.get("modality", ""),
            label=t.get("label", ""),
            value=bool(t.get("value")),
        )
        for t in raw.get("tractability", [])
        if t.get("value")
    ]

    safety = [
        OTSafetyLiability(
            event=s.get("event"),
            datasource=s.get("datasource", ""),
            effects=s.get("effects", []),
            biosamples=s.get("biosamples", []),
        )
        for s in raw.get("safetyLiabilities", [])
    ]

    pathways = [
        OTReactomePathway(
            pathway_id=p.get("pathwayId", ""),
            pathway_name=p.get("pathway", ""),
            top_level_term=p.get("topLevelTerm", ""),
        )
        for p in raw.get("pathways", [])
    ]

    constraints = [
        GeneticConstraint(
            constraint_type=c.get("constraintType", ""),
            score=c.get("score"),
            oe=c.get("oe"),
            oe_lower=c.get("oeLower"),
            oe_upper=c.get("oeUpper"),
        )
        for c in raw.get("geneticConstraint", [])
    ]

    return OpenTargetsData(
        ensembl_id=ensembl_id,
        approved_symbol=raw.get("approvedSymbol"),
        approved_name=raw.get("approvedName"),
        tractability=tract,
        safety_liabilities=safety,
        pathways=pathways,
        genetic_constraint=constraints,
        is_essential=raw.get("isEssential"),
    )


def _parse_diseases(
    rows: list[dict], total: int, ot: OpenTargetsData
) -> None:
    for row in rows:
        disease = row.get("disease", {})
        ta_list = [
            ta.get("name", "")
            for ta in disease.get("therapeuticAreas", [])
            if ta.get("name")
        ]
        dt_scores = {
            ds["id"]: ds["score"]
            for ds in row.get("datatypeScores", [])
            if ds.get("score")
        }
        ot.disease_associations.append(
            DiseaseAssociation(
                disease_id=disease.get("id", ""),
                disease_name=disease.get("name", ""),
                overall_score=row.get("score", 0.0),
                therapeutic_areas=ta_list,
                datatype_scores=dt_scores,
            )
        )
    ot.total_disease_associations = total


def _parse_drugs(rows: list[dict], ot: OpenTargetsData) -> None:
    for row in rows:
        drug = row.get("drug", {})
        moa_rows = (drug.get("mechanismsOfAction") or {}).get("rows", [])
        moa = moa_rows[0].get("mechanismOfAction", "") if moa_rows else None
        diseases = [
            d["disease"]["name"]
            for d in (row.get("diseases") or [])
            if d and d.get("disease") and d["disease"].get("name")
        ]
        ot.known_drugs.append(
            KnownDrug(
                drug_id=drug.get("id", ""),
                drug_name=drug.get("name", ""),
                drug_type=drug.get("drugType"),
                max_clinical_stage=row.get("maxClinicalStage")
                or drug.get("maximumClinicalStage"),
                mechanism_of_action=moa,
                diseases=diseases[:5],
            )
        )


def _safe_str(val: object) -> str | None:
    if val is None or val == -1:
        return None
    return str(val)


def _parse_expressions(rows: list[dict], ot: OpenTargetsData) -> None:
    for row in rows:
        tissue = row.get("tissue") or {}
        rna = row.get("rna") or {}
        protein = row.get("protein") or {}
        ot.expressions.append(
            TissueExpression(
                tissue_id=tissue.get("id", ""),
                tissue_label=tissue.get("label", ""),
                organs=tissue.get("organs") or [],
                rna_value=rna.get("value"),
                rna_zscore=rna.get("zscore"),
                rna_level=_safe_str(rna.get("level")),
                protein_level=_safe_str(protein.get("level")),
            )
        )


def _parse_pharmacogenomics(rows: list[dict], ot: OpenTargetsData) -> None:
    for row in rows:
        drugs = row.get("drugs", [])
        drug_name = None
        drug_id = None
        if drugs:
            d = drugs[0]
            drug_name = d.get("drugFromSource")
            inner = d.get("drug") or {}
            drug_id = inner.get("id")
            if not drug_name:
                drug_name = inner.get("name")
        ot.pharmacogenomics.append(
            PharmacogenomicsEntry(
                variant_rs_id=row.get("variantRsId"),
                genotype=row.get("genotype"),
                pgx_category=row.get("pgxCategory"),
                phenotype_text=row.get("phenotypeText"),
                evidence_level=row.get("evidenceLevel"),
                drug_name=drug_name,
                drug_id=drug_id,
            )
        )


async def fetch_opentargets(ensembl_id: str, disease_limit: int = 50) -> OpenTargetsData | None:
    import asyncio

    results = await asyncio.gather(
        fetch_target_profile(ensembl_id),
        fetch_associated_diseases(ensembl_id, limit=disease_limit),
        fetch_known_drugs(ensembl_id),
        fetch_expressions(ensembl_id),
        fetch_pharmacogenomics(ensembl_id),
        return_exceptions=True,
    )

    profile_raw = results[0] if not isinstance(results[0], Exception) else None
    disease_result = results[1] if not isinstance(results[1], Exception) else ([], 0)
    disease_rows, disease_total = disease_result
    drug_rows = results[2] if not isinstance(results[2], Exception) else []
    expr_rows = results[3] if not isinstance(results[3], Exception) else []
    pgx_rows = results[4] if not isinstance(results[4], Exception) else []

    if not profile_raw:
        return None

    ot = _parse_profile(profile_raw, ensembl_id)
    _parse_diseases(disease_rows, disease_total, ot)
    _parse_drugs(drug_rows, ot)
    _parse_expressions(expr_rows, ot)
    _parse_pharmacogenomics(pgx_rows, ot)

    return ot
