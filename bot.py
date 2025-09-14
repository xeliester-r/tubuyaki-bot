import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from flask import Flask
import threading

from collections import defaultdict
import time

reply_history = defaultdict(list)  # key: (user1_id, user2_id), value: list of dicts
target_channel_ids = {}         # key: guild.id, value: channel.id
last_prompt_messages = {}  # key: channel.id, value: message
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

def is_channel_isolated(channel_id, pair):
    history = reply_history.get((channel_id, *pair), [])
    authors = set(entry["author"].id for entry in history)
    return authors.issubset(set(pair))

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
        await interaction.response.send_message(content="\u200b", ephemeral=True)

        channel_id = interaction.channel.id
        if last_prompt_messages.get(channel_id):
            try:
                await last_prompt_messages[channel_id].delete()
            except discord.NotFound:
                pass

        last_prompt_messages[channel_id] = await interaction.channel.send(
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
        # スレッド化の前に、親チャンネルを明示的に取得
        original_channel = interaction.channel.parent if isinstance(interaction.channel, discord.Thread) else interaction.channel
        channel_id = original_channel.id  # ←履歴キーにも使う
        pair = tuple(sorted([interaction.user.id, self.original_user.id]))
        now = time.time()
        reply_history[(channel_id, *pair)] = [
              r for r in reply_history[(channel_id, *pair)] if now - r["timestamp"] < REPLY_WINDOW
        ]
        reply_history[(channel_id, *pair)].append({
            "timestamp": now,
            "author": interaction.user,
            "content": self.input.value,
            "original_user": self.original_user,
            "original_embed": self.original_embed
        })

        reply_count = len(reply_history[(channel_id, *pair)])

        # 色判定
        if reply_count >= 5:
            color = discord.Color.red()
        elif reply_count >= 3:
            color = discord.Color.orange()
        else:
            color = discord.Color.blue()

        # ❶ Embed構築（返信）
        reply_embed = discord.Embed(
            description=f"↳ {self.original_embed.description}",
            color=color
        )
        avatar_url = interaction.user.avatar.url if interaction.user.avatar else None
        reply_embed.set_author(name=interaction.user.display_name, icon_url=avatar_url)
        reply_embed.add_field(name="返信", value=f"↳ {self.input.value}", inline=False)

        # ❷ 通常チャンネルに返信を送信
        await interaction.channel.send(
            content=f"{self.original_user.mention}",
            embed=reply_embed,
            view=ReplyView(reply_embed, interaction.user)
        )

        # スレッド化条件判定
        should_thread_by_time = reply_count >= REPLY_THRESHOLD
        should_thread_by_isolation = (
            reply_count >= 10 and
            is_channel_isolated(channel_id, pair)
        )

        should_thread = should_thread_by_time or should_thread_by_isolation

        if should_thread:
            # ❸ スレッド作成
            thread = await interaction.channel.create_thread(
                name=f"RP会話：{interaction.user.display_name}↔{self.original_user.display_name}",
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60
            )

            # ❹ 履歴投稿（時系列順）
            for entry in sorted(reply_history[(channel_id, *pair)], key=lambda x: x["timestamp"]):
                embed = discord.Embed(
                    description=f"↳ {entry['original_embed'].description}",
                    color=color
                )
                avatar_url = entry["author"].avatar.url if entry["author"].avatar else None
                embed.set_author(name=entry["author"].display_name, icon_url=avatar_url)
                embed.add_field(name="返信", value=f"↳ {entry['content']}", inline=False)

                await thread.send(
                    content=f"{entry['original_user'].mention}",
                    embed=embed,
                    view=ReplyView(embed, entry["author"])
                )

            # ❺ Botの案内文（1回だけ）
            await thread.send(
                content=f"{interaction.user.mention} {self.original_user.mention}\n会話が盛り上がってたから、こっそり専用スレッド作ったよ。\nここはふたりの秘密基地ってことで。続き、楽しみにしてるね！",
                allowed_mentions=discord.AllowedMentions(users=True)
            )

            await thread.add_user(self.original_user)
            await thread.add_user(interaction.user)

        # スレッド化条件の判定・実行
        # スレッド化の有無に関係なく、案内メッセージは元のチャンネルに送る
        target_channel = original_channel.parent if isinstance(original_channel, discord.Thread) else original_channel

        if last_prompt_messages.get(target_channel.id):
            try:
                await last_prompt_messages[target_channel.id].delete()
            except discord.NotFound:
                pass

        last_prompt_messages[target_channel.id] = await target_channel.send(
            "今の気持ちや想い、少し語ってみませんか？",
            view=RPView(),
            allowed_mentions=discord.AllowedMentions.none()
        )
        
        await interaction.response.send_message(content="\u200b", ephemeral=True)

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
    channel_id = ctx.channel.id
    target_channel_ids[channel_id] = ctx.channel.id
    last_prompt_messages[channel_id] = await ctx.send(
        "今の気持ちや想い、少し語ってみませんか？",
        view=RPView(),
        allowed_mentions=discord.AllowedMentions.none()
    )

@bot.command()
async def rpclear(ctx):
    channel_id = ctx.channel.id
    target_channel_ids.pop(channel_id, None)
    last_prompt_messages.pop(channel_id, None)
    await ctx.send("対象チャンネル設定を解除しました。")

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.bot:
        return

    channel_id = message.channel.id
    if channel_id not in target_channel_ids:
        return
    if message.channel.id != target_channel_ids[channel_id]:
        return
    if message.content.startswith("!rp"):
        return

    if last_prompt_messages.get(channel_id):
        try:
            await last_prompt_messages[channel_id].delete()
        except discord.NotFound:
            pass

    last_prompt_messages[channel_id] = await message.channel.send(
        "今の気持ちや想い、少し語ってみませんか？",
        view=RPView(),
        allowed_mentions=discord.AllowedMentions.none()
    )


# 並列起動（Flask + Discord Bot）
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
