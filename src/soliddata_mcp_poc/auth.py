"""Exchange a SolidData management key for a bearer token."""

import logging

import httpx

from soliddata_mcp_poc.config import get_settings

logger = logging.getLogger(__name__)


def get_mcp_token(management_key: str | None = None, timeout: float = 30.0) -> str:
    """POST management_key to the SolidData auth endpoint and return a bearer token."""
    settings = get_settings()
    key = management_key or settings.soliddata_management_key

    # Basic sanity check: avoid sending placeholder to the API
    if not key or not key.strip():
        raise ValueError(
            "SOLIDDATA_MANAGEMENT_KEY is missing or empty. "
            "Set it in your .env file (see .env.example)."
        )
    if "your_management_key" in key.lower() or "here" in key.lower():
        raise ValueError(
            "SOLIDDATA_MANAGEMENT_KEY looks like a placeholder. "
            "Replace it in .env with your real SolidData management key."
        )

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            settings.auth_endpoint,
            json={"management_key": key},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 401:
            raise ValueError(
                "SolidData returned 401 Unauthorized. "
                "Check that SOLIDDATA_MANAGEMENT_KEY in .env is correct, not expired, "
                "and valid for the auth endpoint (e.g. dev vs prod)."
            ) from None
        resp.raise_for_status()

    data = resp.json()
    if not data:
        raise ValueError(f"Auth endpoint returned empty response. Status {resp.status_code}")

    # Accept either a raw string token or an object with common key names
    if isinstance(data, str):
        token = data.strip()
    elif isinstance(data, dict):
        token = (
            data.get("token")
            or data.get("access_token")
            or data.get("accessToken")
        )
        if not token or not isinstance(token, str):
            raise ValueError(
                "Auth endpoint returned a JSON object but no 'token' or 'access_token' field."
            )
    else:
        raise ValueError(f"Unexpected auth response type: {type(data)}")

    # Normalize: return raw token only (no "Bearer " prefix) so callers can add it consistently
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    logger.info("MCP bearer token obtained successfully.")
    return token


if __name__ == "__main__":
    """Run only the auth exchange and print the raw API response."""
    settings = get_settings()
    key = settings.soliddata_management_key
    if not key or not key.strip():
        raise SystemExit("SOLIDDATA_MANAGEMENT_KEY is missing or empty in .env")
    if "your_management_key" in key.lower() or "here" in key.lower():
        raise SystemExit("SOLIDDATA_MANAGEMENT_KEY looks like a placeholder in .env")

    print("Auth endpoint:", settings.auth_endpoint)
    print("Request body: {\"management_key\": \"<redacted>\"}\n")

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            settings.auth_endpoint,
            json={"management_key": key},
            headers={"Content-Type": "application/json"},
        )

    print("Status:", resp.status_code)
    print("Response headers:", dict(resp.headers))
    print("Response body (raw):", resp.text)
