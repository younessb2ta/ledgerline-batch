"""Deterministic e-commerce event and batch data generator."""

from .generator import GeneratorConfig, generate_day, generate_events
from .model import GENERATOR_VERSION, SCHEMA_VERSION

__version__ = GENERATOR_VERSION

__all__ = [
    "GENERATOR_VERSION",
    "SCHEMA_VERSION",
    "GeneratorConfig",
    "generate_day",
    "generate_events",
    "__version__",
]
