# Declarative audit device (OpenBao 2.6+: runtime `bao audit enable` is
# rejected in favor of config-based management). Every secret access is
# logged here — observability spec, "Bao access is audited".
audit "file" "file" {
  description = "Prokura dev audit log"
  options {
    # Written inside the container; view with `docker compose exec openbao cat /tmp/bao-audit.log`.
    # Not shipped to Loki in v0 (OpenBao has no OTLP export) — known gap; M2's
    # instrumented broker makes Bao access trace-visible via caller-side spans.
    file_path = "/tmp/bao-audit.log"
  }
}
