"""
Sandbox purchase verification (PROVE step).

Opens a store in a real browser, adds the product to the cart, clicks the PayPal
button, logs in with the PayPal Sandbox BUYER account, pays, and then confirms
through the Orders API that the payment was captured. Screenshots are saved
as proof. Run it on the store before and after an upgrade to compare.

    from sandbox_verifier import verify_checkout
    result = verify_checkout("http://localhost:8101", label="before")

Needs in .env (never commit):
    PAYPAL_SANDBOX_BUYER_EMAIL     a UNITED STATES Sandbox *Personal* account
    PAYPAL_SANDBOX_BUYER_PASSWORD

Safety:
  - Only stores on localhost / 127.0.0.1 are allowed (never a real shop).
  - The buyer login is typed only into sandbox.paypal.com, never live PayPal.
  - The password is never printed, logged or returned.
"""

import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from sandbox_verifier.errors import (
    VERIFY_BAD_STORE_URL,
    VERIFY_BROWSER_MISSING,
    VERIFY_NOT_CONFIGURED,
    ModuleError,
)

load_dotenv()

OUTPUT_ROOT = Path(os.getenv("VERIFY_OUTPUT_DIR", "outputs/verifications"))
ALLOWED_STORE_HOSTS = {"localhost", "127.0.0.1"}
SANDBOX_HOST = "www.sandbox.paypal.com"

BUTTON_WAIT_SECONDS = 30      # PayPal button to appear on the store page
POPUP_WAIT_SECONDS = 120      # login + pay inside the PayPal window
SUCCESS_WAIT_SECONDS = 60     # store capturing the payment after the popup closes
POPUP_OPEN_SECONDS = 15       # per click: how long to wait for the PayPal window
CLICK_ATTEMPTS = 2            # click PayPal again if the first click was ignored
BUTTON_SETTLE_SECONDS = 10    # max wait for PayPal's buttons to finish loading

# Failure codes stored in result["error_code"] (the run itself does not raise).
FAIL_STORE = "STORE_ERROR"                    # store page broken / empty cart
FAIL_NO_BUTTON = "PAYPAL_BUTTON_MISSING"      # PayPal button never appeared
FAIL_NO_POPUP = "PAYPAL_POPUP_MISSING"        # clicking PayPal opened nothing
FAIL_NOT_SANDBOX = "PAYPAL_NOT_SANDBOX"       # popup was not sandbox.paypal.com
FAIL_LOGIN = "BUYER_LOGIN_FAILED"             # wrong email/password
FAIL_SELLER = "BUYER_IS_SELLER"               # Business account used as buyer
FAIL_PAYPAL_PAGE = "PAYPAL_PAGE_ERROR"         # "Things don't appear to be working"
FAIL_POPUP_TIMEOUT = "PAYPAL_POPUP_TIMEOUT"   # could not finish login/pay in time
FAIL_CAPTURE = "CAPTURE_FAILED"               # store did not reach /success
FAIL_NOT_COMPLETED = "ORDER_NOT_COMPLETED"    # Orders API says not COMPLETED

# Failures caused by the store itself (as opposed to PayPal's pages or the test login).
STORE_FAILURES = {FAIL_STORE, FAIL_NO_BUTTON, FAIL_CAPTURE, FAIL_NOT_COMPLETED}

# What to look for inside the PayPal window. PayPal changes its pages often,
# so each step has a few options, tried in order.
EMAIL_INPUTS = ["input#email", "input[name='login_email']"]
PASSWORD_INPUTS = ["input#password", "input[name='login_password']"]
NEXT_BUTTONS = ["#btnNext", "button[data-testid='nextButton']", "button[name='btnNext']"]
NEXT_BUTTON_TEXT = re.compile(r"^\s*(Next|Continue)\s*$", re.I)
NEXT_RETRY_SECONDS = 6  # PayPal's newer email page sometimes ignores the first click
TYPING_DELAY_MS = 35     # pause between key presses when typing the login
BROWSER_ARGS = ["--disable-blink-features=AutomationControlled"]
LOGIN_BUTTONS = ["#btnLogin"]
PAY_BUTTONS = ["#payment-submit-btn", "[data-id='payment-submit-btn']",
               "button[data-testid='submit-button-initial']"]
