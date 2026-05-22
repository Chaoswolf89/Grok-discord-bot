import discord
import os
import time
import json
from discord import app_commands
from xai_sdk import Client
from xai_sdk.chat import system, user, assistant

# ==================== CONFIGURATION ====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))   # ← Add your Discord User ID in Railway Variables

MAX_HISTORY = 12
COOLDOWN_SECONDS = 5
MEMORY_TIMEOUT = 3600
MEMORY_FILE = "conversation_memory.json"

if not DISCORD_TOKEN or not XAI_API_KEY:
    print("❌ Missing DISCORD_TOKEN or XAI_API_KEY!")
    exit(1)

xai_client = Client(api_key=XAI_API_KEY)

conversation_memory = {}   # channel_id → {"chat": chat_object, "last_used": timestamp}
user_cooldowns = {}

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ===================== PERSISTENT MEMORY =====================
def load_memory():
    global conversation_memory
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r') as f:
                data = json.load(f)
                conversation_memory = data
            print(f"✅ Loaded {len(conversation_memory)} saved conversations")
    except Exception as e:
        print(f"⚠️ Could not load memory: {e}")

def save_memory():
    try:
        save_data = {k: {"last_used": v["last_used"]} for k, v in conversation_memory.items()}
        with open(MEMORY_FILE, 'w') as f:
            json.dump(save_data, f)
    except:
        pass


# ===================== EVENTS =====================
@client.event
async def on_ready():
    await tree.sync()
    load_memory()
    print(f"\n✅ {client.user} is successfully online!")
    print(f"   Connected to {len(client.guilds)} servers:\n")
    
    for guild in client.guilds:
        print(f"   • {guild.name} ({guild.id}) - {guild.member_count} members")

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
@tree.command(name="ask", description="Chat with Grok (with memory)")
@app_commands.describe(question="Your question for Grok")
async def ask(interaction: discord.Interaction, question: str):
    user_id = interaction.user.id
    channel_id = str(interaction.channel_id)
    now = time.time()

    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        await interaction.response.send_message("⏳ Please wait a few seconds.", ephemeral=True)
        return

    user_cooldowns[user_id] = now
    await interaction.response.defer()

    try:
        cleanup_memory()

        if channel_id not in conversation_memory:
            chat = xai_client.chat.create(model="grok-4")
            chat.append(system("You are Grok, a helpful, witty, and truthful AI built by xAI."))
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
        await interaction.followup.send(f"❌ Error: {str(e)[:400]}")


@tree.command(name="imagine", description="Generate images with Grok Imagine")
@app_commands.describe(
    prompt="Describe the image you want",
    aspect_ratio="Aspect ratio",
    resolution="Quality",
    num_images="Number of images (1-4)"
)
@app_commands.choices(
    aspect_ratio=[
        app_commands.Choice(name="Square (1:1)", value="1:1"),
        app_commands.Choice(name="Widescreen (16:9)", value="16:9"),
        app_commands.Choice(name="Vertical (9:16)", value="9:16"),
        app_commands.Choice(name="Landscape (3:2)", value="3:2"),
        app_commands.Choice(name="Portrait (2:3)", value="2:3"),
    ],
    resolution=[
        app_commands.Choice(name="1K Standard", value="1k"),
        app_commands.Choice(name="2K High Quality", value="2k"),
    ]
)
async def imagine(
    interaction: discord.Interaction,
    prompt: str,
    aspect_ratio: str = "1:1",
    resolution: str = "1k",
    num_images: int = 1
):
    user_id = interaction.user.id
    now = time.time()

    if user_id in user_cooldowns and now - user_cooldowns[user_id] < COOLDOWN_SECONDS:
        await interaction.response.send_message("⏳ Please wait before generating more.", ephemeral=True)
        return

    user_cooldowns[user_id] = now
    await interaction.response.defer()

    try:
        await interaction.followup.send(f"🎨 Generating {num_images} image(s)... ({aspect_ratio}, {resolution})")

        response = xai_client.image.sample(
            prompt=prompt,
            model="grok-imagine-image-quality",
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            n=num_images
        )

        for i, img in enumerate(response.images if hasattr(response, 'images') else [response]):
            embed = discord.Embed(
                title=f"Grok Imagine #{i+1}",
                description=prompt[:200] + ("..." if len(prompt) > 200 else ""),
                color=0x1DA1F2
            )
            embed.set_image(url=img.url)
            embed.add_field(name="Settings", value=f"Ratio: {aspect_ratio} | Quality: {resolution}", inline=True)
            embed.set_footer(text="Generated by xAI Grok Imagine")
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Image generation failed: {str(e)[:400]}")


@tree.command(name="stats", description="Show bot statistics")
async def stats(interaction: discord.Interaction):
    embed = discord.Embed(title="Grok Bot Statistics", color=0x1DA1F2)
    embed.add_field(name="Servers", value=str(len(client.guilds)), inline=True)
    embed.add_field(name="Active Conversations", value=str(len(conversation_memory)), inline=True)
    embed.add_field(name="Memory", value="Persistent (Saved)", inline=True)
    embed.add_field(name="Cooldown", value=f"{COOLDOWN_SECONDS}s", inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="clear", description="Clear conversation memory in this channel")
async def clear(interaction: discord.Interaction):
    channel_id = str(interaction.channel_id)
    if channel_id in conversation_memory:
        del conversation_memory[channel_id]
        save_memory()
        await interaction.response.send_message("🧹 Conversation memory cleared!", ephemeral=True)
    else:
        await interaction.response.send_message("No memory to clear.", ephemeral=True)


@tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Grok Bot",
        description="Powered by Grok from xAI",
        color=0x1DA1F2
    )
    embed.add_field(name="/ask [question]", value="Chat with memory", inline=False)
    embed.add_field(name="/imagine [prompt]", value="Advanced image generation", inline=False)
    embed.add_field(name="/stats", value="Show bot statistics", inline=False)
    embed.add_field(name="/clear", value="Clear memory in channel", inline=False)
    embed.add_field(name="/help", value="Show this help", inline=False)
    embed.set_footer(text=f"Running on {len(client.guilds)} servers")
    await interaction.response.send_message(embed=embed)


# Owner Only Commands
@tree.command(name="reload", description="Reload bot (Owner only)")
async def reload(interaction: discord.Interaction):
    if interaction.user.id != BOT_OWNER_ID:
        await interaction.response.send_message("❌ This command is for the bot owner only.", ephemeral=True)
        return
    await interaction.response.send_message("🔄 Saving memory and restarting...")
    save_memory()
    await asyncio.sleep(2)
    await client.close()


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if client.user.mentioned_in(message):
        await message.channel.send("Hey! Use `/ask` or `/imagine` 😊")


# ===================== START BOT =====================
client.run(DISCORD_TOKEN)