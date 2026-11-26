"""M&T · COM-1 — Tienda Virtual de Soluciones PC (interfaz de escritorio, Tkinter).

Ejecutar:  python app.py
"""
import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import logica
from config import (
    CATEGORIA_ESTILO,
    CATEGORIAS,
    COLORES as C,
    ESLOGAN,
    ESTADO_COLORES,
    ESTADOS_PEDIDO,
    EXPORT_DIR,
    METODOS_PAGO,
    NOMBRE_TIENDA,
    PERFILES_CLIENTE,
    STOCK_BAJO,
    TASA_IVA,
)
from logger import registrar_evento
from storage import (
    guardar_almacenamiento,
    importar_foto_producto,
    inicializar_almacenamiento,
    obtener_ruta_foto,
)

try:
    from PIL import Image, ImageOps, ImageTk

    PIL_DISPONIBLE = True
except ImportError:  # la app funciona sin fotos reales
    PIL_DISPONIBLE = False

ANCHO_TARJETA = 226          # ancho útil de cada tarjeta de producto
ALTO_FOTO = 132
ANCHO_CARRITO = 430          # panel derecho de la pestaña de tienda


def mezclar(hex_color: str, con: str = "#ffffff", t: float = 0.85) -> str:
    """Mezcla dos colores #rrggbb; t=0.85 => 85 % del segundo color (tinte suave)."""
    a = [int(hex_color[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(con[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * (1 - t) + y * t):02x}" for x, y in zip(a, b))


class TiendaMTApp:
    # ------------------------------------------------------------------
    # CONSTRUCCIÓN
    # ------------------------------------------------------------------
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{NOMBRE_TIENDA} — Tienda Virtual de Soluciones PC")
        ancho = min(1320, max(1000, root.winfo_screenwidth() - 80))
        alto = min(820, max(720, root.winfo_screenheight() - 60))
        self.root.geometry(f"{ancho}x{alto}")
        self.root.minsize(1000, 720)
        self.root.configure(bg=C["fondo"])

        self.datos = inicializar_almacenamiento()
        self.carrito = {}                 # {producto_id: cantidad}
        self.id_producto_edicion = None
        self.foto_actual = ""             # nombre de archivo ya guardado en data/fotos
        self.foto_pendiente = ""          # ruta elegida que aún no se copia al guardar
        self._cache_fotos = {}
        self._tarjetas = []
        self._etiquetas_en_carrito = {}
        self._cols_vitrina = 0
        self._fotos_tabla = []

        self._elegir_fuentes()
        self._configurar_estilos()
        self._construir_encabezado()
        self._construir_barra_estado()   # se empaqueta antes del notebook para no quedar recortada
        self._construir_notebook()
        self._atajos()
        self.refrescar_todo()
        self._tic_reloj()

    def _elegir_fuentes(self):
        disponibles = set(tkfont.families())
        for fam in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Ubuntu", "Cantarell", "DejaVu Sans", "Arial"):
            if fam in disponibles:
                self.fam = fam
                break
        else:
            self.fam = "TkDefaultFont"
        self.fam_mono = next(
            (f for f in ("Consolas", "Menlo", "DejaVu Sans Mono", "Courier New") if f in disponibles),
            "TkFixedFont",
        )

    def f(self, tam=10, negrita=False):
        return (self.fam, tam, "bold" if negrita else "normal")

    # ------------------------------------------------------------------
    # ESTILOS
    # ------------------------------------------------------------------
    def _configurar_estilos(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        self.style = s
        f = self.f
        self.root.option_add("*TCombobox*Listbox.font", f(10))
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["acento_osc"])

        s.configure(".", background=C["fondo"], foreground=C["texto"], font=f(10))
        s.configure("TFrame", background=C["fondo"])
        s.configure("Card.TFrame", background=C["tarjeta"])
        s.configure("TLabel", background=C["fondo"], foreground=C["texto"])
        s.configure("Card.TLabel", background=C["tarjeta"])
        s.configure("Muted.TLabel", foreground=C["texto_suave"], font=f(9))
        s.configure("CardMuted.TLabel", background=C["tarjeta"], foreground=C["texto_suave"], font=f(9))
        s.configure("H1.TLabel", font=f(15, True))
        s.configure("H2.TLabel", font=f(12, True))
        s.configure("CardH.TLabel", background=C["tarjeta"], font=f(12, True))
        s.configure("Total.TLabel", background=C["tarjeta"], foreground=C["acento_osc"], font=f(17, True))

        # Notebook
        s.configure("TNotebook", background=C["fondo"], borderwidth=0, tabmargins=(14, 8, 14, 0))
        s.configure(
            "TNotebook.Tab",
            padding=(20, 9),
            background="#dbe4ee",
            foreground=C["texto_suave"],
            font=f(10, True),
            borderwidth=0,
        )
        s.map(
            "TNotebook.Tab",
            background=[("selected", C["tarjeta"]), ("active", "#e8eef5")],
            foreground=[("selected", C["acento_osc"])],
        )

        # Botones
        s.configure("TButton", width=-1, padding=(12, 7), relief="flat", borderwidth=0, background="#e2e8f0", font=f(10))
        s.map("TButton", background=[("active", "#cbd5e1"), ("disabled", "#eef2f6")],
              foreground=[("disabled", "#94a3b8")])
        s.configure("Primario.TButton", background=C["acento_osc"], foreground="#ffffff", font=f(10, True))
        s.map("Primario.TButton", background=[("active", C["acento"]), ("disabled", "#cbd5e1")],
              foreground=[("disabled", "#f1f5f9")])
        s.configure("Peligro.TButton", background="#fee2e2", foreground="#b91c1c")
        s.map("Peligro.TButton", background=[("active", "#fecaca")])
        s.configure("Chip.TButton", padding=(14, 6), background=C["tarjeta"], foreground=C["texto"],
                    borderwidth=1, bordercolor=C["borde"], lightcolor=C["borde"], darkcolor=C["borde"])
        s.map("Chip.TButton", background=[("active", "#e0f2f1")])
        s.configure("ChipOn.TButton", padding=(14, 6), background=C["marino"], foreground="#ffffff",
                    font=f(10, True))
        s.map("ChipOn.TButton", background=[("active", C["marino_2"])])
        s.configure("Mini.TButton", padding=(8, 4), font=f(9))

        # Campos
        for w in ("TEntry", "TCombobox", "TSpinbox"):
            s.configure(w, padding=6, fieldbackground="#ffffff", bordercolor=C["borde"],
                        lightcolor=C["borde"], darkcolor=C["borde"])
        s.map("TEntry", bordercolor=[("focus", C["acento"])], lightcolor=[("focus", C["acento"])])
        s.map("TCombobox", fieldbackground=[("readonly", "#ffffff")], bordercolor=[("focus", C["acento"])])
        s.configure("TScrollbar", background="#cbd5e1", troughcolor=C["fondo"], borderwidth=0, arrowsize=14)

        # Tablas
        s.configure("Treeview", rowheight=32, font=f(10), background="#ffffff", fieldbackground="#ffffff",
                    borderwidth=0)
        s.configure("Treeview.Heading", font=f(9, True), background=C["marino_2"], foreground="#ffffff",
                    relief="flat", padding=(8, 7))
        s.map("Treeview.Heading", background=[("active", C["marino"])])
        s.map("Treeview", background=[("selected", "#ccfbf1")], foreground=[("selected", C["texto"])])
        s.configure("Cat.Treeview", rowheight=52)
        s.configure("Cart.Treeview", rowheight=28)
        s.configure("Sep.TSeparator", background=C["borde"])

    # --- utilidades de UI ------------------------------------------------
    def _card(self, parent, **kw):
        return tk.Frame(parent, bg=C["tarjeta"], highlightbackground=C["borde"], highlightthickness=1, **kw)

    def _tabla(self, parent, columnas, altura=10, estilo="Treeview", **kw):
        """Treeview con scrollbar vertical. columnas = [(id, ancho, ancla, estirar)]"""
        cont = tk.Frame(parent, bg=C["tarjeta"], highlightbackground=C["borde"], highlightthickness=1)
        tree = ttk.Treeview(cont, columns=[c[0] for c in columnas], height=altura, style=estilo, **kw)
        sb = ttk.Scrollbar(cont, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        for col, ancho, ancla, estirar in columnas:
            tree.heading(col, text=col)
            tree.column(col, width=ancho, anchor=ancla, stretch=estirar, minwidth=40)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return cont, tree

    def _modal(self, titulo, ancho, alto):
        m = tk.Toplevel(self.root)
        m.title(titulo)
        m.configure(bg=C["fondo"])
        m.transient(self.root)
        x = self.root.winfo_rootx() + (self.root.winfo_width() - ancho) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - alto) // 3
        m.geometry(f"{ancho}x{alto}+{max(x, 0)}+{max(y, 0)}")
        m.minsize(ancho - 80, alto - 100)
        m.bind("<Escape>", lambda _e: m.destroy())
        m.grab_set()
        m.focus_set()
        return m

    def _insignia(self, parent, texto, color, bg=None):
        return tk.Label(parent, text=f" {texto} ", bg=bg or mezclar(color), fg=color, font=self.f(9, True), padx=4)

    def _abrir_carpeta(self, ruta):
        try:
            if sys.platform.startswith("win"):
                os.startfile(ruta)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", ruta])
            else:
                subprocess.Popen(["xdg-open", ruta])
        except Exception as e:
            messagebox.showwarning("No se pudo abrir", str(e))

    def _avisar_archivo(self, titulo, ruta):
        if messagebox.askyesno(titulo, f"Archivo guardado en:\n{ruta}\n\n¿Abrir la carpeta?"):
            self._abrir_carpeta(os.path.dirname(ruta))

    def _atajos(self):
        for i in range(4):
            self.root.bind(f"<Control-Key-{i + 1}>", lambda _e, i=i: self.notebook.select(i))
        self.root.bind("<F5>", lambda _e: self.refrescar_todo())

    # ------------------------------------------------------------------
    # ENCABEZADO, ALERTA GLOBAL Y BARRA DE ESTADO
    # ------------------------------------------------------------------
    def _construir_encabezado(self):
        barra = tk.Frame(self.root, bg=C["marino"], padx=18, pady=6)
        barra.pack(fill="x")

        logo = tk.Canvas(barra, width=46, height=46, bg=C["marino"], highlightthickness=0)
        logo.create_oval(2, 2, 44, 44, fill=C["acento"], outline="")
        logo.create_oval(9, 9, 44, 44, fill=C["violeta"], outline="", stipple="gray50")
        logo.create_text(23, 23, text="M&T", fill="#ffffff", font=self.f(11, True))
        logo.pack(side="left")

        bloque = tk.Frame(barra, bg=C["marino"])
        bloque.pack(side="left", padx=(12, 0))
        tk.Label(bloque, text=NOMBRE_TIENDA + "  Tienda Virtual", font=self.f(16, True),
                 fg="#ffffff", bg=C["marino"]).pack(anchor="w")
        tk.Label(bloque, text=ESLOGAN + "  ·  Ventas e inventario", font=self.f(9),
                 fg="#5eead4", bg=C["marino"]).pack(anchor="w")

        # Resumen del carrito (clic para ir a pagar)
        self.btn_carrito_top = tk.Label(barra, text="", font=self.f(10, True), fg=C["marino"],
                                        bg="#5eead4", padx=14, pady=6, cursor="hand2")
        self.btn_carrito_top.pack(side="right")
        self.btn_carrito_top.bind("<Button-1>", lambda _e: self.notebook.select(0))

        self.lbl_alerta_stock = tk.Label(self.root, text="", font=self.f(9, True), padx=18, pady=4,
                                         anchor="w", cursor="hand2")
        self.lbl_alerta_stock.pack(fill="x")
        self.lbl_alerta_stock.bind("<Button-1>", lambda _e: self.notebook.select(2))

    def _construir_barra_estado(self):
        barra = tk.Frame(self.root, bg="#dbe4ee", padx=14, pady=3)
        barra.pack(side="bottom", fill="x")
        self.lbl_estado = tk.Label(barra, text="", bg="#dbe4ee", fg=C["texto_suave"], font=self.f(9))
        self.lbl_estado.pack(side="left")
        self.lbl_reloj = tk.Label(barra, text="", bg="#dbe4ee", fg=C["texto_suave"], font=self.f(9))
        self.lbl_reloj.pack(side="right")
        tk.Label(barra, text="Ctrl+1…4 cambia de pestaña  ·  F5 actualiza     ", bg="#dbe4ee",
                 fg="#94a3b8", font=self.f(9)).pack(side="right")

    def _tic_reloj(self):
        self.lbl_reloj.config(text=datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
        self.root.after(1000, self._tic_reloj)

    def _construir_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, pady=(6, 0))

        nombres = [
            ("tab_carrito_pago", "  Tienda y Pago  "),
            ("tab_catalogo", "  Catálogo  "),
            ("tab_stock", "  Inventario  "),
            ("tab_vendedor", "  Panel del Vendedor  "),
        ]
        for attr, texto in nombres:
            frame = ttk.Frame(self.notebook)
            setattr(self, attr, frame)
            self.notebook.add(frame, text=texto)

        self._ui_carrito_pago()
        self._ui_catalogo()
        self._ui_stock()
        self._ui_vendedor()

    def _buscar_producto(self, prod_id: int):
        return logica.buscar_producto(self.datos, prod_id)

    # ------------------------------------------------------------------
    # FOTOS
    # ------------------------------------------------------------------
    def _foto_tk(self, ref, ancho, alto, fondo="#ffffff", ruta_directa=None):
        """Miniatura centrada (sin deformar) sobre un fondo de color. None si no hay imagen."""
        if not PIL_DISPONIBLE:
            return None
        ruta = ruta_directa or obtener_ruta_foto(ref)
        if not ruta or not os.path.exists(ruta):
            return None
        clave = (ruta, ancho, alto, fondo, os.path.getmtime(ruta))
        if clave in self._cache_fotos:
            return self._cache_fotos[clave]
        try:
            img = ImageOps.exif_transpose(Image.open(ruta)).convert("RGBA")
            img = ImageOps.contain(img, (ancho - 10, alto - 10))
            lienzo = Image.new("RGBA", (ancho, alto), fondo)
            lienzo.alpha_composite(img, ((ancho - img.width) // 2, (alto - img.height) // 2))
            foto = ImageTk.PhotoImage(lienzo.convert("RGB"))
        except Exception as e:
            registrar_evento("ERROR", f"No se pudo cargar la imagen {ruta}: {e}")
            return None
        self._cache_fotos[clave] = foto
        return foto

    @staticmethod
    def _estilo_cat(cat):
        return CATEGORIA_ESTILO.get(cat, {"color": "#64748b", "icono": "▣"})

    # ------------------------------------------------------------------
    # PESTAÑA 1: TIENDA, CARRITO Y PAGO
    # ------------------------------------------------------------------
    def _ui_carrito_pago(self):
        tab = self.tab_carrito_pago
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        # ---------- Vitrina (izquierda) ----------
        izq = ttk.Frame(tab, padding=(16, 12, 8, 8))
        izq.grid(row=0, column=0, sticky="nsew")

        fila = ttk.Frame(izq)
        fila.pack(fill="x")
        ttk.Label(fila, text="Vitrina", style="H1.TLabel").pack(side="left")
        self.lbl_conteo_vitrina = ttk.Label(fila, text="", style="Muted.TLabel")
        self.lbl_conteo_vitrina.pack(side="left", padx=(10, 0), pady=(5, 0))

        caja_busca = ttk.Frame(fila)
        caja_busca.pack(side="right")
        self.var_buscar = tk.StringVar()
        self.var_buscar.trace_add("write", lambda *_a: self.refrescar_vitrina())
        ttk.Label(caja_busca, text="Buscar").pack(side="left", padx=(0, 6))
        self.entry_buscar = ttk.Entry(caja_busca, textvariable=self.var_buscar, width=24)
        self.entry_buscar.pack(side="left")
        ttk.Button(caja_busca, text="✕", width=3, style="Mini.TButton",
                   command=lambda: self.var_buscar.set("")).pack(side="left", padx=(4, 0))

        # Chips de categoría
        self.var_filtro_cat = tk.StringVar(value="Todas")
        chips = ttk.Frame(izq)
        chips.pack(fill="x", pady=(10, 8))
        self.chips = {}
        for cat in ["Todas"] + CATEGORIAS:
            icono = "" if cat == "Todas" else self._estilo_cat(cat)["icono"] + "  "
            b = ttk.Button(chips, text=f"{icono}{cat}", style="Chip.TButton",
                           command=lambda c=cat: self._elegir_categoria(c))
            b.pack(side="left", padx=(0, 8))
            self.chips[cat] = b

        # Lienzo con scroll y columnas adaptables
        cont = ttk.Frame(izq)
        cont.pack(fill="both", expand=True)
        self.canvas_vitrina = tk.Canvas(cont, highlightthickness=0, bg=C["fondo"])
        scroll = ttk.Scrollbar(cont, orient="vertical", command=self.canvas_vitrina.yview)
        self.frame_tarjetas = tk.Frame(self.canvas_vitrina, bg=C["fondo"])
        self._ventana_vitrina = self.canvas_vitrina.create_window((0, 0), window=self.frame_tarjetas, anchor="nw")
        self.canvas_vitrina.configure(yscrollcommand=scroll.set)
        self.frame_tarjetas.bind(
            "<Configure>", lambda _e: self.canvas_vitrina.configure(scrollregion=self.canvas_vitrina.bbox("all"))
        )
        self.canvas_vitrina.bind("<Configure>", self._al_redimensionar_vitrina)
        self.canvas_vitrina.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for w in (self.canvas_vitrina, self.frame_tarjetas):
            w.bind("<Enter>", self._activar_rueda)
            w.bind("<Leave>", self._desactivar_rueda)

        # ---------- Carrito (derecha) ----------
        der = self._card(tab, width=ANCHO_CARRITO)
        der.grid(row=0, column=1, sticky="ns", padx=(4, 14), pady=12)
        der.pack_propagate(False)
        inner = tk.Frame(der, bg=C["tarjeta"], padx=14, pady=10)
        inner.pack(fill="both", expand=True)

        cab = tk.Frame(inner, bg=C["tarjeta"])
        cab.pack(fill="x")
        ttk.Label(cab, text="Tu carrito", style="CardH.TLabel").pack(side="left")
        self.lbl_items_carrito = ttk.Label(cab, text="", style="CardMuted.TLabel")
        self.lbl_items_carrito.pack(side="right")

        bajo = tk.Frame(inner, bg=C["tarjeta"])
        bajo.pack(side="bottom", fill="x")
        cont_c, self.tree_carrito = self._tabla(
            inner,
            [("Producto", 180, "w", True), ("Cant.", 58, "center", False), ("Subtotal", 100, "e", False)],
            altura=4, estilo="Cart.Treeview",
            show="headings",
            selectmode="browse",
        )
        cont_c.pack(fill="both", expand=True, pady=(6, 6))
        self.tree_carrito.bind("<Delete>", lambda _e: self.quitar_carrito())
        self.tree_carrito.bind("<Double-1>", lambda _e: self.sumar_carrito())
        self.tree_carrito.tag_configure("vacio", foreground=C["texto_suave"])

        fila_acc = tk.Frame(bajo, bg=C["tarjeta"])
        fila_acc.pack(fill="x")
        for txt, cmd, est in [
            ("+1", self.sumar_carrito, "Mini.TButton"),
            ("−1", self.restar_carrito, "Mini.TButton"),
            ("Quitar", self.quitar_carrito, "Mini.TButton"),
            ("Vaciar", self.vaciar_carrito, "Peligro.TButton"),
        ]:
            b = ttk.Button(fila_acc, text=txt, command=cmd, style=est)
            b.pack(side="left", expand=True, fill="x", padx=2)

        ttk.Separator(bajo, orient="horizontal").pack(fill="x", pady=(6, 6))

        form = tk.Frame(bajo, bg=C["tarjeta"])
        form.pack(fill="x")
        form.columnconfigure((0, 1), weight=1, uniform="f")
        fila_cli = tk.Frame(form, bg=C["tarjeta"])
        fila_cli.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        fila_cli.columnconfigure(1, weight=1)
        ttk.Label(fila_cli, text="Cliente", style="CardMuted.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.var_cliente = tk.StringVar(value="Cliente Regional")
        ttk.Entry(fila_cli, textvariable=self.var_cliente).grid(row=0, column=1, sticky="ew")

        ttk.Label(form, text="Perfil (descuento)", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(form, text="Método de pago", style="CardMuted.TLabel").grid(row=2, column=1, sticky="w", padx=(8, 0))
        self.var_perfil = tk.StringVar(value="General")
        self.cb_perfil = ttk.Combobox(form, values=[logica.etiqueta_perfil(p) for p in PERFILES_CLIENTE],
                                      state="readonly")
        self.cb_perfil.current(list(PERFILES_CLIENTE).index("General"))
        self.cb_perfil.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self.cb_perfil.bind("<<ComboboxSelected>>", self._cambio_perfil)
        self.var_pago = tk.StringVar(value=METODOS_PAGO[0])
        ttk.Combobox(form, textvariable=self.var_pago, values=METODOS_PAGO, state="readonly").grid(
            row=3, column=1, sticky="ew", padx=(8, 0), pady=(2, 0))

        # Totales
        tot = tk.Frame(bajo, bg=C["tarjeta"])
        tot.pack(fill="x", pady=(8, 6))
        tot.columnconfigure(1, weight=1)
        self.lbl_tot = {}
        for r, (clave, txt) in enumerate([("sub", "Subtotal"), ("desc", "Descuento"), ("iva", f"IVA ({round(TASA_IVA * 100)}%)")]):
            ttk.Label(tot, text=txt, style="CardMuted.TLabel").grid(row=r, column=0, sticky="w")
            lbl = ttk.Label(tot, text="", style="Card.TLabel")
            lbl.grid(row=r, column=1, sticky="e")
            self.lbl_tot[clave] = lbl
        ttk.Separator(tot, orient="horizontal").grid(row=3, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Label(tot, text="TOTAL", style="CardH.TLabel").grid(row=4, column=0, sticky="w")
        self.lbl_tot["total"] = ttk.Label(tot, text="", style="Total.TLabel")
        self.lbl_tot["total"].grid(row=4, column=1, sticky="e")

        fila_pago = tk.Frame(bajo, bg=C["tarjeta"])
        fila_pago.pack(fill="x")
        self.btn_comprar = ttk.Button(fila_pago, text="Completar compra", style="Primario.TButton",
                                      command=self.completar_compra)
        self.btn_comprar.pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(fila_pago, text="Cotizar .txt", command=self.exportar_cotizacion).pack(
            side="left", padx=(6, 0), ipady=4)

    def _cambio_perfil(self, _e=None):
        idx = self.cb_perfil.current()
        self.var_perfil.set(list(PERFILES_CLIENTE)[idx])
        self.refrescar_carrito()

    def _elegir_categoria(self, cat):
        self.var_filtro_cat.set(cat)
        for c, b in self.chips.items():
            b.configure(style="ChipOn.TButton" if c == cat else "Chip.TButton")
        self.refrescar_vitrina()

    # --- rueda del ratón ------------------------------------------------
    def _activar_rueda(self, _e=None):
        self.root.bind_all("<MouseWheel>", self._rueda)
        self.root.bind_all("<Button-4>", self._rueda)
        self.root.bind_all("<Button-5>", self._rueda)

    def _desactivar_rueda(self, _e=None):
        # El puntero puede seguir sobre la vitrina (pasó a un hijo): solo se desactiva al salir de verdad
        x, y = self.root.winfo_pointerxy()
        w = self.root.winfo_containing(x, y)
        while w is not None:
            if w is self.canvas_vitrina:
                return
            w = w.master
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.unbind_all(ev)

    def _rueda(self, e):
        bbox = self.canvas_vitrina.bbox("all")
        if not bbox or bbox[3] <= self.canvas_vitrina.winfo_height():
            return  # todo cabe: no hay nada que desplazar
        if e.num == 4:
            paso = -2
        elif e.num == 5:
            paso = 2
        else:
            paso = -1 * (1 if e.delta > 0 else -1) * 2
        self.canvas_vitrina.yview_scroll(paso, "units")

    # --- columnas adaptables ----------------------------------------------
    def _al_redimensionar_vitrina(self, e):
        self.canvas_vitrina.itemconfigure(self._ventana_vitrina, width=e.width)
        cols = max(1, e.width // (ANCHO_TARJETA + 34))
        if cols != self._cols_vitrina:
            self._cols_vitrina = cols
            self._acomodar_tarjetas()

    def _acomodar_tarjetas(self):
        cols = max(1, self._cols_vitrina)
        for c in range(12):
            self.frame_tarjetas.columnconfigure(c, weight=1 if c < cols else 0, uniform="col" if c < cols else "")
        for i, card in enumerate(self._tarjetas):
            card.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="n")

    def _hover(self, card):
        def entra(_e):
            card.configure(highlightbackground=C["acento"])

        def sale(_e):
            x, y = card.winfo_pointerxy()
            w = card.winfo_containing(x, y)
            while w is not None and w is not card:
                w = w.master
            if w is None:  # el puntero salió de la tarjeta (no solo pasó a un hijo)
                card.configure(highlightbackground=C["borde"])

        def ligar(w):
            w.bind("<Enter>", entra, add="+")
            w.bind("<Leave>", sale, add="+")
            for h in w.winfo_children():
                ligar(h)

        ligar(card)

    # --- tarjetas -----------------------------------------------------------
    def _crear_tarjeta(self, prod):
        est = self._estilo_cat(prod["categoria"])
        nivel = logica.estado_stock(prod["stock"])
        tinte = mezclar(est["color"], t=0.88)

        card = tk.Frame(self.frame_tarjetas, bg=C["tarjeta"], highlightbackground=C["borde"],
                        highlightthickness=2)
        cv = tk.Canvas(card, width=ANCHO_TARJETA, height=ALTO_FOTO, bg=tinte, highlightthickness=0)
        cv.pack(padx=10, pady=(10, 6))
        foto = self._foto_tk(prod.get("foto", ""), ANCHO_TARJETA, ALTO_FOTO, fondo=tinte)
        if foto:
            cv.create_image(0, 0, image=foto, anchor="nw")
            cv.image = foto  # referencia para que Tk no la libere
        else:
            cv.create_text(ANCHO_TARJETA // 2, ALTO_FOTO // 2, text=est["icono"],
                           fill=mezclar(est["color"], t=0.35), font=(self.fam, 54))
        # pastillas sobre la imagen
        fpil = tkfont.Font(family=self.fam, size=8, weight="bold")
        ancho_cat = fpil.measure(prod["categoria"].upper()) + 14
        cv.create_rectangle(8, 8, 8 + ancho_cat, 28, fill=est["color"], outline="")
        cv.create_text(15, 18, text=prod["categoria"].upper(), fill="#ffffff", anchor="w", font=fpil)
        if nivel != "ok":
            txt, col = ("AGOTADO", C["rojo"]) if nivel == "agotado" else (f"QUEDAN {prod['stock']}", C["ambar"])
            ancho = fpil.measure(txt) + 14
            cv.create_rectangle(ANCHO_TARJETA - 8 - ancho, 8, ANCHO_TARJETA - 8, 28, fill=col, outline="")
            cv.create_text(ANCHO_TARJETA - 8 - ancho // 2, 18, text=txt, fill="#ffffff", font=fpil)

        tk.Label(card, text=prod["nombre"], bg=C["tarjeta"], fg=C["texto"], font=self.f(10, True),
                 wraplength=ANCHO_TARJETA, justify="left", anchor="nw", height=2).pack(fill="x", padx=12)
        fila = tk.Frame(card, bg=C["tarjeta"])
        fila.pack(fill="x", padx=12, pady=(2, 8))
        tk.Label(fila, text=logica.dinero(prod["precio"]), bg=C["tarjeta"], fg=C["acento_osc"],
                 font=self.f(15, True)).pack(side="left")
        en_carrito = tk.Label(fila, text="", bg=C["tarjeta"], fg=C["violeta"], font=self.f(9, True))
        en_carrito.pack(side="right")
        self._etiquetas_en_carrito[prod["id"]] = en_carrito

        ttk.Button(card, text="Agregar al carrito" if nivel != "agotado" else "Sin existencias",
                   style="Primario.TButton", state="normal" if nivel != "agotado" else "disabled",
                   command=lambda pid=prod["id"]: self.agregar_al_carrito(pid)).pack(
            fill="x", padx=12, pady=(0, 12))
        self._hover(card)
        return card

    def refrescar_vitrina(self):
        for w in self.frame_tarjetas.winfo_children():
            w.destroy()
        self._tarjetas = []
        self._etiquetas_en_carrito = {}

        cat = self.var_filtro_cat.get() if hasattr(self, "var_filtro_cat") else "Todas"
        for c, b in self.chips.items():
            b.configure(style="ChipOn.TButton" if c == cat else "Chip.TButton")
        busqueda = self.var_buscar.get().strip().lower()

        filtrados = [
            p for p in self.datos.get("productos", [])
            if (cat == "Todas" or p["categoria"] == cat)
            and (not busqueda or busqueda in p["nombre"].lower() or busqueda in p["categoria"].lower())
        ]
        self.lbl_conteo_vitrina.config(text=f"{len(filtrados)} producto(s)")

        if not filtrados:
            vacio = tk.Frame(self.frame_tarjetas, bg=C["fondo"])
            vacio.grid(row=0, column=0, padx=30, pady=50)
            tk.Label(vacio, text="∅", font=(self.fam, 40), fg="#cbd5e1", bg=C["fondo"]).pack()
            tk.Label(vacio, text="No hay productos con ese filtro", font=self.f(11, True),
                     fg=C["texto_suave"], bg=C["fondo"]).pack()
            tk.Label(vacio, text="Prueba con otra categoría o borra la búsqueda.", font=self.f(9),
                     fg=C["texto_suave"], bg=C["fondo"]).pack()
            return

        self._tarjetas = [self._crear_tarjeta(p) for p in filtrados]
        self._acomodar_tarjetas()
        self._actualizar_marcas_carrito()
        self.canvas_vitrina.yview_moveto(0)

    def _actualizar_marcas_carrito(self):
        for pid, lbl in self._etiquetas_en_carrito.items():
            n = self.carrito.get(pid, 0)
            lbl.config(text=f"✓ {n} en carrito" if n else "")

    # --- carrito ----------------------------------------------------------------
    def agregar_al_carrito(self, prod_id: int):
        prod = self._buscar_producto(prod_id)
        if not prod:
            return
        if prod["stock"] <= 0:
            messagebox.showwarning("Producto agotado", f"'{prod['nombre']}' no tiene existencias.")
            return
        actual = self.carrito.get(prod_id, 0)
        if actual + 1 > prod["stock"]:
            messagebox.showwarning(
                "Stock insuficiente", f"Solo quedan {prod['stock']} unidad(es) de '{prod['nombre']}'.")
            return
        self.carrito[prod_id] = actual + 1
        self.refrescar_carrito()
        if self.tree_carrito.exists(str(prod_id)):
            self.tree_carrito.selection_set(str(prod_id))
            self.tree_carrito.see(str(prod_id))

    def _seleccion_carrito(self):
        sel = self.tree_carrito.selection()
        return int(sel[0]) if sel else None

    def sumar_carrito(self):
        pid = self._seleccion_carrito()
        if pid is not None:
            self.agregar_al_carrito(pid)

    def restar_carrito(self):
        pid = self._seleccion_carrito()
        if pid is None or pid not in self.carrito:
            return
        if self.carrito[pid] > 1:
            self.carrito[pid] -= 1
        else:
            del self.carrito[pid]
        self.refrescar_carrito()
        if pid in self.carrito:
            self.tree_carrito.selection_set(str(pid))

    def quitar_carrito(self):
        pid = self._seleccion_carrito()
        if pid is None:
            return
        self.carrito.pop(pid, None)
        self.refrescar_carrito()

    def vaciar_carrito(self):
        if self.carrito and messagebox.askyesno("Vaciar carrito", "¿Seguro que deseas vaciar el carrito?"):
            self.carrito.clear()
            self.refrescar_carrito()

    def _totales(self):
        return logica.calcular_totales(self.datos, self.carrito, self.var_perfil.get())

    def refrescar_carrito(self):
        seleccion = self._seleccion_carrito()
        self.tree_carrito.delete(*self.tree_carrito.get_children())
        items, subtotal, descuento, iva, total = self._totales()
        for it in items:
            self.tree_carrito.insert("", "end", iid=str(it["producto_id"]),
                                     values=(it["nombre"], it["cantidad"], logica.dinero(it["importe"])))
        if seleccion is not None and self.tree_carrito.exists(str(seleccion)):
            self.tree_carrito.selection_set(str(seleccion))
        if not items:
            self.tree_carrito.insert("", "end", iid="vacio", tags=("vacio",),
                                     values=("Carrito vacío", "", ""))

        n = sum(it["cantidad"] for it in items)
        pct = round(logica.PERFILES_CLIENTE.get(self.var_perfil.get(), 0.0) * 100)
        self.lbl_items_carrito.config(text=f"{n} artículo(s)")
        self.lbl_tot["sub"].config(text=logica.dinero(subtotal))
        self.lbl_tot["desc"].config(
            text=(f"-{logica.dinero(descuento)}  ({pct}%)" if descuento else logica.dinero(0)))
        self.lbl_tot["iva"].config(text=logica.dinero(iva))
        self.lbl_tot["total"].config(text=logica.dinero(total))
        self.btn_comprar.state(["!disabled"] if items else ["disabled"])
        self.btn_carrito_top.config(
            text=f"▣  Carrito: {n}  ·  {logica.dinero(total)}" if n else "▣  Carrito vacío")
        self._actualizar_marcas_carrito()

    def exportar_cotizacion(self):
        items, subtotal, descuento, iva, total = self._totales()
        if not items:
            messagebox.showinfo("Carrito vacío", "Agrega productos para exportar una cotización.")
            return
        contenido = logica.texto_cotizacion(items, subtotal, descuento, iva, total,
                                            self.var_cliente.get(), self.var_perfil.get())
        ruta = logica.guardar_documento("cotizacion_mt", contenido)
        registrar_evento("INFO", f"Cotización exportada a {ruta}.")
        self._avisar_archivo("Cotización guardada", ruta)

    def completar_compra(self):
        if not self.carrito:
            messagebox.showinfo("Carrito vacío", "Agrega al menos un producto para comprar.")
            return
        try:
            pedido, agotados = logica.crear_pedido(
                self.datos, self.carrito, self.var_cliente.get(), self.var_perfil.get(), self.var_pago.get())
        except ValueError as e:
            messagebox.showerror("No se pudo completar", str(e))
            self.refrescar_todo()
            return
        for nombre in agotados:
            registrar_evento("ALERTA", f"Producto agotado tras compra: {nombre}")
        guardar_almacenamiento(self.datos)
        registrar_evento(
            "COMPRA", f"Pedido #{pedido['id']} por ${pedido['total']:,.2f} ({pedido['cliente']}, {pedido['pago']}).")
        self.carrito.clear()
        self.refrescar_todo()
        self._mostrar_recibo(pedido, agotados)

    def _mostrar_recibo(self, pedido, agotados=()):
        m = self._modal(f"Compra completada — Pedido #{pedido['id']}", 520, 640)
        cab = tk.Frame(m, bg=C["verde"], padx=18, pady=12)
        cab.pack(fill="x")
        tk.Label(cab, text="✓  ¡Compra registrada!", font=self.f(14, True), fg="#ffffff", bg=C["verde"]).pack(anchor="w")
        tk.Label(cab, text=f"Pedido #{pedido['id']}  ·  Total {logica.dinero(pedido['total'])}",
                 font=self.f(10), fg="#dcfce7", bg=C["verde"]).pack(anchor="w")
        if agotados:
            tk.Label(m, text="⚠  Se agotaron las existencias de: " + ", ".join(agotados),
                     bg="#fef3c7", fg="#92400e", font=self.f(9, True), wraplength=480, justify="left",
                     padx=14, pady=6, anchor="w").pack(fill="x")
        texto = tk.Text(m, font=(self.fam_mono, 10), relief="flat", bg="#ffffff", padx=14, pady=12,
                        highlightbackground=C["borde"], highlightthickness=1, wrap="none")
        texto.insert("1.0", logica.texto_ticket(pedido))
        texto.config(state="disabled")
        texto.pack(fill="both", expand=True, padx=14, pady=12)
        botones = ttk.Frame(m, padding=(14, 0, 14, 14))
        botones.pack(fill="x")
        ttk.Button(botones, text="Guardar ticket (.txt)",
                   command=lambda: self.exportar_ticket_pedido(pedido["id"])).pack(side="left")
        ttk.Button(botones, text="Seguir comprando", style="Primario.TButton", command=m.destroy).pack(side="right")

    # ------------------------------------------------------------------
    # PESTAÑA 2: CATÁLOGO (CRUD)
    # ------------------------------------------------------------------
    def _ui_catalogo(self):
        tab = self.tab_catalogo
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        izq = ttk.Frame(tab, padding=(16, 12, 8, 12))
        izq.grid(row=0, column=0, sticky="nsew")
        fila = ttk.Frame(izq)
        fila.pack(fill="x", pady=(0, 8))
        ttk.Label(fila, text="Catálogo de productos", style="H1.TLabel").pack(side="left")

        self.var_filtro_cat_admin = tk.StringVar(value="Todas")
        cb = ttk.Combobox(fila, textvariable=self.var_filtro_cat_admin, values=["Todas"] + CATEGORIAS,
                          state="readonly", width=12)
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refrescar_catalogo())
        ttk.Label(fila, text="Categoría").pack(side="right", padx=(0, 6))
        self.var_buscar_cat = tk.StringVar()
        self.var_buscar_cat.trace_add("write", lambda *_a: self.refrescar_catalogo())
        ttk.Entry(fila, textvariable=self.var_buscar_cat, width=20).pack(side="right", padx=(0, 16))
        ttk.Label(fila, text="Buscar").pack(side="right", padx=(0, 6))

        cont, self.tree_cat = self._tabla(
            izq,
            [("ID", 50, "center", False), ("Nombre", 260, "w", True), ("Categoría", 110, "center", False),
             ("Precio", 105, "e", False), ("Stock", 70, "center", False)],
            altura=12, estilo="Cat.Treeview", show="tree headings", selectmode="browse",
        )
        self.tree_cat.heading("#0", text="Foto")
        self.tree_cat.column("#0", width=70, stretch=False, anchor="center")
        self.tree_cat.tag_configure("agotado", background="#fee2e2")
        self.tree_cat.tag_configure("bajo", background="#fef3c7")
        cont.pack(fill="both", expand=True)
        self.tree_cat.bind("<<TreeviewSelect>>", self._on_seleccionar_cat)

        # Formulario
        der = self._card(tab, width=360)
        der.grid(row=0, column=1, sticky="ns", padx=(4, 14), pady=12)
        der.pack_propagate(False)
        inner = tk.Frame(der, bg=C["tarjeta"], padx=16, pady=14)
        inner.pack(fill="both", expand=True)

        self.lbl_modo_form = ttk.Label(inner, text="Nuevo producto", style="CardH.TLabel")
        self.lbl_modo_form.pack(anchor="w")

        self.cv_prev = tk.Canvas(inner, width=326, height=130, bg="#f1f5f9", highlightthickness=0)
        self.cv_prev.pack(pady=(8, 6))

        fila_foto = tk.Frame(inner, bg=C["tarjeta"])
        fila_foto.pack(fill="x", pady=(0, 8))
        ttk.Button(fila_foto, text="Elegir foto…", style="Mini.TButton", command=self._elegir_foto).pack(
            side="left", expand=True, fill="x", padx=(0, 3))
        ttk.Button(fila_foto, text="Quitar foto", style="Mini.TButton", command=self._quitar_foto).pack(
            side="left", expand=True, fill="x", padx=(3, 0))

        def campo(txt):
            ttk.Label(inner, text=txt, style="CardMuted.TLabel").pack(anchor="w")

        campo("Nombre del producto")
        self.var_prod_nombre = tk.StringVar()
        ttk.Entry(inner, textvariable=self.var_prod_nombre).pack(fill="x", pady=(2, 8))
        campo("Categoría")
        self.var_prod_cat = tk.StringVar(value=CATEGORIAS[0])
        ttk.Combobox(inner, textvariable=self.var_prod_cat, values=CATEGORIAS, state="readonly").pack(
            fill="x", pady=(2, 8))
        dos = tk.Frame(inner, bg=C["tarjeta"])
        dos.pack(fill="x", pady=(0, 10))
        dos.columnconfigure((0, 1), weight=1, uniform="c")
        ttk.Label(dos, text="Precio unitario ($)", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(dos, text="Existencias", style="CardMuted.TLabel").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.var_prod_precio = tk.StringVar()
        self.var_prod_stock = tk.StringVar(value="1")
        ttk.Entry(dos, textvariable=self.var_prod_precio).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        ttk.Entry(dos, textvariable=self.var_prod_stock).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(2, 0))

        ttk.Button(inner, text="Guardar producto", style="Primario.TButton", command=self.guardar_producto).pack(
            fill="x", ipady=4)
        ttk.Button(inner, text="Nuevo / limpiar formulario", command=self.limpiar_form_cat).pack(fill="x", pady=(6, 0))
        ttk.Button(inner, text="Eliminar producto seleccionado", style="Peligro.TButton",
                   command=self.eliminar_producto).pack(fill="x", pady=(6, 0))
        self._dibujar_preview()

    def _dibujar_preview(self):
        self.cv_prev.delete("all")
        ruta = self.foto_pendiente or ""
        foto = self._foto_tk(self.foto_actual, 326, 130, fondo="#f1f5f9", ruta_directa=ruta or None)
        if foto:
            self.cv_prev.create_image(0, 0, image=foto, anchor="nw")
            self.cv_prev.image = foto
        else:
            est = self._estilo_cat(self.var_prod_cat.get() if hasattr(self, "var_prod_cat") else "Equipo")
            self.cv_prev.create_text(163, 58, text=est["icono"], fill=mezclar(est["color"], t=0.35), font=(self.fam, 44))
            self.cv_prev.create_text(163, 108, text="Sin foto" if not PIL_DISPONIBLE else "Sin foto · elige una imagen",
                                     fill=C["texto_suave"], font=self.f(9))

    def _elegir_foto(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar foto de producto",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp *.gif"), ("Todos", "*.*")])
        if ruta:
            self.foto_pendiente = ruta  # se copia a data/fotos solo al guardar el producto
            self._dibujar_preview()

    def _quitar_foto(self):
        self.foto_pendiente = ""
        self.foto_actual = ""
        self._dibujar_preview()

    def limpiar_form_cat(self):
        self.id_producto_edicion = None
        self.foto_actual = ""
        self.foto_pendiente = ""
        self.var_prod_nombre.set("")
        self.var_prod_cat.set(CATEGORIAS[0])
        self.var_prod_precio.set("")
        self.var_prod_stock.set("1")
        self.lbl_modo_form.config(text="Nuevo producto")
        self.tree_cat.selection_remove(self.tree_cat.selection())
        self._dibujar_preview()

    def _on_seleccionar_cat(self, _event):
        sel = self.tree_cat.selection()
        if not sel:
            return
        prod = self._buscar_producto(int(sel[0]))
        if not prod:
            return
        self.id_producto_edicion = prod["id"]
        self.var_prod_nombre.set(prod["nombre"])
        self.var_prod_cat.set(prod["categoria"])
        self.var_prod_precio.set(f"{prod['precio']:g}")
        self.var_prod_stock.set(str(prod["stock"]))
        self.foto_actual = prod.get("foto", "")
        self.foto_pendiente = ""
        self.lbl_modo_form.config(text=f"Editando producto #{prod['id']}")
        self._dibujar_preview()

    def guardar_producto(self):
        nombre = self.var_prod_nombre.get().strip()
        categoria = self.var_prod_cat.get()
        if not nombre:
            messagebox.showwarning("Validación", "Ingresa el nombre del producto.")
            return
        try:
            precio = round(float(self.var_prod_precio.get().replace(",", "").replace("$", "")), 2)
            stock = int(self.var_prod_stock.get())
            if precio < 0 or stock < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validación", "El precio debe ser un número >= 0 y las existencias un entero >= 0.")
            return

        foto = self.foto_actual
        if self.foto_pendiente:
            try:
                foto = importar_foto_producto(self.foto_pendiente)
            except OSError as e:
                messagebox.showerror("Foto", f"No se pudo copiar la imagen:\n{e}")
                return
        foto = os.path.basename(foto) if foto else ""

        if self.id_producto_edicion is None:
            pid = self.datos.get("next_prod_id", 1)
            self.datos["next_prod_id"] = pid + 1
            self.datos.setdefault("productos", []).append(
                {"id": pid, "nombre": nombre, "categoria": categoria, "precio": precio, "stock": stock, "foto": foto})
            registrar_evento("CATALOGO", f"Alta de producto: {nombre} ({categoria}, stock={stock}).")
        else:
            prod = self._buscar_producto(self.id_producto_edicion)
            if prod:
                prod.update(nombre=nombre, categoria=categoria, precio=precio, stock=stock, foto=foto)
                registrar_evento("CATALOGO", f"Edición de producto #{prod['id']}: {nombre}.")

        guardar_almacenamiento(self.datos)
        self.limpiar_form_cat()
        self.refrescar_todo()
        if stock == 0:
            registrar_evento("ALERTA", f"Producto guardado con stock 0: {nombre}")
            messagebox.showwarning("Stock agotado", f"'{nombre}' quedó con 0 unidades.")

    def eliminar_producto(self):
        sel = self.tree_cat.selection()
        if not sel:
            messagebox.showinfo("Seleccionar", "Selecciona un producto de la tabla para eliminarlo.")
            return
        pid = int(sel[0])
        prod = self._buscar_producto(pid)
        if not prod:
            return
        if messagebox.askyesno("Confirmar", f"¿Eliminar '{prod['nombre']}' del catálogo?\n"
                                            "Los pedidos anteriores conservan su detalle."):
            self.datos["productos"] = [p for p in self.datos["productos"] if p["id"] != pid]
            self.carrito.pop(pid, None)
            guardar_almacenamiento(self.datos)
            registrar_evento("CATALOGO", f"Eliminado producto: {prod['nombre']}.")
            self.limpiar_form_cat()
            self.refrescar_todo()

    def refrescar_catalogo(self):
        sel = self.tree_cat.selection()
        self.tree_cat.delete(*self.tree_cat.get_children())
        self._fotos_tabla = []
        busqueda = self.var_buscar_cat.get().strip().lower()
        cat_filtro = self.var_filtro_cat_admin.get()
        for p in self.datos.get("productos", []):
            if cat_filtro != "Todas" and p.get("categoria") != cat_filtro:
                continue
            if busqueda and busqueda not in p.get("nombre", "").lower() and busqueda != str(p.get("id")):
                continue
            est = self._estilo_cat(p["categoria"])
            miniatura = self._foto_tk(p.get("foto", ""), 52, 44, fondo=mezclar(est["color"], t=0.88))
            kw = {}
            if miniatura:
                self._fotos_tabla.append(miniatura)
                kw["image"] = miniatura
            nivel = logica.estado_stock(p["stock"])
            self.tree_cat.insert(
                "", "end", iid=str(p["id"]), text="" if miniatura else est["icono"], **kw,
                values=(p["id"], p["nombre"], p["categoria"], logica.dinero(p["precio"]), p["stock"]),
                tags=(nivel,) if nivel != "ok" else ())
        for iid in sel:
            if self.tree_cat.exists(iid):
                self.tree_cat.selection_set(iid)

    # ------------------------------------------------------------------
    # PESTAÑA 3: INVENTARIO
    # ------------------------------------------------------------------
    def _ui_stock(self):
        marco = ttk.Frame(self.tab_stock, padding=(16, 12, 16, 12))
        marco.pack(fill="both", expand=True)

        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        ttk.Label(fila, text="Control de inventario", style="H1.TLabel").pack(side="left")

        # Contadores clicables que filtran la tabla
        self.var_filtro_stock = tk.StringVar(value="Todos")
        resumen = ttk.Frame(marco)
        resumen.pack(fill="x", pady=(10, 10))
        self.tiles_stock = {}
        for clave, titulo, color in [("Todos", "Todos los productos", C["violeta"]),
                                     ("Disponibles", "Disponibles", C["verde"]),
                                     ("Stock bajo", f"Stock bajo (≤ {STOCK_BAJO})", C["ambar"]),
                                     ("Agotados", "Agotados", C["rojo"])]:
            t = tk.Frame(resumen, bg=C["tarjeta"], highlightbackground=C["borde"], highlightthickness=1, cursor="hand2")
            t.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Frame(t, bg=color, width=5).pack(side="left", fill="y")
            cuerpo = tk.Frame(t, bg=C["tarjeta"], padx=12, pady=8)
            cuerpo.pack(side="left", fill="both", expand=True)
            num = tk.Label(cuerpo, text="0", font=self.f(20, True), fg=color, bg=C["tarjeta"])
            num.pack(anchor="w")
            tk.Label(cuerpo, text=titulo, font=self.f(9), fg=C["texto_suave"], bg=C["tarjeta"]).pack(anchor="w")
            for w in (t, cuerpo, num) + tuple(cuerpo.winfo_children()):
                w.bind("<Button-1>", lambda _e, k=clave: self._filtrar_stock(k))
            self.tiles_stock[clave] = (t, num, color)

        barra = ttk.Frame(marco)
        barra.pack(fill="x", pady=(0, 8))
        ttk.Label(barra, text="Buscar").pack(side="left")
        self.var_buscar_stock = tk.StringVar()
        self.var_buscar_stock.trace_add("write", lambda *_a: self.refrescar_stock())
        ttk.Entry(barra, textvariable=self.var_buscar_stock, width=26).pack(side="left", padx=(6, 0))

        pie = tk.Frame(marco, bg=C["tarjeta"], highlightbackground=C["borde"], highlightthickness=1, padx=12, pady=10)
        pie.pack(side="bottom", fill="x", pady=(10, 0))
        cont, self.tree_stock = self._tabla(
            marco,
            [("ID", 50, "center", False), ("Producto", 300, "w", True), ("Categoría", 120, "center", False),
             ("Existencias", 100, "center", False), ("Nivel", 140, "w", False), ("Estado", 150, "w", False)],
            altura=11, show="headings", selectmode="browse")
        cont.pack(fill="both", expand=True)
        self.tree_stock.tag_configure("agotado", background="#fee2e2", foreground="#991b1b")
        self.tree_stock.tag_configure("bajo", background="#fef3c7", foreground="#92400e")

        ttk.Label(pie, text="Cantidad", style="Card.TLabel").pack(side="left")
        self.var_cant_stock = tk.StringVar(value="5")
        ttk.Spinbox(pie, from_=0, to=9999, textvariable=self.var_cant_stock, width=6).pack(side="left", padx=6)
        ttk.Button(pie, text="Reabastecer (+)", style="Primario.TButton",
                   command=lambda: self._modificar_stock(True)).pack(side="left", padx=3)
        ttk.Button(pie, text="Fijar existencias (=)", command=lambda: self._modificar_stock(False)).pack(
            side="left", padx=3)
        ttk.Separator(pie, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Label(pie, text="Atajos", style="CardMuted.TLabel").pack(side="left", padx=(0, 6))
        for n in (1, 5, 10):
            ttk.Button(pie, text=f"+{n}", width=4, style="Mini.TButton",
                       command=lambda n=n: self._ajuste_rapido(n)).pack(side="left", padx=2)

    def _filtrar_stock(self, clave):
        self.var_filtro_stock.set(clave)
        self.refrescar_stock()

    def _ajuste_rapido(self, cant: int):
        self.var_cant_stock.set(str(cant))
        self._modificar_stock(True)

    def _modificar_stock(self, sumar: bool):
        sel = self.tree_stock.selection()
        if not sel:
            messagebox.showinfo("Seleccionar", "Elige un producto en la tabla de inventario.")
            return
        try:
            cant = int(self.var_cant_stock.get())
            if cant < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Dato inválido", "Ingresa un entero igual o mayor a 0.")
            return
        prod = self._buscar_producto(int(sel[0]))
        if not prod:
            return
        prod["stock"] = prod["stock"] + cant if sumar else cant
        guardar_almacenamiento(self.datos)
        registrar_evento("STOCK", f"Stock de '{prod['nombre']}' actualizado a {prod['stock']}.")
        self.refrescar_todo()
        if self.tree_stock.exists(sel[0]):
            self.tree_stock.selection_set(sel[0])
        if prod["stock"] == 0:
            messagebox.showwarning("Producto agotado", f"AVISO: '{prod['nombre']}' quedó agotado (0 existencias).")

    def refrescar_stock(self):
        sel = self.tree_stock.selection()
        self.tree_stock.delete(*self.tree_stock.get_children())
        busqueda = self.var_buscar_stock.get().strip().lower()
        filtro = self.var_filtro_stock.get()
        cuentas = {"Todos": 0, "Disponibles": 0, "Stock bajo": 0, "Agotados": 0}
        agotados, bajos = [], []

        for p in self.datos.get("productos", []):
            nivel = logica.estado_stock(p["stock"])
            cuentas["Todos"] += 1
            if nivel == "agotado":
                cuentas["Agotados"] += 1
                agotados.append(p["nombre"])
                estado = "● AGOTADO"
            elif nivel == "bajo":
                cuentas["Stock bajo"] += 1
                bajos.append(p["nombre"])
                estado = "● Stock bajo"
            else:
                cuentas["Disponibles"] += 1
                estado = "● Disponible"

            if filtro == "Disponibles" and nivel != "ok":
                continue
            if filtro == "Stock bajo" and nivel != "bajo":
                continue
            if filtro == "Agotados" and nivel != "agotado":
                continue
            if busqueda and busqueda not in p["nombre"].lower() and busqueda != str(p["id"]):
                continue
            llenos = min(p["stock"], 10)
            barra = "▮" * llenos + "▯" * (10 - llenos)
            self.tree_stock.insert("", "end", iid=str(p["id"]), tags=(nivel,) if nivel != "ok" else (),
                                   values=(p["id"], p["nombre"], p["categoria"], p["stock"], barra, estado))

        for iid in sel:
            if self.tree_stock.exists(iid):
                self.tree_stock.selection_set(iid)
        for clave, (marco, num, color) in self.tiles_stock.items():
            num.config(text=str(cuentas[clave]))
            marco.configure(highlightbackground=color if clave == filtro else C["borde"],
                            highlightthickness=2 if clave == filtro else 1)

        # Banner global
        if agotados:
            extra = f"  ·  Stock bajo: {', '.join(bajos)}" if bajos else ""
            self.lbl_alerta_stock.config(
                bg="#fee2e2", fg="#991b1b",
                text=f"⚠  {len(agotados)} producto(s) agotado(s): {', '.join(agotados)}{extra}   (clic para ver inventario)")
        elif bajos:
            self.lbl_alerta_stock.config(
                bg="#fef3c7", fg="#92400e",
                text=f"⚠  Stock bajo en: {', '.join(bajos)}   (clic para ver inventario)")
        else:
            self.lbl_alerta_stock.config(bg="#dcfce7", fg="#166534",
                                         text="✓  Stock controlado: todos los productos tienen existencias suficientes.")

    # ------------------------------------------------------------------
    # PESTAÑA 4: PANEL DEL VENDEDOR
    # ------------------------------------------------------------------
    def _ui_vendedor(self):
        marco = ttk.Frame(self.tab_vendedor, padding=(16, 12, 16, 12))
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Panel del vendedor", style="H1.TLabel").pack(anchor="w")

        kpis = ttk.Frame(marco)
        kpis.pack(fill="x", pady=(10, 8))
        self.kpi = {}
        for clave, titulo, color in [("ventas", "Ventas netas", C["acento_osc"]),
                                     ("pedidos", "Pedidos vigentes", C["violeta"]),
                                     ("proceso", "En proceso", C["ambar"]),
                                     ("ticket", "Ticket promedio", "#0ea5e9")]:
            t = tk.Frame(kpis, bg=C["tarjeta"], highlightbackground=C["borde"], highlightthickness=1)
            t.pack(side="left", fill="x", expand=True, padx=(0, 10))
            tk.Frame(t, bg=color, width=5).pack(side="left", fill="y")
            cuerpo = tk.Frame(t, bg=C["tarjeta"], padx=12, pady=8)
            cuerpo.pack(side="left", fill="both", expand=True)
            tk.Label(cuerpo, text=titulo.upper(), font=self.f(8, True), fg=C["texto_suave"], bg=C["tarjeta"]).pack(anchor="w")
            num = tk.Label(cuerpo, text="—", font=self.f(18, True), fg=color, bg=C["tarjeta"])
            num.pack(anchor="w")
            sub = tk.Label(cuerpo, text="", font=self.f(8), fg=C["texto_suave"], bg=C["tarjeta"])
            sub.pack(anchor="w")
            self.kpi[clave] = (num, sub)

        # Barra segmentada: pedidos por estado
        self.cv_dist = tk.Canvas(marco, height=34, bg=C["fondo"], highlightthickness=0)
        self.cv_dist.pack(fill="x", pady=(0, 8))
        self.cv_dist.bind("<Configure>", lambda _e: self._dibujar_distribucion())

        barra = ttk.Frame(marco)
        barra.pack(fill="x", pady=(0, 6))
        ttk.Label(barra, text="Estado").pack(side="left")
        self.var_filtro_pedidos_estado = tk.StringVar(value="Todos")
        cb = ttk.Combobox(barra, textvariable=self.var_filtro_pedidos_estado, values=["Todos"] + ESTADOS_PEDIDO,
                          state="readonly", width=13)
        cb.pack(side="left", padx=(6, 16))
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refrescar_pedidos())
        ttk.Label(barra, text="Cliente").pack(side="left")
        self.var_buscar_ped_cliente = tk.StringVar()
        self.var_buscar_ped_cliente.trace_add("write", lambda *_a: self.refrescar_pedidos())
        ttk.Entry(barra, textvariable=self.var_buscar_ped_cliente, width=24).pack(side="left", padx=6)

        pie = tk.Frame(marco, bg=C["tarjeta"], highlightbackground=C["borde"], highlightthickness=1, padx=12, pady=10)
        pie.pack(side="bottom", fill="x", pady=(10, 0))
        cont, self.tree_pedidos = self._tabla(
            marco,
            [("Pedido", 80, "center", False), ("Fecha", 140, "center", False), ("Cliente", 150, "w", False),
             ("Perfil", 90, "center", False), ("Pago", 130, "center", False), ("Detalle", 260, "w", True),
             ("Total", 110, "e", False), ("Estado", 140, "w", False)],
            altura=8, show="headings", selectmode="browse")
        cont.pack(fill="both", expand=True)
        self.tree_pedidos.tag_configure("Pendiente", background="#fffbeb")
        self.tree_pedidos.tag_configure("Entregado", background="#f0fdf4")
        self.tree_pedidos.tag_configure("Cancelado", foreground="#94a3b8")
        self.tree_pedidos.bind("<Double-1>", lambda _e: self.ver_detalle_pedido())
        self.tree_pedidos.bind("<<TreeviewSelect>>", self._on_seleccionar_pedido)

        ttk.Label(pie, text="Cambiar estado a", style="Card.TLabel").pack(side="left")
        self.var_estado_pedido = tk.StringVar(value=ESTADOS_PEDIDO[1])
        ttk.Combobox(pie, textvariable=self.var_estado_pedido, values=ESTADOS_PEDIDO, state="readonly",
                     width=14).pack(side="left", padx=6)
        ttk.Button(pie, text="Actualizar estado", style="Primario.TButton",
                   command=self.actualizar_estado_pedido).pack(side="left", padx=4)
        ttk.Button(pie, text="Ver detalle", command=self.ver_detalle_pedido).pack(side="left", padx=4)
        ttk.Button(pie, text="Exportar ticket (.txt)", command=self.exportar_ticket_seleccionado).pack(side="right")

    def _on_seleccionar_pedido(self, _e=None):
        sel = self.tree_pedidos.selection()
        if sel:
            ped = logica.buscar_pedido(self.datos, int(sel[0]))
            if ped:
                self.var_estado_pedido.set(ped.get("estado", "Pendiente"))

    def _dibujar_distribucion(self):
        cv = self.cv_dist
        cv.delete("all")
        ancho = max(cv.winfo_width(), 200)
        cuentas = {e: 0 for e in ESTADOS_PEDIDO}
        for p in self.datos.get("pedidos", []):
            cuentas[p.get("estado", "Pendiente")] = cuentas.get(p.get("estado", "Pendiente"), 0) + 1
        total = sum(cuentas.values())
        if not total:
            cv.create_text(0, 17, anchor="w", text="Aún no hay pedidos. Completa una compra para ver la distribución.",
                           fill=C["texto_suave"], font=self.f(9))
            return
        x = 0
        for est in ESTADOS_PEDIDO:
            n = cuentas[est]
            if not n:
                continue
            w = max(4, int((ancho - 2) * n / total))
            cv.create_rectangle(x, 0, x + w, 12, fill=ESTADO_COLORES[est], outline="")
            x += w
        x = 0
        for est in ESTADOS_PEDIDO:
            cv.create_oval(x, 21, x + 9, 30, fill=ESTADO_COLORES[est], outline="")
            t = cv.create_text(x + 14, 26, anchor="w", text=f"{est} {cuentas[est]}", fill=C["texto_suave"], font=self.f(9))
            x = cv.bbox(t)[2] + 18

    def actualizar_estado_pedido(self):
        sel = self.tree_pedidos.selection()
        if not sel:
            messagebox.showinfo("Seleccionar", "Selecciona un pedido en la tabla.")
            return
        oid = int(sel[0])
        nuevo = self.var_estado_pedido.get()
        ped = logica.buscar_pedido(self.datos, oid)
        if not ped:
            return
        anterior = ped.get("estado", "Pendiente")
        if nuevo == anterior:
            messagebox.showinfo("Sin cambios", f"El pedido #{oid} ya está en estado '{nuevo}'.")
            return

        if nuevo == "Cancelado" and not ped.get("stock_reintegrado", False):
            if messagebox.askyesno(
                "Reintegrar stock",
                f"El pedido #{oid} pasará a 'Cancelado'.\n¿Reintegrar las unidades al inventario?"):
                for it in ped.get("items", []):
                    prod = self._buscar_producto(it["producto_id"])
                    if prod:
                        prod["stock"] += it["cantidad"]
                ped["stock_reintegrado"] = True
                registrar_evento("STOCK", f"Reintegrado stock por cancelación de pedido #{oid}.")
        elif anterior == "Cancelado" and ped.get("stock_reintegrado", False):
            faltan = []
            for it in ped.get("items", []):
                prod = self._buscar_producto(it["producto_id"])
                if not prod or prod["stock"] < it["cantidad"]:
                    nombre = prod["nombre"] if prod else it.get("nombre", f"ID {it['producto_id']}")
                    faltan.append(f"{nombre} (requiere {it['cantidad']})")
            if faltan:
                messagebox.showerror(
                    "Stock insuficiente para reactivar",
                    "No se puede reactivar el pedido porque no hay existencias suficientes:\n• " + "\n• ".join(faltan))
                self.var_estado_pedido.set(anterior)
                return
            for it in ped.get("items", []):
                self._buscar_producto(it["producto_id"])["stock"] -= it["cantidad"]
            ped["stock_reintegrado"] = False
            registrar_evento("STOCK", f"Re-deducido stock al reactivar pedido #{oid}.")

        ped["estado"] = nuevo
        guardar_almacenamiento(self.datos)
        registrar_evento("PEDIDO", f"Pedido #{oid} cambió de '{anterior}' a '{nuevo}'.")
        self.refrescar_todo()
        if self.tree_pedidos.exists(str(oid)):
            self.tree_pedidos.selection_set(str(oid))

    def ver_detalle_pedido(self):
        sel = self.tree_pedidos.selection()
        if not sel:
            messagebox.showinfo("Seleccionar", "Selecciona un pedido para ver su detalle.")
            return
        oid = int(sel[0])
        ped = logica.buscar_pedido(self.datos, oid)
        if not ped:
            return
        m = self._modal(f"Pedido #{oid} — {NOMBRE_TIENDA}", 580, 560)
        estado = ped.get("estado", "Pendiente")
        col = ESTADO_COLORES.get(estado, C["texto_suave"])

        cab = tk.Frame(m, bg=C["marino"], padx=18, pady=12)
        cab.pack(fill="x")
        tk.Label(cab, text=f"Pedido #{oid}", font=self.f(15, True), fg="#ffffff", bg=C["marino"]).pack(side="left")
        tk.Label(cab, text=f"  {estado.upper()}  ", font=self.f(9, True), fg="#ffffff", bg=col).pack(side="right")

        info = self._card(m)
        info.pack(fill="x", padx=14, pady=(12, 8))
        g = tk.Frame(info, bg=C["tarjeta"], padx=14, pady=10)
        g.pack(fill="x")
        for i, (et, val) in enumerate([
            ("Fecha y hora", ped.get("fecha", "-")), ("Cliente", ped.get("cliente", "General")),
            ("Perfil", logica.etiqueta_perfil(ped.get("perfil", "General"))), ("Pago", ped.get("pago", "-"))]):
            ttk.Label(g, text=et, style="CardMuted.TLabel").grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(g, text=val, style="Card.TLabel", font=self.f(10, True)).grid(row=i, column=1, sticky="w", padx=14)

        cont, tree = self._tabla(
            m, [("Producto", 230, "w", True), ("Cant.", 50, "center", False),
                ("P. Unit.", 90, "e", False), ("Importe", 95, "e", False)], altura=5, show="headings")
        cont.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        for it in ped.get("items", []):
            tree.insert("", "end", values=(it.get("nombre", ""), it.get("cantidad", 1),
                                           logica.dinero(it.get("precio", 0.0)), logica.dinero(it.get("importe", 0.0))))

        tot = tk.Frame(m, bg=C["fondo"], padx=16)
        tot.pack(fill="x")
        tot.columnconfigure(0, weight=1)
        for r, (et, val, est) in enumerate([
            ("Subtotal", logica.dinero(ped.get("subtotal", 0)), "Muted.TLabel"),
            ("Descuento", "-" + logica.dinero(ped.get("descuento", 0)), "Muted.TLabel"),
            (f"IVA ({round(TASA_IVA * 100)}%)", logica.dinero(ped.get("iva", 0)), "Muted.TLabel")]):
            ttk.Label(tot, text=et, style=est).grid(row=r, column=0, sticky="e", padx=10)
            ttk.Label(tot, text=val, style="TLabel").grid(row=r, column=1, sticky="e")
        ttk.Label(tot, text="TOTAL", style="H2.TLabel").grid(row=3, column=0, sticky="e", padx=10)
        ttk.Label(tot, text=logica.dinero(ped.get("total", 0)), style="H2.TLabel", foreground=C["acento_osc"]).grid(
            row=3, column=1, sticky="e")

        botones = ttk.Frame(m, padding=(14, 10, 14, 14))
        botones.pack(fill="x")
        ttk.Button(botones, text="Generar ticket (.txt)", command=lambda: self.exportar_ticket_pedido(oid)).pack(side="left")
        ttk.Button(botones, text="Cerrar", style="Primario.TButton", command=m.destroy).pack(side="right")

    def exportar_ticket_seleccionado(self):
        sel = self.tree_pedidos.selection()
        if not sel:
            messagebox.showinfo("Seleccionar", "Selecciona un pedido para exportar su ticket.")
            return
        self.exportar_ticket_pedido(int(sel[0]))

    def exportar_ticket_pedido(self, pedido_id: int):
        ped = logica.buscar_pedido(self.datos, pedido_id)
        if not ped:
            return
        ruta = logica.guardar_documento(f"ticket_mt_pedido_{pedido_id}", logica.texto_ticket(ped))
        registrar_evento("INFO", f"Ticket generado para pedido #{pedido_id}: {ruta}")
        self._avisar_archivo("Ticket exportado", ruta)

    def refrescar_pedidos(self):
        sel = self.tree_pedidos.selection()
        self.tree_pedidos.delete(*self.tree_pedidos.get_children())
        filtro = self.var_filtro_pedidos_estado.get()
        busqueda = self.var_buscar_ped_cliente.get().strip().lower()
        pedidos = self.datos.get("pedidos", [])
        ventas, validos, proceso, cancelados = 0.0, 0, 0, 0

        for ped in pedidos:
            estado = ped.get("estado", "Pendiente")
            total = ped.get("total", 0.0)
            if estado == "Cancelado":
                cancelados += 1
            else:
                ventas += total
                validos += 1
            if estado in ("Pendiente", "Preparando"):
                proceso += 1
            if filtro != "Todos" and estado != filtro:
                continue
            if busqueda and busqueda not in ped.get("cliente", "").lower():
                continue
            detalle = ", ".join(f"{it['nombre']} x{it['cantidad']}" for it in ped.get("items", []))
            self.tree_pedidos.insert(
                "", "end", iid=str(ped["id"]), tags=(estado,),
                values=(f"#{ped['id']}", ped.get("fecha", ""), ped.get("cliente", ""), ped.get("perfil", "General"),
                        ped.get("pago", ""), detalle, logica.dinero(total), f"● {estado}"))
        for iid in sel:
            if self.tree_pedidos.exists(iid):
                self.tree_pedidos.selection_set(iid)

        self.kpi["ventas"][0].config(text=logica.dinero(ventas))
        self.kpi["ventas"][1].config(text="sin contar cancelados")
        self.kpi["pedidos"][0].config(text=str(validos))
        self.kpi["pedidos"][1].config(text=f"{cancelados} cancelado(s)")
        self.kpi["proceso"][0].config(text=str(proceso))
        self.kpi["proceso"][1].config(text="pendientes + preparando")
        self.kpi["ticket"][0].config(text=logica.dinero(ventas / validos if validos else 0.0))
        self.kpi["ticket"][1].config(text="por pedido vigente")
        self._dibujar_distribucion()

    # ------------------------------------------------------------------
    def refrescar_todo(self):
        self.refrescar_vitrina()
        self.refrescar_carrito()
        self.refrescar_catalogo()
        self.refrescar_stock()
        self.refrescar_pedidos()
        prods = self.datos.get("productos", [])
        self.lbl_estado.config(
            text=f"{len(prods)} producto(s)  ·  {sum(p['stock'] for p in prods)} unidades en inventario  ·  "
                 f"{len(self.datos.get('pedidos', []))} pedido(s) registrados")


def main():
    if sys.platform.startswith("win"):
        try:  # pantallas de alta densidad: texto nítido en Windows
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    ventana = tk.Tk()
    TiendaMTApp(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    main()
