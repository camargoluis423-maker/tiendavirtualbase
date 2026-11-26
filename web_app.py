"""Versión web de la tienda M&T · COM-1 (Flask).

Comparte datos y reglas de negocio con la app de escritorio
(`storage.py`, `logica.py`, `config.py`), así que ambas ven el mismo catálogo.

Ejecutar:
    pip install -r requirements.txt
    python web_app.py
y abrir http://localhost:5000

Para verla desde otros dispositivos de tu red:  python web_app.py --lan
(asegúrate de permitir el puerto 5000 en el firewall).
"""
from datetime import datetime, timedelta, timezone
from functools import wraps
import csv
import ipaddress
import io
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

import logica
from config import (
    CATEGORIA_ESTILO,
    CATEGORIAS,
    COLORES,
    CUPONES,
    DATA_DIR,
    ENVIO_GRATIS_MIN,
    ESLOGAN,
    ESTADO_COLORES,
    ESTADOS_PEDIDO,
    FOTOS_DIR,
    METODOS_PAGO,
    NOMBRE_TIENDA,
    PAGO_NOTA,
    PERFILES_CLIENTE,
    PUNTOS_TASA,
    SECCIONES,
    STOCK_BAJO,
    TASA_IVA,
    WHATSAPP,
)
from logger import registrar_evento
from storage import guardar_almacenamiento, inicializar_almacenamiento
from utils_qr import qr_svg

app = Flask(__name__)
_cerrojo = threading.Lock()   # evita que dos compras simultáneas pisen el inventario
_usuarios_cerrojo = threading.RLock()
_auth_cerrojo = threading.Lock()
_intentos_login = {}
_INTENTOS_MAX_LOGIN = 5
_VENTANA_BLOQUEO_LOGIN = 15 * 60
_LONGITUD_MIN_PASSWORD = 12
_LONGITUD_MAX_PASSWORD = 128


def _password_fuerte(password: str) -> bool:
    return _LONGITUD_MIN_PASSWORD <= len(password) <= _LONGITUD_MAX_PASSWORD


def _clave_secreta() -> str:
    """Clave estable entre reinicios (para no perder carritos) guardada fuera del control de versiones."""
    if os.environ.get("MT_SECRET_KEY"):
        clave = os.environ["MT_SECRET_KEY"]
        if len(clave) < 32:
            raise RuntimeError("MT_SECRET_KEY debe tener al menos 32 caracteres aleatorios.")
        return clave
    ruta = os.path.join(DATA_DIR, ".secret_key")
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ruta):
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    with open(ruta, encoding="utf-8") as f:
        return f.read().strip()


app.secret_key = _clave_secreta()


def _contexto_tls():
    """Usa certificados configurados o genera uno local para HTTPS automático."""
    cert_configurado = os.environ.get("MT_SSL_CERT", "").strip()
    clave_configurada = os.environ.get("MT_SSL_KEY", "").strip()
    if cert_configurado and clave_configurada and os.path.isfile(cert_configurado) and os.path.isfile(clave_configurada):
        return cert_configurado, clave_configurada

    if cert_configurado or clave_configurada:
        registrar_evento("ALERTA", "Certificado TLS configurado no encontrado; se generará uno local para HTTPS.")

    carpeta_tls = os.path.join(DATA_DIR, "tls")
    cert_local = os.path.join(carpeta_tls, "localhost.crt")
    clave_local = os.path.join(carpeta_tls, "localhost.key")
    if os.path.isfile(cert_local) and os.path.isfile(clave_local):
        return cert_local, clave_local

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        os.makedirs(carpeta_tls, exist_ok=True)
        privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ahora = datetime.now(timezone.utc)
        nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
        certificado = (
            x509.CertificateBuilder()
            .subject_name(nombre)
            .issuer_name(nombre)
            .public_key(privada.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - timedelta(minutes=1))
            .not_valid_after(ahora + timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]),
                critical=False,
            )
            .sign(privada, hashes.SHA256())
        )
        with open(clave_local, "wb") as archivo:
            archivo.write(
                privada.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                )
            )
        with open(cert_local, "wb") as archivo:
            archivo.write(certificado.public_bytes(serialization.Encoding.PEM))
        try:
            os.chmod(clave_local, 0o600)
        except OSError:
            pass
        registrar_evento("INFO", "Certificado HTTPS local generado automáticamente.")
        return cert_local, clave_local
    except ImportError as e:
        raise RuntimeError("Falta la dependencia cryptography para generar el certificado HTTPS local.") from e


SSL_CONTEXT = _contexto_tls()
_proxy_confiable = os.environ.get("MT_TRUSTED_PROXY", "0") == "1"
if _proxy_confiable:
    # Solo activar si el servidor recibe tráfico exclusivamente desde un proxy propio.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)


