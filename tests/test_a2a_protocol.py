import os
import tempfile
import unittest

from server.a2a_protocol import A2AIdempotencyStore, SQLiteA2AIdempotencyStore, build_handoff


class A2AProtocolTests(unittest.TestCase):
    def test_build_handoff_contains_required_fields(self) -> None:
        handoff = build_handoff(query="What is weather in Paris?", target_agent="weather-specialist")
        payload = handoff.to_dict()

        self.assertTrue(payload["task_id"].startswith("task_"))
        self.assertTrue(payload["trace_id"].startswith("trace_"))
        self.assertEqual(payload["target_agent"], "weather-specialist")
        self.assertIn("idempotency_key", payload)
        self.assertIn("deadline_ms", payload)

    def test_handoff_idempotency_key_is_deterministic_for_same_seed(self) -> None:
        handoff_a = build_handoff(
            query="What is weather in Paris?",
            target_agent="weather-specialist",
            idempotency_seed="same-input",
        )
        handoff_b = build_handoff(
            query="Any other text",
            target_agent="weather-specialist",
            idempotency_seed="same-input",
        )
        self.assertEqual(handoff_a.idempotency_key, handoff_b.idempotency_key)

    def test_handoff_remaining_seconds_decreases(self) -> None:
        handoff = build_handoff(
            query="Q",
            target_agent="weather-specialist",
            deadline_ms=2000,
        )
        self.assertGreater(handoff.remaining_seconds(), 0.0)
        self.assertFalse(handoff.is_expired())

    def test_idempotency_store_round_trip(self) -> None:
        store = A2AIdempotencyStore()
        key = "demo-key"
        self.assertFalse(store.has(key))

        store.set(key, "result payload")
        self.assertTrue(store.has(key))
        self.assertEqual(store.get(key), "result payload")

    def test_sqlite_idempotency_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "a2a_idempotency.db")
            store = SQLiteA2AIdempotencyStore(db_path=db_path)
            key = "persisted-key"

            self.assertFalse(store.has(key))
            store.set(key, "persisted payload")
            self.assertTrue(store.has(key))
            self.assertEqual(store.get(key), "persisted payload")

            reopened = SQLiteA2AIdempotencyStore(db_path=db_path)
            self.assertTrue(reopened.has(key))
            self.assertEqual(reopened.get(key), "persisted payload")


if __name__ == "__main__":
    unittest.main()
