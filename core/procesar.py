"""Une extraccion, categorizacion y Excel. Lo usa la app web y tambien se puede usar por consola."""
from __future__ import annotations

import os
import re

import pandas as pd

from .categorias import categorizar
from .excel import Bloque, Fila
from .extractor import Documento, extraer, normalizar

TIPOS = [("CUENTA DE COBRO", "CUENTA DE COBRO"), ("ORDEN DE DESPACHO", "ORDEN DE DESPACHO"),
         ("ORDEN DE PEDIDO", "ORDEN DE PEDIDO"), ("COTIZACION", "COTIZACION"), ("COTI-", "COTIZACION"),
         ("REMISION", "REMISION"), ("REM #", "REMISION"), ("FACTURA", "FACTURA"), ("ESTIMADO", "ESTIMADO")]

COLS_TABLA = ["categoria", "sub_categoria", "referencia", "nombre", "cantidad", "costo"]


def detectar_tipo_y_numero(texto: str, archivo: str) -> tuple[str, str]:
    t = normalizar(texto[:2500])
    tipo = next((v for k, v in TIPOS if k in t), "FACTURA")
    patrones = [r"COTI-\s*(\d+)",
                r"(?<![A-Z])(?:REM|REMISION|FACTURA|COTIZACION|ESTIMADO|DESPACHO|PEDIDO|COBRO)(?: DE VENTA| ELECTRONICA)*"
                r"\s*(?:NO\.?|NRO\.?|N°|#)?\s*:?\s*([A-Z]{0,4}-?\d{3,9})(?!\d)",
                r"(?<![A-Z])(?:NO|NRO|N°|NUMERO)\.?\s*[:#]?\s*([A-Z]{0,4}[- ]?\d{3,9})(?!\d)",
                r"#\s*(\d{3,9})(?!\d)"]
    for p in patrones:
        for m in re.finditer(p, t):
            n = m.group(1).replace(" ", "").lstrip("-")
            antes = t[max(0, m.start() - 12):m.start()]
            if re.search(r"TEL|NIT|CEL|CC", antes) or re.fullmatch(r"3\d{9}", n):
                continue
            return tipo, n
    nums = re.findall(r"\d{3,}", os.path.splitext(archivo)[0])
    return tipo, (nums[0] if nums else "")


def titulo_bloque(tipo: str, numero: str, proveedor: str, local: str | None, n: int, unidades: float) -> str:
    partes = [f"{tipo} {numero}".strip()]
    if proveedor:
        partes.append(proveedor)
    partes.append(local or "SIN LOCAL")
    u = int(unidades) if unidades == int(unidades) else round(unidades, 2)
    return " — ".join(partes) + f"  ({n} productos, {u} unidades)"


def documento_a_tabla(doc: Documento, taxonomia: dict, memoria: dict) -> pd.DataFrame:
    """Une lineas repetidas (misma referencia, nombre y costo) y asigna categoria."""
    filas: dict[tuple, dict] = {}
    for it in doc.items:
        k = (it.referencia.upper(), normalizar(it.nombre), round(it.costo, 2))
        if k in filas:
            filas[k]["cantidad"] += it.cantidad
            continue
        cat, sub = categorizar(it.nombre, it.referencia, taxonomia, memoria, doc.proveedor)
        ref = it.referencia.upper() if doc.metodo == "ocr" else it.referencia
        filas[k] = {"categoria": cat.strip(), "sub_categoria": sub.strip(), "referencia": ref,
                    "nombre": it.nombre, "cantidad": it.cantidad, "costo": round(it.costo, 2),
                    "ean": it.ean}
    df = pd.DataFrame(list(filas.values()), columns=COLS_TABLA + ["ean"])
    return df