PAY_BUTTON_TEXT = re.compile(r"^\s*(Pay|Pay Now|Complete Purchase|Continue|Agree & Pay|Agree & Continue)\s*$", re.I)
COOKIE_BUTTONS = ["#acceptAllButton"]
PAGE_ERRORS = {
    "account of the seller": FAIL_SELLER,
    "things don't appear to be working": FAIL_PAYPAL_PAGE,
    "things don’t appear to be working": FAIL_PAYPAL_PAGE,
    "check your entries": FAIL_LOGIN,
    "some of your info isn't correct": FAIL_LOGIN,
    "some of your info isn’t correct": FAIL_LOGIN,
}


# ------------------------------------------------------------ helpers ---
def buyer_credentials() -> tuple[str, str]:
    email = os.getenv("PAYPAL_SANDBOX_BUYER_EMAIL", "").strip()
    password = os.getenv("PAYPAL_SANDBOX_BUYER_PASSWORD", "")
    if not email or not password or "example.com" == email.split("@")[-1] \
            or password == "your-sandbox-buyer-password-here":
        raise ModuleError(VERIFY_NOT_CONFIGURED,
                          "Set PAYPAL_SANDBOX_BUYER_EMAIL and PAYPAL_SANDBOX_BUYER_PASSWORD "
                          "(a United States Sandbox Personal account) in .env.")
    return email, password


