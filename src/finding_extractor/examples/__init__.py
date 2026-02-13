"""Few-shot examples for radiology report extraction.

Examples are stored as YAML files in this package directory.
This module provides backward-compatible accessor functions.
"""

from finding_extractor.prompt import load_example


def get_ct_abdomen_example():
    """Return (report_text, ReportExtraction) for the CT abdomen example."""
    return load_example("ct_abdomen")


def get_xr_chest_example():
    """Return (report_text, ReportExtraction) for the chest XR example."""
    return load_example("xr_chest")


def get_default_examples():
    """Return the default set of few-shot examples."""
    return [get_ct_abdomen_example(), get_xr_chest_example()]
