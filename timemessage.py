#!/usr/bin/env python3
"""
time_message_backup.py

Modern iMessage backup tool using Loguru, Rich, and beartype for Python 3.12+.

This script copies the chat database into a temporary working directory and,
for each contact, copies accessible attachments into temp before writing the
final backup to the output directory. The temporary working directory is
cleaned up automatically.

Usage:
    time_message_backup list --db ~/Library/Messages/chat.db
    time_message_backup backup --db ~/Library/Messages/chat.db --out ~/iMessage.backups
"""

import argparse
import json
import shutil
import sqlite3
import time
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Iterable

from loguru import logger as log
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from beartype import beartype


console = Console()


@dataclass
class Config:
    """Configuration for the backup run.

    Attributes:
        database: Path to the chat.db SQLite file.
        output: Path to directory where backups will be written.
        yes: Skip confirmation prompts.
        include_attachments: Whether to include attachments.
        loglevel: Log level for Loguru.
    """

    database: Path
    output: Path
    yes: bool = False
    include_attachments: bool = True
    loglevel: str = "INFO"


@beartype
@contextmanager
def sqlite_connection(path: Path):
    """Context manager yielding an sqlite3.Connection with row factory set.

    Args:
        path: Path to SQLite database file.

    Yields:
        sqlite3.Connection: open sqlite connection
    """
    conn = sqlite3.connect(path.as_posix())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@beartype
def normalize_guid(guid: str) -> str:
    """Strip common iMessage/SMS prefixes from a chat.guid.

    Args:
        guid: Raw guid value from chat table.

    Returns:
        Normalized contact identifier string.
    """
    for prefix in ("iMessage;+;", "iMessage;-;", "SMS;+;", "SMS;-;", "tel;+;"):
        if guid.startswith(prefix):
            return guid[len(prefix) :]
    return guid.replace("chat", "")


@beartype
def apple_time_to_unix_seconds(value: int | float) -> int:
    """Convert Apple/CoreData timestamp variants to Unix seconds.

    Apple epoch starts at 2001-01-01; some fields can be in ns/ms/secs.
    Heuristics are used to detect scale.

    Args:
        value: numeric timestamp from DB

    Returns:
        Unix timestamp (int seconds).
    """
    APPLE_TO_UNIX = 978307200
    v = float(value)
    if v > 1e15:
        v /= 1e9
    elif v > 1e12:
        v /= 1e3
    if v < 1e10:
        return int(round(v + APPLE_TO_UNIX))
    return int(round(v))


@beartype
def load_existing_history(path: Path) -> list:
    """Load existing history.json if present.

    Args:
        path: Path to history.json file.

    Returns:
        List of message dicts (possibly empty).
    """
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return list(data.values())
    except Exception as exc:
        log.warning(f"Failed to read existing history {path}: {exc}")
    return []


@beartype
def dedupe_messages(messages: Iterable[dict]) -> list:
    """Deduplicate messages by (unixtimestamp, participant, text).

    Keeps first occurrence and sorts chronologically.

    Args:
        messages: Iterable of message dicts.

    Returns:
        Sorted list of unique messages.
    """
    seen = set()
    out = []
    for m in messages:
        key = (m.get("unixtimestamp"), m.get("participant"), m.get("text"))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    out.sort(key=lambda x: x.get("unixtimestamp", 0))
    return out


