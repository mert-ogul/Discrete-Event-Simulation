# Security policy

## Supported versions

Security reports are handled on a **best-effort** basis for the `main` branch of this academic project. There is no long-term support commitment beyond the course timeline.

## Reporting a vulnerability

Please **do not** open a public issue for undisclosed security problems.

- **Preferred:** Email or message the course instructors or repository maintainers using the contact channel announced in your 2mbs40 course materials.
- **Include:** A short description, steps to reproduce, and impact assessment if known.

Maintainers will acknowledge receipt when possible and coordinate a fix or mitigation. If you do not receive a response within a reasonable time, escalate through the official TU/e course support path.

## Scope

This repository is a **batch analysis and simulation** codebase. It is not intended to handle authentication, payments, or personally identifiable data in production systems. Still, we treat accidental inclusion of secrets, unsafe dependency versions, and unsafe defaults seriously.

## Credentials

Never commit API keys, passwords, or personal data files. Raw spreadsheets under `data/` are gitignored on purpose—keep them local or in secure team storage.
