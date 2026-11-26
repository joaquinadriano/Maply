"""Tests for the two-way Webex bot: parsing, webhook security and replies (no network)."""

import hashlib
import hmac
import json
import unittest
from unittest import mock

import app as maply
from routes import webex as webex_routes
from services import mapquest_service as mq
from services import webex_bot as bot
from services.graphhopper_service import ServiceError
from tests.test_mapquest import SAMPLE

SECRET = "test-secret"
ME = {"id": "bot-1", "displayName": "Maply", "type": "bot"}
CUBAO = {"name": "Cubao", "label": "Cubao, Quezon City, Metro Manila, Philippines", "lat": 14.6197, "lng": 121.0537}
MAKATI = {"name": "Makati", "label": "Makati, Metro Manila, Philippines", "lat": 14.5547, "lng": 121.0244}


def setUpModule():
    # Never read the developer's real .env; tests set os.environ instead.
    patcher = mock.patch.object(mq, "ENV_PATH", "does-not-exist.env")
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


def event(person="person-1", email="ana@example.com", resource="messages", kind="created"):
    return {"resource": resource, "event": kind, "data": {"id": "msg-1", "roomId": "room-1", "personId": person, "personEmail": email}}


class ParseRequestTests(unittest.TestCase):
    def test_simple_trip_defaults_to_driving_in_km(self):
        self.assertEqual(bot.parse_request("Cubao to Makati"), bot.TripRequest("Cubao", "Makati", "car", "metric"))

    def test_strips_the_mention(self):
        self.assertEqual(bot.parse_request("Maply Cubao to Makati", "Maply").origin, "Cubao")
        self.assertEqual(bot.parse_request("Maply Bot, Cubao to Makati", "Maply Bot").origin, "Cubao")

    def test_mode_and_units(self):
        request = bot.parse_request("UP Diliman to SM Megamall, walk in miles")
        self.assertEqual((request.origin, request.destination, request.mode, request.unit), ("UP Diliman", "SM Megamall", "foot", "imperial"))
        self.assertEqual(bot.parse_request("Quiapo to BGC by bike").mode, "bike")
        self.assertEqual(bot.parse_request("from Quiapo to BGC, driving, km").mode, "car")

    def test_place_names_containing_mode_words_survive(self):
        self.assertEqual(bot.parse_request("Baywalk to Intramuros").origin, "Baywalk")

    def test_help_and_unknown(self):
        self.assertEqual(bot.parse_request("Maply help", "Maply"), "help")
        self.assertEqual(bot.parse_request("", "Maply"), "help")
        self.assertIsNone(bot.parse_request("what's the weather like?"))
        self.assertIsNone(bot.parse_request("Cubao to"))


class SecurityTests(unittest.TestCase):
    def sign(self, body: bytes, secret=SECRET) -> str:
        return hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()

    def test_signature(self):
        body = b'{"a":1}'
        with mock.patch.dict("os.environ", {"WEBEX_WEBHOOK_SECRET": SECRET}):
            self.assertTrue(bot.signature_ok(body, self.sign(body)))
            self.assertFalse(bot.signature_ok(body, self.sign(body, "other")))
            self.assertFalse(bot.signature_ok(body, None))
        with mock.patch.dict("os.environ", {"WEBEX_WEBHOOK_SECRET": ""}):
            self.assertFalse(bot.signature_ok(body, self.sign(body)))

    def test_only_messages_from_people(self):
        self.assertTrue(bot.should_handle(event()))
        self.assertFalse(bot.should_handle(event(email="maply@webex.bot")))
        self.assertFalse(bot.should_handle(event(resource="memberships")))
        self.assertFalse(bot.should_handle(event(kind="deleted")))


class WebhookEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = maply.create_app().test_client()

    def post(self, payload, signature=None, secret=SECRET):
        body = json.dumps(payload).encode()
        sig = signature if signature is not None else hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
        return self.client.post("/webex/webhook", data=body, headers={"X-Spark-Signature": sig, "Content-Type": "application/json"})

    def test_refuses_without_a_secret(self):
        with mock.patch.dict("os.environ", {"WEBEX_WEBHOOK_SECRET": ""}):
            self.assertEqual(self.post(event()).status_code, 503)

    def test_rejects_bad_signature(self):
        with mock.patch.dict("os.environ", {"WEBEX_WEBHOOK_SECRET": SECRET}), mock.patch.object(webex_routes, "dispatch") as dispatch:
            self.assertEqual(self.post(event(), signature="nope").status_code, 401)
        dispatch.assert_not_called()

    def test_accepts_signed_message(self):
        with mock.patch.dict("os.environ", {"WEBEX_WEBHOOK_SECRET": SECRET}), mock.patch.object(webex_routes, "dispatch") as dispatch:
            self.assertEqual(self.post(event()).status_code, 202)
        dispatch.assert_called_once()

    def test_ignores_bot_messages(self):
        with mock.patch.dict("os.environ", {"WEBEX_WEBHOOK_SECRET": SECRET}), mock.patch.object(webex_routes, "dispatch") as dispatch:
            self.assertEqual(self.post(event(email="maply@webex.bot")).status_code, 200)
        dispatch.assert_not_called()


class HandleEventTests(unittest.TestCase):
    def setUp(self):
        bot._me = None
        bot._asks.clear()
        self.text = "Maply Cubao to Makati"
        patches = [
            mock.patch.object(bot, "_get", side_effect=self.fake_get),
            mock.patch.object(bot, "geocode", side_effect=lambda q, limit=1: [CUBAO] if "cubao" in q.lower() else [MAKATI] if "makati" in q.lower() else []),
            mock.patch.object(bot, "mapquest_route_for", side_effect=lambda o, d, mode: mq.parse_route(SAMPLE, o["name"], d["name"], mode)),
            mock.patch.object(bot, "trip_weather", return_value=None),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        post_patcher = mock.patch.object(bot, "post_markdown", return_value={"sent": True, "message": ""})
        self.post = post_patcher.start()
        self.addCleanup(post_patcher.stop)

    def fake_get(self, path):
        return ME if path == "/people/me" else {"id": "msg-1", "text": self.text}

    def reply(self):
        self.post.assert_called_once()
        room, markdown = self.post.call_args.args
        self.assertEqual(room, "room-1")
        self.assertEqual(self.post.call_args.kwargs["parent_id"], "msg-1")
        return markdown

    def test_answers_with_trip_summary(self):
        bot.handle_event(event())
        text = self.reply()
        self.assertIn("Maply trip summary (MapQuest)", text)
        self.assertIn("**From:** Cubao, Quezon City, Metro Manila, Philippines", text)
        self.assertIn("**Units:** Metric", text)

    def test_answers_in_miles(self):
        self.text = "Maply Cubao to Makati in miles"
        bot.handle_event(event())
        self.assertIn("10.0 mi", self.reply())

    def test_help(self):
        self.text = "Maply help"
        bot.handle_event(event())
        self.assertIn("Maply trip bot", self.reply())

    def test_not_understood(self):
        self.text = "Maply good morning"
        bot.handle_event(event())
        self.assertIn("I didn't catch the trip", self.reply())

    def test_unknown_place(self):
        self.text = "Maply Cubao to Atlantis"
        bot.handle_event(event())
        self.assertIn("couldn't find **Atlantis**", self.reply())

    def test_service_error_is_friendly(self):
        bot.mapquest_route_for.side_effect = ServiceError("MapQuest took too long to answer.", 504)
        bot.handle_event(event())
        self.assertIn("Sorry, I couldn't plan that trip. MapQuest took too long", self.reply())

    def test_never_answers_itself(self):
        bot.handle_event(event(person="bot-1"))
        self.post.assert_not_called()

    def test_rate_limit(self):
        for _ in range(bot.ASKS_PER_MINUTE + 1):
            bot.handle_event(event())
        self.assertIn("asking a little fast", self.post.call_args.args[1])
        self.assertEqual(bot.geocode.call_count, bot.ASKS_PER_MINUTE * 2)


class PostMarkdownTests(unittest.TestCase):
    def test_threaded_reply_sends_parent_id(self):
        from services import webex_service as webex

        with mock.patch.dict("os.environ", {"WEBEX_ACCESS_TOKEN": "tok"}):
            with mock.patch.object(webex.session, "post", return_value=mock.Mock(status_code=200)) as post:
                result = webex.post_markdown("room-1", "hi", parent_id="msg-1")
        self.assertTrue(result["sent"])
        self.assertEqual(post.call_args.kwargs["json"], {"roomId": "room-1", "markdown": "hi", "parentId": "msg-1"})


if __name__ == "__main__":
    unittest.main()
