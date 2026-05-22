import os
import discord
from discord import app_commands
from dotenv import load_dotenv
from openai import OpenAI
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")

# Debug key loading
logger.info(f"DISCORD_TOKEN loaded: {'Yes' if DISCORD_TOKEN else 'No'}")
logger.info(f"XAI_API_KEY loaded: {'Yes' if XAI_API_KEY else 'No'}")
if XAI_API_KEY:
    logger.info(f"XAI key preview: {XAI_API_KEY[:15]}...")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

grok = OpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1",
)

# Simple conversation memory (per channel)
conversation_history = defaultdict(list)

@client.event
async def on_ready():
    await tree.sync()
    logger.info(f"✅ Bot is online as {client.user}")
    logger.info(f"✅ Connected to {len(client.guilds)} server(s)")

@tree.command(name="ask", description="Ask Grok anything (remembers conversation in thread)")
async def ask(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    
    channel_id = str(interaction.channel_id)
    
    try:
        # Add user message to history
        conversation_history[channel_id].append({"role": "user", "content": prompt})
        
        # Keep only last 10 messages
        if len(conversation_history[channel_id]) > 20:
            conversation_history[channel_id] = conversation_history[channel_id][-20:]

        logger.info(f"📨 Query from {interaction.user} in channel {channel_id}")

        response = grok.chat.completions.create(
            model="grok-4.3",
            messages=[
                {"role": "system", "content": "You are Grok, a helpful and maximally truthful AI built by xAI."}
            ] + conversation_history[channel_id],
            temperature=0.85,
            max_tokens=1500,
        )
        
        reply = response.choices[0].message.content
        
        # Add assistant reply to history
        conversation_history[channel_id].append({"role": "assistant", "content": reply})
        
        await interaction.followup.send(reply[:2000])
        logger.info("✅ Response sent successfully")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await interaction.followup.send(f"❌ Error: {str(e)}")

@tree.command(name="clear", description="Clear conversation history for this channel")
async def clear(interaction: discord.Interaction):
    channel_id = str(interaction.channel_id)
    conversation_history[channel_id] = []
    await interaction.response.send_message("🧹 Conversation history cleared for this channel.", ephemeral=True)

if __name__ == "__main__":
    if DISCORD_TOKEN:
        client.run(DISCORD_TOKEN)
    else:
        logger.error("❌ DISCORD_TOKEN is missing! Cannot start bot.")
