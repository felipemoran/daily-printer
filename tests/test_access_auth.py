import asyncio
import base64
import hashlib
import hmac
import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

import jwt
from aiohttp import web
from aiohttp.test_utils import TestServer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from access_auth import RETRY_AFTER_SECONDS, AccessCerts, AccessDenied, AccessVerifier  # noqa: E402

TEAM = "daily-printer.cloudflareaccess.com"
AUDIENCE = "4714c1358e65fe4b408ad6d432a5f878f08194bdb4752441fd56faefa9b2b6f2"
KEY_A = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KEY_B = rsa.generate_private_key(public_exponent=65537, key_size=2048)
STRANGER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def key_set(keys: dict[str, rsa.RSAPrivateKey]) -> dict:
    published = []
    for kid, key in keys.items():
        jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        published.append({**jwk, "kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": published}


class FakeCerts(jwt.PyJWKClient):
    def __init__(self, keys: dict[str, rsa.RSAPrivateKey], **options) -> None:
        super().__init__(f"https://{TEAM}/cdn-cgi/access/certs", **options)
        self.published = dict(keys)
        self.fetches = 0

    def fetch_data(self) -> dict:
        self.fetches += 1
        return key_set(self.published)


def claims(**overrides) -> dict:
    now = int(time.time())
    base = {
        "aud": [AUDIENCE],
        "email": "friend@example.com",
        "exp": now + 86400,
        "iat": now,
        "nbf": now,
        "iss": f"https://{TEAM}",
        "type": "app",
        "identity_nonce": "6ei69kawdKzMIAPF",
        "sub": "7335d417-61da-459d-899c-0a01c76a2f94",
        "country": "BR",
    }
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


def sign(payload: dict, key=KEY_A, kid: str = "a") -> str:
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def segment(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class AccessVerifierTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.certs = FakeCerts({"a": KEY_A})
        self.verifier = AccessVerifier(TEAM, AUDIENCE, keys=self.certs)

    async def assertDenied(self, token):
        with self.assertRaises(AccessDenied) as caught:
            await self.verifier.verify(token)
        self.assertNotIn("\n", caught.exception.reason)
        return caught.exception.reason

    async def test_valid_token_returns_the_email(self):
        self.assertEqual(await self.verifier.verify(sign(claims())), "friend@example.com")

    async def test_rejects_wrong_audience(self):
        await self.assertDenied(sign(claims(aud=["another-application"])))

    async def test_accepts_audience_as_a_single_string(self):
        self.assertEqual(await self.verifier.verify(sign(claims(aud=AUDIENCE))), "friend@example.com")

    async def test_rejects_wrong_issuer(self):
        for issuer in ["https://other-team.cloudflareaccess.com", f"https://{TEAM}/", f"http://{TEAM}"]:
            with self.subTest(issuer=issuer):
                await self.assertDenied(sign(claims(iss=issuer)))

    async def test_rejects_token_expired_beyond_leeway(self):
        await self.assertDenied(sign(claims(exp=int(time.time()) - 120)))

    async def test_accepts_token_expired_within_leeway(self):
        self.assertEqual(await self.verifier.verify(sign(claims(exp=int(time.time()) - 30))), "friend@example.com")

    async def test_rejects_token_without_expiry(self):
        await self.assertDenied(sign(claims(exp=None)))

    async def test_rejects_token_signed_by_unknown_key(self):
        await self.assertDenied(sign(claims(), key=STRANGER, kid="stranger"))

    async def test_rejects_token_without_kid(self):
        await self.assertDenied(jwt.encode(claims(), KEY_A, algorithm="RS256"))

    async def test_reason_carries_nothing_from_the_token(self):
        reason = await self.assertDenied(sign(claims(), key=STRANGER, kid="evil\nINJECTED log line"))
        self.assertNotIn("INJECTED", reason)

    async def test_rejects_token_with_known_kid_but_wrong_signature(self):
        await self.assertDenied(sign(claims(), key=STRANGER, kid="a"))

    async def test_rejects_alg_none(self):
        token = jwt.encode(claims(), None, algorithm="none", headers={"kid": "a"})
        await self.assertDenied(token)

    async def test_rejects_hs256_signed_with_the_public_key(self):
        secret = KEY_A.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        signing_input = f"{segment({'alg': 'HS256', 'kid': 'a', 'typ': 'JWT'})}.{segment(claims())}"
        signature = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
        token = f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
        await self.assertDenied(token)

    async def test_rejects_missing_or_empty_email(self):
        await self.assertDenied(sign(claims(email=None)))
        await self.assertDenied(sign(claims(email="")))

    async def test_rejects_garbage_and_absent_tokens(self):
        for token in ["not-a-jwt", "a.b.c", "", None]:
            with self.subTest(token=token):
                await self.assertDenied(token)

    async def test_fetches_keys_again_when_a_new_kid_appears(self):
        certs = FakeCerts({"a": KEY_A}, cooldown_duration=0)
        verifier = AccessVerifier(TEAM, AUDIENCE, keys=certs)
        self.assertEqual(await verifier.verify(sign(claims())), "friend@example.com")
        certs.published["b"] = KEY_B
        rotated = sign(claims(email="colleague@example.com"), key=KEY_B, kid="b")
        self.assertEqual(await verifier.verify(rotated), "colleague@example.com")
        self.assertEqual(await verifier.verify(sign(claims())), "friend@example.com")
        self.assertEqual(certs.fetches, 2)

    async def test_caches_the_key_set_between_requests(self):
        for _ in range(3):
            await self.verifier.verify(sign(claims()))
        self.assertEqual(self.certs.fetches, 1)


class AccessCertsClockTest(unittest.TestCase):
    """Synchronous on purpose: the fake clock replaces time.monotonic, which an event loop also reads."""

    def setUp(self):
        self.now = 1000.0
        self.up = True
        self.fetches = 0
        for patcher in [
            mock.patch("time.monotonic", lambda: self.now),
            mock.patch.object(jwt.PyJWKClient, "fetch_data", side_effect=self.fetch),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.certs = AccessCerts(f"https://{TEAM}/cdn-cgi/access/certs")
        self.token = sign(claims())

    def fetch(self) -> dict:
        self.fetches += 1
        if not self.up:
            raise jwt.PyJWKClientConnectionError("endpoint down")
        return key_set({"a": KEY_A})

    def key_id(self) -> str:
        return self.certs.get_signing_key_from_jwt(self.token).key_id

    def test_fetches_again_once_the_retry_wait_has_passed(self):
        self.up = False
        with self.assertRaises(jwt.PyJWKClientError):
            self.key_id()
        self.now += RETRY_AFTER_SECONDS - 1
        with self.assertRaises(jwt.PyJWKClientError):
            self.key_id()
        self.assertEqual(self.fetches, 1)
        self.up = True
        self.now += 1
        self.assertEqual(self.key_id(), "a")
        self.assertEqual(self.fetches, 2)

    def test_serves_the_last_good_keys_across_cache_lifespans_while_the_endpoint_fails(self):
        self.assertEqual(self.key_id(), "a")
        self.up = False
        for fetches in [2, 3, 4]:
            self.now += 301
            self.assertEqual(self.key_id(), "a")
            self.assertEqual(self.fetches, fetches)


class CertsEndpointTest(unittest.IsolatedAsyncioTestCase):
    TIMEOUT = 0.5
    RESPONSES = {
        "ok": lambda: web.json_response(key_set({"a": KEY_A})),
        "server error": lambda: web.Response(status=500, text="upstream down"),
        "html page": lambda: web.Response(text="<html>Cloudflare error</html>", content_type="text/html"),
        "no keys": lambda: web.json_response({"keys": []}),
    }

    async def asyncSetUp(self):
        self.mode = "ok"
        self.requests = 0
        self.release = asyncio.Event()
        app = web.Application()
        app.router.add_get("/cdn-cgi/access/certs", self.certs)
        self.server = TestServer(app)
        await self.server.start_server()
        self.addAsyncCleanup(self.server.close)
        self.addCleanup(self.release.set)

    async def certs(self, request: web.Request) -> web.Response:
        self.requests += 1
        if self.mode == "hang":
            await self.release.wait()
            return web.Response(status=504)
        return self.RESPONSES[self.mode]()

    def verifier(self, **options) -> AccessVerifier:
        url = str(self.server.make_url("/cdn-cgi/access/certs"))
        return AccessVerifier(TEAM, AUDIENCE, keys=AccessCerts(url, timeout=self.TIMEOUT, **options))

    async def verify_many(self, verifier: AccessVerifier, count: int = 8) -> tuple[list, float]:
        started = time.monotonic()
        results = await asyncio.gather(*(verifier.verify(sign(claims())) for _ in range(count)), return_exceptions=True)
        return results, time.monotonic() - started

    async def test_fetches_keys_over_http(self):
        self.assertEqual(await self.verifier().verify(sign(claims())), "friend@example.com")

    async def test_certs_endpoint_failures_become_access_denied(self):
        for mode in ["server error", "html page", "no keys"]:
            with self.subTest(mode):
                self.mode = mode
                with self.assertRaises(AccessDenied):
                    await self.verifier().verify(sign(claims()))

    async def test_cached_keys_survive_a_failed_refresh(self):
        for mode in ["server error", "html page", "no keys"]:
            with self.subTest(mode):
                self.mode = "ok"
                verifier = self.verifier(lifespan=0.05)
                await verifier.verify(sign(claims()))
                await asyncio.sleep(0.1)
                self.mode = mode
                self.assertEqual(await verifier.verify(sign(claims())), "friend@example.com")

    async def test_hung_endpoint_at_start_costs_one_timeout_for_concurrent_requests(self):
        self.mode = "hang"
        results, elapsed = await self.verify_many(self.verifier())
        self.assertEqual(self.requests, 1)
        self.assertTrue(all(isinstance(result, AccessDenied) for result in results), results)
        self.assertLess(elapsed, 3 * self.TIMEOUT)

    async def test_hung_refresh_serves_cached_keys_after_one_timeout(self):
        verifier = self.verifier(lifespan=0.05)
        await verifier.verify(sign(claims()))
        await asyncio.sleep(0.1)
        self.mode = "hang"
        results, elapsed = await self.verify_many(verifier)
        self.assertEqual(self.requests, 2)
        self.assertEqual(results, ["friend@example.com"] * 8)
        self.assertLess(elapsed, 3 * self.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
