# Time Message - a macOS iMessage Backup Script
*inspired by the shell script [ahmbay/backup-iMessageBackup-macos](https://github.com/ahmbay/backup-iMessageBackup-macos/blob/master/iMessageBackup.sh)*

This script backs up locally stored conversations of timestamped texts and available attachements.

Not all of your iMessage data may be cached locally.

The backup is unencrypted. Make sure to encrypt the output folder, afterwards!

## DISCLAIMER
```
THIS SCRIPT DOES NOT COME WITH ANY GUARANTEE, LIKE COMPLETENESS OF BACKUPS.

MIT LICENSE APPLIES. CHECK THE SOURCE CODE. EVALUATE THE CODE FOR YOUR OWN ENVIRONMENT.

USE AT YOUR OWN RISK! ENCRYPT BACKUPS YOURSELF!
```

## Usage
This script has no pip dependencies or required Python packages. Your CLI tool needs full disk access, configurable in the Settings > Privacy menu.

Run the script and optionally add the location of your `chats.db` SQLite3 database, if it is not in the default location of the macOS `~/Library/Messages/`.

```
usage: timemessage.py [-h] [-db DATABASE_DIRECTORY] [-o OUTPUT_DIRECTORY]

optional arguments:
  -h, --help            show this help message and exit
  -db DATABASE_DIRECTORY, --database_directory DATABASE_DIRECTORY
                        Specifies the iMessage directory (string, default: ~/Library/Messages/).
  -o OUTPUT_DIRECTORY, --output_directory OUTPUT_DIRECTORY
                        Specifies output directory of the backup (string, default: iMessage.backup_YYYY-mm-dd_HH-MM).
```

Let it run a backup:
```bash
python timemessage.py
```

### Example structure
```
./iMessage.backup_YYYY-mm-dd_HH-MM/
    |
    |__+1234567890/
    |   |__ ...
    |
    |__example@mail.com/
    |   |
    |   |__attachements/
    |   |   |__ID.ext
    |   |   |__ ...
    |   |
    |   |__history.json
    |
    |__ ...
```
