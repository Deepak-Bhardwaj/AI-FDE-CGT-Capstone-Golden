from __future__ import annotations

from pathlib import Path

from .adapters.assistant_fake import DeterministicAssistantFake
from .adapters.slot_simulator import SlotSimulator
from .services.assistant import AssistantGateway
from .services.audit_service import AuditService
from .services.cases import CaseService
from .services.commands import CommandService
from .services.evidence import EvidenceService
from .services.identity import IdentityService
from .services.quality import QualityService
from .services.readiness import ReadinessService
from .storage import Database


class CapstoneApplication:
    def __init__(self, database_path: str | Path = ":memory:", ai_mode: str = "off") -> None:
        self.db = Database(database_path)
        self.audit = AuditService(self.db)
        self.evidence = EvidenceService(self.db)
        self.cases = CaseService(self.db)
        self.identity = IdentityService(self.db)
        self.readiness = ReadinessService(self.db)
        self.commands = CommandService(self.db, SlotSimulator())
        provider = DeterministicAssistantFake() if ai_mode == "fake" else None
        if ai_mode not in {"off", "fake"}:
            raise ValueError("LIVE_AI_PROVIDER_NOT_APPROVED")
        self.assistant = AssistantGateway(self.db, provider)
        self.quality = QualityService(self.db)
        self.ai_mode = ai_mode

    def close(self) -> None:
        self.db.close()
