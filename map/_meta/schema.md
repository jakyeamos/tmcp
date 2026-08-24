# TMCP map schema

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `type` | `cluster`, `object`, `source-layer`, `support-layer`, `unknown` | Catalog noun kind |
| `universe` | `live`, `leftover`, `ghost`, `unknown` | Whether the source is in force |
| `status` | `stub`, `verified`, `stale` | Citation/freshness state |
| `access_tier` | `public`, `private`, `owner-only`, `unknown` | Distribution boundary |

Experimental and disabled paths must remain visibly distinct from stable
runtime contracts.

