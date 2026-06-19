import re
from dataclasses import dataclass
from typing import Literal

ConfidenceLevel = Literal["high", "medium", "low"]
SourceReliability = Literal["reliable", "mixed", "weak", "none"]
WebNeeded = Literal["yes", "no"]

CONFIDENCE_MARKER_RE = re.compile(r"\[\[pakko_confidence\s+([^\]]+)]]", re.IGNORECASE)
MARKER_FIELD_RE = re.compile(
    r"(level|source|web_needed)=(high|medium|low|reliable|mixed|weak|none|yes|no)\b"
)


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    level: ConfidenceLevel
    source: SourceReliability
    web_needed: WebNeeded
    marker_found: bool
    clean_text: str

    @property
    def is_low_confidence(self) -> bool:
        return self.level == "low"

    @property
    def should_improve_with_web_search(self) -> bool:
        return self.level == "low" or self.web_needed == "yes"


DEFAULT_ASSESSMENT = {
    "level": "low",
    "source": "none",
    "web_needed": "yes",
}


def assess_confidence(text: str) -> ConfidenceAssessment:
    marker = CONFIDENCE_MARKER_RE.search(text)
    clean_text = CONFIDENCE_MARKER_RE.sub("", text).strip()
    if not marker:
        return ConfidenceAssessment(
            level="low",
            source="none",
            web_needed="yes",
            marker_found=False,
            clean_text=clean_text,
        )

    fields = DEFAULT_ASSESSMENT | {
        key.lower(): value.lower()
        for key, value in MARKER_FIELD_RE.findall(marker.group(1))
    }
    return ConfidenceAssessment(
        level=fields["level"],  # type: ignore[arg-type]
        source=fields["source"],  # type: ignore[arg-type]
        web_needed=fields["web_needed"],  # type: ignore[arg-type]
        marker_found=True,
        clean_text=clean_text,
    )
