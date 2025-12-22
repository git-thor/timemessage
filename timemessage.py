"""
MIT License

Copyright (c) 2021 Thomas Rudolf

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


import logging
import argparse
import sys
import pathlib
import os
import sqlite3
import datetime
import time
import threading
import json
import shutil


log = logging.getLogger()


class TimeMessageBackup:

    def __init__(self, config):

        self.config = config

        self.connection = None
        self.cursors = None

        self.conversations = []

        self.__done = False

        self.__connect()

    def __connect(self):

        self.connection = sqlite3.connect(self.config.database_directory)
        self.cursor = self.connection.cursor()

    def __in_progress(self):

        def __animate(self):
            animation = "|/-\\"
            idx = 0
            while not self.__done:
                print("> Copying, do not interrupt", animation[idx % len(animation)], end="\r")
                idx += 1
                time.sleep(0.1)

            self.__done = False

        t = threading.Thread(target=__animate, args=(self,), daemon=True)
        t.start()

    def retrieve_conversations(self):

        conversations = []
        query = "select * from chat;"
        for con in self.cursor.execute(query):

            if (subs := "iMessage;+;chat") in con[1]:
                conversations.append(con[1].replace(subs, ""))
            elif (subs := "iMessage;-;") in con[1]:
                conversations.append(con[1].replace(subs, ""))
            elif (subs := "SMS;-;") in con[1]:
                conversations.append(con[1].replace(subs, ""))
            elif (subs := "SMS;+;") in con[1]:
                conversations.append(con[1].replace(subs, ""))
            elif (subs := "tel;+;") in con[1]:
                conversations.append(con[1].replace(subs, ""))
            elif (subs := "chat") in con[1]:
                conversations.append(con[1].replace(subs, ""))

        self.conversations = list(dict.fromkeys(conversations))  # Remove duplicates

        log.info(f"Found {len(self.conversations)} conversations in database")

        return self.conversations

    def backup_chat(self, contact):

        query = (f"""
            select is_from_me, date, text from message where handle_id=(
                select handle_id from chat_handle_join where chat_id=(
                    select ROWID from chat where guid='iMessage;-;{contact}'
                )
            );
        """)

        messages = {}
        ts_offset = int(datetime.datetime.strptime("2001-01-01", "%Y-%m-%d").strftime("%s"))
        for id, date, text in self.cursor.execute(query):
            ts = date // 1000000000 + ts_offset
            timestamp = datetime.datetime.fromtimestamp(int(ts))
            # timestamp = datetime.datetime(int(date/100000000) + offset, "unixepoch", "utc")
            if id == 1:
                participant = "me"
            elif id == 0:
                participant = contact
            else:
                participant = f"unknown_{id}"

            messages[str(ts)] = {
                "unixtimestamp": ts,
                "timestamp": str(timestamp),
                "participant_id": str(id),
                "participant": str(participant),
                "text": str(text)
            }

        if messages:

            log.info(f"> Backing up {len(messages)} messages with {contact} ...")

            path = self.config.output_directory + "/" + str(contact)
            os.makedirs(path, exist_ok=True)
            try:
                with open(f"{self.config.output_directory}/{contact}/history.json", "r", encoding="utf8") as f:
                    backup = json.load(f)

                messages.update(backup)
            except Exception:
                # traceback.log.info_exc()
                pass

            with open(f"{self.config.output_directory}/{contact}/history.json", "w", encoding="utf8") as f:
                json.dump(messages, f, sort_keys=True, indent=4, ensure_ascii=True)

            log.info(f"> Backup now contains {len(messages)} messages.")
        else:
            log.info(f"> No messages found with {contact} ...")

    def backup_attachements(self, contact):

        query = (f"""
            select filename from attachment where rowid in (
                select attachment_id from message_attachment_join where message_id in (
                    select rowid from message where cache_has_attachments=1 and handle_id=(
                        select handle_id from chat_handle_join where chat_id=(
                            select ROWID from chat where guid='iMessage;-;{contact}'
                        )
                    )
                )
            )
        """)

        filepaths = []
        for path in self.cursor.execute(query):
            path = path[0]
            if "~" in path:
                path = path.replace("~", "")
                path = str(pathlib.Path.home()) + path
                path = pathlib.Path(path)
            else:
                path = pathlib.Path(path)

            filepaths.append(path)

        if filepaths:

            self.__in_progress()
            log.info(f"> Backing up {len(filepaths)} attachements with {contact} ...")
            for path in filepaths:
                log.debug(f"  > Backing up {path} ...")
                directory = f"{self.config.output_directory}/{contact}/attachements/"
                os.makedirs(directory, exist_ok=True)

                try:
                    shutil.copy2(path, directory)
                except FileNotFoundError:
                    log.warning(f"  > File not found: {path}")

            self.__done = True

        else:
            log.info(f"> No attachements found with {contact} ...")

    def start(self):

        log.info(f"Starting backups from {self.config.database_directory} ...")
        self.retrieve_conversations()

        for contact in self.conversations:
            log.info(f"Backup of contact {contact}:")
            self.backup_chat(contact)
            self.backup_attachements(contact)

        log.info(f"Backups are stored in the target directory {self.config.output_directory}/")


def configure_logger():

    formatter = logging.Formatter('%(asctime)s [%(levelname)7s] %(message)s')

    stream_handler = logging.StreamHandler(sys.stdout)  # Writes into ``sys.stderr`` on default
    stream_handler.setFormatter(formatter)
    log.addHandler(stream_handler)

    file_handler = logging.FileHandler("backup.log")
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)

    log.setLevel(logging.INFO)

    return log


def main():

    argumentParser = argparse.ArgumentParser(
        description=(
            "TimeMessage - an macOS iMessage Backup Script"
            "Backs up locally stored conversations of timestamped texts and available attachements.\n"
            "DISCLAIMER\n"
            "THIS SCRIPT DOES NOT COME WITH ANY GUARANTEE, LIKE COMPLETENESS OF BACKUPS.\n"
            "MIT LICENSE APPLIES. CHECK THE SOURCE CODE. EVALUATE THE CODE FOR YOUR OWN ENVIRONMENT.\n"
            "USE AT YOUR OWN RISK! ENCRYPT BACKUPS YOURSELF!"
        )
    )

    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d_%H-%M")

    argumentParser.add_argument(
        "-db",
        "--database_directory",
        type=str,
        default="",
        help="Specifies the iMessage directory (string, default: ~/Library/Messages/)."
    )
    argumentParser.add_argument(
        "-o",
        "--output_directory",
        type=str,
        default=f"iMessage.backup_{timestamp}",
        help="Specifies output directory of the backup (string, default: iMessage.backup_YYYY-mm-dd_HH-MM)."
    )

    config = argumentParser.parse_args()

    if not config.database_directory:
        config.database_directory = pathlib.Path.home().joinpath("Library", "Messages", "chat.db")
        log.info("No explicit path given as argument, using system standard.")

    print(config)
    configure_logger()

    backup = TimeMessageBackup(config)

    print(
        "\n"
        "# TimeMessage \n"
        "##############\n"
    )

    msg = f"Really backup from {config.database_directory} to {config.output_directory}"
    agreed = input("%s (y/N): " % msg).lower() == "y"
    if not agreed:
        print("No. Abort.")
        exit(0)
    else:
        print("Careful, ensure to encrypt the output directory afterwards. The backup itself is unencrypted!")

    backup.start()


if __name__ == "__main__":
    main()
