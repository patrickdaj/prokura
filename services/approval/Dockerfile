FROM python:3.12-slim
WORKDIR /app
# Shared telemetry module (one copy for all services — was six drifting telemetry.py).
# Installed first so its OTel deps layer-cache across every service image.
COPY sdk/prokura-telemetry /tmp/prokura-telemetry
RUN pip install --no-cache-dir /tmp/prokura-telemetry
COPY services/approval/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/approval/*.py services/approval/approval.html ./
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8120"]
