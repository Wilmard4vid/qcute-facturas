"""Genera el Excel con el formato exacto de la plantilla QCUTE (hoja 'Consolidado')."""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .config import COLUMNAS, LOCALES, VALORES_FIJOS

FUENTE = Font(name="Calibri", size=12)
FUENTE_TITULO = Font(name="Calibri", size=12, bold=True)
RELLENO_TITULO = PatternFill("solid", start_color="FFF2CC")
ANCHOS = [16, 32, 40, 14, 14, 7, 5, 15, 6, 19, 10, 16, 22, 17, 19, 19]


@dataclass
class Fila:
    categoria: str
    sub_categoria: str
    nombre: str
    referencia: str
    marca: str
    costo: float
    cantidades: dict[str, float]  # local -> cantidad
    ean: str = ""


@dataclass
class Bloque:
    titulo: str
    filas: list[Fila]
    # datos para la hoja de verificacion
    archivo: str = ""
    proveedor: str = ""
    local: str = ""
    total_impreso: int | None = None
    resumen: dict = field(default_factory=dict)


def _numero(v: float):
    v = round(float(v), 2)
    return int(v) if v == int(v) else v


def _orden(f: Fila):
    return (f.categoria.strip(), f.sub_categoria.strip(), str(f.referencia))


def consolidar(bloques: list[Bloque]) -> list[Fila]:
    """Une filas con la misma referencia, marca y costo; suma cantidades por local."""
    unidas: dict[tuple, Fila] = {}
    for b in bloques:
        for f in b.filas:
            k = (str(f.referencia).strip().upper() or f.nombre.upper(), f.marca, round(f.costo, 2))
            if k in unidas:
                for loc, q in f.cantidades.items():
                    unidas[k].cantidades[loc] = unidas[k].cantidades.get(loc, 0) + q
            else:
                unidas[k] = Fila(**{**f.__dict__, "cantidades": dict(f.cantidades)})
    return sorted(unidas.values(), key=_orden)


def _escribir_fila(ws, r: int, f: Fila):
    valores = {**VALORES_FIJOS, "categoria": f.categoria, "sub_categoria": f.sub_categoria,
               "nombre": f.nombre, "referencia": str(f.referencia), "marca": f.marca,
               "ean": f.ean or None, "costo": _numero(f.costo)}
    for loc, col in LOCALES.items():
        valores[col] = _numero(f.cantidades.get(loc, 0))
    for c, nombre_col in enumerate(COLUMNAS, start=1):
        celda = ws.cell(row=r, column=c, value=valores.get(nombre_col))
        celda.font = FUENTE
        if nombre_col in ("referencia", "ean"):
            celda.number_format = "@"


def generar_excel(bloques: list[Bloque], separar_por_factura: bool = True) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Consolidado"
    for c, h in enumerate(COLUMNAS, start=1):
        ws.cell(row=1, column=c, value=h).font = FUENTE
    for i, w in enumerate(ANCHOS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    r = 2
    if separar_por_factura:
        for b in bloques:
            for c in range(1, len(COLUMNAS) + 1):
                ws.cell(row=r, column=c).fill = RELLENO_TITULO
            t = ws.cell(row=r, column=1, value=b.titulo)
            t.font = FUENTE_TITULO
            t.alignment = Alignment(horizontal="left")
            r += 1
            for f in sorted(b.filas, key=_orden):
                _escribir_fila(ws, r, f)
                r += 1
    else:
        for f in consolidar(bloques):
            _escribir_fila(ws, r, f)
            r += 1

    # ---- hoja de verificacion (no afecta la hoja que se importa) ----
    v = wb.create_sheet("Verificacion")
    enc = ["archivo", "proveedor", "local", "productos", "unidades", "suma costo x cantidad",
           "total impreso en la factura", "diferencia", "estado"]
    for c, h in enumerate(enc, start=1):
        v.cell(row=1, column=c, value=h).font = FUENTE_TITULO
    for i, b in enumerate(bloques, start=2):
        suma = sum(f.costo * sum(f.cantidades.values()) for f in b.filas)
        unidades = sum(sum(f.cantidades.values()) for f in b.filas)
        dif = None if b.total_impreso is None else round(suma - b.total_impreso)
        estado = "SIN TOTAL PARA COMPARAR" if dif is None else ("OK" if abs(dif) <= max(2, len(b.filas)) else "REVISAR")
        fila = [b.archivo, b.proveedor, b.local, len(b.filas), _numero(unidades), round(suma),
                b.total_impreso, dif, estado]
        for c, val in enumerate(fila, start=1):
            cel = v.cell(row=i, column=c, value=val)
            cel.font = FUENTE
            if c in (6, 7, 8):
                cel.number_format = '#,##0'
    for i, w in enumerate([45, 22, 16, 11, 11, 20, 26, 12, 24], start=1):
        v.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
