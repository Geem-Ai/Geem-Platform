import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const dist = join(process.cwd(), 'dist');
const failures = [];
const siteUrl = (process.env.PUBLIC_SITE_URL || 'https://geem.ai').replace(/\/$/, '');
const socialImageName = 'og-geem.jpg';
const socialImageUrl = `${siteUrl}/${socialImageName}`;
const localizedPages = ['', 'about', 'agent-ai', 'contact', 'pdpl', 'privacy', 'security', 'terms'];
const imageAlt = {
  ar: 'هوية جيم البصرية مع خبير ذكاء اصطناعي متصل بمعرفة المنشأة وأنظمتها فوق أفق سعودي',
  en: 'Geem AI Expert connected to an organization’s knowledge and systems over a Saudi skyline',
};

function assert(condition, message) {
  if (!condition) failures.push(message);
}

function occurrences(haystack, needle) {
  return haystack.split(needle).length - 1;
}

function assertTagOnce(html, tag, label) {
  assert(occurrences(html, tag) === 1, `${label}: expected exactly one ${tag}`);
}

function jpegDimensions(path) {
  const data = readFileSync(path);
  if (data[0] !== 0xff || data[1] !== 0xd8) return null;

  let offset = 2;
  const startOfFrameMarkers = new Set([
    0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf,
  ]);

  while (offset + 8 < data.length) {
    if (data[offset] !== 0xff) {
      offset += 1;
      continue;
    }

    const marker = data[offset + 1];
    offset += 2;
    if (marker === 0xd8 || marker === 0xd9) continue;
    if (marker === 0xda) break;

    const segmentLength = data.readUInt16BE(offset);
    if (startOfFrameMarkers.has(marker)) {
      return {
        height: data.readUInt16BE(offset + 3),
        width: data.readUInt16BE(offset + 5),
      };
    }
    offset += segmentLength;
  }

  return null;
}

assert(existsSync(join(dist, 'index.html')), 'dist/index.html missing');
assert(existsSync(join(dist, 'ar/index.html')), 'dist/ar/index.html missing');
assert(existsSync(join(dist, 'en/index.html')), 'dist/en/index.html missing');
assert(existsSync(join(dist, 'agent-ai/index.html')), 'dist/agent-ai/index.html missing');
assert(existsSync(join(dist, 'robots.txt')), 'robots.txt missing');
assert(existsSync(join(dist, 'sitemap-index.xml')), 'sitemap-index.xml missing');
assert(existsSync(join(dist, socialImageName)), `${socialImageName} missing`);

const root = readFileSync(join(dist, 'index.html'), 'utf8');
assert(root.includes('/ar'), 'root index should redirect to /ar');
assert(root.includes('name="robots" content="noindex"'), 'root index should be noindex');
assert(
  root.includes(`<link rel="canonical" href="${siteUrl}/ar">`),
  'root index should canonicalize to /ar',
);

const ar = readFileSync(join(dist, 'ar/index.html'), 'utf8');
const en = readFileSync(join(dist, 'en/index.html'), 'utf8');
const agentAiRedirect = readFileSync(join(dist, 'agent-ai/index.html'), 'utf8');

assert(agentAiRedirect.includes('/ar/agent-ai'), 'root agent-ai should redirect to /ar/agent-ai');
assert(agentAiRedirect.includes('name="robots" content="noindex,follow"'), 'root agent-ai should be noindex');
assert(
  agentAiRedirect.includes(`<link rel="canonical" href="${siteUrl}/ar/agent-ai">`),
  'root agent-ai should canonicalize to /ar/agent-ai',
);

assert(ar.includes('lang="ar"'), 'Arabic lang');
assert(ar.includes('dir="rtl"'), 'Arabic dir=rtl');
assert(en.includes('lang="en"'), 'English lang');
assert(en.includes('dir="ltr"'), 'English dir=ltr');

