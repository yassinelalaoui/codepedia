from __future__ import annotations

from .diagrams import build_module_diagram
from .generator import DocGenerator
from .impact import compute_regeneration_impact
from .manifest_store import DocPageManifestStore, open_doc_manifest_store
from .models import DocPage, DocumentationSet, PageLink, PageManifestEntry, RegenerationImpactSet
from .features.candidates import Candidate, build_candidates
from .features.evidence import build_repository_evidence
from .features.planner import FeaturePlanner
from .features.validate import Feature, FeatureMember, repair
from .writer import DocumentationWriter, OutputRootEscapeError

__all__ = [
    "DocGenerator",
    "DocPage",
    "DocPageManifestStore",
    "DocumentationSet",
    "DocumentationWriter",
    "OutputRootEscapeError",
    "PageLink",
    "PageManifestEntry",
    "RegenerationImpactSet",
    "Candidate",
    "Feature",
    "FeatureMember",
    "FeaturePlanner",
    "build_candidates",
    "build_module_diagram",
    "build_repository_evidence",
    "compute_regeneration_impact",
    "repair",
    "open_doc_manifest_store",
]
