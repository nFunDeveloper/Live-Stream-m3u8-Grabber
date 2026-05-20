FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend files and prebuilt frontend assets.
# Build the React UI locally before deploying; the low-spec server should not run npm.
COPY src/ .

EXPOSE 9999

CMD ["python", "app.py"]