@app.after_request
def cabeceras_seguridad(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _asegurar_usuarios(datos: dict) -> dict:
    """Crea el vendedor solo con clave configurada y actualiza cuentas semilla antiguas."""
    with _usuarios_cerrojo:
        usuarios = datos.get("usuarios")
        if not isinstance(usuarios, list):
            usuarios = []
            datos["usuarios"] = usuarios
        modificado = False
        if not usuarios:
            password_vendedor = os.environ.get("MT_SELLER_PASSWORD", "")
            if _password_fuerte(password_vendedor):
                usuarios.append({
                    "usuario": "vendedor@mtcom1.mx",
                    "alias": "vendedor",
                    "nombre": "Administrador M&T",
                    "rol": "vendedor",
                    "perfil": "General",
                    "password_hash": generate_password_hash(password_vendedor),
                })
                modificado = True

        # Reemplaza hashes de las claves de demostración de versiones anteriores
        # solo cuando el operador configuró una clave nueva y suficientemente larga.
        semillas = {
            ("vendedor", "vendedor@mtcom1.mx"): ("vendedor123", "MT_SELLER_PASSWORD"),
            ("comprador", "comprador@mtcom1.mx"): ("comprador123", "MT_BUYER_PASSWORD"),
        }
        for usuario in usuarios:
            semilla = semillas.get((usuario.get("rol"), str(usuario.get("usuario", "")).lower()))
            if not semilla:
                continue
            password_anterior, variable = semilla
            try:
                era_semilla = check_password_hash(usuario.get("password_hash", ""), password_anterior)
            except (ValueError, TypeError):
                era_semilla = False
            password_nueva = os.environ.get(variable, "")
            if era_semilla and _password_fuerte(password_nueva):
                usuario["password_hash"] = generate_password_hash(password_nueva)
                modificado = True
        if modificado:
            guardar_almacenamiento(datos)
    return datos


def _credencial_predeterminada(usuario: dict, password: str) -> bool:
    semillas = {
        ("vendedor", "vendedor@mtcom1.mx"): "vendedor123",
        ("comprador", "comprador@mtcom1.mx"): "comprador123",
    }
    predeterminada = semillas.get((usuario.get("rol"), str(usuario.get("usuario", "")).lower()))
    return bool(predeterminada and secrets.compare_digest(password, predeterminada))


def _clave_intento_login(identificador: str) -> tuple[str, str]:
    return (request.remote_addr or "desconocida", (identificador or "").strip().lower()[:120])


def _login_bloqueado(clave: tuple[str, str]) -> bool:
    ahora = time.monotonic()
    with _auth_cerrojo:
        intento = _intentos_login.get(clave)
        if not intento:
            return False
        if intento["bloqueado_hasta"] > ahora:
            return True
        if ahora - intento["ultimo"] >= _VENTANA_BLOQUEO_LOGIN:
            _intentos_login.pop(clave, None)
        return False


def _registrar_fallo_login(clave: tuple[str, str]) -> None:
    ahora = time.monotonic()
    with _auth_cerrojo:
        if len(_intentos_login) > 10000:
            for antigua, intento in list(_intentos_login.items()):
                if ahora - intento["ultimo"] >= _VENTANA_BLOQUEO_LOGIN:
                    _intentos_login.pop(antigua, None)
        intento = _intentos_login.get(clave)
        if not intento or ahora - intento["ultimo"] >= _VENTANA_BLOQUEO_LOGIN:
            intento = {"fallos": 0, "bloqueado_hasta": 0.0}
        intento["fallos"] += 1
        intento["ultimo"] = ahora
        if intento["fallos"] >= _INTENTOS_MAX_LOGIN:
            intento["bloqueado_hasta"] = ahora + _VENTANA_BLOQUEO_LOGIN
        _intentos_login[clave] = intento


def _limpiar_fallos_login(clave: tuple[str, str]) -> None:
    with _auth_cerrojo:
        _intentos_login.pop(clave, None)


def cargar():
    """Lee el JSON en cada petición: así refleja los cambios hechos desde la app de escritorio."""
    return _asegurar_usuarios(inicializar_almacenamiento())


def _buscar_usuario(datos: dict, identificador: str):
    ident = (identificador or "").strip().lower()
    if not ident:
        return None
    for u in datos.get("usuarios", []):
        if u.get("usuario", "").lower() == ident or u.get("alias", "").lower() == ident:
            return u
    return None


def usuario_actual():
    auth = session.get("usuario_auth")
    if not auth or not auth.get("usuario"):
        return None
    u = _buscar_usuario(cargar(), auth["usuario"])
    if not u:
        session.pop("usuario_auth", None)
        return None
    return {
        "usuario": u["usuario"],
        "nombre": u["nombre"],
        "rol": u["rol"],
        "perfil": u.get("perfil", "General"),
        "puntos_lealtad": round(float(u.get("puntos_lealtad", 0.0) or 0.0), 2),
        "favoritos": [int(x) for x in u.get("favoritos", []) if str(x).isdigit()],
        "cupones_usados": list(u.get("cupones_usados", [])),
    }


def requiere_rol(rol=None):
    def decorador(fn):
        @wraps(fn)
        def envuelto(*args, **kwargs):
            u = usuario_actual()
            if not u:
                if request.path != "/":
                    flash("Inicia sesión para acceder a esta sección.", "aviso")
                destino_rol = rol or "comprador"
                return redirect(url_for("login", rol=destino_rol, next=request.full_path.rstrip("?")))
            if rol and u["rol"] != rol:
                if request.method == "POST":
                    abort(403, "No tienes permisos para realizar esta acción.")
                if rol == "vendedor":
                    flash("Esta sección es exclusiva para cuentas de vendedor.", "error")
                    return redirect(url_for("index"))
                flash("Tu cuenta es de vendedor (solo gestión y ventas). No puedes realizar compras.", "aviso")
                return redirect(url_for("vendedor_panel"))
            return fn(*args, **kwargs)
        return envuelto
    return decorador


def _destino_seguro(destino: str, respaldo: str) -> str:
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return respaldo


def carrito_sesion() -> dict:
    return {int(k): int(v) for k, v in session.get("carrito", {}).items() if str(k).isdigit()}


def guardar_carrito(carrito: dict):
    session["carrito"] = {str(k): v for k, v in carrito.items() if v > 0}


# ---------------------------------------------------------------------------
# Especificaciones técnicas para tarjetas, ficha y tabla de componentes
# ---------------------------------------------------------------------------
_SPECS_POR_ID = {
    1: {
        "tipo": "Workstation Portátil",
        "clave_tipo": "laptop",
        "especs": "16 GB RAM · SSD NVMe 512 GB · Chasis profesional",
        "interfaz": "Wi-Fi 6 · USB-C · HDMI",
        "compatibilidad": "Ideal para ingeniería, CAD y multitarea exigente",
        "garantia": "12 meses",
        "etiquetas": ["16 GB RAM", "SSD 512 GB", "Workstation"],
    },
    2: {
        "tipo": "Licencia Digital",
        "clave_tipo": "software",
        "especs": "Suscripción anual · Suite CAD 2D/3D y Simulación",
        "interfaz": "Activación digital · Windows 10/11",
        "compatibilidad": "Equipos con 8+ GB RAM y gráficos dedicados o integrados",
        "garantia": "12 meses de soporte",
        "etiquetas": ["Licencia 1 año", "CAD & Simulación", "Entrega rápida"],
    },
    3: {
        "tipo": "Silla Ergonómica",
        "clave_tipo": "mobiliario",
        "especs": "Malla transpirable alta densidad · Soporte lumbar",
        "interfaz": "Pistón clase 4 · Base 5 puntas",
        "compatibilidad": "Jornadas largas de oficina, estudio o setup home-office",
        "garantia": "12 meses",
        "etiquetas": ["Malla HD", "Soporte lumbar", "Ergonómica"],
    },
    4: {
        "tipo": "Escritorio en L",
        "clave_tipo": "mobiliario",
        "especs": "Superficie amplia en L · Estructura metálica reforzada",
        "interfaz": "Configuración esquina / doble monitor",
        "compatibilidad": "Estaciones duales de trabajo o gaming",
        "garantia": "12 meses",
        "etiquetas": ["Estación Dual", "Formato en L", "Estructura acero"],
    },
    5: {
        "tipo": "Smartphone",
        "clave_tipo": "equipo",
        "especs": "Pantalla AMOLED · Almacenamiento amplio · Conectividad 5G/LTE",
        "interfaz": "USB-C · Dual SIM / Wi-Fi",
        "compatibilidad": "Uso diario, productividad móvil y mensajería",
        "garantia": "12 meses",
        "etiquetas": ["Equipo móvil", "Listo para usar", "Garantía local"],
    },
    6: {
        "tipo": "PC Escritorio",
        "clave_tipo": "pc",
        "especs": "AMD Ryzen 5 · 16 GB RAM · SSD 512 GB",
        "interfaz": "HDMI · USB 3.2 · Ethernet Gigabit",
        "compatibilidad": "Oficina, contabilidad, escuela y negocio",
        "garantia": "12 meses",
        "etiquetas": ["Ryzen 5", "16 GB RAM", "SSD 512 GB"],
    },
    7: {
        "tipo": "All-in-One 24\"",
        "clave_tipo": "pc",
        "especs": "Pantalla 24\" FHD · Intel Core i5 · 16 GB · SSD 512 GB",
        "interfaz": "Wi-Fi · Webcam integrada · USB 3.0",
        "compatibilidad": "Mostradores, recepción, oficina compacta y estudio",
        "garantia": "12 meses",
        "etiquetas": ["Pantalla 24\"", "Core i5", "16 GB / 512 GB"],
    },
    8: {
        "tipo": "Laptop Estudio 14\"",
        "clave_tipo": "laptop",
        "especs": "Pantalla 14\" · Intel Core i3 · 8 GB RAM · SSD 256 GB",
        "interfaz": "Wi-Fi · HDMI · USB-C",
        "compatibilidad": "Clases en línea, paquetería Office y portabilidad",
        "garantia": "12 meses",
        "etiquetas": ["14\" Ligera", "Core i3", "SSD 256 GB"],
    },
    9: {
        "tipo": "PC Gamer",
        "clave_tipo": "gaming",
        "especs": "Ryzen 5 · NVIDIA RTX 4060 8GB · 16 GB RAM · SSD 1 TB",
        "interfaz": "PCIe 4.0 · DisplayPort / HDMI · RGB",
        "compatibilidad": "Gaming 1080p/1440p Ultra, streaming y edición",
        "garantia": "12 meses",
        "etiquetas": ["RTX 4060", "Ryzen 5", "SSD 1 TB"],
    },
    10: {
        "tipo": "PC Gamer Pro",
        "clave_tipo": "gaming",
        "especs": "Core i7 · RTX 4070 Super 12GB · 32 GB RAM · SSD 1 TB",
        "interfaz": "PCIe 4.0 · Refrigeración optimizada · Wi-Fi",
        "compatibilidad": "Gaming 1440p/4K, renderizado 3D y arquitectura",
        "garantia": "12 meses",
        "etiquetas": ["RTX 4070 Super", "32 GB RAM", "Core i7"],
    },
    11: {
        "tipo": "Laptop Gamer 15.6\"",
        "clave_tipo": "gaming",
        "especs": "15.6\" 144Hz · RTX 4050 · 16 GB RAM · Teclado retroiluminado",
        "interfaz": "USB-C · HDMI 2.1 · Wi-Fi 6",
        "compatibilidad": "Juegos competitivos y diseño en movimiento",
        "garantia": "12 meses",
        "etiquetas": ["144 Hz", "RTX 4050", "16 GB RAM"],
    },
    12: {
        "tipo": "Tarjeta Gráfica (GPU)",
        "clave_tipo": "gpu",
        "especs": "8 GB GDDR6 · Arquitectura Ada Lovelace · DLSS 3",
        "interfaz": "PCIe 4.0 x16 · 3× DisplayPort · 1× HDMI 2.1",
        "compatibilidad": "Fuente recomendada 550W+ · Gabinetes ATX / mATX",
        "garantia": "24 meses",
        "etiquetas": ["8 GB GDDR6", "DLSS 3", "PCIe 4.0"],
    },
    13: {
        "tipo": "Memoria RAM",
        "clave_tipo": "ram",
        "especs": "16 GB DDR5 · 5600 MHz · Bajo perfil / Alta velocidad",
        "interfaz": "DIMM 288 pines · 1.1V · XMP / EXPO",
        "compatibilidad": "Placas madre DDR5 (Intel 12ª–14ª gen / AMD AM5)",
        "garantia": "36 meses",
        "etiquetas": ["16 GB DDR5", "5600 MHz", "XMP / EXPO"],
    },
    14: {
        "tipo": "Almacenamiento SSD",
        "clave_tipo": "ssd",
        "especs": "1 TB NVMe · Lectura secuencial alta velocidad PCIe 4.0",
        "interfaz": "M.2 2280 · PCIe Gen 4.0 x4 NVMe",
        "compatibilidad": "PCs de escritorio, laptops y consolas M.2 2280",
        "garantia": "36 meses",
        "etiquetas": ["1 TB NVMe", "PCIe 4.0", "M.2 2280"],
    },
    15: {
        "tipo": "Procesador (CPU)",
        "clave_tipo": "cpu",
        "especs": "6 núcleos / 12 hilos · Hasta 5.1 GHz Boost · 65W TDP",
        "interfaz": "Socket AM5 · Soporta DDR5 y PCIe 5.0",
        "compatibilidad": "Placas madre chipset A620, B650 y X670",
        "garantia": "36 meses",
        "etiquetas": ["6C / 12H", "Socket AM5", "5.1 GHz"],
    },
    16: {
        "tipo": "Fuente de Poder (PSU)",
        "clave_tipo": "psu",
        "especs": "650W reales · Certificación 80+ Bronze · Protecciones OVP/SCP",
        "interfaz": "Formato ATX · Conectores 24-pin, CPU y PCIe 8-pin",
        "compatibilidad": "Equipos oficina y PCs gamer hasta RTX 4060 / 4060 Ti",
        "garantia": "24 meses",
        "etiquetas": ["650 W", "80+ Bronze", "ATX"],
    },
    17: {
        "tipo": "Gabinete ATX",
        "clave_tipo": "gabinete",
        "especs": "Media torre ATX · Panel lateral y ventiladores RGB incluidos",
        "interfaz": "USB 3.0 frontal · Audio HD · Malla frontal",
        "compatibilidad": "Placas ATX, Micro-ATX y Mini-ITX",
        "garantia": "12 meses",
        "etiquetas": ["Formato ATX", "Fans RGB", "Flujo de aire"],
    },
}


def especificaciones_producto(prod: dict) -> dict:
    """Devuelve metadatos técnicos enriquecidos para tarjetas, ficha y tabla de componentes."""
    if not prod:
        return {}
    pid = prod.get("id")
    if pid in _SPECS_POR_ID:
        return _SPECS_POR_ID[pid]

    nombre = (prod.get("nombre") or "").lower()
    cat = prod.get("categoria", "Equipo")

    # Inferencia automática para productos nuevos agregados desde la app de escritorio
    reglas = [
        (("rtx", "gtx", "rx ", "radeon", "video", "gráfica", "grafica", "gpu"),
         "Tarjeta Gráfica (GPU)", "gpu", "Aceleración gráfica dedicada", "PCIe x16 · HDMI / DP", "PCs ATX/mATX con fuente adecuada"),
        (("ram", "ddr4", "ddr5", "sodimm", "memoria"),
         "Memoria RAM", "ram", "Módulo de memoria de alta velocidad", "DIMM / SO-DIMM", "Equipos compatibles con el estándar DDR"),
        (("ssd", "nvme", "hdd", "disco", "almacenamiento", "m.2"),
         "Almacenamiento", "ssd", "Unidad de almacenamiento de estado sólido", "M.2 NVMe / SATA", "PCs de escritorio y laptops"),
        (("ryzen", "core i", "procesador", "cpu", "intel ", "amd "),
         "Procesador (CPU)", "cpu", "Procesamiento multinúcleo", "Socket de escritorio", "Motherboards compatibles según socket"),
        (("fuente", "psu", "watt", "80+", "poder"),
         "Fuente de Poder (PSU)", "psu", "Suministro eléctrico regulado", "ATX estándar", "Configuraciones PC compatibles"),
        (("gabinete", "case", "torre", "chasis"),
         "Gabinete", "gabinete", "Chasis con ventilación optimizada", "ATX / Micro-ATX", "Componentes estándar de escritorio"),
        (("motherboard", "tarjeta madre", "placa", "b650", "b550", "b760", "h610"),
         "Tarjeta Madre", "mobo", "Plataforma base con expansión M.2 y PCIe", "ATX / Micro-ATX", "Procesadores y RAM según socket"),
        (("disipador", "cooler", "enfriamiento", "líquido", "ventilador"),
         "Enfriamiento", "cooler", "Control térmico silencioso", "PWM 4 pines", "Sockets Intel / AMD recientes"),
    ]
    for claves, tipo, clave_tipo, especs, interfaz, comp in reglas:
        if any(c in nombre for c in claves):
            return {
                "tipo": tipo,
                "clave_tipo": clave_tipo,
                "especs": prod.get("especs") or especs,
                "interfaz": interfaz,
                "compatibilidad": comp,
                "garantia": "12 meses",
                "etiquetas": [tipo, cat],
            }

    return {
        "tipo": cat,
        "clave_tipo": cat.lower().replace(" ", "_"),
        "especs": prod.get("especs") or f"Artículo disponible en categoría {cat}",
        "interfaz": "Estándar comercial",
        "compatibilidad": "Uso general en estación de trabajo o hogar",
        "garantia": "12 meses",
        "etiquetas": [cat, "M&T · COM-1"],
    }


@app.template_filter("dinero")
def _dinero(valor):
    return logica.dinero(float(valor or 0))


@app.context_processor
def contexto():
    u = usuario_actual()
    if u:
        datos = cargar()
        carrito = carrito_sesion() if u["rol"] == "comprador" else {}
        n = sum(carrito.get(p["id"], 0) for p in datos["productos"])
        conteos_cat = {"Todas": len(datos["productos"])}
        for c in CATEGORIAS:
            conteos_cat[c] = sum(1 for p in datos["productos"] if p["categoria"] == c)
        total_productos = len(datos["productos"])
        total_disponibles = sum(1 for p in datos["productos"] if p["stock"] > 0)
        fav_ids = set(u.get("favoritos", []))
        favoritos_regreso_stock = [
            p for p in datos["productos"] if p["id"] in fav_ids and p["stock"] > 0
        ]
    else:
        n = 0
        conteos_cat = {}
        total_productos = 0
        total_disponibles = 0
        favoritos_regreso_stock = []
    return {
        "TIENDA": NOMBRE_TIENDA,
        "ESLOGAN": ESLOGAN,
        "COLORES": COLORES,
        "estilo_cat": lambda c: CATEGORIA_ESTILO.get(c, {"color": "#64748b", "icono": "▣"}),
        "nivel_stock": logica.estado_stock,
        "precio_oferta": logica.precio_con_oferta,
        "specs_de": especificaciones_producto,
        "n_carrito": n,
        "conteos_cat": conteos_cat,
        "total_productos": total_productos,
        "total_disponibles": total_disponibles,
        "favoritos_regreso_stock": favoritos_regreso_stock,
        "ENVIO_GRATIS_MIN": ENVIO_GRATIS_MIN,
        "PUNTOS_TASA": PUNTOS_TASA,
        "CUPONES": CUPONES,
        "usuario": u,
        "csrf": session.setdefault("csrf", secrets.token_hex(16)),
        "TASA_IVA": TASA_IVA,
        "TASA_IVA_PCT": round(TASA_IVA * 100),
        "PERFILES_DESCUENTOS": [(p, round(d * 100)) for p, d in PERFILES_CLIENTE.items() if d > 0],
        "ESTADOS_PEDIDO": ESTADOS_PEDIDO,
        "ESTADO_COLORES": ESTADO_COLORES,
        "SECCIONES": SECCIONES,
        "CATEGORIAS": CATEGORIAS,
        "PAGO_NOTA": PAGO_NOTA,
        "WHATSAPP": WHATSAPP,
    }


@app.before_request
def proteger_post():
    if request.method == "POST":
        token = request.form.get("csrf") or request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(token, session.get("csrf", "x")):
            abort(400, "Sesión inválida o expirada. Recarga la página e inténtalo de nuevo.")


# ---------------------------------------------------------------------------
# Archivos y API
# ---------------------------------------------------------------------------
@app.route("/fotos/<path:nombre>")
@requiere_rol()
def foto(nombre):
    """Sirve solo las fotos de productos (nunca el JSON de datos ni los respaldos)."""
    return send_from_directory(FOTOS_DIR, nombre)


@app.route("/api/productos")
def api_productos():
    if not usuario_actual():
        return jsonify({"error": "Autenticación requerida"}), 401
    return jsonify(cargar()["productos"])


# ---------------------------------------------------------------------------
# Asistente Chatbot con Ollama (con respaldo inteligente local)
# ---------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")


def _detectar_modelo_ollama() -> tuple[bool, str]:
    """Comprueba si Ollama está activo y devuelve (activo, nombre_modelo)."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            modelos = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            if not modelos:
                return True, OLLAMA_MODEL
            if OLLAMA_MODEL in modelos:
                return True, OLLAMA_MODEL
            for m in modelos:
                if m.startswith(OLLAMA_MODEL.split(":")[0]):
                    return True, m
            return True, modelos[0]
    except Exception:
        return False, OLLAMA_MODEL


def _contexto_tienda_prompt(datos: dict, rol: str) -> str:
    """Construye el contexto del catálogo actual para el prompt del sistema de Ollama."""
    lineas = []
    for p in datos.get("productos", [])[:35]:
        sp = especificaciones_producto(p)
        estado = "Agotado" if p["stock"] <= 0 else f"{p['stock']} uds."
        lineas.append(
            f"- [ID {p['id']}] {p['nombre']} ({p['categoria']}) | ${p['precio']:,.2f} + IVA | Stock: {estado} | {sp.get('especs', '')}"
        )
    catalogo_txt = "\n".join(lineas)
    return (
        f"Eres el asistente virtual oficial de {NOMBRE_TIENDA} ({ESLOGAN}), ubicada en Tepeaca y región. "
        "Responde siempre en español, de forma amable, breve y útil (máximo 4-5 líneas salvo que pidan comparar). "
        f"El usuario actual tiene rol: {rol}. "
        "Reglas de la tienda: los precios mostrados son sin IVA (se suma 16% al pagar). "
        "Descuentos por perfil: Estudiante 10%, Empresa 8%, Ingeniero 5%. "
        "Métodos de pago: Tarjeta (simulada/sandbox), Transferencia SPEI, Efectivo en sucursal y Contra entrega. "
        "Usa ÚNICAMENTE los productos reales del catálogo siguiente:\n"
        f"{catalogo_txt}"
    )


def _respuesta_asistente_local(mensaje: str, datos: dict) -> str:
    """Respuesta inteligente de respaldo cuando Ollama no está ejecutándose."""
    q = mensaje.lower()
    prods = datos.get("productos", [])

    if any(k in q for k in ("pago", "pagar", "tarjeta", "transferencia", "efectivo", "entrega")):
        return (
            "Aceptamos Tarjeta (Visa/MC en modo prueba), Transferencia bancaria SPEI, Efectivo en sucursal "
            "y Pago contra entrega en Tepeaca y región. Los precios suman 16% de IVA al finalizar."
        )
    if any(k in q for k in ("descuento", "estudiante", "empresa", "ingeniero", "perfil")):
        return (
            "Contamos con descuentos automáticos por perfil: Estudiante (10%), Empresa (8%) e Ingeniero (5%). "
            "Puedes elegir tu perfil directamente en el carrito antes de pagar."
        )

    palabras = [w for w in re.split(r"\W+", q) if len(w) >= 3 and w not in ("que", "cual", "para", "con", "tienes", "recomiendas", "precio", "stock", "hay")]
    coincidencias = []
    for p in prods:
        texto = f"{p['nombre']} {p['categoria']} {especificaciones_producto(p).get('especs', '')}".lower()
        score = sum(1 for w in palabras if w in texto)
        if score > 0 or ("gamer" in q and "gaming" in p["categoria"].lower()) or ("componente" in q and p["categoria"] == "Componentes"):
            coincidencias.append((score, p))

    coincidencias.sort(key=lambda x: (x[0], x[1]["stock"] > 0), reverse=True)
    if coincidencias:
        top = [p for _, p in coincidencias[:3]]
        resumen = "\n".join(
            f"• {p['nombre']}: ${p['precio']:,.2f} + IVA ({'Disponible: ' + str(p['stock']) if p['stock'] > 0 else 'Agotado'})"
            for p in top
        )
        return f"Encontré estas opciones en nuestro catálogo:\n{resumen}\n\n(Tip: inicia Ollama localmente para respuestas conversacionales completas)."

    disponibles = [p for p in prods if p["stock"] > 0][:3]
    sug = ", ".join(p["nombre"] for p in disponibles)
    return (
        f"Tengo {len(prods)} productos en catálogo (por ejemplo: {sug}). "
        "Pregúntame por laptops, PCs gamer, componentes (RTX, RAM, SSD), precios o métodos de pago."
    )


@app.route("/api/chat/status")
def api_chat_status():
    if not usuario_actual():
        return jsonify({"error": "Autenticación requerida"}), 401
    activo, modelo = _detectar_modelo_ollama()
    return jsonify({"ollama_activo": activo, "modelo": modelo})


@app.post("/api/chat")
def api_chat():
    u = usuario_actual()
    if not u:
        return jsonify({"error": "Autenticación requerida"}), 401

    payload = request.get_json(silent=True) or {}
    mensaje = str(payload.get("mensaje", "")).strip()[:500]
    if not mensaje:
        return jsonify({"error": "Escribe un mensaje para el asistente."}), 400

    datos = cargar()
    activo, modelo = _detectar_modelo_ollama()
    if activo:
        try:
            body = json.dumps({
                "model": modelo,
                "messages": [
                    {"role": "system", "content": _contexto_tienda_prompt(datos, u["rol"])},
                    {"role": "user", "content": mensaje},
                ],
                "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                respuesta = (res_data.get("message", {}).get("content") or "").strip()
                if respuesta:
                    return jsonify({"respuesta": respuesta, "motor": f"Ollama ({modelo})"})
        except Exception as e:
            registrar_evento("DEBUG", f"[Ollama] Fallback local por error: {e}")

    return jsonify({
        "respuesta": _respuesta_asistente_local(mensaje, datos),
        "motor": "Asistente local M&T",
    })


# ---------------------------------------------------------------------------
# Vitrina y detalle
# ---------------------------------------------------------------------------
def _ordenar_productos(lista: list, orden: str) -> list:
    if orden == "precio_asc":
        return sorted(lista, key=lambda p: p["precio"])
    if orden == "precio_desc":
        return sorted(lista, key=lambda p: p["precio"], reverse=True)
    if orden == "stock_desc":
        return sorted(lista, key=lambda p: (p["stock"] > 0, p["stock"]), reverse=True)
    if orden == "nombre":
        return sorted(lista, key=lambda p: p["nombre"].lower())
    return lista


@app.route("/")
@requiere_rol()
def index():
    datos = cargar()
    cat = request.args.get("cat", "Todas")
    q = request.args.get("q", "").strip().lower()
    orden = request.args.get("orden", "destacados")
    if orden not in {"destacados", "precio_asc", "precio_desc", "stock_desc", "nombre"}:
        orden = "destacados"

    productos = [
        p for p in datos["productos"]
        if (cat == "Todas" or p["categoria"] == cat)
        and (not q or q in p["nombre"].lower() or q in p["categoria"].lower()
             or q in especificaciones_producto(p).get("especs", "").lower()
             or q in especificaciones_producto(p).get("tipo", "").lower())
    ]
    productos = _ordenar_productos(productos, orden)

    # Vista "Todas" sin búsqueda ni orden personalizado: un bloque por apartado principal + el resto
    secciones = []
    if cat == "Todas" and not q and orden == "destacados":
        for nombre, lema in SECCIONES.items():
            secciones.append((nombre, lema, [p for p in productos if p["categoria"] == nombre]))
        otros = [p for p in productos if p["categoria"] not in SECCIONES]
        if otros:
            secciones.append(("Más productos", "Equipo, software y mobiliario para tu estación", otros))

    # Lista para la tabla técnica de componentes (respeta búsqueda si el filtro actual es Componentes)
    componentes_base = [p for p in datos["productos"] if p["categoria"] == "Componentes"]
    if cat == "Componentes" and q:
        componentes_tabla = productos
    else:
        componentes_tabla = _ordenar_productos(componentes_base, orden)

    # Ofertas relámpago destacadas (prioriza productos con descuento real, luego en stock)
    en_stock = [p for p in datos["productos"] if p["stock"] > 0]
    con_oferta = sorted(en_stock, key=lambda p: float(p.get("descuento", 0) or 0), reverse=True)
    ofertas_relampago = con_oferta[:5]

    # Ventas más codiciadas (calculado de pedidos vigentes + destacados de alta demanda)
    conteo_vendidos = {}
    for ped in datos.get("pedidos", []):
        if ped.get("estado") != "Cancelado":
            for it in ped.get("items", []):
                pid_it = it.get("producto_id")
                conteo_vendidos[pid_it] = conteo_vendidos.get(pid_it, 0) + int(it.get("cantidad", 0))

    prioridad_destacados = {10: 5, 9: 4, 12: 3, 1: 2, 14: 1}
    mas_codiciados = sorted(
        en_stock,
        key=lambda p: (conteo_vendidos.get(p["id"], 0), prioridad_destacados.get(p["id"], 0), p["precio"]),
        reverse=True,
    )[:4]

    return render_template(
        "index.html",
        productos=productos,
        secciones=secciones,
        componentes_tabla=componentes_tabla,
        ofertas_relampago=ofertas_relampago,
        mas_codiciados=mas_codiciados,
        conteo_vendidos=conteo_vendidos,
        categorias=["Todas"] + CATEGORIAS,
        cat=cat,
        q=q,
        orden=orden,
        carrito=carrito_sesion(),
    )


def _tambien_llevaron(datos: dict, pids_base: list, limite: int = 4) -> list:
    """Calcula productos comprados juntos en pedidos reales, con respaldo complementario."""
    base_set = set(pids_base)
    frec = {}
    for ped in datos.get("pedidos", []):
        if ped.get("estado") == "Cancelado":
            continue
        ids_ped = {it.get("producto_id") for it in ped.get("items", [])}
        if ids_ped & base_set:
            for pid_it in ids_ped - base_set:
                frec[pid_it] = frec.get(pid_it, 0) + 1
    prods_map = {p["id"]: p for p in datos.get("productos", [])}
    elegidos = [prods_map[pid] for pid, _ in sorted(frec.items(), key=lambda x: x[1], reverse=True) if pid in prods_map and prods_map[pid]["stock"] > 0]
    if len(elegidos) < limite:
        vistos = base_set | {p["id"] for p in elegidos}
        for p in datos.get("productos", []):
            if p["id"] not in vistos and p["stock"] > 0:
                elegidos.append(p)
                vistos.add(p["id"])
                if len(elegidos) >= limite:
                    break
    return elegidos[:limite]


@app.route("/producto/<int:pid>")
@requiere_rol()
def producto_detalle(pid):
    datos = cargar()
    prod = logica.buscar_producto(datos, pid)
    if not prod:
        flash("Ese producto ya no existe en el catálogo.", "error")
        return redirect(url_for("index"))
    relacionados = [p for p in datos["productos"] if p["categoria"] == prod["categoria"] and p["id"] != pid][:3]
    tambien_llevaron = _tambien_llevaron(datos, [pid], limite=4)
    c = carrito_sesion()
    return render_template(
        "producto.html",
        prod=prod,
        relacionados=relacionados,
        tambien_llevaron=tambien_llevaron,
        en_carrito=c.get(pid, 0),
        carrito=c,
    )


# ---------------------------------------------------------------------------
# Carrito, Cupones, Puntos, Envío Gratis y WhatsApp
# ---------------------------------------------------------------------------
def _cupon_activo(u: dict | None):
    cod = session.get("cupon_codigo", "")
    if not cod or cod not in CUPONES:
        return None
    if u and cod in u.get("cupones_usados", []):
        session.pop("cupon_codigo", None)
        return None
    return {"codigo": cod, **CUPONES[cod]}


@app.route("/carrito")
@requiere_rol("comprador")
def carrito():
    datos = cargar()
    u = usuario_actual()
    c = carrito_sesion()
    perfil = session.get("perfil", "General")
    cupon = _cupon_activo(u)
    cupon_pct = cupon["pct"] if cupon else 0.0
    puntos_disp = u["puntos_lealtad"] if u else 0.0
    usar_puntos = puntos_disp if session.get("usar_puntos") and puntos_disp > 0 else 0.0
    items, subtotal, descuento, iva, total = logica.calcular_totales(
        datos, c, perfil, cupon_pct=cupon_pct, puntos_usar=usar_puntos
    )
    guardar_carrito(c)  # calcular_totales ajusta cantidades a las existencias reales

    envio_faltante = round(max(0.0, ENVIO_GRATIS_MIN - total), 2)
    envio_pct = round(min(100.0, (total / ENVIO_GRATIS_MIN) * 100.0), 1) if ENVIO_GRATIS_MIN else 100.0
    tambien_llevaron = _tambien_llevaron(datos, list(c.keys()), limite=4) if c else []

    whatsapp_url = ""
    if WHATSAPP and items:
        lineas_wa = [f"Hola {NOMBRE_TIENDA}, quiero hacer este pedido:"]
        for it in items:
            lineas_wa.append(f"- {it['cantidad']}x {it['nombre']} ({logica.dinero(it['importe'])})")
        lineas_wa.append(f"Perfil: {perfil}")
        if cupon:
            lineas_wa.append(f"Cupón: {cupon['codigo']} (-{cupon['pct']}%)")
        lineas_wa.append(f"Total c/IVA: {logica.dinero(total)}")
        whatsapp_url = f"https://wa.me/{WHATSAPP}?text={urllib.parse.quote(chr(10).join(lineas_wa))}"

    return render_template(
        "carrito.html",
        items=items, subtotal=subtotal, descuento=descuento, iva=iva, total=total,
        perfiles=[(p, logica.etiqueta_perfil(p)) for p in PERFILES_CLIENTE], perfil=perfil,
        metodos=METODOS_PAGO, cliente=session.get("cliente", ""),
        cupon=cupon,
        puntos_disp=puntos_disp,
        usar_puntos=bool(session.get("usar_puntos")),
        envio_faltante=envio_faltante,
        envio_pct=envio_pct,
        tambien_llevaron=tambien_llevaron,
        whatsapp_url=whatsapp_url,
        productos={p["id"]: p for p in datos["productos"]},
    )


@app.post("/carrito/cupon")
@requiere_rol("comprador")
def carrito_cupon():
    accion = request.form.get("accion", "aplicar")
    if accion == "quitar":
        session.pop("cupon_codigo", None)
        flash("Cupón retirado.", "aviso")
        return redirect(url_for("carrito"))
    codigo = request.form.get("codigo", "").strip().upper()
    if codigo not in CUPONES:
        flash(f"El cupón «{codigo}» no es válido o expiró.", "error")
        return redirect(url_for("carrito"))
    u = usuario_actual()
    if u and codigo in u.get("cupones_usados", []):
        flash(f"Ya utilizaste el cupón «{codigo}» anteriormente.", "aviso")
        return redirect(url_for("carrito"))
    session["cupon_codigo"] = codigo
    flash(f"Cupón «{codigo}» aplicado (−{CUPONES[codigo]['pct']}%).", "ok")
    return redirect(url_for("carrito"))


@app.post("/carrito/puntos")
@requiere_rol("comprador")
def carrito_puntos():
    session["usar_puntos"] = request.form.get("usar", "0") == "1"
    return redirect(url_for("carrito"))


@app.post("/carrito/agregar")
@requiere_rol("comprador")
def carrito_agregar():
    datos = cargar()
    try:
        pid = int(request.form["pid"])
        cantidad = max(1, min(int(request.form.get("cantidad", 1)), 99))
    except (KeyError, ValueError):
        abort(400)
    prod = logica.buscar_producto(datos, pid)
    c = carrito_sesion()
    if not prod:
        flash("Ese producto ya no existe.", "error")
    elif prod["stock"] <= 0:
        flash(f"«{prod['nombre']}» está agotado.", "error")
    else:
        nueva = min(c.get(pid, 0) + cantidad, prod["stock"])
        if nueva < c.get(pid, 0) + cantidad:
            flash(f"Solo hay {prod['stock']} unidad(es) de «{prod['nombre']}».", "aviso")
        else:
            flash(f"Agregado: {prod['nombre']}", "ok")
        c[pid] = nueva
        guardar_carrito(c)
    destino = request.form.get("volver") or url_for("index")
    return redirect(destino if destino.startswith("/") and not destino.startswith("//") else url_for("index"))


@app.post("/carrito/actualizar")
@requiere_rol("comprador")
def carrito_actualizar():
    try:
        pid = int(request.form["pid"])
    except (KeyError, ValueError):
        abort(400)
    accion = request.form.get("accion")
    c = carrito_sesion()
    prod = logica.buscar_producto(cargar(), pid)
    if accion == "mas" and prod and c.get(pid, 0) < prod["stock"]:
        c[pid] = c.get(pid, 0) + 1
    elif accion == "mas":
        flash("No hay más existencias de ese producto.", "aviso")
    elif accion == "menos":
        c[pid] = c.get(pid, 0) - 1
    elif accion == "quitar":
        c[pid] = 0
    guardar_carrito(c)
    return redirect(url_for("carrito"))


@app.post("/carrito/vaciar")
@requiere_rol("comprador")
def carrito_vaciar():
    session.pop("carrito", None)
    return redirect(url_for("carrito"))


@app.post("/carrito/perfil")
@requiere_rol("comprador")
def carrito_perfil():
    perfil = request.form.get("perfil", "General")
    session["perfil"] = perfil if perfil in PERFILES_CLIENTE else "General"
    session["cliente"] = request.form.get("cliente", "")[:80]
    return redirect(url_for("carrito"))


# ---------------------------------------------------------------------------
# Autenticación (Comprador y Vendedor)
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    rol_tab = request.values.get("rol", "comprador")
    if rol_tab not in ("comprador", "vendedor"):
        rol_tab = "comprador"
    siguiente = request.values.get("next", "")

    if request.method == "POST":
        identificador = request.form.get("identificador", "").strip()
        password = request.form.get("password", "")
        clave_intento = _clave_intento_login(identificador)
        if _login_bloqueado(clave_intento):
            flash("Demasiados intentos. Espera 15 minutos antes de volver a intentar.", "error")
            return render_template("login.html", rol_tab=rol_tab, modo="login",
                                   identificador=identificador, next_url=siguiente,
                                   perfiles=[(p, logica.etiqueta_perfil(p)) for p in PERFILES_CLIENTE]), 429

        datos = cargar()
        user = _buscar_usuario(datos, identificador)
        password_valido = False
        if user and 0 < len(password) <= _LONGITUD_MAX_PASSWORD:
            try:
                password_valido = check_password_hash(user.get("password_hash", ""), password)
            except (TypeError, ValueError):
                password_valido = False
        if not password_valido or _credencial_predeterminada(user, password):
            _registrar_fallo_login(clave_intento)
            flash("Usuario o contraseña incorrectos.", "error")
            return render_template("login.html", rol_tab=rol_tab, modo="login",
                                   identificador=identificador, next_url=siguiente,
                                   perfiles=[(p, logica.etiqueta_perfil(p)) for p in PERFILES_CLIENTE]), 401

        _limpiar_fallos_login(clave_intento)
        carrito = session.get("carrito")
        session.clear()  # rota la sesión al autenticar y evita fijación de sesión
        if isinstance(carrito, dict):
            session["carrito"] = carrito
        session["csrf"] = secrets.token_hex(16)
        session["usuario_auth"] = {
            "usuario": user["usuario"],
            "nombre": user["nombre"],
            "rol": user["rol"],
            "perfil": user.get("perfil", "General"),
        }
        if user["rol"] == "comprador":
            session["cliente"] = user["nombre"]
            session["perfil"] = user.get("perfil", "General")
        registrar_evento("AUTH", f"[WEB] Inicio de sesión ({user['rol']}): {user['usuario']}")
        flash(f"Bienvenido, {user['nombre']} ({user['rol'].capitalize()}).", "ok")
        respaldo = url_for("vendedor_panel") if user["rol"] == "vendedor" else url_for("index")
        return redirect(_destino_seguro(siguiente, respaldo))

    return render_template(
        "login.html",
        rol_tab=rol_tab,
        modo=request.args.get("modo", "login"),
        identificador="",
        next_url=siguiente,
        perfiles=[(p, logica.etiqueta_perfil(p)) for p in PERFILES_CLIENTE],
    )


@app.post("/registro")
def registro():
    nombre = request.form.get("nombre", "").strip()[:80]
    identificador = request.form.get("identificador", "").strip().lower()
    password = request.form.get("password", "")
    perfil = request.form.get("perfil", "General")
    perfil = perfil if perfil in PERFILES_CLIENTE else "General"
    siguiente = request.form.get("next", "")

    errores = []
    if len(nombre) < 2:
        errores.append("Ingresa tu nombre completo (mínimo 2 caracteres).")
    if len(identificador) < 3 or " " in identificador:
        errores.append("Ingresa un correo o usuario válido (sin espacios, mínimo 3 caracteres).")
    if len(password) < _LONGITUD_MIN_PASSWORD:
        errores.append(f"La contraseña debe tener al menos {_LONGITUD_MIN_PASSWORD} caracteres.")
    elif len(password) > _LONGITUD_MAX_PASSWORD:
        errores.append(f"La contraseña no puede superar {_LONGITUD_MAX_PASSWORD} caracteres.")

    with _cerrojo:
        datos = cargar()
        if not errores and _buscar_usuario(datos, identificador):
            errores.append("Ese correo o usuario ya está registrado. Inicia sesión.")
        if errores:
            for err in errores:
                flash(err, "error")
            return render_template(
                "login.html", rol_tab="comprador", modo="registro",
                identificador=identificador, nombre_reg=nombre, perfil_reg=perfil,
                next_url=siguiente,
                perfiles=[(p, logica.etiqueta_perfil(p)) for p in PERFILES_CLIENTE],
            ), 400

        nuevo = {
            "usuario": identificador,
            "alias": identificador.split("@")[0] if "@" in identificador else identificador,
            "nombre": nombre,
            "rol": "comprador",
            "perfil": perfil,
            "password_hash": generate_password_hash(password),
        }
        # Evitar colisión de alias si ya existe
        if any(u.get("alias", "").lower() == nuevo["alias"].lower() for u in datos.get("usuarios", [])):
            nuevo["alias"] = identificador
        datos.setdefault("usuarios", []).append(nuevo)
        guardar_almacenamiento(datos)

    carrito = session.get("carrito")
    session.clear()
    if isinstance(carrito, dict):
        session["carrito"] = carrito
    session["csrf"] = secrets.token_hex(16)
    session["usuario_auth"] = {
        "usuario": nuevo["usuario"],
        "nombre": nuevo["nombre"],
        "rol": "comprador",
        "perfil": perfil,
    }
    session["cliente"] = nombre
    session["perfil"] = perfil
    registrar_evento("AUTH", f"[WEB] Nuevo registro de comprador: {nuevo['usuario']} ({perfil})")
    flash(f"Cuenta creada. ¡Bienvenido, {nombre}!", "ok")
    return redirect(_destino_seguro(siguiente, url_for("index")))


@app.post("/logout")
def logout():
    u = usuario_actual()
    session.clear()
    session["csrf"] = secrets.token_hex(16)
    if u:
        registrar_evento("AUTH", f"[WEB] Cierre de sesión: {u['usuario']}")
    flash("Sesión cerrada correctamente.", "ok")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Mis pedidos (Comprador) y Panel del Vendedor
# ---------------------------------------------------------------------------
@app.route("/mis-pedidos")
@requiere_rol("comprador")
def mis_pedidos():
    datos = cargar()
    u = usuario_actual()
    ids_sesion = set(session.get("pedidos", []))
    pedidos_usuario = [
        p for p in datos.get("pedidos", [])
        if p.get("usuario") == u["usuario"] or p["id"] in ids_sesion
    ]
    return render_template("mis_pedidos.html", pedidos=pedidos_usuario)


@app.route("/vendedor")
@requiere_rol("vendedor")
def vendedor_panel():
    datos = cargar()
    estado_filtro = request.args.get("estado", "Todos")
    q = request.args.get("q", "").strip().lower()
    tab = request.args.get("tab", "pedidos")
    if tab not in ("pedidos", "inventario"):
        tab = "pedidos"

    todos_pedidos = datos.get("pedidos", [])
    ventas_netas = 0.0
    validos = 0
    en_proceso = 0
    cancelados = 0
    distribucion = {e: 0 for e in ESTADOS_PEDIDO}

    for p in todos_pedidos:
        est = p.get("estado", "Pendiente")
        distribucion[est] = distribucion.get(est, 0) + 1
        if est == "Cancelado":
            cancelados += 1
        else:
            ventas_netas += float(p.get("total", 0))
            validos += 1
            if est in ("Pendiente", "Preparando"):
                en_proceso += 1

    ticket_promedio = round(ventas_netas / validos, 2) if validos else 0.0
    pedidos_filtrados = [
        p for p in todos_pedidos
        if (estado_filtro == "Todos" or p.get("estado") == estado_filtro)
        and (
            not q
            or q in p.get("cliente", "").lower()
            or q in str(p.get("id", ""))
            or q in p.get("usuario", "").lower()
        )
    ]

    productos = datos.get("productos", [])
    stock_resumen = {
        "total": len(productos),
        "disponibles": sum(1 for pr in productos if logica.estado_stock(pr["stock"]) == "ok"),
        "bajo": sum(1 for pr in productos if logica.estado_stock(pr["stock"]) == "bajo"),
        "agotados": sum(1 for pr in productos if logica.estado_stock(pr["stock"]) == "agotado"),
    }

    # Alertas inteligentes de inventario (stock bajo/agotado + días estimados de agotamiento según ventas reales)
    unidades_vendidas_prod = {}
    ventas_por_dia = {}
    ventas_cat = {c: 0.0 for c in CATEGORIAS}
    ingresos_prod = {}

    for p in todos_pedidos:
        if p.get("estado") != "Cancelado":
            dia = (p.get("fecha") or "")[:10]
            if dia:
                ventas_por_dia[dia] = round(ventas_por_dia.get(dia, 0.0) + float(p.get("total", 0)), 2)
            for it in p.get("items", []):
                pid_it = it.get("producto_id")
                cant_it = int(it.get("cantidad", 0))
                imp_it = float(it.get("importe", 0))
                unidades_vendidas_prod[pid_it] = unidades_vendidas_prod.get(pid_it, 0) + cant_it
                ingresos_prod[pid_it] = round(ingresos_prod.get(pid_it, 0.0) + imp_it, 2)
                c_it = it.get("categoria", "Equipo")
                if c_it in ventas_cat:
                    ventas_cat[c_it] += imp_it

    dias_activos = max(1, len(ventas_por_dia))
    alertas_stock = []
    for pr in productos:
        niv = logica.estado_stock(pr["stock"])
        vendidos_pr = unidades_vendidas_prod.get(pr["id"], 0)
        ritmo_diario = vendidos_pr / dias_activos if vendidos_pr > 0 else 0
        dias_restantes = round(pr["stock"] / ritmo_diario, 1) if ritmo_diario > 0 and pr["stock"] > 0 else None
        if niv in ("agotado", "bajo") or (dias_restantes is not None and dias_restantes <= 7):
            alertas_stock.append({
                "id": pr["id"],
                "nombre": pr["nombre"],
                "stock": pr["stock"],
                "nivel": niv,
                "vendidos": vendidos_pr,
                "dias_restantes": dias_restantes,
            })

    # Ranking real de productos más vendidos
    prods_map = {pr["id"]: pr for pr in productos}
    ranking_vendidos = [
        {
            "id": pid_it,
            "nombre": prods_map[pid_it]["nombre"],
            "categoria": prods_map[pid_it]["categoria"],
            "unidades": cant,
            "ingresos": ingresos_prod.get(pid_it, 0.0),
        }
        for pid_it, cant in sorted(unidades_vendidas_prod.items(), key=lambda x: x[1], reverse=True)
        if pid_it in prods_map
    ][:5]

    # Datos reales para gráficas (por día y por categoría) + estimado basado en promedio real
    dias_ordenados = sorted(ventas_por_dia.keys())[-7:]
    graf_dias_labels = dias_ordenados if dias_ordenados else ["Sin ventas aún"]
    graf_dias_vals = [ventas_por_dia[d] for d in dias_ordenados] if dias_ordenados else [0.0]

    promedio_diario_real = round(ventas_netas / dias_activos, 2) if validos > 0 else 0.0
    estimado_mensual = round(promedio_diario_real * 30, 2)

    max_graf = max([ventas_cat[c] for c in CATEGORIAS] + [1000.0])
    grafico_datos = []
    for c in CATEGORIAS:
        real_v = round(ventas_cat[c], 2)
        est_v = round((real_v / dias_activos) * 30, 2) if real_v > 0 else 0.0
        grafico_datos.append({
            "categoria": c,
            "color": CATEGORIA_ESTILO.get(c, {}).get("color", "#2a9d8f"),
            "real": real_v,
            "estimado": est_v,
            "pct_real": round(min(100.0, (real_v / max_graf) * 100.0), 1),
            "pct_est": round(min(100.0, (est_v / max(max_graf, estimado_mensual, 1000.0)) * 100.0), 1),
        })

    return render_template(
        "vendedor.html",
        tab=tab,
        pedidos=pedidos_filtrados,
        total_pedidos=len(todos_pedidos),
        ventas_netas=round(ventas_netas, 2),
        estimado_mensual=estimado_mensual,
        promedio_diario_real=promedio_diario_real,
        grafico_datos=grafico_datos,
        graf_dias_labels=graf_dias_labels,
        graf_dias_vals=graf_dias_vals,
        ranking_vendidos=ranking_vendidos,
        alertas_stock=alertas_stock,
        pedidos_vigentes=validos,
        en_proceso=en_proceso,
        cancelados=cancelados,
        ticket_promedio=ticket_promedio,
        distribucion=distribucion,
        estado_filtro=estado_filtro,
        q=q,
        productos=productos,
        stock_resumen=stock_resumen,
    )


@app.post("/vendedor/pedido/estado")
@requiere_rol("vendedor")
def vendedor_pedido_estado():
    try:
        oid = int(request.form["pid"])
    except (KeyError, ValueError):
        abort(400)
    nuevo = request.form.get("estado", "")
    if nuevo not in ESTADOS_PEDIDO:
        abort(400)
    reintegrar = request.form.get("reintegrar", "1") == "1"

    with _cerrojo:
        datos = cargar()
        ped = logica.buscar_pedido(datos, oid)
        if not ped:
            flash("Ese pedido ya no existe.", "error")
            return redirect(url_for("vendedor_panel"))

        anterior = ped.get("estado", "Pendiente")
        if nuevo == anterior:
            flash(f"El pedido #{oid} ya está en estado «{nuevo}».", "aviso")
            return redirect(url_for("vendedor_panel"))

        if nuevo == "Cancelado" and not ped.get("stock_reintegrado", False) and reintegrar:
            for it in ped.get("items", []):
                prod = logica.buscar_producto(datos, it["producto_id"])
                if prod:
                    prod["stock"] += it["cantidad"]
            ped["stock_reintegrado"] = True
            registrar_evento("STOCK", f"[WEB] Reintegrado stock por cancelación de pedido #{oid}.")
        elif anterior == "Cancelado" and ped.get("stock_reintegrado", False):
            faltan = []
            for it in ped.get("items", []):
                prod = logica.buscar_producto(datos, it["producto_id"])
                if not prod or prod["stock"] < it["cantidad"]:
                    nombre = prod["nombre"] if prod else it.get("nombre", f"ID {it['producto_id']}")
                    faltan.append(f"{nombre} (requiere {it['cantidad']})")
            if faltan:
                flash("Stock insuficiente para reactivar el pedido: " + ", ".join(faltan), "error")
                return redirect(url_for("vendedor_panel"))
            for it in ped.get("items", []):
                logica.buscar_producto(datos, it["producto_id"])["stock"] -= it["cantidad"]
            ped["stock_reintegrado"] = False
            registrar_evento("STOCK", f"[WEB] Re-deducido stock al reactivar pedido #{oid}.")

        ped["estado"] = nuevo
        ped.setdefault("historial_estados", [{"estado": anterior, "fecha": ped.get("fecha", "")}]).append({
            "estado": nuevo,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        guardar_almacenamiento(datos)

    registrar_evento("PEDIDO", f"[WEB] Pedido #{oid} cambió de '{anterior}' a '{nuevo}'.")
    flash(f"Pedido #{oid} actualizado a «{nuevo}».", "ok")
    return redirect(url_for("vendedor_panel", estado=request.form.get("estado_filtro", "Todos")))


@app.post("/vendedor/producto/stock")
@requiere_rol("vendedor")
def vendedor_producto_stock():
    try:
        pid = int(request.form["pid"])
        cant = int(request.form.get("cantidad", 0))
    except (KeyError, ValueError):
        abort(400)
    if cant < 0 or cant > 9999:
        flash("La cantidad debe estar entre 0 y 9999.", "error")
        return redirect(url_for("vendedor_panel", tab="inventario"))
    accion = request.form.get("accion", "sumar")

    with _cerrojo:
        datos = cargar()
        prod = logica.buscar_producto(datos, pid)
        if not prod:
            flash("Producto no encontrado.", "error")
            return redirect(url_for("vendedor_panel", tab="inventario"))
        prod["stock"] = prod["stock"] + cant if accion == "sumar" else cant
        guardar_almacenamiento(datos)

    registrar_evento("STOCK", f"[WEB] Stock de '{prod['nombre']}' actualizado a {prod['stock']}.")
    flash(f"Existencias de «{prod['nombre']}» actualizadas a {prod['stock']}.", "ok")
    return redirect(url_for("vendedor_panel", tab="inventario"))


@app.post("/vendedor/producto/nuevo")
@requiere_rol("vendedor")
def vendedor_producto_nuevo():
    nombre = request.form.get("nombre", "").strip()[:120]
    categoria = request.form.get("categoria", CATEGORIAS[0])
    especs = request.form.get("especs", "").strip()[:160]
    if categoria not in CATEGORIAS:
        categoria = CATEGORIAS[0]
    try:
        precio = round(float(request.form.get("precio", "0").replace(",", "").replace("$", "")), 2)
        stock = int(request.form.get("stock", "0"))
    except ValueError:
        precio, stock = -1, -1

    if not nombre or precio < 0 or stock < 0:
        flash("Verifica el nombre, precio (>= 0) y stock (>= 0) del producto.", "error")
        return redirect(url_for("vendedor_panel", tab="inventario"))

    foto_nombre = ""
    # Manejar subida de imagen
    if "foto" in request.files:
        archivo = request.files["foto"]
        if archivo and archivo.filename:
            ext = os.path.splitext(archivo.filename)[1].lower()
            if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
                os.makedirs(FOTOS_DIR, exist_ok=True)
                nombre_limpio = secure_filename(archivo.filename) or f"img{ext}"
                foto_nombre = f"prod_{secrets.token_hex(4)}_{nombre_limpio}"
                archivo.save(os.path.join(FOTOS_DIR, foto_nombre))
            else:
                flash("Formato de imagen no admitido. Usa PNG, JPG, JPEG, WEBP o GIF.", "aviso")

    def _pct(campo: str) -> float:
        try:
            v = float(request.form.get(campo, "0") or 0)
            return round(max(0.0, min(90.0, v)), 1)
        except ValueError:
            return 0.0

    descuento_gral = _pct("descuento")
    descuentos_perfil = {}
    for clave, campo in (("Estudiante", "desc_estudiante"), ("Escuela", "desc_escuela"), ("Empresa", "desc_empresa")):
        val = _pct(campo)
        if val > 0:
            descuentos_perfil[clave] = val

    with _cerrojo:
        datos = cargar()
        pid = datos.get("next_prod_id", 1)
        datos["next_prod_id"] = pid + 1
        nuevo = {
            "id": pid,
            "nombre": nombre,
            "categoria": categoria,
            "precio": precio,
            "stock": stock,
            "foto": foto_nombre,
        }
        if descuento_gral > 0:
            nuevo["descuento"] = descuento_gral
        if descuentos_perfil:
            nuevo["descuentos_perfil"] = descuentos_perfil
        if especs:
            nuevo["especs"] = especs
        datos.setdefault("productos", []).append(nuevo)
        guardar_almacenamiento(datos)

    registrar_evento("CATALOGO", f"[WEB] Alta de producto #{pid}: {nombre} ({categoria}, stock={stock}, foto={foto_nombre}).")
    flash(f"Producto «{nombre}» agregado al catálogo.", "ok")
    return redirect(url_for("vendedor_panel", tab="inventario"))


@app.post("/vendedor/producto/foto")
@requiere_rol("vendedor")
def vendedor_producto_foto():
    """Actualiza o asigna la imagen de un producto existente."""
    try:
        pid = int(request.form["pid"])
    except (KeyError, ValueError):
        abort(400)

    if "foto" not in request.files:
        flash("No se seleccionó ningún archivo de imagen.", "error")
        return redirect(url_for("vendedor_panel", tab="inventario"))

    archivo = request.files["foto"]
    if not archivo or not archivo.filename:
        flash("Selecciona un archivo de imagen válido.", "error")
        return redirect(url_for("vendedor_panel", tab="inventario"))

    ext = os.path.splitext(archivo.filename)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        flash("Formato no soportado. Debe ser PNG, JPG, JPEG, WEBP o GIF.", "error")
        return redirect(url_for("vendedor_panel", tab="inventario"))

    os.makedirs(FOTOS_DIR, exist_ok=True)
    nombre_limpio = secure_filename(archivo.filename) or f"img{ext}"
    foto_nombre = f"prod_{secrets.token_hex(4)}_{nombre_limpio}"
    archivo.save(os.path.join(FOTOS_DIR, foto_nombre))

    with _cerrojo:
        datos = cargar()
        prod = logica.buscar_producto(datos, pid)
        if not prod:
            flash("Producto no encontrado.", "error")
            return redirect(url_for("vendedor_panel", tab="inventario"))
        prod["foto"] = foto_nombre
        guardar_almacenamiento(datos)

    registrar_evento("CATALOGO", f"[WEB] Imagen actualizada para producto #{pid}: {prod['nombre']} -> {foto_nombre}")
    flash(f"Imagen actualizada para «{prod['nombre']}».", "ok")
    return redirect(url_for("vendedor_panel", tab="inventario"))



# ---------------------------------------------------------------------------
# Pasarela de pago simulada y compra
# ---------------------------------------------------------------------------
@app.post("/pagar")
@requiere_rol("comprador")
def pagar():
    """Paso intermedio: valida el carrito, calcula totales y muestra la pasarela de pago simulada."""
    perfil = request.form.get("perfil", "General")
    perfil = perfil if perfil in PERFILES_CLIENTE else "General"
    pago = request.form.get("pago", METODOS_PAGO[0])
    pago = pago if pago in METODOS_PAGO else METODOS_PAGO[0]
    cliente = request.form.get("cliente", "")[:80]
    session["perfil"], session["cliente"] = perfil, cliente

    datos = cargar()
    u = usuario_actual()
    c = carrito_sesion()
    cupon = _cupon_activo(u)
    cupon_pct = cupon["pct"] if cupon else 0.0
    puntos_disp = u["puntos_lealtad"] if u else 0.0
    usar_puntos = puntos_disp if session.get("usar_puntos") and puntos_disp > 0 else 0.0
    items, subtotal, descuento, iva, total = logica.calcular_totales(
        datos, c, perfil, cupon_pct=cupon_pct, puntos_usar=usar_puntos
    )
    guardar_carrito(c)

    if not items:
        flash("El carrito está vacío o los productos ya no tienen existencias.", "error")
        return redirect(url_for("carrito"))

    # Generar un token de pago único para esta sesión de checkout
    token_pago = secrets.token_hex(16)
    session["pago_token"] = token_pago
    session["pago_metodo"] = pago

    return render_template(
        "pago.html",
        items=items,
        subtotal=subtotal,
        descuento=descuento,
        iva=iva,
        total=total,
        pago=pago,
        perfil=perfil,
        cliente=cliente,
        token_pago=token_pago,
        productos={p["id"]: p for p in datos["productos"]},
    )


@app.post("/comprar")
@requiere_rol("comprador")
def comprar():
    """Paso final: valida el token de pago y confirma la compra."""
    # Validar que viene de la pasarela de pago
    token = request.form.get("token_pago", "")
    token_sesion = session.pop("pago_token", "")
    if not token or not token_sesion or not secrets.compare_digest(token, token_sesion):
        flash("La sesión de pago ha expirado o es inválida. Intenta de nuevo desde el carrito.", "error")
        return redirect(url_for("carrito"))

    perfil = request.form.get("perfil", "General")
    perfil = perfil if perfil in PERFILES_CLIENTE else "General"
    pago = session.pop("pago_metodo", request.form.get("pago", METODOS_PAGO[0]))
    pago = pago if pago in METODOS_PAGO else METODOS_PAGO[0]
    cliente = request.form.get("cliente", "")[:80]
    session["perfil"], session["cliente"] = perfil, cliente
    u = usuario_actual()

    # Datos de pago simulados (se registran en el pedido pero no se cobran)
    datos_pago = {}
    if pago == "Tarjeta":
        numero = request.form.get("card_number", "").replace(" ", "")
        datos_pago = {
            "ultimos4": numero[-4:] if len(numero) >= 4 else "****",
            "titular": request.form.get("card_name", "")[:60],
            "red": "Visa" if numero[:1] == "4" else "Mastercard" if numero[:1] == "5" else "Otra",
        }
    elif pago == "Transferencia bancaria":
        datos_pago = {
            "banco_origen": request.form.get("banco_origen", "")[:40],
            "referencia": request.form.get("referencia_transfer", "")[:30] or f"REF-{secrets.token_hex(4).upper()}",
        }
    elif pago == "Efectivo":
        datos_pago = {
            "sucursal": request.form.get("sucursal_pago", "M&T Tepeaca")[:40],
            "referencia": f"EF-{secrets.token_hex(4).upper()}",
        }
    elif pago == "Contra entrega":
        datos_pago = {
            "direccion": request.form.get("direccion_entrega", "")[:100],
            "telefono": request.form.get("telefono_entrega", "")[:20],
        }

    with _cerrojo:
        datos = cargar()
        c = carrito_sesion()
        cupon = _cupon_activo(u)
        cupon_pct = cupon["pct"] if cupon else 0.0
        u_rec = _buscar_usuario(datos, u["usuario"]) if u else None
        puntos_disp = float(u_rec.get("puntos_lealtad", 0.0) or 0.0) if u_rec else 0.0
        puntos_usar = puntos_disp if session.get("usar_puntos") and puntos_disp > 0 else 0.0
        try:
            pedido, agotados = logica.crear_pedido(
                datos, c, cliente, perfil, pago, cupon_pct=cupon_pct, puntos_usar=puntos_usar
            )
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("carrito"))
        pedido["datos_pago"] = datos_pago
        if cupon:
            pedido["cupon"] = cupon["codigo"]
        if u_rec:
            pedido["usuario"] = u_rec["usuario"]
            if cupon:
                u_rec.setdefault("cupones_usados", []).append(cupon["codigo"])
            # Descontar puntos usados y acreditar 2% de puntos nuevos
            restante_pts = max(0.0, puntos_disp - puntos_usar)
            ganados = round(pedido["total"] * PUNTOS_TASA, 2)
            u_rec["puntos_lealtad"] = round(restante_pts + ganados, 2)
            pedido["puntos_ganados"] = ganados
        try:
            guardar_almacenamiento(datos)
        except RuntimeError as e:
            registrar_evento("ERROR", f"[WEB] No se pudo finalizar la compra: {e}")
            flash("No pudimos registrar tu compra. El carrito sigue intacto; inténtalo de nuevo.", "error")
            return redirect(url_for("carrito"))

    session.pop("cupon_codigo", None)
    session.pop("usar_puntos", None)

    for nombre in agotados:
        registrar_evento("ALERTA", f"Producto agotado tras compra web: {nombre}")
    registrar_evento("COMPRA", f"[WEB] Pedido #{pedido['id']} por ${pedido['total']:,.2f} ({pedido['cliente']}, {pedido['pago']}, datos_pago={datos_pago}).")
    session.pop("carrito", None)
    session["pedidos"] = session.get("pedidos", []) + [pedido["id"]]
    return redirect(url_for("pedido", pid=pedido["id"]))


def _pedido_propio(pid):
    ped = logica.buscar_pedido(cargar(), pid)
    if not ped:
        abort(404)
    u = usuario_actual()
    es_vendedor = u and u["rol"] == "vendedor"
    es_dueno = u and ped.get("usuario") == u["usuario"]
    if pid not in session.get("pedidos", []) and not es_vendedor and not es_dueno:
        abort(404)
    return ped


@app.route("/pedido/<int:pid>")
@requiere_rol()
def pedido(pid):
    ped = _pedido_propio(pid)
    return render_template("pedido.html", ped=ped, ticket=logica.texto_ticket(ped))


@app.route("/pedido/<int:pid>/ticket.txt")
@requiere_rol()
def pedido_ticket(pid):
    ped = _pedido_propio(pid)
    return Response(logica.texto_ticket(ped), mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=ticket_mt_pedido_{pid}.txt"})


# ---------------------------------------------------------------------------
# Códigos QR (Producto y Pedido)
# ---------------------------------------------------------------------------
@app.route("/qr/producto/<int:pid>.svg")
@requiere_rol()
def qr_producto(pid):
    prod = logica.buscar_producto(cargar(), pid)
    if not prod:
        abort(404)
    url = request.host_url.rstrip("/") + url_for("producto_detalle", pid=pid)
    return Response(qr_svg(url, tam=150), mimetype="image/svg+xml")


@app.route("/qr/pedido/<int:pid>.svg")
@requiere_rol()
def qr_pedido(pid):
    ped = _pedido_propio(pid)
    texto_qr = f"MT-PEDIDO#{ped['id']}|{ped.get('cliente','')}|${ped.get('total',0):.2f}|{ped.get('estado','Pendiente')}"
    return Response(qr_svg(texto_qr, tam=150), mimetype="image/svg+xml")


# ---------------------------------------------------------------------------
# Favoritos con aviso de regreso a stock
# ---------------------------------------------------------------------------
@app.post("/api/favoritos/toggle")
def api_favoritos_toggle():
    u = usuario_actual()
    if not u:
        return jsonify({"error": "Autenticación requerida"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        pid = int(payload.get("pid"))
    except (TypeError, ValueError):
        return jsonify({"error": "ID inválido"}), 400
    with _cerrojo:
        datos = cargar()
        u_rec = _buscar_usuario(datos, u["usuario"])
        if not u_rec:
            return jsonify({"error": "Usuario no encontrado"}), 404
        favs = [int(x) for x in u_rec.get("favoritos", []) if str(x).isdigit()]
        if pid in favs:
            favs.remove(pid)
            activo = False
        else:
            favs.append(pid)
            activo = True
        u_rec["favoritos"] = favs
        guardar_almacenamiento(datos)
    return jsonify({"activo": activo, "favoritos": favs})


# ---------------------------------------------------------------------------
# Armador de PC con compatibilidad, Comparador, Recomendador, Cotizador y Trade-in
# ---------------------------------------------------------------------------
@app.route("/armador-pc")
@requiere_rol()
def armador_pc():
    datos = cargar()
    prods = datos["productos"]
    cpus, rams, gpus, psus, gabinetes, ssds = [], [], [], [], [], []
    for p in prods:
        cl = especificaciones_producto(p).get("clave_tipo", "")
        if cl == "cpu":
            cpus.append(p)
        elif cl == "ram":
            rams.append(p)
        elif cl == "gpu":
            gpus.append(p)
        elif cl == "psu":
            psus.append(p)
        elif cl == "gabinete":
            gabinetes.append(p)
        elif cl == "ssd":
            ssds.append(p)
    return render_template(
        "armador.html",
        cpus=cpus, rams=rams, gpus=gpus, psus=psus, gabinetes=gabinetes, ssds=ssds,
    )


@app.post("/armador-pc/agregar")
@requiere_rol("comprador")
def armador_pc_agregar():
    pids = []
    for k in ("cpu", "ram", "ssd", "gpu", "psu", "gabinete"):
        val = request.form.get(k, "").strip()
        if val.isdigit():
            pids.append(int(val))
    if not pids:
        flash("Selecciona al menos un componente para agregar al carrito.", "aviso")
        return redirect(url_for("armador_pc"))
    datos = cargar()
    c = carrito_sesion()
    agregados = 0
    for pid in pids:
        prod = logica.buscar_producto(datos, pid)
        if prod and prod["stock"] > 0:
            c[pid] = min(c.get(pid, 0) + 1, prod["stock"])
            agregados += 1
    guardar_carrito(c)
    flash(f"Combo armado: {agregados} componente(s) agregados al carrito.", "ok")
    return redirect(url_for("carrito"))


@app.route("/comparador")
@requiere_rol()
def comparador():
    datos = cargar()
    raw = request.args.get("ids", "")
    ids = [int(x) for x in raw.split(",") if x.strip().isdigit()][:3]
    seleccionados = [p for p in datos["productos"] if p["id"] in ids]
    return render_template("comparador.html", seleccionados=seleccionados, todos=datos["productos"], ids=ids)


@app.route("/recomendador", methods=["GET", "POST"])
@requiere_rol()
def recomendador():
    datos = cargar()
    uso = request.values.get("uso", "gaming")
    presupuesto = request.values.get("presupuesto", "25000")
    formato = request.values.get("formato", "indiferente")
    recomendados = []
    if request.method == "POST" or request.args.get("uso"):
        try:
            max_p = float(presupuesto)
        except ValueError:
            max_p = 25000.0
        candidatos = []
        for p in datos["productos"]:
            if p["stock"] <= 0:
                continue
            sp = especificaciones_producto(p)
            cl = sp.get("clave_tipo", "")
            nom = p["nombre"].lower()
            if formato == "portatil" and "laptop" not in nom and cl != "laptop":
                continue
            if formato == "escritorio" and ("laptop" in nom or cl == "laptop"):
                continue
            score = 0
            razon = []
            if p["precio"] <= max_p:
                score += 40
                razon.append("dentro de tu presupuesto")
            elif p["precio"] <= max_p * 1.2:
                score += 15
                razon.append("cercano a tu presupuesto")
            if uso == "gaming" and (p["categoria"] == "Compus Gaming" or cl == "gpu" or "rtx" in nom):
                score += 50
                razon.append("alto rendimiento gráfico para gaming")
            elif uso == "ingenieria" and ("workstation" in nom or "cad" in nom or "i7" in nom or "ryzen" in nom):
                score += 50
                razon.append("potencia ideal para CAD, ingeniería y cálculo")
            elif uso == "estudio" and (p["categoria"] in ("Computadoras", "Software", "Mobiliario") or p["precio"] <= 15000):
                score += 45
                razon.append("equilibrio ideal para clases, oficina y tareas")
            elif uso == "creacion" and ("32gb" in nom or "rtx" in nom or "ssd" in nom or p["categoria"] == "Compus Gaming"):
                score += 48
                razon.append("fluidez para edición, diseño y multitarea")
            if score > 0:
                candidatos.append((score, p, " · ".join(razon).capitalize() or "Excelente relación costo-beneficio"))
        candidatos.sort(key=lambda x: (x[0], -abs(x[1]["precio"] - max_p * 0.8)), reverse=True)
        recomendados = [{"prod": p, "razon": r} for _, p, r in candidatos[:3]]
    return render_template("recomendador.html", uso=uso, presupuesto=presupuesto, formato=formato, recomendados=recomendados)


@app.route("/cotizador", methods=["GET", "POST"])
@requiere_rol()
def cotizador():
    datos = cargar()
    lista_txt = ""
    perfil = request.form.get("perfil", "Escuela")
    if perfil not in PERFILES_CLIENTE:
        perfil = "Escuela"
    items_cot = []
    totales_cot = None
    if request.method == "POST":
        lista_txt = request.form.get("lista", "").strip()[:1000]
        if lista_txt:
            carrito_sim = {}
            partes = re.split(r"[,;\n]+", lista_txt)
            for parte in partes:
                parte_l = parte.strip().lower()
                if not parte_l:
                    continue
                m_cant = re.search(r"\b(\d{1,2})\b", parte_l)
                cant = int(m_cant.group(1)) if m_cant else 1
                palabras = [w for w in re.split(r"\W+", parte_l) if len(w) >= 3 and not w.isdigit()]
                mejor = None
                mejor_sc = 0
                for p in datos["productos"]:
                    if p["stock"] <= 0:
                        continue
                    txt_p = f"{p['nombre']} {p['categoria']} {especificaciones_producto(p).get('especs', '')}".lower()
                    sc = sum(1 for w in palabras if w in txt_p)
                    if "autocad" in parte_l and ("cad" in txt_p or "workstation" in txt_p):
                        sc += 2
                    if "laptop" in parte_l and "laptop" in txt_p:
                        sc += 2
                    if sc > mejor_sc:
                        mejor_sc = sc
                        mejor = p
                if mejor:
                    carrito_sim[mejor["id"]] = min(mejor["stock"], carrito_sim.get(mejor["id"], 0) + max(1, cant))
            if carrito_sim:
                items_cot, sub, desc, iva, tot = logica.calcular_totales(datos, carrito_sim, perfil)
                totales_cot = {"subtotal": sub, "descuento": desc, "iva": iva, "total": tot}
                session["ultima_cotizacion"] = {str(k): v for k, v in carrito_sim.items()}
                session["perfil"] = perfil
    return render_template(
        "cotizador.html",
        lista_txt=lista_txt,
        perfil=perfil,
        perfiles=[(p, logica.etiqueta_perfil(p)) for p in PERFILES_CLIENTE],
        items_cot=items_cot,
        totales_cot=totales_cot,
    )


@app.post("/cotizador/agregar")
@requiere_rol("comprador")
def cotizador_agregar():
    cot = session.get("ultima_cotizacion") or {}
    if not cot:
        flash("Genera una cotización primero.", "aviso")
        return redirect(url_for("cotizador"))
    c = carrito_sesion()
    for k, v in cot.items():
        if str(k).isdigit():
            c[int(k)] = c.get(int(k), 0) + int(v)
    guardar_carrito(c)
    flash("Cotización agregada al carrito.", "ok")
    return redirect(url_for("carrito"))


@app.route("/trade-in", methods=["GET", "POST"])
@requiere_rol()
def trade_in():
    estimacion = None
    if request.method == "POST":
        tipo = request.form.get("tipo", "laptop")
        antiguedad = request.form.get("antiguedad", "1-2")
        condicion = request.form.get("condicion", "buena")
        base_vals = {"laptop": 9500, "pc": 10500, "gpu": 5500, "smartphone": 4200}
        ant_mult = {"<1": 0.75, "1-2": 0.55, "3-4": 0.35, "5+": 0.18}
        cond_mult = {"nueva": 1.0, "buena": 0.82, "detalles": 0.55}
        credito = round(base_vals.get(tipo, 6000) * ant_mult.get(antiguedad, 0.4) * cond_mult.get(condicion, 0.7), -1)
        estimacion = {
            "tipo": tipo,
            "antiguedad": antiguedad,
            "condicion": condicion,
            "credito": credito,
            "folio": f"TI-{secrets.token_hex(3).upper()}",
        }
    return render_template("tradein.html", estimacion=estimacion)


# ---------------------------------------------------------------------------
# Exportar CSV (Excel) y Modo Sucursal (POS) para el Vendedor
# ---------------------------------------------------------------------------
@app.route("/vendedor/exportar/pedidos.csv")
@requiere_rol("vendedor")
def vendedor_exportar_pedidos():
    datos = cargar()
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["ID", "Fecha", "Cliente", "Cuenta", "Perfil", "Pago", "Subtotal", "Descuento", "IVA", "Total", "Estado", "Artículos"])
    for p in datos.get("pedidos", []):
        arts = "; ".join(f"{it['cantidad']}x {it['nombre']}" for it in p.get("items", []))
        w.writerow([p.get("id"), p.get("fecha"), p.get("cliente"), p.get("usuario", ""), p.get("perfil"), p.get("pago"), p.get("subtotal"), p.get("descuento"), p.get("iva"), p.get("total"), p.get("estado"), arts])
    return Response(buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=pedidos_mt.csv"})


@app.route("/vendedor/exportar/productos.csv")
@requiere_rol("vendedor")
def vendedor_exportar_productos():
    datos = cargar()
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["ID", "Nombre", "Categoría", "Precio", "Descuento %", "Stock", "Especificaciones"])
    for pr in datos.get("productos", []):
        w.writerow([pr.get("id"), pr.get("nombre"), pr.get("categoria"), pr.get("precio"), pr.get("descuento", 0), pr.get("stock"), pr.get("especs", "")])
    return Response(buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=productos_mt.csv"})


@app.route("/vendedor/sucursal")
@requiere_rol("vendedor")
def vendedor_sucursal():
    datos = cargar()
    return render_template(
        "vendedor_sucursal.html",
        productos=datos["productos"],
        perfiles=[(p, logica.etiqueta_perfil(p)) for p in PERFILES_CLIENTE],
        metodos=METODOS_PAGO,
    )


@app.post("/vendedor/sucursal/cobrar")
@requiere_rol("vendedor")
def vendedor_sucursal_cobrar():
    cliente = request.form.get("cliente", "Venta en Sucursal").strip()[:80]
    perfil = request.form.get("perfil", "General")
    perfil = perfil if perfil in PERFILES_CLIENTE else "General"
    pago = request.form.get("pago", "Efectivo")
    pago = pago if pago in METODOS_PAGO else "Efectivo"
    raw_items = request.form.get("items_json", "{}")
    try:
        parsed = json.loads(raw_items)
        carrito_pos = {int(k): int(v) for k, v in parsed.items() if str(k).isdigit() and int(v) > 0}
    except Exception:
        carrito_pos = {}
    if not carrito_pos:
        flash("Agrega al menos un producto al ticket de sucursal.", "aviso")
        return redirect(url_for("vendedor_sucursal"))
    with _cerrojo:
        datos = cargar()
        try:
            ped, _ = logica.crear_pedido(datos, carrito_pos, cliente, perfil, pago)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("vendedor_sucursal"))
        ped["estado"] = "Entregado"
        ped["historial_estados"].append({"estado": "Entregado", "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")})
        ped["datos_pago"] = {"canal": "Sucursal POS"}
        guardar_almacenamiento(datos)
    flash(f"Venta en sucursal #{ped['id']} cobrada por {logica.dinero(ped['total'])}.", "ok")
    return redirect(url_for("pedido", pid=ped["id"]))


@app.errorhandler(404)
@app.errorhandler(403)
@app.errorhandler(400)
def error(e):
    return render_template("error.html", e=e), e.code


if __name__ == "__main__":
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    port = int(os.environ.get("MT_PORT", 443 if SSL_CONTEXT else 80))
    app.run(host=host, port=port, debug=False, ssl_context=SSL_CONTEXT)
