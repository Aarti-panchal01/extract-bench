"""Extractor adapters.

Every adapter exposes the same contract:

    extract(html: str) -> {"title": str | None, "text": str}

Adapters whose library failed to import are reported as unavailable instead of
crashing the run. Exceptions raised during extraction are caught by the runner
and recorded as failures for that document.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from importlib import metadata
from typing import Callable


@dataclass(frozen=True)
class AdapterSpec:
    name: str          # row label in results
    module: str        # module inside extract_bench.adapters
    func: str          # function name in that module
    package: str       # distribution name, for version pinning
    config: str        # human description of settings used


ADAPTERS: list[AdapterSpec] = [
    AdapterSpec("trafilatura", "trafilatura_adapter", "extract", "trafilatura", "library defaults"),
    AdapterSpec("readability-lxml", "readability_adapter", "extract", "readability-lxml", "library defaults"),
    AdapterSpec("justext", "justext_adapter", "extract", "jusText", "library defaults, English stoplist"),
    AdapterSpec("html2text", "html2text_adapter", "extract", "html2text", "body_width=0, otherwise defaults"),
    AdapterSpec("bs4-naive", "bs4_adapter", "extract", "beautifulsoup4", "soup.get_text() on the whole page"),
    AdapterSpec("markdownify", "markdownify_adapter", "extract", "markdownify", "library defaults on the whole page"),
]

# The one documented best-config row. Its settings are chosen on the dev split
# only (see run.py: tune_trafilatura) and then frozen for the test split.
BEST_CONFIG_NAME = "trafilatura (best-config)"


class UnavailableAdapter(RuntimeError):
    pass


def load(spec: AdapterSpec) -> Callable[[str], dict]:
    try:
        mod = importlib.import_module(f"{__name__}.{spec.module}")
    except ImportError as e:  # library not installed
        raise UnavailableAdapter(f"{spec.name}: {e}") from e
    return getattr(mod, spec.func)


def available() -> dict[str, Callable[[str], dict]]:
    out = {}
    for spec in ADAPTERS:
        try:
            out[spec.name] = load(spec)
        except UnavailableAdapter:
            continue
    return out


def version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "not installed"


def versions() -> dict[str, str]:
    pkgs = {s.package for s in ADAPTERS} | {"lxml", "lxml_html_clean"}
    return {p: version(p) for p in sorted(pkgs, key=str.lower)}
