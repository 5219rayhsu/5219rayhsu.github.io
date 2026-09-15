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

  /* ---------- lazy image load-in (fade + rise, same easing as [data-reveal]) ----------
     Applies only to loading="lazy" content images (never nav/favicon icons, which
     don't carry that attribute). Cached images (already complete on attach — e.g.
     a repeat visit) get .is-loaded immediately so they never sit invisible; a real
     network load or a decode error both resolve the same way so alt text is never
     permanently hidden. */
  document.querySelectorAll('img[loading="lazy"]').forEach((img) => {
    const markLoaded = () => img.classList.add("is-loaded");
    if (img.complete && img.naturalWidth > 0) {
      markLoaded();
    } else {
      img.addEventListener("load", markLoaded, { once: true });
      img.addEventListener("error", markLoaded, { once: true });
    }
  });

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
      // 手機版 .hero__media 是 object-fit:contain（就是為了「整張看得到」）。
      // 這時再 scale 會反過來把圖切掉：左右各吃掉 2%，加上 transform-origin
      // 在正中央，上緣也被切掉約 8px——正是站主 2026-07-28 回報的「上方切到圖」。
      // 桌機版是寬版視窗、contain 後左右本來就留黑邊，放大 4% 只吃到黑邊，無害。
      const zoom = window.innerWidth <= 700 ? 1 : 1.04;
      heroMedia.style.transform = `translate3d(0, ${y * 0.22}px, 0) scale(${zoom})`;
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

  /* ---------- lightbox: browse images in page order ---------- */
  const lightbox = document.querySelector("[data-lightbox]");
  const lightboxImg = lightbox?.querySelector(".lightbox__img");
  const lightboxClose = lightbox?.querySelector(".lightbox__close");
  const language = document.documentElement.lang;
  const labels = language.startsWith("ja")
    ? { open: "画像を拡大", close: "閉じる", previous: "前の作品", next: "次の作品", gallery: "作品画像", error: "画像を読み込めません。前後の作品へ移動できます。" }
    : language.startsWith("en")
    ? { open: "View larger", close: "Close", previous: "Previous artwork", next: "Next artwork", gallery: "Artwork images", error: "Image could not load. You can still browse previous or next artworks." }
    : { open: "放大檢視", close: "關閉", previous: "上一件作品", next: "下一件作品", gallery: "作品圖片", error: "圖片暫時無法載入，仍可切換前後作品。" };
  const zoomables = [...document.querySelectorAll(
    ".filmstrip, .idgrid, .work, .collage-item__media, .gallery__item"
  )].filter(el => el.querySelector("img"));
  let currentImage = 0;
  let lastFocused = null;
  let previousOverflow = "";

  if (lightbox && lightboxImg && lightboxClose && zoomables.length) {
    lightbox.setAttribute("role", "dialog");
    lightbox.setAttribute("aria-modal", "true");
    lightbox.setAttribute("aria-label", labels.gallery);
    lightboxClose.setAttribute("aria-label", labels.close);
    const lightboxCap = lightbox.querySelector(".lightbox__cap") || document.createElement("p");
    lightboxCap.className = "lightbox__cap";
    lightbox.appendChild(lightboxCap);
    const controls = document.createElement("div");
    controls.className = "lightbox__controls";
    const previous = document.createElement("button");
    const next = document.createElement("button");
    const counter = document.createElement("span");
    counter.className = "lightbox__counter";
    counter.setAttribute("aria-live", "polite");
    counter.setAttribute("aria-atomic", "true");
    [previous, next].forEach((button, index) => {
      button.type = "button";
      button.className = "lightbox__arrow " + (index ? "lightbox__next" : "lightbox__previous");
      button.setAttribute("aria-label", index ? labels.next : labels.previous);
      button.textContent = index ? "→" : "←";
      button.disabled = zoomables.length < 2;
    });
    controls.append(previous, counter, next);
    lightbox.appendChild(controls);

    function showImage(index) {
      currentImage = (index + zoomables.length) % zoomables.length;
      const element = zoomables[currentImage];
      const img = element.querySelector("img");
      lightboxImg.alt = img.alt || "";
      lightboxCap.textContent = (element.querySelector("figcaption")?.textContent || img.alt || "").trim();
      counter.textContent = `${currentImage + 1} / ${zoomables.length}`;
      lightboxImg.src = img.dataset.full || img.src || img.currentSrc;
    }
    function openLightbox(element) {
      lastFocused = document.activeElement;
      previousOverflow = document.body.style.overflow;
      showImage(zoomables.indexOf(element));
      lightbox.hidden = false;
      document.body.style.overflow = "hidden";
      lightboxClose.focus();
    }
    function closeLightbox() {
      if (lightbox.hidden) return;
      lightbox.hidden = true;
      lightboxImg.removeAttribute("src");
      lightboxCap.textContent = "";
      document.body.style.overflow = previousOverflow;
      lastFocused?.focus({ preventScroll: true });
    }
    lightboxImg.addEventListener("error", () => {
      if (!lightbox.hidden) lightboxCap.textContent = labels.error;
    });
    zoomables.forEach(element => {
      element.setAttribute("role", "button");
      element.setAttribute("tabindex", "0");
      element.setAttribute("aria-label", `${labels.open}: ${element.querySelector("img").alt || labels.gallery}`);
      element.addEventListener("click", () => openLightbox(element));
      element.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openLightbox(element);
        }
      });
    });
    previous.addEventListener("click", () => showImage(currentImage - 1));
    next.addEventListener("click", () => showImage(currentImage + 1));
    lightboxClose.addEventListener("click", closeLightbox);
    lightbox.addEventListener("click", event => {
      if (event.target === lightbox) closeLightbox();
    });
    document.addEventListener("keydown", event => {
      if (lightbox.hidden) return;
      if (event.key === "Escape") closeLightbox();
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        showImage(currentImage + (event.key === "ArrowRight" ? 1 : -1));
      }
      if (event.key === "Tab") {
        const buttons = [lightboxClose, previous, next].filter(button => !button.disabled);
        const index = buttons.indexOf(document.activeElement);
        event.preventDefault();
        buttons[(index + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length].focus();
      }
    });
    let touchStart = null;
    lightboxImg.addEventListener("touchstart", event => {
      touchStart = event.touches.length === 1 ? { x: event.touches[0].clientX, y: event.touches[0].clientY } : null;
    }, { passive: true });
    lightboxImg.addEventListener("touchend", event => {
      if (!touchStart || !event.changedTouches.length) return;
      const dx = event.changedTouches[0].clientX - touchStart.x;
      const dy = event.changedTouches[0].clientY - touchStart.y;
      touchStart = null;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) showImage(currentImage + (dx < 0 ? 1 : -1));
    }, { passive: true });
    lightboxImg.addEventListener("touchcancel", () => { touchStart = null; });
  }

  /* ---------- YouTube facade (click-to-load embed, avoids upfront iframe cost) ---------- */
  document.querySelectorAll(".video-embed__facade").forEach((facade) => {
    facade.addEventListener("click", () => {
      const videoId = facade.dataset.videoId;
      if (!videoId) return;
      const title = facade.dataset.videoTitle || "YouTube video";
      const iframe = document.createElement("iframe");
      iframe.src = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&playsinline=1`;
      iframe.title = title;
      iframe.setAttribute("allow", "autoplay; encrypted-media; picture-in-picture");
      iframe.setAttribute("allowfullscreen", "");
      facade.replaceWith(iframe);
    });
  });

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
