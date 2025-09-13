'''
Created on 2025/09/13

@author: fflay
'''
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from flask import Flask
import threading

# .envからトークンを読み込む
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # ←キー名をRenderに合わせて修正

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
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

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

class RPView(discord.ui.View):
    def __init__(self, original_message):
        super().__init__(timeout=900)
        
        self.original_message = original_message

    @discord.ui.button(label="つぶやく", style=discord.ButtonStyle.primary, custom_id="rpbutton")
    async def rp_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RPModal())

    async def on_timeout(self):
        try:
            await self.original_message.edit(
                content="キャラやRPについてつぶやこう！",
                view=RPView(self.original_message)
            )
        except Exception as e:
            print(f"再表示エラー: {e}")


@bot.command()
async def rp(ctx):
    # 最初は仮のViewを送信（Noneを渡す）
    message = await ctx.send("キャラやRPについてつぶやこう！", view=RPView())
    # 送信後に、Viewにメッセージを渡して再設定
    await message.edit(view=RPView(message))


# 並列起動
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
