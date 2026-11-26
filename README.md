# M&T · COM-1 — Tienda Virtual de Soluciones PC (GUI)

Sistema de escritorio desarrollado en **Python** con interfaz gráfica en **Tkinter / ttk**, diseñado para la gestión integral de catálogo, punto de venta (POS), control de inventario y seguimiento de pedidos comerciales para clientes del sector tecnológico, estudiantil y corporativo.

---

## 🚀 Características Principales

1. **Tienda, Carrito y Punto de Pago (POS):**
   - Vitrina visual de productos con soporte para imágenes (`Pillow`).
   - Búsqueda en tiempo real y filtro dinámico por categorías (*Equipo, Software, Mobiliario*).
   - Perfiles de cliente con descuento automático en cascada:
     - **Estudiante:** 10% de descuento.
     - **Empresa:** 8% de descuento.
     - **Ingeniero:** 5% de descuento.
     - **General:** Sin descuento adicional.
   - Cálculo automático de Subtotal, Descuento, **IVA (16%)** y Total neto.
   - Exportación de **Cotizaciones oficiales** en formato `.txt`.

2. **Catálogo de Productos (CRUD):**
   - Alta, edición, visualización y eliminación de productos.
   - Búsqueda por nombre o ID y filtro por categorías.
   - Importación de fotos de productos con almacenamiento relativo y seguro en `data/fotos/`.

3. **Gestión de Stock y Alertas en Tiempo Real:**
   - Semáforo de existencias: *Disponible*, *Stock bajo (<= 2)* y *AGOTADO*.
   - Banner superior dinámico con alertas rojas inmediatas si algún producto se agota.
   - Filtro rápido por estado de existencias.
   - Botones de ajuste rápido (+1, +5, +10) y reabastecimiento manual.

4. **Panel del Vendedor y Dashboard Comercial:**
   - **Métricas comerciales (KPIs):** Ventas netas totales, cantidad de pedidos, pedidos activos en proceso y ticket promedio.
   - Filtros de pedidos por estado (`Pendiente`, `Preparando`, `Enviado`, `Entregado`, `Cancelado`) y buscador por cliente.
   - **Ventana modal de detalle completo de pedido.**
   - **Regla de negocio para cancelaciones:** Si un pedido se cancela, el sistema permite reintegrar el stock al inventario automáticamente; si se reactiva, valida que existan unidades suficientes.
   - Generación de **Tickets / Comprobantes de Venta** en `.txt`.

5. **Persistencia y Auditoría Segura:**
   - MariaDB como base principal; respaldo auxiliar local JSON con copia `.bak`.
   - Bitácora completa de eventos y transacciones en `logs/actividad.log`.

---

## 🎨 Novedades de esta versión

- **Interfaz renovada:** tema propio (marino + turquesa), logo, tarjetas de producto con color e icono por categoría, etiquetas de *Agotado / Quedan N*, tablas con colores por estado y barra de estado inferior.
- **Vitrina adaptable:** las tarjetas se reacomodan en 1, 2, 3… columnas según el ancho de la ventana, con scroll de rueda y chips de categoría.
- **Carrito y pago rediseñados:** el panel siempre muestra totales y botón de compra; al pagar aparece un recibo con vista previa del ticket.
- **Inventario con resumen:** contadores clicables (todos / disponibles / bajo / agotados) y barra de nivel por producto.
- **Panel del vendedor:** KPIs en tarjetas, barra de distribución de pedidos por estado y detalle de pedido con insignia de estado.
- **Catálogo con miniaturas** y vista previa de la foto; la imagen solo se copia a `data/fotos/` al guardar (ya no quedan fotos huérfanas).
- **Versión web completa** (Flask) con el mismo diseño, carrito por sesión, compra que descuenta stock y descarga de ticket.
- **Reglas de negocio compartidas** en `logica.py` (escritorio y web calculan igual).

### Correcciones importantes

- Cotizaciones y tickets ya no se guardan en la carpeta desde donde se ejecuta: van a `exports/`, con nombre ordenado por fecha.
- Se muestra el perfil con su descuento en el selector (antes la lista de etiquetas se calculaba pero no se usaba).
- Importes redondeados a centavos; IVA y porcentajes tomados de `config.py` en vez de estar escritos a mano.
- Al reactivar un pedido cancelado sin existencias suficientes se conserva el estado cancelado y el selector vuelve a su valor.
- La aplicación requiere MariaDB para leer y guardar; el JSON se conserva solo como respaldo y no se usa como sustituto si falla la conexión.
- Web: ya no se expone `data/` completo (JSON y `.bak`) como archivos estáticos; solo `/fotos/`. Se eliminó `/api/pedidos` (datos de clientes sin autenticación), se agregó protección CSRF, clave de sesión estable y cada navegador solo ve sus propios pedidos.

---

## 🛠️ Instalación y Ejecución

### Requisitos previos
- **Python 3.10 o superior** (probado en Python 3.13).
- **Pillow** (opcional, para visualización de fotografías en miniatura).
- **Flask** (solo si usarás la versión web).

