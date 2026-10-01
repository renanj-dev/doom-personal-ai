"""Register a Doom Emergency Override / Break Glass credential.

Run from the project root:
    python scripts/register_emergency_key.py

The generated key is displayed once. Store it securely; Doom stores only a
PBKDF2-derived hash of the credential.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.safety_legal import register_break_glass  # noqa: E402


def main() -> int:
    settings = get_settings()
    init_db()
    db = SessionLocal()
    try:
        label = input("Nome da chave [Emergency Override]: ").strip() or "Emergency Override"
        row, key = register_break_glass(db, label)
        credential_id = row.id
        credential_label = row.label
    finally:
        db.close()

    print("\n=== DOOM EMERGENCY OVERRIDE / BREAK GLASS ===")
    print(f"ID: {credential_id}")
    print(f"Nome: {credential_label}")
    print("\nCHAVE — MOSTRADA APENAS AGORA:")
    print(key)
    print("\nGuarde essa chave em local seguro. O Doom não armazena a chave original.")
    print("Hard blocks continuam bloqueados mesmo com Emergency Override.")
    print(f"Configuração atual: {settings.emergency_session_minutes} min de validade por autorização.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
