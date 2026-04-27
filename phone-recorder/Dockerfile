# Stage 1: Build
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

# Build-time variables (baked into the static bundle by Vite)
ARG VITE_API_URL
ARG VITE_EDITION
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_GOOGLE_REDIRECT_URI
ARG VITE_DEFAULT_ADMIN_EMAIL
ARG VITE_DEFAULT_ADMIN_PASSWORD
ENV VITE_API_URL=$VITE_API_URL \
    VITE_EDITION=$VITE_EDITION \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_GOOGLE_REDIRECT_URI=$VITE_GOOGLE_REDIRECT_URI \
    VITE_DEFAULT_ADMIN_EMAIL=$VITE_DEFAULT_ADMIN_EMAIL \
    VITE_DEFAULT_ADMIN_PASSWORD=$VITE_DEFAULT_ADMIN_PASSWORD

RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]