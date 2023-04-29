import discord
from dotenv import load_dotenv
import os
from discord.ext import commands, tasks
import sqlite3
from datetime import datetime, timezone, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import subprocess

### Helper functions ###
def get_env_value(key):
    value = os.getenv(key)

    assert value is not None

    return value

async def admin_message(message):
    if admin_user is not None:
        await admin_user.send(message)

def check_int(i):
    try:
        int(i)
        return True
    except:
        return False

def get_int(i, x=0):
    try:
        num = int(i)
        return num
    except:
        return x


def command_history(command):
    with open("command_history.txt", "a") as f:
        print(f"{datetime.now():%Y-%m-%d %I:%M%p} - {command}", file=f)


def log_error(error):
    with open("log_error.txt", "a") as f:
        print(f"{datetime.now():%Y-%m-%d %I:%M%p} - {error}", file=f)


def point_history(points):
    with open("point_history.txt", "a") as f:
        print(f"{datetime.now():%Y-%m-%d %I:%M%p} - {points}", file=f)


### END ###

### Initializing constants

# Google sheets config
scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

credentials = ServiceAccountCredentials.from_json_keyfile_name(
    "google_sheet.json", scopes # type: ignore this function accepts arrays...
) 

file = gspread.authorize(credentials)
# END Google sheets config

# Load environment variables
load_dotenv()
token = get_env_value("DISCORD_TOKEN")
admin = get_env_value("BOTADMIN")
reaction_channel = get_env_value("REACTION_CHANNEL")
spreadsheet_link = get_env_value("SPREADSHEET_LINK")
admins = get_env_value("DISCORD_ADMINS")
debug_channel = get_env_value("DEBUG_CHANNEL")
db_path = get_env_value("DB_PATH")
# END Load environment variables

# Bot config
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
# END Bot config

# Database config
db = sqlite3.connect(db_path)

