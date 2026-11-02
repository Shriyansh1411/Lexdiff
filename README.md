Lexdiff — Diff the Law, Test the Code

From regulatory changes to verified code-level compliance evidence.

Lexdiff is an AI-assisted regulatory change impact analysis and compliance verification engine.

When a regulation changes, Lexdiff identifies the application code that may be affected, generates obligation-specific tests before remediation, proves whether the fixes work, and produces an evidence-backed compliance certificate.

AI proposes. Deterministic checks decide.

The bundled demonstration uses Lendwise, a fictional non-bank lender, evaluated against abridged excerpts of the FTC Safeguards Rule (16 CFR Part 314).

The demo covers:

Multi-factor authentication (§314.4(c)(5))

Protection of customer information (§314.4(c)(3))

FTC notification requirements (§314.4(j)(1))

Change management (§314.4(c)(7))

1. The Problem

When regulations change, engineering teams need to determine:

Which regulatory obligations have changed?

Which application components are affected?

What code needs remediation?

How can the fix be independently verified?

What evidence demonstrates that the remediation worked?

Traditional compliance processes rely heavily on manual reviews and static checklists.

Lexdiff connects regulatory changes directly to application code, executable tests and verification evidence.

2. Key Features

Regulatory Redlining: Identifies clause-level changes between regulatory versions.

Obligation Extraction: Converts regulatory clauses into structured obligations with verbatim quotations.

Code Impact Analysis: Maps routes, dependencies, sensitive data fields and application sinks.

Fail-Before / Pass-After Testing: Generates tests before remediation and verifies them against both code versions.

Synthetic Canary Detection: Tracks synthetic sensitive data across logs, exports and databases.

Evidence-Based Certification: Assigns individual verification grades based on automated evidence.

Human-in-the-Loop Approval: Requires named human approval for obligations and authorized test rewrites.

CI Integration: Provides a deterministic guard for identifying code-level findings.

3. Architecture

INPUTS                  LEXDIFF ENGINE                  OUTPUTS

Regulation V1 ──┐
                ├──> Redline ──> Obligations ───────> Locked Tests
Regulation V2 ──┘
                       │
Target Repository ───> Impact Analysis
(Base + Fixed)         │
                       ▼
                  Failing Tests
                       │
                       ▼
                  Canary Detection
                       │
                       ▼
                  Base vs Fix Proof
                       │
                       ▼
                  Evidence Grading
                       │
                       ▼
                  Deterministic Guard
                       │
                       ▼
                 JSON + HTML Certificate
                 CI Findings
                 Dashboard

4. Nine-Stage Workflow

Stage

Component

Function

AI Usage

1

Screen

Detects comments targeting AI agents and potential prompt injection.

Optional second opinion

2

Redline

Performs clause-level regulatory comparison and handles renumbering.

No

3

Obligations

Extracts obligations with verbatim regulatory quotations and human approval.

Optional drafter

4

Impact

Maps routes, dependencies, SQL aliases and data sinks.

No

5

Test Generation

Generates obligation tests and locks them using hashes.

No

6

Canary

Plants synthetic SSN and bank-account data and scans application stores.

No

7

Proof

Verifies that tests fail on the base and pass on the fixed implementation.

No

8

Evidence

Grades each obligation based on verification evidence.

No

9

Guard

Runs deterministic CI checks and reports code-level findings.

No

Only stages 1 and 3 can use an LLM.

Every automated pass or fail decision comes from code execution and deterministic checks.

5. Technology Stack

Category

Technology

Purpose

Backend

Python

Core compliance engine

Frontend

Streamlit

Interactive dashboard

Demo Application

Flask + SQLite

Fictional lending application

AI Integration

OpenAI-compatible LLM API

Optional drafting and screening

Regulatory Processing

difflib

Regulatory redlining

Code Analysis

Python AST

Code dependency analysis

Testing

pytest / unittest

Automated verification

Data Processing

PyYAML

Configuration and obligation processing

Version Control

Git

Repository and revision tracking

CI/CD

GitHub Actions

Automated pull-request checks

6. Getting Started

Prerequisites

Python 3.12 or later

Git

pip

Step 1: Clone the repository

git clone https://github.com/shriyansh1411/Lexdiff.git
cd Lexdiff

Step 2: Create a virtual environment

Windows PowerShell:

py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1

Linux / macOS:

python3 -m venv .venv
source .venv/bin/activate

Step 3: Install dependencies

python -m pip install -r requirements.txt

Step 4: Run the complete Lexdiff pipeline

python -m lexdiff run --base demo/lendwise_base --head demo/lendwise_fixed --reg-old data/regulation/ftc_safeguards_2021-01-01.txt --reg-new data/regulation/ftc_safeguards_2026-09-01.txt --approver "Your Name"

Replace Your Name with the authorized approver's name.

Step 5: Launch the dashboard

python -m lexdiff dashboard

Open the dashboard in your browser:

http://localhost:8501

Step 6: Run the tests

python -m pytest -q tests

7. Available CLI Commands

Lexdiff provides individual commands for executing and inspecting different stages.

# Run the complete pipeline
python -m lexdiff run --base DIR --head DIR --reg-old FILE --reg-new FILE --approver "Name"

# Compare regulatory versions
python -m lexdiff redline --old FILE --new FILE

# Draft obligations
python -m lexdiff draft --old FILE --new FILE

# Validate obligation quotations
python -m lexdiff validate compliance/drafts --regulation FILE

# Approve an obligation
python -m lexdiff approve SG-5 --by "Name"

