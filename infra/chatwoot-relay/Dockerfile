FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && useradd --uid 10001 --create-home relay && mkdir -p /var/lib/channel-relay && chown relay:relay /var/lib/channel-relay
COPY --chown=relay:relay main.py ./
USER relay
EXPOSE 8090
CMD ["uvicorn", "main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8090", "--workers", "1", "--no-access-log", "--no-server-header"]
