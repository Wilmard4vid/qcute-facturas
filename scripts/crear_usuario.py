"""Genera el bloque para agregar un usuario a los secretos de la app.

Uso:  python scripts/crear_usuario.py
"""
import getpass
import re

import bcrypt

usuario = input("Usuario (sin espacios, ej. david): ").strip().lower()
if not re.fullmatch(r"[a-z0-9_.-]{3,30}", usuario):
    raise SystemExit("Usuario invalido: usa 3-30 letras minusculas, numeros, punto o guion.")
nombre = input("Nombre para mostrar: ").strip() or usuario
clave = getpass.getpass("Contraseña (min. 8 caracteres): ")
if len(clave) < 8 or clave != getpass.getpass("Repite la contraseña: "):
    raise SystemExit("La contraseña no coincide o es muy corta.")
h = bcrypt.hashpw(clave.encode(), bcrypt.gensalt(12)).decode()
print("\nPega esto en tus secretos (.streamlit/secrets.toml o Settings > Secrets):\n")
print(f'[usuarios.{usuario}]\nnombre = "{nombre}"\nhash = "{h}"\n')
