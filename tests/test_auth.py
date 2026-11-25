import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from types import SimpleNamespace

import tests.conftest  # noqa: F401
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError
from cryptography.hazmat.primitives.asymmetric import rsa

from api import auth


def bearer(token="signed-token"):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class AuthTests(unittest.TestCase):
    def test_missing_bearer_is_unauthorized(self):
        with self.assertRaises(HTTPException) as raised:
            auth.get_current_user(None)
        self.assertEqual(raised.exception.status_code, 401)

    def test_missing_oidc_configuration_fails_closed(self):
        with patch.object(auth, "OIDC_ISSUER", ""), \
                patch.object(auth, "OIDC_AUDIENCE", ""), \
                patch.object(auth, "OIDC_JWKS_URL", ""):
            with self.assertRaises(HTTPException) as raised:
                auth.get_current_user(bearer())
        self.assertEqual(raised.exception.status_code, 503)

    def test_insecure_oidc_urls_fail_closed(self):
        with patch.object(auth, "OIDC_ISSUER", "http://issuer.example/"), \
                patch.object(auth, "OIDC_AUDIENCE", "ecoguard-api"), \
                patch.object(auth, "OIDC_JWKS_URL", "http://issuer.example/jwks"):
            with self.assertRaises(HTTPException) as raised:
                auth.get_current_user(bearer())
        self.assertEqual(raised.exception.status_code, 503)

    def test_valid_token_requires_expected_issuer_and_audience(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {
            "iss": "https://issuer.example/",
            "sub": "subject-123",
            "aud": "ecoguard-api",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
        with patch.object(auth, "OIDC_ISSUER", claims["iss"]), \
                patch.object(auth, "OIDC_AUDIENCE", claims["aud"]), \
                patch.object(auth, "OIDC_JWKS_URL", "https://issuer.example/jwks"), \
                patch.object(
                    auth,
                    "_jwks_client",
                    return_value=SimpleNamespace(
                        get_signing_key_from_jwt=lambda _token: SimpleNamespace(
                            key=private_key.public_key()
                        )
                    ),
                ):
            identity = auth.get_current_user(bearer(token))

        self.assertEqual(
            identity,
            {"issuer": claims["iss"], "subject": claims["sub"]},
        )

    def test_invalid_token_is_unauthorized(self):
        with patch.object(auth, "OIDC_ISSUER", "https://issuer.example/"), \
                patch.object(auth, "OIDC_AUDIENCE", "ecoguard-api"), \
                patch.object(auth, "OIDC_JWKS_URL", "https://issuer.example/jwks"), \
                patch.object(
                    auth,
                    "_jwks_client",
                    return_value=SimpleNamespace(
                        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key="key")
                    ),
                ), \
                patch.object(auth.jwt, "decode", side_effect=PyJWTError("bad token")):
            with self.assertRaises(HTTPException) as raised:
                auth.get_current_user(bearer())
        self.assertEqual(raised.exception.status_code, 401)

    def test_jwks_outage_is_service_unavailable(self):
        with patch.object(auth, "OIDC_ISSUER", "https://issuer.example/"), \
                patch.object(auth, "OIDC_AUDIENCE", "ecoguard-api"), \
                patch.object(auth, "OIDC_JWKS_URL", "https://issuer.example/jwks"), \
                patch.object(
                    auth,
                    "_jwks_client",
                    return_value=SimpleNamespace(
                        get_signing_key_from_jwt=lambda _token: (_ for _ in ()).throw(
                            PyJWKClientConnectionError("JWKS unavailable")
                        )
                    ),
                ):
            with self.assertRaises(HTTPException) as raised:
                auth.get_current_user(bearer())
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
