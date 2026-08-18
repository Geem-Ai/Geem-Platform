# Dev image — Vite/Astro dev server (do not use in production)
FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
EXPOSE 4321
CMD ["npm", "run", "dev"]