def check_store_url(store_url: str) -> str:
    parsed = urlparse(store_url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ALLOWED_STORE_HOSTS:
        raise ModuleError(VERIFY_BAD_STORE_URL,
                          f"Only local demo stores can be verified (got {store_url!r}).")
    return store_url.rstrip("/")


def is_sandbox_url(url: str) -> bool:
    return urlparse(url).hostname == SANDBOX_HOST


def order_id_from_url(url: str) -> str:
    values = parse_qs(urlparse(url).query).get("order", [""])
    order_id = values[0].strip()
    return order_id if order_id.isalnum() else ""


def _first_visible(page, selectors: list[str]):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible():
                return locator
        except Exception:  # page navigating
            return None
    return None


def _page_error(page) -> str:
    try:
        text = page.inner_text("body", timeout=1000).lower()
    except Exception:
        return ""
    for phrase, code in PAGE_ERRORS.items():
        if phrase in text:
            return code
    return ""


class _Run:
    """Collects steps, screenshots and the final result of one verification."""

    def __init__(self, store_url: str, label: str, out_dir: Path) -> None:
        self.started = time.monotonic()
        self.out_dir = out_dir
        self.result = {
            "verification_id": out_dir.name,
            "store_url": store_url,
            "label": label,
            "purchase_succeeded": False,
            "order_id": "",
            "order_status": "",
            "amount": "",
            "currency": "",
            "paypal_sdk": "",
            "payment_saved": False,   # vaulting is not part of the demo stores yet
            "api_confirmed": False,
            "screenshots": [],
            "steps": [],
            "error_code": "",
            "error_message": "",
            "warnings": [],
            "duration_seconds": 0.0,
        }

    def step(self, name: str, ok: bool = True, detail: str = "") -> None:
        self.result["steps"].append({"name": name, "ok": ok, "detail": detail,
                                     "at_seconds": round(time.monotonic() - self.started, 1)})

    def shot(self, page, name: str) -> None:
        try:
            path = self.out_dir / f"{len(self.result['screenshots']) + 1:02d}_{name}.png"
            page.screenshot(path=str(path), full_page=False)
            self.result["screenshots"].append(str(path).replace("\\", "/"))
        except Exception:
            pass

    def fail(self, code: str, message: str) -> dict:
        self.step(code, ok=False, detail=message)
        self.result["error_code"] = code
        self.result["error_message"] = message
        return self.finish()

    def finish(self) -> dict:
        self.result["duration_seconds"] = round(time.monotonic() - self.started, 1)
        return self.result


# --------------------------------------------------------- store side ---
def _find_paypal_button(page, timeout: float):
    """Wait for the PayPal button. Returns (clickable locator, "v5"|"v6") or (None, reason)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        v6 = page.locator("#paypal-button-container paypal-button:not([hidden])").first
        if v6.count() and v6.is_visible():
            return v6, "v6"
        if page.locator("#paypal-button-container iframe").count():
            v5 = page.frame_locator("#paypal-button-container iframe").first \
                     .locator("[data-funding-source='paypal']").first
            try:
                if v5.is_visible():
                    return v5, "v5"
            except Exception:
                pass
        status = page.locator("#order-status").first
        if status.count():
            text = status.inner_text().strip()
            if text and ("could not" in text.lower() or "not available" in text.lower()):
                return None, text
        page.wait_for_timeout(500)
    return None, f"No PayPal button inside #paypal-button-container after {timeout:.0f}s"


def _wait_for_buttons_ready(page, sdk: str) -> None:
    """Give PayPal's buttons time to finish loading before clicking.

    v5 draws its buttons inside an iframe in steps (the card button's label and
    "Powered by PayPal" come last); a click before that is silently ignored.
    """
    if sdk != "v5":
        page.wait_for_timeout(500)
        return
    deadline = time.monotonic() + BUTTON_SETTLE_SECONDS
    frame = page.frame_locator("#paypal-button-container iframe").first
    while time.monotonic() < deadline:
        try:
            if frame.get_by_text("Powered by", exact=False).first.is_visible():
                break
        except Exception:
            pass
        page.wait_for_timeout(500)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(1000)


# -------------------------------------------------------- PayPal side ---
def complete_paypal_popup(popup, email: str, password: str, timeout: float = POPUP_WAIT_SECONDS,
                          require_sandbox: bool = True) -> str:
    """Log in and pay inside the PayPal window. Returns "" when done, else a failure code.

    Works step by step on whatever PayPal shows (email page, password page,
    combined login, cookie banner, review page) until the window closes.
    """
    deadline = time.monotonic() + timeout
    state = {"typed_email": False, "typed_password": False, "clicked_pay": 0.0}
    while time.monotonic() < deadline:
        if popup.is_closed():
            return ""
        try:
            outcome = _popup_step(popup, email, password, state, require_sandbox)
        except Exception:
            # PayPal closes its window right after "Pay": that ends any check
            # that was running. Closed = done; otherwise just try again.
            if popup.is_closed():
                return ""
            outcome = None
        if outcome is not None:
            return outcome
        _pause(popup, 0.7)
    return FAIL_POPUP_TIMEOUT


def _pause(page, seconds: float) -> None:
    """Wait without crashing if the page closes meanwhile."""
    try:
        page.wait_for_timeout(seconds * 1000)
    except Exception:
        pass


def _normal_user_agent(browser) -> str:
    """The real Chrome user agent, without "HeadlessChrome" (used in headless mode)."""
    version = browser.version  # e.g. "131.0.6778.33"
    return (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{version} Safari/537.36")


def _type_like_a_person(box, text: str) -> None:
    """Type key by key: PayPal's newer login pages only enable Next after real key events."""
    box.click(timeout=5000)
    box.fill("")
    box.press_sequentially(text, delay=TYPING_DELAY_MS)


def _go_to_password_step(popup, email_box, state: dict) -> None:
    """Click PayPal's Next button (old and new email pages), or press Enter."""
    state["next_at"] = time.monotonic()
    button = _first_visible(popup, NEXT_BUTTONS)
    if button is None:
        candidate = popup.get_by_role("button", name=NEXT_BUTTON_TEXT).first
        button = candidate if candidate.count() and candidate.is_visible() else None
    if button is not None:
        button.click(timeout=5000)
    else:
        email_box.press("Enter")


def _popup_step(popup, email: str, password: str, state: dict, require_sandbox: bool):
    """Do the next thing the PayPal window needs. Returns a failure code, or None to keep going."""
    try:
        popup.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        if popup.is_closed():
            return ""
    url = popup.url
    if url.startswith("about:") or not url:
        return None
    if require_sandbox and not is_sandbox_url(url):
        return FAIL_NOT_SANDBOX  # never type the buyer login anywhere else

    error = _page_error(popup)
    if error:
        return error

    cookie = _first_visible(popup, COOKIE_BUTTONS)
    if cookie:
        cookie.click(timeout=5000)
        return None

    email_box = _first_visible(popup, EMAIL_INPUTS)
    password_box = _first_visible(popup, PASSWORD_INPUTS)
    if email_box and not state["typed_email"] and email_box.is_editable():
        _type_like_a_person(email_box, email)
        state["typed_email"] = True
        if not password_box:
            _go_to_password_step(popup, email_box, state)
        return None
    if email_box and state["typed_email"] and not password_box \
            and time.monotonic() - state.get("next_at", 0.0) > NEXT_RETRY_SECONDS:
        # Still on the email page: the Next click did not go through, try again.
        _go_to_password_step(popup, email_box, state)
        return None
    if password_box and not state["typed_password"]:
        _type_like_a_person(password_box, password)
        state["typed_password"] = True
        login = _first_visible(popup, LOGIN_BUTTONS)
        (login.click(timeout=5000) if login else password_box.press("Enter"))
        return None

    pay = _first_visible(popup, PAY_BUTTONS)
    if pay is None:
        candidate = popup.get_by_role("button", name=PAY_BUTTON_TEXT).first
        pay = candidate if candidate.count() and candidate.is_visible() else None
    if pay is not None and time.monotonic() - state["clicked_pay"] > 8:  # don't double-click
        state["clicked_pay"] = time.monotonic()
        pay.click(timeout=5000)
    return None


# ------------------------------------------------------- main function ---
def verify_checkout(store_url: str, label: str = "before", page: str = "checkout",
                    headless: bool = True, slow_mo: int = 0) -> dict:
    """Complete a Sandbox test purchase on a local store and report the result.

    Args:
        store_url: e.g. "http://localhost:8101" (store must already be running).
        label: "before" or "after" (used in the report and folder name).
        page: where to click PayPal - "checkout" (all stores) or "cart" (upgraded store).
        headless: False opens a visible browser window (good for demos).

    Returns a dict. Main keys:
        purchase_succeeded (bool), order_id, order_status ("COMPLETED"), amount,
        paypal_sdk ("v5"/"v6"), screenshots (list of file paths), steps, error_code,
        error_message, duration_seconds. A failed purchase is reported in the dict;
        ModuleError is raised only for setup problems (missing .env values,
        non-local URL, Playwright not installed).
    """
    store_url = check_store_url(store_url)
    email, password = buyer_credentials()
    if page not in ("checkout", "cart"):
        raise ModuleError(VERIFY_BAD_STORE_URL, "page must be 'checkout' or 'cart'")
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise ModuleError(VERIFY_BROWSER_MISSING,
                          "Playwright is not installed. Run: pip install playwright && playwright install chromium") from error

    run_id = f"verify_{label}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    out_dir = OUTPUT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    run = _Run(store_url, label, out_dir)

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo, args=BROWSER_ARGS)
        except PlaywrightError as error:
            raise ModuleError(VERIFY_BROWSER_MISSING,
                              f"Could not start Chromium. Run: playwright install chromium ({error})") from error
        context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US",
                                      user_agent=_normal_user_agent(browser))
        # Hide the "controlled by automation" flag. PayPal's newer email-first login
        # page silently ignores the Next button for browsers that report it.
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        store = context.new_page()
        try:
            return _run_purchase(run, store, context, store_url, page, email, password)
        except Exception as error:  # unexpected browser problem: report, don't crash the backend
            run.shot(store, "unexpected_error")
            return run.fail(FAIL_STORE, f"Unexpected error: {type(error).__name__}: {error}")
        finally:
            context.close()
            browser.close()


