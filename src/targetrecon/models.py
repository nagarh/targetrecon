"""Pydantic v2 data models for TargetRecon."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GoTerm(BaseModel):
    go_id: str = ""
    term: str = ""
    category: str = ""  # biological_process, molecular_function, cellular_component


class UniProtInfo(BaseModel):
    uniprot_id: str
    gene_name: Optional[str] = None
    protein_name: str = ""
    organism: str = ""
    sequence_length: int = 0
    chembl_id: Optional[str] = None
    function_description: Optional[str] = None
    subcellular_locations: list[str] = Field(default_factory=list)
    disease_associations: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    go_terms: list[GoTerm] = Field(default_factory=list)


class ExperimentalMethod(str, Enum):
    XRAY = "X-RAY DIFFRACTION"
    CRYO_EM = "ELECTRON MICROSCOPY"
    NMR = "SOLUTION NMR"
    NEUTRON = "NEUTRON DIFFRACTION"
    OTHER = "OTHER"


class PDBLigand(BaseModel):
    ligand_id: str
    smiles: Optional[str] = None
    name: Optional[str] = None
    formula: Optional[str] = None


class PDBStructure(BaseModel):
    pdb_id: str
    method: ExperimentalMethod = ExperimentalMethod.OTHER
    resolution: Optional[float] = None
    release_date: Optional[str] = None
    title: str = ""
    ligands: list[PDBLigand] = Field(default_factory=list)


class AlphaFoldModel(BaseModel):
    model_config = {"protected_namespaces": ()}

    uniprot_id: str
    pdb_url: Optional[str] = None
    model_url: Optional[str] = None
    version: int = 4
    mean_plddt: Optional[float] = None
    sequence_length: Optional[int] = None


class BioactivityRecord(BaseModel):
    molecule_chembl_id: Optional[str] = None
    smiles: Optional[str] = None
    activity_type: str = ""
    value: Optional[float] = None  # in nM
    pchembl_value: Optional[float] = None
    source: str = "ChEMBL"
    assay_id: Optional[str] = None
    name: Optional[str] = None


class LigandSummary(BaseModel):
    smiles: str
    name: Optional[str] = None
    chembl_id: Optional[str] = None
    best_activity_type: str = ""
    best_activity_value_nM: Optional[float] = None
    best_pchembl: Optional[float] = None
    num_assays: int = 0
    sources: list[str] = Field(default_factory=list)
    pdb_ids: list[str] = Field(default_factory=list)


class ProteinInteraction(BaseModel):
    gene_a: str
    gene_b: str
    score: float
    experimental: float = 0.0
    database: float = 0.0
    textmining: float = 0.0
    coexpression: float = 0.0
    string_id_b: str = ""


class TargetReport(BaseModel):
    query: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    targetrecon_version: str = "0.1.8"
    uniprot: Optional[UniProtInfo] = None
    pdb_structures: list[PDBStructure] = Field(default_factory=list)
    alphafold: Optional[AlphaFoldModel] = None
    bioactivities: list[BioactivityRecord] = Field(default_factory=list)
    ligand_summary: list[LigandSummary] = Field(default_factory=list)
    num_pdb_structures: int = 0
    num_bioactivities: int = 0
    num_unique_ligands: int = 0
    best_ligand: Optional[LigandSummary] = None
    interactions: list[ProteinInteraction] = Field(default_factory=list)
    ai_analysis: Optional[str] = None  # Claude AI analysis
