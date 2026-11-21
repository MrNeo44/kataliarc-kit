"""Tipos del metamodelo declarativo (contrato serializado en JSON)."""
from dataclasses import dataclass, field
from typing import Literal, Optional

Priority = Literal["A", "M", "B", "pendiente"]
EvidenceStatus = Literal["documentada", "inferencia/hipótesis", "desconocida"]


@dataclass
class QualityScenario:
    id: str
    description: str
    quality_attribute: str
    priority: Priority = "pendiente"
    acceptance_criteria: Optional[str] = None
    known_context: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    mandatory: bool = False


@dataclass
class ArchitecturalArgument:
    claim: str
    grounds: list[str] = field(default_factory=list)
    warrant: str = ""
    backing: list[str] = field(default_factory=list)
    qualifier: str = ""
    rebuttal: str = ""
    source_refs: list[str] = field(default_factory=list)
    evidence_status: EvidenceStatus = "desconocida"


@dataclass
class DecisionOutcome:
    selected_alternative_id: Optional[str] = None
    status: Literal["definitivo", "provisional", "indeterminado"] = "indeterminado"
    tradeoffs: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    rationale: str = ""
