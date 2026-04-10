from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import hmac
import json
import secrets


class DenyReason(Enum):
    INVALID_SIGNATURE = "invalid_signature"
    EXPIRED_CREDENTIALS = "expired_credentials"
    INSUFFICIENT_ROLE = "insufficient_role"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    GEOGRAPHIC_RESTRICTION = "geographic_restriction"
    INTENT_CLASS_RESTRICTED = "intent_class_restricted"


@dataclass
class AgentIdentity:
    """Identity metadata for an agent principal."""
    issuer: str
    subject: str
    audience: str
    role: str = "guest"
    issued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "subject": self.subject,
            "audience": self.audience,
            "role": self.role,
            "issued_at": self.issued_at,
        }


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""
    allowed: bool
    reason: DenyReason | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason.value if self.reason else None,
            "details": self.details,
        }


class PolicyEngine:
    """Enforces tool access policies based on agent identity and intent."""

    def __init__(self, signing_key: str | None = None) -> None:
        self.signing_key = signing_key or secrets.token_hex(32)
        self.tool_role_restrictions: dict[str, set[str]] = {
            "get_alerts": {"supervisor", "admin"},
            "get_coordinates": {"supervisor", "specialist", "admin"},
            "get_global_forecast": {"supervisor", "specialist", "admin"},
        }
        self.geographic_restrictions: dict[str, list[str]] = {
            "guest": ["US"],
            "supervisor": ["US", "Global"],
            "specialist": ["US", "Global"],
            "admin": ["US", "Global"],
        }

    def sign_identity(self, identity: AgentIdentity) -> str:
        """Create an HMAC signature of identity metadata."""
        payload = json.dumps(identity.to_dict(), sort_keys=True)
        signature = hmac.new(
            self.signing_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def verify_identity_signature(self, identity: AgentIdentity, signature: str) -> bool:
        """Verify an HMAC signature matches the identity."""
        expected = self.sign_identity(identity)
        return hmac.compare_digest(expected, signature)

    def evaluate_tool_access(
        self,
        tool_name: str,
        identity: AgentIdentity,
        intent_class: str = "neutral",
        region: str = "US",
    ) -> PolicyDecision:
        """Evaluate whether an agent can access a tool."""
        if tool_name not in self.tool_role_restrictions:
            return PolicyDecision(
                allowed=False,
                reason=DenyReason.TOOL_NOT_ALLOWED,
                details={"tool": tool_name, "reason": "unknown tool"},
            )

        allowed_roles = self.tool_role_restrictions[tool_name]
        if identity.role not in allowed_roles:
            return PolicyDecision(
                allowed=False,
                reason=DenyReason.INSUFFICIENT_ROLE,
                details={
                    "role": identity.role,
                    "required_roles": list(allowed_roles),
                },
            )

        allowed_regions = self.geographic_restrictions.get(identity.role, [])
        if region not in allowed_regions:
            return PolicyDecision(
                allowed=False,
                reason=DenyReason.GEOGRAPHIC_RESTRICTION,
                details={
                    "requested_region": region,
                    "allowed_regions": allowed_regions,
                },
            )

        if intent_class == "harmful" and identity.role != "admin":
            return PolicyDecision(
                allowed=False,
                reason=DenyReason.INTENT_CLASS_RESTRICTED,
                details={"intent_class": intent_class},
            )

        return PolicyDecision(allowed=True)


@dataclass
class SignedHandoffMetadata:
    """Handoff envelope with cryptographic signatures."""
    task_id: str
    trace_id: str
    identity: AgentIdentity
    signature: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "identity": self.identity.to_dict(),
            "signature": self.signature,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
