import json
from typing import Union, Dict

import requests
import os
from dotenv import load_dotenv
from util.util import get_env_var, get_notion_url, get_discord_event_url, get_discord_channels_url
from datetime import datetime, timezone, timedelta


def check_valid(func):
    def wrapper(self, *args, **kwargs):
        if not self.valid:
            raise ValueError(f"{self.__class__.__name__} instance is not valid.")
        return func(self, *args, **kwargs)

    return wrapper


class Bot:
    def __init__(self):
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
            if not os.path.exists(self.config_file):
                self.config = {"last_query_time": "2020-01-01T00:00:00.000Z",
                               "meeting_dict": {}}
                self.update_config()

            with open(self.config_file, "r") as file:
                self.config = json.load(file)

            self.valid = True

        except Exception as e:
            print(e)

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
                self.update_config()

            with open(self.config_file, "r") as file:
                self.config = json.load(file)

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

    def process_meetings(self):
        """Process meetings from Notion and create Discord events."""
        current_time = datetime.now()

        meetings = self.fetch_new_meetings()
        meeting_dict = self.config["meeting_dict"]
        print(len(meetings))
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
            attendees = properties.get("Attendees", {}).get("people", [])
            attendees = [person.get("name", "Unknown") for person in attendees]
            meeting_type_name = properties.get("Type", {}).get("select", {}).get("name", "Unknown")
            meeting_type = 2
            if meeting_type_name == "External":
                meeting_type = 3
                location = properties.get("External link", {})["url"]
                if not location:
                    location = "Placeholder link"
            elif meeting_type_name == "Team":
                location = self.get_channel_id_from_name("Dev")
            elif meeting_type_name == "Design":
                location = self.get_channel_id_from_name("Design")
            elif meeting_type_name == "Programming":
                location = self.get_channel_id_from_name("Programming - The Git Pit")
            elif meeting_type_name == "Art":
                location = self.get_channel_id_from_name("Art")
            elif meeting_type_name == "Audio":
                location = self.get_channel_id_from_name("Audio")
            else:
                continue

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

    def get_channel_id_from_name(self, channel_name):
        """
        Fetch the ID of a Discord channel by its name.

        :param guild_id: The ID of the Discord guild (server)
        :param channel_name: The name of the channel to find
        :param bot_token: Your Discord bot token
        :return: The channel ID if found, or None
        """
        if not channel_name:
            return None

        url = get_discord_channels_url(self.guild_id)

        response = requests.get(url, headers=self.discord_headers)
        if response.status_code == 200:
            channels = response.json()
            for channel in channels:
                if channel["name"] == channel_name and channel["type"] == 2:
                    return channel["id"]
            print(f"Channel with name '{channel_name}' not found.")
            return None
        else:
            print(f"Error fetching channels: {response.status_code}, {response.json()}")
            return None

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

    def clean_meeting_dict(self, current_time):
        meeting_dict: Dict = self.config["meeting_dict"]
        for meeting_id, discord_event_info in meeting_dict.items():
            if datetime.fromisoformat(discord_event_info["discord_event_time"]).replace(tzinfo=None) < current_time:
                meeting_dict.pop(meeting_id)

    def update_config(self):
        with open(self.config_file, "w") as file:
            json.dump(self.config, file, indent=4)


if __name__ == "__main__":
    bot = Bot()
    # bot.reset(True)
    bot.process_meetings()
