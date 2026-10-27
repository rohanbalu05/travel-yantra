"""Read-only check: which apps are subscribed to the WhatsApp Business Account's webhooks.

    python -m app.webhook_check     (env: WHATSAPP_TOKEN, WHATSAPP_WABA_ID)

Prints only success and the subscribed app ids; never the token, the account id or any number.
Exits 0 when at least one app is subscribed, 1 otherwise. Subscribing is a Meta setting and stays
with Rohan (Graph API Explorer: POST /{WABA_ID}/subscribed_apps).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

GRAPH = "https://graph.facebook.com/v23.0"


def _error(body: bytes, status: int) -> str:
    try:
        err = json.loads(body).get("error", {})
    except ValueError:
        err = {}
    return (
        f"HTTP {status} code={err.get('code')} subcode={err.get('error_subcode')} "
        f"type={err.get('type')}"
    )


def check(token: str, waba: str, opener=urllib.request.urlopen) -> tuple[bool, str]:
    req = urllib.request.Request(
        f"{GRAPH}/{waba}/subscribed_apps", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with opener(req, timeout=20) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return False, "failed: " + _error(e.read(), e.code)
    except (urllib.error.URLError, ValueError) as e:
        return False, f"failed: {type(e).__name__}"
    ids = [
        str((a.get("whatsapp_business_api_data") or a).get("id", "?")) for a in data.get("data", [])
    ]
    return bool(ids), f"subscribed apps: {len(ids)} {ids}"


def main() -> int:
    token = os.environ.get("WHATSAPP_TOKEN", "").strip()
    waba = os.environ.get("WHATSAPP_WABA_ID", "").strip()
    if not token or not waba:
        print("failed: WHATSAPP_TOKEN or WHATSAPP_WABA_ID is unset")
        return 1
    ok, line = check(token, waba)
    print(f"success={str(ok).lower()} {line}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
