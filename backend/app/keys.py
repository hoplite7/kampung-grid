"""Where the two long-term keys live.

In real life these belong to two DIFFERENT organisations:
  - the SYSTEM key belongs to Kampung Grid,
  - the INCIDENT (authority) key belongs to the agency that declares incidents.
In this prototype both are files in backend/.keys/ (created on first run, never
committed), and only authority.py ever touches the authority key.
They can also be supplied as 64-character hex strings in .env
(KG_SYSTEM_KEY, KG_AUTHORITY_KEY).
"""

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_DIR = Path(os.getenv("KG_KEY_DIR", Path(__file__).resolve().parent.parent / ".keys"))


def load_or_create(name: str, env_var: str) -> bytes:
    if os.getenv(env_var):
        return bytes.fromhex(os.environ[env_var])
    path = KEY_DIR / f"{name}.key"
    if path.exists():
        return path.read_bytes()
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    key = AESGCM.generate_key(bit_length=256)
    path.write_bytes(key)
    try:
        path.chmod(0o600)  # readable only by this user
    except OSError:
        pass
    return key
