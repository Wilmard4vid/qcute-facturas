"""Taxonomia de categorias de QCUTE + asignacion automatica + memoria de correcciones."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .config import CATEGORIA_POR_PROVEEDOR, SIN_CATEGORIA
from .extractor import normalizar

DATA = Path(__file__).resolve().parents[1] / "data"
ARCHIVO_TAXONOMIA = DATA / "categorias.xlsx"
ARCHIVO_MEMORIA = DATA / "memoria_categorias.json"


# ---------------------------------------------------------------------------
# Taxonomia oficial (CATEGORIAS_PRODUCTO_QUALITY_RESUMEN.xlsx)
# ---------------------------------------------------------------------------
def cargar_taxonomia(origen=None) -> dict[str, list[str]]:
    df = pd.read_excel(origen or ARCHIVO_TAXONOMIA)
    df.columns = [normalizar(str(c)).strip() for c in df.columns]
    tax: dict[str, list[str]] = {}
    for _, r in df.iterrows():
        # se conserva el texto EXACTO de la taxonomia (incluye espacios finales que tiene el archivo)
        cat, sub = str(r["CATEGORIA"]), str(r["SUBCATEGORIA"])
        if cat.strip() and cat != "nan" and sub.strip() and sub != "nan":
            tax.setdefault(cat, [])
            if sub not in tax[cat]:
                tax[cat].append(sub)
    tax.setdefault(SIN_CATEGORIA[0], [SIN_CATEGORIA[1]])
    return tax


# ---------------------------------------------------------------------------
# Reglas por palabra clave (se evaluan en orden; la primera que aplica gana)
# ---------------------------------------------------------------------------
TEMAS_NINA = r"(HELLO KITTY|KITTY|STITCH|STICH|K-?POP|SANRIO|KUROMI|MY MELODY|CINNAMOROLL|TOY STORY|FROZEN|" \
             r"BARBIE|PRINCESA|INFANTIL|NIÑA|NINA|NIÑAS|NINAS)"

REGLAS: list[tuple[str, str, str]] = [
    # --- infantiles primero ---
    (rf"\b(MAQUILLAJE|KIT|SET DE NIÑA|SET NIÑA)\b.*{TEMAS_NINA}|{TEMAS_NINA}.*\bMAQUILLAJE\b", "MAQUILLAJE", "NIÑA"),
    (rf"\b(BOLSO|CARTERA|MORRAL)\b.*{TEMAS_NINA}|{TEMAS_NINA}.*\b(BOLSO|CARTERA)\b", "BOLSOS", "CARTERAS / NIÑAS"),
    (r"\bSET DE NI[NÑ]A\b", "MAQUILLAJE", "NIÑA"),
    (rf"\bU[NÑ]AS?\b.*{TEMAS_NINA}|\bU[NÑ]AS NI[NÑ]AS?\b", "ACCESORIOS BELLEZA", "UÑAS / NIÑAS"),
    (rf"\b(COLLAR|PULSERA|ARETE)S?\b.*\bINFANTIL\b", "JOYERIA", "NIÑA"),
    # --- joyeria ---
    (r"\b(EARCUFFS?|CANDONGAS?|ARGOLLAS?|TOPOS?|ARETES?)\b", "JOYERIA", "ARETES / ARGOLLAS / EARCUFF / TOPOS"),
    (r"\b(CADENAS?|COLLARES?|COLLAR)\b", "JOYERIA", "COLLARES / CADENAS"),
    (r"\bJUEGOS? (RF|DE)\b|^JUEGOS?\b", "JOYERIA", "JUEGOS"),
    (r"\b(CAMANDULA|PANDORA|PULSERAS?|PULCERAS?|ANILLOS?|AROS?)\b", "JOYERIA", "PULSERAS / AROS / PULSERA / PANDORA"),
    # --- maquillaje ---
    (r"\b(PRIMER)\b", "MAQUILLAJE", "PRIMER"),
    (r"\b(BB CREAM|BASE|BASES)\b", "MAQUILLAJE", "BASE"),
    (r"\bBRONZER\b", "MAQUILLAJE", "BRONZER"),
    (r"\b(CEJAS?|CEJA)\b", "MAQUILLAJE", "CEJAS / SOMBRA DE CEJAS / BETUN DE CEJAS / JABON DE CEJAS"),
    (r"\bCONTORNO", "MAQUILLAJE", "CONTORNOS"),
    (r"\b(CORRECTOR|CORR LIQ|CORRECTORES)\b", "MAQUILLAJE", "CORRECTORES"),
    (r"\b(DELINEAD|DELINEADOR|LAPIZ DELINEAD|PLUMON|EYELINER)", "MAQUILLAJE", "DELINEADORES"),
    (r"\bILUMINADOR", "MAQUILLAJE", "ILUMINADORES"),
    (r"\b(PESTA[NÑ]INA|MASCARA|MASCA-PESTA|MASC EFECTO|LASH)\b", "MAQUILLAJE", "PESTANIÑAS"),
    (r"\b(POLVOS?|POL COMP|POLCOMP|POL COMPACTO)\b", "MAQUILLAJE", "POLVOS"),
    (r"\b(RUBOR|BLUSH)\b", "MAQUILLAJE", "RUBOR"),
    (r"\b(SOMBRAS?|PALETA)\b", "MAQUILLAJE", "SOMBRAS / SOMBRA EN PASTA / SOMBRA LIQUIDA"),
    (r"\b(TINTA|GLOSS|LIPGLOSS|BRILLOS?|BALSAMOS?|LIP OIL|LIP BALM|LIP PLUMPER|LIPBLUMPER|JELLY TINT|"
     r"MANTECA CACAO|LIP FAT|LIPS)\b", "MAQUILLAJE", "BRILLOS / TINTAS / BALSAMOS"),
    (r"\b(LABIAL|LABIALES|LAB LIQ|LAB COLORISSIMO)\b", "MAQUILLAJE", "LABIALES"),
    # --- accesorios de belleza ---
    (r"\bBROCHAS?\b|\bPINCELES\b", "ACCESORIOS BELLEZA", "BROCHAS"),
    (r"\b(CORTA[UÑ]?[NÑ]AS|CORTAUNAS|LIMAS?|DEPILADOR|CORTACUTICULA|PUSHER)\b", "ACCESORIOS BELLEZA",
     "CORTAUÑAS / LIMAS / DEPILADORES"),
    (r"\b(COSMETIQUERAS?|NECESER)\b", "ACCESORIOS BELLEZA", "COSMETIQUERAS"),
    (r"\bCUBRE ?PEZON", "ACCESORIOS BELLEZA", "CUBRE PEZONES"),
    (r"\b(SECADOR|PLANCHA|RIZADORA|PEINE PLANCHA)\b", "ACCESORIOS BELLEZA",
     "ELECTRODOMESTICOS / SECADORES / PINZAS / PLANCHAS"),
    (r"\bESPEJOS?\b", "ACCESORIOS BELLEZA", "ESPEJOS"),
    (r"\bGAFAS?\b", "ACCESORIOS BELLEZA", "GAFAS"),
    (r"\bGORROS?\b", "ACCESORIOS BELLEZA", "GORRO"),
    (r"\b(ENCRESPADOR|PERFILADOR)", "ACCESORIOS BELLEZA", "PERFILADORES / ENCRESPADORES"),
    (r"\bPERFUMES?\b", "ACCESORIOS BELLEZA", "PERFUMES"),
    (r"\bPESTA[NÑ]AS?\b", "ACCESORIOS BELLEZA", "PESTAÑAS"),
    (r"\b(POMOS?|BLENDERS?|BORLAS?)\b", "ACCESORIOS BELLEZA", "POMOS / BLENDERS"),
    (r"\bU[NÑ]AS\b|\bU[NÑ]A ALMENDRADA|\bPEGANTE PARA U", "ACCESORIOS BELLEZA", "UÑAS"),
    # --- accesorios pelo ---
    (r"\b(BAMBAS?|BANDAS?|COLEROS?|CAUCHOS?|MOÑOS?|MONOS?|RESORTES|PANOLETAS?|PAÑOLETAS?)\b", "ACCESORIOS PELO", "BAMBAS / BANDAS / COLEROS"),
    (r"\bHEBILLAS?\b|\bTIC TAC\b", "ACCESORIOS PELO", "HEBILLAS"),
    (r"\b(CAIMAN|CAIMANES|BANANA)\b", "ACCESORIOS PELO", "CAIMAN"),
    (r"\b(CEPILLOS?|PEINILLA|PEINETA|PEINE)\b", "ACCESORIOS PELO", "CEPILLOS"),
    (r"\b(DIADEMAS?|BALACAS?)\b", "ACCESORIOS PELO", "DIADEMAS / BALACAS"),
    (r"\bGANCHOS?\b", "ACCESORIOS PELO", "GANCHOS"),
    (r"\bPONY CUFF\b", "ACCESORIOS PELO", "PONY CUFF"),
    (r"\bPINZAS?\b", "ACCESORIOS PELO", "PINZAS"),
    # --- bolsos ---
    (r"\bBILLETERAS?\b", "BOLSOS", "BILLETERAS"),
    (r"\bMANO ?S? ?LIBRES?\b|\bMANOLIBRES\b", "BOLSOS", "MANOS LIBRES"),
    (r"\bCARTERAS?\b", "BOLSOS", "CARTERAS"),
    (r"\bMONEDEROS?\b", "BOLSOS", "MONEDEROS"),
    (r"\b(MORRALES?|MORRAL)\b", "BOLSOS", "MORRALES"),
    (r"\bRI[NÑ]ONERAS?\b", "BOLSOS", "RIÑONERAS"),
    # --- cabello ---
    (r"\bSHAMPOO\b", "CIUDADO CABELLO", "SHAMPOO"),
    # --- hogar ---
    (r"\bCINTURON", "HOGAR", "CINTURONES"),
    (r"\b(LONCHERAS?|CONTENEDOR)", "HOGAR", "CONTENEDORES / LONCHERAS"),
    (r"\b(BON BON|DULCES?|GOMAS|CHOCOLATE|CARAMELO|MENTA|CHICLE|TRIDENT|BOCADILLO|TURRON|MANI)\b", "HOGAR", "DULCES"),
    (r"\bGORRAS?\b", "HOGAR", "GORRAS"),
    (r"\bLAMPARA", "HOGAR", "LAMPARAS"),
    (r"\bLLAVEROS?\b", "HOGAR", "LLAVEROS"),
    (r"\bMASCOTA", "HOGAR", "MASCOTAS"),
    (r"\bMEDIAS?|\bANTIDESLI", "HOGAR", "MEDIAS"),
    (r"\b(PANTUFLAS?|CHANCLAS?)\b", "HOGAR", "PANTUFLAS / CHANCLAS"),
    (r"\bRELOJ", "HOGAR", "RELOJES"),
    (r"\bSOMBREROS?\b", "HOGAR", "SOMBREROS"),
    (r"\bSOMBRILLAS?\b", "HOGAR", "SOMBRILLAS"),
    (r"\b(AUDIFONOS?|CARGADOR|CABLE USB)\b", "HOGAR", "TECNOLOGIA / CABLES / CARGADORES / AUDIFONOS"),
    (r"\b(TERMOS?|TAZAS?|VASO)\b", "HOGAR", "TERMOS / TAZAS"),
    (r"\bVENTILADOR", "HOGAR", "VENTILADORES"),
    # --- juguetes ---
    (r"\bSLIME", "JUGUETES", "SLIMES"),
    (r"\bMU[NÑ]EC[OA]S?\b", "JUGUETES", "MUÑECOS"),
    (r"\b(PELUCHES?|OSO|STITCH|ANGELA|CONEJO|SNOOPY|CERDIT|PATRULLA CANINA|CAPIBARA|WINNIE)\b",
     "JUGUETES", "PELUCHES"),
    # --- papeleria ---
    (r"\bBOLSA DE REGALO\b|\bPAPEL COREANO\b", "PAPELERIA", "BOLSA DE REGALO"),
    (r"\b(LAPICEROS?|MARCADORES?|BORRADOR|TAJALAPIZ|PEGAMENTO)\b", "PAPELERIA", "LAPICEROS / MARCADORES"),
    (r"\b(LIBRETAS?|CUADERNOS?|AGENDAS?|CARPETAS?|PEGATINAS?|STICKERS?)\b", "PAPELERIA", "LIBRETAS / CARPETA / PEGATINAS"),
    (r"\bPORTA ?DOCUMENTOS\b", "PAPELERIA", "PORTA DOCUMENTOS"),
    # --- skin care ---
    (r"\bK?IT (FACIAL|NUTRITIVO)\b", "SKIN CARE", "KITS"),
    (r"\b(CREMAS?|MANTEQUILLA|HIDRATANTE|COLAGENO)\b", "SKIN CARE", "CREMAS HIDRATANTES"),
    (r"\b(JABON|JABONES|AGUA MICELAR|LIMPIADOR)\b", "SKIN CARE", "JABONES / AGUA MICELAR"),
    (r"\b(MASCARILLAS?|MASCARA FACIAL|VELOS? FACIAL\w*|PARCHES?|PATCH)\b", "SKIN CARE", "MASCARILLAS"),
    (r"\b(PA[NÑ]ITOS|PA[NÑ]OS? FACIAL|PAPEL(ITOS)? (DE ARROZ|ABSORV)|PAPELETA)", "SKIN CARE", "PAÑOS FACIALES"),
    (r"\bTONICOS?\b", "SKIN CARE", "TONICOS"),
]
_REGLAS = [(re.compile(p), c, s) for p, c, s in REGLAS]


# ---------------------------------------------------------------------------
# Memoria: referencia -> categoria elegida por el usuario (aprende de las correcciones)
# ---------------------------------------------------------------------------
def cargar_memoria() -> dict[str, list[str]]:
    try:
        return json.loads(ARCHIVO_MEMORIA.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def guardar_memoria(nuevas: dict[str, tuple[str, str]]) -> None:
    mem = cargar_memoria()
    for ref, (c, s) in nuevas.items():
        if ref and c != SIN_CATEGORIA[0]:
            mem[normalizar(ref)] = [c, s]
    try:
        ARCHIVO_MEMORIA.write_text(json.dumps(mem, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def _exacto(taxonomia: dict | None, c: str, sub: str) -> tuple[str, str] | None:
    """Busca (c, sub) en la taxonomia ignorando espacios y devuelve el texto exacto del archivo."""
    if taxonomia is None:
        return c, sub
    for cat_t, subs in taxonomia.items():
        if cat_t.strip() == c.strip():
            for s_t in subs:
                if s_t.strip() == sub.strip():
                    return cat_t, s_t
    return None


def categorizar(nombre: str, referencia: str = "", taxonomia: dict | None = None,
                memoria: dict | None = None, proveedor: str = "") -> tuple[str, str]:
    if memoria and referencia and normalizar(referencia) in memoria:
        c, s = memoria[normalizar(referencia)]
        return _exacto(taxonomia, c, s) or (c, s)
    n = normalizar(nombre)
    for patron, c, s in _REGLAS:
        if patron.search(n):
            r = _exacto(taxonomia, c, s)
            if r:
                return r
    if proveedor in CATEGORIA_POR_PROVEEDOR:
        r = _exacto(taxonomia, *CATEGORIA_POR_PROVEEDOR[proveedor])
        if r:
            return r
    return SIN_CATEGORIA