### Pasos para iniciar

1. Clona o descarga la carpeta del proyecto:
   ```bash
   cd mt_tienda_gui
   ```

2. (Recomendado) Instalar dependencias para soporte de imágenes:
   ```bash
   pip install -r requirements.txt
   ```

3. Ejecutar la aplicación de escritorio:
   ```bash
   python app.py
   ```

4. (Opcional) Ejecutar la versión web y abrir http://localhost:
   ```bash
   python web_app.py          # solo tu equipo
   python web_app.py --lan    # visible en tu red local
   ```
   Escritorio y web usan MariaDB como fuente principal. `data/tienda_mt.json` se conserva únicamente como respaldo; si MariaDB no está disponible, la aplicación se detiene y no cambia a JSON.

### Preparar MariaDB (requerido)

1. Con MariaDB iniciado, abre el monitor usando la ruta instalada en tu equipo:
   ```powershell
   & "C:\Program Files\MariaDB 13.1\bin\mysql.exe" -u root -p
   ```
2. Dentro del monitor crea las tablas del proyecto y verifica que aparezcan:
   ```sql
   source C:/Users/Camar/Downloads/mt_tienda_gui/database_schema.sql;
   SHOW TABLES;
   SELECT COUNT(*) FROM productos;
   ```
   Crea un usuario dedicado para la aplicación (elige una contraseña propia):
   ```sql
   CREATE USER 'mt_app'@'localhost' IDENTIFIED BY 'PON_AQUI_UNA_CLAVE_LARGA';
   GRANT SELECT, INSERT, UPDATE, DELETE ON tienda_mt.* TO 'mt_app'@'localhost';
   ```
3. Para ejecutar la tienda, configura las variables en la misma ventana de PowerShell con esa contraseña:
   ```powershell
   $env:DB_HOST = "localhost"
   $env:DB_PORT = "3306"
   $env:DB_USER = "mt_app"
   $env:DB_PASSWORD = "<contraseña-configurada-para-mt_app>"
   $env:DB_NAME = "tienda_mt"
   python web_app.py
   ```

   En el primer arranque, si la tabla `productos` está vacía, la aplicación migra a MariaDB el catálogo, las cuentas y los pedidos del JSON existente. Después MariaDB será la fuente de lectura y escritura; el JSON solo se actualiza como copia auxiliar. Si la conexión o el esquema falla, la aplicación se detiene con un error y no carga ese respaldo.

Atajos de la app de escritorio: `Ctrl+1…4` cambia de pestaña, `F5` actualiza, `Supr` quita del carrito.

### HTTPS y protección de cuentas

La versión web activa HTTPS cuando se configuran un certificado TLS y su clave privada. En PowerShell:

```powershell
$env:MT_SSL_CERT = "C:\certificados\tienda.crt"
$env:MT_SSL_KEY = "C:\certificados\tienda.key"
$env:MT_SELLER_PASSWORD = "usa-una-frase-larga-y-unica"
python web_app.py
```

Con HTTPS, el puerto predeterminado es 443 y la dirección es `https://localhost`. Para usar `--lan`, el certificado debe corresponder al nombre o IP con que se conectan los otros dispositivos. Usa un certificado emitido para ese nombre; los certificados autofirmados sirven para desarrollo local, pero el navegador mostrará una advertencia. Mantén la clave privada fuera del repositorio. Si TLS termina en un proxy inverso de confianza, configura también `MT_TRUSTED_PROXY=1` y `MT_SECURE_COOKIES=1`.

Las contraseñas nuevas deben tener de 12 a 128 caracteres. El vendedor inicial solo se crea si `MT_SELLER_PASSWORD` está configurada con una contraseña de esa longitud; los compradores pueden registrarse desde la tienda. Para reemplazar las contraseñas de demostración de cuentas existentes, configura `MT_SELLER_PASSWORD` y/o `MT_BUYER_PASSWORD` con contraseñas nuevas de al menos 12 caracteres y reinicia la aplicación. Los intentos fallidos de inicio de sesión se bloquean durante 15 minutos después de cinco fallos para la misma cuenta y dirección IP.

---

## 📁 Estructura del Proyecto

```text
mt_tienda_gui/
├── app.py                # Interfaz de escritorio (Tkinter)
├── web_app.py            # Versión web (Flask)
├── logica.py             # Reglas de negocio: totales, pedidos, tickets (compartido)
├── config.py             # Parámetros, perfiles, IVA, colores y estilos
├── storage.py            # Persistencia MariaDB, respaldo JSON y gestión de fotos
├── logger.py             # Registro de auditoría cronológica
├── templates/            # Plantillas web (base, index, producto, carrito, pedido, error)
├── static/style.css      # Estilos de la versión web
├── requirements.txt
├── data/
│   ├── tienda_mt.json    # Respaldo auxiliar; MariaDB es la fuente principal
│   └── fotos/            # Imágenes de los artículos
├── exports/              # Cotizaciones y tickets .txt (se crea sola)
└── logs/actividad.log    # Historial de operaciones
```
