# The autoscaler drives the docker daemon rather than serving traffic, so it
# is the one image that needs a docker CLI. Taking the binaries out of the
# official cli image beats apt-getting docker into a python base.
FROM python:3.12-slim

COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:27-cli /usr/local/libexec/docker/cli-plugins/docker-compose \
     /usr/local/libexec/docker/cli-plugins/docker-compose

WORKDIR /srv
COPY libs/core /srv/libs/core
RUN pip install --no-cache-dir /srv/libs/core

COPY infra /srv/infra
COPY tools /srv/tools
# docker-compose.yml and .env are mounted, not copied: compose reads the same
# file the host does, so the two can never drift.
