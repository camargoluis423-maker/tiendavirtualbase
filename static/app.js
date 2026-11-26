/* M&T · COM-1 — Interacciones progresivas y animaciones (sin dependencias externas) */
(function () {
  "use strict";

  const header = document.getElementById("topHeader");
  const btnArriba = document.getElementById("btnArriba");

  // 1. Encabezado elevado y botón volver arriba
  function alHacerScroll() {
    const y = window.scrollY || 0;
    if (header) header.classList.toggle("scrolled", y > 18);
    if (btnArriba) btnArriba.classList.toggle("visible", y > 360);
  }
  window.addEventListener("scroll", alHacerScroll, { passive: true });
  alHacerScroll();

  if (btnArriba) {
    btnArriba.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // 2. Cierre de notificaciones flash
  document.querySelectorAll(".flash").forEach(function (el) {
    const closeBtn = el.querySelector(".flash-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        el.classList.add("saliendo");
        setTimeout(function () { el.remove(); }, 220);
      });
    }
    if (el.classList.contains("ok")) {
      setTimeout(function () {
        if (!document.body.contains(el)) return;
        el.classList.add("saliendo");
        setTimeout(function () { el.remove(); }, 240);
      }, 4500);
    }
  });

  // 3. Animaciones de entrada al hacer scroll (IntersectionObserver)
  const reveals = Array.from(document.querySelectorAll(".reveal"));
  if ("IntersectionObserver" in window && reveals.length) {
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -24px 0px" });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("in"); });
  }

  // 4. Tabla interactiva de componentes (filtro por subtipo, ordenamiento y modo de vista)
  const compSec = document.getElementById("tabla-componentes");
  if (compSec) {
    const tbody = compSec.querySelector("tbody");
    const filas = tbody ? Array.from(tbody.querySelectorAll("tr[data-tipo]")) : [];
    const chipsTipo = Array.from(compSec.querySelectorAll("[data-comp-filter]"));
    const buscadorLocal = compSec.querySelector("#compFiltroTexto");
    const contadorEl = compSec.querySelector("#compVisibleCount");
    const vacioFila = compSec.querySelector("#compEmptyRow");
    const sortBtns = Array.from(compSec.querySelectorAll("[data-sort]"));

    let filtroTipo = "todos";
    let filtroTexto = "";
    let sortCol = null;
    let sortDir = "asc";

    function aplicarTabla() {
      let visibles = 0;
      filas.forEach(function (tr, idx) {
        const tipo = tr.dataset.tipo || "";
        const texto = (tr.dataset.search || "").toLowerCase();
        const okTipo = filtroTipo === "todos" || tipo === filtroTipo;
        const okTxt = !filtroTexto || texto.indexOf(filtroTexto) !== -1;
        const mostrar = okTipo && okTxt;
        tr.hidden = !mostrar;
        if (mostrar) {
          visibles++;
          tr.style.setProperty("--row-i", Math.min(visibles - 1, 10));
          tr.classList.remove("row-enter");
          // Reflow ligero para re-disparar animación de fila al filtrar
          void tr.offsetWidth;
          tr.classList.add("row-enter");
        }
      });
      if (vacioFila) vacioFila.hidden = visibles > 0;
      if (contadorEl) contadorEl.textContent = String(visibles);
    }

    chipsTipo.forEach(function (btn) {
      btn.addEventListener("click", function () {
        filtroTipo = btn.dataset.compFilter || "todos";
        chipsTipo.forEach(function (b) { b.classList.toggle("on", b === btn); });
        aplicarTabla();
      });
    });

    if (buscadorLocal) {
      buscadorLocal.addEventListener("input", function () {
        filtroTexto = buscadorLocal.value.trim().toLowerCase();
        aplicarTabla();
      });
    }

    sortBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const col = btn.dataset.sort;
        if (sortCol === col) {
          sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
          sortCol = col;
          sortDir = "asc";
        }
        sortBtns.forEach(function (b) {
          b.classList.remove("asc", "desc");
          if (b === btn) b.classList.add(sortDir);
        });
        filas.sort(function (a, b) {
          let va = a.dataset[col] || "";
          let vb = b.dataset[col] || "";
          if (col === "precio" || col === "stock") {
            const na = parseFloat(va) || 0;
            const nb = parseFloat(vb) || 0;
            return sortDir === "asc" ? na - nb : nb - na;
          }
          return sortDir === "asc"
            ? va.localeCompare(vb, "es")
            : vb.localeCompare(va, "es");
        });
        filas.forEach(function (tr) { tbody.appendChild(tr); });
        if (vacioFila) tbody.appendChild(vacioFila);
        aplicarTabla();
      });
    });

    // Alternar vista (Tabla + Tarjetas / Solo Tabla / Solo Tarjetas)
    const viewBtns = Array.from(document.querySelectorAll("[data-comp-view]"));
    const cardsBox = document.getElementById("componentes-tarjetas");
    const tableBox = document.getElementById("componentes-tabla-wrap");
    if (viewBtns.length && cardsBox && tableBox) {
      function setView(mode) {
        viewBtns.forEach(function (b) { b.classList.toggle("on", b.dataset.compView === mode); });
        tableBox.hidden = mode === "cards";
        cardsBox.hidden = mode === "table";
        try { sessionStorage.setItem("mt_comp_view", mode); } catch (e) {}
      }
      let saved = "both";
      try { saved = sessionStorage.getItem("mt_comp_view") || "both"; } catch (e) {}
      setView(saved);
      viewBtns.forEach(function (b) {
        b.addEventListener("click", function () { setView(b.dataset.compView || "both"); });
      });
    }
  }

  // 5. Selector de cantidad (+/-) en ficha de producto
  document.querySelectorAll("[data-qty-stepper]").forEach(function (wrap) {
    const input = wrap.querySelector("input[type='number']");
    const minus = wrap.querySelector("[data-qty='-1']");
    const plus = wrap.querySelector("[data-qty='1']");
    if (!input || !minus || !plus) return;
    function sync() {
      const min = parseInt(input.min || "1", 10);
      const max = parseInt(input.max || "99", 10);
      const val = parseInt(input.value || "1", 10);
      minus.disabled = input.disabled || val <= min;
      plus.disabled = input.disabled || val >= max;
    }
    minus.addEventListener("click", function () {
      const min = parseInt(input.min || "1", 10);
      input.value = Math.max(min, (parseInt(input.value || "1", 10) || min) - 1);
      sync();
    });
    plus.addEventListener("click", function () {
      const max = parseInt(input.max || "99", 10);
      input.value = Math.min(max, (parseInt(input.value || "1", 10) || 1) + 1);
      sync();
    });
    input.addEventListener("input", sync);
    sync();
  });

  // 6. Copiar ticket en página de pedido
  const copyBtn = document.getElementById("btnCopiarTicket");
  const ticketPre = document.getElementById("ticketContenido");
  if (copyBtn && ticketPre && navigator.clipboard) {
    copyBtn.addEventListener("click", function () {
      navigator.clipboard.writeText(ticketPre.textContent || "").then(function () {
        const span = copyBtn.querySelector("span");
        const original = span ? span.textContent : copyBtn.textContent;
        if (span) {
          span.textContent = "✓ Ticket copiado";
        } else {
          copyBtn.textContent = "✓ Ticket copiado";
        }
        copyBtn.classList.add("copiado");
        setTimeout(function () {
          if (span) {
            span.textContent = original;
          } else {
            copyBtn.textContent = original;
          }
          copyBtn.classList.remove("copiado");
        }, 2200);
      });
    });
  }

  // 7. Efecto de feedback inmediato en botones "Agregar al carrito"
  document.querySelectorAll("form[action*='carrito/agregar']").forEach(function (form) {
    form.addEventListener("submit", function () {
      const btn = form.querySelector("button[type='submit'], button:not([type])");
      if (btn && !btn.disabled) {
        btn.classList.add("enviando");
      }
    });
  });

  // 8. Login / Registro: cambio de rol (Comprador vs Vendedor) y relleno demo
  const rolBtns = Array.from(document.querySelectorAll("[data-rol-tab]"));
  const modoTabs = document.getElementById("modoTabs");
  const modoBtns = Array.from(document.querySelectorAll("[data-auth-modo]"));
  const formLogin = document.getElementById("formLogin");
  const formRegistro = document.getElementById("formRegistro");
  const loginRolInput = document.getElementById("loginRolInput");
  const rolBanner = document.getElementById("rolBanner");
  const rolBannerTexto = document.getElementById("rolBannerTexto");
  const loginBtnTexto = document.getElementById("loginBtnTexto");
  const loginUser = document.getElementById("loginUser");
  const loginPass = document.getElementById("loginPass");

  if (rolBtns.length && formLogin && loginRolInput) {
    let modoActual = formRegistro && !formRegistro.hidden ? "registro" : "login";

    function syncAuthUI(rol) {
      loginRolInput.value = rol;
      rolBtns.forEach(function (b) {
        const activo = b.dataset.rolTab === rol;
        b.classList.toggle("on", activo);
        b.setAttribute("aria-selected", activo ? "true" : "false");
      });
      if (rolBanner && rolBannerTexto && loginBtnTexto) {
        rolBanner.className = "auth-rol-banner " + rol;
        if (rol === "vendedor") {
          rolBannerTexto.textContent = "Acceso administrativo para gestión de ventas e inventario.";
          loginBtnTexto.textContent = "Entrar como Vendedor";
          if (loginUser) loginUser.placeholder = "ej. vendedor@mtcom1.mx";
        } else {
          rolBannerTexto.textContent = "Acceso de cliente para compras y seguimiento de pedidos.";
          loginBtnTexto.textContent = "Entrar como Comprador";
          if (loginUser) loginUser.placeholder = "ej. comprador@mtcom1.mx";
        }
      }
      if (rol === "vendedor") {
        modoActual = "login";
      }
      if (modoTabs) modoTabs.hidden = rol === "vendedor";
      if (formLogin) formLogin.hidden = modoActual === "registro" && rol === "comprador";
      if (formRegistro) formRegistro.hidden = !(modoActual === "registro" && rol === "comprador");
      modoBtns.forEach(function (b) {
        b.classList.toggle("on", b.dataset.authModo === modoActual);
      });
    }

    rolBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        syncAuthUI(btn.dataset.rolTab || "comprador");
      });
    });

    modoBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        modoActual = btn.dataset.authModo || "login";
        syncAuthUI(loginRolInput.value || "comprador");
      });
    });

    document.querySelectorAll("[data-demo-role]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const rol = btn.dataset.demoRole || "comprador";
        modoActual = "login";
        syncAuthUI(rol);
        if (loginUser) loginUser.value = btn.dataset.demoUser || "";
        if (loginPass) loginPass.value = btn.dataset.demoPass || "";
        if (loginUser) loginUser.focus();
      });
    });
  }

  // 9. Pasarela de pago simulada (pestañas, tarjeta en vivo y copiar CLABE)
  const formPago = document.getElementById("formPago");
  if (formPago) {
    const pagoTabs = Array.from(document.querySelectorAll("[data-pago-tab]"));
    const pagoInput = document.getElementById("pagoMetodoInput");
    const pagoPanels = Array.from(document.querySelectorAll(".pago-panel"));

    function activarMetodoPago(metodo) {
      if (pagoInput) pagoInput.value = metodo;
      pagoTabs.forEach(function (t) {
        const on = t.dataset.pagoTab === metodo;
        t.classList.toggle("on", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      pagoPanels.forEach(function (panel) {
        const activo = panel.id === "pago-" + metodo;
        panel.hidden = !activo;
        panel.querySelectorAll("input, select").forEach(function (inp) {
          inp.disabled = !activo;
        });
      });
    }

    if (pagoInput) activarMetodoPago(pagoInput.value || "Tarjeta");
    pagoTabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activarMetodoPago(tab.dataset.pagoTab);
      });
    });

    // Vista previa en vivo de tarjeta
    const cardNum = document.getElementById("cardNumber");
    const cardName = document.getElementById("cardName");
    const cardExp = document.getElementById("cardExp");
    const pNum = document.getElementById("cardPreviewNum");
    const pName = document.getElementById("cardPreviewName");
    const pExp = document.getElementById("cardPreviewExp");
    const pRed = document.getElementById("cardPreviewRed");

    if (cardNum && pNum) {
      cardNum.addEventListener("input", function () {
        const digits = cardNum.value.replace(/\D/g, "").slice(0, 16);
        const grupos = digits.match(/.{1,4}/g) || [];
        cardNum.value = grupos.join(" ");
        pNum.textContent = cardNum.value || "•••• •••• •••• ••••";
        if (pRed) {
          pRed.textContent = digits.startsWith("4") ? "VISA" : digits.startsWith("5") ? "MASTERCARD" : "";
        }
      });
    }
    if (cardName && pName) {
      cardName.addEventListener("input", function () {
        pName.textContent = (cardName.value.trim() || "TU NOMBRE").toUpperCase();
      });
    }
    if (cardExp && pExp) {
      cardExp.addEventListener("input", function () {
        let v = cardExp.value.replace(/\D/g, "").slice(0, 4);
        if (v.length >= 3) v = v.slice(0, 2) + "/" + v.slice(2);
        cardExp.value = v;
        pExp.textContent = v || "MM/AA";
      });
    }

    // Copiar CLABE SPEI
    const btnClabe = document.getElementById("btnCopiarClabe");
    const clabeEl = document.getElementById("clabeDisplay");
    if (btnClabe && clabeEl && navigator.clipboard) {
      btnClabe.addEventListener("click", function () {
        navigator.clipboard.writeText(clabeEl.textContent.replace(/\s+/g, "")).then(function () {
          btnClabe.textContent = "✓ Copiada";
          setTimeout(function () { btnClabe.textContent = "Copiar"; }, 2000);
        });
      });
    }

    // Feedback al confirmar pago
    formPago.addEventListener("submit", function () {
      const btnPagar = document.getElementById("btnPagar");
      if (btnPagar) {
        btnPagar.classList.add("enviando");
        const span = btnPagar.querySelector("span");
        if (span) span.textContent = "Procesando pago…";
      }
    });
  }

  // 10. Contador de Ofertas Relámpago (estilo Temu / Mercado Libre)
  const dealTimer = document.getElementById("dealCountdown");
  if (dealTimer) {
    function tickDeal() {
      const ahora = new Date();
      const fin = new Date(ahora);
      fin.setHours(23, 59, 59, 999);
      const diff = Math.max(0, Math.floor((fin - ahora) / 1000));
      const h = String(Math.floor(diff / 3600)).padStart(2, "0");
      const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
      const s = String(diff % 60).padStart(2, "0");
      dealTimer.textContent = h + ":" + m + ":" + s;
    }
    tickDeal();
    setInterval(tickDeal, 1000);
  }

  // 11. Favoritos con sincronización al usuario (estilo Shein / Mercado Libre / Amazon)
  let favs = [];
  try { favs = JSON.parse(localStorage.getItem("mt_favs") || "[]"); } catch (e) { favs = []; }
  const chatWidgetEl = document.getElementById("chatWidget");
  const csrfTokenGlobal = chatWidgetEl ? (chatWidgetEl.dataset.csrf || "") : "";
  document.querySelectorAll("[data-fav-btn]").forEach(function (btn) {
    const pid = btn.dataset.favBtn;
    function renderFav() {
      const on = favs.indexOf(pid) !== -1;
      btn.classList.toggle("on", on);
      btn.innerHTML = on ? "&#9829;" : "&#9825;";
    }
    renderFav();
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const idx = favs.indexOf(pid);
      if (idx === -1) favs.push(pid); else favs.splice(idx, 1);
      try { localStorage.setItem("mt_favs", JSON.stringify(favs)); } catch (err) {}
      renderFav();
      if (csrfTokenGlobal) {
        fetch("/api/favoritos/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfTokenGlobal },
          body: JSON.stringify({ pid: pid })
        }).catch(function () {});
      }
    });
  });

  // 12. Modal de Vista Rápida (Quick View estilo Amazon / Temu)
  const qvModal = document.getElementById("quickViewModal");
  const qvClose = document.getElementById("qvClose");
  if (qvModal) {
    const qvImg = document.getElementById("qvImg");
    const qvNoImg = document.getElementById("qvNoImg");
    const qvCat = document.getElementById("qvCat");
    const qvRating = document.getElementById("qvRating");
    const qvTitulo = document.getElementById("qvTitulo");
    const qvSpecs = document.getElementById("qvSpecs");
    const qvPrecio = document.getElementById("qvPrecio");
    const qvPrecioIva = document.getElementById("qvPrecioIva");
    const qvStock = document.getElementById("qvStock");
    const qvPid = document.getElementById("qvPid");
    const qvBtnAdd = document.getElementById("qvBtnAdd");
    const qvLinkDetalle = document.getElementById("qvLinkDetalle");

    function cerrarQV() {
      qvModal.hidden = true;
      qvModal.setAttribute("aria-hidden", "true");
    }

    document.querySelectorAll("[data-quick-view]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        const d = btn.dataset;
        if (d.foto) {
          qvImg.src = d.foto;
          qvImg.alt = d.nombre || "";
          qvImg.hidden = false;
          qvNoImg.hidden = true;
        } else {
          qvImg.hidden = true;
          qvNoImg.hidden = false;
        }
        qvCat.textContent = d.cat || "";
        qvRating.textContent = d.rating || "4.9";
        qvTitulo.textContent = d.nombre || "";
        qvSpecs.textContent = d.specs || "";
        qvPrecio.innerHTML = (d.precio || "") + " <small>+ IVA</small>";
        qvPrecioIva.textContent = d.precioIva || "";
        const stockNum = parseInt(d.stock || "0", 10);
        qvStock.textContent = stockNum > 0 ? "Disponible (" + stockNum + " unidades en inventario)" : "Agotado por el momento";
        qvStock.className = "qv-stock " + (d.nivel || "");
        if (qvPid) qvPid.value = d.pid || "";
        if (qvBtnAdd) qvBtnAdd.disabled = stockNum <= 0;
        if (qvLinkDetalle) qvLinkDetalle.href = d.url || "#";
        qvModal.hidden = false;
        qvModal.setAttribute("aria-hidden", "false");
      });
    });

    if (qvClose) qvClose.addEventListener("click", cerrarQV);
    qvModal.addEventListener("click", function (e) {
      if (e.target === qvModal) cerrarQV();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !qvModal.hidden) cerrarQV();
    });
  }

  // 13. Asistente Chatbot con Ollama
  const chatWidget = document.getElementById("chatWidget");
  const chatToggle = document.getElementById("chatToggleBtn");
  const chatClose = document.getElementById("chatCloseBtn");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const chatMsgs = document.getElementById("chatMsgs");
  const chatBadge = document.getElementById("chatStatusBadge");

  if (chatWidget && chatToggle) {
    let statusChecked = false;
    function checkOllamaStatus() {
      if (statusChecked || !chatBadge) return;
      statusChecked = true;
      fetch("/api/chat/status")
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.ollama_activo) {
            chatBadge.innerHTML = '<i class="dot ok"></i> Ollama activo (' + d.modelo + ")";
          } else {
            chatBadge.innerHTML = '<i class="dot local"></i> Modo local (Ollama offline)';
          }
        })
        .catch(function () {
          chatBadge.innerHTML = '<i class="dot local"></i> Modo local M&T';
        });
    }

    chatToggle.addEventListener("click", function () {
      chatWidget.hidden = !chatWidget.hidden;
      if (!chatWidget.hidden) {
        checkOllamaStatus();
        if (chatInput) chatInput.focus();
      }
    });
    if (chatClose) {
      chatClose.addEventListener("click", function () { chatWidget.hidden = true; });
    }

    function addMsg(texto, tipo, motor) {
      const div = document.createElement("div");
      div.className = "chat-msg " + tipo;
      div.textContent = texto;
      if (motor && tipo === "bot") {
        const tag = document.createElement("small");
        tag.className = "chat-motor";
        tag.textContent = motor;
        div.appendChild(tag);
      }
      chatMsgs.appendChild(div);
      chatMsgs.scrollTop = chatMsgs.scrollHeight;
      return div;
    }

    function enviarChat(texto) {
      if (!texto) return;
      addMsg(texto, "user");
      const loading = addMsg("Pensando…", "bot typing");
      fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": chatWidget.dataset.csrf || ""
        },
        body: JSON.stringify({ mensaje: texto })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          loading.remove();
          addMsg(data.respuesta || data.error || "No pude procesar tu consulta.", "bot", data.motor);
        })
        .catch(function () {
          loading.remove();
          addMsg("Error de conexión con el asistente.", "bot");
        });
    }

    if (chatForm) {
      chatForm.addEventListener("submit", function (e) {
        e.preventDefault();
        const txt = (chatInput.value || "").trim();
        if (!txt) return;
        chatInput.value = "";
        enviarChat(txt);
      });
    }

    document.querySelectorAll("[data-chat-q]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        enviarChat(btn.dataset.chatQ || "");
      });
    });
  }

  // 14. Modal de Detalle de Compra en Panel del Vendedor
  const pdModal = document.getElementById("pedidoDetalleModal");
  const pdClose = document.getElementById("pdClose");
  if (pdModal) {
    const pdTitulo = document.getElementById("pdTitulo");
    const pdMeta = document.getElementById("pdMeta");
    const pdPago = document.getElementById("pdPago");
    const pdItems = document.getElementById("pdItems");
    const pdTotales = document.getElementById("pdTotales");

    function cerrarPD() {
      pdModal.hidden = true;
      pdModal.setAttribute("aria-hidden", "true");
    }

    function fmtDinero(n) {
      return "$" + (parseFloat(n) || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    document.querySelectorAll("[data-ver-pedido]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        let p = {};
        try { p = JSON.parse(btn.dataset.verPedido || "{}"); } catch (e) {}
        pdTitulo.textContent = "Detalle de compra · Pedido #" + (p.id || "");
        pdMeta.innerHTML =
          "<div><span>Cliente:</span> <b>" + (p.cliente || "-") + "</b></div>" +
          "<div><span>Cuenta:</span> <b>" + (p.usuario || "Invitado") + "</b></div>" +
          "<div><span>Fecha:</span> <b>" + (p.fecha || "-") + "</b></div>" +
          "<div><span>Perfil:</span> <b>" + (p.perfil || "General") + "</b></div>" +
          "<div><span>Estado:</span> <b>" + (p.estado || "Pendiente") + "</b></div>";

        const dp = p.datos_pago || {};
        const detallesPago = Object.keys(dp).map(function (k) {
          return k + ": " + dp[k];
        }).join(" · ");
        pdPago.innerHTML = "<b>Método de pago:</b> " + (p.pago || "-") + (detallesPago ? "<br><small>" + detallesPago + "</small>" : "");

        pdItems.innerHTML = "";
        (p.items || []).forEach(function (it) {
          const tr = document.createElement("tr");
          tr.innerHTML =
            "<td>" + (it.nombre || "") + "</td>" +
            '<td class="num">' + (it.cantidad || 1) + "</td>" +
            '<td class="num">' + fmtDinero(it.precio) + "</td>" +
            '<td class="num"><b>' + fmtDinero(it.importe) + "</b></td>";
          pdItems.appendChild(tr);
        });

        pdTotales.innerHTML =
          '<span class="suave">Subtotal</span><span>' + fmtDinero(p.subtotal) + "</span>" +
          '<span class="suave">Descuento</span><span class="ahorro">-' + fmtDinero(p.descuento) + "</span>" +
          '<span class="suave">IVA</span><span>' + fmtDinero(p.iva) + "</span>" +
          '<span class="gran">Total</span><span class="gran">' + fmtDinero(p.total) + "</span>";

        pdModal.hidden = false;
        pdModal.setAttribute("aria-hidden", "false");
      });
    });

    if (pdClose) pdClose.addEventListener("click", cerrarPD);
    pdModal.addEventListener("click", function (e) { if (e.target === pdModal) cerrarPD(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !pdModal.hidden) cerrarPD(); });
  }

  // 15. Modo oscuro con botón en el encabezado
  const themeBtn = document.getElementById("themeToggle");
  if (themeBtn) {
    function syncThemeIcon() {
      const isDark = document.documentElement.getAttribute("data-theme") === "dark";
      themeBtn.innerHTML = isDark ? "&#9728;&#65039;" : "&#127769;";
    }
    syncThemeIcon();
    themeBtn.addEventListener("click", function () {
      const isDark = document.documentElement.getAttribute("data-theme") === "dark";
      if (isDark) {
        document.documentElement.removeAttribute("data-theme");
        try { localStorage.setItem("mt_theme", "light"); } catch (e) {}
      } else {
        document.documentElement.setAttribute("data-theme", "dark");
        try { localStorage.setItem("mt_theme", "dark"); } catch (e) {}
      }
      syncThemeIcon();
    });
  }

  // 16. Comparador de productos (hasta 3)
  let cmpIds = [];
  try { cmpIds = JSON.parse(localStorage.getItem("mt_cmp") || "[]"); } catch (e) { cmpIds = []; }
  const cmpBar = document.getElementById("compareBar");
  const cmpCount = document.getElementById("compareCount");
  const cmpGo = document.getElementById("compareGoBtn");
  const cmpClear = document.getElementById("compareClearBtn");
  function syncCmp() {
    document.querySelectorAll("[data-compare-btn]").forEach(function (b) {
      b.classList.toggle("primario", cmpIds.indexOf(b.dataset.compareBtn) !== -1);
    });
    if (cmpBar && cmpCount && cmpGo) {
      cmpBar.hidden = cmpIds.length === 0;
      cmpCount.textContent = String(cmpIds.length);
      cmpGo.href = "/comparador?ids=" + encodeURIComponent(cmpIds.join(","));
    }
  }
  syncCmp();
  document.querySelectorAll("[data-compare-btn]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const pid = btn.dataset.compareBtn;
      const idx = cmpIds.indexOf(pid);
      if (idx !== -1) cmpIds.splice(idx, 1);
      else if (cmpIds.length < 3) cmpIds.push(pid);
      else { cmpIds.shift(); cmpIds.push(pid); }
      try { localStorage.setItem("mt_cmp", JSON.stringify(cmpIds)); } catch (e) {}
      syncCmp();
    });
  });
  if (cmpClear) {
    cmpClear.addEventListener("click", function () {
      cmpIds = [];
      try { localStorage.setItem("mt_cmp", "[]"); } catch (e) {}
      syncCmp();
    });
  }

  // 17. Armador de PC con validación de compatibilidad
  const armForm = document.getElementById("armadorForm");
  if (armForm) {
    const sels = Array.from(armForm.querySelectorAll("[data-arm-sel]"));
    const checksBox = document.getElementById("armChecks");
    const countEl = document.getElementById("armCount");
    const totalEl = document.getElementById("armTotal");

    function evaluarArmado() {
      let total = 0;
      let count = 0;
      const info = {};
      const msgs = [];
      sels.forEach(function (s) {
        const opt = s.options[s.selectedIndex];
        if (opt && opt.value) {
          count++;
          total += parseFloat(opt.dataset.precio || "0");
          info[s.dataset.armSel] = {
            text: opt.textContent,
            specs: (opt.dataset.specs || "").toLowerCase(),
            stock: parseInt(opt.dataset.stock || "0", 10)
          };
          if (parseInt(opt.dataset.stock || "0", 10) <= 0) {
            msgs.push({ cls: "warn", txt: opt.textContent.split("—")[0].trim() + " está agotado actualmente." });
          }
        }
      });
      if (info.cpu) {
        if (info.cpu.specs.indexOf("am5") !== -1) {
          msgs.push({ cls: "ok", txt: "CPU usa socket AM5 y requiere RAM DDR5 ✅" });
          if (info.ram && info.ram.specs.indexOf("ddr5") !== -1) {
            msgs.push({ cls: "ok", txt: "Memoria DDR5 compatible con plataforma AM5 ✅" });
          } else if (info.ram) {
            msgs.push({ cls: "warn", txt: "Verifica que la RAM sea DDR5 para socket AM5 ⚠️" });
          }
        }
      }
      if (info.gpu) {
        if (info.gpu.specs.indexOf("550w") !== -1) {
          msgs.push({ cls: "ok", txt: "Esta GPU recomienda fuente de 550W+ ✅" });
          if (info.psu && (info.psu.specs.indexOf("650w") !== -1 || info.psu.specs.indexOf("750w") !== -1)) {
            msgs.push({ cls: "ok", txt: "Fuente seleccionada cubre los 550W+ recomendados ✅" });
          }
        }
      }
      if (!msgs.length) {
        msgs.push({ cls: "ok", txt: "Selecciona componentes para validar compatibilidad." });
      }
      if (checksBox) {
        checksBox.innerHTML = msgs.map(function (m) {
          return '<div class="arm-msg ' + m.cls + '">' + m.txt + "</div>";
        }).join("");
      }
      if (countEl) countEl.textContent = String(count);
      if (totalEl) totalEl.textContent = "$" + total.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    sels.forEach(function (s) { s.addEventListener("change", evaluarArmado); });
    evaluarArmado();
  }

  // 18. Gráfica Chart.js en Panel Vendedor (si Chart.js cargó)
  const ventasCanvas = document.getElementById("ventasChartCanvas");
  if (ventasCanvas) {
    window.addEventListener("load", function () {
      if (typeof window.Chart !== "function") {
        ventasCanvas.hidden = true;
        return;
      }
      let labels = [];
      let values = [];
      try {
        labels = JSON.parse(ventasCanvas.dataset.labels || "[]");
        values = JSON.parse(ventasCanvas.dataset.values || "[]");
      } catch (e) {}
      new window.Chart(ventasCanvas, {
        type: "bar",
        data: {
          labels: labels,
          datasets: [{
            label: "Ventas reales por día ($ MXN)",
            data: values,
            backgroundColor: "rgba(42, 157, 143, 0.85)",
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: true } },
          scales: { y: { beginAtZero: true } }
        }
      });
    });
  }

  // 19. Modo Sucursal (POS) para el Vendedor
  const posGrid = document.getElementById("posGrid");
  if (posGrid) {
    const posBuscar = document.getElementById("posBuscar");
    const posItemsEl = document.getElementById("posTicketItems");
    const posTotalEl = document.getElementById("posTotal");
    const posJsonEl = document.getElementById("posItemsJson");
    const posLimpiar = document.getElementById("posLimpiar");
    const carritoPos = {};
    const nombresPos = {};
    const preciosPos = {};

    function renderPos() {
      const keys = Object.keys(carritoPos);
      if (!keys.length) {
        posItemsEl.innerHTML = '<p class="suave">Toca un producto para agregarlo.</p>';
        posTotalEl.textContent = "$0.00";
        posJsonEl.value = "{}";
        return;
      }
      let sub = 0;
      posItemsEl.innerHTML = "";
      keys.forEach(function (pid) {
        const cant = carritoPos[pid];
        const imp = cant * preciosPos[pid];
        sub += imp;
        const row = document.createElement("div");
        row.className = "pos-row";
        row.innerHTML = "<span>" + cant + "× " + nombresPos[pid] + "</span><b>$" + imp.toFixed(2) + "</b>";
        posItemsEl.appendChild(row);
      });
      const totalEst = sub * 1.16;
      posTotalEl.textContent = "$" + totalEst.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      posJsonEl.value = JSON.stringify(carritoPos);
    }

    posGrid.querySelectorAll("[data-pos-add]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const pid = btn.dataset.pid;
        const maxS = parseInt(btn.dataset.stock || "0", 10);
        if ((carritoPos[pid] || 0) < maxS) {
          carritoPos[pid] = (carritoPos[pid] || 0) + 1;
          nombresPos[pid] = btn.dataset.nombre;
          preciosPos[pid] = parseFloat(btn.dataset.precio || "0");
          renderPos();
        }
      });
    });

    if (posBuscar) {
      posBuscar.addEventListener("input", function () {
        const q = posBuscar.value.trim().toLowerCase();
        posGrid.querySelectorAll("[data-pos-add]").forEach(function (btn) {
          btn.hidden = q && (btn.dataset.search || "").indexOf(q) === -1;
        });
      });
    }
    if (posLimpiar) {
      posLimpiar.addEventListener("click", function () {
        Object.keys(carritoPos).forEach(function (k) { delete carritoPos[k]; });
        renderPos();
      });
    }
  }

  // 20. Barra de progreso de lectura/scroll superior
  const scrollBar = document.getElementById("scrollProgress");
  if (scrollBar) {
    function actualizarScrollBar() {
      const doc = document.documentElement;
      const max = (doc.scrollHeight - window.innerHeight) || 1;
      const pct = Math.max(0, Math.min(100, (window.scrollY / max) * 100));
      scrollBar.style.width = pct.toFixed(1) + "%";
    }
    window.addEventListener("scroll", actualizarScrollBar, { passive: true });
    actualizarScrollBar();
  }

  // 21. Carga suave de imágenes de producto (fade-in sin saltos)
  document.querySelectorAll(".foto img, .deal-img img, .cod-media img").forEach(function (img) {
    if (img.complete) {
      img.classList.add("img-ready");
    } else {
      img.addEventListener("load", function () { img.classList.add("img-ready"); }, { once: true });
      img.addEventListener("error", function () { img.classList.add("img-ready"); }, { once: true });
    }
  });

  // 22. Conteo animado sutil para KPIs numéricos al entrar en pantalla
  const prefersReduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!prefersReduced && "IntersectionObserver" in window) {
    const kpis = Array.from(document.querySelectorAll(".heroe-kpis b, .kpi-card b"));
    const kpiIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        kpiIO.unobserve(entry.target);
        const el = entry.target;
        const raw = (el.textContent || "").trim();
        const m = raw.match(/^(\$?)([\d,]+)(\.\d+)?$/);
        if (!m) return;
        const prefix = m[1] || "";
        const target = parseFloat(m[2].replace(/,/g, "") + (m[3] || ""));
        const dec = m[3] ? m[3].length - 1 : 0;
        if (!target || target <= 0) return;
        const dur = 480;
        const t0 = performance.now();
        function step(now) {
          const p = Math.min(1, (now - t0) / dur);
          const ease = 1 - Math.pow(1 - p, 3);
          const cur = target * ease;
          el.textContent = prefix + cur.toLocaleString("en-US", {
            minimumFractionDigits: dec,
            maximumFractionDigits: dec
          });
          if (p < 1) requestAnimationFrame(step);
          else el.textContent = raw;
        }
        requestAnimationFrame(step);
      });
    }, { threshold: 0.3 });
    kpis.forEach(function (k) { kpiIO.observe(k); });
  }
})();
