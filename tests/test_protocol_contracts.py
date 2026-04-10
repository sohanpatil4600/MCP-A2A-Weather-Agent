import json
import unittest
from unittest.mock import patch

from server import weather


class ProtocolContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_capabilities_contract_shape(self) -> None:
        payload = json.loads(await weather.get_capabilities())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], weather.SCHEMA_VERSION)

        data = payload["data"]
        self.assertEqual(data["server"], weather.SERVER_NAME)
        self.assertIn("protocol", data)
        self.assertIn("tool_contracts", data)
        self.assertIn("get_alerts", data["tool_contracts"])

    async def test_negotiate_protocol_supported(self) -> None:
        payload = json.loads(await weather.negotiate_protocol("2024-11-05"))
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["data"]["selected_protocol_version"],
            "2024-11-05",
        )

    async def test_negotiate_protocol_unsupported(self) -> None:
        payload = json.loads(await weather.negotiate_protocol("2022-01-01"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], -32010)

    async def test_get_alerts_rejects_invalid_state(self) -> None:
        payload = json.loads(await weather.get_alerts("California"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], -32602)

    async def test_get_global_forecast_rejects_out_of_range_coordinates(self) -> None:
        payload = json.loads(await weather.get_global_forecast(100, 50))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], -32602)

    async def test_get_alerts_formats_success_response(self) -> None:
        fake_response = {
            "features": [
                {
                    "properties": {
                        "event": "Flood Warning",
                        "areaDesc": "Sample County",
                        "severity": "Severe",
                        "description": "Test description",
                        "instruction": "Test instruction",
                    }
                }
            ]
        }

        with patch("server.weather.make_nws_request", return_value=fake_response):
            payload = json.loads(await weather.get_alerts("ca"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["state"], "CA")
        self.assertEqual(payload["data"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
