"""Governed core for CGT patient-to-batch orchestration.

Additive and read-only with respect to the legacy estate. Nothing in this package
mutates data/, shadow_ops/, contracts/ or src/cgt_orchestrator/.
"""

__all__ = ["types", "loader", "sop", "authority", "audit", "reality", "release_gate", "identity", "intelligence"]
