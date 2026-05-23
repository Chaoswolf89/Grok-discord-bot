# =============================================
# GROK DISCORD BOT - WITH PERSISTENT SQLITE DATABASE
# =============================================

import discord
import os
import time
import random
import aiosqlite
from discord import app_commands
from xai_sdk import Client
from xai_sdk.chat import system, user, assistant

# ==================== CONFIG ====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))

if not DISCORD_TOKEN or not XAI_API_KEY:
    print("❌ Missing DISCORD_TOKEN or XAI_API_KEY!")
    exit(1)

print("✅ Tokens loaded successfully!")
print(f"   Discord token starts with: {DISCORD_TOKEN[:4]}... ends with: ...{DISCORD_TOKEN[-4:]}")
print(f"   XAI key starts with: {XAI_API_KEY[:6]}")

xai_client = Client(api_key=XAI_API_KEY)

# ==================== DATABASE SETUP ====================
DB_FILE = "bot_memory.db"
MAX_HISTORY = 12
COOLDOWN_SECONDS = 6
START_TIME = time.time()
user_cooldowns = {}

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    print("✅ Database initialized (SQLite)")

async def save_message(user_id: str, role: str, content: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        await db.commit()

async def get_user_history(user_id: str, limit: int = MAX_HISTORY):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            """
            SELECT role, content FROM conversations 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """,
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        # Return in chronological order (oldest first)
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

def is_owner(interaction: discord.Interaction):
    return interaction.user.id == BOT_OWNER_ID

# ==================== BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ==================== EVENTS ====================
@client.event
async def on_ready():
    await init_db()           # Initialize database when bot starts
    await tree.sync()
    print(f"✅ {client.user} is online on {len(client.guilds)} servers!")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if client.user.mentioned_in(message):
        replies = ["Yeah? What's up?", "You rang?", "I'm here. What's on your mind?", "Sup. Hit me with it.", "You got my attention 👀"]
        await message.channel.send(random.choice(replies))

# ==================== COMMANDS ====================

@tree.command(name="ask", description="Chat with Grok (with persistent memory)")
@app_commands.describe(question="What do you want to ask?")
async def ask(interaction: discord.Interaction, question: str):
    user_id = str(interaction.user.id)
    now = time.time()

    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        await interaction.response.send_message("⏳ Slow down a bit.", ephemeral=True)
        return
    user_cooldowns[user_id] = now

    await interaction.response.defer()

    try:
        history = await get_user_history(user_id)

        chat = xai_client.chat.create(model="grok-4")
        chat.append(system("You are Grok, helpful, witty, and a little chaotic. Remember previous messages."))

        for msg in history:
            if msg["role"] == "user":
                chat.append(user(msg["content"]))
            else:
                chat.append(assistant(msg["content"]))

        chat.append(user(question))
        response = await chat.sample()
        reply_text = response.text

        # Save to database
        await save_message(user_id, "user", question)
        await save_message(user_id, "assistant", reply_text)

        await interaction.followup.send(reply_text)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:200]}")

@tree.command(name="imagine", description="Generate images with Grok (NSFW allowed)")
@app_commands.describe(prompt="Describe what you want to see")
async def imagine(interaction: discord.Interaction, prompt: str):
    user_id = str(interaction.user.id)
    now = time.time()

    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        await interaction.response.send_message("⏳ Slow down.", ephemeral=True)
        return
    user_cooldowns[user_id] = now

    await interaction.response.defer()
    try:
        await interaction.followup.send("🎨 Generating...")
        response = xai_client.image.sample(prompt=prompt, model="grok-imagine-image-quality")
        embed = discord.Embed(title="Grok Imagine", description=prompt[:200], color=0xFF00FF)
        embed.set_image(url=response.images[0].url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:200]}")

@tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot Commands", color=0x00FFAA)
    embed.add_field(name="/ask [question]", value="Chat with Grok (persistent memory)", inline=False)
    embed.add_field(name="/imagine [prompt]", value="Generate images (NSFW allowed)", inline=False)
    embed.add_field(name="/ping", value="Check bot latency", inline=True)
    embed.add_field(name="/uptime", value="How long the bot has been running", inline=True)
    embed.add_field(name="/stats", value="Show your memory stats", inline=True)
    embed.add_field(name="/memory", value="Clear your conversation memory", inline=True)
    if is_owner(interaction):
        embed.add_field(name="/servers", value="List all servers (Owner only)", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(client.latency * 1000)}ms")

@tree.command(name="uptime", description="How long the bot has been running")
async def uptime(interaction: discord.Interaction):
    uptime_seconds = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    await interaction.response.send_message(f"⏱️ Uptime: {hours}h {minutes}m {seconds}s")

@tree.command(name="stats", description="Show your memory stats")
async def stats(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    history = await get_user_history(user_id, limit=100)
    await interaction.response.send_message(f"**Your stats:**\n• Messages in memory: {len(history)}")

@tree.command(name="memory", description="Clear your conversation memory")
async def memory_clear(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        await db.commit()
    await interaction.response.send_message("🧹 Your conversation memory has been cleared.")

@tree.command(name="servers", description="List all servers (Owner only)")
async def servers(interaction: discord.Interaction):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Owner only.", ephemeral=True)
        return
    guilds = [f"• {g.name} ({g.member_count} members)" for g in client.guilds]
    await interaction.response.send_message("**Servers I'm in:**\n" + "\n".join(guilds))

client.run(DISCORD_TOKEN)