"""Label semantics and ground-truth definitions for ThermalIntel V2 evaluation.

Explicitly categorizes evaluation targets into 4 non-overlapping semantic categories:
- GROUND_TRUTH: Verified physical evidence (e.g. ground fire perimeters, industrial logs, field audits).
- WEAK_LABEL: Proxy or heuristic label (e.g. land-cover overlay or distance thresholding).
- SYNTHETIC_EXPECTATION: Simulation author expectation encoded in a synthetic scenario pack.
- UNLABELLED: Raw telemetry without verified or expected label.

Prevents presenting synthetic scenario expectations as real-world validation.
"""

from enum import Enum
from typing import Optional


class LabelType(str, Enum):
    """Categorical classification of evaluation label provenance."""
    GROUND_TRUTH = "GROUND_TRUTH"
    WEAK_LABEL = "WEAK_LABEL"
    SYNTHETIC_EXPECTATION = "SYNTHETIC_EXPECTATION"
    UNLABELLED = "UNLABELLED"

    @classmethod
    def from_str(cls, val: Optional[str]) -> "LabelType":
        """Parse string to LabelType safely, defaulting to UNLABELLED."""
        if not val:
            return cls.UNLABELLED
        normalized = val.strip().upper().replace(" ", "_")
        for member in cls:
            if member.value == normalized:
                return member
        # Also check lower / mixed
        for member in cls:
            if member.name == normalized:
                return member
        return cls.UNLABELLED

    @property
    def is_ground_truth(self) -> bool:
        """True only if label originates from confirmed physical ground truth."""
        return self == LabelType.GROUND_TRUTH

    @property
    def allows_accuracy_metric(self) -> bool:
        """True if label can be used to score classification accuracy/confusion matrix."""
        return self in (LabelType.GROUND_TRUTH, LabelType.WEAK_LABEL, LabelType.SYNTHETIC_EXPECTATION)
