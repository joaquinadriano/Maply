"""Webhook endpoint for the two-way Webex bot (see services/webex_bot.py)."""

from threading import Thread

from flask import Blueprint, jsonify, request

from services import webex_bot
from services.mapquest_service import setting

webex = Blueprint("webex", __name__)


def dispatch(event: dict) -> None:
    """Answer in the background: Webex wants a quick 200, and planning takes a few seconds."""
    Thread(target=webex_bot.handle_event, args=(event,), daemon=True).start()


@webex.post("/webex/webhook")
def webhook():
    if not setting("WEBEX_WEBHOOK_SECRET"):
        # Without a secret anyone could trigger billable GraphHopper/MapQuest calls.
        return jsonify({"error": "The Webex bot is not set up. Add WEBEX_WEBHOOK_SECRET to .env."}), 503
    if not webex_bot.signature_ok(request.get_data(), request.headers.get("X-Spark-Signature")):
        return jsonify({"error": "Invalid signature."}), 401

    event = request.get_json(silent=True) or {}
    if webex_bot.should_handle(event):
        dispatch(event)
        return jsonify({"status": "accepted"}), 202
    return jsonify({"status": "ignored"}), 200
