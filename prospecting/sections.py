"""Keep only the responsibilities / requirements part of a job description and drop vendor-context sentences.

Patterns live in config/job_sections.csv and config/vendor_context.txt so they can be tuned without code changes.
"""
import csv
import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_HEADING_MAX_LEN = 70
_HEADING_MAX_WORDS = 8
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n")


@dataclass(frozen=True)
class SectionConfig:
    keep: list[re.Pattern]
    drop: list[re.Pattern]
    vendor: list[re.Pattern]


def load_config(config_dir: Path = CONFIG_DIR) -> SectionConfig:
    keep, drop = [], []
    with open(config_dir / "job_sections.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(line for line in f if not line.startswith("#")):
            (keep if r["kind"].strip() == "keep" else drop).append(re.compile(r["pattern"].strip(), re.I))
    vendor = [re.compile(line.strip(), re.I)
              for line in (config_dir / "vendor_context.txt").read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")]
    return SectionConfig(keep, drop, vendor)


def _heading_kind(line: str, cfg: SectionConfig) -> str:
    h = line.strip().strip("-•*#:").strip()
    if not h or len(h) > _HEADING_MAX_LEN or len(h.split()) > _HEADING_MAX_WORDS or h.endswith("."):
        return ""
    if any(p.search(h) for p in cfg.keep):
        return "keep"
    if any(p.search(h) for p in cfg.drop):
        return "drop"
    return ""


def role_sections(description: str, cfg: SectionConfig) -> tuple[str, bool]:
    """Text under responsibilities/requirements headings. Returns (text, structured).

    If no keep heading is found the whole description is returned with structured=False. Keep-heading lines are
    kept too, since a short bullet ("You have migrated legacy systems") can look like a heading.
    """
    lines = description.split("\n")
    kinds = [_heading_kind(line, cfg) for line in lines]
    if "keep" not in kinds:
        return description, False
    out, keeping = [], False
    for line, kind in zip(lines, kinds):
        if kind:
            keeping = kind == "keep"
        if keeping:
            out.append(line)
    return "\n".join(out), True


def drop_vendor_context(text: str, cfg: SectionConfig) -> str:
    return "\n".join(s for s in _SENTENCE_SPLIT.split(text) if s.strip() and not any(p.search(s) for p in cfg.vendor))


def relevant_text(description: str, cfg: SectionConfig) -> tuple[str, bool]:
    text, structured = role_sections(description, cfg)
    return drop_vendor_context(text, cfg), structured
