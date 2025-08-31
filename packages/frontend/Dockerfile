# Frontend Dockerfile for ECS deployment
# Use ECR Public Gallery Node image to avoid Docker Hub rate limits
FROM public.ecr.aws/docker/library/node:20-alpine AS builder

# Install dependencies
RUN apk add --no-cache libc6-compat
RUN npm install -g pnpm

WORKDIR /app

# Build-time envs for Next.js public runtime
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_ECS_BACKEND_URL
ARG NEXT_PUBLIC_WEBSOCKET_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_ECS_BACKEND_URL=$NEXT_PUBLIC_ECS_BACKEND_URL
ENV NEXT_PUBLIC_WEBSOCKET_URL=$NEXT_PUBLIC_WEBSOCKET_URL

# Copy package files first
COPY packages/frontend/package.json ./
COPY packages/frontend/pnpm-lock.yaml* ./

# Install dependencies
RUN pnpm install

# Copy source files (excluding node_modules)
COPY packages/frontend/src ./src
COPY packages/frontend/public ./public
COPY packages/frontend/*.js ./
COPY packages/frontend/*.ts ./
COPY packages/frontend/*.json ./
COPY packages/frontend/*.mjs ./
COPY packages/frontend/tailwind.config.* ./
COPY packages/frontend/next.config.* ./
COPY packages/frontend/postcss.config.* ./
COPY packages/frontend/tsconfig* ./
COPY packages/frontend/components.json ./

# Build the application with memory optimization
ENV NEXT_TELEMETRY_DISABLED=1
ENV SKIP_ESLINT=true
ENV NODE_OPTIONS="--max-old-space-size=2048"
RUN pnpm build

# Production image, copy all the files and run next
FROM public.ecr.aws/docker/library/node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public

# Set the correct permission for prerender cache
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Automatically leverage output traces to reduce image size
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]