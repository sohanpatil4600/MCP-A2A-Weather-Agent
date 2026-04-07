from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("weather")

# Constants
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"


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
                return {"error": "Resource not found (404)", "code": -32601} # Method not found equivalent
            elif response.status_code == 403:
                return {"error": "Access Forbidden (403)", "code": -32000} # Server error equivalent
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            return {"error": "Request timed out", "code": -32001}
        except Exception as e:
            return {"error": str(e), "code": -32603} # Internal error

@mcp.tool()
async def get_capabilities() -> str:
    """Get the weather server's capabilities and protocol version support.
    
    Returns standard server metadata for handshake negotiation.
    """
    import json
    capabilities = {
        "server": "MCP Weather Pro",
        "version": "2.1.0",
        "protocol_version": "2024-11-05", # Following Anthropic's MCP versioning
        "supported_regions": ["US", "Global"],
        "auth_methods": ["None", "Simulation_Token"],
        "throttling": "Enabled (Simulated)",
        "features": {
            "real_time_alerts": True,
            "geocoding": True,
            "forecast_3day": True,
            "sse_streaming": True
        }
    }
    return f"CAPABILITIES_JSON: {json.dumps(capabilities)}"

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
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if "error" in data:
        return f"Protocol Error: {data['error']} (Code: {data['code']})"

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)

# --- Global Weather Support (Open-Meteo) ---

OPEN_METEO_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_API_URL = "https://api.open-meteo.com/v1/forecast"

@mcp.tool()
async def get_coordinates(city_name: str) -> str:
    """Get latitude and longitude for a city name.
    
    Args:
        city_name: Name of the city (e.g. "Paris", "Tokyo")
    """
    url = f"{OPEN_METEO_GEO_URL}?name={city_name}&count=1&language=en&format=json"
    headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            data = response.json()
            
            if "results" not in data or not data["results"]:
                return f"Could not find coordinates for {city_name}"
                
            result = data["results"][0]
            name = result.get("name")
            country = result.get("country")
            lat = result.get("latitude")
            lon = result.get("longitude")
            
            return f"Found {name}, {country}: Latitude {lat}, Longitude {lon}"
        except Exception as e:
            return f"Error fetching coordinates: {str(e)}"

@mcp.tool()
async def get_global_forecast(latitude: Any, longitude: Any) -> str:
    """Get global weather forecast for coordinates.
    
    Args:
        latitude: Latitude of the location (e.g. 51.5)
        longitude: Longitude of the location (e.g. -0.12)
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
    except ValueError:
        return f"Error: Latitude and Longitude must be numbers. Received: {latitude}, {longitude}"

    # Fetch daily forecast (max/min temp, rain, wind, uv, sunrise/set)
    url = f"{OPEN_METEO_API_URL}?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,wind_speed_10m_max,uv_index_max,sunrise,sunset&timezone=auto"
    headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            data = response.json()
            
            if "daily" not in data:
                return "Could not fetch global forecast data."
                
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
                
            return "\n\n".join(forecasts)
        except Exception as e:
            return f"Error fetching global forecast: {str(e)}"

@mcp.resource("echo://{message}")
def echo_resource(message: str) -> str:
    """Echo a message as a resource"""
    return f"Resource echo: {message}"