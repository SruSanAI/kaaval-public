# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x (latest) | ✅ |
| Older | ❌ — please upgrade |

## Reporting a vulnerability

**Please do not open a public issue.** Report it privately to **[sanjay@srusan.com](mailto:sanjay@srusan.com)**, or
through GitHub's **[Security → Report a vulnerability](https://github.com/SruSanAI/kaaval-public/security/advisories/new)**.

Please include the version, your OS and runtime version, what you ran, what happened, a minimal reproduction if you
have one, and what an attacker could achieve.

You will get an acknowledgement within **3 working days** and an assessment within **10**. Fixes ship as a new patch
version with a GitHub security advisory and credit to you unless you prefer otherwise. Please give us a reasonable
chance to ship a fix before disclosing publicly.

## What counts

In scope: anything in a reviewed repository that gets executed (Kaaval must read schematics and netlists only as text and build every deck itself), reading or writing files outside a review's workspace, a server-side key (Muse Spark, Minnal) reaching a page, log or report, and bypassing the access code or rate limits of a hosted instance.

Out of scope: the accuracy of a simulation result (open sky130 models, not foundry sign-off: please open a normal issue), bugs in ngspice or the PDK themselves, and issues needing an already-compromised machine.
