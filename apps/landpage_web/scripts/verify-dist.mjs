import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const dist = join(process.cwd(), 'dist');
const failures = [];

function assert(condition, message) {
  if (!condition) failures.push(message);
}

assert(existsSync(join(dist, 'index.html')), 'dist/index.html missing');
assert(existsSync(join(dist, 'ar/index.html')), 'dist/ar/index.html missing');
assert(existsSync(join(dist, 'en/index.html')), 'dist/en/index.html missing');
assert(existsSync(join(dist, 'robots.txt')), 'robots.txt missing');
assert(existsSync(join(dist, 'sitemap-index.xml')), 'sitemap-index.xml missing');
assert(existsSync(join(dist, 'og-image.webp')), 'og-image.webp missing');

const root = readFileSync(join(dist, 'index.html'), 'utf8');
assert(root.includes('/ar'), 'root index should redirect to /ar');

const ar = readFileSync(join(dist, 'ar/index.html'), 'utf8');
const en = readFileSync(join(dist, 'en/index.html'), 'utf8');

assert(ar.includes('lang="ar"'), 'Arabic lang');
assert(ar.includes('dir="rtl"'), 'Arabic dir=rtl');
assert(en.includes('lang="en"'), 'English lang');
assert(en.includes('dir="ltr"'), 'English dir=ltr');

for (const [label, html] of [
  ['ar', ar],
  ['en', en],
]) {
  assert(html.includes('<title>'), `${label}: title`);
  assert(html.includes('name="description"'), `${label}: description`);
  assert(html.includes('rel="canonical"'), `${label}: canonical`);
  assert(html.includes('hreflang="ar"'), `${label}: hreflang ar`);
  assert(html.includes('hreflang="en"'), `${label}: hreflang en`);
  assert(html.includes('hreflang="x-default"'), `${label}: hreflang x-default`);
  assert(html.includes('property="og:title"'), `${label}: og:title`);
  assert(html.includes('application/ld+json'), `${label}: JSON-LD`);
  assert(!html.includes('geem.ai/assets/'), `${label}: no hotlinked geem.ai assets`);
}

assert(ar.includes('خبراء') || ar.includes('خبير'), 'AR homepage mentions Experts');
assert(ar.includes('مستندات') || ar.includes('معرفة'), 'AR homepage mentions documents/knowledge');
assert(ar.includes('WhatsApp') || ar.includes('واتساب'), 'AR homepage mentions WhatsApp');
assert(ar.includes('موقع') || ar.includes('ودجت'), 'AR homepage mentions website');
assert(ar.includes('chat/completions') || ar.includes('dalseen/geem-1.0'), 'AR homepage includes API sample');
assert(en.includes('Experts'), 'EN homepage mentions Experts');
assert(en.includes('documents') || en.includes('knowledge'), 'EN homepage mentions documents/knowledge');
assert(en.includes('chat/completions') || en.includes('dalseen/geem-1.0'), 'EN homepage includes API sample');
assert(!ar.includes('RAG'), 'AR homepage should avoid RAG jargon');
assert(!en.includes('RAG'), 'EN homepage should avoid RAG jargon');
assert(!en.includes('OpenWA'), 'EN homepage should avoid OpenWA jargon');
assert(!ar.includes('OpenWA'), 'AR homepage should avoid OpenWA jargon');

const inner = ['about', 'contact', 'privacy', 'terms', 'pdpl', 'security'];
for (const page of inner) {
  assert(existsSync(join(dist, 'ar', page, 'index.html')), `missing /ar/${page}`);
  assert(existsSync(join(dist, 'en', page, 'index.html')), `missing /en/${page}`);
}

const astroDir = join(dist, '_astro');
const jsFiles = existsSync(astroDir)
  ? readdirSync(astroDir).filter((f) => f.endsWith('.js'))
  : [];
const largeJs = jsFiles.filter((f) => {
  const size = readFileSync(join(astroDir, f)).byteLength;
  return size > 50_000;
});
assert(largeJs.length === 0, `Unexpected large JS bundles: ${largeJs.join(', ') || 'none'}`);

if (failures.length) {
  console.error('verify-dist failed:');
  for (const f of failures) console.error(' -', f);
  process.exit(1);
}

console.log('verify-dist OK');
console.log(` JS files in _astro: ${jsFiles.length}`);
