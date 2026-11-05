"""Extraccion con IA (API de Claude) para fotos, letra a mano o formatos que las reglas no leen.

Es OPCIONAL: solo se activa si existe la clave ANTHROPIC_API_KEY (en .streamlit/secrets.toml
o como variable de entorno). Tiene costo por uso en la cuenta de API de Anthropic.
"""
from __future__ import annotations

import base64
import json
import os
import re

from . import config
from .extractor import EXT_IMAGEN, Documento, Item, detectar_local, detectar_proveedor, limpiar_nombre

MODELO_POR_DEFECTO = "claude-sonnet-5-5"

PROMPT = f"""Eres un asistente que transcribe facturas, remisiones y cuentas de cobro de proveedores
colombianos para la empresa QCUTE. Lee el documento y devuelve SOLO un JSON valido, sin texto extra:

{{
  "proveedor": "nombre comercial del proveedor que emite el documento",
  "local": "uno de {list(config.LOCALES)} o null si no se puede saber",
  "numero_documento": "numero de factura/remision o null",
  "total_impreso": numero (subtotal o total antes de IVA si lo discrimina, si no el total) o null,
  "items": [
    {{"referencia": "codigo del producto tal cual (\\"\\" si no tiene)",
      "nombre": "descripcion del producto",
      "cantidad": numero,
      "costo": numero (precio unitario SIN IVA si la factura lo discrimina),
      "total": numero (valor total de la linea tal como aparece)}}
  ]
}}

Reglas:
- Transcribe TODAS las lineas de producto, en el orden en que aparecen. No inventes lineas.
- Los montos estan en pesos colombianos: "4.500" y "4,500" significan cuatro mil quinientos.
- Respeta las correcciones escritas a mano sobre el documento (numeros tachados o reescritos).
- El local: "ARRECIFE" (CC Arrecife, Rodadero, Santa Marta), "LA 30" (Maka La 30, Santa Marta),
  "PLAZA DEL SOL" (CC Plaza del Sol, Soledad / Barranquilla, local 176A).
"""


def clave_api() -> str | None:
    try:
        import streamlit as st
        k = st.secrets.get("ANTHROPIC_API_KEY")
        if k:
            return k
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get("ANTHROPIC_API_KEY")


def ia_disponible() -> bool:
    return bool(clave_api())


def _modelo() -> str:
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_MODEL", MODELO_POR_DEFECTO)
    except Exception:  # noqa: BLE001
        return os.environ.get("ANTHROPIC_MODEL", MODELO_POR_DEFECTO)


def _bloque(nombre: str, datos: bytes) -> dict:
    ext = os.path.splitext(nombre)[1].lower()
    b64 = base64.standard_b64encode(datos).decode()
    if ext == ".pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    if ext in EXT_IMAGEN:
        mt = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext)
        if not mt:  # bmp/tif -> convertir a png
            import io
            from PIL import Image
            buf = io.BytesIO()
            Image.open(io.BytesIO(datos)).save(buf, "PNG")
            b64, mt = base64.standard_b64encode(buf.getvalue()).decode(), "image/png"
        return {"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}}
    raise ValueError(f"Formato no soportado: {ext}")


def interpretar_respuesta(nombre: str, texto: str) -> Documento:
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        raise ValueError("La IA no devolvio un JSON valido")
    data = json.loads(m.group(0))

    def num(v) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        s = re.sub(r"[^\d.,]", "", str(v or "0"))
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
            s = re.sub(r"[.,]", "", s)
        return float(s.replace(",", ".") or 0)

    items = []
    for it in data.get("items", []):
        q, p, t = num(it.get("cantidad")), num(it.get("costo")), num(it.get("total"))
        if q <= 0:
            continue
        if not p and t:
            p = t / q
        items.append(Item(referencia=str(it.get("referencia") or "").strip(),
                          nombre=limpiar_nombre(str(it.get("nombre") or "")),
                          cantidad=q, costo=p, total=t or q * p,
                          total_con_iva=bool(t) and abs(t - q * p * 1.19) < abs(t - q * p)))
    local = data.get("local")
    local = local if local in config.LOCALES else detectar_local("", nombre)
    proveedor = detectar_proveedor(str(data.get("proveedor") or ""), nombre) or \
        str(data.get("proveedor") or "").upper()
    total = data.get("total_impreso")
    return Documento(archivo=nombre, local=local, proveedor=proveedor, items=items,
                     totales_impresos=[int(round(num(total)))] if total else [], metodo="ia",
                     texto=texto)


def extraer_con_ia(nombre: str, datos: bytes) -> Documento:
    import anthropic

    cliente = anthropic.Anthropic(api_key=clave_api())
    resp = cliente.messages.create(
        model=_modelo(),
        max_tokens=8000,
        messages=[{"role": "user", "content": [_bloque(nombre, datos), {"type": "text", "text": PROMPT}]}],
    )
    texto = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return interpretar_respuesta(nombre, texto)
