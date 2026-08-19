# Build the Vite SPA, serve the static bundle with nginx.
#
# The VITE_* values are baked in at BUILD time (Vite inlines them), so the
# gateway/supabase/interview URLs must be known when this image is built - pass
# them as --build-arg (the build-and-push script and README show how). Rebuild
# the UI image whenever those public URLs change.
FROM node:20-alpine AS build
WORKDIR /app
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
ARG VITE_GATEWAY_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_INTERVIEW_URL
ENV VITE_GATEWAY_URL=$VITE_GATEWAY_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_INTERVIEW_URL=$VITE_INTERVIEW_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
