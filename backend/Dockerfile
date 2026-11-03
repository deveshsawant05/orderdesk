FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY . .
RUN useradd -m orderdesk
USER orderdesk
EXPOSE 8000
