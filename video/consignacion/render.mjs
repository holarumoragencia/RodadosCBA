// Renderiza index.html cuadro por cuadro sobre los fondos procesados (work/bg, generados por fx.py)
// y lo codifica a MP4 con el audio del video fuente.
// Uso: node render.mjs [salida.mp4] [--frames=1,2.5,9]  (con --frames exporta JPGs de prueba)
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const FPS = 24;
const dir = path.dirname(fileURLToPath(import.meta.url));
const out = process.argv.find(a => a.endsWith('.mp4')) || path.join(dir, 'rodados-0km.mp4');
const framesArg = process.argv.find(a => a.startsWith('--frames='));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 } });
await page.goto(pathToFileURL(path.join(dir, 'index.html')).href);
await page.evaluate(() => window.ready);
const duration = await page.evaluate(() => window.DURATION);

const shot = async t => {
  await page.evaluate(t => window.render(t), t);
  return page.screenshot({ type: 'jpeg', quality: 95 });
};

if (framesArg) {
  fs.mkdirSync(path.join(dir, 'work', 'test'), { recursive: true });
  for (const t of framesArg.slice(9).split(',').map(Number)) {
    fs.writeFileSync(path.join(dir, 'work', 'test', `t${t.toFixed(2)}.jpg`), await shot(t));
  }
} else {
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-i', '-',
    '-i', path.join(dir, 'work', 'fuente.mp4'), '-map', '0:v', '-map', '1:a', '-shortest',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
    '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const total = Math.round(duration * FPS);
  for (let f = 0; f < total; f++) {
    const buf = await shot(f / FPS);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (f % 48 === 0) console.log(`cuadro ${f}/${total}`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  console.log('listo:', out);
}
await browser.close();