# Generate the application code graph
python -m lexdiff graph --target DIR

# Generate obligation tests
python -m lexdiff gen-tests --target DIR

# Run synthetic canary detection
python -m lexdiff canary --target DIR

# Verify base and fixed implementations
python -m lexdiff verify --base DIR --head DIR

# Run the deterministic guard
python -m lexdiff guard --target DIR --format text

# Run the benchmark
python -m lexdiff benchmark --target DIR

# Fetch regulatory text from eCFR
python -m lexdiff fetch-ecfr --date 2026-09-01 --out FILE

# Launch the dashboard
python -m lexdiff dashboard

The run command stops after obligation extraction until a named human approves the obligations.

8. Running with Make

The project includes Makefile shortcuts:

make test
make demo
make guard-base
make benchmark
make dashboard
make demo-git

Command

Purpose

make test

Runs the engine test suite

make demo

Executes all nine stages on the demo

make guard-base

Runs the guard against the deliberately vulnerable application

make benchmark

Compares Lexdiff against keyword search

make dashboard

Launches the Streamlit dashboard

make demo-git

Runs the proof using Git-based base and head references

9. Demo Application — Lendwise

Lendwise is a fictional non-bank lending application designed to demonstrate regulatory change impact analysis.

It contains two versions:

demo/lendwise_base: Original implementation with deliberately planted violations.

demo/lendwise_fixed: Remediated implementation with selected unresolved issues retained for verification.

The demonstration evaluates application behavior against abridged FTC Safeguards Rule excerpts.

Sample Verification Results

Obligation

Regulatory Clause

Result

SG-3

314.4(c)(3)

Partially verified

SG-5

314.4(c)(5)

Verified

SG-7

314.4(c)(7)

Human review required

SG-9

314.4(j)(1)

Verified

Benchmark Results

The bundled Lendwise demo contains:

11 deliberately planted violations.

2 decoy markers.

9 detected planted violations.

0 decoy flags.

2 documented missed detections.

The benchmark identifies limitations such as MD5 password hashing and hard-coded secrets, for which the current rule pack does not provide detection rules.

These are results from the bundled demonstration, not guaranteed performance on arbitrary applications.

10. Compliance Certificate

After execution, Lexdiff generates:

.lexdiff/
├── certificate.html
└── certificate.json

The certificate contains obligation-level grades and supporting verification evidence.

Supported grades:

Verified

Partially verified

Unverified

Human review required

Lexdiff deliberately avoids making unsupported claims of full regulatory compliance.

11. Using Lexdiff on Your Own Repository

Add a lexdiff_target.json file to the root of the target repository.

Refer to:

demo/lendwise_base/lexdiff_target.json

Important configuration fields include:

Key

Purpose

app_factory

Flask application factory in module:function format

data_dir_env

Environment variable used to configure the application's data directory

public_routes

Routes permitted without a second authentication factor

sensitive_names

Names of variables and columns containing regulated information

mfa

MFA decorator, request header and verification configuration

notice

Module and function handling FTC notification decisions

canary

Synthetic values, store paths and HTTP execution scenarios

The engine is designed to be framework-agnostic at its core. However, route detection and canary execution currently target Flask-style decorators and the Flask test client.

12. Optional LLM Configuration

Lexdiff does not require an API key.

Without LEXDIFF_LLM_API_KEY, the engine uses a deterministic offline drafter.

To enable optional LLM-assisted drafting and screening:

export LEXDIFF_LLM_API_KEY=your_api_key
export LEXDIFF_LLM_MODEL=gpt-4o-mini
export LEXDIFF_LLM_BASE_URL=https://api.openai.com/v1

The LLM can only draft from the regulatory clause text supplied to it.

Every generated quotation is checked by the same verbatim validation mechanism used for human-written obligations. Invalid output falls back to the offline drafter.

The LLM does not determine whether tests pass or whether an obligation is verified.

13. Project Structure

Lexdiff/
│
├── .github/
│   └── workflows/
│       └── lexdiff.yml
│
├── compliance/
│   ├── drafts/
│   └── test_changes.yaml
│
├── dashboard/
│   └── app.py
│
├── data/
│   └── regulation/
│
├── demo/
│   ├── lendwise_base/
│   ├── lendwise_fixed/
│   └── lexdiff/
│
├── lexdiff/
│   ├── obligations/
│   ├── proof/
│   ├── regulation/
│   ├── canary/
│   ├── pipeline.py
│   ├── graph.py
│   ├── screen.py
│   ├── guard.py
│   ├── evidence.py
│   └── ...
│
├── scripts/
├── tests/
├── .gitignore
├── Makefile
├── README.md
└── requirements.txt

14. Limitations and Disclaimer

The regulatory documents included in the repository are abridged demonstration excerpts, not complete authoritative legal texts.

The bundled Lendwise application is fictional and uses synthetic data.

The benchmark demonstrates the method on a controlled application, not universal detection accuracy.

Only obligations that can be evaluated through the implemented technical checks are covered.

Route detection and canary execution currently target Flask applications.

Static code analysis may miss dynamically generated routes and dependencies.

Organizational policies, employee training and vendor oversight require separate human assessment.

Lexdiff provides technical verification evidence, not legal advice or a formal legal compliance certification.

Always consult the applicable official regulatory text and qualified compliance professionals before relying on results in production.

Repository

GitHub: github.com/shriyansh1411/Lexdiff

Lexdiff — AI-assisted regulatory intelligence with deterministic code-level verification.