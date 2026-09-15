"""
Twilio SMS integration.

Credentials (Account SID, Auth Token, From number) are stored ENCRYPTED in
MongoDB `business_settings.twilio.*`. Auth Token ciphertext is the only
sensitive field; SID + From are stored in plaintext.

Public API:
    async send_sms(sid, encrypted_auth_token, from_number, to_number, body) -> dict
        returns {"sid": <message_sid>, "status": <twilio_status>}
    async send_test_sms(sid, encrypted_auth_token, from_number, to_number) -> dict
"""
from __future__ import annotations

import asyncio
from typing import Any

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from settings_crypto import decrypt_str


class TwilioError(Exception):
    def __init__(self, status: int, message: str, code: int | None = None):
        self.status = status
        self.message = message
        self.code = code
        super().__init__(message)


def _map_error(e: TwilioRestException) -> TwilioError:
    """Twilio error codes to human-friendly messages.
    https://www.twilio.com/docs/api/errors
    """
    code = e.code
    status = e.status or 502
    if code == 20003:
        return TwilioError(401, "Invalid Twilio Account SID or Auth Token.", code)
    if code == 21211:
        return TwilioError(400, "Invalid destination phone number (must be E.164, e.g. +14165551234).", code)
    if code == 21606:
        return TwilioError(400, "This Twilio phone number can't send SMS to that region.", code)
    if code == 21608:
        return TwilioError(
            400,
            "Twilio trial account: the destination number is not verified. "
            "Verify it in the Twilio Console → Phone Numbers → Verified Caller IDs, "
            "or upgrade to a paid Twilio account to send to any number.",
            code,
        )
    if code == 21610:
        return TwilioError(400, "Destination has opted out of receiving SMS (STOP).", code)
    if code == 21614:
        return TwilioError(400, "Destination number is not SMS-capable.", code)
    if code == 21659:
        return TwilioError(400, "Sender ('From') number is not owned by this Twilio account.", code)
    if code == 21408:
        return TwilioError(400, "Your Twilio account doesn't have permission to send to this country.", code)
    return TwilioError(status, f"Twilio error ({code}): {e.msg}", code)


def _client(sid: str, encrypted_auth_token: str) -> Client:
    auth_token = decrypt_str(encrypted_auth_token)
    return Client(sid, auth_token)


def _send_sync(sid: str, encrypted_auth_token: str, from_number: str,
               to_number: str, body: str) -> dict[str, Any]:
    try:
        client = _client(sid, encrypted_auth_token)
        msg = client.messages.create(body=body, from_=from_number, to=to_number)
        return {"sid": msg.sid, "status": msg.status or "queued"}
    except TwilioRestException as e:
        raise _map_error(e)


async def send_sms(sid: str, encrypted_auth_token: str, from_number: str,
                   to_number: str, body: str) -> dict:
    # Enforce a small max length so accidental floods don't happen.
    if len(body) > 1500:
        body = body[:1497] + "..."
    return await asyncio.to_thread(
        _send_sync, sid, encrypted_auth_token, from_number, to_number, body
    )


async def send_test_sms(sid: str, encrypted_auth_token: str, from_number: str,
                        to_number: str) -> dict:
    body = "Curry & Co. test SMS — Twilio integration is working. Reply STOP to unsubscribe."
    return await send_sms(sid, encrypted_auth_token, from_number, to_number, body)
