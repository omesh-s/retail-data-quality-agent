# Local / container run: API health service + project files for pipeline & ADK.
# Example: docker build -t retail-dq .
#          docker run -p 8080:8080 --env-file .env retail-dq
#
# Note: ADK web is typically run on the host with `adk web .` for dev UI;
# this image focuses on the FastAPI companion and CLI-friendly layout.

FROM python:3.13-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
