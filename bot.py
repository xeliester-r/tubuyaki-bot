import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from flask import Flask
import threading

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
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url)
        await interaction.channel.send(embed=embed, view=ReplyView(embed, interaction.user.display_name))
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
    def __init__(self, original_embed: discord.Embed, original_author: str):
        super().__init__(title="RP返信")
        self.input = discord.ui.TextInput(label="返信内容", style=discord.TextStyle.short)
        self.original_embed = original_embed
        self.original_author = original_author
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        reply_embed = discord.Embed(
            description=self.input.value,
            color=discord.Color.blue()
        )
        reply_embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url)
        reply_embed.add_field(name="返信先", value=f"{self.original_author}: {self.original_embed.description}", inline=False)

        await interaction.channel.send(embed=reply_embed)
        await interaction.response.defer(ephemeral=True)


class RPView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 無効化されないように timeout を無効化

    @discord.ui.button(label="つぶやく", style=discord.ButtonStyle.primary, custom_id="rpbutton")
    async def rp_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RPModal())

class ReplyView(discord.ui.View):
    def __init__(self, original_embed: discord.Embed, original_author: str):
        super().__init__(timeout=None)
        self.original_embed = original_embed
        self.original_author = original_author

    @discord.ui.button(label="返信する", style=discord.ButtonStyle.secondary, custom_id="replybutton")
    async def reply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReplyModal(self.original_embed, self.original_author))


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
