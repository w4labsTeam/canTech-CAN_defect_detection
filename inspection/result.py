"""
Defines the standardized result format shared with the application layer.
"""
from dataclasses import dataclass, field
from typing import Any

import numpy as np

@dataclass
class InspectionResult:
    """
    Standardized output from an inspection operation 
    """

    frame_id: int
    timestamp_ns: int

    # True = defective, False = non-defective
    is_defective: bool

    # Cofidence associated with the defect decision 
    confidence: float

    # Detection details independent of the model implementation 
    detections: list[dict[str, any]] = field(default_factory=list)

    # Time spent processing the image, in milliseconds.
    processing_time_ms: float = 0.0

    # Optional error description
    error: str | None = None

    # Original Image associated with this result.
    image: np.ndarray | None = field(default=None, repr=False)