"""
Core Module

Exports key components for UBL AI system:
- model_manager: Shared YOLO model manager
- analyzers: All 4 image analyzers
- pipeline: Image processing pipeline
"""

__version__ = "0.9.0"

from core.model_manager import model_manager
from core.analyzers import (
    analyze_share_of_shelf,
    analyze_fixed_shelf,
    analyze_sachet,
    analyze_posm,
    analyze_sovm
)
from core.retail_experiment import analyze_retail_experiment
from core.pipeline import process_image

__all__ = [
    'model_manager',
    'analyze_share_of_shelf',
    'analyze_fixed_shelf',
    'analyze_sachet',
    'analyze_posm',
    'analyze_sovm',
    'analyze_retail_experiment',
    'process_image',
]
