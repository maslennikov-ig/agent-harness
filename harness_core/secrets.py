from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


class SecretVaultError(ValueError):
    pass


class SecretVault:
    """Small passphrase vault used when applying private overlays.

    The default on a real machine should be age where available. This built-in
    envelope keeps bootstrap self-contained and testable with Python stdlib.
    """

    format = "harness-v1"
    iterations = 240_000

    def encrypt_json(self, payload: dict[str, Any], passphrase: str) -> str:
        salt = os.urandom(16)
        nonce = os.urandom(16)
        key = self._key(passphrase, salt)
        plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ciphertext = self._xor_stream(plaintext, key, nonce)
        tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        envelope = {
            "format": self.format,
            "kdf": "pbkdf2-sha256",
            "iterations": self.iterations,
            "salt": self._b64(salt),
            "nonce": self._b64(nonce),
            "ciphertext": self._b64(ciphertext),
            "tag": self._b64(tag),
        }
        return json.dumps(envelope, indent=2, sort_keys=True) + "\n"

    def decrypt_json(self, encrypted: str, passphrase: str) -> dict[str, Any]:
        try:
            envelope = json.loads(encrypted)
            if envelope.get("format") != self.format:
                raise SecretVaultError("unsupported secrets format")
            salt = self._unb64(envelope["salt"])
            nonce = self._unb64(envelope["nonce"])
            ciphertext = self._unb64(envelope["ciphertext"])
            expected_tag = self._unb64(envelope["tag"])
        except (KeyError, json.JSONDecodeError) as error:
            raise SecretVaultError("invalid encrypted secrets file") from error
        key = self._key(passphrase, salt)
        actual_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(actual_tag, expected_tag):
            raise SecretVaultError("invalid passphrase or corrupted secrets file")
        plaintext = self._xor_stream(ciphertext, key, nonce)
        return json.loads(plaintext.decode("utf-8"))

    def write_encrypted(self, path: str | Path, payload: dict[str, Any], passphrase: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.encrypt_json(payload, passphrase), encoding="utf-8")
        try:
            target.chmod(0o600)
        except OSError:
            pass

    def read_encrypted(self, path: str | Path, passphrase: str) -> dict[str, Any]:
        return self.decrypt_json(Path(path).read_text(encoding="utf-8"), passphrase)

    def _key(self, passphrase: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, self.iterations, dklen=32)

    def _xor_stream(self, data: bytes, key: bytes, nonce: bytes) -> bytes:
        output = bytearray()
        counter = 0
        while len(output) < len(data):
            block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
            output.extend(block)
            counter += 1
        return bytes(left ^ right for left, right in zip(data, output))

    def _b64(self, value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    def _unb64(self, value: str) -> bytes:
        return base64.b64decode(value.encode("ascii"), validate=True)
