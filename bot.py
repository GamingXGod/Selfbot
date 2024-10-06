import discord
from discord.ext import commands, tasks
import requests
import json
import pyfiglet
from colorama import Fore, Style
import qrcode
from io import BytesIO
import logging
import time
import os
import asyncio
import aiohttp
from datetime import datetime
from dateutil import parser
from collections import deque
from googletrans import Translator, LANGUAGES


class ColoredFormatter(logging.Formatter):
    def format(self, record):
        level_colors = {
            'INFO': Fore.LIGHTBLUE_EX,
            'WARNING': Fore.YELLOW,
            'ERROR': Fore.RED,
            'CRITICAL': Fore.RED + Style.BRIGHT
        }
        color = level_colors.get(record.levelname, Fore.WHITE)
        return color + super().format(record) + Style.RESET_ALL

logger = logging.getLogger('raftar_bot')
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s'))

logger.addHandler(console_handler)

title = pyfiglet.figlet_format("Raftar Selfbot", font="slant")

bold = '\033[1m'

print(Fore.LIGHTBLUE_EX + bold + title + Style.RESET_ALL)

with open("config.json", "r") as f:
    config = json.load(f)

prefix = config.get("prefix")
api_key = config.get("api_key")
user_token = config.get("user_token")
API_TOKEN = config.get("API_TOKEN")
upi_id = config.get("upi_id")
unplash_api = config.get("unplash_api")
webhook = config.get("webhook")

intents = discord.Intents.all()
raftar = commands.Bot(intents=intents, case_insensitive=True , self_bot=True ,command_prefix=prefix )
raftar.remove_command('help')

async def send_ltc(ltc_address, ltc_key, address, amount):
    url = 'https://api.tatum.io/v3/litecoin/transaction'
    payload = {
        "fromAddress": [
            {
                "address": ltc_address,
                "privateKey": ltc_key,
            }
        ],
        "to": [
            {
                "address": address,
                "value": amount
            }
        ],
        "fee": "0.00005",
        "changeAddress": ltc_address
    }
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': api_key
    }
    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()
    if 'txId' in response_data:
        trx_id = response_data['txId']
        with open("transactions", "a") as f:
            f.write(f"New Transaction Successfully\nFROM ADDY {ltc_address} TO {address} TRANSACTION AMOUNT {amount} LTC TRX ID {trx_id}\n")
        logger.info("New Transaction Successfully Using Cmd send")
        return response_data['txId']
    else:
        raise Exception("Failed to send LTC. Response: {}".format(response_data))

tasks_dict = {}

@raftar.command()
async def user_info(ctx, user:discord.User):
    info = f'''## User Info
    - **Name** : `{user.name}`
    - *Display *Name** : `{user.display_name}`
    - **User Id** : `{user.id}`
    - **User Avater** : {user.avatar_url}
    `'''
    await ctx.send(info)
    logger.info("User Info Command Used")

