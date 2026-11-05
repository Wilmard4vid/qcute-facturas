"""Inicio de sesion con usuarios y contrasenas cifradas (bcrypt) guardados en los secretos de la app.

Formato en .streamlit/secrets.toml (o en Settings > Secrets de Streamlit Cloud):

    [usuarios.david]
    nombre = "David Gomez"
    hash = "$2b$12$...."          # generar con: python scripts/crear_usuario.py

Nunca se guarda la contrasena en texto plano.
"""
from __future__ import annotations

import time

import bcrypt
import streamlit as st

MAX_INTENTOS = 5
BLOQUEO_SEG = 300


def _usuarios() -> dict:
    try:
        return {k: dict(v) for k, v in st.secrets.get("usuarios", {}).items()}
    except Exception:  # noqa: BLE001
        return {}


def verificar(usuario: str, clave: str) -> dict | None:
    datos = _usuarios().get(usuario.strip().lower())
    if not datos or not datos.get("hash"):
        bcrypt.checkpw(b"x", bcrypt.hashpw(b"y", bcrypt.gensalt(4)))  # tiempo constante aproximado
        return None
    if bcrypt.checkpw(clave.encode(), datos["hash"].encode()):
        return {"usuario": usuario.strip().lower(), "nombre": datos.get("nombre", usuario)}
    return None


def requerir_login() -> dict:
    """Muestra el formulario de ingreso y detiene la app hasta que el usuario inicie sesion."""
    if st.session_state.get("sesion"):
        return st.session_state["sesion"]

    if not _usuarios():
        st.error("No hay usuarios configurados. Agrega la seccion [usuarios] en los secretos de la app "
                 "(ver README, paso 'Crear usuarios').")
        st.stop()

    bloqueado_hasta = st.session_state.get("bloqueado_hasta", 0)
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.markdown("## QCUTE · Facturas a plantilla")
        st.caption("Ingresa con tu usuario para continuar")
        if time.time() < bloqueado_hasta:
            st.error(f"Demasiados intentos. Espera {int(bloqueado_hasta - time.time())} segundos.")
            st.stop()
        with st.form("login"):
            usuario = st.text_input("Usuario")
            clave = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
        if entrar:
            sesion = verificar(usuario, clave)
            if sesion:
                st.session_state["sesion"] = sesion
                st.session_state["intentos"] = 0
                st.rerun()
            st.session_state["intentos"] = st.session_state.get("intentos", 0) + 1
            if st.session_state["intentos"] >= MAX_INTENTOS:
                st.session_state["bloqueado_hasta"] = time.time() + BLOQUEO_SEG
                st.session_state["intentos"] = 0
            st.error("Usuario o contraseña incorrectos")
    st.stop()


def cerrar_sesion():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