c = db.cursor()
c.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    doubloons INTEGER
)
"""
)
db.commit()
c.close()
# END Database config

# Constants
adminsarray = admins.split()

emoji_doubloon_map = {
    "☑️": 3,
    "✅": 1,
}

valid_emojis = ["☑️", "✅"]

lock = asyncio.Lock()
# END Constants
### END Initializing constants

### Bot events

@bot.event
async def on_ready():
    assert bot.user is not None

    global admin_user
    admin_user = await bot.fetch_user(int(admin))
    print(f"{bot.user.display_name} is online")
    updateleaderboard_task.start()

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.channel_id) != reaction_channel:
        return

    reaction = payload.emoji

    command_history(f"{payload.user_id} added {reaction.name} to {payload.message_id}")

    if reaction.name not in valid_emojis:
        return

    channel = bot.get_channel(payload.channel_id)

    if channel is None or type(channel) is not discord.TextChannel:
        log_error(f"{payload.channel_id} is not a text channel")
        await admin_message(f"Error: Getting reaction channel {reaction_channel} resulted in non TextChannel")
        return

    message = await channel.fetch_message(payload.message_id)

    user = await bot.fetch_user(payload.user_id)
    with db:
        c = db.cursor()
        c.execute(
            """
        INSERT OR IGNORE INTO users (id, username, doubloons)
        VALUES (?, ?, ?)
        """,
            (message.author.id, message.author.name, 0),
        )

        # Update the user's doubloons value in the database
        c.execute(
            """
        UPDATE users
        SET doubloons = doubloons + ?
        WHERE id = ?
        """,
            (emoji_doubloon_map[reaction.name], message.author.id),
        )
    c.close()

    point_history(f"{user.name} added {emoji_doubloon_map[reaction.name]} doubloons to {message.author.name}")


@bot.event
async def on_raw_reaction_remove(payload):
    if str(payload.channel_id) != reaction_channel:
        return

    reaction = payload.emoji

    command_history(
        f"{payload.user_id} removed {reaction.name} from {payload.message_id}"
    )

    if reaction.name not in valid_emojis:
        log_error(f"Invalid reaction {reaction.name}")
        return

    channel = bot.get_channel(payload.channel_id)

    if channel is None or type(channel) is not discord.TextChannel:
        log_error(f"{payload.channel_id} is not a text channel")
        await admin_message(f"Error: Getting reaction channel {reaction_channel} resulted in non TextChannel")
        return

    message = await channel.fetch_message(payload.message_id)

    with db:
        c = db.cursor()
        c.execute("SELECT doubloons FROM users WHERE id = ?", (message.author.id,))
        result = c.fetchone()
    c.close()

    if result is None:
        log_error(f"Error: User with ID {message.author.id} does not exist.")
        await admin_message(f"There was a problem removing doubloons from {message.author.id} {message.author.name}, they do not exist in the DB.")
        return

    current_doubloons = result[0]
    if current_doubloons - emoji_doubloon_map[reaction.name] < 0:
        log_error(f"Error: Decreasing doubloons by {emoji_doubloon_map[reaction.name]} would result in a negative value for user with ID {message.author.id} {message.author.name}.",)
        return

    with db:
        c = db.cursor()
        # Update the user's doubloons value in the database
        c.execute(
            """
        UPDATE users
        SET doubloons = doubloons - ?
        WHERE id = ?
        """,
            (emoji_doubloon_map[reaction.name], message.author.id),
        )
    c.close()

    user = await bot.fetch_user(payload.user_id)

    point_history(f"{user.name} removed {emoji_doubloon_map[reaction.name]} doubloons from {message.author.name}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        command_history(f"{ctx.author.id} tried updating the leaderboard too fast")
        await ctx.send(
            f"Updating sheet too often, try again in {round(error.retry_after)} seconds"
        )


### END Bot events

### Admin commands
@bot.command(name="adddoubloons")
async def adddoubloons(ctx, *args):
    command_history(f"{ctx.author.id} used adddoubloons with arguments {args}")

    if str(ctx.author.id) not in adminsarray:
        return

    if ";" in str(args):
        await ctx.send("no sql injection plz ty")
        return

    if len(args) < 1 or args[0] == "help":
        await ctx.send("adddoubloons usage: !adddoubloons [userid] [points]")

    user_id = args[0]
    if user_id[0] == "<":
        user_id = user_id[2:-1]

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send(f"User ID {user_id} does not exist")
        return

    doubloon_count = args[1]

    if not check_int(doubloon_count):
        await ctx.send(f"{doubloon_count} is not a valid number of doubloons!")
        return

    with db:
        c = db.cursor()
        c.execute(
            """
        INSERT OR IGNORE INTO users (id, username, doubloons)
        VALUES (?, ?, ?)
        """,
            (user_id, user.name, 0),
        )

        # Update the user's doubloons value in the database
        c.execute(
            """
        UPDATE users
        SET doubloons = doubloons + ?
        WHERE id = ?
        """,
            (doubloon_count, user_id),
        )

        c.execute("SELECT doubloons FROM users WHERE id = ?", (user_id,))
        result = c.fetchone()
    c.close()

    point_history(
            f"{ctx.author.name} manually added {doubloon_count} doubloons to {user.name}")

    await ctx.send(
        f"{doubloon_count} added to {user.name}! They now have {result[0]} doubloon(s)!"
    )

    return


@bot.command(name="removedoubloons")
async def removedoubloons(ctx, *args):
    command_history(f"{ctx.author.id} used removedoubloons with arguments {args}")

    if str(ctx.author.id) not in adminsarray:
        return

    if ";" in str(args):
        await ctx.send("no sql injection plz ty")
        return

    if len(args) < 1 or args[0] == "help":
        await ctx.send("removedoubloons usage: !removedoubloons [userid] [points]")

    user_id = args[0]
    if user_id[0] == "<":
        user_id = user_id[2:-1]

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send(f"User ID {user_id} does not exist")
        return

    doubloon_count = args[1]

    if not check_int(doubloon_count):
        await ctx.send(f"{doubloon_count} is not a valid number of doubloons!")
        return

    with db:
        c = db.cursor()
        c.execute("SELECT doubloons FROM users WHERE id = ?", (user_id,))
        result = c.fetchone()
    c.close()

    if result is None:
        await ctx.send(f"{user.name} doesn't have any doubloonds yet!")
        return

    current_doubloons = result[0]
    if current_doubloons - int(doubloon_count) < 0:
        await ctx.send(
            f"{user.name} only has {current_doubloons} doubloon(s)! You can remove them all by using the exact number."
        )
        return

    with db:
        c = db.cursor()
        # Update the user's doubloons value in the database
        c.execute(
            """
        UPDATE users
        SET doubloons = doubloons - ?
        WHERE id = ?
        """,
            (doubloon_count, user_id),
        )
    c.close()

    point_history(f"{ctx.author.name} manually removed {doubloon_count} doubloons from {user.name}")
    await ctx.send(
        f"{doubloon_count} doubloons removed from {user.name}, they now have {current_doubloons - int(doubloon_count)} doubloon(s)!"
    )

    return


@bot.command(name="register")
async def register(ctx, *args):
    command_history(f"{ctx.author.id} used register with arguments {args}")

    if str(ctx.author.id) not in adminsarray:
        return

    if ";" in str(args):
        await ctx.send("no sql injection plz ty")
        return

    if len(args) < 1 or args[0] == "help":
        await ctx.send("register usage: !register [userid] [user name]")

    user_id = args[0]
    if user_id[0] == "<":
        user_id = user_id[2:-1]

    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await ctx.send(f"User ID {user_id} does not exist")
        return

    username = " ".join(args[1:]).strip()
    print(username)

    with db:
        c = db.cursor()
        c.execute(
            """
        INSERT OR IGNORE INTO users (id, username, doubloons)
        VALUES (?, ?, ?)
        """,
            (user_id, username, 0),
        )

        # Update the user's doubloons value in the database
        c.execute(
            """
        UPDATE users
        SET username = ?
        WHERE id = ?
        """,
            (username, user_id),
        )
    c.close()

    await ctx.send(f"Updated {user_id}'s username to {username}")

### END Admin commands

### User commands

@bot.command(name="doubloons")
async def doubloons(ctx):
    command_history(f"{ctx.author.id} checked their doubloon count")
    with db:
        c = db.cursor()
        c.execute("SELECT doubloons FROM users WHERE id = ?", (str(ctx.author.id),))
        result = c.fetchone()
    c.close()

    if result is None:
        await ctx.send("You don't have any doubloonds yet!")
        return

    await ctx.send(f"You have {result[0]} doubloons!")


@bot.command(name="leaderboard")
async def leaderboard(ctx):
    command_history(f"{ctx.author.id} viewed the leaderboard")
    with db:
        c = db.cursor()
        c.execute("SELECT id, username, doubloons FROM users")
        users = c.fetchall()
        sorted_users = sorted(users, key=lambda user: user[2], reverse=True)
    c.close()

    leaderboard = "Leaderboard TOP 10:\n"
    for i, user in enumerate(sorted_users[:10], start=1):
        leaderboard += f"{i}. {user[1]} - {user[2]} doubloons\n"

    leaderboard += f"\n See the full board here: <{spreadsheet_link}>\nand update it with !updateleaderboard (allow 60 seconds for new changes)"
    await ctx.send(leaderboard)

@bot.command(name="updateleaderboard")
@commands.cooldown(1, 60, commands.BucketType.default)
async def updateleaderboard_command(ctx):
    command_history(f"{ctx.author.id} updated the leaderboard")

    await updateleaderboard()

    await ctx.send(f"Leaderboard up to date! View it here: <{spreadsheet_link}>")

### END User commands

### Leaderboard utilities

async def updateleaderboard():
    async with lock:
        last_update = datetime.utcfromtimestamp(os.path.getmtime(db_path)).replace(
            tzinfo=timezone.utc
        )
        sheet = file.open("Leaderboard")

        # Grabbing sheet last updated time, and rolling back 60 seconds to buffer for time reporting differences
        # Also reduces chances of repeated update requests
        sheettime = datetime.strptime(
            sheet.lastUpdateTime, "%Y-%m-%dT%H:%M:%S.%f%z"
        ) - timedelta(seconds=60)

        # If the database has been not been updated more recently than the sheet, bail out
        if sheettime > last_update:
            command_history(
                f"Bailing out of sheet update - sheet was updated {(sheettime - last_update).seconds} seconds after the DB"
            )
            return
        else:
            command_history(
                f"Sheet was updated {(last_update - sheettime).seconds} seconds before the DB, proceeding with update"
            )

        worksheet = sheet.sheet1

        with db:
            c = db.cursor()
            c.execute("SELECT id, username, doubloons FROM users")
            users = c.fetchall()
            sorted_users = sorted(users, key=lambda user: user[2], reverse=True)
        c.close()

        sheet_values = []

        for user in sorted_users:
            sheet_values.append([user[1], user[2]])

        worksheet.clear()
        worksheet.update(f"A1:B{len(sorted_users)}", sheet_values)

    command_history("Leaderboard updated")


@tasks.loop(minutes=10)
async def updateleaderboard_task():
    command_history("Auto updating the leaderboard")

    await updateleaderboard()


@updateleaderboard_task.before_loop
async def before_updateleaderboard_task():
    await bot.wait_until_ready()
    print("Update leaderboard task ready to start")

### END Leaderboard utilities

### Debug utilities

def get_file_lines(file_name, line_count):
    try:
        # Execute the tail command and capture its output
        output = subprocess.check_output(['tail', f'-n{line_count}', file_name])
        # Decode the output and print the last X lines
        return output.decode().rstrip()
    except subprocess.CalledProcessError as e:
        return (f"Error while executing tail command: {e}")


async def send_file(ctx, filename):
    with open(filename, "rb") as f:
        try:
            await ctx.send(file=f)
        except Exception as e:
            print(f"Error sending file: {e}")


async def send_file_lines(ctx, arg, filename):
    try:
        line_count = get_int(arg, 15)
        output = get_file_lines(filename, line_count)
        try:
            await ctx.send(output)
        except discord.HTTPException:
            await ctx.send(f"Truncated output, full is {len(output)} characters:\n {output[-1500:]}")
    except Exception as e:
        print(f"Error sending file lines: {e}")

### END Debug utilities

### Debug commands

@bot.command(name="test")
async def test(ctx):
    if str(ctx.author.id) != admin:
        print(f"!test attempted by {ctx.author.id}")
        command_history(f"non admin using test: {ctx.author.id}")
        return
    
@bot.command(name="commandhistory")
async def get_command_history(ctx, *arg):
    if str(ctx.channel.id) != debug_channel:
        command_history(f"commandhistory attempted in channel {ctx.channel.id} by {ctx.author.id}")

    if arg == "full":
        await send_file(ctx, "command_history.txt")
        return

    await send_file_lines(ctx, arg, "command_history.txt")

@bot.command(name="pointhistory")
async def get_point_history(ctx, *arg):
    if str(ctx.channel.id) != debug_channel:
        command_history(f"pointhistory attempted in channel {ctx.channel.id} by {ctx.author.id}")

    if arg == "full":
        await send_file(ctx, "point_history.txt")
        return

    await send_file_lines(ctx, arg, "point_history.txt")

@bot.command(name="errorlog")
async def get_error_log(ctx, *arg):
    if str(ctx.author.id) != admin:
        command_history(f"errorlog attempted in channel {ctx.channel.id} by {ctx.author.id}")

    if arg == "full":
        await send_file(ctx, "error_log.txt")
        return

    await send_file_lines(ctx, arg, "error_log.txt")

### END Debug commands


### Start the bot


try:
    bot.run(token)
finally:
    db.close()
    print("DB closed")
