#!/usr/bin/env python3
"""
Script para generar e insertar un token de enrollment directamente en la base de datos.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coordinator.node_tokens import generate_token, hash_token
from coordinator.database import db


async def create_enrollment_token(label: str = "manual-token"):
    """Genera e inserta un token en la base de datos."""

    # Conectar a la base de datos
    await db.connect()

    # Generar token
    token, payload = generate_token(label=label)
    token_hash = hash_token(token)

    # Insertar en la base de datos
    await db.conn.execute(
        """
        INSERT INTO node_tokens (id, token_hash, label)
        VALUES (?, ?, ?)
        """,
        (payload.jti, token_hash, label)
    )
    await db.conn.commit()

    await db.disconnect()

    return token, payload.jti


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "nodo-default"

    token, token_id = asyncio.run(create_enrollment_token(label))

    print("\n" + "="*60)
    print("TOKEN DE ENROLLMENT GENERADO")
    print("="*60)
    print(f"\nLabel:    {label}")
    print(f"Token ID: {token_id}")
    print(f"\nToken:\n{token}")
    print("\n" + "="*60)
    print("\nUsa este token para enrollar un nodo:")
    print(f"  ENROLLMENT_TOKEN=\"{token}\"")
    print("="*60 + "\n")
