const bar = document.getElementById('bar');
const sub = document.getElementById('sub');
let pct = 0;
const timer = setInterval(() => {
  pct = Math.min(100, pct + Math.random() * 15 + 5);
  bar.style.width = pct + '%';
  if (pct > 95) sub.textContent = 'Almost there...';
  if (pct >= 100) clearInterval(timer);
}, 250);

setTimeout(async () => {
  // After 4 seconds main will decide where to navigate
  // No-op here; main process handles it.
}, 4000);
