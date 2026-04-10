from __future__ import annotations

from typing import Any
import json
import re
import httpx
from mcp.server.fastmcp import FastMCP

try:
    from server.security import PolicyEngine, AgentIdentity
except ModuleNotFoundError:
    # Supports direct execution via: mcp run /path/to/server/weather.py
    from security import PolicyEngine, AgentIdentity

# Initialize FastMCP server
mcp = FastMCP("weather")
policy_engine = PolicyEngine()

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"
SERVER_NAME = "MCP Weather Pro"
SERVER_VERSION = "2.2.0"
SCHEMA_VERSION = "1.0.0"
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05",)


class ProtocolError(Exception):
    """Typed protocol error for deterministic tool responses."""

    def __init__(self, code: int, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "get_capabilities": {
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["server", "version", "schema_version", "protocol"],
        },
    },
    "negotiate_protocol": {
        "input_schema": {
            "type": "object",
            "required": ["client_protocol_version"],
            "properties": {
                "client_protocol_version": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["ok", "selected_protocol_version", "supported_protocol_versions"],
        },
    },
    "get_alerts": {
        "input_schema": {
            "type": "object",
            "required": ["state"],
            "properties": {
                "state": {"type": "string", "pattern": "^[A-Za-z]{2}$"},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["ok"],
        },
    },
    "get_coordinates": {
        "input_schema": {
            "type": "object",
            "required": ["city_name"],
            "properties": {
                "city_name": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["ok"],
        },
    },
    "get_global_forecast": {
        "input_schema": {
            "type": "object",
            "required": ["latitude", "longitude"],
            "properties": {
                "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                "longitude": {"type": "number", "minimum": -180, "maximum": 180},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": ["ok"],
        },
    },
}


def _serialize_ok(data: dict[str, Any]) -> str:
    payload = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "data": data,
    }
    return json.dumps(payload)


def _serialize_error(error: ProtocolError) -> str:
    payload = {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "error": error.to_dict(),
    }
    return json.dumps(payload)


def _enforce_policy(
    tool_name: str,
    agent_role: str = "supervisor",
    region: str = "US",
) -> tuple[bool, str | None]:
    """Check policy before tool execution. Returns (allowed, error_json or None)."""
    identity = AgentIdentity(
        issuer="mcp-weather-server",
        subject="agent",
        audience="weather-tools",
        role=agent_role,
    )
    decision = policy_engine.evaluate_tool_access(
        tool_name=tool_name,
        identity=identity,
        region=region,
    )
    if not decision.allowed:
        error = ProtocolError(
            code=-32000,
            message="Access denied by policy",
            details=decision.to_dict(),
        )
        return False, _serialize_error(error)
    return True, None


def _validate_state(state: str) -> str:
    normalized = state.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", normalized):
        raise ProtocolError(
            code=-32602,
            message="Invalid params",
            details={"field": "state", "reason": "Must be a two-letter US state code"},
        )
    return normalized


def _validate_city_name(city_name: str) -> str:
    normalized = city_name.strip()
    if not normalized:
        raise ProtocolError(
            code=-32602,
            message="Invalid params",
            details={"field": "city_name", "reason": "City name cannot be empty"},
        )
    if len(normalized) > 120:
        raise ProtocolError(
            code=-32602,
            message="Invalid params",
            details={"field": "city_name", "reason": "City name exceeds 120 characters"},
        )
    return normalized


def _coerce_coordinate(name: str, value: Any, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ProtocolError(
            code=-32602,
            message="Invalid params",
            details={"field": name, "reason": "Must be numeric"},
        )
    if parsed < min_value or parsed > max_value:
        raise ProtocolError(
            code=-32602,
            message="Invalid params",
            details={"field": name, "reason": f"Must be in range [{min_value}, {max_value}]"},
        )
    return parsed


def _build_capabilities() -> dict[str, Any]:
    return {
        "server": SERVER_NAME,
        "version": SERVER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "protocol": {
            "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "default_protocol_version": SUPPORTED_PROTOCOL_VERSIONS[0],
            "compatibility_policy": {
                "minor_backward_compatible": True,
                "major_breaking_requires_new_version": True,
                "deprecation_notice_days": 90,
            },
        },
        "supported_regions": ["US", "Global"],
        "auth_methods": ["None", "Simulation_Token"],
        "throttling": "Enabled (Simulated)",
        "features": {
            "real_time_alerts": True,
            "geocoding": True,
            "forecast_3day": True,
            "sse_streaming": True,
            "protocol_negotiation": True,
            "contract_validation": True,
            "policy_enforcement": True,
        },
        "tool_contracts": TOOL_CONTRACTS,
        "security": {
            "policy_engine_enabled": True,
            "requires_authenticated_identity": False,
        },
    }


async def make_nws_request(url: str) -> dict[str, Any]:
    """Make a request to the NWS API with proper error handling and protocol status mapping."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json"
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            if response.status_code == 404:
                return {"error": "Resource not found (404)", "code": -32601}
            elif response.status_code == 403:
                return {"error": "Access Forbidden (403)", "code": -32000}
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            return {"error": "Request timed out", "code": -32001}
        except Exception as e:
            return {"error": str(e), "code": -32603}

@mcp.tool()
async def get_capabilities() -> str:
    """Get the weather server's capabilities and protocol version support.
    
    Returns standard server metadata for handshake negotiation.
    """
    return _serialize_ok(_build_capabilities())


@mcp.tool()
async def negotiate_protocol(client_protocol_version: str) -> str:
    """Negotiate the protocol version between client and server."""
    version = client_protocol_version.strip()
    if not version:
        return _serialize_error(
            ProtocolError(
                code=-32602,
                message="Invalid params",
                details={"field": "client_protocol_version", "reason": "Cannot be empty"},
            )
        )

    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        return _serialize_error(
            ProtocolError(
                code=-32010,
                message="Protocol version mismatch",
                details={
                    "client_protocol_version": version,
                    "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
                },
            )
        )

    return _serialize_ok(
        {
            "selected_protocol_version": version,
            "supported_protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
            "compatibility": "accepted",
        }
    )

def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
        Event: {props.get('event', 'Unknown')}
        Area: {props.get('areaDesc', 'Unknown')}
        Severity: {props.get('severity', 'Unknown')}
        Description: {props.get('description', 'No description available')}
        Instructions: {props.get('instruction', 'No specific instructions provided')}
        """

@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state.

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
    allowed, error_response = _enforce_policy("get_alerts", region="US")
    if not allowed:
        return error_response or ""

    try:
        normalized_state = _validate_state(state)
    except ProtocolError as error:
        return _serialize_error(error)

    url = f"{NWS_API_BASE}/alerts/active/area/{normalized_state}"
    data = await make_nws_request(url)

    if "error" in data:
        return _serialize_error(
            ProtocolError(
                code=data["code"],
                message="Upstream request failed",
                details={"upstream_error": data["error"]},
            )
        )

    if not data or "features" not in data:
        return _serialize_error(
            ProtocolError(
                code=-32603,
                message="Malformed upstream response",
                details={"source": "NWS", "expected_field": "features"},
            )
        )

    if not data["features"]:
        return _serialize_ok({"state": normalized_state, "alerts": [], "count": 0})

    alerts = [format_alert(feature) for feature in data["features"]]
    return _serialize_ok(
        {
            "state": normalized_state,
            "count": len(alerts),
            "alerts": alerts,
            "summary": "\n---\n".join(alerts),
        }
    )

# --- Global Weather Support (Open-Meteo) ---

OPEN_METEO_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_API_URL = "https://api.open-meteo.com/v1/forecast"

@mcp.tool()
async def get_coordinates(city_name: str) -> str:
    """Get latitude and longitude for a city name.
    
    Args:
        city_name: Name of the city (e.g. "Paris", "Tokyo")
    """
    allowed, error_response = _enforce_policy("get_coordinates", region="Global")
    if not allowed:
        return error_response or ""

    try:
        normalized_city = _validate_city_name(city_name)
    except ProtocolError as error:
        return _serialize_error(error)

    url = f"{OPEN_METEO_GEO_URL}?name={normalized_city}&count=1&language=en&format=json"
    headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            data = response.json()
            
            if "results" not in data or not data["results"]:
                return _serialize_error(
                    ProtocolError(
                        code=-32601,
                        message="Location not found",
                        details={"city_name": normalized_city},
                    )
                )
                
            result = data["results"][0]
            name = result.get("name")
            country = result.get("country")
            lat = result.get("latitude")
            lon = result.get("longitude")
            
            return _serialize_ok(
                {
                    "city_name": normalized_city,
                    "name": name,
                    "country": country,
                    "latitude": lat,
                    "longitude": lon,
                    "summary": f"Found {name}, {country}: Latitude {lat}, Longitude {lon}",
                }
            )
        except Exception as e:
            return _serialize_error(
                ProtocolError(
                    code=-32603,
                    message="Coordinate lookup failed",
                    details={"error": str(e)},
                )
            )

@mcp.tool()
async def get_global_forecast(latitude: Any, longitude: Any) -> str:
    """Get global weather forecast for coordinates.
    
    Args:
        latitude: Latitude of the location (e.g. 51.5)
        longitude: Longitude of the location (e.g. -0.12)
    """
    allowed, error_response = _enforce_policy("get_global_forecast", region="Global")
    if not allowed:
        return error_response or ""

    try:
        lat = _coerce_coordinate("latitude", latitude, -90, 90)
        lon = _coerce_coordinate("longitude", longitude, -180, 180)
    except ProtocolError as error:
        return _serialize_error(error)

    # Fetch daily forecast (max/min temp, rain, wind, uv, sunrise/set)
    url = f"{OPEN_METEO_API_URL}?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,wind_speed_10m_max,uv_index_max,sunrise,sunset&timezone=auto"
    headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            data = response.json()
            
            if "daily" not in data:
                return _serialize_error(
                    ProtocolError(
                        code=-32603,
                        message="Malformed forecast response",
                        details={"expected_field": "daily"},
                    )
                )
                
            daily = data["daily"]
            times = daily["time"]
            max_temps = daily["temperature_2m_max"]
            min_temps = daily["temperature_2m_min"]
            precip = daily["precipitation_sum"]
            wind = daily.get("wind_speed_10m_max", [])
            uv = daily.get("uv_index_max", [])
            sunrise = daily.get("sunrise", [])
            sunset = daily.get("sunset", [])
            
            forecasts = []
            for i in range(min(5, len(times))): # Next 5 days
                # Extract time only from sunrise/sunset (YYYY-MM-DDTHH:MM)
                sr_time = sunrise[i].split("T")[1] if i < len(sunrise) else "N/A"
                ss_time = sunset[i].split("T")[1] if i < len(sunset) else "N/A"
                wind_speed = wind[i] if i < len(wind) else "N/A"
                uv_index = uv[i] if i < len(uv) else "N/A"
                
                forecasts.append(
                    f"--- Date: {times[i]} ---\n"
                    f"* 🌡️ Temp: Max {max_temps[i]}°C / Min {min_temps[i]}°C\n"
                    f"* 🌧️ Precip: {precip[i]}mm\n"
                    f"* 💨 Wind: {wind_speed} km/h\n"
                    f"* ☀️ UV Index: {uv_index}\n"
                    f"* 🌅 Sun: Rise {sr_time} / Set {ss_time}\n"
                )
                
            return _serialize_ok(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "days": len(forecasts),
                    "forecast": forecasts,
                    "summary": "\n\n".join(forecasts),
                }
            )
        except Exception as e:
            return _serialize_error(
                ProtocolError(
                    code=-32603,
                    message="Forecast lookup failed",
                    details={"error": str(e)},
                )
            )

@mcp.resource("echo://{message}")
def echo_resource(message: str) -> str:
    """Echo a message as a resource"""
    return f"Resource echo: {message}"