import discord
import aiohttp
from dotenv import load_dotenv
import os
from discord.ext import commands
import sqlite3
import datetime

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
admin = os.getenv('BOTADMIN')
reaction_channel = os.getenv('REACTION_CHANNEL')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

db = sqlite3.connect('discordbot.db')

c = db.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    doubloons INTEGER
)
""")
db.commit()
c.close()
emoji_doubloon_map = {
    "☑️": 3,
    "✅": 1,
}

valid_emojis = ["☑️", "✅"]


def check_int(i):
    try:
        int(i)
        return True
    except:
        return False


@bot.event
async def on_raw_reaction_add(payload):
    if payload.channel_id != int(reaction_channel):
        return
    reaction = payload.emoji

    if reaction.name not in valid_emojis:
        with open("error_log.txt", "a") as f:
            print(f"Invalid reaction {reaction.name}", file=f)
        return

    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    user = await bot.fetch_user(payload.user_id)
    with db:
        c = db.cursor()
        c.execute("""
        INSERT OR IGNORE INTO users (id, username, doubloons)
        VALUES (?, ?, ?)
        """, (message.author.id, message.author.name, 0))

        # Update the user's doubloons value in the database
        c.execute("""
        UPDATE users
        SET doubloons = doubloons + ?
        WHERE id = ?
        """, (emoji_doubloon_map[reaction.name], message.author.id))
    c.close()

    with open("point_history.txt", "a") as f:
        print(
            f"{user.name} added {emoji_doubloon_map[reaction.name]} doubloons to {message.author.name} at {datetime.datetime.now()}", file=f)


@bot.event
async def on_raw_reaction_remove(payload):
    if payload.channel_id != int(reaction_channel):
        return
    reaction = payload.emoji

    if reaction.name not in valid_emojis:
        with open("error_log.txt", "a") as f:
            print(f"Invalid reaction {reaction.name}", file=f)
        return

    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    with db:
        c = db.cursor()
        c.execute("SELECT doubloons FROM users WHERE id = ?",
                  (message.author.id,))
        result = c.fetchone()
    c.close()

    if result is None:
        with open("error_log.txt", "a") as f:
            print(
                f"Error: User with ID {message.author.id} does not exist.", file=f)
            admin_user = await bot.fetch_user(int(admin))
            await admin_user.send(f"There was a problem removing doubloons from {message.author.id} {message.author.name}, they do not exist in the DB.")
        return

    current_doubloons = result[0]
    if current_doubloons - emoji_doubloon_map[reaction.name] < 0:
        with open("error_log.txt", "a") as f:
            print(
                f"Error: Decreasing doubloons by {emoji_doubloon_map[reaction.name]} would result in a negative value for user with ID {message.author.id} {message.author.name}.", file=f)
        return

    with db:
        c = db.cursor()
        # Update the user's doubloons value in the database
        c.execute("""
        UPDATE users
        SET doubloons = doubloons - ?
        WHERE id = ?
        """, (emoji_doubloon_map[reaction.name], message.author.id))
    c.close()

    user = await bot.fetch_user(payload.user_id)

    with open("point_history.txt", "a") as f:
        print(
            f"{user.name} removed {emoji_doubloon_map[reaction.name]} doubloons from {message.author.name} at {datetime.datetime.now()}", file=f)


@bot.command(name="adddoubloons")
async def adddoubloons(ctx, *args):
    if ";" in str(args):
        await ctx.send('no sql injection plz ty')
        return

    if len(args) < 1 or args[0] == "help":
        await ctx.send('adddoubloons usage: !adddoubloons [userid] [points]')

    user_id = args[0]
    if user_id[0] == "<":
        user_id = user_id[2:-1]

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send(f'User ID {user_id} does not exist')
        return

    doubloon_count = args[1]

    if not check_int(doubloon_count):
        await ctx.send(f'{doubloon_count} is not a valid number of doubloons!')
        return

    with db:
        c = db.cursor()
        c.execute("""
        INSERT OR IGNORE INTO users (id, username, doubloons)
        VALUES (?, ?, ?)
        """, (user_id, user.name, 0))

        # Update the user's doubloons value in the database
        c.execute("""
        UPDATE users
        SET doubloons = doubloons + ?
        WHERE id = ?
        """, (doubloon_count, user_id))

        c.execute("SELECT doubloons FROM users WHERE id = ?",
                  (user_id,))
        result = c.fetchone()
    c.close()

    with open("point_history.txt", "a") as f:
        print(
            f"{ctx.author.name} added {doubloon_count} doubloons to {user.name} at {datetime.datetime.now()}", file=f)

    await ctx.send(f'{doubloon_count} added to {user.name}! They now have {result[0]} doubloon(s)!')

    return


@bot.command(name="removedoubloons")
async def removedoubloons(ctx, *args):
    if ";" in str(args):
        await ctx.send('no sql injection plz ty')
        return

    if len(args) < 1 or args[0] == "help":
        await ctx.send('removedoubloons usage: !removedoubloons [userid] [points]')

    user_id = args[0]
    if user_id[0] == "<":
        user_id = user_id[2:-1]

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send(f'User ID {user_id} does not exist')
        return

    doubloon_count = args[1]

    if not check_int(doubloon_count):
        await ctx.send(f'{doubloon_count} is not a valid number of doubloons!')
        return

    with db:
        c = db.cursor()
        c.execute("SELECT doubloons FROM users WHERE id = ?",
                  (user_id,))
        result = c.fetchone()
    c.close()

    if result is None:
        await ctx.send(f'{user.name} doesn\'t have any doubloonds yet!')
        return

    current_doubloons = result[0]
    if current_doubloons - int(doubloon_count) < 0:
        await ctx.send(f'{user.name} only has {current_doubloons} doubloon(s)! You can remove them all by using the exact number.')
        return

    with db:
        c = db.cursor()
        # Update the user's doubloons value in the database
        c.execute("""
        UPDATE users
        SET doubloons = doubloons - ?
        WHERE id = ?
        """, (doubloon_count, user_id))
    c.close()

    with open("point_history.txt", "a") as f:
        print(
            f"{ctx.author.name} removed {doubloon_count} doubloons from {user.name} at {datetime.datetime.now()}", file=f)
    await ctx.send(f'{doubloon_count} doubloons removed from {user.name}, they now have {current_doubloons - int(doubloon_count)} doubloon(s)!')

    return


@bot.command(name="register")
async def register(ctx, *args):
    if ";" in str(args):
        await ctx.send('no sql injection plz ty')
        return

    if len(args) < 1 or args[0] == "help":
        await ctx.send('register usage: !register [userid] [user name]')

    user_id = args[0]
    if user_id[0] == "<":
        user_id = user_id[2:-1]

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send(f'User ID {user_id} does not exist')
        return

    username = ' '.join(args[1:]).strip()
    print(username)

    with db:
        c = db.cursor()
        c.execute("""
        INSERT OR IGNORE INTO users (id, username, doubloons)
        VALUES (?, ?, ?)
        """, (user_id, username, 0))

        # Update the user's doubloons value in the database
        c.execute("""
        UPDATE users
        SET username = ?
        WHERE id = ?
        """, (username, user_id))
    c.close()

    await ctx.send(f'Updated {user_id}\'s username to {username}')


@bot.command(name="leaderboard")
async def leaderboard(ctx):
    with db:
        c = db.cursor()
        c.execute("SELECT id, username, doubloons FROM users")
        users = c.fetchall()
        sorted_users = sorted(users, key=lambda user: user[2], reverse=True)
    c.close()

    leaderboard = "Leaderboard:\n"
    for i, user in enumerate(sorted_users, start=1):
        leaderboard += f"{i}. {user[1]} - {user[2]} doubloons\n"

    await ctx.send(leaderboard)


@bot.command(name="test")
async def test(ctx, *args):
    if str(ctx.author.id) != str(admin):
        return

    user_id = args[0]
    if user_id[0] == "<":
        user_id = user_id[2:-1]

    print(f'{user_id}')
    try:
        user = await bot.fetch_user(user_id)
    except:
        print(f'User ID {user_id} does not exist')
        return
    print(f'{user.name}')


@bot.event
async def on_ready():
    print(f'{bot.user.display_name} is online')

try:
    bot.run(token)
finally:
    db.close()
    print("DB closed")
