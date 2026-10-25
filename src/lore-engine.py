import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions
import sqlite3
import re
from datetime import datetime, timedelta


# clean up Hugging Face warning spam in terminal
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


# load discord bot token & channel id from env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

channel_id_str = os.getenv('LEADERBOARD_CHANNEL_ID')
LEADERBOARD_CHANNEL_ID = int(channel_id_str) if channel_id_str else 0



# initialise chromadb
chroma_client = chromadb.PersistentClient(path="./library_db")
default_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
collection = chroma_client.get_or_create_collection(
    name="server_quotes",
    embedding_function=default_ef
)


# initialise sqlite for vote
conn = sqlite3.connect("vote.db")
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS quote_stats (
                    quote_id TEXT PRIMARY KEY,
                    upvotes INTEGER DEFAULT 0,
                    downvotes INTEGER DEFAULT 0)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS user_votes (
                    quote_id TEXT,
                    user_id TEXT,
                    last_vote_date TEXT,
                    PRIMARY KEY (quote_id, user_id))''')

# invis map bot msg to quote
cursor.execute('''CREATE TABLE IF NOT EXISTS lookup_messages (
                    message_id TEXT PRIMARY KEY,
                    quote_id TEXT)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS bot_settings (
                    setting_name TEXT PRIMARY KEY,
                    setting_value TEXT)''')

# upgtade old database to support changing votes
cursor.execute("PRAGMA table_info(user_votes)")
columns = [col[1] for col in cursor.fetchall()]
if "vote_type" not in columns:
    cursor.execute("ALTER TABLE user_votes ADD COLUMN vote_type TEXT DEFAULT 'SKIP'")
conn.commit()

# bot permissions
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True 
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

    if not leaderboard_loop.is_running():
        leaderboard_loop.start()

# helper function for leaderboard
def get_leaderboard_text(time_pattern, limit, title):
    cursor.execute('''
        SELECT quote_id, 
               SUM(CASE WHEN vote_type = 'UP' THEN 1 ELSE 0 END) - 
               SUM(CASE WHEN vote_type = 'DOWN' THEN 1 ELSE 0 END) as score
        FROM user_votes 
        WHERE last_vote_date LIKE ? 
        GROUP BY quote_id 
        HAVING score > 0
        ORDER BY score DESC 
        LIMIT ?
    ''', (time_pattern, limit))
    results = cursor.fetchall()
    
    if not results:
        return f"*No positive votes cast yet for {title}!*\n"
        
    text = ""
    for i, (q_id, score) in enumerate(results):
        # force qid to be a str
        c_result = collection.get(ids=[str(q_id)])
        
        if c_result and c_result.get('documents') and len(c_result['documents']) > 0:
            quote_text = c_result['documents'][0]
            if len(quote_text) > 100:
                quote_text = quote_text[:97] + "..."
                
            metadata = c_result['metadatas'][0] if c_result.get('metadatas') and len(c_result['metadatas']) > 0 else {}
            author = metadata.get('messager_name', 'Unknown User')
            
            text += f"**{i+1}.** \"{quote_text}\" - **{author}** ({score} pts)\n"
            
    if text == "":
        return f"*No positive votes cast yet for {title}!*\n"
        
    return text


# 1a. automated leaderbaord background
@tasks.loop(hours=1)
async def leaderboard_loop():
    await bot.wait_until_ready()
    
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel:
        return
        
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    
    if tomorrow.month != now.month and now.hour == 23:
        current_month_str = now.strftime("%Y-%m")
        cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name='last_monthly_sent'")
        row = cursor.fetchone()
        
        if not row or row[0] != current_month_str:
            monthly_text = get_leaderboard_text(f"{current_month_str}-%", 5, "this month")
            
            response = f"🏆 **Top 5 Quotes of {now.strftime('%B %Y')}** 🏆\n\n{monthly_text}"
            await channel.send(response)
            
            cursor.execute("INSERT OR REPLACE INTO bot_settings (setting_name, setting_value) VALUES ('last_monthly_sent', ?)", (current_month_str,))
            conn.commit()
            
        if tomorrow.year != now.year:
            current_year_str = now.strftime("%Y")
            cursor.execute("SELECT setting_value FROM bot_settings WHERE setting_name='last_yearly_sent'")
            row = cursor.fetchone()
            
            if not row or row[0] != current_year_str:
                yearly_text = get_leaderboard_text(f"{current_year_str}-%", 3, "this year")
                
                response = f"👑 **BEST QUOTES OF {current_year_str}** 👑\n\n{yearly_text}"
                await channel.send(response)
                
                cursor.execute("INSERT OR REPLACE INTO bot_settings (setting_name, setting_value) VALUES ('last_yearly_sent', ?)", (current_year_str,))
                conn.commit()



# 1b. archive background
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
            ids=[str(message.id)]
        )
    except Exception as e:
        print(f"Error auto-logging message: {e}")

    await bot.process_commands(message)


# 2. emoji save and reaction save system
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    # change emoji to whatever for trigger
    TARGET_EMOJI = "🔖" 
    UPVOTE = "⬆️"
    DOWNVOTE = "⬇️"
    SKIP = "❌"

    if str(payload.emoji) not in [TARGET_EMOJI, UPVOTE, DOWNVOTE, SKIP]:
        return

    channel = bot.get_channel(payload.channel_id)
    if not channel:
        channel = await bot.fetch_channel(payload.channel_id)

    message = await channel.fetch_message(payload.message_id)
    server = bot.get_guild(payload.guild_id)
    reacter = await server.fetch_member(payload.user_id)

    # bookmark
    if str(payload.emoji) == TARGET_EMOJI:
        if not message.content or not message.content.strip():
            return

        quote_id = str(message.id)
        try:
            collection.upsert(
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

            await channel.send(f" Okok got u, bookmark liao. *Saved quote from **{message.author.display_name}**.")
        except Exception as e:
            print(f"Failed to archive via reaction: {e}")

    # voting system
    if str(payload.emoji) in [UPVOTE, DOWNVOTE, SKIP]:
        if message.author != bot.user:
            return

        # fetch quote_id from database using msg id
        cursor.execute("SELECT quote_id FROM lookup_messages WHERE message_id=?", (str(payload.message_id),))
        lookup_row = cursor.fetchone()

        if not lookup_row:
            return

        quote_id = lookup_row[0]
        today = datetime.now().strftime("%Y-%m-%d")
        user_id = str(reacter.id)


        # determine what button pressed
        if str(payload.emoji) == UPVOTE:
            new_vote = 'UP'
        elif str(payload.emoji) == DOWNVOTE:
            new_vote = 'DOWN'
        else:
            new_vote = 'SKIP'

        cursor.execute("SELECT last_vote_date, vote_type FROM user_votes WHERE quote_id=? AND user_id=?", (quote_id, user_id))
        row = cursor.fetchone()

        if row and row[0] == today:
            old_vote = row[1]

            if old_vote == new_vote:
            # alr interacted tdy
                try:
                    await message.remove_reaction(payload.emoji, reacter)
                    await channel.send(f"Already voted or skip la u want be najib meh?", delete_after=8.0)
                except discord.Forbidden:
                    pass
                return
            else:
                # changed vote
                if old_vote == 'UP':
                    cursor.execute("UPDATE quote_stats SET upvotes = upvotes - 1 WHERE quote_id=?", (quote_id,))
                elif old_vote == 'DOWN':
                    cursor.execute("UPDATE quote_stats SET downvotes = downvotes - 1 WHERE quote_id=?", (quote_id,))
                    
                if new_vote == 'UP':
                    cursor.execute("UPDATE quote_stats SET upvotes = upvotes + 1 WHERE quote_id=?", (quote_id,))
                elif new_vote == 'DOWN':
                    cursor.execute("UPDATE quote_stats SET downvotes = downvotes + 1 WHERE quote_id=?", (quote_id,))
                    
                cursor.execute("UPDATE user_votes SET vote_type=? WHERE quote_id=? AND user_id=?", (new_vote, quote_id, user_id))
                conn.commit()
                action_reply = f"Changed vote to {payload.emoji}!"
        else:
            # first vote today
            if new_vote == 'UP':
                cursor.execute("""
                    INSERT INTO quote_stats (quote_id, upvotes, downvotes) VALUES (?, 1, 0)
                    ON CONFLICT(quote_id) DO UPDATE SET upvotes = upvotes + 1
                """, (quote_id,))
            elif new_vote == 'DOWN':
                cursor.execute("""
                    INSERT INTO quote_stats (quote_id, upvotes, downvotes) VALUES (?, 0, 1)
                    ON CONFLICT(quote_id) DO UPDATE SET downvotes = downvotes + 1
                """, (quote_id,))
                
            cursor.execute("""
                INSERT INTO user_votes (quote_id, user_id, last_vote_date, vote_type) VALUES (?, ?, ?, ?)
                ON CONFLICT(quote_id, user_id) DO UPDATE SET last_vote_date = ?, vote_type = ?
            """, (quote_id, user_id, today, new_vote, today, new_vote))
            conn.commit()
            action_reply = f"Voted {payload.emoji}!"

        # remove reaction asap
        try:
            await message.remove_reaction(payload.emoji, reacter)
        except discord.Forbidden:
            pass

        # fetch updated total n edit message
        cursor.execute("SELECT upvotes, downvotes FROM quote_stats WHERE quote_id=?", (quote_id,))
        new_stats = cursor.fetchone()

        if new_stats:
            # replace votes with regex
            new_content = re.sub(
                r'📊 \*\*Votes:\*\* ⬆️ \d+ \| ⬇️ \d+',
                f'📊 **Votes:** ⬆️ {new_stats[0]} | ⬇️ {new_stats[1]}',
                message.content
            )
            await message.edit(content=new_content)

        try:
            await channel.send(f"✅ {reacter.mention} {action_reply}", delete_after=5.0)
        except:
            pass



# 3. /ping command
@bot.tree.command(name="ping", description="Check if the librarian is awake")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('AHHHH IM HERE LA SHUT IT')


# 4. /lookup command
@bot.tree.command(name="lookup", description="Search the archive logs")
@app_commands.describe(
    search_query="What do you want to find?",
    is_special="True for special quotes, False for auto-log, empty for both",
    by_user="Search for quotes by user, blank for anyone"
)

async def lookup(
    interaction: discord.Interaction,
    search_query: str,
    is_special: bool = None,
    by_user: discord.User = None
    ):

    await interaction.response.defer()

    # lookup [] filter
    where_conditions = []

    if is_special is not None:
        where_conditions.append({"is_special": "True" if is_special else "False"})

    if by_user is not None:
        # match discord id
        where_conditions.append({"messager_id": str(by_user.id)})

    # chromaDB formatting for multiple filter
    where_clause = None
    if len(where_conditions) == 1:
        where_clause = where_conditions[0]
    elif len(where_conditions) > 1:
        where_clause = {"$and": where_conditions}

    # search parameter setup
    query_kwargs = {
        "query_texts": [search_query],
        "n_results": 1
    }

    # apply filter only if filled
    if where_clause:
        query_kwargs["where"] = where_clause

    # search database
    try:
        results = collection.query(**query_kwargs)

        if results['documents'] and results['documents'][0]:
            best_quote = results["documents"][0][0]
            # in case metadata empty
            metadata = results['metadatas'][0][0] if results['metadatas'] and results['metadatas'][0] else {}
            quote_id = results['ids'][0][0]

            # fetch data n prevent keylog on old metadata
            author_name = metadata.get('messager_name', 'Unknown User')
            recorded_by = metadata.get('recorded_by', 'System Auto-Log')
            channel_name = metadata.get('channel', 'unknown-channel')

            cursor.execute("SELECT upvotes, downvotes FROM quote_stats WHERE quote_id=?", (quote_id,))
            row = cursor.fetchone()
            upvotes, downvotes = row if row else (0, 0)

            response = f'"{best_quote}" \n'
            response += f"- **{author_name}** (Logged via {recorded_by} in #{channel_name})"
            # zero space link to hide ID
            response += f"📊 **Votes:** ⬆️ {upvotes} | ⬇️ {downvotes}"

            msg = await interaction.followup.send(response, wait=True)

            cursor.execute("INSERT OR REPLACE INTO lookup_messages (message_id, quote_id) VALUES (?, ?)", (str(msg.id), quote_id))
            conn.commit()

            await msg.add_reaction("⬆️")
            await msg.add_reaction("⬇️")
            await msg.add_reaction("❌")
        else:
            await interaction.followup.send("tak ada la u sendiri cari la")

    except Exception as e:
        print(f"Lookup error: {e}")
        await interaction.followup.send("❌ Something went wrong while searching the library.")




# 5. ...>app>save quote
@bot.tree.context_menu(name="Save Quote")
async def save_quote_context(interaction: discord.Interaction, message: discord.Message):
    if not message.content.strip():
        await interaction.response.send_message("❌ Blind is it tryna save empty message do wat?", ephemeral= True)
        return

    quote_id= str(message.id)

    try: 
        collection.upsert(
            documents=[message.content],
            metadatas=[{
                "messager_id": str(message.author.id),
                "messager_name": message.author.display_name,
                "recorded_by": interaction.user.display_name,
                "channel": interaction.channel.name if interaction.channel else "DM",
                "is_special": "True"
            }],
            ids= [quote_id]
        )
        await interaction.response.send_message(f"KK tunggu saya tulis quote ni from **{message.author.display_name}***.")
    except Exception as e:
        print(f"fail to save via context menu: {e}")
        await interaction.response.send_message("❌ gg cant save quote idk why", ephemeral= True)


# 6. !save
@bot.command(name="save")
async def save_prefix(ctx):
    # check if user reply
    if not ctx.message.reference:
        await ctx.send("❌ Reply a message with '!save' la be hiao sio?")
        return

    try:
        # fetch message replied to
        message= await ctx.channel.fetch_message(ctx.message.reference.message_id)
        
        if not message.content.strip():
            await ctx.send("❌Blind is it replying to empty message?")
            return
    
        quote_id= str(message.id)
    
        collection.upsert(
            documents=[message.content],
            metadatas=[{
                "messager_id": str(message.author.id),
                "messager_name": message.author.display_name,
                "recorded_by": ctx.author.display_name,
                "channel": ctx.channel.name,
                "is_special": "True"
            }],
            ids=[quote_id]
        )
        
        await ctx.send(f"🔖 *Archived succesfully* Saved quote from **{message.author.display_name}**.")
    except Exception as e:
        print(f"Failed to save via !save:{e}")
        await ctx.send("❌ Failed to archive the quote.")



# 7. /leaderboard
@bot.tree.command(name="leaderboard", description="Show the best quotes of the month and year!")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        now = datetime.now()
        current_month = now.strftime("%Y-%m")
        current_year = now.strftime("%Y")
        
        monthly_text = get_leaderboard_text(f"{current_month}-%", 5, "this month")
        yearly_text = get_leaderboard_text(f"{current_year}-%", 3, "this year")
        
        response = "🏆 **THE LIBRARIAN'S LEADERBOARD** 🏆\n\n"
        response += f"📅 **Monthly Top 5 ({now.strftime('%B')})**\n{monthly_text}\n"
        response += f"👑 **Yearly Top 3 ({now.strftime('%Y')})**\n{yearly_text}"
        
        await interaction.followup.send(response)
    except Exception as e:
        print(f"Leaderboard crash: {e}")
        await interaction.followup.send(f"❌ leaderboard crashed! Check bot terminal: `{e}`")

# start the bot
bot.run(TOKEN)