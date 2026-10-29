// Disa aktarma: node scripts/render.mjs <props.json> <cikti.mp4>
// Onizlemedeki Remotion kompozisyonunun aynisini MP4'e render eder. Ilerleme "PROGRESS 0.xx" satirlariyla.
import { bundle } from '@remotion/bundler';
import { renderMedia, selectComposition } from '@remotion/renderer';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const [, , propsPath, out] = process.argv;
const inputProps = JSON.parse(fs.readFileSync(propsPath, 'utf-8'));
const here = path.dirname(fileURLToPath(import.meta.url));
const cacheDir = path.join(here, '..', '.bundle');

// paket her seferinde yeniden derlenmesin: kaynak degismediyse onceki bundle kullanilir
const srcDir = path.join(here, '..', 'src');
const stamp = (dir) => fs.readdirSync(dir, { recursive: true }).map(f => {
  const p = path.join(dir, f);
  return fs.statSync(p).mtimeMs;
}).reduce((a, b) => Math.max(a, b), 0);
const stampFile = path.join(cacheDir, 'stamp.txt');
let serveUrl;
const cur = String(stamp(srcDir));
if (fs.existsSync(stampFile) && fs.readFileSync(stampFile, 'utf-8') === cur && fs.existsSync(path.join(cacheDir, 'bundle', 'index.html'))) {
  serveUrl = path.join(cacheDir, 'bundle');
} else {
  console.log('bundle hazirlaniyor...');
  const nm = (p) => path.join(here, '..', 'node_modules', p);
  serveUrl = await bundle({
    entryPoint: path.join(srcDir, 'remotion', 'index.ts'), outDir: path.join(cacheDir, 'bundle'),
    // vite.config.ts ile ayni: captioneer bilesenleri + tek react/remotion kopyasi
    webpackOverride: (config) => ({
      ...config,
      resolve: {
        ...config.resolve,
        alias: {
          ...(config.resolve?.alias ?? {}),
          'captioneer-ui': nm('remotion-captioneer/dist/components/index.js'),
          'captioneer-presets': nm('remotion-captioneer/dist/presets/index.js'),
          react: nm('react'), 'react-dom': nm('react-dom'), remotion: nm('remotion'),
        },
      },
    }),
  });
  fs.writeFileSync(stampFile, cur);
}

const composition = await selectComposition({ serveUrl, id: 'Main', inputProps, timeoutInMilliseconds: 120000 });
console.log(`render: ${composition.durationInFrames} kare @ ${composition.fps} fps`);
let last = -1;
await renderMedia({
  composition, serveUrl, codec: 'h264', outputLocation: out, inputProps,
  crf: 18, audioBitrate: '192k', concurrency: 4,
  // makine mesgulken (Whisper/arka plan isleri) video karesi cikarma 30 sn varsayilanini asabiliyor
  timeoutInMilliseconds: 120000,
  onProgress: ({ progress }) => {
    const p = Math.floor(progress * 100);
    if (p !== last) { last = p; console.log(`PROGRESS ${progress.toFixed(3)}`); }
  },
});
console.log('DONE ' + out);
