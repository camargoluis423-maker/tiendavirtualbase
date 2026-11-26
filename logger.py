import os
from datetime import datetime
from config import LOG_FILE, LOGS_DIR


def registrar_evento(nivel: str, mensaje: str) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{marca}] [{nivel.upper()}] {mensaje}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as archivo:
        archivo.write(linea)