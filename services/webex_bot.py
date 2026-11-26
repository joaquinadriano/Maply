"""Two-way Webex bot: answers "@Maply Cubao to Makati, drive" with a MapQuest trip summary.

Webex calls /webex/webhook when someone messages the bot (an @mention in a group room, or any
message in a 1:1 space). The webhook only carries the message id, so the bot fetches the text,
works out the trip, plans it with MapQuest (plus weather) and replies in a thread under the
question. Message formatting is shared with the automatic summaries in webex_service.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic, time

import requests

from services.graphhopper_service import ServiceError, geocode
from services.mapquest_service import route_for as mapquest_route_for
from services.mapquest_service import setting
from services.weather_service import trip_weather
from services.webex_service import build_summary, post_markdown

log = logging.getLogger(__name__)

API_URL = "https://webexapis.com/v1"
TIMEOUT = (4, 10)
session = requests.Session()

# Each answer costs two GraphHopper geocodes, one MapQuest route and two weather calls,
# so one person can ask at most this many times a minute.
ASKS_PER_MINUTE = 5
_asks: dict[str, deque] = defaultdict(deque)
_asks_lock = Lock()
_me: dict | None = None

MODE_WORDS = {
    "car": ("drive", "driving", "car", "by car"),
    "bike": ("bike", "biking", "cycle", "cycling", "bicycle", "by bike"),
    "foot": ("walk", "walking", "foot", "on foot"),
}
UNIT_WORDS = {
    "imperial": ("miles", "in miles", "mi", "english", "imperial"),
    "metric": ("km", "in km", "kilometres", "kilometers", "metric"),
}
_OPTION = {word: ("mode", mode) for mode, words in MODE_WORDS.items() for word in words}
_OPTION.update({word: ("unit", unit) for unit, words in UNIT_WORDS.items() for word in words})
# A trailing option such as ", drive", " by bike" or " in miles" (longest phrases first).
_TRAILING = re.compile(
    r"(?:\s*,\s*|\s+)(?:by\s+|in\s+)?(" + "|".join(sorted(map(re.escape, _OPTION), key=len, reverse=True)) + r")\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"\s+to\s+", re.IGNORECASE)

HELP = "\n".join(
    [
        "### 🗺️ Maply trip bot",
        "Ask me for a trip in Metro Manila and I'll reply with MapQuest's directions and the weather.",
        "",
        "- `Cubao to Makati`",
        "- `Quiapo to BGC, bike`",
        "- `UP Diliman to SM Megamall, walk in miles`",
        "",
        "Modes: **drive** (default), **bike**, **walk**. Add **miles** or **km** to pick the units.",
    ]
)


@dataclass
class TripRequest:
    origin: str
    destination: str
    mode: str = "car"
    unit: str = "metric"


def parse_request(text: str, bot_name: str = "") -> TripRequest | str | None:
    """Read a chat message. Returns a TripRequest, "help", or None when it isn't a trip."""
    text = re.sub(r"\s+", " ", text or "").strip()
    # In group rooms the message text starts with the bot's display name (the @mention).
    # Try the full name first ("Maply Bot"), then its first word ("Maply").
    name = bot_name.strip()
    for name in filter(None, dict.fromkeys([name, name.split(" ")[0]])):
        if text.lower().startswith(name.lower()):
            text = text[len(name):].lstrip(" ,:")
            break
    text = text.lstrip("@").strip()
    if not text or text.lower().strip(" ?!.") in ("help", "hi", "hello", "start", "how", "what can you do"):
        return "help"

    mode, unit = "car", "metric"
    while match := _TRAILING.search(text):
        kind, value = _OPTION[match.group(1).lower()]
        if kind == "mode":
            mode = value
        else:
            unit = value
        text = text[: match.start()].rstrip(" ,")

    parts = _SPLIT.split(re.sub(r"^(?:from|trip from|route from)\s+", "", text, flags=re.IGNORECASE), maxsplit=1)
    if len(parts) != 2 or not parts[0].strip(" ,.") or not parts[1].strip(" ,.?"):
        return None
    return TripRequest(parts[0].strip(" ,."), parts[1].strip(" ,.?"), mode, unit)


def find_place(query: str) -> dict:
    """The best Metro Manila match for a place name, as {name, lat, lng}."""
    hits = geocode(query, limit=1)
    if not hits:
        raise ServiceError(f"I couldn't find **{query}** in Metro Manila. Try a landmark, mall or barangay name.", 404)
    hit = hits[0]
    return {"name": hit.get("label") or hit.get("name") or query, "lat": hit["lat"], "lng": hit["lng"]}


def answer(request: TripRequest) -> str:
    """Plan the trip and build the reply (raises ServiceError with a friendly message)."""
    origin = find_place(request.origin)
    destination = find_place(request.destination)
    if abs(origin["lat"] - destination["lat"]) < 1e-6 and abs(origin["lng"] - destination["lng"]) < 1e-6:
        raise ServiceError("Those look like the same place. Try two different places.", 400)
    trip = mapquest_route_for(origin, destination, request.mode)
    now_ms = int(time() * 1000)
    weather = trip_weather(origin, destination, now_ms, trip.seconds, trip.mode, now_ms)
    return build_summary(trip, request.unit, weather)


# ---------- Webex plumbing ----------


def signature_ok(body: bytes, signature: str | None) -> bool:
    """Webex signs each webhook with HMAC-SHA1 of the raw body, using the webhook's secret."""
    secret = setting("WEBEX_WEBHOOK_SECRET")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def _get(path: str) -> dict:
    token = setting("WEBEX_ACCESS_TOKEN")
    response = session.get(f"{API_URL}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def bot_identity() -> dict:
    """The bot's own Webex person (cached), so it never answers itself."""
    global _me
    if _me is None:
        _me = _get("/people/me")
    return _me


def allow_ask(person_id: str) -> bool:
    now = monotonic()
    with _asks_lock:
        bucket = _asks[person_id]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= ASKS_PER_MINUTE:
            return False
        bucket.append(now)
        return True


def should_handle(event: dict) -> bool:
    """Only new messages from people (never from this or any other bot)."""
    if event.get("resource") != "messages" or event.get("event") != "created":
        return False
    data = event.get("data") or {}
    if not data.get("id") or not data.get("roomId"):
        return False
    if str(data.get("personEmail", "")).lower().endswith("@webex.bot"):
        return False
    return True


def handle_event(event: dict) -> None:
    """Answer one webhook event. Runs in a background thread; never raises."""
    data = event.get("data") or {}
    room_id, message_id, person_id = data.get("roomId"), data.get("id"), data.get("personId", "")
    try:
        me = bot_identity()
        if person_id and person_id == me.get("id"):
            return
        message = _get(f"/messages/{message_id}")
        parsed = parse_request(message.get("text", ""), me.get("displayName", ""))
        if parsed == "help":
            reply = HELP
        elif parsed is None:
            reply = "I didn't catch the trip. Try `Cubao to Makati` or `Quiapo to BGC, bike`. Say `help` for more."
        elif not allow_ask(person_id or room_id):
            reply = "You're asking a little fast. Please wait a minute and try again."
        else:
            try:
                reply = answer(parsed)
            except ServiceError as exc:
                reply = f"Sorry, I couldn't plan that trip. {exc}"
    except requests.RequestException:
        log.exception("Webex bot could not read the message")
        return
    # Reply in the question's thread (a reply to a reply must point at the thread's first message).
    result = post_markdown(room_id, reply, parent_id=message.get("parentId") or message_id)
    if not result["sent"]:
        log.warning("Webex bot reply was not sent: %s", result["message"])
