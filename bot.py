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

class RPModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="RPつぶやき")
        self.input = discord.ui.TextInput(label="内容", style=discord.TextStyle.short)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(description=self.input.value, color=discord.Color.purple())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url)
        await interaction.channel.send(embed=embed)
        await interaction.response.defer(ephemeral=True)

        # 案内文を再投稿
        await interaction.channel.send(
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

@bot.command()
async def rp(ctx):
    global target_channel_id
    target_channel_id = ctx.channel.id  # 実行されたチャンネルを記録
    
    await ctx.send(
        "今の気持ちや想い、少し語ってみませんか？",
        view=RPView(),
        allowed_mentions=discord.AllowedMentions.none()
    )

@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.author.bot:
        return
    if target_channel_id is None or message.channel.id != target_channel_id:
        return
    await message.channel.send(
        "今の気持ちや想い、少し語ってみませんか？",
        view=RPView(),
        allowed_mentions=discord.AllowedMentions.none()
    )

# 並列起動（Flask + Discord Bot）
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
