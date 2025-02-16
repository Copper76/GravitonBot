import json
from typing import Union, Dict

import discord
import requests
import os

from discord.ext import commands
from dotenv import load_dotenv
from util.util import get_env_var, get_notion_url, get_discord_event_url, get_discord_channels_url
from datetime import datetime, timezone, timedelta


def check_valid(func):
    def wrapper(self, *args, **kwargs):
        if not self.valid:
            raise ValueError(f"{self.__class__.__name__} instance is not valid.")
        return func(self, *args, **kwargs)

    return wrapper


class LocalBot:
    def __init__(self, command_prefix="c!"):
        self.valid = False

        intents = discord.Intents.all()

        self.command_prefix = command_prefix
        self.bot = commands.Bot(command_prefix=command_prefix, intents=intents)

        try:
            load_dotenv()
            # Fetch required variables
            self.notion_api_key = get_env_var("NOTION_API_KEY")
            self.calendar_id = get_env_var("CALENDAR_ID")
            self.bot_token = get_env_var("DISCORD_BOT_TOKEN")
            self.guild_id = get_env_var("GUILD_ID")

            # Notion and Discord configuration
            self.notion_headers = {
                "Authorization": f"Bearer {self.notion_api_key}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            }
            self.discord_headers = {
                "Authorization": f"Bot {self.bot_token}",
                "Content-Type": "application/json",
            }

            self.config_file = get_env_var("CONFIG_FILE")
            if not os.path.exists(self.config_file):
                self.config = {"last_query_time": "2020-01-01T00:00:00.000Z",
                               "meeting_dict": {}}
                self.update_config()

            with open(self.config_file, "r") as file:
                self.config = json.load(file)

            self.valid = True

        except Exception as e:
            print(e)

        self.add_listeners()
        self.add_commands()

    def reset(self, hard: bool = False):
        self.valid = False

        try:
            load_dotenv()
            # Fetch required variables
            self.notion_api_key = get_env_var("NOTION_API_KEY")
            self.calendar_id = get_env_var("CALENDAR_ID")
            self.bot_token = get_env_var("DISCORD_BOT_TOKEN")
            self.guild_id = get_env_var("GUILD_ID")

            # Notion and Discord configuration
            self.notion_headers = {
                "Authorization": f"Bearer {self.notion_api_key}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            }
            self.discord_headers = {
                "Authorization": f"Bot {self.bot_token}",
                "Content-Type": "application/json",
            }

            self.config_file = get_env_var("CONFIG_FILE")
            if (not os.path.exists(self.config_file)) or hard:
                self.config = {"last_query_time": "2020-01-01T00:00:00.000Z",
                               "meeting_dict": {}}
            else:
                with open(self.config_file, "r") as file:
                    self.config = json.load(file)
                    self.config["last_query_time"] = "2020-01-01T00:00:00.000Z"
                    self.config["Meeting_dict"] = {}
            self.update_config()

            self.valid = True

        except Exception as e:
            print(e)

    def fetch_new_meetings(self):
        """Fetch new meetings from the Notion calendar."""
        payload = {
            "filter": {
                "timestamp": "last_edited_time",
                "last_edited_time": {
                    "after": self.config.get("last_query_time", "2020-01-01T00:00:00.000Z")
                }
            },
        }
        response = requests.post(get_notion_url(self.calendar_id), headers=self.notion_headers, json=payload)
        if response.status_code == 200:
            self.config["last_query_time"] = datetime.now(timezone.utc).isoformat()
            self.update_config()
            return response.json().get("results", [])
        else:
            print(f"Error fetching Notion data: {response.status_code}")
            print(response.text)
            return []

    def modify_discord_event(self, title: str, start_time: str, event_end: str, meeting_type: int, location: str = "",
                             event_id="") -> \
            Union[str, None]:
        """Create a scheduled event in Discord."""
        event_url = get_discord_event_url(self.guild_id)
        if event_id:
            event_url = '/'.join([event_url, event_id])
        print(event_url)

        # Convert Notion date to ISO format for Discord
        event_start = datetime.fromisoformat(start_time).astimezone(timezone.utc).isoformat()

        event_data = {
            "name": title,
            "scheduled_start_time": event_start,
            "scheduled_end_time": event_end,
            "privacy_level": 2,
            "entity_type": meeting_type
        }

        if meeting_type == 2:
            event_data["channel_id"] = location
        else:
            event_data["entity_metadata"] = {
                "location": location
            }

        print(event_data)
        if event_id:
            response = requests.patch(event_url, headers=self.discord_headers, json=event_data)
        else:
            response = requests.post(event_url, headers=self.discord_headers, json=event_data)
        if response.status_code == 200:
            print(f"Event '{title}' created successfully!")
            return response.json()["id"]
        else:
            print(f"Error creating event: {response.status_code}, {response.text}")
            return None

    @check_valid
    async def process_meetings(self):
        """Process meetings from Notion and create Discord events."""
        current_time = datetime.now()

        meetings = self.fetch_new_meetings()
        meeting_dict = self.config["meeting_dict"]

        for meeting in meetings:
            properties = meeting["properties"]
            event_time = properties["Event time"]["date"]
            start_time = event_time["start"]
            end_time = event_time["end"]
            if not end_time:
                time_object = datetime.fromisoformat(start_time.replace("Z", "+00:00")).replace(tzinfo=None)
                time_object = time_object + timedelta(hours=1)
                end_time = time_object.isoformat()  # default to one hour if not specified
            else:
                time_object = datetime.fromisoformat(end_time.replace("Z", "+00:00")).replace(tzinfo=None)
            # no point dealing with past event
            if time_object < current_time:
                continue

            title = ""
            title_property = properties.get("Name", {}).get("title", [])
            if title_property:
                title = " ".join([t["text"]["content"] for t in title_property if "text" in t])
            meeting_type_name = properties.get("Type", {}).get("select", {}).get("name", "Unknown")
            meeting_type = 2
            if meeting_type_name == "External":
                meeting_type = 3
                location = properties.get("External link", {})["url"]
                if not location:
                    location = "Placeholder link"
            else:
                location = self.config["channel_dict"][meeting_type_name]

            meeting_id = meeting["id"]
            discord_event_id = ""
            if meeting_id in meeting_dict and datetime.fromisoformat(
                    meeting_dict[meeting_id]["discord_event_time"]).replace(tzinfo=None) > current_time:
                discord_event = self.get_scheduled_event(meeting_dict[meeting_id]["discord_event_id"])
                if discord_event:
                    discord_event_id = meeting_dict[meeting_id]["discord_event_id"]
            discord_event_id = self.modify_discord_event(title, start_time, end_time, meeting_type, location,
                                                         discord_event_id)

            if discord_event_id:
                self.config["meeting_dict"][meeting_id] = {"discord_event_id": discord_event_id,
                                                           "discord_event_time": start_time.replace("Z", "+00:00")}

        self.clean_meeting_dict(current_time)
        self.update_config()

    def get_scheduled_event(self, event_id):
        """Fetch a specific scheduled event by its ID."""
        url = f"{get_discord_event_url(self.guild_id)}/{event_id}"

        response = requests.get(url, headers=self.discord_headers)
        if response.status_code == 200:
            event = response.json()
            return event
        else:
            print(f"Error fetching event: {response.status_code}, {response.json()}")
            return None

    async def get_ip(self, ctx, v4=True):
        try:
            if (v4):
                received_ip = requests.get("https://api4.ipify.org?format=json").json()['ip']
            else:
                received_ip = requests.get("https://ifconfig.me").text.strip()
            await ctx.send(received_ip)
        except Exception as e:
            await ctx.send(f"Error fetching public IP Contact Bill or Cuneyd")

    def clean_meeting_dict(self, current_time):
        meeting_dict: Dict = self.config["meeting_dict"]
        deleting_id = []
        for meeting_id, discord_event_info in meeting_dict.items():
            if datetime.fromisoformat(discord_event_info["discord_event_time"]).replace(tzinfo=None) < current_time:
                deleting_id.append(meeting_id)
        for meeting_id in deleting_id:
            meeting_dict.pop(meeting_id)

    def update_config(self):
        with open(self.config_file, "w") as file:
            json.dump(self.config, file, indent=4)

    def add_listeners(self):
        """Add event listeners to the bot."""

        @self.bot.event
        async def on_ready():
            print(f"Talking Cactus is ready! Logged in as {self.bot.user}. Bot uses {self.bot.command_prefix} as prefix.")

        @self.bot.event
        async def on_command_error(ctx, error):
            """Handle command errors."""
            if isinstance(error, commands.CommandNotFound):
                await ctx.send(f"Command not found. Use `{self.bot.command_prefix}help` to see available commands.")
            else:
                await ctx.send(f"An error occurred: {error}")

    def add_commands(self):
        @self.bot.command(name="meeting", aliases=["pull_meeting"], help="Updates discord event with Notion meetings.")
        async def pull_meeting(ctx):
            await self.process_meetings()
            await ctx.send("Discord Event Updated")

        @self.bot.command(name="ip", aliases=["cuneyd_ip"], help="Get the current public IP on Cuneyd's server, no need to bother Cuneyd")
        async def get_ip(ctx):
            await self.get_ip(ctx)

        @self.bot.command(name="ipv6", aliases=["cuneyd_ipv6"], help="Get v6 of IP on Cyneyd's server, not sure it's useful at the moment")
        async def get_ip(ctx):
            await self.get_ip(ctx,v4=False)

    def run(self):
        """Run the bot."""
        self.bot.run(self.bot_token)



if __name__ == "__main__":
    bot = LocalBot()
