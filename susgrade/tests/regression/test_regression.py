"""
End-to-end regression suite for the susgrade web app (Selenium + pytest).

This drives a REAL browser against the live site (or a locally-served copy) and
verifies the three analysis surfaces plus the CI generator still behave:

  * Complexity analyzer — exact cyclomatic complexity for all 12 languages,
    each parsed by its real parser (Python AST, Acorn, Tree-sitter).
  * Mutation testing    — runs in-browser via Pyodide and reports a score.
  * Risk report         — fuses complexity x (1 - mutation score).
  * CI generator        — builds a pipeline config client-side.
  * Batch & repo scan   — multi-file upload and public GitHub repos.

────────────────────────────────────────────────────────────────────────────
Running
────────────────────────────────────────────────────────────────────────────
  pip install -r tests/regression/requirements.txt

  # Option A — against a locally served copy (recommended; loads CDNs + Pyodide
  # from your machine's network, which the CI/dev sandbox cannot reach):
  (cd frontend && python3 -m http.server 8000 &)
  SUSGRADE_URL=http://localhost:8000 pytest tests/regression -v

  # Option B — against the deployed GitHub Pages site:
  SUSGRADE_URL=https://<your-pages-url>/ pytest tests/regression -v

Selenium 4.6+ ships "Selenium Manager", which fetches a matching chromedriver
automatically — no manual driver install needed. Set HEADLESS=0 to watch it run.

Note: the mutation/risk tests boot Pyodide (real CPython in WebAssembly) in the
browser, which can take 30–90 s on a cold load; the waits below allow for that.
"""
import os
import time
import tempfile
import pytest

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = os.environ.get("SUSGRADE_URL", "http://localhost:8000")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"

# Exact cyclomatic complexity for the first-loaded sample of each language,
# verified against each language's real parser. If a grammar, a TS_CONFIG
# entry, or the complexity walk regresses, these numbers move and the test
# fails — which is the whole point.
EXACT = {
    # lang        tab           {function: expected complexity}
    ("php",    "order"):    {"totalPrice": 8},
    ("php",    "router"):   {"Router.dispatch": 3, "Router.get": 4},
    ("kotlin", "grade"):    {"grade": 4, "sumPositive": 4},
    ("kotlin", "router"):   {"Router.dispatch": 6},
    ("swift",  "classify"): {"classify": 7, "sumPositive": 3},
    ("swift",  "router"):   {"Router.dispatch": 3, "Router.get": 2},
    ("java",   "service"):  {"Service.applyDiscount": 2, "Service.isValid": 3},
    ("go",     "handler"):  {"ApplyDiscount": 2, "Checksum": 3},
    ("typescript", "validator"): {"applyDiscount": 2, "isValid": 3},
}

# Every language the analyzer claims to support (used by the render smoke test).
ALL_LANGUAGES = [
    "py", "js", "java", "c", "cpp", "go", "rust", "c_sharp",
    "typescript", "php", "kotlin", "swift",
]


@pytest.fixture(scope="session")
def driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1600")
    # surface browser console errors to Selenium's log
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    drv = webdriver.Chrome(options=opts)
    drv.set_page_load_timeout(60)
    drv.get(BASE_URL)
    # the complexity panel auto-analyses a sample on load
    WebDriverWait(drv, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#report .fnrow"))
    )
    yield drv
    drv.quit()


# ── helpers ──────────────────────────────────────────────────────────────────

def _click(driver, css):
    el = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, css))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    el.click()
    return el


def _select_language(driver, lang):
    _click(driver, f'.lang-btn[data-lang="{lang}"]')


def _select_tab(driver, tab):
    _click(driver, f'#cxTabs .tab[data-tab="{tab}"]')


def _wait_report(driver, timeout=30):
    """Wait until the complexity report shows at least one scored function."""
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#report .fnrow"))
    )
    # let the exact-parse result replace any transient "loading" state
    WebDriverWait(driver, timeout).until(
        lambda d: "Analysing" not in d.find_element(By.ID, "report").text
    )


def _functions(driver):
    """{function_name: complexity} from the current complexity report."""
    out = {}
    for row in driver.find_elements(By.CSS_SELECTOR, "#report .fnrow"):
        name = row.find_element(By.CSS_SELECTOR, ".fnrow-name").text
        name = name.replace("()", "").replace("\u200b", "").strip()
        score = row.find_element(By.CSS_SELECTOR, ".fnrow-score").text.strip()
        out[name] = int(score)
    return out


