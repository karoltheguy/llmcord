import asyncio
from base64 import b64encode
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any, Literal, Optional

import discord
from discord.app_commands import Choice
from discord.ext import commands
from discord.ui import LayoutView, TextDisplay
from dotenv import load_dotenv
import httpx
from openai import AsyncOpenAI

from config import get_config
from conversation import build_user_prefix, render_exchange, select_recent_context, should_chain_to_previous
from memory_commands import current_epoch, forget_memory, may_write_memory, read_memory
from memory_extract import DEFAULT_EXTRACTION_PROMPT, extract_memory
from memory_store import Claim, MemoryStore
from models import accepts_images, parse_provider_model
from permissions import is_allowed
from prompt import build_system_prompt

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)

EMBED_COLOR_COMPLETE = discord.Color.dark_green()
EMBED_COLOR_INCOMPLETE = discord.Color.orange()

STREAMING_INDICATOR = " ⚪"
EDIT_DELAY_SECONDS = 1

MAX_MESSAGE_NODES = 500


config = get_config()
curr_model = next(iter(config["models"]))

msg_nodes = {}
last_task_time = 0
background_tasks = set()
forget_epochs: dict[int, int] = {}

memory_store = MemoryStore(config.get("memory_db_path", "data/memory.db")) if config.get("memory_enabled", False) else None

intents = discord.Intents.default()
intents.message_content = True
activity = discord.CustomActivity(name=(config.get("status_message") or "github.com/jakobdylanc/llmcord")[:128])
discord_bot = commands.Bot(intents=intents, activity=activity, command_prefix=None)

httpx_client = httpx.AsyncClient()


@dataclass
class MsgNode:
    role: Literal["user", "assistant"] = "assistant"

    text: Optional[str] = None
    images: list[dict[str, Any]] = field(default_factory=list)

    has_bad_attachments: bool = False
    fetch_parent_failed: bool = False

    parent_msg: Optional[discord.Message] = None

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@discord_bot.tree.command(name="model", description="View or switch the current model")
async def model_command(interaction: discord.Interaction, model: str) -> None:
    global curr_model

    if model == curr_model:
        output = f"Current model: `{curr_model}`"
    else:
        if user_is_admin := interaction.user.id in config["permissions"]["users"]["admin_ids"]:
            curr_model = model
            output = f"Model switched to: `{model}`"
            logging.info(output)
        else:
            output = "You don't have permission to change the model."

    await interaction.response.send_message(output, ephemeral=(interaction.channel.type == discord.ChannelType.private))


@model_command.autocomplete("model")
async def model_autocomplete(interaction: discord.Interaction, curr_str: str) -> list[Choice[str]]:
    global config

    if curr_str == "":
        config = await asyncio.to_thread(get_config)

    choices = [Choice(name=f"◉ {curr_model} (current)", value=curr_model)] if curr_str.lower() in curr_model.lower() else []
    choices += [Choice(name=f"○ {model}", value=model) for model in config["models"] if model != curr_model and curr_str.lower() in model.lower()]

    return choices[:25]


@discord_bot.tree.command(name="memory", description="View what the bot has stored about you")
async def memory_command(interaction: discord.Interaction) -> None:
    if memory_store is None:
        await interaction.response.send_message("Memory is disabled on this bot.", ephemeral=True)
        return
    output = await read_memory(memory_store, interaction.user.id)
    await interaction.response.send_message(output, ephemeral=True)


