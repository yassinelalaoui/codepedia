# Provider Routing Contract — Rate-Limit Backoff Delta

## Purpose

This feature changes exactly one behaviour of the `FailoverExecutor` defined
by `specs/029-provider-fallback-chains/contracts/provider-protocols.md`: what
happens on a `rate_limited` failure. Nothing else about provider routing
changes — chain resolution, `isAvailable`, the classification of failures, the
`engine_failover_log` schema, and `FailoverExhaustedError` are all unaffected
and unchanged.

The reason it is in scope at all is that indexing now calls providers from
thread pools (`indexing-concurrency-delta.md`). Under the old behaviour — burn
the current provider on its first HTTP 429 and move down the chain — several
concurrent workers hitting the same limit would exhaust the entire chain
within seconds, and concurrency would make indexing *less* reliable rather
than faster. A rate limit is a property of the API key over time, not of the
provider's health: the next provider in the chain is no more likely to answer,
and only waiting clears it.

## `BackoffPolicy` — new

```python
@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    initialDelaySeconds: float = 1.0
    factor: float = 2.0
    maxDelaySeconds: float = 30.0
    maxWaits: int = 4
```

`delay_for(wait_index)` returns `random.uniform(0, min(initialDelaySeconds *
factor**wait_index, maxDelaySeconds))` — exponential, capped, with **full
jitter**. The jitter is not decoration: without it, N pool workers rejected by
the same limit would wake in lockstep and re-hit it together.

With the defaults, one provider is retried after intervals capped at 1s, 2s,
4s and 8s — at most ~15s of waiting, ~7.5s expected — before the chain moves
on.

Constructor validation: `initialDelaySeconds`, `maxDelaySeconds` and
`maxWaits` must not be negative; `factor` must be at least 1. `maxWaits=0`
reproduces the pre-feature behaviour exactly.

## `FailoverExecutor.__init__` — three new keyword arguments

| Argument | Default | Purpose |
|---|---|---|
| `backoff` | `BackoffPolicy()` | The wait schedule for `rate_limited`. |
| `sleep` | `time.sleep` | Injected so a caller can prove the schedule without spending it. |
| `on_backoff` | `None` | Called before each wait; see **Visibility** below. |

`on_backoff` is called as
`on_backoff(stage=..., provider=..., delay_seconds=..., wait_number=..., max_waits=...)`.

`build_stage_executor` accepts and forwards `backoff` and `on_backoff`;
omitting them keeps the default policy, which is what every caller outside
`cli/index_command.py` does.

## `FailoverExecutor.run` — changed

For each provider in the chain, in order:

- A **`rate_limited`** failure with waits remaining: sleep `delay_for(n)` and
  call **the same provider** again. The chain does not advance.
- A `rate_limited` failure with the wait budget exhausted: behave exactly as
  before — record `outcome="unavailable"`, log one switch, advance.
- `network_error` and `auth_failed`: unchanged, immediate switch. Neither an
  unreachable host nor a rejected key repairs itself within seconds of
  sleeping, so waiting on them would only add latency to a failure.
- `unknown`: unchanged, re-raised without any failover.

`FailoverExhaustedError` is still raised when every provider in the chain has
been abandoned, with the same message and fields.

## `FailoverAttempt.outcome` — one new value

`"retried"` joins `"success"` and `"unavailable"`. It means a wait, not a
switch: the same provider is about to be called again. Consumers that count
provider switches must count `"unavailable"`, not the length of `attempts`.

A single call that is rate-limited twice and then succeeds returns
`attempts == (retried, retried, success)` and a `providerUsed` equal to the
**first** provider in the chain.

## Visibility, and what is deliberately *not* logged

Constitution 2.3 requires every automatic provider switch to remain visible to
the user. It is, and identically to before: **one row in
`engine_failover_log` per actual switch**, with the same `stage`,
`attempted_provider`, `result_provider` and `reason` values.

A backoff wait writes **no** row, by design. `engine_failover_log` means "the
system stopped using provider A and started using provider B"; waiting on
provider A is the precise opposite of that, and recording waits there would
both misstate what happened and bury the real switches under repetitions of
them. Three waits followed by a switch remain *one* logged event.

Waits stay visible by two other routes:

- `FailoverResult.attempts`, which carries a `"retried"` entry per wait;
- `on_backoff`, which `cli/index_command.py` wires to a console line
  (`rate limited by groq:… ; waiting 1.4s before retry 1/4`), so an indexing
  run slowed by a rate limit is never mistaken for a hung one.

`engine_failover_log` row ids gain a random component. They were seeded on
`stage|attempted_provider|timestamp`, which is not unique once several pool
workers hit the same limit within one clock tick; the duplicate would have
failed the table's primary key and lost a genuine event. Nothing reads an id
back by reconstructing its seed.

## `FailoverExecutor.stream` — unchanged

The streaming path carries **no** backoff and is byte-for-byte unchanged. It
serves chat, where an interactive answer is better served by switching
provider at once than by sleeping seconds before the first token. Backoff
exists for batch throughput during indexing, which this path never does.
