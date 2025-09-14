import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from flask import Flask
import threading

from collections import defaultdict
import time

reply_history = defaultdict(list)  # key: (user1_id, user2_id), value: list of dicts
REPLY_WINDOW = 1200  # 秒（例：20分）
REPLY_THRESHOLD = 6  # 回数（例：6回以上）

# .envからトークンを読み込む
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Flaskサーバ（RenderのHealth Check用）
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

# Discord Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def no_other_activity_in_channel(channel, pair):
    async for message in channel.history(limit=10):
        if message.author.bot:
            continue
        if message.author.id not in pair:
            return False
    return True

# ❶ 対象チャンネルIDの記録用（初期値は未設定）
target_channel_id = None
last_prompt_message = None

class RPModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="RPつぶやき")
        self.input = discord.ui.TextInput(label="内容", style=discord.TextStyle.short)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        global last_prompt_message

        embed = discord.Embed(description=self.input.value, color=discord.Color.purple())
        avatar_url = interaction.user.avatar.url if interaction.user.avatar else None
        embed.set_author(name=interaction.user.display_name, icon_url=avatar_url)
        await interaction.channel.send(embed=embed, view=ReplyView(embed, interaction.user))
        await interaction.response.defer(ephemeral=True)

        if last_prompt_message:
            try:
                await last_prompt_message.delete()
            except discord.NotFound:
                pass

        last_prompt_message = await interaction.channel.send(
            "今の気持ちや想い、少し語ってみませんか？",
            view=RPView(),
            allowed_mentions=discord.AllowedMentions.none()
        )


class ReplyModal(discord.ui.Modal):
    def __init__(self, original_embed: discord.Embed, original_user: discord.User):
        super().__init__(title="RP返信")
        self.input = discord.ui.TextInput(label="返信内容", style=discord.TextStyle.short)
        self.original_embed = original_embed
        self.original_user = original_user
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        # 履歴記録
        pair = tuple(sorted([interaction.user.id, self.original_user.id]))
        now = time.time()
        reply_history[pair] = [r for r in reply_history[pair] if now - r["timestamp"] < REPLY_WINDOW]
        reply_history[pair].append({
            "timestamp": now,
            "author": interaction.user,
            "content": self.input.value,
            "original_user": self.original_user,
            "original_embed": self.original_embed
        })

        reply_count = len(reply_history[pair])

        # 色判定
        if reply_count >= 10:
            color = discord.Color.red()
        elif reply_count >= 5:
            color = discord.Color.orange()
        else:
            color = discord.Color.blue()
        
        reply_embed = discord.Embed(
            description=f"🗨️ {self.original_user.display_name}: {self.original_embed.description}",
            color=color
        )
        avatar_url = interaction.user.avatar.url if interaction.user.avatar else None
        reply_embed.set_author(name=interaction.user.display_name, icon_url=avatar_url)

        reply_embed.add_field(
            name="返信",
            value=self.input.value,
            inline=False
        )

        # 履歴記録
        pair = tuple(sorted([interaction.user.id, self.original_user.id]))
        now = time.time()

        # 条件判定
        should_thread_by_time = len(reply_history[pair]) >= REPLY_THRESHOLD
        # 条件②：静かな空間での連続返信（新規）
        should_thread_by_isolation = (
            len(reply_history[pair]) >= 10 and
            await no_other_activity_in_channel(interaction.channel, pair)
        )
        # 最終判定：どちらかが成立したらスレッド化
        should_thread = should_thread_by_time or should_thread_by_isolation

        if should_thread:
            thread = await interaction.channel.create_thread(
                name=f"RP会話：{interaction.user.display_name}↔{self.original_user.display_name}",
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60
            )
            await thread.send(
                content="会話が盛り上がってたから、こっそり専用スレッド作ったよ。 \nここはふたりの秘密基地ってことで。続き、楽しみにしてるね！",
                allowed_mentions=discord.AllowedMentions.none()
            )

            for entry in sorted(reply_history[pair], key=lambda x: x["timestamp"]):
                embed = discord.Embed(
                    description=f"🗨️ {entry['original_user'].display_name}: {entry['original_embed'].description}",
                    color=color
                )
                avatar_url = entry["author"].avatar.url if entry["author"].avatar else None
                embed.set_author(name=entry["author"].display_name, icon_url=avatar_url)
                embed.add_field(name="返信", value=entry["content"], inline=False)

                await thread.send(
                    content=f"{entry['original_user'].mention}",
                    embed=embed,
                    view=ReplyView(embed, entry["author"])
                )

            await thread.add_user(self.original_user)
            await thread.add_user(interaction.user)
        else:
            await interaction.channel.send(
                content=f"{self.original_user.mention}",
                embed=reply_embed,
                view=ReplyView(reply_embed, interaction.user)
            )

        await interaction.response.defer(ephemeral=True)
        global last_prompt_message
        if last_prompt_message:
            try:
                await last_prompt_message.delete()
            except discord.NotFound:
                pass

        last_prompt_message = await interaction.channel.send(
            "今の気持ちや想い、少し語ってみませんか？",
            view=RPView(),
            allowed_mentions=discord.AllowedMentions.none()
        )


class RPView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 無効化されないように timeout を無効化

    @discord.ui.button(label="つぶやく", style=discord.ButtonStyle.primary, custom_id="rpbutton")
    async def rp_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RPModal())

class ReplyView(discord.ui.View):
    def __init__(self, original_embed: discord.Embed, original_user: discord.User):
        super().__init__(timeout=None)
        self.original_embed = original_embed
        self.original_user = original_user

    @discord.ui.button(label="返信する", style=discord.ButtonStyle.secondary, custom_id="replybutton")
    async def reply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReplyModal(self.original_embed, self.original_user))


@bot.command()
async def rp(ctx):
    global target_channel_id, last_prompt_message
    target_channel_id = ctx.channel.id  # 実行されたチャンネルを記録
    
    last_prompt_message = await ctx.send(
        "今の気持ちや想い、少し語ってみませんか？",
        view=RPView(),
        allowed_mentions=discord.AllowedMentions.none()
    )

@bot.command()
async def rpclear(ctx):
    global target_channel_id
    target_channel_id = None
    await ctx.send("対象チャンネル設定を解除しました。")

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.bot:
        return
    if target_channel_id is None or message.channel.id != target_channel_id:
        return
    if message.content.startswith("!rp"):
        return

    global last_prompt_message
    if last_prompt_message:
        try:
            await last_prompt_message.delete()
        except discord.NotFound:
            pass
    last_prompt_message = await message.channel.send(
        "今の気持ちや想い、少し語ってみませんか？",
        view=RPView(),
        allowed_mentions=discord.AllowedMentions.none()
    )

# 並列起動（Flask + Discord Bot）
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
