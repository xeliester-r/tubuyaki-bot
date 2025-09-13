import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from flask import Flask
import threading
from datetime import datetime
import asyncio
import traceback

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

def get_prompt():
    hour = datetime.now().hour
    if 0 <= hour < 6:
        return "静かな夜に、少し語ってみませんか？"
    elif 6 <= hour < 18:
        return "今の気持ちや想い、少し語ってみませんか？"
    else:
        return "今日の終わりに、少しだけ言葉を紡いでみませんか？"

# Discord Botの設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
latest_rp_message = {}
latest_rp_message_id = {}
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
            if self.original_message:
                await self.original_message.edit(
                    content="今の気持ちや想い、少し語ってみませんか？",
                    view=RPView(self.original_message)
                )
        except Exception as e:
            print(f"[再表示エラー] {e}")
            traceback.print_exc()

@bot.command()
async def rp(ctx):
    message = await ctx.send(
        get_prompt(),
        allowed_mentions=discord.AllowedMentions.none()
    )
    await message.edit(view=RPView(message))
    latest_rp_message[ctx.channel.id] = message
    latest_rp_message_id[ctx.channel.id] = message.id
    print(f"[rp] 案内文登録: id={message.id} | channel={ctx.channel.id}")

@bot.event
async def on_message(message):
    try:
        await bot.process_commands(message)
        print(f"[on_message] author={message.author} | id={message.id} | content={message.content}")

        if message.author.bot:
            return
        if message.content.startswith("!rp"):
            return
        if message.channel.id in latest_rp_message_id:
            if message.id == latest_rp_message_id[message.channel.id]:
                return

        await asyncio.sleep(0.2)

        if message.channel.id in latest_rp_message:
            old_msg = latest_rp_message.get(message.channel.id)
            if old_msg is None:
                print("[削除スキップ] 案内文が None です")
            elif old_msg.deletable:
                await old_msg.delete()
                print(f"[削除成功] id={old_msg.id}")
            else:
                print(f"[削除不可] id={old_msg.id} は削除できません")

            new_msg = await message.channel.send(
                get_prompt(),
                allowed_mentions=discord.AllowedMentions.none()
            )
            await new_msg.edit(view=RPView(new_msg))
            latest_rp_message[message.channel.id] = new_msg
            latest_rp_message_id[message.channel.id] = new_msg.id
            print(f"[再投稿] id={new_msg.id}")
    except Exception as e:
        print(f"[on_messageエラー] {e}")
        traceback.print_exc()

# 並列起動
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
