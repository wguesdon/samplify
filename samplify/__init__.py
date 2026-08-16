"""samplify: find and harmonize misspelled sample names, with a person deciding.

The version is read from the installed package metadata, so ``pyproject.toml``
is the only place it is written down.
"""

from importlib.metadata import PackageNotFoundError, version

from .csv_processor import apply_mapping, diagnose, harmonize_csv, propose, propose_csv
from .harmonizer import harmonize
from .mapping import MappingFile, read, write
from .matching import group_names, hamming_distance, levenshtein_distance, similarity

try:
    __version__ = version("samplify")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = [
    "MappingFile",
    "apply_mapping",
    "diagnose",
    "group_names",
    "hamming_distance",
    "harmonize",
    "harmonize_csv",
    "levenshtein_distance",
    "propose",
    "propose_csv",
    "read",
    "similarity",
    "write",
    "__version__",
]
