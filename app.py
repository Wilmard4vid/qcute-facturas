"""QCUTE · Facturas a plantilla
App web: sube facturas (PDF o foto) de cualquier proveedor, revisa/corrige, descarga el Excel.

Ejecutar en local:   streamlit run app.py
"""
from __future__ import annotations

import hashlib
from datetime import datetime

import pandas as pd
import streamlit as st

from core import auth
from core.categorias import cargar_memoria, cargar_taxonomia, guardar_memoria
from core.config import LOCALES, SIN_CATEGORIA
from core.excel import generar_excel
from core.extractor import OCR_DISPONIBLE
from core.ia import ia_disponible
from core.procesar import (COLS_TABLA, detectar_tipo_y_numero, documento_a_tabla, problemas_tabla,
                           procesar_archivo, tabla_a_bloque, titulo_bloque)

st.set_page_config(page_title="QCUTE · Facturas", page_icon="🧾", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1400px;}
  div[data-testid="stExpander"] details summary p {font-size: 1.02rem; font-weight: 600;}
  div[data-testid="stMetricValue"] {font-size: 1.25rem;}
</style>""", unsafe_allow_html=True)

sesion = auth.requerir_login()
ss = st.session_state
ss.setdefault("docs", {})          # id -> dict con el documento y sus ajustes
ss.setdefault("uploader_n", 0)

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"**{sesion['nombre']}**")
    if st.button("Cerrar sesión", use_container_width=True):
        auth.cerrar_sesion()
    st.divider()

    st.markdown("**Lectura de facturas**")
    opciones = {"auto": "Automático (reglas; IA solo si no cuadra)", "reglas": "Solo reglas (gratis)",
                "ia": "Siempre con IA"}
    if not ia_disponible():
        opciones = {"reglas": "Solo reglas (gratis)"}
    motor = st.radio("Motor", list(opciones), format_func=opciones.get, label_visibility="collapsed")
    if not ia_disponible():
        st.caption("IA desactivada: agrega ANTHROPIC_API_KEY en los secretos para leer fotos de papel "
                   "y remisiones a mano.")
    if not OCR_DISPONIBLE:
        st.caption("OCR no instalado: las fotos solo se pueden leer con IA.")
    st.divider()

    st.markdown("**Formato de salida**")
    separar = st.radio("Salida", ["Una sección por factura", "Consolidado (una fila por referencia)"],
                       label_visibility="collapsed") == "Una sección por factura"
    st.divider()

    st.markdown("**Categorías**")
    tax_subida = st.file_uploader("Reemplazar taxonomía (xlsx)", type=["xlsx"], key="tax")
    if st.button("Limpiar todo", use_container_width=True):
        ss.docs = {}
        st.rerun()


@st.cache_data(show_spinner=False)
def _taxonomia(datos: bytes | None):
    import io
    return cargar_taxonomia(io.BytesIO(datos) if datos else None)


taxonomia = _taxonomia(tax_subida.getvalue() if tax_subida else None)
todas_subs = sorted({s.strip() for subs in taxonomia.values() for s in subs})
todas_cats = [c.strip() for c in taxonomia]

# ---------------------------------------------------------------------------
# Carga de archivos
# ---------------------------------------------------------------------------
st.markdown("### Facturas a plantilla")
st.caption("Sube PDF o fotos de cualquier proveedor. Revisa cada factura, corrige lo necesario y descarga el Excel.")

archivos = st.file_uploader("Arrastra aquí las facturas", accept_multiple_files=True,
                            type=["pdf", "jpg", "jpeg", "png", "webp"], key=f"up_{ss.uploader_n}")
if archivos and st.button(f"Procesar {len(archivos)} archivo(s)", type="primary"):
    memoria = cargar_memoria()
    barra = st.progress(0.0)
    for n, f in enumerate(archivos, start=1):
        datos = f.getvalue()
        did = hashlib.md5(datos).hexdigest()[:10]
        if did in ss.docs:
            continue
        try:
            doc = procesar_archivo(f.name, datos, motor)
        except Exception as e:  # noqa: BLE001
            st.error(f"No se pudo leer **{f.name}**: {e}")
            continue
        tipo, numero = detectar_tipo_y_numero(doc.texto, f.name)
        df = documento_a_tabla(doc, taxonomia, memoria)
        ss.docs[did] = {
            "archivo": f.name, "doc": doc, "df": df, "tipo": tipo, "numero": numero,
            "total": doc.total_que_cuadra or (doc.totales_impresos[0] if doc.totales_impresos else None),
            "iva_en_linea": any(i.total_con_iva for i in doc.items),
        }
        barra.progress(n / len(archivos), text=f.name)
    barra.empty()
    ss.uploader_n += 1
    st.rerun()

if not ss.docs:
    st.info("Aún no hay facturas cargadas.")
    st.stop()

# ---------------------------------------------------------------------------
# Revision por factura
# ---------------------------------------------------------------------------
bloques, nuevas_categorias, pendientes = [], {}, 0
cfg_cols = {
    "categoria": st.column_config.SelectboxColumn("Categoría", options=todas_cats, required=True, width="small"),
    "sub_categoria": st.column_config.SelectboxColumn("Subcategoría", options=todas_subs, required=True, width="medium"),
    "referencia": st.column_config.TextColumn("Referencia", width="small"),
    "nombre": st.column_config.TextColumn("Nombre", width="medium"),
    "cantidad": st.column_config.NumberColumn("Cant.", min_value=0, step=1, width="small"),
    "costo": st.column_config.NumberColumn("Costo unit.", min_value=0, format="$ %,.0f", width="small"),
}

for did, d in list(ss.docs.items()):
    doc = d["doc"]
    local_def = doc.local if doc.local in LOCALES else None
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.1, 1.2, 1, 0.5])
        local = c1.selectbox("Local", list(LOCALES), key=f"loc_{did}",
                             index=list(LOCALES).index(local_def) if local_def else None,
                             placeholder="Elige el local")
        marca = c2.text_input("Proveedor / marca", value=doc.proveedor, key=f"mar_{did}").strip().upper()
        total = c3.number_input("Total de la factura (para verificar)", value=float(d["total"] or 0),
                                min_value=0.0, step=100.0, format="%.0f", key=f"tot_{did}")
        sumar_iva = c4.checkbox("Costo + IVA", key=f"iva_{did}",
                                help="Multiplica el costo por 1.19 en el Excel")
        if c4.button("Quitar", key=f"del_{did}"):
            del ss.docs[did]
            st.rerun()

        edit = st.data_editor(d["df"][COLS_TABLA], key=f"ed_{did}", num_rows="dynamic",
                              use_container_width=True, hide_index=True, column_config=cfg_cols)
        edit = edit.fillna({"referencia": "", "nombre": "", "cantidad": 0, "costo": 0,
                            "categoria": SIN_CATEGORIA[0], "sub_categoria": SIN_CATEGORIA[1]})
        if "ean" in d["df"].columns:
            edit["ean"] = d["df"]["ean"].reindex(edit.index).fillna("")

        suma = float((edit["cantidad"] * edit["costo"]).sum())
        unidades = float(edit["cantidad"].sum())
        dif = suma - total if total else None
        cuadra = dif is not None and abs(dif) <= max(2, len(edit))
        titulo_def = titulo_bloque(d["tipo"], d["numero"], marca, local, len(edit), unidades)
        titulo = st.text_input("Título en el Excel", value=titulo_def, key=f"tit_{did}_{local}_{marca}_{len(edit)}_{unidades}")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Archivo", d["archivo"][:28], help=d["archivo"])
        m2.metric("Productos", len(edit))
        m3.metric("Unidades", f"{unidades:,.0f}")
        m4.metric("Costo × cantidad", f"${suma:,.0f}")
        if dif is None:
            m5.metric("Verificación", "sin total", help="Escribe el total de la factura para comparar")
        else:
            m5.metric("Verificación", "Cuadra ✅" if cuadra else f"Dif ${dif:,.0f} ⚠️")

        avisos = problemas_tabla(edit, taxonomia)
        if local is None:
            avisos.insert(0, "elige el local")
        if d["iva_en_linea"] and not sumar_iva:
            avisos.append("esta factura trae el IVA dentro del total de cada línea: el costo quedó SIN IVA")
        if avisos:
            st.warning(" · ".join(avisos))
        if doc.lineas_no_leidas and (not cuadra or not len(edit)):
            with st.expander(f"Líneas del documento que no se reconocieron ({len(doc.lineas_no_leidas)})"):
                st.caption("Si alguna es un producto, agrégalo en la tabla con el botón + al final.")
                st.code("\n".join(doc.lineas_no_leidas[:80]), language=None)

    if local is None:
        pendientes += 1
        continue
    bloques.append(tabla_a_bloque(edit, titulo=titulo, marca=marca, local=local, sumar_iva=sumar_iva,
                                  archivo=d["archivo"], proveedor=marca, total_impreso=int(total) if total else None,
                                  taxonomia=taxonomia))
    for r in edit.itertuples():
        if r.referencia and r.categoria != SIN_CATEGORIA[0]:
            nuevas_categorias[r.referencia] = (r.categoria, r.sub_categoria)

# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------
st.divider()
if pendientes:
    st.error(f"{pendientes} factura(s) sin local asignado: no se incluirán hasta que elijas el local.")
if bloques:
    nombre = f"plantilla_{datetime.now():%Y%m%d_%H%M}.xlsx"
    st.download_button(f"Descargar Excel ({sum(len(b.filas) for b in bloques)} filas)",
                       data=generar_excel(bloques, separar), file_name=nombre, type="primary",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       on_click=guardar_memoria, args=(nuevas_categorias,),
                       help="Al descargar, la app recuerda las categorías que corregiste para la próxima vez")
