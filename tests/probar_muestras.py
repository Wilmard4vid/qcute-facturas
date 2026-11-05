"""Corre el extractor sobre todas las facturas de muestra y reporta si cuadran."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.extractor import extraer

carpeta = Path(sys.argv[1])
solo_pdf = "--pdf" in sys.argv
ok = 0; total = 0
for f in sorted(carpeta.iterdir()):
    if f.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}: continue
    if solo_pdf and f.suffix.lower() != ".pdf": continue
    t0 = time.time()
    d = extraer(f.name, f.read_bytes())
    total += 1
    cuadra = d.total_que_cuadra
    ok += bool(cuadra)
    print(f"{'OK ' if cuadra else '-- '} {f.name[9:55]:46s} {d.metodo:6s} local={str(d.local):13s} prov={d.proveedor[:16]:16s} "
          f"items={len(d.items):3d} suma={d.suma:>10,} totales={d.totales_impresos[:4]} noleidas={len(d.lineas_no_leidas)} {time.time()-t0:.1f}s")
print(f"\n{ok}/{total} cuadran")