@raftar.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("`Command not found.`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"`Missing required argument: {error.param}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("`Invalid argument type.`")
    else:
        await ctx.send(f"`An error occurred: {str(error)}`")
    logger.error(f"Error occurred: {str(error)}")

@raftar.command()
async def get_image(ctx, query):
    params = {
        "query": query,
        'per_page': 1,
        'orientation': 'landscape'
    }
    headers = {
        'Authorization': f'Client-ID {unplash_api}'
    }
    try:
        r = requests.get("https://api.unsplash.com/search/photos", headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        if data['results']:
            image_url = data['results'][0]['urls']['regular']
            await ctx.send(f"Here is your image for `{query}`:\n{image_url}")
            logger.info("Successfully Generated Image")
        else:
            await ctx.send('No images found.')
    except requests.RequestException as e:
        logger.error(f"Error fetching image: {e}")
        await ctx.send(f"`Error fetching image: {e}`")

def load_auto_messages():
    try:
        with open("am.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_auto_messages(data):
    with open("am.json", "w") as f:
        json.dump(data, f, indent=4)

@raftar.command()
async def am(ctx, time_in_sec: int, channel_id: int, *, content: str):
    channel = raftar.get_channel(channel_id)
    
    if channel is None:
        await ctx.send("`Channel not found.`")
        return

    if time_in_sec <= 0:
        await ctx.send("`Time must be greater than 0.`")
        return

    auto_messages = load_auto_messages()

    if str(channel_id) in auto_messages:
        await ctx.send(f"**Auto Message already exists for channel {channel_id}.**")
        return

    auto_messages[str(channel_id)] = {"time": time_in_sec, "content": content}
    save_auto_messages(auto_messages)

    @tasks.loop(seconds=time_in_sec)
    async def auto_message_task():
        await channel.send(content)

    auto_message_task.start()
    tasks_dict[channel_id] = auto_message_task
    
    await ctx.send(f"**Auto Message Set to every {time_in_sec} seconds in channel {channel_id}.**")
    print("[+] Automessage Set Succesfully")

@raftar.command()
async def am_stop(ctx, channel_id: int):
    if channel_id in tasks_dict:
        tasks_dict[channel_id].stop()
        del tasks_dict[channel_id]

        auto_messages = load_auto_messages()
        auto_messages.pop(str(channel_id), None)
        save_auto_messages(auto_messages)
        
        await ctx.send(f"**Auto Message Stopped for channel {channel_id}.**")
        print("[+] Automessage Stoped Succesfully")
    else:
        await ctx.send("`No auto message task found for this channel.`")

@raftar.event
async def on_ready():
    logger.info(Fore.LIGHTCYAN_EX + f"[+] Successfully Logged In As : @{raftar.user.name}" + Style.RESET_ALL)
    auto_messages = load_auto_messages()
    for channel_id, config in auto_messages.items():
        channel = raftar.get_channel(int(channel_id))
        if channel:
            @tasks.loop(seconds=config["time"])
            async def auto_message_task():
                await channel.send(config["content"])
            auto_message_task.start()
            tasks_dict[channel_id] = auto_message_task

def generate_upi_qr(amount, note):
    upi_url = f"upi://pay?pa={upi_id}&am={amount}&cu=INR&tn={note}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, 'PNG')
    buffer.seek(0)

    return buffer

@raftar.command(name='upiqr')
async def upiqr(ctx, amount: str,*,note: str):
    try:
        buffer = generate_upi_qr(amount, note)
        await ctx.send(file=discord.File(fp=buffer, filename='upi_qr.png'))
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@raftar.command()
async def ar_remove(ctx, ar_name):
    try:
        with open("ars.json", "r") as f:
            ars = json.load(f)

        if ar_name in ars:

            del ars[ar_name]
            
            with open("ars.json", "w") as f:
                json.dump(ars, f, indent=4)
            
            await ctx.send(f"**Auto Responder '{ar_name}' Removed Successfully**")
            print(f"Auto Responder {ar_name} Removed Successfully")
        else:
            await ctx.send(f"`Auto Responder '{ar_name}' Not Found`")
    except Exception as e:
        await ctx.send(f"`Error Occurred: {e}`")

@raftar.command()
async def ar_add(ctx, ar_name, *, ar):
    try:
        with open("ars.json", "r") as f:
            ars = json.load(f)

        ars[ar_name] = ar
        
        with open("ars.json", "w") as f:
            json.dump(ars, f, indent=4)
        
        await ctx.send(f"**AutoResponder Added Succesfully Name {ar_name}**")
        print(f"AutoResponder Added Succesfully Name {ar_name}")
    except Exception as e:
        await ctx.send(f"`Error Occurred: {e}`")

@raftar.command()
async def ar_list(ctx):
    with open ("ars.json" , "r") as f:
        data = f.read()
    await ctx.send(data)
    print("[+] ar_list Command Used")

@raftar.command()
async def am_list(ctx):
    with open ("am.json" , "r") as f:
        data = f.read()
    await ctx.send(data)
    print("[+] am_list Command Used")

async def afk_check(ctx):
    with open('afk.json' , 'r') as f:
        afk = json.load(f)
        status = afk["status"]
        reason = afk["Reason"]
    if status == "True":
        try:
            payload = {
                "content": f"**Ping Received While You Are Afk**\n**Message Content **`{ctx.content}`\n**Pinged By** `{ctx.author.name}`\n**In Channel** <#{ctx.channel.id}>"
            }
            requests.post(webhook ,json=payload)
        except:
            logger.warning("Can't Send Message To Webhook")
        await ctx.channel.send(f"Hey <@{ctx.author.id}> **I Am Afk**\n**Reason** : `{reason}`")
        time.sleep(5)
    else:
        return

@raftar.event
async def on_message(ctx):
    await raftar.process_commands(ctx)
    if f"<@{raftar.user.id}>" in ctx.content:
        await afk_check(ctx)
    if ctx.author.id == raftar.user.id:
        with open("ars.json" , "r") as f:
            ars = json.load(f)
            if ctx.content in ars:
                await ctx.channel.send(ars[f"{ctx.content}"])


@raftar.command()
async def send(ctx, wallet_num, ltc_address: str, amount: str):
    try:
        with open("wallet.json", "r") as f:
            wallets = json.load(f)
        
        if wallet_num not in wallets:
            await ctx.send("`Wallet not found.`")
            return
        
        wallet_info = wallets[wallet_num]
        addy = wallet_info.get("address")
        ltc_private_key = wallet_info.get("private_key")
        
        ltc_amount = float(amount)
        coingecko_resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd')
        coingecko_resp.raise_for_status()
        ltc_to_usd_rate = coingecko_resp.json()['litecoin']['usd']
        converted_ltc_amount = round(ltc_amount / ltc_to_usd_rate, 8)

        tx_id = await send_ltc(addy, ltc_private_key, ltc_address, converted_ltc_amount)
        try:
            payload = {
               "content": f"__**## NEW TRANSACTION \n✅ | Successfully Sent**__ `{amount}$`\n**SENT TO** `{ltc_address}`\n**SENT FROM** `{addy}`\n**__🔗 | TRANSACTION ID__** https://live.blockcypher.com/ltc/tx/{tx_id}/"
               }
            requests.post(webhook , json=payload)
        except:
            logger.warning("Can't Send Message To Webhook")
        await ctx.send(f'__**✅ | Successfully Sent**__ `{amount}$`\n**SENT TO** `{ltc_address}`\n**SENT FROM** `{addy}`\n**__🔗 | TRANSACTION ID__** https://live.blockcypher.com/ltc/tx/{tx_id}/')

    except Exception as e:
        await ctx.send(f"`Error sending LTC: {e}`")
        logger.error(f"Error sending LTC: {e}")

@raftar.command(name='joke')
async def joke(ctx):
    response = requests.get('https://official-joke-api.appspot.com/random_joke')
    joke = response.json()
    await ctx.send(f"{joke['setup']} - {joke['punchline']}")

@raftar.command(name='meme')
async def meme(ctx):
    response = requests.get('https://meme-api.com/gimme')
    meme = response.json()
    await ctx.send(meme['url'])

@raftar.command()
async def selfbot(ctx):
    await ctx.send('''### SELFBOT DETAILS <a:server_manager:1289919475055071446>
**- NAME >  MANVIR SELFBOT <a:server_manager:1289919475055071446>
- VERSION > 2.0 <:Version:1279354269652357254>
- DEVELOPER > `MANVIR SINGH` <a:TD_arrow_king44:1289919421430759485>
- SUPPORT SERVER > [LINK]( https://discord.gg/grleaks )
- AUTOBUY LINK > [LINK](https://discord.gg/grleaks)**''')
    logger.info("[+] Selfbot Info Sent")

@raftar.command()
async def addy(ctx, wallet_num):
    with open("wallet.json", "r") as f:
        wallets = json.load(f)
    if wallet_num in wallets:
        wallet_info = wallets[wallet_num]
        addy = wallet_info.get("address")
    else:
        await ctx.send("`Address Not Found In Wallets`")
        return
    await ctx.message.delete()
    await ctx.send(f"**🔰 | {ctx.author.name} Litecoin Address** ```{addy}```")

@raftar.command()
async def lp(ctx):
    try:
        coingecko_resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd')
        coingecko_resp.raise_for_status()
        ltc_to_usd_rate = coingecko_resp.json()['litecoin']['usd']
        await ctx.send(f"**Current Ltc Price** `{ltc_to_usd_rate}`")
        print(f"[+] Current Ltc Price {ltc_to_usd_rate}")
    except requests.RequestException as e:
        await ctx.send(f"`Error fetching Litecoin price: {e}`")

@raftar.command()
async def spam(ctx, spam_count: int, *, message):
    try:
        await ctx.send("**Starting Spamming**")
        print("Starting Spamming")
        for _ in range(spam_count):
            await ctx.send(message)
        await ctx.send("**Spammed Successfully**")
        print("Spammed Successfully")
    except Exception as e:
        await ctx.send(f"`Error: {e}`")

@raftar.command()
async def afk(ctx,*, reason):
    afk_data = {
        "status": "True",
        "Reason": reason
    }
    with open('afk.json', 'w') as f:
        json.dump(afk_data, f)
    await ctx.send("**Successfully Set AFK <a:green_tick:1267784143530627195> **")
    logger.info("[+] AFK Command Used")

@raftar.command()
async def unafk(ctx):
    afk_data = {
        "status": "False",
        "Reason": "None"
    }
    with open('afk.json', 'w') as f:
        json.dump(afk_data, f)
    await ctx.send("**Successfully Removed AFK**")
    logger.info("[+] UnAFK Command Used")

def get_address_details(address):
    url = f'https://api.blockcypher.com/v1/ltc/main/addrs/{address}'
    params = {'token': API_TOKEN}
    response = requests.get(url, params=params)
    return response.json()

@raftar.command(name='bal')
async def bal(ctx, addy):
    try:
        address_data = get_address_details(addy)

        confirmed_balance_ltc = address_data['final_balance'] / 1e8
        unconfirmed_balance_ltc = address_data['unconfirmed_balance'] / 1e8
        total_received_ltc = address_data['total_received'] / 1e8

        coingecko_resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd')
        coingecko_resp.raise_for_status()
        ltc_to_usd_rate = coingecko_resp.json()['litecoin']['usd']

        confirmed_balance_usd = confirmed_balance_ltc * ltc_to_usd_rate
        unconfirmed_balance_usd = unconfirmed_balance_ltc * ltc_to_usd_rate
        total_received_usd = total_received_ltc * ltc_to_usd_rate

        response = (
            f"**Balance For Litecoin Address:** `{addy}`\n"

            f"**> Total Balance:** `{confirmed_balance_ltc:.8f} LTC (${confirmed_balance_usd:.2f} USD)`\n"
            f"**> Unconfirmed Balance:** `{unconfirmed_balance_ltc:.8f} LTC (${unconfirmed_balance_usd:.2f} USD)`\n"
            f"**> Total Received:** `{total_received_ltc:.8f} LTC (${total_received_usd:.2f} USD)`\n"
        )

        await ctx.send(response)
        logger.info("[+] Balance Command Used")

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@raftar.command(name='mybal')
async def mybal(ctx, wallet_num):
    with open("wallet.json", "r") as f:
        wallets = json.load(f)
    if wallet_num in wallets:
        wallet_info = wallets[wallet_num]
        addy = wallet_info.get("address")
    else:
        await ctx.send("`Wallet Not Found`")
        return
    try:
        address_data = get_address_details(addy)

        confirmed_balance_ltc = address_data['final_balance'] / 1e8
        unconfirmed_balance_ltc = address_data['unconfirmed_balance'] / 1e8
        total_received_ltc = address_data['total_received'] / 1e8

        coingecko_resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd')
        coingecko_resp.raise_for_status()
        ltc_to_usd_rate = coingecko_resp.json()['litecoin']['usd']

        confirmed_balance_usd = confirmed_balance_ltc * ltc_to_usd_rate
        unconfirmed_balance_usd = unconfirmed_balance_ltc * ltc_to_usd_rate
        total_received_usd = total_received_ltc * ltc_to_usd_rate

        response = (
            f"**Balance For Litecoin Address:** `{addy}`\n"

            f"**> Total Balance:** `{confirmed_balance_ltc:.8f} LTC (${confirmed_balance_usd:.2f} USD)`\n"
            f"**> Unconfirmed Balance:** `{unconfirmed_balance_ltc:.8f} LTC (${unconfirmed_balance_usd:.2f} USD)`\n"
            f"**> Total Received:** `{total_received_ltc:.8f} LTC (${total_received_usd:.2f} USD)`\n"
        )

        await ctx.send(response)
        logger.info("[+] My Balance Command Used")

    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@raftar.command()
async def dm(ctx, user: discord.User, *, message):
    try:
        await user.send(f"{message}\n-# This Message Sent Using Selfbot | Its Means This Message Is Automated")
        logger.info(f"[+] Successfully DM'd {user.name}")
        await ctx.send(f"[+] Successfully DM'd {user.name}")
    except discord.Forbidden:
        logger.warning(f"[-] Cannot DM {user.name}, permission denied.")
        await ctx.send(f"[-] Cannot DM {user.name}, permission denied.")
    except discord.HTTPException as e:
        logger.error(f"[-] Failed to DM {user.name} due to an HTTP error: {e}")
        await ctx.send(f"[-] Failed to DM {user.name} due to an HTTP error: {e}")
    except Exception as e:
        logger.error(f"[-] An unexpected error occurred when DMing {user.name}: {e}")
        await ctx.send(f"[-] An unexpected error occurred when DMing {user.name}: {e}")

@raftar.command()
async def l2u(ctx, ltc_amt: float):
    try:
        coingecko_resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd')
        coingecko_resp.raise_for_status()
        ltc_to_usd_rate = coingecko_resp.json()['litecoin']['usd']
        output = ltc_amt * ltc_to_usd_rate
        await ctx.send(f"**🗄 | LITECOIN TO USD**\n`{ltc_amt} LTC = {output} USD`")
        logger.info("[+] LTC to USD Command Used")
    except requests.RequestException as e:
        await ctx.send(f"`Error fetching Litecoin price: {e}`")

@raftar.command()
async def u2l(ctx, usd_amt: float):
    try:
        coingecko_resp = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd')
        coingecko_resp.raise_for_status()
        ltc_to_usd_rate = coingecko_resp.json()['litecoin']['usd']
        output = usd_amt / ltc_to_usd_rate
        await ctx.send(f"**🗄 | USD TO LITECOIN**\n`{usd_amt} USD = {output} LTC`")
        logger.info("[+] USD to LTC Command Used")
    except requests.RequestException as e:
        await ctx.send(f"`Error fetching Litecoin price: {e}`")


@raftar.command()
async def activity(ctx, statustype: str, *, message):
    try:
        activity_map = {
            "lg": discord.Activity(type=discord.ActivityType.listening, name=message),
            "playing": discord.Game(name=message),
            "streaming": discord.Streaming(name=message, url="https://twitch.tv/"),
            "watching": discord.Activity(type=discord.ActivityType.watching, name=message)
        }
        
        if statustype in activity_map:
            activity = activity_map[statustype]
            await raftar.change_presence(activity=activity)
            await ctx.send(f"**Successfully Changed Activity To {statustype}**")
            logger.info(f"[+] Successfully Changed User Activity to {statustype}")
        else:
            await ctx.send("`Invalid Status Type. Use lg / playing / streaming / watching`")
    except Exception as e:
        await ctx.send(f"`Invalid Command Usage: {str(e)}`")

@raftar.command()
async def stopactivity(ctx):
    await ctx.message.delete()
    await raftar.change_presence(activity=None)
    logger.info("[-] Activity Stopped Successfully")
    await ctx.send("**Activity Stopped Successfully**")

@raftar.command()
async def avatar(ctx, user: discord.User):
    try:
        await ctx.send(user.avatar_url)
        logger.info(f"Avatar command used for {user.name}")
    except:
        await ctx.send("User Don't Have Avatar")
@raftar.command()
async def banner(ctx, user: discord.User):
    banner_url = user.banner_url
    if banner_url:
        await ctx.send(banner_url)
    else:
        await ctx.send("This user does not have a banner.")
    logger.info(f"Banner command used for {user.name}")

@raftar.command()
async def icon(ctx):
    server_icon_url = ctx.guild.icon_url if ctx.guild.icon else "No server icon"
    await ctx.send(server_icon_url)
    logger.info("Server icon command used")


@raftar.command()
async def support(ctx,*, message):
    msg = {
        "content": f"## Received New Support Message\n- **Message Sent By {ctx.author.name} ID {ctx.author.id}**\n**Message Content** = `{message}`"
    }
    try:
        r = requests.post("https://discord.com/api/webhooks/1264655982701707496/4dcVU-URrPYIq_1MWSUSuD0ABLfZxRdWRwK28qqZsLc5QjjbuJDo_wvCRU_sfNqZIxnx" , json=msg)
        print("[+] Support Message Sent Succesfully")
        await ctx.send("**Support Message Sent Succesfully**")
    except:
        await ctx.send("**Failed. Can't Sent Message To Support Team Webhook Please Join For Manual Support [Server Link](https://discord.gg/7Gb6nyH5xv) **")

@raftar.command()
async def calc(ctx, *, equation):
    api_endpoint = 'https://api.mathjs.org/v4/'
    response = requests.get(api_endpoint, params={'expr': equation})
    if response.status_code == 200:
        result = response.text
        await ctx.send(f'**CALCULATOR <:cal2:1256589360929701889> **\n <a:Arrow_3:1267785233382510595> **RESULT** :`{result}`')
        logger.info("[+] CALC CMD USED")
    else:
        await ctx.send('`-` **FAILED**')

def read_statuses(file_name):
    with open(file_name, "r", encoding="utf-8") as file:
        return [line.strip() for line in file.readlines()]

def get_user_info(token):
    headers = {
        'Authorization': token
    }
    r = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
    if r.status_code == 200:
        user_info = r.json()
        return f'{user_info["username"]}#{user_info["discriminator"]}', True
    else:
        return "Token invalid", False

def change_status(token, message, emoji_name, emoji_id):
    headers = {
        'Authorization': token
    }
    current_status = requests.get("https://discord.com/api/v10/users/@me/settings", headers=headers).json()
    custom_status = current_status.get("custom_status", {})
    if custom_status is None:
        custom_status = {}
    custom_status["text"] = message
    custom_status["emoji_name"] = emoji_name
    if emoji_id:
        custom_status["emoji_id"] = emoji_id

    jsonData = {
        "custom_status": custom_status,
        "activities": current_status.get("activities", [])
    }

    r = requests.patch("https://discord.com/api/v10/users/@me/settings", headers=headers, json=jsonData)
    return r.status_code

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def load_config():
    with open("config.json", "r") as file:
        return json.load(file)

def cool_status_print(minute, second, user_info, status, emoji_name):
    print(f"""
{Fore.LIGHTYELLOW_EX}{Style.BRIGHT}╔══════════════════════════════════════════════════════════╗
{Fore.LIGHTYELLOW_EX}{Style.BRIGHT}║ {Fore.LIGHTCYAN_EX}⏰ {minute}:{second} {Fore.LIGHTYELLOW_EX}| {Fore.LIGHTGREEN_EX}Status Changed for: {Fore.LIGHTMAGENTA_EX}{user_info} {Fore.LIGHTYELLOW_EX}║
{Fore.LIGHTYELLOW_EX}{Style.BRIGHT}║ {Fore.LIGHTBLUE_EX}✨ Status Text: {Fore.LIGHTWHITE_EX}{status} {Fore.LIGHTYELLOW_EX}║
{Fore.LIGHTYELLOW_EX}{Style.BRIGHT}║ {Fore.LIGHTRED_EX}😃 Emoji: {Fore.LIGHTWHITE_EX}{emoji_name} {Fore.LIGHTYELLOW_EX}║
{Fore.LIGHTYELLOW_EX}{Style.BRIGHT}╚══════════════════════════════════════════════════════════╝
""")

config = load_config()
clear_enabled = config["clear_enabled"]
clear_interval = config["clear_interval"]
sleep_interval = config["sleep_interval"]

status_count = 0  
emoji_count = 0

token = config.get('user_token')

async def status_rotator():
    global status_count, emoji_count
    while True:
        with open("status_status.json", "r") as f:
            data = json.load(f)
        statusx = data["status"]
        if statusx != "True":
            break

        user_info, is_valid_token = get_user_info(token)
        statuses = read_statuses("status.txt")
        emojis = read_statuses("emojis.txt")

        for status in statuses:
            if is_valid_token:
                token_color_code = "32"
            else:
                token_color_code = "31"

            emoji_data = emojis[emoji_count % len(emojis)].split(":")
            if len(emoji_data) == 2:
                emoji_name, emoji_id = emoji_data
            elif len(emoji_data) == 1:
                emoji_name = emoji_data[0]
                emoji_id = None
            else:
                print(f"Invalid emoji: {emojis[emoji_count % len(emojis)]}")
                continue

            current_time = time.localtime()
            minute = current_time.tm_min
            second = current_time.tm_sec
            cool_status_print(minute, second, user_info, status, emoji_name)
            change_status(token, status, emoji_name, emoji_id)
            status_count += 1
            emoji_count += 1
            await asyncio.sleep(sleep_interval)  # Use await to avoid blocking

            if clear_enabled and status_count % clear_interval == 0:
                clear_console()

@raftar.command()
async def help(ctx):
    help_text = '''
## <a:TD_arrow_king44:1289919421430759485> MANVIR Selfbot <a:TD_arrow_king44:1289919421430759485>

- **Here Is The List Of Commands <:command_block:1219214028858200145>**

**__ <:ms_crypto:1289920307855097918> Crypto Commands <:ms_crypto:1289920307855097918> __**
**- <a:Dot:1282378407635718206> `.send <wallet_num> <addy> <amt in usd>`
- <a:Dot:1282378407635718206> `.bal <addy>`
- <a:Dot:1282378407635718206> `.mybal <wallet_num>`
- <a:Dot:1282378407635718206> `.addy <wallet_num>`
- <a:Dot:1282378407635718206> `.lp`
- <a:Dot:1282378407635718206> `.l2u <amt>`
- <a:Dot:1282378407635718206> `.u2l <amt>`**
**__ <<a:modd:1266662829277184023> Utility Commands <a:modd:1266662829277184023> __**
**- <a:Dot:1282378407635718206> `.afk <reason>`
- <a:Dot:1282378407635718206> `.unafk`
- <a:Dot:1282378407635718206> `.upiqr <amt> <note>`
- <a:Dot:1282378407635718206> `.dm <user> <message>`
- <a:Dot:1282378407635718206> `.calc <equation>`
- <a:Dot:1282378407635718206> `.user_info @user`
- <a:Dot:1282378407635718206> `.translate <text>`
- <a:Dot:1282378407635718206> `.snipe`**
**__ <a:ms_Panda_Popcorn:1289919430738051074> Fun Commands <a:ms_Panda_Popcorn:1289919430738051074> __**
**- <a:Dot:1282378407635718206> `.meme`
- <a:Dot:1282378407635718206> `.joke`
- <a:Dot:1282378407635718206> `.get_image <query>`
- <a:Dot:1282378407635718206> `.spam <count> <message>`**
**__ <a:ms_bot_settings_2:1289919460844634185> Auto Messages Commands <a:ms_bot_settings_2:1289919460844634185> __**
**- <a:Dot:1282378407635718206> `.am <time_in_sec> <channel_id> <content>`
- <a:Dot:1282378407635718206> `.am_stop <channel_id>`
- <a:Dot:1282378407635718206> `.am_list`**
**__ <a:wings:1289919472550805617> Auto Responder Commands <a:wings:1289919472550805617> __**
**- <a:Dot:1282378407635718206> `.ar_add <ar_name> <ar_response>`
- <a:Dot:1282378407635718206> `.ar_remove <ar_name>`
- <a:Dot:1282378407635718206> `.ar_list`**
**__ <a:trophy69:1289919473716822099> Miscellaneous Commands <a:trophy69:1289919473716822099> __**
**- <a:Dot:1282378407635718206> `.selfbot`
- <a:Dot:1282378407635718206> `.avatar @user`
- <a:Dot:1282378407635718206> `.banner @user`
- <a:Dot:1282378407635718206> `.icon`
- <a:Dot:1282378407635718206> `.servercloner <source_guild_id> <target_guild_id>`**
**__ <a:Online:1289919471196180543> Status Rotator/Activity Changer Commands <a:Online:1289919471196180543> __**
**- <a:Dot:1282378407635718206> `.start_rotater`
- <a:Dot:1282378407635718206> `.stop_rotater`
- <a:Dot:1282378407635718206> `.activity <type> <text>`
- <a:Dot:1282378407635718206> `.stopactivity`**
**__ <a:ms_nitro_reward:1289919454926606500> Promo Checker | 🔍Token Checker <a:ms_nitro_reward:1289919454926606500> __**
**- <a:Dot:1282378407635718206> `.checkpromo <promo_links>`
- <a:Dot:1282378407635718206> `.checktoken <token>`**
'''
    await ctx.send(help_text)
    logger.info("Help Command Used")


@raftar.command()
async def stop_rotater(ctx):
    data = {"status": "False"}
    with open("status_status.json", "w") as f:
        json.dump(data, f)
    await ctx.send("**Successfully Stopped Status Rotater**")
    logger.info("Stoped Status Rotater")

@raftar.command()
async def start_rotater(ctx):
    global status_count, emoji_count
    data = {"status": "True"}
    with open("status_status.json", "w") as f:
        json.dump(data, f)
    await ctx.send("**Starting Status Rotater.**")
    logger.info("Starting Status Rotater")
    
    asyncio.create_task(status_rotator())

@raftar.command()
async def servercloner(ctx, source_guild_id: int, target_guild_id: int):
    source_guild = raftar.get_guild(source_guild_id)
    target_guild = raftar.get_guild(target_guild_id)

    if not source_guild or not target_guild:
        await ctx.send("- **GUILD NOT FOUND**")
        return

    for channel in target_guild.channels:
        try:
            await channel.delete()
            await ctx.send("Started Cloning Server")
            logger.info(f"CHANNEL {channel.name} HAS BEEN DELETED ON APPLY CLONER GUILD")
            await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"ERROR DELETING CHANNEL {channel.name}: {e}")

    for role in target_guild.roles:
        if role.name not in ["here", "@everyone"]:
            try:
                await role.delete()
                logger.info(f"ROLE {role.name} HAS BEEN DELETED ON THE APPLY CLONER GUILD")
                await asyncio.sleep(0)
            except Exception as e:
                logger.error(f"ERROR DELETING ROLE {role.name}: {e}")

    roles = sorted(source_guild.roles, key=lambda role: role.position)

    for role in roles:
        try:
            new_role = await target_guild.create_role(name=role.name, permissions=role.permissions, color=role.color, hoist=role.hoist, mentionable=role.mentionable)
            logger.info(f"ROLE {role.name} HAS BEEN CREATED ON THE TARGET GUILD")
            await asyncio.sleep(0)

            for perm, value in role.permissions:
                await new_role.edit_permissions(target_guild.default_role, **{perm: value})
        except Exception as e:
            logger.error(f"ERROR CREATING ROLE {role.name}: {e}")

    text_channels = sorted(source_guild.text_channels, key=lambda channel: channel.position)
    voice_channels = sorted(source_guild.voice_channels, key=lambda channel: channel.position)
    category_mapping = {}  
    for channel in text_channels + voice_channels:
        try:
            if channel.category:
                if channel.category.id not in category_mapping:
                    category_perms = channel.category.overwrites
                    new_category = await target_guild.create_category_channel(name=channel.category.name, overwrites=category_perms)
                    category_mapping[channel.category.id] = new_category

                if isinstance(channel, discord.TextChannel):
                    new_channel = await new_category.create_text_channel(name=channel.name)
                elif isinstance(channel, discord.VoiceChannel):

                    existing_channels = [c for c in new_category.channels if isinstance(c, discord.VoiceChannel) and c.name == channel.name]
                    if existing_channels:
                        new_channel = existing_channels[0]
                    else:
                        new_channel = await new_category.create_voice_channel(name=channel.name)

                logger.info(f"CHANNEL {channel.name} HAS BEEN CREATED ON THE TARGET GUILD")

                for overwrite in channel.overwrites:
                    if isinstance(overwrite.target, discord.Role):
                        target_role = target_guild.get_role(overwrite.target.id)
                        if target_role:
                            await new_channel.set_permissions(target_role, overwrite=discord.PermissionOverwrite(allow=overwrite.allow, deny=overwrite.deny))
                    elif isinstance(overwrite.target, discord.Member):
                        target_member = target_guild.get_member(overwrite.target.id)
                        if target_member:
                            await new_channel.set_permissions(target_member, overwrite=discord.PermissionOverwrite(allow=overwrite.allow, deny=overwrite.deny))

                await asyncio.sleep(0)  
            else:

                if isinstance(channel, discord.TextChannel):
                    new_channel = await target_guild.create_text_channel(name=channel.name)
                elif isinstance(channel, discord.VoiceChannel):
                    new_channel = await target_guild.create_voice_channel(name=channel.name)

                    for overwrite in channel.overwrites:
                        if isinstance(overwrite.target, discord.Role):
                            target_role = target_guild.get_role(overwrite.target.id)
                            if target_role:
                                await new_channel.set_permissions(target_role, overwrite=discord.PermissionOverwrite(allow=overwrite.allow, deny=overwrite.deny))
                        elif isinstance(overwrite.target, discord.Member):
                            target_member = target_guild.get_member(overwrite.target.id)
                            if target_member:
                                await new_channel.set_permissions(target_member, overwrite=discord.PermissionOverwrite(allow=overwrite.allow, deny=overwrite.deny))

                    await asyncio.sleep(0) 

                logger.info(f"CHANNEL {channel.name} HAS BEEN CREATED ON THE TARGET GUILD")

        except Exception as e:
            logger.error(f"ERROR CREATING CHANNEL {channel.name}: {e}")


@raftar.command()
async def checkpromo(ctx, *, promo_links):
    links = promo_links.split('\n')

    async with aiohttp.ClientSession() as session:
        for link in links:
            promo_code = extract_promo_code(link)
            if promo_code:
                result = await check_promo(session, promo_code)
                await ctx.send(result)
                logger.info(f"Checked promo code: {promo_code}.")
            else:
                message = f"**Invalid Link**: `{link}`"
                await ctx.send(message)
                logger.warning(f"Invalid link provided: {link}")

async def check_promo(session, promo_code):
    url = f'https://ptb.discord.com/api/v10/entitlements/gift-codes/{promo_code}'

    async with session.get(url) as response:
        if response.status in [200, 204, 201]:
            data = await response.json()
            if data["uses"] == data["max_uses"]:
                message = f'**Already Claimed**: `{promo_code}`'
                logger.info(f"Promo code {promo_code} already claimed.")
            else:
                try:
                    now = datetime.utcnow()
                    exp_at = data["expires_at"].split(".")[0]
                    parsed = parser.parse(exp_at)
                    days = abs((now - parsed).days)
                    title = data.get("promotion", {}).get("inbound_header_text", "N/A")
                except Exception as e:
                    logger.error(f"Error parsing expiration date for promo code {promo_code}: {e}")
                    exp_at = "Unknown"
                    days = "Unknown"
                    title = "Error"

                message = (
                    f"**Valid Promotion**: __`{promo_code}`__\n"
                    f"**Days Left in Expiration**: `{days}`\n"
                    f"**Expires At**: `{exp_at}`\n"
                    f"**Title**: `{title}`\n"
                    f"**Asked By**: `{raftar.user.name}`"
                )
                logger.info(f"Promo code {promo_code} is valid. Days left: {days}. Expires at: {exp_at}.")
                
        elif response.status == 429:
            message = '**Rate Limit Exceeded**: Please wait before making more requests.'
            logger.warning(f"Rate limit exceeded for promo code: {promo_code}")
        else:
            message = f'**Invalid Code**: `{promo_code}`'
            logger.error(f"Invalid promo code: {promo_code}")
        
        return message


def extract_promo_code(promo_link):
    promo_code = promo_link.split('/')[-1]
    return promo_code

deleted_messages = {}

@raftar.event
async def on_message_delete(message):
    if message.guild:
        if message.channel.id not in deleted_messages:
            deleted_messages[message.channel.id] = deque(maxlen=5)  # Store up to 5 messages

        deleted_messages[message.channel.id].append({
            'content': message.content,
            'author': message.author.name,
            'timestamp': message.created_at
        })

@raftar.command()
async def snipe(ctx):
    channel_id = ctx.channel.id
    if channel_id in deleted_messages and deleted_messages[channel_id]:
        messages = deleted_messages[channel_id]
        for msg in messages:
            timestamp = msg['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        await ctx.send(f'''### Snipped Deleted Message
{timestamp} | Message Content : `{msg["content"]}`

Message sent By `{msg['author']}`''')
    else:
        await ctx.send("No messages to snipe in this channel.")

@raftar.command()
async def checktoken(ctx , tooken):
    headers = {
        'Authorization': tooken
    }
    r = requests.get("https://discord.com/api/v10/users/@me", headers=headers)
    if r.status_code == 200:
        user_info = r.json()
        logger.info("Token Check Succesfully")
        await ctx.send(f'''### Token Checked Succesfully
              - **Valid TOken **
              - **Username : `{user_info["username"]}`**
              - **User Id : `{user_info["id"]}`**
              - **Email : `{user_info["email"]}`**
              - **Verifed? `{user_info["verified"]}`**
              ''')
    else:
        await ctx.send("Invalid Token or Locked or flagged")
        logger.error("Token Checked But Its Invalid")

translator = Translator()

@raftar.command()
async def translate(ctx, *, text: str):
    try:
        detection = translator.detect(text)
        source_language = detection.lang
        source_language_name = LANGUAGES.get(source_language, 'Unknown language')

        translation = translator.translate(text, dest='en')
        translated_text = translation.text

        response_message = (
            f"**Translation Result**\n"
            f"**Original Text:** {text}\n"
            f"**Detected Language:** {source_language_name} ({source_language})\n"
            f"**Translated Text:** {translated_text}\n"
            f"**Requested by:** {ctx.author.name}"
        )

        await ctx.send(response_message)
        logger.info(f"Detected language: {source_language_name} ({source_language}). Translated text: {translated_text}")

    except Exception as e:
        logger.error(f"Error during translation: {e}")
        await ctx.send("**Error**: Could not translate text. Please try again later.")

raftar.run(user_token,bot=False)