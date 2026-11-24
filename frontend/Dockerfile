FROM node:24.16.0-slim AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# The API's HTTPS origin (e.g. https://api.nanai.khoofia.com); empty keeps the API on
# the page's own origin. See src/services/apiOrigin.ts.
ARG VITE_API_ORIGIN=""
ENV VITE_API_ORIGIN=${VITE_API_ORIGIN}
RUN npm run build

FROM nginx:1.31-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
