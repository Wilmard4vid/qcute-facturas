"""Extraccion de productos desde facturas (PDF con texto, PDF escaneado o foto).

Idea central: en lugar de un patron por proveedor, cada linea se acepta como producto solo si
contiene tres numeros que cumplan  cantidad x precio = total  (o x 1.19 si el total trae IVA).
Eso funciona igual para Bambella, Samy, Lovers, remisiones escritas a mano, etc.
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
from dataclasses import dataclass, field
from itertools import permutations

import pdfplumber

from . import config

try:  # OCR opcional (fotos y PDF escaneados)
    import pytesseract
    from PIL import Image, ImageOps

    if os.name == "nt":
        for _r in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                   r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
            if os.path.exists(_r):
                pytesseract.pytesseract.tesseract_cmd = _r
                break
    pytesseract.get_tesseract_version()
    OCR_DISPONIBLE = True
except Exception:  # noqa: BLE001
    OCR_DISPONIBLE = False

EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
@dataclass
class Item:
    referencia: str
    nombre: str
    cantidad: float
    costo: float
    total: float
    ean: str = ""
    total_con_iva: bool = False  # el total de la linea ya traia IVA


@dataclass
class Documento:
    archivo: str
    local: str | None
    proveedor: str
    items: list[Item]
    totales_impresos: list[int] = field(default_factory=list)
    ivas_impresos: list[int] = field(default_factory=list)
    lineas_no_leidas: list[str] = field(default_factory=list)
    metodo: str = "reglas"   # reglas | ocr | ia
    texto: str = ""

    @property
    def suma(self) -> int:
        """Suma cantidad x costo (sin IVA cuando la factura lo discrimina)."""
        return int(round(sum(i.cantidad * i.costo for i in self.items)))

    @property
    def suma_lineas(self) -> int:
        return int(round(sum(i.total for i in self.items)))

    @property
    def total_que_cuadra(self) -> int | None:
        """Total impreso que coincide con la suma (base o con IVA). Tolera 1 peso de redondeo por linea."""
        tol = max(2, len(self.items))
        for t in self.totales_impresos:
            if abs(t - self.suma) <= tol or abs(t - self.suma_lineas) <= tol:
                return t
            for iva in self.ivas_impresos:  # precios de linea con IVA incluido
                if abs(t + iva - self.suma) <= tol:
                    return t + iva
        return None


# ---------------------------------------------------------------------------
# Utilidades de texto y numeros
# ---------------------------------------------------------------------------
def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def valores_posibles(tok: str) -> list[float]:
    """Todas las lecturas razonables de un numero escrito con formato colombiano o gringo.
    '4.500' -> [4500, 4.5]   '1.710.400' -> [1710400]   '6.500,00' -> [6500]   '12.0' -> [12]"""
    s = tok.strip().lstrip("$").rstrip(".").strip()
    if not s or not re.fullmatch(r"\d[\d.,]*", s):
        return []
    if len(re.sub(r"\D", "", s)) >= 10 and not re.search(r"[.,]", s):
        return []  # codigos de barras / NIT, no son montos
    vals: set[float] = set()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):          # 1.234,56
            vals.add(float(s.replace(".", "").replace(",", ".")))
        else:                                     # 1,234.56
            vals.add(float(s.replace(",", "")))
    elif "," in s:
        partes = s.split(",")
        if all(len(p) == 3 for p in partes[1:]):  # 21,664 -> miles
            vals.add(float(s.replace(",", "")))
        if len(partes) == 2 and len(partes[1]) != 3:  # 0,0  /  4,5 -> decimal
            vals.add(float(s.replace(",", ".")))
    elif "." in s:
        partes = s.split(".")
        if all(len(p) == 3 for p in partes[1:]):  # 4.500 / 1.710.400 -> miles
            vals.add(float(s.replace(".", "")))
        if len(partes) == 2:                      # 12.0 / 4.500 (decimal)
            vals.add(float(s))
    else:
        vals.add(float(s))
    return sorted(vals)


TOKEN_NUM_PEGADO = re.compile(r"^(\d[\d.,]*)([A-Za-z]{2,})$")   # 4.00UNIDAD, 12PCS
UNIDADES = {"UNIDAD", "UNIDADES", "UND", "UNI", "UN", "UDS", "PCS", "PZ", "DZ", "DOC", "PAQ", "ST",
            "CJ", "CAJA", "X"}
PALABRAS_NO_PRODUCTO = ("TOTAL", "SUBTOTAL", "IVA", "FIRMA", "NIT", "TELEFONO", "FECHA", "PAGINA",
                        "AUTORIZACION", "RESOLUCION", "CUFE", "DESCUENTO", "RETE", "BASE GRAVABLE",
                        "BASE EXENTA", "SALDO", "CANTIDAD TOTAL", "TOTAL ITEMS", "VALOR EN LETRAS")


def tokenizar(linea: str) -> list[str]:
    linea = linea.replace("|", " ").replace("\t", " ")
    linea = re.sub(r"\$\s+", "$", linea)
    toks = []
    for t in linea.split():
        m = TOKEN_NUM_PEGADO.match(t)
        if m and normalizar(m.group(2)) in UNIDADES:
            toks.extend([m.group(1), m.group(2)])
        else:
            toks.append(t)
    return toks


def es_codigo(tok: str) -> bool:
    """Parece una referencia de producto: tiene digitos y letras, o guion, o es numero largo."""
    t = tok.strip(".,:;")
    if len(t) < 3 or len(t) > 30:
        return False
    tiene_d = any(c.isdigit() for c in t)
    tiene_l = any(c.isalpha() for c in t)
    return tiene_d and (tiene_l or "-" in t or len(t) >= 4)


def limpiar_nombre(nombre: str, ref: str = "") -> str:
    nombre = re.sub(r"(?<=[A-Za-z])\?(?=[A-Za-z])", "Ñ", nombre)
    toks = [t for t in nombre.split() if not re.fullmatch(r"REF[\w-]+", normalizar(t))
            and not re.fullmatch(r"/?L\d{3,5}(/\S*)?", normalizar(t))]
    while toks and normalizar(toks[-1].strip(".,")) in UNIDADES:
        toks.pop()
    while toks and normalizar(toks[0].strip(".,")) in UNIDADES:
        toks.pop(0)
    return " ".join(toks).strip(" -/")


def es_porcentaje(toks: list[str], i: int) -> bool:
    return toks[i].endswith("%") or (i + 1 < len(toks) and toks[i + 1].startswith("%"))


# ---------------------------------------------------------------------------
# Lectura de una linea de producto
# ---------------------------------------------------------------------------
def leer_linea(linea: str) -> Item | None:
    toks = tokenizar(linea)
    if len(toks) < 4:
        return None
    norm = normalizar(linea)
    empieza_con_codigo = es_codigo(toks[0]) or re.fullmatch(r"\d{12,14}", toks[0]) or (
        re.fullmatch(r"\d{1,3}", toks[0]) and (es_codigo(toks[1]) or re.fullmatch(r"\d{3,}", toks[1])))
    if not empieza_con_codigo and any(re.search(r"(?<![A-Z])" + p + r"(?![A-Z])", norm)
                                      for p in PALABRAS_NO_PRODUCTO):
        return None

    # numeros candidatos (posicion, lecturas posibles)
    nums = []
    for i, t in enumerate(toks):
        if es_porcentaje(toks, i):
            continue
        vs = valores_posibles(t)
        if vs:
            nums.append((i, vs))
    if len(nums) < 3:
        return None

    # buscar (cantidad, precio, total) con cantidad*precio == total
    mejor = None
    for (iq, vq), (ip, vp), (it, vt) in permutations(nums, 3):
        if not (iq < it and ip < it):
            continue
        for q in vq:
            if q <= 0 or q > 5000:
                continue
            for p in vp:
                if p <= 0:
                    continue
                for t in vt:
                    for factor, con_iva in ((1.0, False), (1.19, True)):
                        esperado = q * p * factor
                        if t >= 1 and abs(esperado - t) <= max(1.5, t * 0.0015):
                            # puntuacion: total lo mas a la derecha, precio junto al total, sin IVA preferido
                            score = (it * 10) - abs(it - ip) - (5 if con_iva else 0) \
                                - (3 if q != int(q) else 0) - (2 if iq > ip else 0) \
                                + (8 if p == int(p) and t == int(t) else 0) + (4 if p >= 50 else 0) \
                                - (25 if iq == 0 else 0) + (3 if ip == iq + 1 else 0) \
                                - (6 if toks[iq].startswith("0") and len(toks[iq]) > 1 and "." not in toks[iq] else 0)
                            if mejor is None or score > mejor[0]:
                                mejor = (score, iq, ip, it, q, p, t, con_iva)
    if not mejor:
        return None
    _, iq, ip, it, q, p, t, con_iva = mejor

    # ---- referencia / ean ----------------------------------------------------
    inicio_nums = min(iq, ip)
    usados = {iq, ip, it}
    pre = [(i, t.strip(".,:;")) for i, t in enumerate(toks[:inicio_nums])]
    if not pre:
        return None
    # numero de item consecutivo al inicio (1, 2, 3...) seguido de un codigo
    if len(pre) > 1 and re.fullmatch(r"\d{1,3}", pre[0][1]) and (es_codigo(pre[1][1]) or len(pre) > 2):
        pre = pre[1:]
    ean = ""
    i_ref = None
    if re.fullmatch(r"\d{12,14}", pre[0][1]):                     # EAN al inicio
        ean = pre[0][1]
        if len(pre) > 1 and es_codigo(pre[1][1]) and any(c.isalpha() for c in pre[1][1]):
            i_ref = pre[1][0]                                       # EAN + codigo interno (Loreal)
        else:
            i_ref = pre[0][0]                                       # solo EAN (Samy)
    elif es_codigo(pre[0][1]) or re.fullmatch(r"\d{3,}", pre[0][1]):
        i_ref = pre[0][0]                                           # referencia primero
    elif len(pre) > 1 and (es_codigo(pre[-1][1]) or re.fullmatch(r"\d{3,}", pre[-1][1])):
        i_ref = pre[-1][0]                                          # descripcion primero, ref despues
    else:
        primero = pre[0][1]
        resto_letras = re.sub(r"[^A-Z]", "", normalizar(" ".join(t for _, t in pre[1:])))
        if re.fullmatch(r"[A-Z]{3,}", primero) and len(pre) > 1 and (
                len(primero) >= 10 or primero in resto_letras):
            i_ref = pre[0][0]                                       # ref solo letras (SH Maquillaje)
    ref = toks[i_ref].strip(".,:;") if i_ref is not None else ""
    descartar = usados | ({i_ref} if i_ref is not None else set())
    if ean:
        descartar |= {i for i, t in enumerate(toks) if t == ean}

    # ---- nombre: texto restante antes del total ---------------------------------
    palabras = []
    for i, tok in enumerate(toks[:it]):
        if i in descartar or (pre and i < pre[0][0]):
            continue
        limpio = tok.strip(",;:")
        if normalizar(limpio) in UNIDADES and not palabras:
            continue
        if re.fullmatch(r"\$?[\d.,]+%?", limpio) and i > ip:
            continue  # columnas numericas (iva, descuentos) entre precio y total
        if re.fullmatch(r"\d{8,}(-\d)?", limpio):
            continue  # manifiestos, codigos de barras embebidos
        if limpio in ("-", "%", "$", "|"):
            continue
        palabras.append(limpio)
    nombre = limpiar_nombre(" ".join(palabras), ref)
    if sum(c.isalpha() for c in nombre) < 3:
        if not ref:
            return None
        nombre = ""

    return Item(referencia=ref, nombre=nombre, cantidad=q, costo=p, total=t, ean=ean,
                total_con_iva=con_iva)


# ---------------------------------------------------------------------------
# Deteccion de local, proveedor y totales
# ---------------------------------------------------------------------------
def detectar_local(texto: str, archivo: str) -> str | None:
    """Puntua cada local: sucursal/observacion (12) > cliente/senores (10) > nombre de archivo (8)
    > cualquier parte del texto (1). Cada fuente cuenta una sola vez por local."""
    nombre_arch = normalizar(re.sub(r"[_\-.]+", " ", os.path.splitext(archivo)[0]))
    lineas = normalizar(texto).splitlines()
    fuertes = [l for l in lineas if re.search(r"\b(SUC|SUCURSAL|OBSERVACION|OBSERVA)\b", l)]
    campos = [l for l in lineas if any(c in l for c in config.CAMPOS_CLIENTE)]
    todo = " ".join(lineas)
    puntos = {}
    for local, alias in config.LOCAL_ALIAS.items():
        pats = [re.compile(r"(?<![A-Z0-9])" + re.escape(normalizar(a)) + r"(?![A-Z0-9])") for a in alias]
        hay = lambda txt: any(p.search(txt) for p in pats)  # noqa: E731
        puntos[local] = (12 if any(hay(l) for l in fuertes) else 0) \
            + (10 if any(hay(l) for l in campos) else 0) \
            + (8 if hay(nombre_arch) else 0) + (1 if hay(todo) else 0)
    orden = sorted(puntos.values(), reverse=True)
    if orden[0] == 0 or orden[0] == orden[1]:
        return None
    return max(puntos, key=puntos.get)


def detectar_proveedor(texto: str, archivo: str) -> str:
    t = normalizar(texto[:3000]) + " " + normalizar(archivo)
    for clave, marca in config.PROVEEDORES.items():
        if re.search(r"(?<![A-Z])" + re.escape(normalizar(clave)) + r"(?![A-Z])", t):
            return marca
    return ""


ETIQUETAS_TOTAL = r"(TOTAL A PAGAR|A PAGAR|TOTAL NETO|TOTAL FACTURA|TOTAL OPERACION|TOTAL BRUTO|" \
                  r"VALOR TOTAL|GRAN TOTAL|SUBTOTAL|SUB-TOTAL|SUB TOTAL|TOTAL|VALOR)"


def detectar_ivas(texto: str) -> list[int]:
    res = []
    for linea in normalizar(texto).splitlines():
        m = re.search(r"(?<![A-Z])I\.?\s?V\.?\s?A\.?(?![A-Z])", linea)
        if m and "RETE" not in linea[max(0, m.start() - 8):m.start()]:
            toks = tokenizar(linea[m.end():])
            for i, tok in enumerate(toks):
                if es_porcentaje(toks, i):
                    continue
                for v in valores_posibles(tok):
                    if v >= 100 and v == int(v):
                        res.append(int(v))
    return list(dict.fromkeys(res))


def detectar_totales(texto: str) -> list[int]:
    """Todos los montos que aparecen junto a una etiqueta de total (se usan para verificar)."""
    res = []
    for linea in normalizar(texto).splitlines():
        solo_numeros = re.fullmatch(r"[\d.,$\s%-]+", linea.strip() or "x")
        if not re.search(ETIQUETAS_TOTAL, linea) and not solo_numeros:
            continue
        for tok in tokenizar(linea):
            for v in valores_posibles(tok):
                if v >= 1000 and v == int(v):
                    res.append(int(v))
    return list(dict.fromkeys(res))


# ---------------------------------------------------------------------------
# Lectura del archivo
# ---------------------------------------------------------------------------
def _ocr(imagen) -> str:
    imagen = ImageOps.exif_transpose(imagen).convert("L")
    if imagen.width < 1800:
        f = 1800 / imagen.width
        imagen = imagen.resize((int(imagen.width * f), int(imagen.height * f)))
    try:
        return pytesseract.image_to_string(imagen, lang="spa", config="--psm 6")
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(imagen, config="--psm 6")


def leer_texto(nombre: str, datos: bytes) -> tuple[str, str]:
    """Devuelve (texto, metodo)."""
    ext = os.path.splitext(nombre)[1].lower()
    if ext == ".pdf":
        with pdfplumber.open(io.BytesIO(datos)) as pdf:
            texto = "\n".join((p.extract_text() or "") for p in pdf.pages)
            if len(texto.strip()) > 40:
                return texto, "reglas"
            if not OCR_DISPONIBLE:
                return "", "sin_texto"
            return "\n".join(_ocr(p.to_image(resolution=300).original) for p in pdf.pages), "ocr"
    if ext in EXT_IMAGEN:
        if not OCR_DISPONIBLE:
            return "", "sin_texto"
        return _ocr(Image.open(io.BytesIO(datos))), "ocr"
    raise ValueError(f"Formato no soportado: {ext}")


STOP_CONTINUACION = ("GRACIAS", "TOTAL", "FIRMA", "OBSERV", "SON:", "PAGINA", "VALOR", "CUFE",
                     "MILLONES", "PESOS", "CREDITO", "VENCE", "DEVOLUCION")


def extraer(nombre: str, datos: bytes) -> Documento:
    texto, metodo = leer_texto(nombre, datos)
    items: list[Item] = []
    no_leidas: list[str] = []
    previo: Item | None = None          # item al que se le puede continuar el nombre
    sin_nombre: Item | None = None      # item esperando nombre en el renglon siguiente
    texto_suelto: str | None = None     # renglon de texto justo antes (nombre partido arriba)
    for linea in texto.splitlines():
        l = linea.strip()
        if not l:
            continue
        it = leer_linea(l)
        if it:
            if not it.nombre:
                if texto_suelto:
                    it.nombre = limpiar_nombre(texto_suelto, it.referencia)
                    if no_leidas and no_leidas[-1] == texto_suelto:
                        no_leidas.pop()
                else:
                    sin_nombre = it
            items.append(it)
            previo = it if it.nombre else None
            texto_suelto = None
            continue
        n = normalizar(l)
        es_texto = bool(re.search(r"[A-Za-z]{3,}", l)) and not any(st in n for st in STOP_CONTINUACION) \
            and n.strip(". ") not in UNIDADES
        if sin_nombre and es_texto:
            sin_nombre.nombre = limpiar_nombre(re.sub(r"\s+\d+([.,]\d+)?$", "", l), sin_nombre.referencia)
            sin_nombre = None
            continue
        # continuacion corta del nombre del item anterior (p. ej. "CARAMELO")
        if previo and len(l) <= 30 and re.fullmatch(r"[A-Za-zÀ-ÿÑñ .,/()&'-]+", l) and es_texto:
            previo.nombre = f"{previo.nombre} {l}".strip()
            previo = None
            continue
        previo = None
        texto_suelto = l if es_texto and len(l) <= 90 else None
        if re.search(r"\d", l) and re.search(r"[A-Za-z]{3,}", l) and len(l) > 12:
            no_leidas.append(l)
        elif texto_suelto and re.search(r"REF", n):
            no_leidas.append(l)

    return Documento(archivo=nombre, local=detectar_local(texto, nombre),
                     proveedor=detectar_proveedor(texto, nombre), items=items,
                     totales_impresos=detectar_totales(texto), ivas_impresos=detectar_ivas(texto),
                     lineas_no_leidas=no_leidas,
                     metodo=metodo, texto=texto)
