"""Register, list or remove the Webex webhook for Maply's trip bot.

    python scripts/webex_webhook.py register https://<your-public-url>
    python scripts/webex_webhook.py list
    python scripts/webex_webhook.py delete

Uses WEBEX_ACCESS_TOKEN (the bot's token) and WEBEX_WEBHOOK_SECRET from .env. The public URL is
where Webex can reach this Flask app, e.g. an ngrok tunnel to http://127.0.0.1:5000.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.mapquest_service import setting  # noqa: E402

API_URL = "https://webexapis.com/v1"
WEBHOOK_NAME = "Maply trip bot"
TIMEOUT = (4, 15)


def call(method: str, path: str, **kwargs) -> dict:
    token = setting("WEBEX_ACCESS_TOKEN")
    if not token:
        sys.exit("WEBEX_ACCESS_TOKEN is not set in .env. Use the bot's access token.")
    response = requests.request(method, f"{API_URL}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT, **kwargs)
    if response.status_code == 401:
        sys.exit("Webex rejected WEBEX_ACCESS_TOKEN. Check that it is the bot's access token.")
    response.raise_for_status()
    return response.json() if response.content else {}


def maply_webhooks() -> list[dict]:
    return [hook for hook in call("GET", "/webhooks").get("items", []) if hook.get("name") == WEBHOOK_NAME]


def delete() -> None:
    hooks = maply_webhooks()
    for hook in hooks:
        call("DELETE", f"/webhooks/{hook['id']}")
        print(f"Removed webhook -> {hook['targetUrl']}")
    if not hooks:
        print("No Maply webhook to remove.")


def register(base_url: str) -> None:
    secret = setting("WEBEX_WEBHOOK_SECRET")
    if not secret:
        sys.exit(
            "WEBEX_WEBHOOK_SECRET is not set. Add a random secret to .env first, for example:\n"
            f"WEBEX_WEBHOOK_SECRET={secrets.token_hex(24)}"
        )
    if not base_url.startswith("https://"):
        sys.exit("Webex needs a public https:// URL, e.g. https://abc123.ngrok-free.app")

    me = call("GET", "/people/me")
    if me.get("type") != "bot":
        print(f"Warning: this token belongs to {me.get('displayName')} ({me.get('type')}), not a bot. "
              "Personal tokens expire after 12 hours and the bot would answer your own messages.")
    delete()
    target = base_url.rstrip("/") + "/webex/webhook"
    hook = call(
        "POST",
        "/webhooks",
        json={"name": WEBHOOK_NAME, "targetUrl": target, "resource": "messages", "event": "created", "secret": secret},
    )
    print(f"Registered {hook['id']} -> {target}")
    print(f"Add {me.get('displayName')} ({', '.join(me.get('emails', []))}) to a Webex space and @mention it, "
          "or message it directly. Try: Cubao to Makati")


def list_hooks() -> None:
    hooks = maply_webhooks()
    for hook in hooks:
        print(f"{hook['id']}  {hook.get('status', '?'):9}  {hook['targetUrl']}")
    if not hooks:
        print("No Maply webhook registered.")


def main(argv: list[str]) -> None:
    if len(argv) >= 2 and argv[0] == "register":
        register(argv[1])
    elif argv[:1] == ["list"]:
        list_hooks()
    elif argv[:1] == ["delete"]:
        delete()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
