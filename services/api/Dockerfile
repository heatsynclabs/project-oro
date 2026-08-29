# The members API image.
#
# Pinned by digest as well as by tag, the way every other image this repository
# runs is pinned. python:3.13-slim, which is 3.13.15 on Debian trixie, digest
# read from `docker buildx imagetools inspect python:3.13-slim` on 2026-08-28.
# That digest is the image index and carries linux/amd64 and linux/arm64, so a
# laptop and a CI runner both get a native image.
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f

# --require-hashes turns requirements.txt into a lock the installer enforces. A
# package whose contents changed under its version number fails the build rather
# than reaching the image. Every wheel in that file carries the hashes for every
# platform, which is why it is generated with uv rather than by pip freeze.
# docs/decisions/0012-python-dependencies.md holds the reasoning.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes --requirement /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# Not root. The service opens no files, writes nothing, and needs no port below
# 1024, so there is nothing here that a privileged process would buy.
RUN useradd --create-home --uid 1000 oro
USER oro
WORKDIR /srv
COPY app /srv/app

# One worker on purpose. The connection pool is per process, and the leak this
# service is built to prevent is one request's identity surviving on a pooled
# connection into the next. A second worker would hide that behind a second
# pool rather than fix it. Scaling is a later decision with a measurement
# behind it.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
