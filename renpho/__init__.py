"""renpho - Unofficial Python client for the Renpho Health API.

Pull body composition measurements from Renpho smart scales.

Quick start::

    from renpho import RenphoClient

    client = RenphoClient("user@example.com", "password")
    client.login()
    measurements = client.get_all_measurements()
"""

from importlib.metadata import PackageNotFoundError, version

from .client import RenphoAPIError, RenphoClient
from .export import format_measurement, format_timestamp, save_csv, save_json

try:
    __version__ = version("renpho-py")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0"

__all__ = [
    "RenphoClient",
    "RenphoAPIError",
    "format_measurement",
    "format_timestamp",
    "save_csv",
    "save_json",
]