class ForgetConfirmView(discord.ui.View):
    def __init__(self, user_id: int) -> None:
        super().__init__(timeout=60)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
        return False

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        output = await forget_memory(memory_store, self.user_id, forget_epochs)
        await interaction.response.edit_message(content=output, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled. Nothing was deleted.", view=None)


@discord_bot.tree.command(name="forget", description="Delete everything the bot has stored about you")
async def forget_command(interaction: discord.Interaction) -> None:
    if memory_store is None:
        await interaction.response.send_message("Memory is disabled on this bot.", ephemeral=True)
        return
    await interaction.response.send_message(
        "This will permanently delete everything I have stored about you. Are you sure?",
        view=ForgetConfirmView(interaction.user.id),
        ephemeral=True,
    )


@discord_bot.event
async def on_ready() -> None:
    if client_id := config.get("client_id"):
        logging.info(f"\n\nBOT INVITE URL:\nhttps://discord.com/oauth2/authorize?client_id={client_id}&permissions=412317191168&scope=bot\n")

    await discord_bot.tree.sync()


def make_openai_client(config: dict[str, Any], provider_slash_model: str) -> tuple[AsyncOpenAI, str, dict[str, Any]]:
    provider, model = parse_provider_model(provider_slash_model)
    provider_config = config["providers"][provider]
    return AsyncOpenAI(base_url=provider_config["base_url"], api_key=provider_config.get("api_key", "sk-no-key-required")), model, provider_config


def subjects_still_writable(subjects: set[int], epochs_at_start: dict[int, int]) -> bool:
    """True when no subject ran /forget during extraction.

    A subject missing from the snapshot was never present in the conversation,
    so its epoch cannot have moved and the claim stands.
    """
    return all(
        may_write_memory(forget_epochs, subject_id, epochs_at_start[subject_id])
        for subject_id in subjects
        if subject_id in epochs_at_start
    )


def extraction_subjects(participants: set[int] | None, user_id: int, bot_id: int | None) -> set[int]:
    return {pid for pid in (participants or set()) if pid != user_id and pid != bot_id}


async def read_known_claim_ids(user_id: int, subjects: set[int]) -> set[int]:
    if not subjects:
        return set()
    existing_claims = await memory_store.claims_by(user_id, subject_ids=subjects)
    return {claim.id for claim in existing_claims if claim.id is not None}


async def write_extracted_claims(user_id: int, subjects: set[int], claims: list, epochs_at_start: dict[int, int]) -> None:
    kept = [
        Claim(id=claim.id, source_id=user_id, subjects=claim.subjects, text=claim.text)
        for claim in claims
        if subjects_still_writable(claim.subjects, epochs_at_start)
    ]
    await memory_store.replace_claims(user_id, subjects, kept)


async def update_user_memory(
    config: dict[str, Any],
    user_id: int,
    exchange: str,
    participants: set[int] | None = None,
    bot_id: int | None = None,
) -> None:
    try:
        if not memory_store or not config.get("memory_model") or not exchange:
            return

        openai_client, model, _ = make_openai_client(config, config["memory_model"])

        subjects = extraction_subjects(participants, user_id, bot_id)
        epochs_at_start = {uid: current_epoch(forget_epochs, uid) for uid in {user_id} | subjects}

        existing_memory = await memory_store.get(user_id)
        known_claim_ids = await read_known_claim_ids(user_id, subjects)

        result = await extract_memory(
            client=openai_client,
            model=model,
            existing_memory=existing_memory,
            exchange=exchange,
            prompt=config.get("memory_extraction_prompt") or DEFAULT_EXTRACTION_PROMPT,
            max_chars=config.get("max_memory_text", 2000),
            speaker_id=user_id,
            bot_id=bot_id,
            known_claim_ids=known_claim_ids,
            max_claims=config.get("memory_max_claims_per_extraction", 20),
        )

        if not may_write_memory(forget_epochs, user_id, epochs_at_start[user_id]):
            return

        if result.self_memory is not None:
            await memory_store.upsert(user_id, result.self_memory)

        if subjects:
            await write_extracted_claims(user_id, subjects, result.claims, epochs_at_start)
    except Exception:
        logging.exception("Error while updating user memory")


def select_good_attachments(curr_msg: discord.Message) -> list:
    return [att for att in curr_msg.attachments if att.content_type and any(att.content_type.startswith(x) for x in ("text", "image"))]


def node_text(cleaned_content: str, curr_msg: discord.Message, good_attachments: list, attachment_responses: list) -> str:
    return "\n".join(
        ([cleaned_content] if cleaned_content else [])
        + ["\n".join(filter(None, (embed.title, embed.description, embed.footer.text))) for embed in curr_msg.embeds]
        + [component.content for component in curr_msg.components if component.type == discord.ComponentType.text_display]
        + [resp.text for att, resp in zip(good_attachments, attachment_responses) if att.content_type.startswith("text")]
    )


def node_images(good_attachments: list, attachment_responses: list) -> list:
    return [
        dict(type="image_url", image_url=dict(url=f"data:{att.content_type};base64,{b64encode(resp.content).decode('utf-8')}"))
        for att, resp in zip(good_attachments, attachment_responses)
        if att.content_type.startswith("image")
    ]


async def build_msg_node(curr_node: MsgNode, curr_msg: discord.Message) -> None:
    cleaned_content = curr_msg.content.removeprefix(discord_bot.user.mention).lstrip()

    good_attachments = select_good_attachments(curr_msg)

    attachment_responses = await asyncio.gather(*[httpx_client.get(att.url) for att in good_attachments])

    curr_node.role = "assistant" if curr_msg.author == discord_bot.user else "user"

    curr_node.text = node_text(cleaned_content, curr_msg, good_attachments, attachment_responses)

    curr_node.images = node_images(good_attachments, attachment_responses)

    if curr_node.role == "user" and (curr_node.text or curr_node.images):
        curr_node.text = build_user_prefix(
            user_id=curr_msg.author.id,
            display_name=getattr(curr_msg.author, "display_name", None),
        ) + curr_node.text

    curr_node.has_bad_attachments = len(curr_msg.attachments) > len(good_attachments)


def node_content(node: MsgNode, max_text: int, max_images: int):
    if node.images[:max_images]:
        return [dict(type="text", text=node.text[:max_text])] + node.images[:max_images]
    return node.text[:max_text]


def answered_author_id(prev_msg: discord.Message) -> int | None:
    prev_node = msg_nodes.get(prev_msg.id)
    prev_parent = prev_node.parent_msg if prev_node else None
    return prev_parent.author.id if prev_parent else None


async def chained_previous_msg(curr_msg: discord.Message, config: dict[str, Any]):
    if curr_msg.reference is not None:
        return None

    prev_msg_in_channel = ([m async for m in curr_msg.channel.history(before=curr_msg, limit=1)] or [None])[0]
    if not prev_msg_in_channel:
        return None

    if prev_msg_in_channel.type not in (discord.MessageType.default, discord.MessageType.reply):
        return None

    if should_chain_to_previous(
        is_dm=curr_msg.channel.type == discord.ChannelType.private,
        content_mentions_bot=discord_bot.user.mention in curr_msg.content,
        prev_author_id=prev_msg_in_channel.author.id,
        curr_author_id=curr_msg.author.id,
        bot_id=discord_bot.user.id,
        prev_answered_author_id=answered_author_id(prev_msg_in_channel),
        implicit_public_chaining=config.get("implicit_public_chaining", True),
    ):
        return prev_msg_in_channel

    return None


async def explicit_parent_msg(curr_msg: discord.Message):
    is_public_thread = curr_msg.channel.type == discord.ChannelType.public_thread
    parent_is_thread_start = is_public_thread and curr_msg.reference is None and curr_msg.channel.parent.type == discord.ChannelType.text

    if parent_msg_id := curr_msg.channel.id if parent_is_thread_start else getattr(curr_msg.reference, "message_id", None):
        if parent_is_thread_start:
            return curr_msg.channel.starter_message or await curr_msg.channel.parent.fetch_message(parent_msg_id)
        return curr_msg.reference.cached_message or await curr_msg.channel.fetch_message(parent_msg_id)

    return None


async def resolve_parent_msg(curr_node: MsgNode, curr_msg: discord.Message, config: dict[str, Any]) -> None:
    try:
        if prev_msg_in_channel := await chained_previous_msg(curr_msg, config):
            curr_node.parent_msg = prev_msg_in_channel
        else:
            parent_msg = await explicit_parent_msg(curr_msg)
            if parent_msg is not None:
                curr_node.parent_msg = parent_msg

    except (discord.NotFound, discord.HTTPException):
        logging.exception("Error fetching next message in the chain")
        curr_node.fetch_parent_failed = True


@discord_bot.event
async def on_message(new_msg: discord.Message) -> None:
    global last_task_time

    is_dm = new_msg.channel.type == discord.ChannelType.private

    if (not is_dm and discord_bot.user not in new_msg.mentions) or new_msg.author.bot:
        return

    role_ids = set(role.id for role in getattr(new_msg.author, "roles", ()))
    channel_ids = set(filter(None, (new_msg.channel.id, getattr(new_msg.channel, "parent_id", None), getattr(new_msg.channel, "category_id", None))))

    config = await asyncio.to_thread(get_config)

    allow_dms = config.get("allow_dms", True)

    if not is_allowed(
        user_id=new_msg.author.id,
        role_ids=role_ids,
        channel_ids=channel_ids,
        permissions=config["permissions"],
        is_dm=is_dm,
        allow_dms=allow_dms,
    ):
        return

    provider_slash_model = curr_model
    openai_client, model, provider_config = make_openai_client(config, provider_slash_model)

    model_parameters = config["models"].get(provider_slash_model, None)

    extra_headers = provider_config.get("extra_headers")
    extra_query = provider_config.get("extra_query")
    extra_body = (provider_config.get("extra_body") or {}) | (model_parameters or {}) or None

    accept_images = accepts_images(provider_slash_model)

    max_text = config.get("max_text", 100000)
    max_images = config.get("max_images", 5) if accept_images else 0
    max_messages = config.get("max_messages", 25)
    recent_limit = config.get("recent_context_messages", 0)
    recent_window_hours = config.get("recent_context_window_hours", 24)

    # Build message chain and set user warnings
    messages = []
    chain_ids = set()
    chain_entries = []
    participant_ids: set[int] = set()
    exchange_entries: list = []
    user_warnings = set()
    curr_msg = new_msg

    while curr_msg is not None and len(messages) < max_messages:
        curr_node = msg_nodes.setdefault(curr_msg.id, MsgNode())

        async with curr_node.lock:
            if curr_node.text is None:
                await build_msg_node(curr_node, curr_msg)
                await resolve_parent_msg(curr_node, curr_msg, config)

            content = node_content(curr_node, max_text, max_images)

            if content != "":
                messages.append(dict(content=content, role=curr_node.role))
                chain_ids.add(curr_msg.id)
                chain_entries.append((curr_msg.created_at, dict(content=content, role=curr_node.role)))
                if curr_node.role == "user":
                    participant_ids.add(curr_msg.author.id)
                exchange_entries.append((curr_msg.created_at, curr_node.role, curr_node.text[:max_text]))

            if len(curr_node.text) > max_text:
                user_warnings.add(f"⚠️ Max {max_text:,} characters per message")
            if len(curr_node.images) > max_images:
                user_warnings.add(f"⚠️ Max {max_images} image{'' if max_images == 1 else 's'} per message" if max_images > 0 else "⚠️ Can't see images")
            if curr_node.has_bad_attachments:
                user_warnings.add("⚠️ Unsupported attachments")
            if curr_node.fetch_parent_failed or (curr_node.parent_msg is not None and len(messages) == max_messages):
                user_warnings.add(f"⚠️ Only using last {len(messages)} message{'' if len(messages) == 1 else 's'}")

            curr_msg = curr_node.parent_msg

    if recent_limit > 0:
        try:
            history = [m async for m in new_msg.channel.history(before=new_msg, limit=recent_limit)]
        except (discord.NotFound, discord.HTTPException):
            logging.exception("Error fetching recent channel context")
            history = []

        by_id = {m.id: m for m in history}
        selected = select_recent_context(
            candidates=[(m.id, m.author.id, m.created_at, m.author.bot) for m in history],
            now=new_msg.created_at,
            window=timedelta(hours=recent_window_hours),
            limit=recent_limit,
            exclude_ids=chain_ids,
        )

        window_entries = []
        for entry_id, _author_id, created_at, _is_bot in selected:
            recent_msg = by_id[entry_id]
            if recent_msg.author.bot and recent_msg.author != discord_bot.user:
                continue
            if recent_msg.type not in (discord.MessageType.default, discord.MessageType.reply):
                continue

            recent_node = msg_nodes.setdefault(recent_msg.id, MsgNode())
            async with recent_node.lock:
                if recent_node.text is None:
                    await build_msg_node(recent_node, recent_msg)
                content = node_content(recent_node, max_text, max_images)

            if content != "":
                window_entries.append((created_at, dict(content=content, role=recent_node.role)))
                if not recent_msg.author.bot:
                    participant_ids.add(recent_msg.author.id)
                exchange_entries.append((created_at, recent_node.role, recent_node.text[:max_text]))

        merged = sorted(chain_entries + window_entries, key=lambda entry: entry[0], reverse=True)
        messages = [entry[1] for entry in merged[:max_messages]]

    logging.info(f"Message received (user ID: {new_msg.author.id}, attachments: {len(new_msg.attachments)}, conversation length: {len(messages)}):\n{new_msg.content}")

    memory = await memory_store.get(new_msg.author.id) if memory_store else None

    if system_prompt := build_system_prompt(config.get("system_prompt"), datetime.now().astimezone(), memory=memory, max_memory_text=config.get("max_memory_text", 2000)):
        messages.append(dict(role="system", content=system_prompt))

    # Generate and send response message(s) (can be multiple if response is long)
    curr_content = finish_reason = None
    response_msgs = []
    response_contents = []

    openai_kwargs = dict(model=model, messages=messages[::-1], stream=True, extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body)

    if use_plain_responses := config.get("use_plain_responses", False):
        max_message_length = 4000
    else:
        max_message_length = 4096 - len(STREAMING_INDICATOR)
        embed = discord.Embed.from_dict(dict(fields=[dict(name=warning, value="", inline=False) for warning in sorted(user_warnings)]))

    async def reply_helper(**reply_kwargs) -> None:
        reply_target = new_msg if not response_msgs else response_msgs[-1]
        response_msg = await reply_target.reply(**reply_kwargs)
        response_msgs.append(response_msg)

        msg_nodes[response_msg.id] = MsgNode(parent_msg=new_msg)
        await msg_nodes[response_msg.id].lock.acquire()

    try:
        async with new_msg.channel.typing():
            async for chunk in await openai_client.chat.completions.create(**openai_kwargs):
                if finish_reason is not None:
                    break

                if not (choice := chunk.choices[0] if chunk.choices else None):
                    continue

                finish_reason = choice.finish_reason

                prev_content = curr_content or ""
                curr_content = choice.delta.content or ""

                new_content = prev_content if finish_reason is None else (prev_content + curr_content)

                if response_contents == [] and new_content == "":
                    continue

                if start_next_msg := response_contents == [] or len(response_contents[-1] + new_content) > max_message_length:
                    response_contents.append("")

                response_contents[-1] += new_content

                if not use_plain_responses:
                    time_delta = datetime.now().timestamp() - last_task_time

                    ready_to_edit = time_delta >= EDIT_DELAY_SECONDS
                    msg_split_incoming = finish_reason is None and len(response_contents[-1] + curr_content) > max_message_length
                    is_final_edit = finish_reason is not None or msg_split_incoming
                    is_good_finish = finish_reason is not None and finish_reason.lower() in ("stop", "end_turn")

                    if start_next_msg or ready_to_edit or is_final_edit:
                        embed.description = response_contents[-1] if is_final_edit else (response_contents[-1] + STREAMING_INDICATOR)
                        embed.color = EMBED_COLOR_COMPLETE if msg_split_incoming or is_good_finish else EMBED_COLOR_INCOMPLETE

                        if start_next_msg:
                            await reply_helper(embed=embed, silent=True)
                        else:
                            await asyncio.sleep(EDIT_DELAY_SECONDS - time_delta)
                            await response_msgs[-1].edit(embed=embed)

                        last_task_time = datetime.now().timestamp()

            if use_plain_responses:
                for content in response_contents:
                    await reply_helper(view=LayoutView().add_item(TextDisplay(content=content)))

    except Exception:
        logging.exception("Error while generating response")

    for response_msg in response_msgs:
        msg_nodes[response_msg.id].text = "".join(response_contents)
        msg_nodes[response_msg.id].lock.release()

    if response_contents:
        exchange = render_exchange(
            entries=exchange_entries,
            limit=config.get("memory_extraction_max_messages", 8),
            assistant_reply="".join(response_contents),
        )
        task = asyncio.create_task(
            update_user_memory(
                config,
                new_msg.author.id,
                exchange,
                participants=participant_ids,
                bot_id=discord_bot.user.id if discord_bot.user else None,
            )
        )
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    # Delete oldest MsgNodes (lowest message IDs) from the cache
    if (num_nodes := len(msg_nodes)) > MAX_MESSAGE_NODES:
        for msg_id in sorted(msg_nodes.keys())[: num_nodes - MAX_MESSAGE_NODES]:
            async with msg_nodes.setdefault(msg_id, MsgNode()).lock:
                msg_nodes.pop(msg_id, None)


async def main() -> None:
    if memory_store:
        await memory_store.initialize()

    await discord_bot.start(config["bot_token"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
