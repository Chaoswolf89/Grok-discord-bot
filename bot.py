import discord
import os
import time
import asyncio
import random
import json
import logging
from datetime import datetime
from discord import app_commands, Embed, ui
from import discord
import os
import time
import asyncio
import random
import json
import logging
from datetime import datetime
from discord import app_commands, Embed, ui
from xai_sdk import Client
from xai_sdk.chat import system, user, assistant

# ==================== CONFIG ====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))

# Advanced Settings
conversation_memory = {}
user_cooldowns = {}
MAX_HISTORY = 15
COOLDOWN_SECONDS = 4
START_TIME = time.time()
MEMORY_FILE = "conversation_memory.json"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not DISCORD_TOKEN or not XAI_API_KEY:
    print("❌ Missing DISCORD_TOKEN or XAI_API_KEY!")
    exit(1)

print("✅ Tokens loaded successfully!")

xai_client = Client(api_key=XAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def is_owner(interaction: discord.Interaction):
    return interaction.user.id == BOT_OWNER_ID


def get_uptime():
    uptime = time.time() - START_TIME
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    return f"{hours}h {minutes}m {seconds}s"


def load_memory():
    global conversation_memory
    try:
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
            conversation_memory = {k: [eval(msg) for msg in v] for k, v in data.items()}
        logger.info(f"✅ Loaded memory for {len(conversation_memory)} channels")
    except:
        conversation_memory = {}


def save_memory():
    try:
        data = {k: [str(msg) for msg in v] for k, v in conversation_memory.items()}
        with open(MEMORY_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save memory: {e}")


@client.event
async def on_ready():
    await tree.sync()
    load_memory()
    print(f"✅ {client.user} is online on {len(client.guilds)} servers!")
    logger.info("Bot fully initialized and ready!")


# ===================== ASK WITH MEMORY =====================
@tree.command(name="ask", description="Chat with Grok (Memory enabled)")
@app_commands.describe(question="Your question")
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer()

    user_id = interaction.user.id
    now = time.time()
    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        return await interaction.followup.send("⏳ Slow down! Wait a few seconds.")

    user_cooldowns[user_id] = now

    channel_id = str(interaction.channel_id)
    if channel_id not in conversation_memory:
        conversation_memory[channel_id] = []

    conversation_memory[channel_id].append(user(question))

    if len(conversation_memory[channel_id]) > MAX_HISTORY * 2:
        conversation_memory[channel_id] = conversation_memory[channel_id][-MAX_HISTORY*2:]

    try:
        chat = xai_client.chat.create(model="grok-4")
        chat.append(system("You are a helpful, witty, and fun Grok bot."))
        for msg in conversation_memory[channel_id]:
            chat.append(msg)

        response = await chat.sample()
        reply = response.text
        conversation_memory[channel_id].append(assistant(reply))

        await interaction.followup.send(reply)
        save_memory()
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:250]}")


# ===================== IMAGINE =====================
@tree.command(name="imagine", description="Generate images (NSFW allowed)")
@app_commands.describe(prompt="Describe the image")
async def imagine(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        await interaction.followup.send("🎨 Generating image...")
        response = xai_client.image.sample(prompt=prompt)
        embed = discord.Embed(title="Grok Imagine", description=prompt[:200], color=0xFF00FF)
        embed.set_image(url=response.images[0].url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:250]}")


# ===================== UTILITY COMMANDS =====================
@tree.command(name="clear", description="Clear memory in this channel")
async def clear(interaction: discord.Interaction):
    channel_id = str(interaction.channel_id)
    if channel_id in conversation_memory:
        del conversation_memory[channel_id]
        save_memory()
        await interaction.response.send_message("🧹 Memory cleared for this channel!")
    else:
        await interaction.response.send_message("No memory to clear.")


@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! `{latency}ms`")


@tree.command(name="uptime", description="Show bot uptime")
async def uptime(interaction: discord.Interaction):
    await interaction.response.send_message(f"⏱️ Uptime: **{get_uptime()}**")


