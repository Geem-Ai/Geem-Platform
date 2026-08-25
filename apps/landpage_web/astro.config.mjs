// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

const siteUrl = (process.env.PUBLIC_SITE_URL || 'https://geem.ai').replace(/\/$/, '');
const tunnelHost = process.env.PUBLIC_TUNNEL_HOST?.trim();
const allowedHosts = ['.geem.dm', '.geem.ai', 'localhost'];

export default defineConfig({
  site: siteUrl,
  trailingSlash: 'never',
  output: 'static',
  server: {
    allowedHosts,
  },
  i18n: {
    defaultLocale: 'ar',
    locales: ['ar', 'en'],
    routing: {
      prefixDefaultLocale: true,
      redirectToDefaultLocale: false,
    },
  },
  integrations: [
    sitemap({
      filter: (page) =>
        page !== siteUrl &&
        page !== `${siteUrl}/` &&
        page !== `${siteUrl}/agent-ai` &&
        page !== `${siteUrl}/agent-ai/`,
      i18n: {
        defaultLocale: 'ar',
        locales: {
          ar: 'ar',
          en: 'en',
        },
      },
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts,
      ...(tunnelHost
        ? {
            hmr: {
              host: tunnelHost,
              protocol: 'wss',
              clientPort: 443,
            },
          }
        : {}),
    },
  },
});
