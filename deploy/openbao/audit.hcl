# Declarative audit device (OpenBao 2.6+: runtime `bao audit enable` is
# rejected in favor of config-based management). Every secret access is
# logged here — observability spec, "Bao access is audited".
audit "file" "file" {
  description = "Prokura dev audit log"
  options {
    file_path = "/tmp/bao-audit.log"
  }
}
