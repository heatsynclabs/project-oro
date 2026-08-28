# The mock server image, in one place, so the version is pinned once.
#
# Read by tools/mock/run.sh and tools/mock/tests/run.sh. Nothing sources this
# for anything else.
#
# Pinned by digest as well as by tag. A tag can be moved onto a different build
# by the person who publishes it; a digest cannot. ADR 0001 gives the reasoning
# for pinning the contract toolchain at all: a tool that changes its behaviour
# on somebody else's release schedule turns an unrelated pull request red.
#
# stoplight/prism:5.15.10, published 2026-04-20. It is the newest version tag on
# Docker Hub, read on 2026-08-27. A `master` tag is newer by date and is not a
# release. The npm package is one minor ahead at 5.16.0, and ADR 0002 says why
# the image is used rather than npx.
ORO_MOCK_IMAGE="stoplight/prism:5.15.10@sha256:586d1f0f94f8d0eaf20b26b8b41f985f2a2d494bea297bd3988c3de3eb87094e"

# There is one manifest and its platform is linux/amd64. Asking for it by name
# stops docker printing a platform warning on every start on an arm64 machine,
# where it runs under emulation. On an arm64 host with no emulation configured
# this fails with an exec format error, which is the honest outcome.
ORO_MOCK_PLATFORM="linux/amd64"

# The document being served. The mock has no other input.
ORO_MOCK_DOCUMENT="members-v1.yaml"
