#!/usr/bin/env python3
"""Capture screenshots for documentation using Playwright in mock mode."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path("docs/screenshots")
BASE_URL = "http://localhost:8000"

async def capture_screenshots():
    """Capture all documentation screenshots."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        
        # Use mock mode
        await page.goto(f"{BASE_URL}/?mock")
        await page.wait_for_load_state("networkidle")
        
        print("Capturing submit-view.png...")
        await page.screenshot(path=SCREENSHOTS_DIR / "submit-view.png")
        
        # Fill in report
        print("Capturing submit-filled.png...")
        await page.get_by_label("Report Text").fill("FINDINGS: Small bilateral pleural effusions. No pneumothorax.")
        await page.get_by_label("Patient ID").fill("MRN12345")
        await page.screenshot(path=SCREENSHOTS_DIR / "submit-filled.png")
        
        # Submit and navigate to reports list
        print("Capturing reports-list.png...")
        await page.get_by_role("button", name="Submit Report").click()
        await asyncio.sleep(2)  # Wait for hash route change
        await page.screenshot(path=SCREENSHOTS_DIR / "reports-list.png")
        
        # Navigate to report detail
        print("Capturing report-detail.png...")
        await page.goto(f"{BASE_URL}/?mock#/reports/rpt-mock-001")
        await asyncio.sleep(1)
        await page.screenshot(path=SCREENSHOTS_DIR / "report-detail.png")
        
        # Navigate to extraction detail
        print("Capturing extraction-detail.png...")
        await page.goto(f"{BASE_URL}/?mock#/extractions/extr-mock-001")
        await asyncio.sleep(2)  # Wait for users to load
        await page.screenshot(path=SCREENSHOTS_DIR / "extraction-detail.png", full_page=True)
        
        await browser.close()
        print("\n✅ All screenshots captured!")

if __name__ == "__main__":
    asyncio.run(capture_screenshots())
