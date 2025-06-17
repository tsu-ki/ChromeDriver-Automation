# zefoy_views.py
import os
import sys
import time
from pathlib import Path

from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- chromium bits ----------------------------------------------------------
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
# ---------------------------------------------------------------------------


ZEFOY_HOME = "https://zefoy.com/"
TARGET_URL  = (
    "https://www.tiktok.com/@tyma.uk/video/7479124834044235030"
)
AD_URL_PATTERNS = [
    "*#goog_fullscreen_ad*",
    "*://*.doubleclick.net/*",
    "*://*.googleadservices.com/*",
    "*://*.googlesyndication.com/*",
    "*://*.google-analytics.com/*",
    "*://*.adnxs.com/*",
    "*://*.adsafeprotected.com/*",
    "*://*.pubmatic.com/*",
    "*://*.adform.net/*",
    "*://*.moatads.com/*"
]

WAIT_HOME_LOAD   = 120
WAIT_ELEMENT     =  60
LOOP_SLEEP       =   1
WAIT_CLOUDFLARE  = 180
LOG_DIR          = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def make_driver() -> uc.Chrome:
    """Spin up Chrome with several network-level ad-blocking rules."""
    logger.debug("Bootstrapping Chrome driver …")

    chrome_opts = Options()
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    chrome_opts.add_argument("--disable-notifications")
    chrome_opts.add_argument("--disable-infobars")
    chrome_opts.add_argument("--start-maximized")

    driver = uc.Chrome(options=chrome_opts)

    logger.debug("Blocking ad urls → {}", AD_URL_PATTERNS)
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": AD_URL_PATTERNS})

    return driver


def wait_for_manual_captcha(driver):
    logger.info("Waiting up to {} s for user to solve captcha …", WAIT_HOME_LOAD)
    try:
        WebDriverWait(driver, WAIT_HOME_LOAD).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button.t-views-button"))
        )
        logger.success("Captcha solved – home page detected.")
    except TimeoutException:
        logger.error("Captcha not solved within {} s. Aborting.", WAIT_HOME_LOAD)
        raise


def click_views_card(driver):
    logger.info("Clicking the Views ▶️ card …")
    arrow_btn = WebDriverWait(driver, WAIT_ELEMENT).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.t-views-button"))
    )
    arrow_btn.click()


def submit_video(driver, video_url: str):
    logger.info("Entering video URL and pressing Search …")

    end_time = time.time() + WAIT_ELEMENT
    input_box = None
    while time.time() < end_time:
        input_box = get_visible_video_input(driver)
        if input_box:
            break
        time.sleep(0.5)

    if not input_box:
        raise TimeoutException("Visible 'Enter Video URL' input not found")

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_box)

    end_time = time.time() + WAIT_ELEMENT
    while time.time() < end_time:
        if input_box.is_enabled() and input_box.is_displayed():
            break
        time.sleep(0.5)

    try:
        input_box.clear()
        input_box.click()
        input_box.send_keys(video_url)
    except Exception as e:
        logger.debug("send_keys failed: {} – will fallback to JS setValue", e)

    if input_box.get_attribute("value").strip() != video_url:
        logger.debug("Value not reflected in DOM, injecting via JS…")
        driver.execute_script("arguments[0].value = arguments[1];", input_box, video_url)
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
            input_box,
        )

    form_el = input_box.find_element(By.XPATH, "ancestor::form")
    search_btn = form_el.find_element(By.XPATH, ".//button[@type='submit']")

    WebDriverWait(driver, WAIT_ELEMENT).until(lambda d: search_btn.is_displayed() and search_btn.is_enabled())

    try:
        search_btn.click()
        time.sleep(2)  # give UI a moment before rate-limit span appears
    except Exception as e:
        logger.debug("Native click failed: {} – using JS click", e)
        driver.execute_script("arguments[0].click();", search_btn)


