"""Módulo de Conexión y Persistencia con MariaDB / MySQL para M&T · COM-1.

MariaDB es la base principal obligatoria. Si no está disponible, las operaciones
fallan en lugar de cambiar silenciosamente a un almacén local.
"""
import json
import os
import sys
import re
import threading
from datetime import datetime
from logger import registrar_evento

# Configuración por variables de entorno o valores por defecto
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "tienda_mt")

_driver = None
try:
    import pymysql
    _driver = "pymysql"
except ImportError:
    try:
        import mysql.connector as pymysql
        _driver = "mysql.connector"
    except ImportError:
        _driver = None


def _leer_payload(fila: dict) -> dict:
    """Restaura campos completos guardados junto a las columnas indexables."""
    payload = fila.pop("payload_json", None)
    try:
        datos = json.loads(payload) if payload else {}
    except (TypeError, ValueError):
        datos = {}
    if not isinstance(datos, dict):
        datos = {}
    datos.update(fila)
    return datos


class MariaDBManager:
    def __init__(self):
        self._local = threading.local()
        self._disponible = False
        self._schema_listo = False
        self._schema_lock = threading.Lock()
        self._migracion_lock = threading.Lock()

    @property
    def conexion(self):
        return getattr(self._local, "conexion", None)

    @conexion.setter
    def conexion(self, valor):
        self._local.conexion = valor

    def conectar(self) -> bool:
        """Intenta conectarse automáticamente a MariaDB."""
        if not _driver:
            return False

        try:
            # Intento de conexión con timeout corto para no demorar el inicio
            if _driver == "pymysql":
                self.conexion = pymysql.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                    charset="utf8mb4",
                    autocommit=True,
                    connect_timeout=3,
                    cursorclass=pymysql.cursors.DictCursor
                )
            elif _driver == "mysql.connector":
                self.conexion = pymysql.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                    charset="utf8mb4",
                    autocommit=True,
                    connection_timeout=3,
                )
            self._disponible = True
            registrar_evento("INFO", f"[MariaDB] Conexión establecida con {DB_HOST}:{DB_PORT}/{DB_NAME}")
            return True
        except Exception as e:
            self._disponible = False
            self.conexion = None
            registrar_evento("ERROR", f"[MariaDB] No se pudo conectar a {DB_HOST}:{DB_PORT}/{DB_NAME}: {e}")
            return False

    def asegurar_conexion(self) -> bool:
        """Reconexión automática si la conexión se perdió."""
        if not _driver:
            return False

        try:
            if self.conexion:
                if hasattr(self.conexion, "ping"):
                    self.conexion.ping(reconnect=True)
                    return True
        except Exception:
            pass

        return self.conectar()

    @property
    def activa(self) -> bool:
        return self.asegurar_conexion()

    def _cursor(self):
        if _driver == "mysql.connector":
            return self.conexion.cursor(dictionary=True)
        return self.conexion.cursor()

    def asegurar_esquema(self) -> bool:
        """Crea o actualiza tablas desde database_schema.sql una vez por proceso."""
        if self._schema_listo:
            return True
        with self._schema_lock:
            if self._schema_listo:
                return True
            if not self.asegurar_conexion():
                return False
            ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database_schema.sql")
            try:
                with open(ruta, "r", encoding="utf-8") as archivo:
                    contenido = archivo.read()
                # Quita comentarios antes de dividir para que las directivas CREATE DATABASE/USE
                # se reconozcan aunque el archivo las documente con encabezados SQL.
                contenido = re.sub(r"(?m)^[ \t]*--.*(?:\r?\n|$)", "", contenido)
                with self._cursor() as cur:
                    for raw in contenido.split(";"):
                        sentencia = raw.strip()
                        if not sentencia:
                            continue
                        if sentencia.upper().startswith(("CREATE DATABASE", "USE ")):
                            continue
                        cur.execute(sentencia)
                self._schema_listo = True
                registrar_evento("INFO", "[MariaDB] Esquema verificado/actualizado automáticamente.")
                return True
            except Exception as e:
                registrar_evento("ERROR", f"[MariaDB] No se pudo crear/actualizar el esquema: {e}")
                return False

    def inicializar_tablas_desde_json(self, ruta_json: str):
        """Migra automáticamente el catálogo JSON a MariaDB si la BD está vacía."""
        with self._migracion_lock:
            return self._migrar_json_si_vacia(ruta_json)

    def _migrar_json_si_vacia(self, ruta_json: str):
        if not self.asegurar_conexion():
            return False

        try:
            with self._cursor() as cur:
                # Comprobar si hay productos
                cur.execute("SELECT COUNT(*) as total FROM productos")
                row = cur.fetchone()
                total = row["total"] if isinstance(row, dict) else row[0]
                if total > 0:
                    return True # Ya tiene datos

                if os.path.exists(ruta_json):
                    with open(ruta_json, "r", encoding="utf-8") as f:
                        datos = json.load(f)

                    # Migrar usuarios
                    for u in datos.get("usuarios", []):
                        cur.execute("""
                            INSERT IGNORE INTO usuarios (usuario, alias, nombre, rol, perfil, password_hash, payload_json)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (u["usuario"], u.get("alias", u["usuario"]), u["nombre"], u["rol"], u.get("perfil", "General"), u["password_hash"], json.dumps(u, ensure_ascii=False)))

                    # Migrar productos
                    for p in datos.get("productos", []):
                        cur.execute("""
                            INSERT INTO productos (id, nombre, categoria, precio, stock, foto, especs, payload_json)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE stock=VALUES(stock), precio=VALUES(precio), foto=VALUES(foto), payload_json=VALUES(payload_json)
                        """, (p["id"], p["nombre"], p["categoria"], p["precio"], p["stock"], p.get("foto", ""), p.get("especs", ""), json.dumps(p, ensure_ascii=False)))

                    for ped in datos.get("pedidos", []):
                        cur.execute("""
                            INSERT INTO pedidos (id, fecha, cliente, usuario, perfil, pago, subtotal, descuento, iva, total, estado, stock_reintegrado, datos_pago_json, payload_json)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json)
                        """, (ped["id"], ped.get("fecha", datetime.now().strftime("%Y-%m-%d %H:%M")), ped.get("cliente", ""), ped.get("usuario"), ped.get("perfil", "General"), ped.get("pago", "Tarjeta"), ped.get("subtotal", 0), ped.get("descuento", 0), ped.get("iva", 0), ped.get("total", 0), ped.get("estado", "Pendiente"), ped.get("stock_reintegrado", False), json.dumps(ped.get("datos_pago", {}), ensure_ascii=False), json.dumps(ped, ensure_ascii=False)))
                        for item in ped.get("items", []):
                            cur.execute("""
                                INSERT INTO pedido_items (pedido_id, producto_id, nombre, categoria, cantidad, precio, importe, payload_json)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, (ped["id"], item["producto_id"], item["nombre"], item.get("categoria", "Equipo"), item["cantidad"], item["precio"], item["importe"], json.dumps(item, ensure_ascii=False)))

                    registrar_evento("INFO", "[MariaDB] Datos iniciales sincronizados automáticamente desde JSON.")
                    return True
        except Exception as e:
            registrar_evento("ERROR", f"[MariaDB] Error al inicializar tablas: {e}")
            return False

    def obtener_todo(self) -> dict:
        """Lee el estado completo desde MariaDB compatible con la estructura de la tienda."""
        if not self.asegurar_conexion():
            return None

        try:
            with self._cursor() as cur:
                # Productos
                cur.execute("SELECT id, nombre, categoria, CAST(precio AS FLOAT) as precio, stock, foto, especs, payload_json FROM productos ORDER BY id ASC")
                prods = [_leer_payload(p) for p in cur.fetchall()]

                # Usuarios
                cur.execute("SELECT usuario, alias, nombre, rol, perfil, password_hash, payload_json FROM usuarios")
                users = [_leer_payload(u) for u in cur.fetchall()]

                # Pedidos
                cur.execute("SELECT id, DATE_FORMAT(fecha, '%Y-%m-%d %H:%i') as fecha, cliente, usuario, perfil, pago, CAST(subtotal AS FLOAT) as subtotal, CAST(descuento AS FLOAT) as descuento, CAST(iva AS FLOAT) as iva, CAST(total AS FLOAT) as total, estado, stock_reintegrado, datos_pago_json, payload_json FROM pedidos ORDER BY id DESC")
                pedidos = [_leer_payload(p) for p in cur.fetchall()]

                # Cargar items de cada pedido
                for ped in pedidos:
                    cur.execute("SELECT producto_id, nombre, categoria, cantidad, CAST(precio AS FLOAT) as precio, CAST(importe AS FLOAT) as importe, payload_json FROM pedido_items WHERE pedido_id = %s", (ped["id"],))
                    ped["items"] = [_leer_payload(item) for item in cur.fetchall()]
                    if ped.get("datos_pago_json"):
                        try:
                            ped["datos_pago"] = json.loads(ped["datos_pago_json"])
                        except Exception:
                            ped["datos_pago"] = {}
                    else:
                        ped["datos_pago"] = {}

                next_prod = max((p["id"] for p in prods), default=0) + 1
                next_ped = max((p["id"] for p in pedidos), default=0) + 1

                return {
                    "next_prod_id": next_prod,
                    "next_pedido_id": next_ped,
                    "productos": prods,
                    "usuarios": users,
                    "pedidos": pedidos
                }
        except Exception as e:
            registrar_evento("ERROR", f"[MariaDB] Error al leer base de datos: {e}")
            return None


# Instancia única del gestor
db_manager = MariaDBManager()
