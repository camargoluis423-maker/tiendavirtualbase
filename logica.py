"""Reglas de negocio compartidas por la app de escritorio y la versión web.

Aquí no hay nada de interfaz: solo cálculos, validaciones y formato de
documentos, de modo que ambas interfaces se comporten exactamente igual.
"""
import os
from datetime import datetime

from config import (
    EXPORT_DIR,
    MONEDA,
    PERFILES_CLIENTE,
    STOCK_BAJO,
    TASA_IVA,
)

ANCHO = 52


def dinero(valor: float) -> str:
    return f"{MONEDA}{valor:,.2f}"


def buscar_producto(datos: dict, prod_id: int):
    return next((p for p in datos.get("productos", []) if p["id"] == prod_id), None)


def buscar_pedido(datos: dict, pedido_id: int):
    return next((p for p in datos.get("pedidos", []) if p["id"] == pedido_id), None)


def estado_stock(stock: int) -> str:
    """Devuelve 'agotado', 'bajo' o 'ok'."""
    if stock <= 0:
        return "agotado"
    if stock <= STOCK_BAJO:
        return "bajo"
    return "ok"


def etiqueta_perfil(perfil: str) -> str:
    desc = PERFILES_CLIENTE.get(perfil, 0.0)
    return f"{perfil} ({round(desc * 100)}% desc.)" if desc > 0 else f"{perfil} (sin desc.)"


def precio_con_oferta(prod: dict) -> float:
    """Precio unitario aplicando el descuento general del producto (si tiene)."""
    precio = float(prod.get("precio", 0) or 0)
    desc_pct = max(0.0, min(95.0, float(prod.get("descuento", 0) or 0)))
    return round(precio * (1.0 - desc_pct / 100.0), 2)


def tasa_descuento_perfil(prod: dict, perfil: str) -> float:
    """Devuelve la tasa (0..1) de descuento por perfil para un producto."""
    personalizados = prod.get("descuentos_perfil") or {}
    if perfil in personalizados and personalizados[perfil] is not None:
        return max(0.0, min(0.95, float(personalizados[perfil]) / 100.0))
    return PERFILES_CLIENTE.get(perfil, 0.0)


def calcular_totales(datos: dict, carrito: dict, perfil: str, cupon_pct: float = 0.0, puntos_usar: float = 0.0):
    """Calcula líneas y totales. `carrito` es {producto_id: cantidad}.

    Ajusta el carrito en sitio: quita productos eliminados/agotados y recorta
    cantidades que superen el stock. Devuelve (items, subtotal, descuento, iva, total).
    """
    items = []
    subtotal = 0.0
    descuento = 0.0
    for pid, cant in list(carrito.items()):
        prod = buscar_producto(datos, pid)
        if not prod or prod["stock"] <= 0 or cant <= 0:
            del carrito[pid]
            continue
        if cant > prod["stock"]:
            cant = carrito[pid] = prod["stock"]
        precio_unit = precio_con_oferta(prod)
        importe = round(precio_unit * cant, 2)
        subtotal += importe
        descuento += round(importe * tasa_descuento_perfil(prod, perfil), 2)
        items.append(
            {
                "producto_id": prod["id"],
                "nombre": prod["nombre"],
                "categoria": prod["categoria"],
                "cantidad": cant,
                "precio": precio_unit,
                "precio_original": prod["precio"],
                "descuento_prod": float(prod.get("descuento", 0) or 0),
                "importe": importe,
            }
        )
    subtotal = round(subtotal, 2)
    descuento_cupon = round(max(0.0, subtotal - descuento) * max(0.0, min(90.0, float(cupon_pct or 0))) / 100.0, 2)
    descuento_total = round(descuento + descuento_cupon, 2)
    base_iva = max(0.0, subtotal - descuento_total)
    iva = round(base_iva * TASA_IVA, 2)
    total_antes_puntos = round(base_iva + iva, 2)
    puntos_aplicados = round(min(max(0.0, float(puntos_usar or 0)), total_antes_puntos), 2)
    total = round(total_antes_puntos - puntos_aplicados, 2)
    return items, subtotal, round(descuento_total + puntos_aplicados, 2), iva, total


