/* =================================================================
   許哲睿 HSU Che-jui — interactions
   Scroll reveals · nav state · hero parallax · lightbox
   (forked from the prototype main.js; adds .gallery__item to the
   lightbox targets. All behaviour is progressive: pages without a
   given element simply skip it.)
   ================================================================= */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- language switch: preserve scroll position (2026-07-11D #1) ----------
     Click on a non-current .nav__lang link: remember where we are (nearest
     in-viewport [id] anchor, else scroll ratio) in sessionStorage. The next
     page checks it on load, jumps instantly (no smooth animation), then
     clears the key so normal navigation is never affected. */
  const LANG_SCROLL_KEY = "langSwitchScroll";

  function nearestAnchorId() {
    const ids = Array.from(document.querySelectorAll("main [id]")).filter(
      (el) => el.id && el.id !== "main" && el.id !== "top"
    );
    if (!ids.length) return null;
    const ref = window.scrollY + window.innerHeight * 0.3;
    let best = null,
      bestTop = -Infinity;
    ids.forEach((el) => {
      const top = el.getBoundingClientRect().top + window.scrollY;
      if (top <= ref && top > bestTop) {
        bestTop = top;
        best = el.id;
      }
    });
    return best || ids[0].id;
  }

  document.querySelectorAll(".nav__lang a:not(.is-current)").forEach((a) => {
    a.addEventListener("click", () => {
      const anchorId = nearestAnchorId();
      const payload = anchorId
        ? { type: "anchor", id: anchorId }
        : {
            type: "ratio",
            value:
              window.scrollY /
              Math.max(1, document.documentElement.scrollHeight - window.innerHeight),
          };
      try {
        sessionStorage.setItem(LANG_SCROLL_KEY, JSON.stringify(payload));
      } catch (e) {
        /* sessionStorage unavailable (private mode etc.) — fall back to top */
      }
    });
  });

  (function restoreLangSwitchScroll() {
    let raw = null;
    try {
      raw = sessionStorage.getItem(LANG_SCROLL_KEY);
    } catch (e) {
      /* no-op */
    }
    if (!raw) return;
    try {
      sessionStorage.removeItem(LANG_SCROLL_KEY);
    } catch (e) {
      /* no-op */
    }
    let data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      return;
    }
    const apply = () => {
      if (data.type === "anchor") {
        const target = document.getElementById(data.id);
        if (target) {
          target.scrollIntoView({ behavior: "auto", block: "start" });
          return;
        }
      }
      const max = document.documentElement.scrollHeight - window.innerHeight;
      window.scrollTo({ top: Math.max(0, max * (data.value || 0)), behavior: "auto" });
    };
    // force instant (html has scroll-behavior:smooth globally; JS behavior:"auto"
    // would inherit that unless we momentarily flip it off).
    const prevBehavior = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = "auto";
    apply();
    window.addEventListener("load", apply, { once: true });
    requestAnimationFrame(() => {
      document.documentElement.style.scrollBehavior = prevBehavior;
    });
  })();

  /* ---------- back-to-top floating button (2026-07-11D #2) ----------
     Injected on every page — no per-page markup needed. Fades in past
     ~1 viewport of scroll; label follows the page's own lang. */
  (function backToTop() {
    const labels = { en: "Back to top", ja: "トップへ戻る" };
    const lang = document.documentElement.lang || "";
    const label = labels[lang.slice(0, 2)] || "回到頂端";
    const totop = document.createElement("a");
    totop.href = "#top";
    totop.className = "totop";
    totop.setAttribute("aria-label", label);
    totop.setAttribute("aria-hidden", "true");
    totop.setAttribute("tabindex", "-1");
    totop.textContent = "↑";
    document.body.appendChild(totop);
    function update() {
      const visible = window.scrollY > window.innerHeight * 0.9;
      totop.classList.toggle("is-visible", visible);
      totop.setAttribute("aria-hidden", visible ? "false" : "true");
      totop.setAttribute("tabindex", visible ? "0" : "-1");
    }
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update, { passive: true });
    update();
  })();

  /* ---------- scroll reveal ---------- */
  const revealEls = document.querySelectorAll("[data-reveal]");
  if (reduceMotion || !("IntersectionObserver" in window)) {
    revealEls.forEach((el) => el.classList.add("is-visible"));
  } else {
    const io = new IntersectionObserver(
      (entries, obs) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            obs.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.08 }
    );
    revealEls.forEach((el) => io.observe(el));
  }

  /* ---------- nav state + hero parallax (single rAF loop) ---------- */
  const nav = document.querySelector("[data-nav]");
  const hero = document.querySelector(".hero");
  const heroMedia = document.querySelector(".hero__media");
  let ticking = false;

  // active-section tracking for the side quick-jump rail. Generalized (2026-07-11D
  // #7) from a CBS-only hardcoded id list: derives the tracked sections from
  // whichever #hash targets the page's own .rail--series links point to, so any
  // page that ships the rail markup (works/answer, works/medicine, texts/*, …)
  // gets working scroll-spy for free. Top-nav active state is set statically
  // per page (class="is-active") in HTML.
  const seriesLinks = document.querySelectorAll(".rail--series .rail__item");
  const seriesEls = Array.from(seriesLinks)
    .map((a) => {
      const href = a.getAttribute("href") || "";
      return href.startsWith("#") ? document.getElementById(href.slice(1)) : null;
    })
    .filter(Boolean);
  const absTop = (el) => el.getBoundingClientRect().top + window.scrollY;

  function updateActive() {
    if (!seriesLinks.length || !seriesEls.length) return;
    const mid = window.scrollY + window.innerHeight * 0.42;
    let series = null,
      bestTop = -Infinity;
    for (const el of seriesEls) {
      const t = absTop(el);
      if (t <= mid && t > bestTop) {
        bestTop = t;
        series = el.id;
      }
    }
    seriesLinks.forEach((a) =>
      a.classList.toggle("is-active", !!series && a.getAttribute("href") === "#" + series)
    );
  }

  function onScroll() {
    const y = window.scrollY;
    const switchPoint = (hero ? hero.offsetHeight : 600) - 64;
    if (nav) nav.classList.toggle("is-scrolled", y > switchPoint);

    if (heroMedia && !reduceMotion && y < (hero ? hero.offsetHeight : 0)) {
      heroMedia.style.transform = `translate3d(0, ${y * 0.22}px, 0) scale(1.04)`;
    }
    updateActive();
    ticking = false;
  }
  function requestTick() {
    if (!ticking) {
      window.requestAnimationFrame(onScroll);
      ticking = true;
    }
  }
  window.addEventListener("scroll", requestTick, { passive: true });
  window.addEventListener("resize", requestTick, { passive: true });
  onScroll();

  /* ---------- lightbox ---------- */
  const lightbox = document.querySelector("[data-lightbox]");
  const lightboxImg = lightbox ? lightbox.querySelector(".lightbox__img") : null;
  const lightboxClose = lightbox ? lightbox.querySelector(".lightbox__close") : null;
  // caption element (2026-07-11D #3): reuse it if a page already ships one,
  // otherwise inject it — keeps every existing lightbox markup working as-is.
  let lightboxCap = lightbox ? lightbox.querySelector(".lightbox__cap") : null;
  if (lightbox && !lightboxCap) {
    lightboxCap = document.createElement("p");
    lightboxCap.className = "lightbox__cap";
    lightbox.appendChild(lightboxCap);
  }
  const zoomables = document.querySelectorAll(
    ".filmstrip, .idgrid, .work, .collage-item__media, .gallery__item"
  );
  let lastFocused = null;

  function openLightbox(srcEl) {
    const img = srcEl.querySelector("img");
    if (!img || !lightbox) return;
    lastFocused = document.activeElement;
    lightboxImg.src = img.currentSrc || img.src;
    lightboxImg.alt = img.alt || "";
    if (lightboxCap) {
      const figcap = srcEl.querySelector("figcaption");
      lightboxCap.textContent = (figcap ? figcap.textContent : img.alt || "").trim();
    }
    lightbox.hidden = false;
    document.body.style.overflow = "hidden";
    lightboxClose.focus();
  }
  function closeLightbox() {
    if (!lightbox || lightbox.hidden) return;
    lightbox.hidden = true;
    lightboxImg.removeAttribute("src");
    if (lightboxCap) lightboxCap.textContent = "";
    document.body.style.overflow = "";
    if (lastFocused) lastFocused.focus();
  }

  zoomables.forEach((el) => {
    el.setAttribute("role", "button");
    el.setAttribute("tabindex", "0");
    el.setAttribute("aria-label", "放大檢視 View larger");
    el.addEventListener("click", () => openLightbox(el));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openLightbox(el);
      }
    });
  });

  if (lightbox) {
    lightbox.addEventListener("click", (e) => {
      if (e.target === lightbox || e.target === lightboxImg) closeLightbox();
    });
    lightboxClose.addEventListener("click", closeLightbox);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeLightbox();
    });
  }

  /* ---------- smooth anchor focus handoff (a11y) ---------- */
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", () => {
      const id = a.getAttribute("href").slice(1);
      const target = document.getElementById(id);
      if (target) {
        setTimeout(() => {
          target.setAttribute("tabindex", "-1");
          target.focus({ preventScroll: true });
        }, 600);
      }
    });
  });
})();