class TimeMessageBackup:
    """Main class handling backing up chat messages and attachments into an output folder.

    The class copies the supplied chat.db into a temporary working directory to avoid
    touching the original database during processing. Attachments are copied individually
    from their original locations into the temporary directory and then into the final
    backup directory for each contact.
    """

    @beartype
    def __init__(self, config: Config):
        """Create a temporary working directory and copy chat.db into it.

        Args:
            config: Config dataclass instance.

        Raises:
            PermissionError: If chat.db cannot be read (suggest Full Disk Access).
            FileNotFoundError: If chat.db does not exist.
        """
        self.config = config
        self.output_dir = config.output
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Temporary working directory
        self.temp_dir = tempfile.TemporaryDirectory(prefix="time_message_")
        self.temp_path = Path(self.temp_dir.name)
        log.debug(f"Temporary working directory: {self.temp_path}")

        # Copy only the chat.db file into temp for safe reads
        self.db_path = self.temp_path / config.database.name
        try:
            shutil.copy2(config.database, self.db_path)
            log.info(f"📁 Copied chat database to temporary location: {self.db_path}")
            console.print(
                f"📁 Copied chat database to temporary location: [bold]{self.db_path}[/]"
            )
        except PermissionError:
            log.error(
                f"❌ Cannot access database at {config.database}. "
                "Make sure your Terminal has Full Disk Access (System Settings → Privacy & Security → Full Disk Access)."
            )
            console.print(
                f"❌ [red]Cannot access database at {config.database}.[/]\n"
                "Make sure Terminal has Full Disk Access (System Settings → Privacy & Security → Full Disk Access)."
            )
            raise
        except FileNotFoundError:
            log.error(f"❌ Database file not found: {config.database}")
            console.print(f"❌ [red]Database file not found:[/red] {config.database}")
            raise

    @beartype
    def cleanup(self) -> None:
        """Cleanup the temporary working directory."""
        try:
            self.temp_dir.cleanup()
            log.info("🧹 Temporary working directory cleaned up.")
        except Exception as exc:
            log.warning(f"Failed to cleanup temp directory: {exc}")

    @beartype
    def list_conversations(self) -> list:
        """Return a deduplicated list of conversation identifiers.

        Returns:
            List[str]: list of contact identifiers (phone/email).
        """
        query = "SELECT guid FROM chat;"
        contacts: list = []
        with sqlite_connection(self.db_path) as conn:
            for row in conn.execute(query):
                guid = row["guid"] if "guid" in row.keys() else row[0]
                if not guid:
                    continue
                contacts.append(normalize_guid(guid))
        # deduplicate preserving order
        seen = set()
        unique = []
        for c in contacts:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        log.info(f"🔎 Found {len(unique)} conversations")
        return unique

    @beartype
    def backup_chat(self, contact: str) -> None:
        """Export messages for a single contact into output/<contact>/history.json.

        Args:
            contact: Contact identifier string.
        """
        log.info(f"💬 Backing up messages for {contact}")
        guid = f"iMessage;-;{contact}"
        query = """
            SELECT is_from_me, date, text
            FROM message
            WHERE handle_id = (
                SELECT handle_id
                FROM chat_handle_join
                WHERE chat_id = (
                    SELECT ROWID FROM chat WHERE guid = ?
                )
            );
        """
        messages: list = []
        with sqlite_connection(self.db_path) as conn:
            for row in conn.execute(query, (guid,)):
                is_from_me = row["is_from_me"] if "is_from_me" in row.keys() else row[0]
                date_raw = row["date"] if "date" in row.keys() else row[1]
                text = row["text"] if "text" in row.keys() else row[2]
                unixts = apple_time_to_unix_seconds(date_raw)
                ts_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(unixts))
                participant = (
                    "me"
                    if is_from_me == 1
                    else contact
                    if is_from_me == 0
                    else f"unknown_{is_from_me}"
                )
                messages.append(
                    {
                        "unixtimestamp": unixts,
                        "timestamp": ts_iso,
                        "participant_id": str(is_from_me),
                        "participant": participant,
                        "text": "" if text is None else str(text),
                    }
                )

        target_dir = self.output_dir / contact
        target_dir.mkdir(parents=True, exist_ok=True)
        history_file = target_dir / "history.json"

        existing = load_existing_history(history_file)
        combined = dedupe_messages(existing + messages)
        with history_file.open("w", encoding="utf8") as fh:
            json.dump(combined, fh, indent=4, ensure_ascii=False)
        log.success(f"✅ Saved {len(combined)} messages to {history_file}")
        console.print(
            f"✅ Saved [bold]{len(combined)}[/bold] messages to [green]{history_file}[/]"
        )

    @beartype
    def _attachment_sources_for_contact(self, contact: str) -> list[Path]:
        """Query the DB and return the original attachment paths for a contact.

        Note: these original paths may be protected. We check existence and skip
        inaccessible files. Copying happens later.

        Args:
            contact: Contact identifier.

        Returns:
            List[Path]: list of original attachment file paths (may be empty).
        """
        guid = f"iMessage;-;{contact}"
        query = """
            SELECT filename FROM attachment
            WHERE rowid IN (
                SELECT attachment_id FROM message_attachment_join
                WHERE message_id IN (
                    SELECT rowid FROM message WHERE cache_has_attachments=1 AND handle_id = (
                        SELECT handle_id FROM chat_handle_join WHERE chat_id = (
                            SELECT ROWID FROM chat WHERE guid = ?
                        )
                    )
                )
            );
        """
        sources: list[Path] = []
        with sqlite_connection(self.db_path) as conn:
            for row in conn.execute(query, (guid,)):
                raw = row["filename"] if "filename" in row.keys() else row[0]
                if not raw:
                    continue
                p = Path(raw).expanduser()
                # If the DB stored a tilde-less relative path, try to resolve it.
                if not p.is_absolute():
                    p = (Path.home() / p).resolve()
                sources.append(p)
        return sources

    @beartype
    def _copy_attachments_to_temp(self, source_paths: list[Path]) -> list[Path]:
        """Copy a list of source attachment files into the temp attachments folder.

        Shows a progress bar and skips files that are missing or inaccessible.

        Args:
            source_paths: List of Path objects pointing to original attachment files.

        Returns:
            List[Path]: paths of copied files inside the temp attachments folder.
        """
        copied: list[Path] = []
        dest_base = self.temp_path / "attachments"
        dest_base.mkdir(parents=True, exist_ok=True)

        total = len(source_paths)
        if total == 0:
            return []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("🔁 Copying attachments to temp", total=total)
            for src in source_paths:
                try:
                    if not src.exists():
                        log.warning(f"Attachment not found or inaccessible: {src}")
                        progress.advance(task)
                        continue
                    dest = dest_base / src.name
                    shutil.copy2(src, dest)
                    copied.append(dest)
                except PermissionError:
                    log.warning(f"Permission denied copying attachment: {src}")
                except Exception as exc:
                    log.warning(f"Failed to copy {src}: {exc}")
                progress.advance(task)
        log.info(f"Copied {len(copied)}/{total} attachments to temp")
        return copied

    @beartype
    def backup_attachments(self, contact: str) -> None:
        """Copy attachments for a contact from temp into the final output directory.

        Steps:
            - Query DB for attachment original paths
            - Copy accessible attachments into temp (with progress)
            - Copy temp attachments into final output/<contact>/attachments (with progress)

        Args:
            contact: Contact identifier.
        """
        console.print(f"📎 Processing attachments for [bold]{contact}[/bold]...")
        sources = self._attachment_sources_for_contact(contact)
        if not sources:
            log.info(f"No attachments found for {contact}")
            console.print(f"ℹ️  No attachments found for {contact}")
            return

        # Copy originals into temp (reads original protected locations once)
        temp_copied = self._copy_attachments_to_temp(sources)
        if not temp_copied:
            console.print(
                f"⚠️  No accessible attachments could be copied for {contact}."
            )
            return

        # Now copy from temp to final output location with a progress bar
        dest_dir = self.output_dir / contact / "attachments"
        dest_dir.mkdir(parents=True, exist_ok=True)

        total = len(temp_copied)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(
                f"📂 Writing attachments for {contact}", total=total
            )
            for tpath in temp_copied:
                try:
                    # final write
                    shutil.copy2(tpath, dest_dir)
                except Exception as exc:
                    log.warning(f"Failed to copy {tpath} -> {dest_dir}: {exc}")
                progress.advance(task)

        log.success(f"📁 Attachments for {contact} copied to {dest_dir}")
        console.print(
            f"📁 Attachments for [bold]{contact}[/bold] copied to [green]{dest_dir}[/green]"
        )

    @beartype
    def backup_all(self, contacts: Iterable[str]) -> None:
        """Backup multiple contacts, cleaning up temp directory when finished.

        Args:
            contacts: Iterable of contact identifier strings.
        """
        try:
            for c in contacts:
                console.rule(f"🔹 Backing up {c}")
                log.info(f"----- Contact: {c} -----")
                self.backup_chat(c)
                if self.config.include_attachments:
                    self.backup_attachments(c)
        finally:
            self.cleanup()


