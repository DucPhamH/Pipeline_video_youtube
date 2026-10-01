# Frontend production — build Vite rồi serve bằng nginx (proxy /api → crawl-service).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# Browser gọi cùng origin; nginx proxy /api → backend trong mạng compose.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ARG VITE_TRANSLATE_API_BASE_URL=
ENV VITE_TRANSLATE_API_BASE_URL=$VITE_TRANSLATE_API_BASE_URL
ARG VITE_TTS_API_BASE_URL=
ENV VITE_TTS_API_BASE_URL=$VITE_TTS_API_BASE_URL
ARG VITE_WRITE_API_BASE_URL=
ENV VITE_WRITE_API_BASE_URL=$VITE_WRITE_API_BASE_URL
ARG VITE_AI_API_BASE_URL=
ENV VITE_AI_API_BASE_URL=$VITE_AI_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
