"""
Interactive Login Setup Helper for Taskmaster Persistent Browser Profile.

Usage:
    python -m agent.browser.login_helper [--url URL]

Launches a real headed Chrome window with the persistent profile (data/browser_profile/)
allowing the user to log in manually to Google/YouTube, Spotify, GitHub, etc.
Once logged in, the user presses Enter in the terminal to save cookies and exit cleanly.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from agent.config import settings


async def run_login_helper(target_url: str):
    profile_dir = Path(settings.BROWSER_USER_DATA_DIR)
    profile_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("🤖 TASKMASTER PERSISTENT BROWSER PROFILE SETUP HELPER")
    print("=" * 70)
    print(f"Profile Directory: {profile_dir.resolve()}")
    print(f"Target URL:        {target_url}")
    print("\nInstructions:")
    print("1. A Chrome browser window will now open.")
    print("2. Log into your accounts (e.g. Google, YouTube, Spotify, GitHub).")
    print("3. Complete any 2FA or CAPTCHA prompts manually.")
    print("4. When you are fully logged in and ready, return here and press [ENTER].")
    print("=" * 70)

    async with async_playwright() as p:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
        ]
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=args,
            viewport=None,
            ignore_default_args=["--enable-automation"],
        )

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(target_url)

        # Wait for user confirmation in terminal
        await asyncio.get_event_loop().run_in_executor(None, input, "\n👉 Press [ENTER] once you have finished logging in to save and exit: ")

        print("\nSaving session cookies and profile state...")
        await context.close()
        print("✅ Session state saved successfully! Taskmaster can now reuse this profile autonomously.")


def main():
    parser = argparse.ArgumentParser(description="Taskmaster Browser Login Helper")
    parser.add_argument(
        "--url",
        default="https://accounts.google.com",
        help="Initial URL to open (default: https://accounts.google.com)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_login_helper(args.url))
    except KeyboardInterrupt:
        print("\nSetup cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
