# ------------------------------------------------------------------------------
# Copyright (c) 2026 Adrian Pascut (ESLAMERA LIMITED). All rights reserved.
#
# LICENCE NOTICE:
# Permitted ONLY for free, non-commercial personal job-search use by Private
# Individuals. Any use, copying, or modification by a Commercial Entity—or for
# non-job-search purposes—requires prior written permission from the author.
#
# BREACH PENALTIES (Liquidated Damages):
# - Commercial Entity Breach: £100,000 per breach/deployment + legal fees.
# - Private Individual Breach: £10,000 per breach + legal fees.
#
# See the root LICENSE file for full legal terms, restrictions, and disclaimers.
# ------------------------------------------------------------------------------

# ai_assistant.py
from playwright.async_api import BrowserContext, Page
from base_assistant import BaseAIAssistant
from gemini_assistant import GeminiAssistant
from groq_assistant import GroqAssistant
from config_manager import ConfigManager


class AIAssistant:
    def __init__(self, browser_context: BrowserContext):
        self.context = browser_context
        
        # Instantiate both dedicated assistants
        self.copilot = BaseAIAssistant(browser_context, ConfigManager.AI_COPILOT)
        self.groq = GroqAssistant()
        self.gemini = GeminiAssistant()

    async def initialize_tabs(self, status_callback=None):
        """Opens dedicated tabs for Copilot and Gemini inside the active browser context."""
        if status_callback:
            status_callback("[*] Initializing AI Assistant tabs (Copilot & Gemini)...")

        # Initialize Copilot tab
        await self.copilot.initialize_tab(status_callback)

        # Initialize Gemini tab
        await self.gemini.initialize_tab(status_callback)

        if status_callback:
            status_callback("✅ AI Assistant tabs successfully launched.")