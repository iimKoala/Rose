"""Where this version's party server is (relay-worker/, on Cloudflare's free plan).

The original Rose keeps its own address out of git, and .gitignore still names this file. This one is added
on purpose (git add -f): an install that updates from GitHub has no other way to learn it. Anyone can read
it here, so the worst a stranger can do is use up the free plan's requests for a day.
"""

RELAY_URL = "wss://rose-party-relay.rose-partyup.workers.dev"