def _run_purchase(run: _Run, store, context, store_url: str, page: str, email: str, password: str) -> dict:
    # 1. Add the product to the cart.
    store.goto(store_url + "/", wait_until="domcontentloaded")
    if not store.locator("#add-to-cart").count():
        run.shot(store, "product_page")
        return run.fail(FAIL_STORE, "Product page has no #add-to-cart button.")
    store.click("#add-to-cart")
    run.step("added_to_cart")

    # 2. Open the payment page and wait for the PayPal button.
    store.goto(f"{store_url}/{page}", wait_until="domcontentloaded")
    button, sdk = _find_paypal_button(store, BUTTON_WAIT_SECONDS)
    run.shot(store, f"{page}_page")
    if button is None:
        return run.fail(FAIL_NO_BUTTON, sdk)
    run.result["paypal_sdk"] = sdk
    run.step("paypal_button_found", detail=f"SDK {sdk} on /{page}")

    # 3. Click PayPal: a PayPal window (popup) opens. PayPal ignores clicks while
    #    its buttons are still loading, so wait for them to settle and retry once.
    _wait_for_buttons_ready(store, sdk)
    popup = None
    for attempt in range(CLICK_ATTEMPTS):
        try:
            with context.expect_page(timeout=POPUP_OPEN_SECONDS * 1000) as popup_info:
                button.click()
            popup = popup_info.value
            break
        except Exception:
            if attempt + 1 < CLICK_ATTEMPTS:
                run.step("paypal_click_retry", ok=True, detail="No PayPal window yet; clicking again")
                store.wait_for_timeout(2000)
    if popup is None:
        run.shot(store, "no_popup")
        status = store.locator("#order-status").first
        detail = status.inner_text().strip() if status.count() else ""
        return run.fail(FAIL_NO_POPUP, detail or "Clicking PayPal did not open the PayPal window.")
    run.step("paypal_window_opened")

    # 4. Log in as the Sandbox buyer and pay.
    failure = complete_paypal_popup(popup, email, password)
    if failure:
        if not popup.is_closed():
            run.shot(popup, "paypal_window")
        messages = {
            FAIL_NOT_SANDBOX: "The PayPal window was not sandbox.paypal.com, so no login was typed.",
            FAIL_SELLER: "PayPal says this is the seller's account. Use a Personal (buyer) Sandbox account.",
            FAIL_LOGIN: "PayPal rejected the buyer email/password in .env.",
            FAIL_PAYPAL_PAGE: "PayPal showed 'Things don't appear to be working'. Use a United States "
                              "Personal Sandbox account, or try again later.",
            FAIL_POPUP_TIMEOUT: "Could not finish login and payment in the PayPal window in time.",
        }
        return run.fail(failure, messages.get(failure, failure))
    run.step("paid_in_paypal_window")

    # 5. The store captures the payment and redirects to /success?order=...
    try:
        store.wait_for_url(re.compile(r".*/success\?order=.*"), timeout=SUCCESS_WAIT_SECONDS * 1000)
    except Exception:
        run.shot(store, "after_paypal")
        status = store.locator("#order-status").first
        detail = status.inner_text().strip() if status.count() else ""
        return run.fail(FAIL_CAPTURE, detail or "The store did not reach the success page.")
    order_id = order_id_from_url(store.url)
    run.result["order_id"] = order_id
    store.wait_for_load_state("domcontentloaded")
    run.shot(store, "success_page")
    run.step("store_success_page", detail=order_id)

    # 6. Double-check with PayPal's Orders API.
    _confirm_with_api(run, order_id)
    return run.finish()