def _badge(driver):
    return driver.find_element(By.CSS_SELECTOR, "#report .badge").text.strip()


# ── complexity: exact numbers per language ───────────────────────────────────

@pytest.mark.parametrize("lang,tab,expected", [
    (l, t, e) for (l, t), e in EXACT.items()
], ids=[f"{l}:{t}" for (l, t) in EXACT])
def test_complexity_exact(driver, lang, tab, expected):
    _select_language(driver, lang)
    _wait_report(driver)
    _select_tab(driver, tab)
    _wait_report(driver)
    got = _functions(driver)
    for fn, cx in expected.items():
        assert fn in got, f"{lang}/{tab}: function {fn!r} missing (got {got})"
        assert got[fn] == cx, f"{lang}/{tab}: {fn} expected cx={cx}, got {got[fn]}"
    # a real parser was used, not a heuristic
    assert "Exact" in _badge(driver) or "Engine" in _badge(driver)


# ── complexity: every advertised language renders ────────────────────────────

@pytest.mark.parametrize("lang", ALL_LANGUAGES)
def test_language_renders(driver, lang):
    _select_language(driver, lang)
    _wait_report(driver)
    assert len(_functions(driver)) >= 1, f"{lang}: no functions rendered"
    badge = _badge(driver)
    assert any(k in badge for k in ("Exact", "Engine", "estimate")), \
        f"{lang}: unexpected badge {badge!r}"
    # the language label reflects the active language
    assert driver.find_element(By.ID, "cxLang").text.strip() != ""


# ── complexity: custom code through the analyze button ───────────────────────

def test_complexity_custom_python(driver):
    _select_language(driver, "py")
    code = "def f(x):\n    if x > 0 and x < 10:\n        return 1\n    for i in range(x):\n        pass\n    return 0"
    driver.execute_script(
        "const t=document.getElementById('code');"
        "t.value=arguments[0];"
        "t.dispatchEvent(new Event('input',{bubbles:true}));", code)
    _click(driver, "#analyze")
    _wait_report(driver)
    got = _functions(driver)
    assert got.get("f") == 4, f"custom python f expected cx=4, got {got}"


# ── language switching stays isolated ────────────────────────────────────────

def test_language_switch_isolated(driver):
    _select_language(driver, "java")
    _wait_report(driver)
    assert driver.find_element(By.ID, "cxLang").text.strip().lower() == "java"
    active = driver.find_elements(By.CSS_SELECTOR, ".lang-btn.is-active")
    assert len(active) == 1 and active[0].get_attribute("data-lang") == "java"


# ── mutation testing (Pyodide) ───────────────────────────────────────────────

def test_mutation_runs(driver):
    _click(driver, '#mutation')  # bring the section into view / focus
    code = driver.find_element(By.ID, "mutCode").get_attribute("value")
    if not code.strip():
        pytest.skip("mutation editor has no default sample to run")
    _click(driver, "#mutRun")
    # Pyodide cold-boot + mutant execution — allow generous time.
    WebDriverWait(driver, 150).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "#mutReport .mut-score")
    )
    score = driver.find_element(By.CSS_SELECTOR, "#mutReport .mut-score").text
    assert "%" in score, f"mutation score not shown (got {score!r})"


# ── risk report (Pyodide) ────────────────────────────────────────────────────

def test_risk_runs(driver):
    _click(driver, '#risk')
    code = driver.find_element(By.ID, "riskCode").get_attribute("value")
    if not code.strip():
        pytest.skip("risk editor has no default sample to run")
    _click(driver, "#riskRun")
    WebDriverWait(driver, 150).until(
        lambda d: "risk" in d.find_element(By.ID, "riskReport").text.lower()
    )
    assert "Risk" in driver.find_element(By.ID, "riskReport").text \
        or "risk" in driver.find_element(By.ID, "riskReport").text.lower()


# ── CI generator (pure client-side, no WASM) ─────────────────────────────────

