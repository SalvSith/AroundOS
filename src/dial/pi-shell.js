/* Invisible desktop integration. Upstream drawing/animation code is unchanged. */
(() => {
  'use strict';
  const exit = () => fetch('/app/close', {
    method: 'POST', headers: {'X-Dial-Token': '__DIAL_TOKEN__'}
  });
  // Swipe down from the top centre of the screen to return to the desktop.
  // No permanent controls cover the original watch face.
  let start = null;
  document.addEventListener('pointerdown', e => {
    start = e.isPrimary && e.clientY < innerHeight * 0.09 &&
      Math.abs(e.clientX - innerWidth / 2) < innerWidth * 0.18
      ? {x: e.clientX, y: e.clientY, id: e.pointerId} : null;
  }, true);
  document.addEventListener('pointermove', e => {
    if (!start || e.pointerId !== start.id) return;
    if (Math.abs(e.clientX - start.x) > innerWidth * 0.12) { start = null; return; }
    if (e.clientY - start.y > innerHeight * 0.18) { start = null; exit(); }
  }, true);
  for (const type of ['pointerup', 'pointercancel']) {
    document.addEventListener(type, () => { start = null; }, true);
  }
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !document.getElementById('wf-overlay').classList.contains('wf-active')) {
      e.preventDefault(); exit();
    }
  }, true);
})();
