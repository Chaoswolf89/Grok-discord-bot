import discord
import os
import time
import asyncio
import random
from discord import app_commands
from xai_sdk import Client
from xai_sdk.chat import system, user, assistant

# ==================== CONFIG ====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))

conversation_memory = {}
user_cooldowns = {}
MAX_HISTORY = 12
COOLDOWN_SECONDS = 5
START_TIME = time.time()

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
    return f"{hours}h {minutes}m"


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ {client.user} is online on {len(client.guilds)} servers!")


# ===================== CHAT WITH MEMORY =====================
@tree.command(name="ask", description="Chat with Grok (Memory enabled)")
@app_commands.describe(question="Your question")
async def ask(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    
    user_id = interaction.user.id
    now = time.time()
    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        return await interaction.followup.send("⏳ Slow down!")

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
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:300]}")


# ===================== IMAGINE =====================
@tree.command(name="imagine", description="Generate images with Grok (NSFW allowed)")
@app_commands.describe(prompt="Describe the image")
async def imagine(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        await interaction.followup.send("🎨 Generating...")
        response = xai_client.image.sample(prompt=prompt)
        embed = discord.Embed(title="Grok Imagine", description=prompt[:200], color=0xFF00FF)
        embed.set_image(url=response.images[0].url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:300]}")


# ===================== UTILITY =====================
@tree.command(name="clear", description="Clear memory in this channel")
async def clear(interaction: discord.Interaction):
    channel_id = str(interaction.channel_id)
    if channel_id in conversation_memory:
        del conversation_memory[channel_id]
        await interaction.response.send_message("🧹 Memory cleared!")
    else:
        await interaction.response.send_message("Nothing to clear.")


@tree.command(name="ping", description="Check latency")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! `{latency}ms`")


@tree.command(name="uptime", description="Show how long the bot has been running")
async def uptime(interaction: discord.Interaction):
    await interaction.response.send_message(f"⏱️ Uptime: **{get_uptime()}**")


@tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot - Ultimate Edition", color=0x1DA1F2)
    embed.add_field(name="Main", value="/ask\n/imagine", inline=False)
    embed.add_field(name="Utility", value="/clear\n/ping\n/uptime\n/help", inline=False)
    embed.add_field(name="Owner", value="/servers\n/reload", inline=False)
    await interaction.response.send_message(embed=embed)


# ===================== OWNER COMMANDS =====================
@tree.command(name="servers", description="List servers (Owner only)")
async def servers(interaction: discord.Interaction):
    if not is_owner(interaction):
        return await interaction.response.send_message("❌ Owner only", ephemeral=True)
    await interaction.response.send_message(f"🤖 Bot is in **{len(client.guilds)}** servers.")


@tree.command(name="reload", description="Reload slash commands (Owner only)")
async def reload(interaction: discord.Interaction):
    if not is_owner(interaction):
        return await interaction.response.send_message("❌ Owner only", ephemeral=True)
    await tree.sync()
    await interaction.response.send_message("✅ Commands reloaded!")


# ===================== MENTION RESPONSE =====================
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if client.user in message.mentions:
        responses = ["Yes?", "What's up?", "I'm here!", "Need something?"]
        await message.channel.send(random.choice(responses))


client.run(DISCORD_TOKEN)