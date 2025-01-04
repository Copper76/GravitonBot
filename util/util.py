import os


def get_env_var(key: str) -> str:
    val = os.getenv(key)

    if val is None:
        raise ValueError(f"Environment Variable {key} doesn't exist")

    return val


def get_notion_url(page_id: str) -> str:
    return f"https://api.notion.com/v1/databases/{page_id}/query"


def get_discord_base_url(guild_id: str) -> str:
    return f"https://discord.com/api/v10/guilds/{guild_id}"


def get_discord_event_url(guild_id: str) -> str:
    return f"{get_discord_base_url(guild_id)}/scheduled-events"


def get_discord_channels_url(guild_id: str) -> str:
    return f"{get_discord_base_url(guild_id)}/channels"

