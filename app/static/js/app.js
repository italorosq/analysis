// Serra Rocketry - navegação e UI
document.addEventListener("DOMContentLoaded", function () {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const hamburger = document.getElementById("hamburger");
  const mobileBtn = document.getElementById("mobileMenuBtn");
  const wrapper = document.querySelector(".app-wrapper");

  function openSidebar() {
    if (sidebar) sidebar.classList.add("sidebar-open");
    if (wrapper) wrapper.classList.add("sidebar-open");
    if (overlay) overlay.classList.add("visible");
    [hamburger, mobileBtn].forEach((b) => {
      if (b) b.setAttribute("aria-expanded", "true");
    });
  }

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove("sidebar-open");
    if (wrapper) wrapper.classList.remove("sidebar-open");
    if (overlay) overlay.classList.remove("visible");
    [hamburger, mobileBtn].forEach((b) => {
      if (b) b.setAttribute("aria-expanded", "false");
    });
  }

  function toggleSidebar(event) {
    if (event) event.preventDefault();
    const isOpen = sidebar && sidebar.classList.contains("sidebar-open");
    if (isOpen) {
      closeSidebar();
    } else {
      openSidebar();
    }
  }

  if (hamburger) hamburger.addEventListener("click", toggleSidebar);
  if (mobileBtn) mobileBtn.addEventListener("click", toggleSidebar);
  if (overlay) overlay.addEventListener("click", closeSidebar);

  // Fecha o menu ao clicar num link (mobile)
  const navLinks = document.querySelectorAll(".menu-list li a");
  navLinks.forEach((link) => {
    link.addEventListener("click", function () {
      if (window.innerWidth <= 900) {
        closeSidebar();
      }
    });
  });

  // Marca o link ativo conforme a URL atual
  const path = window.location.pathname;
  navLinks.forEach((link) => {
    const href = link.getAttribute("href");
    if (href && href !== "#" && path.endsWith(href.replace(/\/$/, ""))) {
      link.classList.add("active");
    }
  });
  // Fallback: se nenhum casou e estamos na raiz, marca Home (primeiro link)
  if (!document.querySelector(".menu-list a.active") && navLinks.length) {
    if (path === "/" || path.endsWith("/home") || path.endsWith("serra-rocketry/")) {
      navLinks[0].classList.add("active");
    }
  }

  // Auto-dismiss das mensagens flash
  const flashes = document.querySelectorAll(".flash");
  flashes.forEach((flash) => {
    setTimeout(() => {
      flash.style.transition = "opacity 0.5s ease";
      flash.style.opacity = "0";
      setTimeout(() => flash.remove(), 500);
    }, 5000);
  });

  initTitleEditor();
});

// ---------------------------------------------------------------------------
// Editor de títulos de gráficos/relatório (aba Salvar + Biblioteca)
// - preview ao vivo de cada campo
// - contagem de campos personalizados (valor != padrão)
// - reset por grupo / reset total
// ---------------------------------------------------------------------------
function initTitleEditor() {
  const editor = document.getElementById("te-editor");
  if (!editor) return;

  const countEl = document.getElementById("te-count");

  const isDirty = (input) => (input.value || "").trim() !== (input.placeholder || "").trim();

  function refresh() {
    let total = 0;
    editor.querySelectorAll("[data-te-key]").forEach((input) => {
      const dirty = isDirty(input);
      input.classList.toggle("dirty", dirty);
      if (dirty) total++;

      const pv = document.getElementById("te-pv-" + input.dataset.teKey);
      if (pv) pv.textContent = (input.value || "").trim() || input.placeholder || "\u2014";
    });
    if (countEl) countEl.textContent = String(total);

    editor.querySelectorAll(".te-group").forEach((group) => {
      const badge = group.querySelector("[data-badge]");
      if (!badge) return;
      const count = group.querySelectorAll("[data-te-key].dirty").length;
      badge.textContent = String(count);
      badge.setAttribute("data-count", String(count));
    });
  }

  function resetGroup(gid) {
    editor.querySelectorAll(".g" + gid + " [data-te-key]").forEach((input) => {
      input.value = "";
    });
    refresh();
  }

  editor.addEventListener("input", (event) => {
    if (event.target.matches("[data-te-key]")) refresh();
  });
  editor.addEventListener("click", (event) => {
    const resetBtn = event.target.closest("[data-reset-group]");
    if (resetBtn) {
      resetGroup(resetBtn.getAttribute("data-reset-group"));
      return;
    }
    if (event.target.closest("#te-reset-all")) {
      editor.querySelectorAll("[data-te-key]").forEach((input) => {
        input.value = "";
      });
      refresh();
    }
  });

  refresh();
}