import unittest

from server.security import (
    AgentIdentity,
    DenyReason,
    PolicyEngine,
    SignedHandoffMetadata,
)


class AgentIdentityTests(unittest.TestCase):
    def test_agent_identity_to_dict_includes_all_fields(self) -> None:
        identity = AgentIdentity(
            issuer="test-issuer",
            subject="test-agent",
            audience="test-audience",
            role="admin",
        )

        payload = identity.to_dict()
        self.assertEqual(payload["issuer"], "test-issuer")
        self.assertEqual(payload["subject"], "test-agent")
        self.assertEqual(payload["role"], "admin")
        self.assertIn("issued_at", payload)


class PolicyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PolicyEngine(signing_key="test-key-12345")

    def test_policy_engine_signs_identity(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="supervisor",
        )

        sig1 = self.engine.sign_identity(identity)
        sig2 = self.engine.sign_identity(identity)

        self.assertEqual(sig1, sig2)
        self.assertGreater(len(sig1), 0)

    def test_policy_engine_verifies_valid_signature(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="supervisor",
        )

        sig = self.engine.sign_identity(identity)
        self.assertTrue(self.engine.verify_identity_signature(identity, sig))

    def test_policy_engine_rejects_tampered_signature(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="supervisor",
        )

        sig = self.engine.sign_identity(identity)
        bad_sig = sig[:-4] + "xxxx"

        self.assertFalse(self.engine.verify_identity_signature(identity, bad_sig))

    def test_policy_engine_rejects_insufficient_role(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="guest",
        )

        decision = self.engine.evaluate_tool_access("get_alerts", identity)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, DenyReason.INSUFFICIENT_ROLE)

    def test_policy_engine_allows_supervisor_get_alerts(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="supervisor",
        )

        decision = self.engine.evaluate_tool_access("get_alerts", identity, region="US")

        self.assertTrue(decision.allowed)
        self.assertIsNone(decision.reason)

    def test_policy_engine_enforces_geographic_restriction(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="specialist",
        )

        decision = self.engine.evaluate_tool_access(
            "get_coordinates",
            identity,
            region="EU",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, DenyReason.GEOGRAPHIC_RESTRICTION)

    def test_policy_engine_rejects_harmful_intent_for_non_admin(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="supervisor",
        )

        decision = self.engine.evaluate_tool_access(
            "get_coordinates",
            identity,
            intent_class="harmful",
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, DenyReason.INTENT_CLASS_RESTRICTED)

    def test_policy_engine_allows_harmful_intent_for_admin(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="admin",
        )

        decision = self.engine.evaluate_tool_access(
            "get_coordinates",
            identity,
            intent_class="harmful",
        )

        self.assertTrue(decision.allowed)

    def test_policy_engine_rejects_unknown_tool(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
            role="admin",
        )

        decision = self.engine.evaluate_tool_access(
            "unknown_tool_xyz",
            identity,
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, DenyReason.TOOL_NOT_ALLOWED)


class SignedHandoffMetadataTests(unittest.TestCase):
    def test_signed_handoff_metadata_round_trip(self) -> None:
        identity = AgentIdentity(
            issuer="issuer",
            subject="agent",
            audience="weather",
        )

        metadata = SignedHandoffMetadata(
            task_id="task_abc123",
            trace_id="trace_def456",
            identity=identity,
            signature="sig_xyz789",
        )

        payload = metadata.to_dict()
        self.assertEqual(payload["task_id"], "task_abc123")
        self.assertEqual(payload["trace_id"], "trace_def456")
        self.assertEqual(payload["signature"], "sig_xyz789")
        self.assertIn("identity", payload)
        self.assertIn("created_at", payload)


if __name__ == "__main__":
    unittest.main()
