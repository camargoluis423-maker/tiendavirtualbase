import json
import os
import shutil
from datetime import datetime
from config import DATA_DIR, DB_FILE, FOTOS_DIR
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
    from db_mariadb import db_manager

    if not db_manager.asegurar_conexion():
        raise RuntimeError(
            "MariaDB es obligatoria y no está disponible. Revisa DB_HOST, DB_PORT, "
            "DB_USER, DB_PASSWORD y DB_NAME. No se usará el JSON como alternativa."
        )
    if not db_manager.asegurar_esquema():
        raise RuntimeError(
            "No se pudo preparar automáticamente el esquema de MariaDB. "
            "Revisa permisos CREATE/ALTER del usuario y logs/actividad.log."
        )
    if not db_manager.inicializar_tablas_desde_json(DB_FILE):
        raise RuntimeError(
            "No se pudo inicializar MariaDB. Verifica los permisos CREATE/ALTER y "
            "revisa logs/actividad.log. No se usará el JSON como alternativa."
        )
    datos_sql = db_manager.obtener_todo()
    if datos_sql is None:
        raise RuntimeError("MariaDB no pudo entregar los datos; revisa logs/actividad.log.")
    return datos_sql


def guardar_almacenamiento(datos: dict) -> None:
    """Persiste primero en MariaDB; el JSON queda solo como respaldo de lectura humana."""
    from db_mariadb import db_manager

    if not db_manager.asegurar_conexion():
        raise RuntimeError("MariaDB es obligatoria y no está disponible; no se guardaron los cambios.")

    conexion = db_manager.conexion
    try:
        conexion.begin()
        with db_manager._cursor() as cur:
            ids_productos = [p["id"] for p in datos.get("productos", [])]
            if ids_productos:
                marcas = ",".join(["%s"] * len(ids_productos))
                cur.execute(f"DELETE FROM productos WHERE id NOT IN ({marcas})", ids_productos)
            else:
                cur.execute("DELETE FROM productos")

            for p in datos.get("productos", []):
                cur.execute("""
                    INSERT INTO productos (id, nombre, categoria, precio, stock, foto, especs, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE nombre=VALUES(nombre), categoria=VALUES(categoria),
                        precio=VALUES(precio), stock=VALUES(stock), foto=VALUES(foto), especs=VALUES(especs), payload_json=VALUES(payload_json)
                """, (p["id"], p["nombre"], p["categoria"], p["precio"], p["stock"], p.get("foto", ""), p.get("especs", ""), json.dumps(p, ensure_ascii=False)))

            for u in datos.get("usuarios", []):
                cur.execute("""
                    INSERT INTO usuarios (usuario, alias, nombre, rol, perfil, password_hash, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE alias=VALUES(alias), nombre=VALUES(nombre), rol=VALUES(rol),
                        perfil=VALUES(perfil), password_hash=VALUES(password_hash), payload_json=VALUES(payload_json)
                """, (u["usuario"], u.get("alias", u["usuario"]), u["nombre"], u["rol"], u.get("perfil", "General"), u["password_hash"], json.dumps(u, ensure_ascii=False)))

            for ped in datos.get("pedidos", []):
                dp_json = json.dumps(ped.get("datos_pago", {}), ensure_ascii=False)
                ped_json = json.dumps(ped, ensure_ascii=False)
                fecha_str = ped.get("fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
                cur.execute("""
                    INSERT INTO pedidos (id, fecha, cliente, usuario, perfil, pago, subtotal, descuento, iva, total, estado, stock_reintegrado, datos_pago_json, payload_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE estado=VALUES(estado), stock_reintegrado=VALUES(stock_reintegrado),
                        datos_pago_json=VALUES(datos_pago_json), payload_json=VALUES(payload_json)
                """, (ped["id"], fecha_str, ped.get("cliente", ""), ped.get("usuario"), ped.get("perfil", "General"), ped.get("pago", "Tarjeta"), ped.get("subtotal", 0), ped.get("descuento", 0), ped.get("iva", 0), ped.get("total", 0), ped.get("estado", "Pendiente"), ped.get("stock_reintegrado", False), dp_json, ped_json))

                cur.execute("DELETE FROM pedido_items WHERE pedido_id = %s", (ped["id"],))
                for it in ped.get("items", []):
                    cur.execute("""
                        INSERT INTO pedido_items (pedido_id, producto_id, nombre, categoria, cantidad, precio, importe, payload_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (ped["id"], it["producto_id"], it["nombre"], it.get("categoria", "Equipo"), it["cantidad"], it["precio"], it["importe"], json.dumps(it, ensure_ascii=False)))
        conexion.commit()
    except Exception as e:
        try:
            conexion.rollback()
        except Exception:
            pass
        registrar_evento("ERROR", f"[MariaDB] No se pudo guardar la operación: {e}")
        raise RuntimeError("No se pudo guardar la operación en MariaDB. Intenta de nuevo.") from e

    # Copia de seguridad auxiliar: nunca se lee como fuente principal.
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_file = DB_FILE + ".tmp"
    bak_file = DB_FILE + ".bak"
    try:
        with open(temp_file, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, indent=2, ensure_ascii=False)
        if os.path.exists(DB_FILE):
            shutil.copy2(DB_FILE, bak_file)
        os.replace(temp_file, DB_FILE)
    except OSError as e:
        registrar_evento("ALERTA", f"MariaDB se guardó, pero falló el respaldo JSON: {e}")



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
