# State

Base commit: b6de953e867fe52ce76f51fab2a826afa6a59f6e

v4 proved that environment and constructor patching were active, but Hermes'
internal `docker run` still returned 125. v5 avoids that create path entirely
by pre-creating the audited sandbox and using label-based reuse.
