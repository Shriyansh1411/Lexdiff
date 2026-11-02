# Lendwise (fixed): the demo lender after the Lexdiff remediation

Fictional non-bank lender used as Lexdiff's test target. MFA on every non-public route, no customer data in logs or exports,
an FTC notification handler. **Still open on purpose:** plaintext `ssn` / `account_number` at rest in SQLite (V9),
MD5 password hashing (V10) and a hard-coded secret (V11), so the certificate stays honest.
