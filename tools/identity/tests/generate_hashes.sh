#!/bin/sh
# Regenerate tools/identity/fixtures/legacy-hashes.json with bcrypt-ruby.
#
#   tools/identity/tests/generate_hashes.sh
#
# The fixture is committed, so this is not run by the suite and not run by CI.
# It exists so the fixture can be reproduced rather than trusted, and so the
# next person can add a case.
#
# bcrypt-ruby is the library the legacy Rails application hashes with, through
# Devise, at cost 10 with no pepper. Generating the fixture with anything else
# would make the suite prove that Zitadel agrees with a hasher nobody runs.
#
# Needs docker. The gem is compiled in a throwaway container, so nothing is
# installed on this machine and the ruby on it is not used.

set -e
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/tools/identity/fixtures/legacy-hashes.json"

# ruby 3.3 and bcrypt 3.1.20, pinned. The cost and the absence of a pepper are
# what matter here, not the ruby version: a bcrypt hash records its own cost and
# salt, so any correct implementation produces an interchangeable string.
docker run --rm -i ruby:3.3-alpine sh -c '
  apk add --no-cache build-base >/dev/null 2>&1
  gem install bcrypt -v 3.1.20 --no-document >/dev/null 2>&1
  ruby -' > "$OUT" <<'RUBY'
require 'bcrypt'
require 'json'

# Every password here is invented. Rule 13 of CLAUDE.md: no fixture may resemble
# a real credential or a real address.
cases = [
  ["ordinary",      "correct horse battery staple",
   "The common case. Nothing awkward about it"],
  ["minimum",       "Passw0rd",
   "Eight bytes, the shortest Zitadel accepts by default"],
  ["non_ascii",     "paßwort-日本語-éè",
   "Sharp s, Japanese and accented Latin, 23 bytes in 14 characters"],
  ["trailing_space","trailing space ",
   "A space at the end is part of the password and must stay part of it"],
  ["bytes_71",      "A" * 71,
   "One under the bcrypt input limit"],
  ["bytes_72",      "A" * 72,
   "Exactly the bcrypt input limit. The last length that works"],
  ["bytes_73",      "A" * 73,
   "One over. Ruby truncates and accepts it. Go refuses"],
  ["japanese_27",   "日本語" * 9,
   "27 characters and 81 bytes. Nothing about it looks long"],
]

out = {
  "generated_by" => "tools/identity/tests/generate_hashes.sh",
  "hasher" => "bcrypt-ruby 3.1.20, cost 10, no pepper, which is what config/initializers/devise.rb sets in the legacy application",
  "cases" => cases.map { |name, password, note|
    hash = BCrypt::Password.create(password, cost: 10)
    raise "cost is not 10" unless BCrypt::Password.new(hash).cost == 10
    raise "ruby cannot verify its own hash" unless BCrypt::Password.new(hash) == password
    {
      "name" => name,
      "password" => password,
      "bytes" => password.bytesize,
      "characters" => password.length,
      "hash" => hash.to_s,
      "note" => note,
    }
  },
}
puts JSON.pretty_generate(out)
RUBY

echo "wrote $OUT" >&2