def wait_for_ready_and_fire(driver):
    """After cooldown READY, Search again then hit the video-camera submit button.

    Flow:
    1. Poll the #login-countdown span until text contains READY.
    2. Click the blue "Search" (button.disableButton) that becomes re-enabled.
       This refreshes the form.
    3. Wait for the dark "video-camera" button.wbutton to appear/enabled and click it.
    4. Wait for green "Successfully … views sent" span, then pause 5 s so the
       server can finish processing before we navigate home.
    """

    logger.info("Waiting until rate-limit countdown reaches READY …")

    countdown = WebDriverWait(driver, WAIT_ELEMENT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "span#login-countdown"))
    )

    # ── 1) Wait for READY text ─────────────────────────────────────────────
    while True:
        txt = countdown.text.strip()
        logger.debug("Countdown text → {}", txt)
        if "READY" in txt.upper():
            logger.success("Rate limit reset – attempting second Search …")
            break
        time.sleep(LOOP_SLEEP)

    # ── 2) Click the blue Search button (it gets re-enabled) ────────────────
    def get_enabled_search():
        for btn in driver.find_elements(By.CSS_SELECTOR, "button.disableButton[type='submit']"):
            if btn.is_displayed() and btn.is_enabled() and btn.get_attribute("disabled") is None:
                return btn
        return None

    search_btn = WebDriverWait(driver, WAIT_ELEMENT).until(lambda d: get_enabled_search())

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", search_btn)
    try:
        search_btn.click()
        time.sleep(2)  # pause after second Search click
    except Exception as e:
        logger.debug("Native click failed on Search: {} – using JS", e)
        driver.execute_script("arguments[0].click();", search_btn)

    logger.info("Search clicked – waiting for Submit (video-camera) button …")

    # ── 3) Wait for dark wbutton to appear & click ─────────────────────────
    def get_enabled_wbutton():
        for btn in driver.find_elements(By.CSS_SELECTOR, "button.wbutton[type='submit']"):
            if btn.is_displayed() and btn.is_enabled() and btn.get_attribute("disabled") is None:
                return btn
        return None

    wbutton = WebDriverWait(driver, WAIT_ELEMENT).until(lambda d: get_enabled_wbutton())

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", wbutton)
    try:
        wbutton.click()
        time.sleep(2)  # pause after Submit click
    except Exception as e:
        logger.debug("Native click failed on video-camera button: {} – using JS", e)
        driver.execute_script("arguments[0].click();", wbutton)

    # ── 4) Wait for success message and pause 5 s ──────────────────────────
    try:
        WebDriverWait(driver, WAIT_ELEMENT).until(
            EC.visibility_of_element_located((By.XPATH, "//span[contains(text(),'Successfully') and contains(text(),'views sent')]"))
        )
        logger.success("🎉  Views successfully submitted!")
    except TimeoutException:
        logger.warning("Success message not detected within {} s", WAIT_ELEMENT)

    time.sleep(4)  # brief post-success delay before navigating Home


def main():
    LOG_FILE = LOG_DIR / f"run-{time.strftime('%Y-%m-%d')}.log"
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(LOG_FILE, rotation="500 KB", level="DEBUG",
               format="{time} | {level} | {message}")

    try:
        driver = make_driver()
        driver.get(ZEFOY_HOME)

        wait_for_cloudflare(driver)
        wait_for_manual_captcha(driver)

        remove_inline_ads(driver)

        run_count = 0
        while True:
            run_count += 1
            logger.info("=== RUN {} started at {} ===", run_count, time.strftime("%H:%M:%S"))

            click_views_card(driver)

            try:
                wait_for_cloudflare(driver)
            except TimeoutException:
                pass

            remove_inline_ads(driver)

            try:
                submit_video(driver, TARGET_URL)
                wait_for_ready_and_fire(driver)
                logger.success("RUN {} completed ✅", run_count)
            except Exception as inner_exc:
                logger.exception("RUN {} failed: {}", run_count, inner_exc)

            go_home(driver)
            remove_inline_ads(driver)
            time.sleep(4)  # pause before next iteration

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt – exiting loop …")
    finally:
        if "driver" in locals():
            driver.quit()
        logger.info("Session ended – logs saved to {}", LOG_FILE.resolve())


def remove_inline_ads(driver):
    script = """
        const selectors = [
            'iframe[src*="ad" i]',
            'iframe[src*="doubleclick" i]',
            'iframe[src*="googlesyndication" i]',
            'div[id*="ad" i]',
            'div[class*="ad" i]',
            'div[data-google-query-id]'
        ];
        try {
            selectors.forEach(sel =>
                document.querySelectorAll(sel).forEach(el => el.remove())
            );
        } catch(e) { /* no-op */ }
    """
    driver.execute_script(script)
    logger.debug("Inline ad/overlay elements (if any) removed from DOM.")

    return driver


def wait_for_cloudflare(driver):
    logger.info("Waiting for Cloudflare verification page to finish … (≤ {} s)", WAIT_CLOUDFLARE)
    end_time = time.time() + WAIT_CLOUDFLARE

    while time.time() < end_time:
        if driver.find_elements(By.CSS_SELECTOR, "button.t-views-button"):
            logger.success("Cloudflare challenge passed – Zefoy dashboard reachable.")
            return

        page_text = driver.page_source
        if "Ray ID" not in page_text and "Just a moment" not in page_text:
            logger.debug("CF indicator not present any more – continuing …")
            return

        logger.debug("Still on CF check page – sleeping 2 s …")
        time.sleep(2)

    raise TimeoutException("Stuck on Cloudflare verification > {} s".format(WAIT_CLOUDFLARE))


def get_visible_video_input(driver):
    candidates = driver.find_elements(By.CSS_SELECTOR, "input[placeholder='Enter Video URL']")
    for el in candidates:
        if el.is_displayed():
            return el
    return None


def go_home(driver):
    logger.info("Returning to Home page …")
    try:
        home_anchor = driver.find_element(By.CSS_SELECTOR, "nav a.nav-link.navbar-brand")
    except Exception:
        icon = driver.find_element(By.CSS_SELECTOR, "nav i.fa-home")
        home_anchor = icon.find_element(By.XPATH, "ancestor::a")

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", home_anchor)
    try:
        home_anchor.click()
    except Exception as e:
        logger.debug("Native click on Home failed: {} – using JS", e)
        driver.execute_script("arguments[0].click();", home_anchor)

    WebDriverWait(driver, WAIT_ELEMENT).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "button.t-views-button"))
    )


if __name__ == "__main__":
    main()