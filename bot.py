import discord
import os
import time
import json
import asyncio
import logging
from discord import app_commands
from xai_sdk import Client
from xai_sdk.chat import system, user, assistant

# ===================== CONFIG =====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))

MAX_HISTORY = 12
COOLDOWN_SECONDS = 5
MEMORY_TIMEOUT = 3600
MEMORY_FILE = "conversation_memory.json"

logging.basicConfig(level=logging.INFO)

if not DISCORD_TOKEN or not XAI_API_KEY:
    print("❌ Missing tokens!")
    exit(1)

xai_client = Client(api_key=XAI_API_KEY)
conversation_memory = {}
user_cooldowns = {}

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ===================== MEMORY =====================
def load_memory():
    global conversation_memory
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r') as f:
                conversation_memory = json.load(f)
            print(f"✅ Loaded {len(conversation_memory)} conversations")
    except:
        pass

def save_memory():
    try:
        data = {k: {"last_used": v["last_used"]} for k, v in conversation_memory.items()}
        with open(MEMORY_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass


# ===================== EVENTS =====================
@client.event
async def on_ready():
    await tree.sync()
    load_memory()
    print(f"\n✅ {client.user} is ONLINE!")
    print(f"   Connected to {len(client.guilds)} servers\n")
    
    for guild in client.guilds:
        print(f"   • {guild.name} ({guild.id})")

    await client.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="/ask | /imagine")
    )


def cleanup_memory():
    now = time.time()
    for cid in list(conversation_memory.keys()):
        if now - conversation_memory[cid]["last_used"] > MEMORY_TIMEOUT:
            del conversation_memory[cid]
    save_memory()


# ===================== COMMANDS =====================
@tree.command(name="ask", description="Chat with Grok")
@app_commands.describe(question="Your question")
async def ask(interaction: discord.Interaction, question: str):
    user_id = interaction.user.id
    channel_id = str(interaction.channel_id)
    now = time.time()

    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        await interaction.response.send_message("⏳ Slow down!", ephemeral=True)
        return

    user_cooldowns[user_id] = now
    await interaction.response.defer()

    try:
        cleanup_memory()
        if channel_id not in conversation_memory:
            chat = xai_client.chat.create(model="grok-4")
            chat.append(system("You are Grok, helpful, witty, and truthful."))
            conversation_memory[channel_id] = {"chat": chat, "last_used": now}
        else:
            conversation_memory[channel_id]["last_used"] = now
            chat = conversation_memory[channel_id]["chat"]

        chat.append(user(question))
        response = await chat.sample()
        chat.append(assistant(response.text))

        if len(chat.messages) > MAX_HISTORY * 2:
            chat.messages = chat.messages[-MAX_HISTORY * 2:]

        reply = response.text
        if len(reply) > 1900:
            await interaction.followup.send(reply[:1900])
            await interaction.followup.send(reply[1900:])
        else:
            await interaction.followup.send(reply)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:300]}")


@tree.command(name="imagine", description="Generate images with Grok Imagine")
@app_commands.describe(prompt="Image description", aspect_ratio="Ratio", resolution="Quality", num_images="Count")
@app_commands.choices(
    aspect_ratio=[app_commands.Choice(name=n, value=v) for n, v in [
        ("Square 1:1", "1:1"), ("Widescreen 16:9", "16:9"), ("Vertical 9:16", "9:16"),
        ("Landscape 3:2", "3:2"), ("Portrait 2:3", "2:3")]],
    resolution=[app_commands.Choice(name=n, value=v) for n, v in [("1K", "1k"), ("2K", "2k")]]
)
async def imagine(interaction: discord.Interaction, prompt: str, aspect_ratio: str = "1:1", 
                 resolution: str = "1k", num_images: int = 1):
    user_id = interaction.user.id
    now = time.time()

    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        await interaction.response.send_message("⏳ Wait a bit!", ephemeral=True)
        return

    user_cooldowns[user_id] = now
    await interaction.response.defer()

    try:
        await interaction.followup.send(f"🎨 Generating {num_images} image(s)...")

        response = xai_client.image.sample(
            prompt=prompt,
            model="grok-imagine-image-quality",
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            n=num_images
        )

        for i, img in enumerate(response.images if hasattr(response, 'images') else [response]):
            embed = discord.Embed(title=f"Grok Imagine #{i+1}", description=prompt[:200], color=0x1DA1F2)
            embed.set_image(url=img.url)
            embed.add_field(name="Settings", value=f"{aspect_ratio} | {resolution}", inline=True)
            embed.set_footer(text="xAI Grok Imagine")
            await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {str(e)[:300]}")


@tree.command(name="stats", description="Bot statistics")
async def stats(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot Stats", color=0x1DA1F2)
    embed.add_field(name="Servers", value=len(client.guilds), inline=True)
    embed.add_field(name="Conversations", value=len(conversation_memory), inline=True)
    embed.add_field(name="Memory", value="Persistent", inline=True)
    embed.add_field(name="Uptime", value="Active", inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! `{latency}ms`")


@tree.command(name="clear", description="Clear memory")
async def clear(interaction: discord.Interaction):
    channel_id = str(interaction.channel_id)
    if channel_id in conversation_memory:
        del conversation_memory[channel_id]
        save_memory()
        await interaction.response.send_message("🧹 Memory cleared!", ephemeral=True)
    else:
        await interaction.response.send_message("No memory to clear.", ephemeral=True)


@tree.command(name="help", description="Show commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot", description="Powered by xAI", color=0x1DA1F2)
    embed.add_field(name="/ask", value="Chat with memory", inline=False)
    embed.add_field(name="/imagine", value="Generate images", inline=False)
    embed.add_field(name="/stats", value="Show statistics", inline=False)
    embed.add_field(name="/ping", value="Check latency", inline=False)
    embed.add_field(name="/clear", value="Clear memory", inline=False)
    embed.set_footer(text=f"Active on {len(client.guilds)} servers")
    await interaction.response.send_message(embed=embed)


@tree.command(name="reload", description="Restart bot (Owner only)")
async def reload(interaction: discord.Interaction):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ Owner only", ephemeral=True)
        return
    await interaction.response.send_message("🔄 Restarting...")
    save_memory()
    await asyncio.sleep(2)
    await client.close()


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if client.user.mentioned_in(message):
        await message.channel.send("Hi! Use `/ask` or `/imagine` 😊")


# ===================== START =====================
client.run(DISCORD_TOKEN)