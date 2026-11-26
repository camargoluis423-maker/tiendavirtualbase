import copy
import json
import os
import shutil
from datetime import datetime
from config import DATOS_INICIALES, DATA_DIR, DB_FILE, FOTOS_DIR
from logger import registrar_evento


def obtener_ruta_foto(foto_ref: str) -> str:
    """Resuelve la ruta completa de una foto, aceptando nombres relativos o rutas absolutas."""
    if not foto_ref:
        return ""
    # Si la ruta absoluta existe directamente
    if os.path.isabs(foto_ref) and os.path.exists(foto_ref):
        return foto_ref
    # Si es solo el nombre de archivo dentro de FOTOS_DIR
    nombre = os.path.basename(foto_ref)
    ruta_en_fotos = os.path.join(FOTOS_DIR, nombre)
    if os.path.exists(ruta_en_fotos):
        return ruta_en_fotos
    return ""


def inicializar_almacenamiento() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(FOTOS_DIR, exist_ok=True)

    # 1. Comprobación de MariaDB (conexión automática si está activa)
    try:
        from db_mariadb import db_manager
        if db_manager.activa:
            db_manager.inicializar_tablas_desde_json(DB_FILE)
            datos_sql = db_manager.obtener_todo()
            if datos_sql and datos_sql.get("productos"):
                return datos_sql
    except Exception as e:
        registrar_evento("DEBUG", f"MariaDB no disponible, usando JSON: {e}")

    # 2. Almacenamiento local JSON (Fallback automático y confiable)
    if not os.path.exists(DB_FILE):
        datos = copy.deepcopy(DATOS_INICIALES)
        guardar_almacenamiento(datos)
        registrar_evento("INFO", "Base JSON inicializada con catálogo base M&T · COM-1.")
        return datos

    try:
        with open(DB_FILE, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except Exception as e:
        registrar_evento("ERROR", f"Fallo al leer {DB_FILE}: {e}")
        # Si existe backup, intentar recuperar
        bak_file = DB_FILE + ".bak"
        datos = None
        if os.path.exists(bak_file):
            registrar_evento("ALERTA", "Intentando recuperar datos desde respaldo .bak")
            try:
                with open(bak_file, "r", encoding="utf-8") as archivo:
                    datos = json.load(archivo)
            except Exception as e2:
                registrar_evento("ERROR", f"El respaldo .bak tampoco es legible: {e2}")
        if datos is None:
            # Conserva el archivo dañado para poder revisarlo y arranca limpio
            try:
                os.replace(DB_FILE, DB_FILE + ".corrupto")
            except OSError:
                pass
            datos = copy.deepcopy(DATOS_INICIALES)

    # Garantiza la estructura mínima aunque el JSON venga incompleto
    datos.setdefault("productos", [])
    datos.setdefault("pedidos", [])
    datos.setdefault(
        "next_prod_id", max((p["id"] for p in datos["productos"]), default=0) + 1
    )
    datos.setdefault(
        "next_pedido_id", max((p["id"] for p in datos["pedidos"]), default=0) + 1
    )

    # Normalizar rutas de fotos a nombres de archivo relativos (mayor portabilidad)
    modificado = False
    for prod in datos.get("productos", []):
        foto = prod.get("foto", "")
        if foto and (os.path.isabs(foto) or "/" in foto or "\\" in foto):
            prod["foto"] = os.path.basename(foto)
            modificado = True

    if modificado:
        guardar_almacenamiento(datos)

    return datos


def guardar_almacenamiento(datos: dict) -> None:
    """Guarda los datos de manera atómica con archivo temporal y respaldo .bak."""
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_file = DB_FILE + ".tmp"
    bak_file = DB_FILE + ".bak"

    # Escribir primero en temporal
    with open(temp_file, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=2, ensure_ascii=False)

    # Si ya existía DB_FILE, hacer una copia de seguridad rápida
    if os.path.exists(DB_FILE):
        try:
            shutil.copy2(DB_FILE, bak_file)
        except Exception:
            pass

    # Reemplazo atómico
    os.replace(temp_file, DB_FILE)

    # Si MariaDB está conectado, sincronizar los datos en la base relacional
    try:
        from db_mariadb import db_manager
        if db_manager.activa:
            with db_manager.conexion.cursor() as cur:
                # Sincronizar existencias de productos
                for p in datos.get("productos", []):
                    cur.execute("""
                        INSERT INTO productos (id, nombre, categoria, precio, stock, foto, especs)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE stock=VALUES(stock), precio=VALUES(precio), foto=VALUES(foto), especs=VALUES(especs)
                    """, (p["id"], p["nombre"], p["categoria"], p["precio"], p["stock"], p.get("foto", ""), p.get("especs", "")))
                
                # Sincronizar usuarios
                for u in datos.get("usuarios", []):
                    cur.execute("""
                        INSERT IGNORE INTO usuarios (usuario, alias, nombre, rol, perfil, password_hash)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (u["usuario"], u.get("alias", u["usuario"]), u["nombre"], u["rol"], u.get("perfil", "General"), u["password_hash"]))

                # Sincronizar pedidos
                for ped in datos.get("pedidos", []):
                    dp_json = json.dumps(ped.get("datos_pago", {}))
                    fecha_str = ped.get("fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
                    cur.execute("""
                        INSERT INTO pedidos (id, fecha, cliente, usuario, perfil, pago, subtotal, descuento, iva, total, estado, stock_reintegrado, datos_pago_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE estado=VALUES(estado), stock_reintegrado=VALUES(stock_reintegrado)
                    """, (ped["id"], fecha_str, ped.get("cliente", ""), ped.get("usuario"), ped.get("perfil", "General"), ped.get("pago", "Tarjeta"), ped.get("subtotal", 0), ped.get("descuento", 0), ped.get("iva", 0), ped.get("total", 0), ped.get("estado", "Pendiente"), ped.get("stock_reintegrado", False), dp_json))

                    for it in ped.get("items", []):
                        cur.execute("""
                            INSERT IGNORE INTO pedido_items (pedido_id, producto_id, nombre, categoria, cantidad, precio, importe)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (ped["id"], it["producto_id"], it["nombre"], it["categoria"], it["cantidad"], it["precio"], it["importe"]))
    except Exception as e:
        registrar_evento("DEBUG", f"[MariaDB Sync] Error en sincronización: {e}")



def importar_foto_producto(ruta_origen: str) -> str:
    """Copia la imagen a data/fotos con nombre único y retorna solo el nombre del archivo."""
    if not ruta_origen or not os.path.exists(ruta_origen):
        return ""
    os.makedirs(FOTOS_DIR, exist_ok=True)
    nombre_limpio = os.path.basename(ruta_origen).replace(" ", "_")
    # microsegundos para no pisar fotos importadas en el mismo segundo
    nombre_archivo = f"prod_{datetime.now():%Y%m%d%H%M%S%f}_{nombre_limpio}"
    destino = os.path.join(FOTOS_DIR, nombre_archivo)
    shutil.copy2(ruta_origen, destino)
    return nombre_archivo
