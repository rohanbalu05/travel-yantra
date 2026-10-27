# apps/web as a Next.js standalone server on Cloud Run. Build from the repo root:
#   docker build -f infra/web/Dockerfile --build-arg NEXT_PUBLIC_API_BASE_URL=https://... .
# The web app imports packages/contracts/ts, so the context must be the root.

FROM node:22-slim AS build
WORKDIR /repo
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/
RUN cd apps/web && pnpm install --frozen-lockfile
COPY packages/contracts/ts packages/contracts/ts
COPY apps/web apps/web
# NEXT_PUBLIC_* values are inlined at build time.
ARG NEXT_PUBLIC_API_BASE_URL=""
# Firebase web config for Google sign-in (V3-AG): public client config, empty = sign-in off.
ARG NEXT_PUBLIC_FIREBASE_API_KEY=""
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=""
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID=""
ARG NEXT_PUBLIC_FIREBASE_APP_ID=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY \
    NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN \
    NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID \
    NEXT_PUBLIC_FIREBASE_APP_ID=$NEXT_PUBLIC_FIREBASE_APP_ID
# public/ is optional in apps/web; make sure the runtime COPY has a source.
RUN cd apps/web && mkdir -p public && pnpm build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=8080
# Standalone output leaves static assets and public/ out; copy them beside server.js.
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./.next/static
COPY --from=build --chown=node:node /repo/apps/web/public ./public
USER node
EXPOSE 8080
CMD ["node", "server.js"]
