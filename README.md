# TimeMessage - a macOS iMessage Backup CLI

*Inspired by the shell script [ahmbay/backup-iMessageBackup-macos](https://github.com/ahmbay/backup-iMessageBackup-macos/blob/master/iMessageBackup.sh)*

TimeMessage is a modern Python CLI tool to backup locally stored iMessage conversations on macOS, including timestamped texts and available attachments.

Not all of your iMessage data may be cached locally.

The backup is **unencrypted**. Make sure to encrypt the output folder afterwards.

## DISCLAIMER
```

THIS SCRIPT DOES NOT COME WITH ANY GUARANTEE, INCLUDING COMPLETENESS OF BACKUPS.

LICENSE APPLIES. CHECK THE SOURCE CODE. EVALUATE THE CODE FOR YOUR OWN ENVIRONMENT.

USE AT YOUR OWN RISK! ENCRYPT BACKUPS YOURSELF!

```

---

## Features

- Backup all conversations or select specific contacts
- Copy attachments automatically (optional)
- Modern CLI with Rich progress bars and spinner
- Logging via Loguru with configurable log level
- Runtime type enforcement via beartype
- Compatible with Python 3.12+
- Supports dry-run mode to preview backups without writing files

---

## Installation

Using **uv** (recommended for package management):

```bash
uv tool install git+https://github.com/git-thor/timemessage.git
```

This installs the `timemessage` CLI globally.

---

## Usage

Once installed, you can use the CLI with the following commands:

### List available conversations

```bash
timemessage list --db ~/Library/Messages/chat.db
```

* `--db` : Optional path to your `chat.db`. Defaults to `~/Library/Messages/chat.db`.

### Backup all conversations

```bash
timemessage backup --db ~/Library/Messages/chat.db --out ~/iMessage.backups
```

* `--out` : Optional output directory. Default: `iMessage.backup_YYYY-mm-dd_HH-MM`
* `--no-attachments` : Skip copying attachments
* `--yes` : Skip confirmation prompt
* `--dry-run` : Show what would be backed up without writing files

### Backup specific contacts

```bash
timemessage backup --contact "+1234567890" "example@mail.com"
```

---

## Example backup structure

```
./iMessage.backup_YYYY-mm-dd_HH-MM/
    |
    |__+1234567890/
    |   |__history.json
    |   |__attachments/
    |       |__ID.ext
    |       |__...
    |
    |__example@mail.com/
        |__history.json
        |__attachments/
            |__ID.ext
            |__...
```

---

## Notes

* Your CLI tool requires **full disk access**: System Settings > Privacy > Full Disk Access.
* All messages are exported in **JSON** format, with timestamps, sender info, and message text.
* Attachments are copied to `<contact>/attachments/`.
* Messages are deduplicated and sorted chronologically.

---

## License

MIT License. See [LICENSE](LICENSE).
