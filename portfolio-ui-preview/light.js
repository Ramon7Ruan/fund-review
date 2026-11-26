"use strict";

(() => {
  const layer = document.getElementById("ambient-light");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const home = { x: .7, y: .39 };
  const point = { ...home };
  const target = { ...home };
  let frame = 0;
  let last = 0;

  function paint() {
    layer.style.setProperty("--light-x", `${(point.x * 100).toFixed(2)}%`);
    layer.style.setProperty("--light-y", `${(point.y * 100).toFixed(2)}%`);
  }

  function tick(now) {
    const progress = 1 - Math.exp(-Math.min(last ? now - last : 16, 40) / 145);
    last = now;
    point.x += (target.x - point.x) * progress;
    point.y += (target.y - point.y) * progress;
    paint();
    if (Math.hypot(point.x - target.x, point.y - target.y) > .001) {
      frame = requestAnimationFrame(tick);
    } else {
      frame = 0;
      last = 0;
    }
  }

  function follow(x, y) {
    if (reduced.matches) return;
    Object.assign(target, { x, y });
    if (!frame) frame = requestAnimationFrame(tick);
  }

  function release() {
    follow(home.x, home.y);
  }

  function reset() {
    cancelAnimationFrame(frame);
    frame = 0;
    last = 0;
    Object.assign(point, home);
    Object.assign(target, home);
    paint();
  }

  window.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    follow(event.clientX / window.innerWidth, event.clientY / window.innerHeight);
  }, { passive: true });
  document.documentElement.addEventListener("pointerleave", release);
  window.addEventListener("blur", release);
  reduced.addEventListener("change", reset);
})();
