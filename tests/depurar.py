import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.extractor import extraer, leer_linea
f = Path(sys.argv[1]); n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
d = extraer(f.name, f.read_bytes())
print("TEXTO:"); print("\n".join(d.texto.splitlines()[:n]))
print("\nNO LEIDAS:"); [print("  ", l) for l in d.lineas_no_leidas[:12]]
print("\nLEIDOS (primeros 5):"); [print("  ", i) for i in d.items[:5]]
