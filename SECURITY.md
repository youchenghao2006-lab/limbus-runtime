# Security and privacy / 安全与隐私

This is experimental software with no security response SLA. No public repository or private contact channel has been configured by this source package.

If you find a vulnerability, use the hosting repository's private vulnerability-reporting feature once its owner enables it. If no private route exists, open a minimal issue asking for a private contact method, without exploit details or personal data. Do not upload credentials or account files to public issues.

## Scope and boundaries

- The launcher uses a dedicated Wine prefix. Wine is a compatibility layer, **not a sandbox**; Windows applications may still access files allowed by the macOS process. Use only software you trust.
- Runtime archives are size/hash checked before staged extraction. This confirms pinned content, not that its upstream code is free of vulnerabilities.
- Steam downloads are explicit and use the official HTTPS URL, but the mutable installer is not hash pinned.
- Downloaded components, Steam and the game follow their own security and privacy policies. This launcher makes no claims about their telemetry.
- Logs stay local unless you share them. They can contain personal paths and information emitted by external processes. Review and redact before sharing.
- Source publishing uses an allowlist and checks for selected suspicious patterns. This is not a comprehensive secret scanner.

The `stop` action closes this launcher's Wine environment and can lose unsaved progress. The `repair` action updates prefix system files; back up important saves before maintenance. The setup tool does not replace an existing runtime.
