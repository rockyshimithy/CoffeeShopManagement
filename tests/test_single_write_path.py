"""SC-003 and SC-006 as searchable facts, not intentions.

One module writes stock, and no role is compared outside the permission helper.
Both are read straight off the source, so a later commit cannot quietly break
them.
"""

import pathlib

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "src" / "apps" / "inventory"
WRITE_PATH = "services.py"
WRITE_CALLS = (
    ".create(",
    ".update(",
    ".update_one(",
    ".delete(",
    ".save(",
    ".bulk_create(",
    ".bulk_update(",
)


def _modules():
    return sorted(PACKAGE.glob("*.py"))


def _lines(path):
    return [line.strip() for line in path.read_text().splitlines()]


def _write_lines(path):
    return [line for line in _lines(path) if any(call in line for call in WRITE_CALLS)]


def test_the_package_is_where_we_think_it_is():
    names = [path.name for path in _modules()]
    assert "services.py" in names
    assert "models.py" in names


def test_only_the_service_writes():
    """FR-024: no second write path exists, in this context or beside it."""
    offenders = {
        path.name: _write_lines(path)
        for path in _modules()
        if path.name != WRITE_PATH and _write_lines(path)
    }
    assert offenders == {}


def test_the_service_really_does_write():
    """Guards the test above: an empty services.py would also pass it."""
    lines = " ".join(_write_lines(PACKAGE / WRITE_PATH))
    assert ".create(" in lines
    assert ".update(" in lines


def test_no_role_comparison_outside_the_helper():
    """SC-006: authorization is decided in identity.permissions and nowhere else."""
    offenders = {
        path.name: [line for line in _lines(path) if "User.Role" in line]
        for path in _modules()
    }
    assert {name: hits for name, hits in offenders.items() if hits} == {}


def test_the_admin_cannot_write():
    """FR-027: the admin is not a legal write path for stock."""
    text = (PACKAGE / "admin.py").read_text()
    assert text.count("return False") == 6
