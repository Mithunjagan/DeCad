FROM node:22-bookworm-slim AS builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/app ./app
COPY frontend/public ./public
COPY frontend/next.config.mjs ./
ENV NODE_OPTIONS=--max-old-space-size=512 NEXT_TELEMETRY_DISABLED=1 INTERNAL_API_URL=http://kicad:8000
RUN npm run build
FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