@tree.command(name="stats", description="Show detailed bot stats")
async def stats(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot Statistics", color=0x1DA1F2, timestamp=datetime.utcnow())
    embed.add_field(name="Servers", value=len(client.guilds), inline=True)
    embed.add_field(name="Latency", value=f"{round(client.latency*1000)}ms", inline=True)
    embed.add_field(name="Uptime", value=get_uptime(), inline=True)
    embed.add_field(name="Active Memory Channels", value=len(conversation_memory), inline=True)
    embed.add_field(name="Memory File", value="Loaded" if os.path.exists(MEMORY_FILE) else "Not Found", inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot - Ultimate Version", color=0x1DA1F2)
    embed.add_field(name="Chat & Images", value="/ask [question]\n/imagine [prompt]", inline=False)
    embed.add_field(name="Utility", value="/clear\n/ping\n/uptime\n/stats\n/help", inline=False)
    embed.add_field(name="Owner", value="/servers", inline=False)
    await interaction.response.send_message(embed=embed)


# ===================== OWNER COMMANDS =====================
@tree.command(name="servers", description="Show server count (Owner only)")
async def servers(interaction: discord.Interaction):
    if not is_owner(interaction):
        return await interaction.response.send_message("❌ Owner only", ephemeral=True)
    await interaction.response.send_message(f"🤖 Bot is in **{len(client.guilds)}** servers.")


# ===================== MENTION RESPONSE =====================
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if client.user in message.mentions:
        responses = ["Hey! 👋", "Yes?", "I'm here!", "What can I help with?", "Sup?", "Ready!", "Hello!"]
        await message.channel.send(random.choice(responses))


client.run(DISCORD_TOKEN) import Client
from xai_sdk.chat import system, user, assistant

# ==================== CONFIG ====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))

# Advanced Settings
conversation_memory = {}
user_cooldowns = {}
MAX_HISTORY = 15
COOLDOWN_SECONDS = 4
START_TIME = time.time()
MEMORY_FILE = "conversation_memory.json"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not DISCORD_TOKEN or not XAI_API_KEY:
    print("❌ Missing DISCORD_TOKEN or XAI_API_KEY!")
    exit(1)

print("✅ Tokens loaded successfully!")

xai_client = Client(api_key=XAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def is_owner(interaction: discord.Interaction):
    return interaction.user.id == BOT_OWNER_ID


def get_uptime():
    uptime = time.time() - START_TIME
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)
    return f"{hours}h {minutes}m {seconds}s"


def load_memory():
    global conversation_memory
    try:
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
            conversation_memory = {k: [eval(msg) for msg in v] for k, v in data.items()}
        logger.info(f"✅ Loaded memory for {len(conversation_memory)} channels")
    except:
        conversation_memory = {}


def save_memory():
    try:
        data = {k: [str(msg) for msg in v] for k, v in conversation_memory.items()}
        with open(MEMORY_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save memory: {e}")


@client.event
async def on_ready():
    await tree.sync()
    load_memory()
    print(f"✅ {client.user} is online on {len(client.guilds)} servers!")
    logger.info("Bot fully initialized and ready!")


# ===================== ASK WITH MEMORY =====================
@tree.command(name="ask", description="Chat with Grok (Memory enabled)")
@app_commands.describe(question="Your question")
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer()

    user_id = interaction.user.id
    now = time.time()
    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        return await interaction.followup.send("⏳ Slow down! Wait a few seconds.")

    user_cooldowns[user_id] = now

    channel_id = str(interaction.channel_id)
    if channel_id not in conversation_memory:
        conversation_memory[channel_id] = []

    conversation_memory[channel_id].append(user(question))

    if len(conversation_memory[channel_id]) > MAX_HISTORY * 2:
        conversation_memory[channel_id] = conversation_memory[channel_id][-MAX_HISTORY*2:]

    try:
        chat = xai_client.chat.create(model="grok-4")
        chat.append(system("You are a helpful, witty, and fun Grok bot."))
        for msg in conversation_memory[channel_id]:
            chat.append(msg)

        response = await chat.sample()
        reply = response.text
        conversation_memory[channel_id].append(assistant(reply))

        await interaction.followup.send(reply)
        save_memory()
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:250]}")


# ===================== IMAGINE =====================
@tree.command(name="imagine", description="Generate images (NSFW allowed)")
@app_commands.describe(prompt="Describe the image")
async def imagine(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        await interaction.followup.send("🎨 Generating image...")
        response = xai_client.image.sample(prompt=prompt)
        embed = discord.Embed(title="Grok Imagine", description=prompt[:200], color=0xFF00FF)
        embed.set_image(url=response.images[0].url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:250]}")


# ===================== UTILITY COMMANDS =====================
@tree.command(name="clear", description="Clear memory in this channel")
async def clear(interaction: discord.Interaction):
    channel_id = str(interaction.channel_id)
    if channel_id in conversation_memory:
        del conversation_memory[channel_id]
        save_memory()
        await interaction.response.send_message("🧹 Memory cleared for this channel!")
    else:
        await interaction.response.send_message("No memory to clear.")


@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! `{latency}ms`")


@tree.command(name="uptime", description="Show bot uptime")
async def uptime(interaction: discord.Interaction):
    await interaction.response.send_message(f"⏱️ Uptime: **{get_uptime()}**")


@tree.command(name="stats", description="Show detailed bot stats")
async def stats(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot Statistics", color=0x1DA1F2, timestamp=datetime.utcnow())
    embed.add_field(name="Servers", value=len(client.guilds), inline=True)
    embed.add_field(name="Latency", value=f"{round(client.latency*1000)}ms", inline=True)
    embed.add_field(name="Uptime", value=get_uptime(), inline=True)
    embed.add_field(name="Active Memory Channels", value=len(conversation_memory), inline=True)
    embed.add_field(name="Memory File", value="Loaded" if os.path.exists(MEMORY_FILE) else "Not Found", inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot - Ultimate Version", color=0x1DA1F2)
    embed.add_field(name="Chat & Images", value="/ask [question]\n/imagine [prompt]", inline=False)
    embed.add_field(name="Utility", value="/clear\n/ping\n/uptime\n/stats\n/help", inline=False)
    embed.add_field(name="Owner", value="/servers", inline=False)
    await interaction.response.send_message(embed=embed)


# ===================== OWNER COMMANDS =====================
@tree.command(name="servers", description="Show server count (Owner only)")
async def servers(interaction: discord.Interaction):
    if not is_owner(interaction):
        return await interaction.response.send_message("❌ Owner only", ephemeral=True)
    await interaction.response.send_message(f"🤖 Bot is in **{len(client.guilds)}** servers.")


# ===================== MENTION RESPONSE =====================
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if client.user in message.mentions:
        responses = ["Hey! 👋", "Yes?", "I'm here!", "What can I help with?", "Sup?", "Ready!", "Hello!"]
        await message.channel.send(random.choice(responses))


client.run(DISCORD_TOKEN)