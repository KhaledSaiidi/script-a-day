# task Creates a backup of the configuration directory /etc/myapp/ into a config-backup-YYYY-MM-DD.tar.gz. archive &
# Deletes backup files older than 7 days, keeping only the most recent 7 backups

#!/bin/bash

CONFIG_DIR=$1

BACKUP_DIR="/path/to/backup/directory"

# date in YYYY-MM-DD format
date=$(date + %F)

BACKUP_FILE="config-backup-$date.tar.gz"

if [ -f "$BACKUP_DIR/$BACKUP_FILE"]; then
  echo "Backup file $BACKUP_FILE already exists."

else
  # c: Create an archive, -z: Compress using gzip, -f: Specify the filename.
  tar -czf "$BACKUP_DIR/$BACKUP_FILE" "$CONFIG_DIR"
  echo "Backup created: $BACKUP_FILE"
  
fi

find "$BACKUP_DIR" -name "config-backup-*.tar.gz" -type f -mtime +7 -print -delete 

# $? holds the exit status of the last command, 0 means successful, Non-zero means failed
if [ $? -eq 0 ]; then
  echo "Old backups older than 7 days were deleted."
else
  echo "No old backups found."
fi
