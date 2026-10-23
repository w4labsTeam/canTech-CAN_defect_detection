"""
Defines the common interface every inspection method must implement.
"""
from abc import ABC, abstractmethod
import numpy as np 
from inspection.result import InspectionResult

class BaseInspector(ABC):
    """
    Interface for interchangable inspection implementatios.
    """

    @abstractmethod
    def inspect(
        self,
        image: np.ndarray,
        frame_id: int,
        timestamp_ns: int,

    ) -> InspectionResult:
        """
        Inspect one image and return a standardized result.
        """

    def close(self) -> None:
        """
        Release resources used by the inspector.
        """
        pass

    