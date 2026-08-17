# Standalone simulation image containing the unified simulation package.
FROM python:3.11-slim

WORKDIR /srv

COPY infra/docker/requirements/simulation.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/simulation /srv/simulation

# Command is specified in docker-compose.yml:
# e.g., python -m simulation.run --type cstr
