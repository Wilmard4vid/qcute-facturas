# QCUTE · Facturas a plantilla

App web con inicio de sesión para convertir facturas, remisiones y cuentas de cobro de **cualquier
proveedor** (PDF o foto) en el Excel de la plantilla QCUTE: 16 columnas, una fila-título por factura,
cantidades en `CC_ADMARRECIFES`, `CC_ADMLA30STAMTA` y `CC_ADMPSOLQUILLA`.

## Cómo funciona

1. **Iniciar sesión** con usuario y contraseña.
2. **Subir** uno o varios archivos (PDF, JPG, PNG). Se pueden mezclar proveedores y locales.
3. La app lee cada documento y muestra una **tabla editable** por factura con: local detectado,
   proveedor, categoría/subcategoría, referencia, nombre, cantidad y costo.
4. **Verificación automática**: compara `costo × cantidad` con el total impreso en la factura
   (✅ Cuadra / ⚠️ Diferencia). Avisa productos sin referencia, sin categoría o sin local.
5. **Descargar Excel**. Hoja `Consolidado` (formato de la plantilla) + hoja `Verificacion` aparte.
   Al descargar, la app recuerda las categorías que corregiste para la próxima vez.

### Cómo lee las facturas

No usa un formato por proveedor. En cada renglón busca tres números que cumplan
**cantidad × precio = total** (o × 1,19 si el total trae IVA); eso identifica el producto sin
importar el orden de las columnas. Probado con 45 PDF reales de 20 proveedores
(Bambella, Samy, L'Oréal, Lovers, Engol, Panda, Aventurina/Maffick, Day Colors, Santus, etc.):
**44 de 45 cuadran al peso**; el que no cuadra es un PDF al que le falta una línea desde el origen,
y la app lo marca en rojo.

| Tipo de archivo | Cómo se lee | Costo |
|---|---|---|
| PDF con texto (facturas electrónicas, remisiones de sistema) | Reglas | Gratis |
| Captura de pantalla / imagen nítida | OCR (Tesseract) | Gratis |
| Foto de papel arrugado o inclinado, remisión escrita a mano | IA (opcional) | Pago por uso en la API de Anthropic |

Sin la IA, las fotos difíciles y la letra a mano no se leen solas: la app muestra lo que no reconoció
y se completan a mano en la tabla.

## Publicarla en internet (Streamlit Community Cloud, gratis)

1. Crea un repositorio **privado** en GitHub y sube esta carpeta
   (el `.gitignore` ya evita subir contraseñas).
2. Entra a <https://share.streamlit.io>, conecta tu GitHub y elige **Create app** → tu repositorio →
   archivo principal `app.py`.
3. En **Advanced settings → Secrets** pega los usuarios (ver abajo) y, si quieres IA, la clave.
4. **Deploy**. Comparte la URL; solo entra quien tenga usuario.

`packages.txt` instala Tesseract (OCR) automáticamente en Streamlit Cloud.
Alternativa: el `Dockerfile` sirve para Render, Railway o un servidor propio.

## Crear usuarios

```bash
pip install bcrypt
python scripts/crear_usuario.py
```

Pega el bloque que imprime en los secretos (Streamlit Cloud → Settings → Secrets, o
`.streamlit/secrets.toml` en local). Ver `.streamlit/secrets.toml.example`.
Las contraseñas se guardan cifradas (bcrypt); tras 5 intentos fallidos se bloquea 5 minutos.

## Activar la IA (opcional)

En los secretos agrega:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
ANTHROPIC_MODEL = "claude-sonnet-5-5"   # opcional
```

La clave se crea en <https://console.anthropic.com>. Con IA activa, el modo **Automático** solo la usa
cuando las reglas no cuadran o no leen nada, para no gastar en las facturas que ya se leen gratis.

## Ejecutar en tu computador

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # y pega tus usuarios
streamlit run app.py
```

Para fotos en local instala Tesseract: Windows <https://github.com/UB-Mannheim/tesseract/wiki>
(marca Spanish), Mac `brew install tesseract tesseract-lang`, Linux `apt install tesseract-ocr tesseract-ocr-spa`.

## Personalizar

Todo en `core/config.py`:

- **`LOCAL_ALIAS`**: palabras que identifican cada local (si un proveedor escribe el local distinto).
- **`PROVEEDORES`**: texto que aparece en la factura → valor de la columna `marca`.
- **`CATEGORIA_POR_PROVEEDOR`**: categoría por defecto de un proveedor (ej. Lovers → Peluches).

Reglas de categorización por palabra clave: `core/categorias.py` (`REGLAS`).
Taxonomía: `data/categorias.xlsx` (o súbela desde la barra lateral). Los nombres se escriben en el
Excel **exactamente** como están en ese archivo, incluidos los espacios finales.

## Probar con tus facturas

```bash
python tests/probar_muestras.py carpeta_con_facturas --pdf
```

Muestra, por archivo, local, proveedor, productos leídos y si cuadra con el total.

## Limitaciones conocidas

- Las categorías aprendidas se guardan en `data/memoria_categorias.json`. En Streamlit Cloud ese
  archivo se reinicia cuando la app se reinstala; para conservarlo de forma permanente habría que
  pasarlo a una base de datos.
- Si una misma referencia trae varios colores (ej. `CA1862` tonos 00–04), quedan como filas con la
  misma referencia; la app lo avisa por si tu sistema exige referencias únicas.
- El número del documento del título se detecta por patrones; si sale raro, el título es editable.
