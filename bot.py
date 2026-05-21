import os
import discord
from discord import app_commands
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
XAI_API_KEY = os.getenv("XAI_API_KEY")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

grok = OpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1",
)

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")

@tree.command(name="ask", description="Ask Grok anything")
async def ask(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()
    try:
        response = grok.chat.completions.create(
            model="grok-4.3",
            messages=[
                {"role": "system", "content": "You are Grok, a helpful and maximally truthful AI built by xAI."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=1200,
        )
        reply = response.choices[0].message.content
        await interaction.followup.send(reply)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

client.run(DISCORD_TOKEN)
