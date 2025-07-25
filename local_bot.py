import json
from typing import Union, Dict

import discord
import requests
import os
import asyncio

from discord.ext import commands, tasks
from notion_client import Client as NotionClient
from dotenv import load_dotenv
from util.util import get_env_var, get_notion_url, get_discord_event_url
from datetime import datetime, timezone, timedelta

EXCLUDED_COMMANDS = ["help", "about"]


class SprintDashboardView(discord.ui.View):
    def __init__(self, sprint_id: str, completed_tasks: list, in_progress_tasks: list, blocked_tasks: list):
        super().__init__(timeout=300)
        self.sprint_id = sprint_id
        self.completed_tasks = completed_tasks
        self.in_progress_tasks = in_progress_tasks
        self.blocked_tasks = blocked_tasks
        
        # Add the direct link button
        if sprint_id:
            base_url = f"https://www.notion.so/{sprint_id.replace('-', '')}"
            self.add_item(discord.ui.Button(
                label="Open Full Sprint",
                style=discord.ButtonStyle.link,
                emoji="📝",
                url=base_url
            ))
    
    @discord.ui.button(label="Completed Tasks", style=discord.ButtonStyle.success, emoji="✅")
    async def completed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.completed_tasks:
            await interaction.response.send_message("No completed tasks in this sprint.", ephemeral=True)
            return
        
        view = TaskListView(self.completed_tasks, f"Completed Tasks ({len(self.completed_tasks)})", "✅", dashboard_view=self)
        
        embed = view.get_embed()
        embed.color = discord.Color.green()
        
        # Send as ephemeral so only the user who clicked sees it
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="In Progress Tasks", style=discord.ButtonStyle.primary, emoji="🔄")
    async def in_progress_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.in_progress_tasks:
            await interaction.response.send_message("No tasks in progress in this sprint.", ephemeral=True)
            return
        
        view = TaskListView(self.in_progress_tasks, f"In Progress Tasks ({len(self.in_progress_tasks)})", "🔄", dashboard_view=self)
        
        embed = view.get_embed()
        embed.color = discord.Color.blue()
        
        # Send as ephemeral so only the user who clicked sees it
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Blocked Tasks", style=discord.ButtonStyle.danger, emoji="🚫")
    async def blocked_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.blocked_tasks:
            await interaction.response.send_message("No blocked tasks in this sprint.", ephemeral=True)
            return
        
        view = TaskListView(self.blocked_tasks, f"Blocked Tasks ({len(self.blocked_tasks)})", "🚫", dashboard_view=self)
        
        embed = view.get_embed()
        embed.color = discord.Color.red()
        
        # Send as ephemeral so only the user who clicked sees it
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class TaskListView(discord.ui.View):
    def __init__(self, tasks: list, title: str, emoji: str, page: int = 0, dashboard_view: SprintDashboardView = None):
        super().__init__(timeout=300)
        self.tasks = tasks
        self.title = title
        self.emoji = emoji
        self.page = page
        self.tasks_per_page = 10
        self.dashboard_view = dashboard_view
        
        self.update_buttons()
    
    def update_buttons(self):
        self.clear_items()
        
        # Add navigation buttons if needed
        if len(self.tasks) > self.tasks_per_page:
            if self.page > 0:
                prev_button = discord.ui.Button(
                    label="◀ Previous",
                    style=discord.ButtonStyle.secondary,
                    custom_id="prev"
                )
                prev_button.callback = self.previous_page
                self.add_item(prev_button)
            
            start_idx = self.page * self.tasks_per_page
            end_idx = min(start_idx + self.tasks_per_page, len(self.tasks))
            
            if end_idx < len(self.tasks):
                next_button = discord.ui.Button(
                    label="Next ▶",
                    style=discord.ButtonStyle.secondary,
                    custom_id="next"
                )
                next_button.callback = self.next_page
                self.add_item(next_button)
        
        # # Add back button (always present)
        # back_button = discord.ui.Button(
        #     label="← Back to Sprint Overview",
        #     style=discord.ButtonStyle.primary,
        #     custom_id="back"
        # )
        # back_button.callback = self.back_to_overview
        # self.add_item(back_button)
    
    def get_embed(self):
        start_idx = self.page * self.tasks_per_page
        end_idx = min(start_idx + self.tasks_per_page, len(self.tasks))
        page_tasks = self.tasks[start_idx:end_idx]
        
        # Create the embed
        embed = discord.Embed(
            title=f"{self.emoji} {self.title}",
            color=discord.Color.blue()
        )
        
        # Add pagination info if needed
        if len(self.tasks) > self.tasks_per_page:
            total_pages = (len(self.tasks) - 1) // self.tasks_per_page + 1
            embed.description = f"Page {self.page + 1} of {total_pages}"
        
        # Add tasks to embed as clickable links
        if page_tasks:
            current_field_text = ""
            field_count = 1
            
            for i, task in enumerate(page_tasks, start=start_idx + 1):
                # Truncate task name to prevent overly long lines
                max_task_name_length = 60
                truncated_name = task['name'][:max_task_name_length]
                if len(task['name']) > max_task_name_length:
                    truncated_name += "..."
                
                # Create clickable link format
                task_link = f"[📄 {truncated_name}]({task['url']})"
                task_line = f"**{i}.** {task_link}"
                
                # Check if adding this task would exceed the 1024 character limit
                test_text = current_field_text + ("\n\n" if current_field_text else "") + task_line
                
                if len(test_text) > 1000:  # Leave some buffer
                    # Add current field and start a new one
                    field_name = "Tasks"
                    embed.add_field(
                        name=field_name,
                        value=current_field_text,
                        inline=False
                    )
                    current_field_text = task_line
                    field_count += 1
                else:
                    if current_field_text:
                        current_field_text += "\n\n" + task_line
                    else:
                        current_field_text = task_line
            
            # Add the final field
            if current_field_text:
                field_name = "Tasks"
                embed.add_field(
                    name=field_name,
                    value=current_field_text,
                    inline=False
                )
        else:
            embed.add_field(
                name="Tasks",
                value="No tasks found.",
                inline=False
            )
        
        return embed
    
    async def previous_page(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            embed = self.get_embed()
            await interaction.response.edit_message(embed=embed, view=self, ephemeral=True)
    
    async def next_page(self, interaction: discord.Interaction):
        max_page = (len(self.tasks) - 1) // self.tasks_per_page
        if self.page < max_page:
            self.page += 1
            self.update_buttons()
            embed = self.get_embed()
            await interaction.response.edit_message(embed=embed, view=self, ephemeral=True)
    
    # async def back_to_overview(self, interaction: discord.Interaction):
    #     await interaction.response.defer()
    #     if self.dashboard_view:
    #         # Create a new ephemeral overview instead of editing the original
    #         embed = discord.Embed(
    #             title=f"Sprint Overview",
    #             description="Click a button below to view tasks in that category:",
    #             color=discord.Color.blue()
    #         )
            
    #         embed.add_field(
    #             name="✅ Completed",
    #             value=f"{len(self.dashboard_view.completed_tasks)} tasks",
    #             inline=True
    #         )
            
    #         embed.add_field(
    #             name="🔄 In Progress", 
    #             value=f"{len(self.dashboard_view.in_progress_tasks)} tasks",
    #             inline=True
    #         )
            
    #         embed.add_field(
    #             name="🚫 Blocked",
    #             value=f"{len(self.dashboard_view.blocked_tasks)} tasks", 
    #             inline=True
    #         )
            
    #         await interaction.response.edit_message(embed=embed, view=self.dashboard_view)
    #     else:
    #         await interaction.response.send_message("No Overview", ephemeral=True)


class SprintUpdateView(discord.ui.View):
    def __init__(self, sprint_id: str):
        super().__init__(timeout=300)
        self.sprint_id = sprint_id
        
        if self.sprint_id:
            sprint_url = f"https://www.notion.so/{self.sprint_id.replace('-', '')}"
            self.add_item(discord.ui.Button(
                label="Open Sprint in Notion",
                style=discord.ButtonStyle.link,
                emoji="📝",
                url=sprint_url
            ))

class LocalBot:
    def __init__(self, command_prefix="c!"):
        self.valid = False

        intents = discord.Intents.all()

        self.command_prefix = command_prefix
        self.bot = commands.Bot(command_prefix=command_prefix, intents=intents, help_command=None)

        try:
            load_dotenv()
            # Fetch required variables
            # self.notion_api_key = get_env_var("NOTION_API_KEY")
            self.calendar_id = get_env_var("CALENDAR_ID")
            self.bot_token = get_env_var("DISCORD_BOT_TOKEN")
            self.guild_id = get_env_var("GUILD_ID")
            self.notion_client = NotionClient(auth=get_env_var("NOTION_API_KEY"))

            # Notion and Discord configuration
            # self.notion_headers = {
            #     "Authorization": f"Bearer {self.notion_api_key}",
            #     "Content-Type": "application/json",
            #     "Notion-Version": "2022-06-28",
            # }
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
                # Ensure new config keys exist
                if "last_sprint_reminder" not in self.config:
                    self.config["last_sprint_reminder"] = None

            self.valid = True

        except Exception as e:
            print(e)

        self.add_listeners()
        self.add_commands()

        self.bot.check(self.global_check)
        
    @tasks.loop(hours=1)  # Check every hour
    async def weekly_sprint_check(self):
        """Check if it's Friday 6pm and send sprint updates"""
        try:        
            now = datetime.now()
            
            # Check if it's Friday (weekday 4) and between 6pm-7pm
            if now.weekday() == 4 and now.hour == 18:  # Friday at 6pm
                # Check if we already sent this week
                last_reminder = self.config.get('last_sprint_reminder')
                if last_reminder:
                    last_date = datetime.fromisoformat(last_reminder).date()
                    if last_date == now.date():
                        return  # Already sent today
                
                # Check if channel_dict and Update channel are configured
                if 'channel_dict' not in self.config:
                    print("No channel_dict configured for sprint automation")
                    return
                    
                if 'Update' not in self.config['channel_dict']:
                    print("No 'Update' channel configured in channel_dict")
                    return
                
                # Get the channel
                channel = self.bot.get_channel(int(self.config['channel_dict']['Update']))
                if not channel:
                    print(f"Sprint channel {self.config['channel_dict']['Update']} not found")
                    return
                
                print(f"Sending scheduled sprint update to {channel.name}")
                
                # Create a fake context for the commands
                class FakeContext:
                    def __init__(self, channel, bot):
                        self.channel = channel
                        self.bot = bot
                        self.guild = channel.guild
                        
                    async def send(self, *args, **kwargs):
                        return await self.channel.send(*args, **kwargs)
                
                fake_ctx = FakeContext(channel, self.bot)
                
                await self.get_sprint_dashboard(fake_ctx)
                
                await asyncio.sleep(2)
                await self.request_update(fake_ctx)
                
                self.config['last_sprint_reminder'] = now.isoformat()
                self.update_config()
                
        except Exception as e:
            print(f"Error in weekly sprint check: {e}")

    @weekly_sprint_check.before_loop
    async def before_weekly_sprint_check(self):
        """Wait until the bot is ready before starting the loop"""
        await self.bot.wait_until_ready()

    async def global_check(self, ctx):
        if not self.valid:
            raise commands.CheckFailure("The bot is not valid at the moment")

        if ctx.command.name in EXCLUDED_COMMANDS or (ctx.guild and ctx.author == ctx.guild.owner):
            return True

        allowed_roles = ["Dev Team"]
        if any(role.name in allowed_roles for role in ctx.author.roles):
            return True
        else:
            raise commands.CheckFailure("You do not have permission to use this command")

    def reset(self, hard: bool = False):
        self.valid = False

        try:
            load_dotenv()
            # Fetch required variables
            # self.notion_api_key = get_env_var("NOTION_API_KEY")
            self.calendar_id = get_env_var("CALENDAR_ID")
            self.bot_token = get_env_var("DISCORD_BOT_TOKEN")
            self.guild_id = get_env_var("GUILD_ID")
            self.notion_client = NotionClient(auth=get_env_var("NOTION_API_KEY"))

            # Notion and Discord configuration
            # self.notion_headers = {
            #     "Authorization": f"Bearer {self.notion_api_key}",
            #     "Content-Type": "application/json",
            #     "Notion-Version": "2022-06-28",
            # }
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
                    if "last_sprint_reminder" not in self.config:
                        self.config["last_sprint_reminder"] = None
            self.update_config()

            self.valid = True

        except Exception as e:
            print(e)

    def fetch_new_meetings(self):
        """Fetch new meetings from the Notion calendar."""
        response = self.notion_client.databases.query(
            database_id=self.calendar_id,
            filter={
                "timestamp": "last_edited_time",
                "last_edited_time": {
                    "after": self.config.get("last_query_time", "2020-01-01T00:00:00.000Z")
                }
            }
        )
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
            await ctx.send("Error fetching public IP Contact Bill or Cuneyd")

    async def request_update(self, ctx):
        try:
            # Find the Dev Team role to ping it properly
            dev_team_role = discord.utils.get(ctx.guild.roles, name="Dev Team")
            role_mention = dev_team_role.mention if dev_team_role else "@Dev Team"
            
            # Create the embed
            current_sprint_id = self.config.get('current_sprint_id')
            if not current_sprint_id:
                await ctx.send("No current sprint configured.")
                return
            
            database_info = self.notion_client.databases.retrieve(database_id=current_sprint_id)
            
            sprint_title = "Sprint"
            if database_info.get("title") and len(database_info["title"]) > 0:
                sprint_title = database_info["title"][0].get("text", {}).get("content", "Sprint")
            
            
            embed = discord.Embed(
                title=f"{sprint_title} Update",
                description=f"{role_mention} Please put in your updates",
                color=discord.Color.blue()
            )
            
            view = SprintUpdateView(self.config.get('current_sprint_id', ''))
            
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            print(e)
            await ctx.send("Error creating sprint update embed")

    async def start_new_sprint(self, ctx):
        # Temporarily disable this command
        await ctx.send("❌ This command is temporarily disabled due to issues. Please use `c!update_sprint_id` to manually set the current sprint.")
        return
        
        try:
            previous_sprint_id = self.config['current_sprint_id']
            previous_sprint = self.notion_client.databases.retrieve(database_id=previous_sprint_id)
            
            # Debug: print the parent structure to understand the issue
            print(f"Previous sprint parent structure: {previous_sprint['parent']}")
            
            # Extract sprint number from previous sprint title
            previous_title = ""
            if previous_sprint.get("title") and len(previous_sprint["title"]) > 0:
                previous_title = previous_sprint["title"][0].get("text", {}).get("content", "")
            
            # Parse the sprint number and increment it
            new_sprint_number = 1  # Default fallback
            if previous_title:
                import re
                # Look for "Sprint X" pattern and extract the number
                match = re.search(r'Sprint\s+(\d+)', previous_title, re.IGNORECASE)
                if match:
                    new_sprint_number = int(match.group(1)) + 1
                else:
                    # If no number found, try to extract any number from the title
                    numbers = re.findall(r'\d+', previous_title)
                    if numbers:
                        new_sprint_number = int(numbers[-1]) + 1
            
            new_sprint_title = f"Sprint {new_sprint_number}"
            print(f"Creating new sprint: {new_sprint_title} (previous was: {previous_title})")
            
            properties = previous_sprint["properties"]
            clean_properties = {
                key: value for key, value in properties.items()
                if value["type"] not in ("formula", "rollup", "created_time", "last_edited_time")
            }

            # Handle different parent types properly
            parent_info = previous_sprint["parent"]
            new_sprint = None
            
            if parent_info["type"] == "block_id":
                # For block_id parent, create the database directly as a block within the parent block
                try:
                    block_response = self.notion_client.blocks.children.append(
                        block_id=parent_info["block_id"],
                        children=[{
                            "type": "database",
                            "database": {
                                "title": [{
                                    "type": "text",
                                    "text": {"content": new_sprint_title}
                                }],
                                "properties": clean_properties
                            }
                        }]
                    )
                    # Get the database ID from the created block
                    if block_response["results"]:
                        new_sprint_block = block_response["results"][0]
                        if new_sprint_block["type"] == "database":
                            # For database blocks, the database ID is the block ID
                            new_sprint = {"id": new_sprint_block["id"]}
                            print(f"✅ Successfully created database in the same block location")
                    
                    if not new_sprint:
                        raise Exception("Failed to get database ID from block creation")
                        
                except Exception as block_error:
                    print(f"⚠️ Warning: Could not create in same block location: {block_error}")
                    print("Falling back to page-level creation...")
                    
                    # Fallback: create at page level
                    block = self.notion_client.blocks.retrieve(block_id=parent_info["block_id"])
                    if block["parent"]["type"] == "page_id":
                        parent_config = {"type": "page_id", "page_id": block["parent"]["page_id"]}
                    else:
                        parent_config = {"type": "workspace", "workspace": True}
                    
                    new_sprint = self.notion_client.databases.create(
                        parent=parent_config,
                        title=[{
                            "type": "text",
                            "text": {"content": new_sprint_title}
                        }],
                        properties=clean_properties
                    )
            else:
                # For page_id or workspace parents, use the regular database creation
                if parent_info["type"] == "page_id":
                    parent_config = {"type": "page_id", "page_id": parent_info["page_id"]}
                elif parent_info["type"] == "workspace":
                    parent_config = {"type": "workspace", "workspace": True}
                else:
                    parent_config = parent_info

                new_sprint = self.notion_client.databases.create(
                    parent=parent_config,
                    title=[{
                        "type": "text",
                        "text": {"content": new_sprint_title}
                    }],
                    properties=clean_properties
                )
            
            if not new_sprint or "id" not in new_sprint:
                raise Exception("Failed to create new sprint database")
                
            self.config['current_sprint_id'] = new_sprint["id"]
            
            
            await self.request_update(ctx)
            self.update_config()
            
            await ctx.send(f"Started sprint {new_sprint_title}")
        except Exception as e:
            print(f"Error in start_new_sprint: {e}")
            print(f"Error type: {type(e)}")
            await ctx.send(f"Error starting a new sprint: {str(e)}")

    async def get_sprint_dashboard(self, ctx):
        try:
            current_sprint_id = self.config.get('current_sprint_id')
            if not current_sprint_id:
                await ctx.send("No current sprint configured.")
                return

            # Get the database info to extract the title
            database_info = self.notion_client.databases.retrieve(database_id=current_sprint_id)
            sprint_title = "Sprint"
            if database_info.get("title") and len(database_info["title"]) > 0:
                sprint_title = database_info["title"][0].get("text", {}).get("content", "Sprint")

            # Query the current sprint database for all tasks
            response = self.notion_client.databases.query(
                database_id=current_sprint_id,
                sorts=[
                    {
                        "property": "Status",
                        "direction": "ascending"
                    }
                ]
            )

            tasks = response.get("results", [])
            
            # Organize tasks by status with proper format for buttons
            completed_tasks = []
            in_progress_tasks = []
            blocked_tasks = []

            for task in tasks:
                properties = task["properties"]
                
                # Get task name
                name_property = properties.get("Name", {}).get("title", [])
                task_name = " ".join([t["text"]["content"] for t in name_property if "text" in t]) if name_property else "Untitled"
                
                # Get task status
                status_property = properties.get("Status", {}).get("select")
                status = status_property.get("name", "Unknown") if status_property else "Unknown"
                
                # Get task owner(s)
                assigned_property = properties.get("Assigned To", {}).get("people", [])
                owners = [person.get("name", "Unknown") for person in assigned_property] if assigned_property else ["Unassigned"]
                owner_text = ", ".join(owners)
                
                # Create task data for buttons
                task_url = f"https://www.notion.so/{task['id'].replace('-', '')}"
                task_data = {
                    'name': f"{task_name} | {owner_text}",
                    'url': task_url
                }

                # Categorize by status
                if status.lower() == "complete":
                    completed_tasks.append(task_data)
                elif status.lower() == "in progress":
                    in_progress_tasks.append(task_data)
                elif status.lower() == "blocked":
                    blocked_tasks.append(task_data)

            # Create the main overview embed
            embed = discord.Embed(
                title=sprint_title,
                description="Click a button below to view tasks in that category:",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )

            embed.add_field(
                name="✅ Completed",
                value=f"{len(completed_tasks)} tasks",
                inline=True
            )
            
            embed.add_field(
                name="🔄 In Progress", 
                value=f"{len(in_progress_tasks)} tasks",
                inline=True
            )
            
            embed.add_field(
                name="🚫 Blocked",
                value=f"{len(blocked_tasks)} tasks", 
                inline=True
            )

            # Create the interactive dashboard view
            view = SprintDashboardView(
                current_sprint_id, 
                completed_tasks, 
                in_progress_tasks, 
                blocked_tasks
            )

            await ctx.send(embed=embed, view=view)

        except Exception as e:
            print(e)
            await ctx.send("Error getting sprint update")

    async def update_sprint_id(self, ctx, sprint_id):
        try:
            if not sprint_id:
                await ctx.send("No sprint id provided")
                return
            
            self.config['current_sprint_id'] = sprint_id
            self.update_config()
            await ctx.send(f"Updated current sprint to {sprint_id}")
        except Exception as e:
            print(e)
            await ctx.send(f"Error updating sprint id: {e}")

    async def get_about(self, ctx):
        await ctx.send("Welcome to Lunaboot Studio")

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
            # Start the sprint check loop when the bot is ready
            self.weekly_sprint_check.start()

        @self.bot.event
        async def on_command_error(ctx, error):
            """Handle command errors."""
            if isinstance(error, commands.CommandNotFound):
                await ctx.send(f"Command not found. Use `{self.bot.command_prefix}help` to see available commands.")
            elif isinstance(error, commands.CheckFailure):
                await ctx.send(str(error))
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

        @self.bot.command(name="about", help="Displays information about Lunaboot Studios")
        async def get_about(ctx):
            await self.get_about(ctx)

        @self.bot.command(name="sprint_dashboard", aliases=["sprint"], help="Display interactive sprint dashboard with scrollable task lists")
        async def sprint_dashboard(ctx):
            await self.get_sprint_dashboard(ctx)

        @self.bot.command(name="start_new_sprint", aliases=["start_sprint", "new_sprint"], help="[DISABLED] Start a new sprint - temporarily unavailable", disabled=True)
        async def start_new_sprint(ctx):
            await self.start_new_sprint(ctx)

        @self.bot.command(name="update_sprint_id", aliases=["update_sprint"], help="Update the current sprint id e.g. c!update_sprint_id 1234567890")
        async def update_sprint_id(ctx, *, sprint_id):
            await self.update_sprint_id(ctx, sprint_id)

        @self.bot.command(name="sprint_update", aliases=["update"], help="Post sprint update embed with role ping and button")
        async def sprint_update_post(ctx):
            await self.request_update(ctx)

        @self.bot.command(name="help", help="Displays the help information")
        async def custom_help(ctx):
            embed = discord.Embed(title="Bot Commands", description="Here are the commands you can use:",
                                  color=discord.Color.blue())

            # Define command categories
            sprint_commands = ["sprint_dashboard", "start_new_sprint", "update_sprint_id", "sprint_update"]
            server_commands = ["ip", "ipv6"]
            meeting_commands = ["meeting"]
            general_commands = ["about", "help"]

            # Group commands by category
            categorized_commands = {
                "🏃 Sprint Commands": [],
                "🖥️ Server Commands": [],
                "📅 Meeting Commands": [],
                "ℹ️ General Commands": []
            }

            for command in self.bot.commands:
                try:
                    if await command.can_run(ctx):  # Check if user has permission for the command
                        command_info = f"**c!{command.name}** - {command.help or 'No description'}"
                        
                        if command.name in sprint_commands:
                            categorized_commands["🏃 Sprint Commands"].append(command_info)
                        elif command.name in server_commands:
                            categorized_commands["🖥️ Server Commands"].append(command_info)
                        elif command.name in meeting_commands:
                            categorized_commands["📅 Meeting Commands"].append(command_info)
                        elif command.name in general_commands:
                            categorized_commands["ℹ️ General Commands"].append(command_info)
                        else:
                            categorized_commands["ℹ️ General Commands"].append(command_info)
                except commands.CheckFailure:
                    pass

            # Add fields for each category that has commands
            for category, commands in categorized_commands.items():
                if commands:  # Only add if there are commands in this category
                    embed.add_field(
                        name=category,
                        value="\n".join(commands),
                        inline=False
                    )

            await ctx.send(embed=embed)

    def run(self):
        """Run the bot."""
        try:
            self.bot.run(self.bot_token)
        finally:
            if hasattr(self, 'weekly_sprint_check'):
                self.weekly_sprint_check.cancel()


if __name__ == "__main__":
    bot = LocalBot()
