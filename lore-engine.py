import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions

# clean up Hugging Face warning spam in terminal
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# load discord bot token from env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# initialise chromadb
chroma_client = chromadb.PersistentClient(path="./library_db")
default_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
collection = chroma_client.get_or_create_collection(
    name="server_quotes",
    embedding_function=default_ef
)

# bot permissions
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True # CRITICAL: Allows the bot to see emoji reactions
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Hollo why am i doing this {bot.user.name}')
    print("chromadb library loaded")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} app command(s) successfully!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


# 1. archive background
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.content.startswith('!') or message.content.startswith('/'):
        await bot.process_commands(message) 
        return
    if not message.content.strip():
        return

    try:
        collection.add(
            documents=[message.content],
            metadatas=[{
                "messager_id": str(message.author.id),
                "messager_name": message.author.display_name,
                "recorded_by": "System Auto-Log",
                "channel": message.channel.name,
                "is_special": "False"
            }],
            ids=[f"auto_{message.id}"]
        )
    except Exception as e:
        print(f"Error auto-logging message: {e}")

    await bot.process_commands(message)


# 2. emoji reaction save system
@bot.event
async def on_raw_reaction_add(payload):
    # change emoji to whatever for trigger
    TARGET_EMOJI = "🔖" 
    
    if str(payload.emoji) == TARGET_EMOJI:
        # fetch channel and message objects from the event payload
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            channel = await bot.fetch_channel(payload.channel_id)
            
        message = await channel.fetch_message(payload.message_id)
        
        # don't save if message is blank (embeds/images)
        if not message.content or not message.content.strip():
            return
            
        # get person who reacted
        server = bot.get_guild(payload.guild_id)
        reacter = await server.fetch_member(payload.user_id)
        
        # ignore if bot reacts to itself
        if reacter == bot.user:
            return

        quote_id = f"special_{message.id}"
        
        try:
            collection.add(
                documents=[message.content],
                metadatas=[{
                    "messager_id": str(message.author.id),
                    "messager_name": message.author.display_name,
                    "recorded_by": reacter.display_name,
                    "channel": channel.name,
                    "is_special": "True"
                }],
                ids=[quote_id]
            )
            # send quick confirmation message to the channel
            await channel.send(f"🔖 *The Librarian saw your bookmark!* Saved quote from **{message.author.display_name}**.")
        except Exception as e:
            print(f"Failed to archive via reaction: {e}")


# 3. /ping command
@bot.tree.command(name="ping", description="Check if the librarian is awake")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('AHHHH IM HERE LA SHUT IT')


# 4. /lookup command
@bot.tree.command(name="lookup", description="Search the archive logs")
@app_commands.describe(search_query="What do you want to find?")
async def lookup(interaction: discord.Interaction, search_query: str):
    await interaction.response.defer()

    results = collection.query(
        query_texts=[search_query],
        n_results=1
    )

    if results['documents'] and results['documents'][0]:
        best_quote = results['documents'][0][0]
        metadata = results['metadatas'][0][0]

        if metadata.get('is_special') == "True":
            response = f" **[Special quote]**\n"
        else:
            response = f" *[Daily quote]*\n "
        
        response += f'"{best_quote}" \n'
        response += f"- **{metadata['messager_name']}** (Logged via {metadata['recorded_by']} in #{metadata['channel']})"
        
        await interaction.followup.send(response)
    else:
        await interaction.followup.send("tak ada la u sendiri cari la")

# start the bot
bot.run(TOKEN)