def _confirm_with_api(run: _Run, order_id: str) -> None:
    try:
        from paypal_integration import PayPalClient
        client = PayPalClient()
        if not client.is_configured():
            raise RuntimeError("PayPal API keys not set")
        order = client.get_order(order_id)
    except Exception as error:
        message = getattr(error, "message", str(error))
        run.result["warnings"].append(f"Could not confirm with the Orders API: {message}")
        run.result["purchase_succeeded"] = bool(order_id)  # success page only
        run.step("orders_api_check", ok=False, detail=message)
        return
    run.result.update(order_status=order["status"], amount=order["amount"],
                      currency=order["currency"], api_confirmed=True)
    run.step("orders_api_check", ok=order["status"] == "COMPLETED", detail=order["status"])
    if order["status"] == "COMPLETED":
        run.result["purchase_succeeded"] = True
    else:
        run.result["error_code"] = FAIL_NOT_COMPLETED
        run.result["error_message"] = f"PayPal says the order is {order['status']}, not COMPLETED."


def compare_runs(before: dict, after: dict) -> dict:
    """Summarise the difference between a 'before' and 'after' verification."""
    def describe(run: dict) -> str:
        if run.get("purchase_succeeded"):
            return f"paid with SDK {run.get('paypal_sdk') or '?'} in {run.get('duration_seconds', 0)}s"
        return f"failed ({run.get('error_code') or 'unknown'})"

    both_paid = bool(before.get("purchase_succeeded") and after.get("purchase_succeeded"))
    changes = []
    if before.get("paypal_sdk") != after.get("paypal_sdk") and after.get("paypal_sdk"):
        changes.append(f"PayPal SDK {before.get('paypal_sdk') or 'unknown'} -> {after.get('paypal_sdk')}")
    if before.get("purchase_succeeded") and not after.get("purchase_succeeded"):
        changes.append("REGRESSION: the upgrade broke checkout. Do not approve.")
    if not before.get("purchase_succeeded") and after.get("purchase_succeeded"):
        if before.get("error_code") in STORE_FAILURES:
            changes.append("The upgrade fixed a checkout that was failing.")
        else:
            # The "before" run stopped inside PayPal's window or at login: that says
            # nothing about the old store, so do not claim the upgrade fixed it.
            changes.append(f"The 'before' payment could not be completed by the verifier "
                           f"({before.get('error_code') or 'unknown'}); this is not a store problem.")

    if both_paid:
        summary = "Checkout works before and after the upgrade."
    elif after.get("purchase_succeeded"):
        summary = "Checkout works after the upgrade."
    else:
        summary = "The upgraded checkout did not complete a Sandbox payment."
    return {
        "before": before,
        "after": after,
        "safe_to_approve": bool(after.get("purchase_succeeded")),
        "summary": summary,
        "changes": changes,
        "before_text": describe(before),
        "after_text": describe(after),
    }