def texto_exacto(taxonomia: dict | None, cat: str, sub: str) -> tuple[str, str]:
    """Devuelve categoria/subcategoria con el texto EXACTO del archivo de taxonomia (con sus espacios)."""
    for c in (taxonomia or {}):
        if c.strip() == cat.strip():
            for s_ in taxonomia[c]:
                if s_.strip() == sub.strip():
                    return c, s_
            return c, sub
    return cat, sub


def tabla_a_bloque(df: pd.DataFrame, *, titulo: str, marca: str, local: str, sumar_iva: bool,
                   archivo: str = "", proveedor: str = "", total_impreso: int | None = None,
                   taxonomia: dict | None = None) -> Bloque:
    filas = []
    for _, r in df.iterrows():
        try:
            q = float(r.get("cantidad") or 0)
            costo = float(r.get("costo") or 0)
        except (TypeError, ValueError):
            continue
        if q <= 0 and not str(r.get("nombre") or "").strip():
            continue
        if sumar_iva:
            costo = round(costo * 1.19, 2)
        cat, sub = texto_exacto(taxonomia, str(r.get("categoria") or "SIN CATEGORIZAR"),
                                str(r.get("sub_categoria") or "SIN CATEGORIZAR"))
        filas.append(Fila(categoria=cat, sub_categoria=sub,
                          nombre=str(r.get("nombre") or "").strip(),
                          referencia=str(r.get("referencia") or "").strip(),
                          marca=marca, costo=costo, cantidades={local: q},
                          ean=str(r.get("ean") or "") if "ean" in df.columns else ""))
    total = None
    if total_impreso is not None:
        total = round(total_impreso * 1.19) if sumar_iva else total_impreso
    return Bloque(titulo=titulo, filas=filas, archivo=archivo, proveedor=proveedor, local=local,
                  total_impreso=total)


def problemas_tabla(df: pd.DataFrame, taxonomia: dict) -> list[str]:
    """Avisos para que el usuario revise antes de descargar."""
    avisos = []
    sin_ref = df[df["referencia"].astype(str).str.strip() == ""]
    if len(sin_ref):
        avisos.append(f"{len(sin_ref)} producto(s) sin referencia")
    sin_cat = df[df["categoria"].astype(str).str.strip() == "SIN CATEGORIZAR"]
    if len(sin_cat):
        avisos.append(f"{len(sin_cat)} producto(s) SIN CATEGORIZAR")
    tax = {c.strip(): {x.strip() for x in v} for c, v in taxonomia.items()}
    malas = [r.sub_categoria for r in df.itertuples()
             if str(r.categoria).strip() in tax and str(r.sub_categoria).strip() not in tax[str(r.categoria).strip()]]
    if malas:
        avisos.append(f"{len(malas)} subcategoria(s) que no pertenecen a su categoria")
    rep = df.groupby(df["referencia"].astype(str).str.upper())["nombre"].nunique()
    rep = rep[(rep > 1) & (rep.index != "")]
    if len(rep):
        avisos.append("misma referencia con nombres distintos: " + ", ".join(rep.index[:5]) +
                      " (tu sistema puede necesitar referencias unicas)")
    return avisos


def procesar_archivo(nombre: str, datos: bytes, motor: str = "auto") -> Documento:
    """motor: 'reglas' (gratis) | 'ia' | 'auto' (reglas y, si no cuadra o no lee nada, IA si hay clave)."""
    from .ia import extraer_con_ia, ia_disponible

    if motor == "ia" and ia_disponible():
        return extraer_con_ia(nombre, datos)
    doc = extraer(nombre, datos)
    if motor == "auto" and ia_disponible() and (not doc.items or not doc.total_que_cuadra):
        try:
            doc_ia = extraer_con_ia(nombre, datos)
            if doc_ia.total_que_cuadra or len(doc_ia.items) > len(doc.items):
                doc_ia.texto = doc.texto or doc_ia.texto
                return doc_ia
        except Exception as e:  # noqa: BLE001
            doc.lineas_no_leidas.insert(0, f"(La IA no pudo leer este archivo: {e})")
    return doc
