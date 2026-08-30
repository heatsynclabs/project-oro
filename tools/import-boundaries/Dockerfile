# The image the import boundary gate runs in.
#
# There is no published import-linter image, checked on 2026-08-29 against
# ghcr.io and Docker Hub, so this repository builds the one it needs rather
# than installing anything on the machine running the gate. The reasoning and
# what was priced against it are in
# docs/decisions/0011-import-linter-arrives.md.
#
# Pinned by digest as well as by tag, the way every other image here is pinned.
# python:3.13-slim, which is 3.13.15 on Debian trixie, digest read from
# `docker buildx imagetools inspect python:3.13-slim` on 2026-08-29. That digest
# is the image index and carries linux/amd64 and linux/arm64, so a laptop and a
# CI runner both get a native image.
#
# 3.13 rather than 3.14 is the whole reason this arrives as an image. grimp
# publishes a cp313 wheel for every platform this runs on, and its only cp314
# macOS arm64 wheel is for the free threaded build, so a plain 3.14 on a laptop
# compiles it from source.
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f

# --require-hashes turns requirements.txt into a lock the installer enforces. A
# package whose contents changed under its version number fails the build rather
# than reaching the image. docs/decisions/0012-python-dependencies.md holds the
# reasoning for the same mechanism in services/api.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes --requirement /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# Not root. This reads a source tree and writes nothing.
RUN useradd --create-home --uid 1000 oro
USER oro
WORKDIR /io
