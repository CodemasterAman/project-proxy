# End-to-end regression tests

Browser-driven (Selenium) regression suite for the susgrade web app. It opens a
real Chrome, exercises every analysis surface, and asserts the results — so a
broken parser, grammar config, or UI wiring fails the build instead of shipping.

## What it covers

| Test | What it checks |
|------|----------------|
| `test_complexity_exact` | Exact cyclomatic complexity for PHP, Kotlin, Swift, Java, Go and TypeScript samples (each via its real parser). |
| `test_language_renders` | All **12** languages (Python, JavaScript, Java, C, C++, Go, Rust, C#, TypeScript, PHP, Kotlin, Swift) render a report with a real-parser badge. |
| `test_complexity_custom_python` | Typing custom code and hitting **Analyze** produces the expected score. |
| `test_language_switch_isolated` | Switching languages updates the label and leaves exactly one chip active. |
| `test_mutation_runs` | Mutation testing (Pyodide) runs and reports a score. |
| `test_risk_runs` | The fused risk report renders. |
| `test_ci_generator` | The CI config generator emits a config and reacts to provider changes. |
| `test_no_severe_js_errors` | No severe browser-console errors during the whole session. |

## Running

```bash
pip install -r tests/regression/requirements.txt
```

**Against a locally-served copy (recommended):**

```bash
# serve the frontend so the CDN scripts + Pyodide load from your network
(cd frontend && python3 -m http.server 8000 &)
SUSGRADE_URL=http://localhost:8000 pytest tests/regression -v
```

**Against the deployed site:**

```bash
SUSGRADE_URL=https://<your-pages-url>/ pytest tests/regression -v
```

Selenium 4.6+ bundles *Selenium Manager*, which downloads a matching
`chromedriver` automatically — no manual driver setup. Set `HEADLESS=0` to watch
the browser drive itself.

> The mutation/risk tests boot Pyodide (real CPython in WebAssembly) in the
> browser; a cold load can take 30–90 s, and the waits allow for that. They
> `skip` (rather than fail) if a panel has no default sample loaded.
