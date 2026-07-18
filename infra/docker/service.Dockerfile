# one image recipe for every python service; pick the service via build arg
# (build context is the repo root)
FROM python:3.12-slim
ARG SERVICE

WORKDIR /srv
COPY libs/core /srv/libs/core
COPY infra/docker/requirements/${SERVICE}.txt /tmp/requirements.txt
RUN pip install --no-cache-dir /srv/libs/core -r /tmp/requirements.txt \
 && if pip show opencv-python >/dev/null 2>&1; then \
      HEADLESS_VER=$(pip show opencv-python-headless 2>/dev/null | grep '^Version:' | awk '{print $2}'); \
      pip uninstall -y opencv-python opencv-python-headless; \
      pip install --no-cache-dir opencv-python-headless==${HEADLESS_VER:-4.13.0.92}; \
    fi

COPY services/${SERVICE} /srv/${SERVICE}
# command comes from docker-compose.yml
