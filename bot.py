import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from database import Database
from config import ADMIN_IDS, BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_valid_discord_link(link: str) -> bool:
    link = link.strip().lower()
    return (
        "discord.com/users/" in link or
        "discordapp.com/users/" in link or
        link.startswith("@") or
        "discord.gg/" in link
    )


# ─────────────────────────────────────────────
# USER COMMANDS
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.ensure_user(user.id, user.username or user.first_name)
    text = (
        f"👋 Hey {user.first_name}! Welcome to the Referral Contest Bot.\n\n"
        "📋 *How it works:*\n"
        "1. Invite people to our Discord server\n"
        "2. Submit their Discord profile link using /submit\n"
        "3. An admin will verify and approve each submission\n"
        "4. Track your score with /mystats\n\n"
        "🏆 The person with the most approved referrals wins!\n\n"
        "*Commands:*\n"
        "/submit `<discord_link>` — Submit a referral\n"
        "/mystats — View your referral stats\n"
        "/help — Show this message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.ensure_user(user.id, user.username or user.first_name)

    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/submit <discord_profile_link>`\n\n"
            "Example:\n`/submit https://discord.com/users/123456789`",
            parse_mode="Markdown"
        )
        return

    link = " ".join(context.args).strip()

    if not is_valid_discord_link(link):
        await update.message.reply_text(
            "❌ That doesn't look like a valid Discord profile link.\n\n"
            "Please use a link like:\n`https://discord.com/users/123456789`",
            parse_mode="Markdown"
        )
        return

    if await db.link_already_submitted(link):
        await update.message.reply_text(
            "⚠️ This Discord profile has already been submitted. "
            "Each referral can only be counted once."
        )
        return

    submission_id = await db.add_submission(user.id, link)

    await update.message.reply_text(
        f"✅ Referral submitted!\n\n"
        f"🔗 Link: `{link}`\n"
        f"🆔 Submission ID: `{submission_id}`\n"
        f"⏳ Status: *Pending approval*\n\n"
        f"You'll be notified once an admin reviews it.",
        parse_mode="Markdown"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"📨 *New Referral Submission*\n\n"
                    f"👤 From: @{user.username or user.first_name} (`{user.id}`)\n"
                    f"🔗 Link: `{link}`\n"
                    f"🆔 ID: `{submission_id}`\n\n"
                    f"Use /approve `{submission_id}` or /reject `{submission_id}` to review."
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")


async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.ensure_user(user.id, user.username or user.first_name)

    stats = await db.get_user_stats(user.id)
    rank = await db.get_user_rank(user.id)

    text = (
        f"📊 *Your Referral Stats*\n\n"
        f"👤 {user.first_name}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ Approved: *{stats['approved']}*\n"
        f"⏳ Pending: *{stats['pending']}*\n"
        f"❌ Rejected: *{stats['rejected']}*\n"
        f"📦 Total Submitted: *{stats['total']}*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🏆 Current Rank: *#{rank}*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
# ADMIN COMMANDS
# ─────────────────────────────────────────────

async def list_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    leaderboard = await db.get_leaderboard()

    if not leaderboard:
        await update.message.reply_text("No approved referrals yet.")
        return

    lines = ["🏆 *Referral Leaderboard*\n━━━━━━━━━━━━━━━━"]
    medals = ["🥇", "🥈", "🥉"]

    for i, row in enumerate(leaderboard):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} @{row['username']} — *{row['approved']}* approved ({row['pending']} pending)")

    lines.append(f"\n━━━━━━━━━━━━━━━━\n👥 Total participants: {len(leaderboard)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    submissions = await db.get_pending_submissions()

    if not submissions:
        await update.message.reply_text("✅ No pending submissions!")
        return

    lines = [f"⏳ *Pending Submissions ({len(submissions)})*\n━━━━━━━━━━━━━━━━"]
    for s in submissions:
        lines.append(
            f"🆔 `{s['id']}` | @{s['username']}\n"
            f"   🔗 {s['link']}\n"
            f"   📅 {s['submitted_at']}\n"
        )
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("Use /approve `<id>` or /reject `<id>` `<reason>`")

    full_text = "\n".join(lines)
    if len(full_text) > 4000:
        chunk = []
        for line in lines:
            chunk.append(line)
            if len("\n".join(chunk)) > 3500:
                await update.message.reply_text("\n".join(chunk), parse_mode="Markdown")
                chunk = []
        if chunk:
            await update.message.reply_text("\n".join(chunk), parse_mode="Markdown")
    else:
        await update.message.reply_text(full_text, parse_mode="Markdown")


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/approve <submission_id>`", parse_mode="Markdown")
        return

    sub_id = context.args[0].strip()
    result = await db.update_submission_status(sub_id, "approved")

    if not result:
        await update.message.reply_text(f"❌ Submission `{sub_id}` not found or already reviewed.", parse_mode="Markdown")
        return

    await update.message.reply_text(f"✅ Submission `{sub_id}` approved!", parse_mode="Markdown")

    try:
        await context.bot.send_message(
            chat_id=result["user_id"],
            text=(
                f"🎉 *Referral Approved!*\n\n"
                f"Your submission `{sub_id}` has been approved.\n"
                f"🔗 `{result['link']}`\n\n"
                f"Keep inviting to climb the leaderboard! 🏆\n"
                f"Check your stats with /mystats"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not notify user {result['user_id']}: {e}")


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/reject <submission_id> [reason]`", parse_mode="Markdown")
        return

    sub_id = context.args[0].strip()
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Does not meet requirements"

    result = await db.update_submission_status(sub_id, "rejected", reason)

    if not result:
        await update.message.reply_text(f"❌ Submission `{sub_id}` not found or already reviewed.", parse_mode="Markdown")
        return

    await update.message.reply_text(f"🗑️ Submission `{sub_id}` rejected.", parse_mode="Markdown")

    try:
        await context.bot.send_message(
            chat_id=result["user_id"],
            text=(
                f"❌ *Referral Rejected*\n\n"
                f"Submission `{sub_id}` was not approved.\n"
                f"🔗 `{result['link']}`\n"
                f"📝 Reason: _{reason}_\n\n"
                f"Make sure the person has actually joined the Discord server before submitting."
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not notify user {result['user_id']}: {e}")


async def reset_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    if not context.args or context.args[0] != "CONFIRM":
        await update.message.reply_text(
            "⚠️ This will delete ALL submission data.\n\n"
            "To confirm: `/reset CONFIRM`",
            parse_mode="Markdown"
        )
        return

    await db.reset_all()
    await update.message.reply_text("🔄 Contest has been reset. All submissions cleared.")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")


async def post_init(application: Application):
    await db.init()
    logger.info("Database initialized.")


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set in environment variables")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("submit", submit))
    app.add_handler(CommandHandler("mystats", mystats))
    app.add_handler(CommandHandler("list", list_referrals))
    app.add_handler(CommandHandler("pending", pending))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("reset", reset_contest))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
