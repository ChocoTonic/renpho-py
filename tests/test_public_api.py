"""Public API contract — a canary that fails if the stable surface changes.

These names and signatures are what downstream users depend on. Changing
anything here is a breaking change: it must be a MAJOR version bump and a
*deliberate* edit to this test (see NEW_LIBRARY_PLAN.md, "Public API Contract").
Adding a new public method/kwarg is fine — extend the expectations below in the
same commit so the addition is conscious rather than silent surface creep.

Note: the *shape* of returned measurement dicts (weight, bodyfat, timeStamp,
id, ...) is passthrough from Renpho's reverse-engineered API and is explicitly
NOT part of this contract — the server owns those keys.
"""

import inspect

import renpho
from renpho.client import RenphoAPIError, RenphoClient

# Top-level re-exports (renpho.__all__).
EXPECTED_EXPORTS = [
    "Measurement",
    "RenphoAPIError",
    "RenphoClient",
    "format_measurement",
    "format_timestamp",
    "save_csv",
    "save_json",
]

# Public RenphoClient methods -> ordered parameter names (incl. keyword-only).
EXPECTED_METHODS = {
    "__init__": ["self", "email", "password", "debug"],
    "login": ["self"],
    "get_device_info": ["self"],
    "get_measurements": ["self", "table_name", "user_id", "total_count", "page_size"],
    "get_body_composition_measurements": [
        "self",
        "table_name",
        "user_id",
        "page_size",
    ],
    "discover_user_tables": ["self", "user_id", "refresh", "max_workers"],
    "get_all_measurements": ["self", "extra_user_ids", "max_workers"],
    "clear_table_cache": ["self"],
}


def test_exports_are_stable():
    assert sorted(renpho.__all__) == EXPECTED_EXPORTS
    for name in EXPECTED_EXPORTS:
        assert hasattr(renpho, name), f"missing export: {name}"


def test_client_public_methods_have_expected_params():
    for name, params in EXPECTED_METHODS.items():
        method = getattr(RenphoClient, name)
        got = list(inspect.signature(method).parameters)
        assert got == params, f"{name} signature changed: {got} != {params}"


def test_no_unexpected_public_methods():
    # Any *new* public (non-underscore) method is a contract addition; force it
    # to be declared above rather than appearing silently.
    public = {n for n in dir(RenphoClient) if not n.startswith("_")}
    expected_public = set(EXPECTED_METHODS) - {"__init__"}
    assert public == expected_public, f"unexpected public surface: {public ^ expected_public}"


def test_error_exposes_context_code_msg():
    err = RenphoAPIError("Login", 401, "Unauthorized")
    assert err.context == "Login"
    assert err.code == 401
    assert err.msg == "Unauthorized"


def test_version_is_exposed():
    assert isinstance(renpho.__version__, str) and renpho.__version__


def test_package_is_typed():
    # py.typed must ship so downstream type-checkers honor our annotations.
    import importlib.resources

    assert importlib.resources.files("renpho").joinpath("py.typed").is_file()
