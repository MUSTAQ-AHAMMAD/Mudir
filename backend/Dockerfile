# Mudir backend — production image
# Multi-stage build keeps the final image small and free of dev dependencies.

# ---- deps stage: install only production dependencies -----------------------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

# ---- runtime stage ----------------------------------------------------------
FROM node:20-alpine AS runtime
ENV NODE_ENV=production
WORKDIR /app

# Run as a non-root user for security.
RUN addgroup -S mudir && adduser -S mudir -G mudir

COPY --from=deps /app/node_modules ./node_modules
COPY package.json ./
COPY src ./src
COPY migrations ./migrations

USER mudir
EXPOSE 3000

# Basic container healthcheck hitting the /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/health || exit 1

CMD ["node", "src/index.js"]
