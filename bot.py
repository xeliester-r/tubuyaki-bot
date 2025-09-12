'''
Created on 2025/09/13

@author: fflay
'''
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv  # ← 追加

# .envからトークンを読み込む
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# インテント設定（メッセージ内容とメンバー情報を取得可能に）
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Botの初期化
bot = commands.Bot(command_prefix="!", intents=intents)

# Modal（ポップアップ入力フォーム）の定義
class RPModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="RPつぶやき")
        self.input = discord.ui.TextInput(label="内容", style=discord.TextStyle.short)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(description=self.input.value, color=discord.Color.purple())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url)
        await interaction.channel.send(embed=embed)
        await interaction.response.defer(ephemeral=True)  # ← これで完全非表示
        # await interaction.response.send_message("投稿しました！", ephemeral=True)

# ボタンとそのイベント処理をViewにまとめる
class RPView(discord.ui.View):
    @discord.ui.button(label="入力", style=discord.ButtonStyle.primary, custom_id="rp_button")
    async def rp_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RPModal())

# コマンド定義：!rp でボタンを表示
@bot.command()
async def rp(ctx):
    await ctx.send("RPつぶやきを入力してください", view=RPView())

# Bot起動（トークンを貼り付け済みならこのままでOK）
bot.run(TOKEN)
