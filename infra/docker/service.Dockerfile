# one image recipe for every python service; pick the service via build arg
# (build context is the repo root)
FROM python:3.12-slim
ARG SERVICE

WORKDIR /srv
COPY libs/core /srv/libs/core
COPY infra/docker/requirements/${SERVICE}.txt /tmp/requirements.txt
RUN pip install --no-cache-dir /srv/libs/core -r /tmp/requirements.txt

COPY services/${SERVICE} /srv/${SERVICE}
# command comes from docker-compose.yml
