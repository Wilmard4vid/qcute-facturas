"""Configuracion editable: locales, proveedores conocidos y columnas de la plantilla."""

# ---------------------------------------------------------------------------
# LOCALES  -> columna de cantidades en la plantilla
# ---------------------------------------------------------------------------
LOCALES = {
    "ARRECIFE": "CC_ADMARRECIFES",
    "LA 30": "CC_ADMLA30STAMTA",
    "PLAZA DEL SOL": "CC_ADMPSOLQUILLA",
}

# Palabras que identifican cada local dentro del documento o del nombre del archivo.
# Se comparan sin tildes y en mayusculas.
LOCAL_ALIAS = {
    "ARRECIFE": ["ARRECIFE", "ARRECIFES", "ARRE", "RODADERO", "CRA 4 11A", "CR 4 11A", "LOCAL 102"],
    "LA 30": ["LA 30", "LA30", "LA TREINTA", "CL 30 18", "CALLE 30 18"],
    "PLAZA DEL SOL": ["PLAZA DEL SOL", "PLAZA SOL", "GRAN PLAZA", "PLAZA BARRANQUILLA", "SOLEDAD",
                      "176A", "176-A", "PLAZA"],
}

# Campos de la factura donde normalmente aparece el nombre del local (pesan mas que una direccion)
CAMPOS_CLIENTE = ["CLIENTE", "RAZON SOCIAL", "SUCURSAL", "SENORES", "VENDIDO A", "OBSERVACION",
                  "OFRECIDO A", "SUC", "NOMBRE"]

# ---------------------------------------------------------------------------
# PROVEEDORES conocidos -> valor de la columna "marca"
# clave: texto a buscar en la factura (sin tildes, mayusculas) | valor: marca a escribir
# Agrega aqui los proveedores nuevos.
# ---------------------------------------------------------------------------
PROVEEDORES = {
    "BAMBELLA": "BAMBELLA",
    "CAPRICHOS MAKEUP": "CAPRICHOS",
    "SANTUS": "SANTUS",
    "ERIKA MARIA GIRALDO": "SANTUS",
    "GLASEYIS": "GLASEYIS",
    "PANDA MEDELLIN": "PANDA MEDELLIN",
    "AVENTURINA": "MAFFICK",
    "MAFFICK": "MAFFICK",
    "COSMETICOS SAMY": "SAMY",
    "SAMY": "SAMY",
    "MAKASTORE": "MAKASTORE",
    "HADARA": "HADARA",
    "SH MAQUILLAJE": "SH MAQUILLAJE",
    "BUSTAMANTE": "FREDY BUSTAMANTE",
    "MAQUILLAJE SYS": "MAQUILLAJE SYS",
    "ENGOL": "ENGOL",
    "LUNA BARRANQUILLA": "ENGOL",
    "RYOMED": "RYOMED",
    "MALU": "MALU",
    "LOVERS": "LOVERS",
    "DAY COLORS": "DAY COLORS",
    "IMPORTADORA DE BELLEZA": "IMPORTADORA DE BELLEZA",
    "KOPPED": "ANI-K",
    "ANI-K": "ANI-K",
    "PARAGUITAS": "DULCERIA LOS PARAGUITAS",
    "LOREAL": "LOREAL",
    "L'OREAL": "LOREAL",
}

# ---------------------------------------------------------------------------
# PLANTILLA DE SALIDA (orden exacto de columnas)
# ---------------------------------------------------------------------------
COLUMNAS = ["categoria", "sub_categoria", "nombre", "referencia", "marca", "unidad", "iva", "ean",
            "clase", "margen_dcto_compra", "costo", "PRECIO_PUBLICO", "DCTO_PRECIO_PUBLICO",
            *LOCALES.values()]

VALORES_FIJOS = {"unidad": "UND", "iva": 19, "clase": "I", "margen_dcto_compra": 0,
                 "PRECIO_PUBLICO": 0, "DCTO_PRECIO_PUBLICO": 0}

SIN_CATEGORIA = ("SIN CATEGORIZAR", "SIN CATEGORIZAR")

# Si ninguna regla aplica, se usa la categoria tipica del proveedor
CATEGORIA_POR_PROVEEDOR = {
    "LOVERS": ("JUGUETES", "PELUCHES"),
    "DULCERIA LOS PARAGUITAS": ("HOGAR", "DULCES"),
    "GLASEYIS": ("ACCESORIOS BELLEZA", "GAFAS"),
}
