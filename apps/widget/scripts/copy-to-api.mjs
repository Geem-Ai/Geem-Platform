import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const destDir = resolve(root, '../../api/app/widgets/static');
mkdirSync(destDir, { recursive: true });

const jsSrc = resolve(root, '../dist/geem-widget.js');
const jsDest = resolve(destDir, 'geem-widget.js');
copyFileSync(jsSrc, jsDest);
console.log(`Copied ${jsSrc} -> ${jsDest}`);

const mascotCandidates = [
  resolve(root, '../../workspace_web/public/brand/geem-animated.svg'),
  resolve(destDir, 'geem-animated.svg'),
];
const mascotSrc = mascotCandidates.find((path) => existsSync(path));
if (mascotSrc) {
  const mascotDest = resolve(destDir, 'geem-animated.svg');
  copyFileSync(mascotSrc, mascotDest);
  console.log(`Copied ${mascotSrc} -> ${mascotDest}`);
} else {
  console.warn('geem-animated.svg not found; launcher will fall back to icon');
}
