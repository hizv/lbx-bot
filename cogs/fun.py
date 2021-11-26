from io import BytesIO

import aiohttp
import discord
from config import SETTINGS, conn_url
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
from utils.api import api_call
from utils.film import get_search_result

prefix = SETTINGS["prefix"]


def get_conn_url(db_name: str) -> str:
    """Return the psql connection url."""
    return conn_url + db_name + "?retryWrites=true&w=majority"


class Fun(commands.Cog):
    """Fun commands."""

    def __init__(self, bot):  # noqa
        self.bot = bot
        self.db = bot.db

    @commands.command(aliases=["da"])
    async def pick(self, ctx, *, keywords: str):  # noqa
        if not keywords:
            return None
        minion, bob = keywords.split("|")
        film1 = await get_search_result(minion)
        film2 = await get_search_result(bob)
        if not (film1 or film2):
            return None

        f1_details = await api_call(f"film/{film1['id']}")
        f2_details = await api_call(f"film/{film2['id']}")

        if "poster" not in f1_details or "poster" not in f2_details:
            await ctx.send("No poster found")

        async with aiohttp.ClientSession() as cs:
            async with cs.get(f1_details["poster"]["sizes"][-1]["url"]) as r:
                if r.status >= 400:
                    await ctx.send("Connection error. Try again")
                else:
                    response = await r.read()
                    path = BytesIO(response)
                    poster1 = Image.open(path)

            async with cs.get(f2_details["poster"]["sizes"][-1]["url"]) as r:
                if r.status >= 400:
                    await ctx.send("Connection error. Try again")
                else:
                    response = await r.read()
                    path = BytesIO(response)
                    poster2 = Image.open(path)

            background = Image.open("background.png")
            poster1Resize = poster1.resize((240, 360))
            poster2Resize = poster2.resize((240, 360))
            template = Image.open("fo-today-template.png")
            newImage = background.copy()
            newImage.paste(poster1Resize, (50, 95))
            newImage.paste(poster2Resize, (420, 95))
            newImage.paste(template, (0, 0), template)
            drawing1 = ImageDraw.Draw(newImage)
            myFont = ImageFont.truetype("times-new-roman.ttf", 20)

            title1 = f"{f1_details['name']}"
            if "releaseYear" in f1_details:
                title1 += " (" + str(f1_details["releaseYear"]) + ")"
            title2 = f"{f2_details['name']}"
            if "releaseYear" in f2_details:
                title2 += " (" + str(f1_details["releaseYear"]) + ")"

            drawing1.text((55, 425), title1, fill=(255, 255, 255), font=myFont)
            drawing1.text((55, 525), title2, fill=(255, 255, 255), font=myFont)
            newImage.save("new-image.png", quality=95)
            await ctx.send(file=discord.File("new-image.png"))


def setup(bot):
    bot.add_cog(Fun(bot))
