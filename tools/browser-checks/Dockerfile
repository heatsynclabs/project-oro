# The image the browser checks run in.
#
# Microsoft publishes this base for exactly this job: Ubuntu 24.04 with the
# chromium, firefox and webkit builds playwright 1.62 expects, and every shared
# library those three need. What it deliberately does not ship is the Python
# package that drives them. Read out of the image on 2026-08-30: `pip list`
# names six packages and playwright is not one of them, and the build step that
# installed it ends `rm -rf /ms-playwright-agent`, which throws the virtual
# environment away once the browsers are down. So the browsers arrive in the
# base and the driver is installed here.
#
# Pinned by digest as well as by tag, the way every other image here is pinned.
# v1.62.0-noble, index digest read from
# `docker buildx imagetools inspect` on 2026-08-30. That digest is the image
# index and carries linux/amd64 and linux/arm64, so a laptop and a CI runner
# both get a native image.
#
# The version in requirements.in has to match the version in this tag. The base
# image holds one browser build per browser, named for the playwright release
# that pinned it, and a driver of another version goes looking for a build that
# is not in the image.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble@sha256:aa81288e738725378becba5b3e06cb0f3a7f012a610e87e8d767a090ea3f740d

# --require-hashes turns requirements.txt into a lock the installer enforces. A
# package whose contents changed under its version number fails the build rather
# than reaching the image. docs/decisions/0012-python-dependencies.md holds the
# reasoning for the same mechanism in services/api, and
# docs/decisions/0011-import-linter-arrives.md for the same shape one directory
# over.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages \
      --require-hashes --requirement /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# Not root. This reads one source file and writes one screenshot, and run.sh
# hands it the caller's own user id so the screenshot belongs to the person who
# asked for it rather than to root. HOME has to be somewhere that user can
# write, because chromium puts its profile there.
ENV HOME=/tmp
WORKDIR /io
