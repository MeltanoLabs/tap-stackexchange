# Copyright (C) 2026 Meltano.

"""Tap executable."""

from __future__ import annotations

from tap_stackexchange.tap import TapStackExchange

TapStackExchange.cli()
