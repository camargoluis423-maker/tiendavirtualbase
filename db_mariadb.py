"""Módulo de Conexión y Persistencia con MariaDB / MySQL para M&T · COM-1.

Características:
1. Conexión automática: Si MariaDB está encendido y accesible, se conecta y usa la BD.
2. Reconexión automática: Si la conexión cae por timeout o reinicio del servicio, se restablece sola.
3. Fallback tolerante: Si MariaDB no está instalado o está apagado, conmuta automáticamente
   al almacenamiento JSON local sin interrumpir la tienda.
"""
import json
import os
import sys
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


class MariaDBManager:
    def __init__(self):
        self.conexion = None
        self._disponible = False

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
            self._disponible = True
            registrar_evento("INFO", f"[MariaDB] Conexión establecida con {DB_HOST}:{DB_PORT}/{DB_NAME}")
            return True
        except Exception as e:
            self._disponible = False
            self.conexion = None
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

    def inicializar_tablas_desde_json(self, ruta_json: str):
        """Migra automáticamente el catálogo JSON a MariaDB si la BD está vacía."""
        if not self.asegurar_conexion():
            return False

        try:
            with self.conexion.cursor() as cur:
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
                            INSERT IGNORE INTO usuarios (usuario, alias, nombre, rol, perfil, password_hash)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (u["usuario"], u.get("alias", u["usuario"]), u["nombre"], u["rol"], u.get("perfil", "General"), u["password_hash"]))

                    # Migrar productos
                    for p in datos.get("productos", []):
                        cur.execute("""
                            INSERT INTO productos (id, nombre, categoria, precio, stock, foto, especs)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE stock=VALUES(stock), precio=VALUES(precio), foto=VALUES(foto)
                        """, (p["id"], p["nombre"], p["categoria"], p["precio"], p["stock"], p.get("foto", ""), p.get("especs", "")))

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
            with self.conexion.cursor() as cur:
                # Productos
                cur.execute("SELECT id, nombre, categoria, CAST(precio AS FLOAT) as precio, stock, foto, especs FROM productos ORDER BY id ASC")
                prods = cur.fetchall()

                # Usuarios
                cur.execute("SELECT usuario, alias, nombre, rol, perfil, password_hash FROM usuarios")
                users = cur.fetchall()

                # Pedidos
                cur.execute("SELECT id, DATE_FORMAT(fecha, '%Y-%m-%d %H:%i') as fecha, cliente, usuario, perfil, pago, CAST(subtotal AS FLOAT) as subtotal, CAST(descuento AS FLOAT) as descuento, CAST(iva AS FLOAT) as iva, CAST(total AS FLOAT) as total, estado, stock_reintegrado, datos_pago_json FROM pedidos ORDER BY id DESC")
                pedidos = cur.fetchall()

                # Cargar items de cada pedido
                for ped in pedidos:
                    cur.execute("SELECT producto_id, nombre, categoria, cantidad, CAST(precio AS FLOAT) as precio, CAST(importe AS FLOAT) as importe FROM pedido_items WHERE pedido_id = %s", (ped["id"],))
                    ped["items"] = cur.fetchall()
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
