import json
from pathlib import Path
from types import MappingProxyType


def _read():
    here = Path(__file__).parent

    # Wheels ship the manifest inside the package, while source checkouts and
    # editable installs keep it at the root of the repository.
    for path in (here / "versions.json", here.parent.parent / "versions.json"):
        if path.is_file():
            return json.loads(path.read_text())

    raise FileNotFoundError("No versions.json manifest")


versions = MappingProxyType(_read())
"""The versions of the components shipped with this package, named as in
``Bare.versions``, such as ``versions["bare"]`` for the bundled Bare."""
