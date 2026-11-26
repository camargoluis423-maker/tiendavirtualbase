import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FOTOS_DIR = os.path.join(DATA_DIR, "fotos")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")   # cotizaciones y tickets .txt

DB_FILE = os.path.join(DATA_DIR, "tienda_mt.json")
LOG_FILE = os.path.join(LOGS_DIR, "actividad.log")

# Las tres primeras son los apartados principales de la tienda (COM-1)
SECCIONES = {
    "Computadoras": "Para la escuela, la oficina y el negocio",
    "Compus Gaming": "Rendimiento para jugar, diseñar y crear",
    "Componentes": "Arma o mejora tu propio equipo",
}
CATEGORIAS = ["Computadoras", "Compus Gaming", "Componentes", "Equipo", "Software", "Mobiliario"]

PERFILES_CLIENTE = {
    "Estudiante": 0.10,   # 10% descuento académico
    "Escuela": 0.12,      # 12% descuento institucional para escuelas
    "Ingeniero": 0.05,    # 5% descuento profesional
    "Empresa": 0.08,      # 8% descuento empresarial
    "General": 0.00,
}

ESTADOS_PEDIDO = [
    "Pendiente",
    "Preparando",
    "Enviado",
    "Entregado",
    "Cancelado",
]

METODOS_PAGO = [
    "Tarjeta",
    "Transferencia bancaria",
    "Efectivo",
    "Contra entrega",
]
PAGO_NOTA = "Pago en modo de prueba (sandbox) o contra entrega: no se cobra nada real."
WHATSAPP = os.environ.get("MT_WHATSAPP", "5212245550000")

CUPONES = {
    "REGRESO10": {"pct": 10, "desc": "10% de descuento de bienvenida / regreso"},
    "MT15": {"pct": 15, "desc": "15% de descuento especial M&T"},
    "ESCUELA20": {"pct": 20, "desc": "20% de descuento para instituciones"},
    "GAMER5": {"pct": 5, "desc": "5% extra en hardware y setups"},
}
ENVIO_GRATIS_MIN = 5000.0
PUNTOS_TASA = 0.02  # 2% de cada compra se convierte en saldo de puntos de lealtad

TASA_IVA = 0.16
STOCK_BAJO = 2          # <= este valor se considera "stock bajo"
MONEDA = "$"
NOMBRE_TIENDA = "M&T · COM-1"
ESLOGAN = "Computadoras · Gaming · Componentes"

# --- Identidad visual corporativa M&T (Azul tecnológico, Verde esmeralda y tonos cálidos) ---
COLORES = {
    "marino": "#0d3b66",      # Azul naval profundo corporativo M&T
    "marino_2": "#1b4965",    # Azul acero elegante
    "acento": "#2a9d8f",      # Verde azulado / esmeralda fresco
    "acento_osc": "#1e6f5c",
    "violeta": "#6b705c",
    "ambar": "#f4a261",       # Tono cálido ámbar / terracota suave
    "rojo": "#e76f51",        # Cálido coral / terracota
    "verde": "#28a745",       # Verde éxito / crecimiento
    "fondo": "#f8f9fa",       # Fondo cálido claro y limpio
    "tarjeta": "#ffffff",     # Tarjeta blanca impecable
    "borde": "#e9ecef",       # Borde sutil
    "texto": "#212529",       # Texto legible y contrastado
    "texto_suave": "#6c757d",
}

# Color y símbolo por categoría (colores equilibrados en azul, verde y tonos cálidos)
CATEGORIA_ESTILO = {
    "Computadoras": {"color": "#0077b6", "icono": "\u2328"},   # Azul tecnológico
    "Compus Gaming": {"color": "#e76f51", "icono": "\u2726"},  # Coral cálido enérgico
    "Componentes": {"color": "#2a9d8f", "icono": "\u2699"},    # Verde esmeralda M&T
    "Equipo": {"color": "#457b9d", "icono": "\u2328"},         # Azul cobalto
    "Software": {"color": "#588157", "icono": "\u2699"},       # Verde oliva suave
    "Mobiliario": {"color": "#e9c46a", "icono": "\u2756"},     # Dorado cálido
}

ESTADO_COLORES = {
    "Pendiente": "#f59e0b",
    "Preparando": "#6366f1",
    "Enviado": "#0ea5e9",
    "Entregado": "#16a34a",
    "Cancelado": "#dc2626",
}

DATOS_INICIALES = {
    "next_prod_id": 5,
    "next_pedido_id": 1,
    "productos": [
        {
            "id": 1,
            "nombre": "Laptop Workstation 16GB RAM / SSD 512GB",
            "categoria": "Equipo",
            "precio": 17500.0,
            "stock": 4,
            "foto": "",
        },
        {
            "id": 2,
            "nombre": "Licencia Suite CAD y Simulación (1 año)",
            "categoria": "Software",
            "precio": 2800.0,
            "stock": 7,
            "foto": "",
        },
        {
            "id": 3,
            "nombre": "Silla Ergonómica de Malla Alta Densidad",
            "categoria": "Mobiliario",
            "precio": 3950.0,
            "stock": 2,
            "foto": "",
        },
        {
            "id": 4,
            "nombre": "Escritorio en L para Estación Dual",
            "categoria": "Mobiliario",
            "precio": 4600.0,
            "stock": 0,
            "foto": "",
        },
    ],
    "pedidos": [],
}