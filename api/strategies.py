"""
api/strategies.py — strategy archetypes available inside the Docker container.
Mirrors scripts/strategies.py; kept here so COPY api/ ./api/ always picks it up.
"""
from scripts.strategies import _ARCHETYPES, _SL_TP, get_archetype  # noqa: F401
