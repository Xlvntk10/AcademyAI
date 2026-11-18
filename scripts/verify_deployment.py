"""Readiness probe for the published STATIC SITE origin. Never sends OTP or writes progress.

The final rejected logout request checks CSRF without a cookie. Run only after
publication is authorized. Use --ca-file for an explicitly trusted local test CA.
"""
import argparse
import json
import re
import ssl
from urllib.parse import urlparse
import httpx


def check(response, status, label):
    if response.status_code != status:
        raise RuntimeError(f"{label}: expected HTTP {status}, received {response.status_code}")
    return response


def private(response):
    for header in ("Cache-Control", "CDN-Cache-Control"):
        if "no-store" not in response.headers.get(header, "").lower():
            raise RuntimeError(f"Private API missing {header}: no-store")
    if int(response.headers.get("Age", "0")) > 0:
        raise RuntimeError("A private API response was served from a shared cache")


def verify(client):
    home = check(client.get("/"), 200, "Frontend")
    if "text/html" not in home.headers.get("content-type", "") or 'id="root"' not in home.text:
        raise RuntimeError("Frontend shell missing")
    for route in ("/today", "/learn", "/plan", "/progress"):
        page = check(client.get(route), 200, route)
        if 'id="root"' not in page.text:
            raise RuntimeError("React route rewrite missing")
    worker = check(client.get("/sw.js"), 200, "Service Worker")
    if "javascript" not in worker.headers.get("content-type", ""):
        raise RuntimeError("Service Worker returned a wrong MIME type")
    match = re.search(r"const PRECACHE = (\[.*?\]);", worker.text)
    if not match:
        raise RuntimeError("Service Worker precache missing")
    paths = json.loads(match.group(1))
    for path in paths:
        if not path.startswith("/") or path.startswith(("//", "/api")):
            raise RuntimeError("Unsafe resource in precache")
        check(client.get(path), 200, "Precache resource")
    manifest = check(client.get("/manifest.webmanifest"), 200, "Manifest").json()
    if manifest.get("scope") != "/" or manifest.get("display") != "standalone":
        raise RuntimeError("Invalid PWA manifest")
    health = check(client.get("/api/health"), 200, "API health")
    private(health)
    if health.json() != {"status":"ok", "schema":"cloud_0001"}:
        raise RuntimeError("Cloud API schema mismatch")
    session = check(client.get("/api/auth/session"), 200, "Anonymous session")
    private(session)
    if session.json() != {"mode":"supabase", "user":None}:
        raise RuntimeError("Account mode must be enabled in production")
    private(check(client.get("/api/progress"), 401, "Anonymous access"))
    private(check(client.post("/api/auth/logout", json={}, headers={"Origin":"https://academy-invalid.example", "X-Academy-Request":"1"}), 403, "CSRF rejection"))
    return {"frontend_routes":4,"precache_resources":len(paths),"cloud_schema":"cloud_0001",
            "anonymous_access_blocked":True,"private_cache_disabled":True,"csrf_rejected":True,
            "real_login_and_cookie_replay":"manual check required"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="HTTPS origin of the STATIC SITE, not the API")
    parser.add_argument("--ca-file", help="Optional trusted CA file; TLS verification is never disabled")
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        parser.error("Provide one HTTPS origin without credentials, path or query")
    context = ssl.create_default_context(cafile=args.ca_file)
    with httpx.Client(base_url=args.url.rstrip("/"), verify=context, timeout=90, follow_redirects=False, trust_env=False) as client:
        print(json.dumps(verify(client), ensure_ascii=False, indent=2))