for (const locale of ['ar', 'en']) {
  for (const page of localizedPages) {
    const suffix = page ? `/${page}` : '';
    const label = `${locale}${suffix || '/home'}`;
    const file = page
      ? join(dist, locale, page, 'index.html')
      : join(dist, locale, 'index.html');
    assert(existsSync(file), `${label}: generated HTML missing`);
    if (!existsSync(file)) continue;

    const html = readFileSync(file, 'utf8');
    const canonical = `${siteUrl}/${locale}${suffix}`;
    const alternateAr = `${siteUrl}/ar${suffix}`;
    const alternateEn = `${siteUrl}/en${suffix}`;

    assert(html.includes('<title>'), `${label}: title`);
    assert(html.includes('name="description"'), `${label}: description`);
    assert(html.includes('name="robots" content="index,follow"'), `${label}: index,follow robots`);
    assertTagOnce(html, '<link rel="canonical"', `${label}: canonical`);
    assert(
      html.includes(`<link rel="canonical" href="${canonical}">`),
      `${label}: canonical should be ${canonical}`,
    );
    assert(
      html.includes(`<link rel="alternate" hreflang="ar" href="${alternateAr}">`),
      `${label}: Arabic alternate`,
    );
    assert(
      html.includes(`<link rel="alternate" hreflang="en" href="${alternateEn}">`),
      `${label}: English alternate`,
    );
    assert(
      html.includes(`<link rel="alternate" hreflang="x-default" href="${alternateAr}">`),
      `${label}: x-default alternate`,
    );
    assert(html.includes(`<meta property="og:url" content="${canonical}">`), `${label}: og:url`);
    assert(html.includes(`<meta property="og:image" content="${socialImageUrl}">`), `${label}: og:image`);
    assert(
      html.includes(`<meta property="og:image:secure_url" content="${socialImageUrl}">`),
      `${label}: og:image:secure_url`,
    );
    assert(html.includes('property="og:image:type" content="image/jpeg"'), `${label}: og:image:type`);
    assert(html.includes('property="og:image:width" content="1200"'), `${label}: og:image:width`);
    assert(html.includes('property="og:image:height" content="630"'), `${label}: og:image:height`);
    assert(
      html.includes(`<meta property="og:image:alt" content="${imageAlt[locale]}">`),
      `${label}: localized og:image:alt`,
    );
    assert(html.includes('name="twitter:card" content="summary_large_image"'), `${label}: Twitter card`);
    assert(html.includes(`<meta name="twitter:image" content="${socialImageUrl}">`), `${label}: Twitter image`);
    assert(
      html.includes(`<meta name="twitter:image:alt" content="${imageAlt[locale]}">`),
      `${label}: localized Twitter image alt`,
    );
    assert(html.includes('property="og:title"'), `${label}: og:title`);
    assert(html.includes('application/ld+json'), `${label}: JSON-LD`);
    assert(!html.includes('geem.ai/assets/'), `${label}: no hotlinked geem.ai assets`);
  }
}

for (const locale of ['ar', 'en']) {
  const agentAi = readFileSync(join(dist, locale, 'agent-ai', 'index.html'), 'utf8');
  assert(agentAi.includes('/api/v1/agent'), `${locale}/agent-ai: Agent base URL`);
  assert(agentAi.includes('dalseen/geem-1.0'), `${locale}/agent-ai: public model`);
  assert(agentAi.includes('agent:write'), `${locale}/agent-ai: required scope`);
  assert(agentAi.includes('X-Geem-Expert-Id'), `${locale}/agent-ai: Expert header`);
  assert(agentAi.includes('openai-compatible'), `${locale}/agent-ai: Laravel provider`);
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

const socialImagePath = join(dist, socialImageName);
if (existsSync(socialImagePath)) {
  const dimensions = jpegDimensions(socialImagePath);
  assert(dimensions?.width === 1200, `${socialImageName}: width should be 1200`);
  assert(dimensions?.height === 630, `${socialImageName}: height should be 630`);
  assert(statSync(socialImagePath).size <= 500_000, `${socialImageName}: should be no larger than 500 KB`);
}

const sitemapPath = join(dist, 'sitemap-0.xml');
assert(existsSync(sitemapPath), 'sitemap-0.xml missing');
if (existsSync(sitemapPath)) {
  const sitemap = readFileSync(sitemapPath, 'utf8');
  assert(occurrences(sitemap, `<loc>${siteUrl}</loc>`) === 0, 'sitemap should exclude redirecting root URL');
  assert(occurrences(sitemap, `<loc>${siteUrl}/</loc>`) === 0, 'sitemap should exclude redirecting root URL with slash');
  assert(occurrences(sitemap, `<loc>${siteUrl}/agent-ai</loc>`) === 0, 'sitemap should exclude redirecting agent-ai URL');
  for (const locale of ['ar', 'en']) {
    for (const page of localizedPages) {
      const suffix = page ? `/${page}` : '';
      const canonical = `${siteUrl}/${locale}${suffix}`;
      assert(
        occurrences(sitemap, `<loc>${canonical}</loc>`) === 1,
        `sitemap should contain ${canonical} exactly once`,
      );
    }
  }
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