def crear_pedido(datos: dict, carrito: dict, cliente: str, perfil: str, pago: str, cupon_pct: float = 0.0, puntos_usar: float = 0.0):
    """Valida existencias, descuenta stock y registra el pedido.

    Devuelve (pedido, agotados) o lanza ValueError con un mensaje legible.
    El llamador es responsable de guardar `datos`.
    """
    items, subtotal, descuento, iva, total = calcular_totales(datos, carrito, perfil, cupon_pct=cupon_pct, puntos_usar=puntos_usar)
    if not items:
        raise ValueError("El carrito está vacío o sus productos ya no tienen existencias.")

    agotados = []
    for it in items:
        prod = buscar_producto(datos, it["producto_id"])
        prod["stock"] -= it["cantidad"]
        if prod["stock"] == 0:
            agotados.append(prod["nombre"])

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    pedido = {
        "id": datos.get("next_pedido_id", 1),
        "fecha": ahora,
        "cliente": cliente.strip() or "Cliente Regional",
        "perfil": perfil,
        "pago": pago,
        "items": items,
        "subtotal": subtotal,
        "descuento": descuento,
        "iva": iva,
        "total": total,
        "estado": "Pendiente",
        "historial_estados": [{"estado": "Pendiente", "fecha": ahora}],
        "stock_reintegrado": False,
    }
    datos["next_pedido_id"] = pedido["id"] + 1
    datos.setdefault("pedidos", []).insert(0, pedido)
    return pedido, agotados


# ----------------------------------------------------------------------
# Documentos de texto
# ----------------------------------------------------------------------
def _linea(char="="):
    return char * ANCHO + "\n"


def texto_cotizacion(items, subtotal, descuento, iva, total, cliente, perfil) -> str:
    out = [_linea(), "COTIZACIÓN M&T · COM-1".center(ANCHO) + "\n", _linea()]
    out.append(f"Fecha:   {datetime.now():%Y-%m-%d %H:%M}\n")
    out.append(f"Cliente: {cliente.strip() or 'Cliente Regional'}\n")
    out.append(f"Perfil:  {etiqueta_perfil(perfil)}\n")
    out.append(_linea("-"))
    for it in items:
        out.append(f"{it['nombre']}\n")
        out.append(f"   {it['cantidad']} x {dinero(it['precio'])} = {dinero(it['importe'])}\n")
    out.append(_linea("-"))
    out.append(_totales(subtotal, descuento, iva, total, "TOTAL"))
    out.append(_linea())
    out.append("Cotización informativa, sujeta a existencias.".center(ANCHO) + "\n")
    return "".join(out)


def texto_ticket(ped: dict) -> str:
    out = [_linea(), "COMPROBANTE DE VENTA — M&T · COM-1".center(ANCHO) + "\n", _linea()]
    out.append(f"Pedido:  #{ped['id']}\n")
    out.append(f"Fecha:   {ped.get('fecha', '-')}\n")
    out.append(f"Cliente: {ped.get('cliente', 'General')}\n")
    out.append(f"Perfil:  {etiqueta_perfil(ped.get('perfil', 'General'))}\n")
    out.append(f"Pago:    {ped.get('pago', '-')}\n")
    out.append(f"Estado:  {ped.get('estado', 'Pendiente')}\n")
    out.append(_linea("-"))
    for it in ped.get("items", []):
        out.append(f"{it['nombre']}\n")
        out.append(f"   {it['cantidad']} x {dinero(it['precio'])} = {dinero(it['importe'])}\n")
    out.append(_linea("-"))
    out.append(
        _totales(
            ped.get("subtotal", 0.0),
            ped.get("descuento", 0.0),
            ped.get("iva", 0.0),
            ped.get("total", 0.0),
            "TOTAL PAGADO",
        )
    )
    out.append(_linea())
    out.append("¡Gracias por su compra en M&T Soluciones!".center(ANCHO) + "\n")
    return "".join(out)


def _totales(subtotal, descuento, iva, total, etiqueta_total):
    def fila(txt, val):
        return f"{txt:<{ANCHO - 16}}{val:>16}\n"

    return (
        fila("Subtotal:", dinero(subtotal))
        + fila("Descuento:", "-" + dinero(descuento))
        + fila(f"IVA ({round(TASA_IVA * 100)}%):", dinero(iva))
        + fila(etiqueta_total + ":", dinero(total))
    )


def guardar_documento(prefijo: str, contenido: str) -> str:
    """Guarda un .txt en la carpeta exports/ y devuelve la ruta completa."""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    nombre = f"{prefijo}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    ruta = os.path.join(EXPORT_DIR, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)
    return ruta
