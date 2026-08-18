# One-shot image for the Neo4j topology seed jobs (tep-seed).
#
# Its own recipe rather than a reuse of service.Dockerfile because the seed
# needs a combination no single service ships: the scripts themselves, the
# simulation package they import topology constants from, and the neo4j driver.
# Baking those into the shared service image would put them in all eleven
# long-running containers that never run a seed; keeping them here costs one
# small image that is built once and exits.
#
# The layout under /srv mirrors the repo on purpose. seed_tep_topology.py
# resolves its root as the parent of scripts/ and then imports
# simulation.tep.topology from <root>/services, so scripts/ has to sit beside
# services/ and libs/ exactly as it does in the checkout, or that import fails
# the same way the missing script did.
FROM python:3.11-slim

WORKDIR /srv

COPY libs/core /srv/libs/core
# neo4j is not a plantmind-core dependency (only the graph services pull it),
# so the seed installs it explicitly alongside the core package it shares with
# the rest of the system for config and settings.
RUN pip install --no-cache-dir /srv/libs/core "neo4j>=5.28"

COPY services/simulation /srv/services/simulation
COPY scripts /srv/scripts

# command comes from docker-compose.yml (python scripts/seed_tep_topology.py)
