from __future__ import annotations

from .diagrams import build_module_diagram
from .generator import DocGenerator
from .impact import compute_regeneration_impact
from .manifest_store import DocPageManifestStore, open_doc_manifest_store
from .models import DocPage, DocumentationSet, PageLink, PageManifestEntry, RegenerationImpactSet
from .section_narrator import SectionNarration, SectionNarrator, apply_section_narrations
from .sections import Section, SectionMember, SectionSelection, build_sections
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
    "Section",
    "SectionMember",
    "SectionNarration",
    "SectionNarrator",
    "SectionSelection",
    "apply_section_narrations",
    "build_module_diagram",
    "build_sections",
    "compute_regeneration_impact",
    "open_doc_manifest_store",
]
