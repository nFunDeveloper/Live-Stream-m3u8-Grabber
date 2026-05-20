# Stage 1: Build the frontend dashboard
FROM node:20-alpine AS frontend-builder
WORKDIR /build

COPY src/ui/package*.json ./
RUN npm install

COPY src/ui/ ./
RUN npm run build

# Stage 2: Runtime environment with Python
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend files
COPY src/ .

# Copy built frontend assets to the static directory used by Flask
COPY --from=frontend-builder /build/dist ./ui/dist

EXPOSE 9999

CMD ["python", "app.py"]

