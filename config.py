import os

# ─────────────────────────────────────────────
# BOT CONFIGURATION
# ─────────────────────────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Add Telegram user IDs of all admins here
# Get your ID by messaging @userinfobot on Telegram
_admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [
    int(uid.strip())
    for uid in _admin_ids_raw.split(",")
    if uid.strip().isdigit()
]

# Fallback: hardcode admin IDs here if not using env vars
# ADMIN_IDS = [123456789, 987654321]
