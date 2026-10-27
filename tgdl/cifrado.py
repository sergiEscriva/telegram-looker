"""Cifrado de las sesiones de Telegram con una contraseña.

Formato del archivo .session.enc:  "TGDL1" | sal (16) | nonce (16) | HMAC-SHA256 (32) | datos cifrados
- Clave derivada de la contraseña con scrypt (lento a propósito: dificulta probar contraseñas).
- AES-256-CTR para cifrar (pyaes, que ya instala Telethon) y HMAC-SHA256 para detectar una
  contraseña incorrecta o un archivo manipulado.
"""
import hashlib
import hmac
import os

import pyaes

_MAGIA = b"TGDL1"
_SAL, _NONCE, _MAC = 16, 16, 32


class ContrasenaIncorrecta(ValueError):
    pass


def _claves(contrasena: str, sal: bytes):
    k = hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=64)
    return k[:32], k[32:]


def _ctr(clave: bytes, nonce: bytes):
    return pyaes.AESModeOfOperationCTR(clave, counter=pyaes.Counter(int.from_bytes(nonce, "big")))


def cifrar(texto: str, contrasena: str) -> bytes:
    sal, nonce = os.urandom(_SAL), os.urandom(_NONCE)
    k_aes, k_mac = _claves(contrasena, sal)
    datos = _ctr(k_aes, nonce).encrypt(texto.encode("utf-8"))
    mac = hmac.new(k_mac, _MAGIA + sal + nonce + datos, hashlib.sha256).digest()
    return _MAGIA + sal + nonce + mac + datos


def descifrar(blob: bytes, contrasena: str) -> str:
    if not blob.startswith(_MAGIA) or len(blob) < len(_MAGIA) + _SAL + _NONCE + _MAC:
        raise ValueError("El archivo de sesión cifrada está dañado.")
    i = len(_MAGIA)
    sal, nonce, mac, datos = blob[i:i + 16], blob[i + 16:i + 32], blob[i + 32:i + 64], blob[i + 64:]
    k_aes, k_mac = _claves(contrasena, sal)
    if not hmac.compare_digest(mac, hmac.new(k_mac, _MAGIA + sal + nonce + datos, hashlib.sha256).digest()):
        raise ContrasenaIncorrecta("Contraseña de las sesiones incorrecta.")
    return _ctr(k_aes, nonce).decrypt(datos).decode("utf-8")
