import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import string
import subprocess
from dotenv import load_dotenv
import asyncio
import datetime
import docker
import time
import logging
import psutil
import sqlite3

# ================= Logging =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('powerhost_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('PowerHostBot')

# ================= Config =================
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_IDS = {int(id_) for id_ in os.getenv('ADMIN_IDS', '1210291131301101618').split(',') if id_.strip()}
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', '1376177459870961694'))
DEFAULT_OS_IMAGE = os.getenv('DEFAULT_OS_IMAGE', 'ubuntu:22.04')
DB_FILE = 'powerhost.db'

# ================= Database =================
class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS vps_instances (
                token TEXT PRIMARY KEY,
                vps_id TEXT UNIQUE,
                container_id TEXT,
                memory INTEGER,
                cpu INTEGER,
                disk INTEGER,
                username TEXT,
                password TEXT,
                created_by TEXT,
                created_at TEXT,
                status TEXT DEFAULT 'running'
            )
        ''')
        self.conn.commit()

    def add_vps(self, vps_data):
        columns = ', '.join(vps_data.keys())
        placeholders = ', '.join('?' for _ in vps_data)
        self.cursor.execute(f'INSERT INTO vps_instances ({columns}) VALUES ({placeholders})', tuple(vps_data.values()))
        self.conn.commit()

    def get_user_vps(self, user_id):
        self.cursor.execute('SELECT * FROM vps_instances WHERE created_by = ?', (str(user_id),))
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in self.cursor.fetchall()]

    def get_vps_by_id(self, vps_id):
        self.cursor.execute('SELECT * FROM vps_instances WHERE vps_id = ?', (vps_id,))
        row = self.cursor.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in self.cursor.description]
        return dict(zip(columns, row))

    def remove_vps(self, vps_id):
        self.cursor.execute('DELETE FROM vps_instances WHERE vps_id = ?', (vps_id,))
        self.conn.commit()

    def update_vps(self, vps_id, updates):
        set_clause = ', '.join(f'{k} = ?' for k in updates)
        values = list(updates.values()) + [vps_id]
        self.cursor.execute(f'UPDATE vps_instances SET {set_clause} WHERE vps_id = ?', values)
        self.conn.commit()

# ================= Bot =================
class PowerHostBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = Database(DB_FILE)
        self.docker_client = docker.from_env()

    async def setup_hook(self):
        await self.tree.sync()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = PowerHostBot(command_prefix='/', intents=intents, help_command=None)

# ================= /help =================
@bot.tree.command(name="help", description="Show bot help")
async def help_command(interaction: discord.Interaction):
    text = (
        "**Available Commands:**\n\n"
        "📝 `/list` - List your VPS\n"
        "🚀 `/create_vps` - Create new VPS (admin only)\n"
        "🟢 `/start <id>` - Start VPS\n"
        "🛑 `/stop <id>` - Stop VPS\n"
        "❌ `/delete_vps <id>` - Delete VPS (admin only)\n"
        "🔁 `/regen_ssh <id>` - Regenerate SSH password\n"
        "📊 `/admin_stats` - Show system stats (admin only)\n"
        "🏓 `/ping` - Check latency\n"
    )
    embed = discord.Embed(title="✨ Bot Help ✨", description=text, color=discord.Color.red())
    await interaction.response.send_message(embed=embed)

# ================= /ping =================
@bot.tree.command(name="ping", description="Check bot latency")
async def ping_command(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="🏓 Pong!", description=f"Latency: {latency}ms", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

# ================= /create_vps =================
@bot.tree.command(name="create_vps", description="Create a new VPS (admin only)")
@app_commands.describe(memory="Memory in GB", cpu="CPU cores", disk="Disk in GB")
async def create_vps(interaction: discord.Interaction, memory: int, cpu: int, disk: int):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Only admins can use this!", ephemeral=True)
        return

    vps_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    username = interaction.user.name.lower()
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))

    container = bot.docker_client.containers.run(
        DEFAULT_OS_IMAGE,
        detach=True,
        tty=True,
        hostname=f"powerhost-{vps_id}",
        mem_limit=f"{memory}g"
    )

    vps_data = {
        "token": ''.join(random.choices(string.ascii_letters + string.digits, k=24)),
        "vps_id": vps_id,
        "container_id": container.id,
        "memory": memory,
        "cpu": cpu,
        "disk": disk,
        "username": username,
        "password": password,
        "created_by": str(interaction.user.id),
        "created_at": str(datetime.datetime.now()),
        "status": "running"
    }
    bot.db.add_vps(vps_data)

    embed = discord.Embed(title="🎉 VPS Created", color=discord.Color.green())
    embed.add_field(name="VPS ID", value=vps_id)
    embed.add_field(name="Username", value=username)
    embed.add_field(name="Password", value=f"||{password}||")
    embed.add_field(name="Docker ID", value=container.id[:12])
    try:
        await interaction.user.send(embed=embed)
    except:
        await interaction.response.send_message("⚠️ VPS created but DM failed!", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ VPS {vps_id} created and details sent to DM")

# ================= /list =================
@bot.tree.command(name="list", description="List your VPS")
async def list_vps(interaction: discord.Interaction):
    user_vps = bot.db.get_user_vps(interaction.user.id)
    if not user_vps:
        await interaction.response.send_message("You don't have any VPS.")
        return
    embed = discord.Embed(title="Your VPS Instances", color=discord.Color.blue())
    for vps in user_vps:
        embed.add_field(
            name=f"VPS {vps['vps_id']}",
            value=f"Status: {vps['status']} | Memory: {vps['memory']}GB | CPU: {vps['cpu']} cores",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

# ================= /start =================
@bot.tree.command(name="start", description="Start a VPS")
@app_commands.describe(vps_id="ID of VPS to start")
async def start_vps(interaction: discord.Interaction, vps_id: str):
    vps = bot.db.get_vps_by_id(vps_id)
    if not vps:
        await interaction.response.send_message("❌ VPS not found")
        return
    container = bot.docker_client.containers.get(vps['container_id'])
    container.start()
    bot.db.update_vps(vps_id, {"status": "running"})
    await interaction.response.send_message(f"🟢 VPS {vps_id} started")

# ================= /stop =================
@bot.tree.command(name="stop", description="Stop a VPS")
@app_commands.describe(vps_id="ID of VPS to stop")
async def stop_vps(interaction: discord.Interaction, vps_id: str):
    vps = bot.db.get_vps_by_id(vps_id)
    if not vps:
        await interaction.response.send_message("❌ VPS not found")
        return
    container = bot.docker_client.containers.get(vps['container_id'])
    container.stop()
    bot.db.update_vps(vps_id, {"status": "stopped"})
    await interaction.response.send_message(f"🛑 VPS {vps_id} stopped")

# ================= /delete_vps =================
@bot.tree.command(name="delete_vps", description="Delete a VPS (admin only)")
@app_commands.describe(vps_id="ID of VPS to delete")
async def delete_vps(interaction: discord.Interaction, vps_id: str):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Only admins can use this!", ephemeral=True)
        return
    vps = bot.db.get_vps_by_id(vps_id)
    if not vps:
        await interaction.response.send_message("❌ VPS not found")
        return
    try:
        container = bot.docker_client.containers.get(vps['container_id'])
        container.stop()
        container.remove()
    except:
        pass
    bot.db.remove_vps(vps_id)
    await interaction.response.send_message(f"✅ VPS {vps_id} deleted")

# ================= /regen_ssh =================
@bot.tree.command(name="regen_ssh", description="Regenerate SSH password for a VPS")
@app_commands.describe(vps_id="ID of VPS to update")
async def regen_ssh(interaction: discord.Interaction, vps_id: str):
    vps = bot.db.get_vps_by_id(vps_id)
    if not vps:
        await interaction.response.send_message("❌ VPS not found")
        return
    if str(interaction.user.id) != vps['created_by'] and interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ You don't own this VPS")
        return
    new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    bot.db.update_vps(vps_id, {"password": new_password})
    embed = discord.Embed(title="🔁 SSH Password Regenerated", color=discord.Color.orange())
    embed.add_field(name="VPS ID", value=vps_id)
    embed.add_field(name="New Password", value=f"||{new_password}||")
    try:
        await interaction.user.send(embed=embed)
        await interaction.response.send_message("✅ New SSH password sent to DM")
    except:
        await interaction.response.send_message("⚠️ Password regenerated but DM failed")

# ================= /admin_stats =================
@bot.tree.command(name="admin_stats", description="System statistics (Admin only)")
async def admin_stats(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Only admins can use this!", ephemeral=True)
        return
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    embed = discord.Embed(title="System Stats", color=discord.Color.orange())
    embed.add_field(name="CPU Usage", value=f"{cpu}%")
    embed.add_field(name="Memory", value=f"{mem.percent}% ({mem.used//(1024**3)}GB/{mem.total//(1024**3)}GB)")
    embed.add_field(name="Disk", value=f"{disk.percent}% ({disk.used//(1024**3)}GB/{disk.total//(1024**3)}GB)")
    await interaction.response.send_message(embed=embed)

# ================= Run Bot =================
bot.run(TOKEN)
