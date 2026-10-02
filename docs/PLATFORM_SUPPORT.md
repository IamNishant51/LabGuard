# Platform support and lab network

## Requirement
LabGuard monitors authorized Windows and Ubuntu/Linux lab computers. PCs are Ethernet-connected. The lab administrator authorizes installation and operation of the agent.

## Support policy
“Windows any version” must not be interpreted as a promise to support every historical Windows release. Older releases differ in Python compatibility, TLS defaults, security updates, and service behavior.

| Platform | Initial target | Status |
|---|---|---|
| Windows | Windows 10 x64 and Windows 11 x64 | Target; verify actual lab builds |
| Ubuntu | Supported Ubuntu LTS x64 | Target; verify exact release |
| Dual boot | Windows + Ubuntu on one physical PC | Separate per-OS installations; only booted OS reports |
| Older Windows | Older than Windows 10 | Not guaranteed; evaluate if actually present in the lab |

Display platform and agent version reported by the agent. Maintain a tested-platform list in release notes. Do not claim a platform is tested merely because the code is intended to be cross-platform.

## Ethernet/LAN design
1. Run FastAPI and PostgreSQL on an approved, always-on internal server or designated lab machine.
2. Give the server a stable internal DNS name or reserved IP.
3. Configure each agent with the internal API base URL.
4. Permit only the required outbound connection from lab PCs to the API through firewalls.
5. Keep PostgreSQL inaccessible to lab PCs; only the API connects to the database.
6. Use HTTPS with a certificate trusted by clients where practical. Never disable certificate validation to work around certificate errors.
7. Once dependencies and updates are installed, telemetry should function without internet access. Document any operation that does require internet.
8. Test connectivity from a lab PC, not just from the server.

## Dual-boot identity
A normal dual-boot computer runs only one OS at a time. Install the agent separately in Windows and Ubuntu. If approved, both installations can use credentials associated with one registered physical-computer record to retain one history; each heartbeat reports the currently running OS. Alternating platform values are expected.

Alternatively, create separate records such as `LAB-PC-023-WIN` and `LAB-PC-023-UBU`. Choose one model before pilot enrollment and document it consistently.

## Pilot checklist
- [ ] Administrator approval recorded.
- [ ] Exact Windows edition, version, build, and architecture recorded.
- [ ] Exact Ubuntu release and architecture recorded.
- [ ] Server owner and stable LAN address agreed.
- [ ] Agent reaches API over Ethernet.
- [ ] Firewall permits only required traffic.
- [ ] Valid TLS certificate or isolated development-only setup.
- [ ] Agent starts after reboot as configured.
- [ ] Invalid/revoked token is rejected.
- [ ] Stopping the agent changes status after the configured timeout.
- [ ] Windows and Ubuntu volume metrics are meaningful.
- [ ] Uninstall and credential revocation verified.
