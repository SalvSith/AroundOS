// Live Pi checks through an SSH-forwarded, loopback-only Chromium diagnostic port.
// Usage: node scripts/check-dial.mjs [port] [screenshot-directory] [--exit]
import fs from 'node:fs/promises';
import path from 'node:path';

const port = Number(process.argv[2] || 9224);
const out = process.argv[3];
const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const target = targets.find(t => t.type === 'page' && t.url.startsWith('http://127.0.0.1:'));
if (!target) throw new Error('No Dial page found');
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
let serial = 0;
const pending = new Map();
const errors = [], external = [], failures = [];
ws.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const item = pending.get(message.id);
    if (!item) return;
    pending.delete(message.id); clearTimeout(item.timer);
    message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result);
  } else {
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
    if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') errors.push(message.params.args);
    if (message.method === 'Network.requestWillBeSent' && /^https?:/.test(message.params.request.url) && !message.params.request.url.startsWith(new URL(target.url).origin + '/')) external.push(message.params.request.url);
    if (message.method === 'Network.loadingFailed') failures.push(message.params);
  }
};
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timed out: ${method}`)); }, 15000);
    pending.set(id, {resolve, reject, timer});
    ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const check = (name, value) => { if (!value) throw new Error(name); console.log('PASS', name); };
async function snapshot(name) {
  if (!out) return;
  await fs.mkdir(out, {recursive: true});
  const shot = await call('Page.captureScreenshot', {format: 'png'});
  await fs.writeFile(path.join(out, name + '.png'), Buffer.from(shot.data, 'base64'));
}
const touch = (type, x, y) => call('Input.dispatchTouchEvent', {type, touchPoints: type === 'touchEnd' ? [] : [{x, y, id: 0}]});
async function hold() {
  await touch('touchStart', 540, 540); await sleep(850); await touch('touchEnd'); await sleep(1900);
}
async function settle() {
  for (let i=0;i<40;i++) {
    if (await evaluate('document.getElementById("wf-select-btn").classList.contains("active")')) return;
    await sleep(250);
  }
  throw new Error('Selector did not settle');
}
async function tapSelector(selector) {
  const point = await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
  await touch('touchStart', point.x, point.y); await touch('touchEnd'); await sleep(1100);
}
try {
  await call('Runtime.enable'); await call('Network.enable'); await call('Page.enable');
  await call('Page.bringToFront');
  await call('Network.setCacheDisabled', {cacheDisabled: true});
  await call('Page.reload', {ignoreCache: true}); await sleep(3500);
  check('1080 × 1080, device scale 1', await evaluate('innerWidth===1080 && innerHeight===1080 && devicePixelRatio===1'));
  check('Original image decoded', await evaluate('document.querySelector(".dial img").naturalWidth>0'));
  check('Offline fonts loaded', await evaluate('document.fonts.ready.then(()=>document.fonts.check(\'500 152px "Barlow Condensed"\') && document.fonts.check(\'600 32px "Cormorant Garamond"\'))'));
  check('Local graphics dependency loaded', await evaluate('typeof glMatrix!=="undefined"'));
  const first = await evaluate('document.getElementById("second-hand").style.transform');
  await sleep(1000);
  check('Clock advances', first !== await evaluate('document.getElementById("second-hand").style.transform'));
  check('Lens WebGL healthy', await evaluate('(()=>{let g=document.getElementById("cyclops-canvas").getContext("webgl");return !!g && !g.isContextLost() && g.getError()===0})()'));
  await snapshot('datejust');
  await hold();
  check('Touch hold opens selector', await evaluate('document.getElementById("wf-overlay").classList.contains("wf-active")'));
  check('Selector WebGL 2 healthy', await evaluate('(()=>{let g=document.getElementById("wf-menu-canvas").getContext("webgl2");return !!g && !g.isContextLost() && g.getError()===0})()'));
  check('Close and Apply fit the physical circle', await evaluate('Array.from(document.querySelectorAll("#wf-close,#wf-select-btn")).every(e=>{let r=e.getBoundingClientRect();return [r.left,r.right].every(x=>[r.top,r.bottom].every(y=>Math.hypot(x-540,y-540)<515))})'));
  const before = await evaluate('document.getElementById("wf-title").textContent');
  await touch('touchStart', 740, 540);
  for (let i=1;i<=12;i++) { await touch('touchMove', 740-i*35, 540+i*7); await sleep(35); }
  await touch('touchEnd'); await settle();
  const after = await evaluate('document.getElementById("wf-title").textContent');
  check('Touch drag changes selected face', !!after && before !== after);
  console.log('Selected:', after);
  await snapshot('selector');
  const preview = await evaluate('({src:document.querySelector(".dial img").src,filter:document.querySelector(".dial img").style.filter})');
  await tapSelector('#wf-select-btn');
  check('Apply returns to selected watch', await evaluate('!document.getElementById("wf-overlay").classList.contains("wf-active") && document.getElementById("watch").style.opacity==="1"'));
  await snapshot('selected');
  await hold(); await tapSelector('#wf-close');
  check('Cancel preserves applied watch', JSON.stringify(preview) === JSON.stringify(await evaluate('({src:document.querySelector(".dial img").src,filter:document.querySelector(".dial img").style.filter})')));
  check('No JavaScript errors', errors.length === 0);
  check('No external page requests', external.length === 0);
  check('No failed asset requests', failures.length === 0);
  const diagnostics = await evaluate('(()=>{let gl=document.getElementById("wf-menu-canvas").getContext("webgl2");let ext=gl.getExtension("WEBGL_debug_renderer_info");return {renderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),date:new Date().toString(),resources:performance.getEntriesByType("resource").map(e=>e.name)}})()');
  console.log(JSON.stringify(diagnostics, null, 2));
  if (process.argv.includes('--exit')) {
    await touch('touchStart', 540, 45);
    for (const y of [80, 120, 160, 200, 250]) {
      await touch('touchMove', 540, y); await sleep(30);
    }
    await sleep(1500);
    check('Swipe down exits the app', ws.readyState === WebSocket.CLOSED);
  }
} finally {
  ws.close();
  if (errors.length || external.length || failures.length) console.log(JSON.stringify({errors, external, failures}, null, 2));
}
