# Auth-gated sources (M1)

X and LinkedIn collectors are not implemented. Supplying a token or a session
alone does not make them work. Keep these sources disabled in config. An enabled
source returns a visible needs_auth/collector_not_implemented outcome; healthy
sources and ready backlog can continue. If all sources fail and no ready backlog
exists, the CLI returns an error instead of reporting no news.

Later collectors belong in the_few/collectors.py or a dedicated collector
package, using the same FetchResult, source identity and transactional store.
Credentials must live in environment/provider configuration, never shared YAML,
collected units, exported lists or git. No auth retry loops or silently expanded
source lists. Actual host/browser authorization is a separate provider contract.
