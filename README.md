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

## Instalación y ejecución

Guía para Windows y PowerShell. La aplicación de escritorio y la versión web usan MariaDB como base principal. Si MariaDB no está disponible, la aplicación se detiene; `data/tienda_mt.json` se conserva solo como respaldo auxiliar.

### Requisitos

- Windows 10 u 11.
- Python 3.10 o superior.
- MariaDB Server instalado y en ejecución.

Las dependencias (Flask, PyMySQL, cryptography y Pillow) se instalan desde `requirements.txt`.

### 1. Instalar dependencias de Python

Abre PowerShell y entra a la carpeta del proyecto:

```powershell
Set-Location "C:\Users\Camar\Downloads\mt_tienda_gui"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

Si PowerShell impide activar el entorno virtual, ejecuta `\.venv\Scripts\python.exe -m pip install -r requirements.txt` y usa ese Python para los siguientes pasos.

### 2. Crear la base de datos y el usuario de la tienda

Inicia el servicio MariaDB desde **Servicios** de Windows. Abre el cliente SQL (la ruta puede variar según la versión instalada):

```powershell
& "C:\Program Files\MariaDB 13.1\bin\mysql.exe" -u root -p
```

Escribe la contraseña de `root`. En el prompt de MariaDB crea la base y un usuario dedicado. Cambia `PON_UNA_CLAVE_LARGA` por una contraseña propia y consérvala:

```sql
CREATE DATABASE IF NOT EXISTS tienda_mt
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'mt_app'@'localhost'
  IDENTIFIED BY 'PON_UNA_CLAVE_LARGA';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, REFERENCES
  ON tienda_mt.* TO 'mt_app'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

La aplicación crea y actualiza las tablas automáticamente al iniciar, usando `database_schema.sql`. Para eso `mt_app` requiere los permisos `CREATE` y `ALTER`; no necesitas ejecutar el archivo SQL manualmente.

### 3. Configurar la conexión y la cuenta vendedora

En la misma ventana de PowerShell donde ejecutarás la tienda, establece la conexión. Reemplaza las contraseñas de ejemplo por las que elegiste:

```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "3306"
$env:DB_USER = "mt_app"
$env:DB_PASSWORD = "PON_UNA_CLAVE_LARGA"
$env:DB_NAME = "tienda_mt"
$env:MT_SELLER_PASSWORD = "frase-segura-de-al-menos-12-caracteres"
```

Si aún no hay cuentas, se crea el vendedor inicial con usuario `vendedor@mtcom1.mx` y la contraseña de `MT_SELLER_PASSWORD`. Los compradores pueden registrarse desde la página de acceso.

En el primer inicio, si MariaDB no tiene productos, la aplicación importa productos, usuarios y pedidos de `data/tienda_mt.json` cuando ese archivo contiene datos. Si la tabla `productos` ya tiene registros, MariaDB se conserva y no se mezcla con el JSON. Después MariaDB es la única fuente de lectura y escritura; el JSON queda como respaldo auxiliar.

### 4. Iniciar la tienda

Para la versión web local, usa un puerto alto para no requerir permisos de administrador:

```powershell
$env:MT_PORT = "8443"
py web_app.py
```

Abre `https://127.0.0.1:8443` o `https://localhost:8443`. En el primer inicio se genera un certificado local en `data/tls/`; el navegador advertirá que es autofirmado. Para usar un certificado propio, configura `MT_SSL_CERT` y `MT_SSL_KEY` con sus rutas antes de iniciar.

Para iniciar la aplicación de escritorio, desde la misma ventana y con las variables `DB_*` configuradas ejecuta:

```powershell
py app.py
```

Atajos de escritorio: `Ctrl+1…4` cambia de pestaña, `F5` actualiza y `Supr` quita un artículo del carrito.

Para que otros equipos de tu red accedan, inicia con `py web_app.py --lan` y configura un certificado válido para el nombre o la IP de acceso. El certificado local generado para `localhost` es solo para este equipo.

### Cuentas y sesiones

Comprador y vendedor pueden iniciar sesión en pestañas distintas del mismo navegador. El catálogo se puede consultar sin iniciar sesión; agregar productos al carrito y comprar requiere una cuenta de comprador. La administración requiere una cuenta de vendedor.

Las contraseñas nuevas deben tener entre 12 y 128 caracteres. Cinco intentos fallidos para la misma cuenta e IP bloquean temporalmente el acceso durante 15 minutos. Para actualizar la contraseña de una cuenta semilla existente, configura `MT_SELLER_PASSWORD` o `MT_BUYER_PASSWORD` con una nueva contraseña de al menos 12 caracteres y reinicia la aplicación.

### Solución rápida de problemas

- `Access denied for user`: revisa `DB_USER`, `DB_PASSWORD` y que el usuario tenga permisos sobre `tienda_mt`.
- No conecta a `localhost:3306`: confirma que MariaDB esté iniciado y que `DB_PORT` sea correcto.
- No se crean tablas: revisa que `mt_app` tenga permisos `CREATE` y `ALTER`; el esquema se aplica automáticamente al iniciar.
- El navegador advierte sobre HTTPS: es normal con el certificado local autofirmado. Usa `https://localhost:8443` o `https://127.0.0.1:8443`.
- Los datos no se guardan: confirma que ejecutas la app desde la misma PowerShell donde definiste las variables `DB_*` y revisa `logs/actividad.log`.

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