def build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the CLI."""
    p = argparse.ArgumentParser(
        prog="timemessage", description="Backup iMessage (chat.db) conversations."
    )
    p.add_argument(
        "--db",
        "-d",
        type=Path,
        default=Path.home() / "Library/Messages/chat.db",
        help="Path to chat.db",
    )
    p.add_argument(
        "--out",
        "-o",
        type=Path,
        default=Path(f"iMessage.backup_{time.strftime('%Y-%m-%d_%H-%M')}"),
        help="Output directory for backups",
    )
    p.add_argument("--yes", "-y", action="store_true", help="Assume yes for prompts")
    p.add_argument(
        "--no-attachments", action="store_true", help="Skip copying attachments"
    )
    p.add_argument(
        "--log", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)"
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List available conversations")
    backup = sub.add_parser("backup", help="Backup conversations")
    backup.add_argument(
        "--contact",
        "-c",
        type=str,
        nargs="*",
        help="Specific contact(s) to backup (defaults to all)",
    )
    backup.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be backed up without writing files",
    )
    return p


def confirm(prompt: str) -> bool:
    """Ask the user to confirm a prompt, returning True for yes."""
    ans = input(f"{prompt} [y/N]: ").strip().lower()
    return ans in ("y", "yes")


@beartype
def main(argv: Optional[list[str]] = None) -> int:
    """Main entrypoint for the CLI.

    Args:
        argv: Optional list of argv strings (for testing).

    Returns:
        Exit code int.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    cfg = Config(
        database=args.db,
        output=args.out,
        yes=args.yes,
        include_attachments=not args.no_attachments,
        loglevel=args.log,
    )

    # Configure loguru
    log.remove()
    log.add(lambda msg: print(msg, end=""), level=cfg.loglevel.upper())

    if not cfg.database.exists():
        log.error(f"❌ Database not found: {cfg.database}")
        console.print(f"❌ [red]Database not found:[/red] {cfg.database}")
        return 2

    try:
        backup = TimeMessageBackup(cfg)
    except Exception:
        # message already logged / printed
        return 3

    try:
        if args.command == "list":
            contacts = backup.list_conversations()
            for c in contacts:
                console.print(f"• {c}")
            # cleanup before exit
            backup.cleanup()
            return 0

        if args.command == "backup":
            contacts = args.contact or backup.list_conversations()
            if not contacts:
                log.info("ℹ️ No conversations found to backup.")
                console.print("ℹ️  No conversations found to backup.")
                backup.cleanup()
                return 0

            console.print(
                f"📦 Backing up [bold]{len(contacts)}[/bold] conversation(s) to [green]{cfg.output}[/green]"
            )
            if not cfg.yes and not args.dry_run:
                if not confirm(
                    f"Really backup {len(contacts)} conversation(s) from {cfg.database} to {cfg.output}?"
                ):
                    log.info("Abort by user")
                    console.print("Abort by user")
                    backup.cleanup()
                    return 0

            if args.dry_run:
                for c in contacts:
                    console.print(
                        f"Would backup: {c} (attachments: {cfg.include_attachments})"
                    )
                backup.cleanup()
                return 0

            backup.backup_all(contacts)
            log.success(f"🎉 Backups stored in {cfg.output}")
            console.print(f"🎉 Backups stored in [bold]{cfg.output}[/bold]")
            return 0

        log.error("Unknown command")
    except Exception as e:
        log.exception(repr(e))
    finally:
        backup.cleanup()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.exception(repr(e))
