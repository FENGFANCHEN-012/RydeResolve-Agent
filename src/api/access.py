"""Scoped demo access. No unauthenticated API access outside loopback."""
import hmac
import ipaddress
import os

from fastapi import HTTPException, Request
from src import config


def _loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def authorize(request: Request) -> str:
    """Return a server-assigned identity; never trust reviewer names in JSON."""
    admin_key = os.getenv("API_ADMIN_KEY", "")
    demo_key = os.getenv("API_DEMO_KEY", "")
    authorization = request.headers.get("authorization", "")
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    if token and admin_key and hmac.compare_digest(token, admin_key):
        return "admin"
    admin_route = (request.url.path.startswith(("/api/rulings", "/api/precedents", "/api/flags",
                                               "/api/people", "/api/audit")) or
                   request.url.path.startswith("/api/rag/upload") or
                   (request.url.path == "/api/rag/collection" and request.method == "DELETE"))
    if token and demo_key and hmac.compare_digest(token, demo_key):
        if admin_route:
            raise HTTPException(403, "This action requires administrator access.")
        return "demo"
    if admin_key or demo_key:
        raise HTTPException(401, "An access code is required.", headers={"WWW-Authenticate": "Bearer"})
    # Host check also blocks DNS rebinding; Origin blocks cross-site local mutations.
    if request.client and _loopback(request.client.host) and _loopback(request.url.hostname):
        origin = request.headers.get("origin")
        allowed = set(config.CORS_ORIGINS) | {str(request.base_url).rstrip("/")}
        if origin and origin not in allowed:
            raise HTTPException(403, "This website is not allowed to access the local API.")
        return "local-reviewer"
    raise HTTPException(503, "Remote access is disabled. Configure API_DEMO_KEY and API_ADMIN_KEY before publishing.")