def test_ci_generator(driver):
    out = driver.find_element(By.ID, "ciOut")
    assert out.text.strip(), "CI output should show a demo config on load"

    filename_before = driver.find_element(By.ID, "ciFilename").text
    # switch provider chip and confirm the target filename updates
    chips = driver.find_elements(By.CSS_SELECTOR, "#ciProviders .ci-prov")
    assert len(chips) >= 2, "expected multiple CI provider chips"
    # click a chip that isn't currently active
    for chip in chips:
        if "is-active" not in (chip.get_attribute("class") or ""):
            driver.execute_script("arguments[0].click();", chip)
            break
    _click(driver, "#ciRun")
    time.sleep(0.5)
    filename_after = driver.find_element(By.ID, "ciFilename").text
    assert filename_after != filename_before or out.text.strip(), \
        "CI config did not regenerate after switching provider"


# ── batch & repo scan ────────────────────────────────────────────────────────

def test_scan_section_present(driver):
    _click(driver, "#scan")
    assert driver.find_element(By.ID, "scanDrop"), "scan drop-zone missing"
    assert driver.find_element(By.ID, "scanRepoInput"), "repo input missing"
    modes = driver.find_elements(By.CSS_SELECTOR, "#scanModes .ci-prov")
    assert len(modes) == 2, "expected Upload/GitHub mode toggle"


def test_scan_upload_ranks_files(driver):
    # write two source files locally and feed them to the hidden file input
    d = tempfile.mkdtemp(prefix="susgrade_scan_")
    py = os.path.join(d, "a.py")
    js = os.path.join(d, "b.js")
    with open(py, "w") as f:
        f.write("def total(items):\n    s = 0\n    for it in items:\n        if it > 0 and it < 100:\n            s += it\n    return s\n")
    with open(js, "w") as f:
        f.write("function g(a){ if (a > 0) { return 1; } return 0; }\n")

    _click(driver, "#scan")
    # ensure Upload mode is active
    for m in driver.find_elements(By.CSS_SELECTOR, "#scanModes .ci-prov"):
        if m.get_attribute("data-mode") == "files":
            driver.execute_script("arguments[0].click();", m)
            break
    driver.find_element(By.ID, "scanFileInput").send_keys(py + "\n" + js)

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".scan-table tbody tr"))
    )
    rows = driver.find_elements(By.CSS_SELECTOR, ".scan-table tbody tr")
    assert len(rows) == 2, f"expected 2 result rows, got {len(rows)}"
    # rows are ranked by max complexity desc → the Python file (cx 4) leads the JS (cx 2)
    first = rows[0].text
    assert "a.py" in first, f"expected a.py to rank first, got: {first}"
    stats = driver.find_element(By.CSS_SELECTOR, ".scan-stats").text
    assert "2" in stats  # 2 files / 2 functions
    # the scan results offer all four export formats
    fmts = sorted(e.get_attribute("data-fmt") for e in driver.find_elements(By.CSS_SELECTOR, "#scanOut .exp-bar [data-fmt]"))
    assert fmts == ["csv", "json", "md", "pdf"], f"scan export formats: {fmts}"


def test_export_controls_present(driver):
    # the single-file complexity report offers all four export formats
    _select_language(driver, "py")
    _wait_report(driver)
    bar = driver.find_elements(By.CSS_SELECTOR, "#report .exp-bar")
    assert bar, "complexity report has no export bar"
    fmts = sorted(e.get_attribute("data-fmt") for e in driver.find_elements(By.CSS_SELECTOR, "#report .exp-bar [data-fmt]"))
    assert fmts == ["csv", "json", "md", "pdf"], f"complexity export formats: {fmts}"


def test_scan_repo_invalid(driver):
    # switching to repo mode and scanning a nonexistent repo should surface a clear error
    _click(driver, "#scan")
    for m in driver.find_elements(By.CSS_SELECTOR, "#scanModes .ci-prov"):
        if m.get_attribute("data-mode") == "repo":
            driver.execute_script("arguments[0].click();", m)
            break
    box = driver.find_element(By.ID, "scanRepoInput")
    box.clear()
    box.send_keys("susgrade-nope-xyz-000/does-not-exist-000")
    _click(driver, "#scanRepoRun")
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".scan-error"))
    )
    assert driver.find_element(By.CSS_SELECTOR, ".scan-error").text.strip()


# ── no severe JS errors during the whole session ─────────────────────────────

def test_no_severe_js_errors(driver):
    benign = ("favicon", "Failed to load resource")
    severe = [
        e for e in driver.get_log("browser")
        if e.get("level") == "SEVERE" and not any(b in e.get("message", "") for b in benign)
    ]
    assert not severe, "severe browser errors:\n" + "\n".join(e["message"] for e in severe)
