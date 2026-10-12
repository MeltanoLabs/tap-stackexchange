# Copyright (C) 2026 Meltano.

"""Test Configuration."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Configure Pytest."""
    if sys.version_info < (3, 11):
        config.addinivalue_line(
            "filterwarnings",
            "once:Python 3.10 reached its end of life on 2026-10:FutureWarning",
        )
