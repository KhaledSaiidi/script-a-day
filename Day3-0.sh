# automate the process of backing logs and cleaning up old logs
# find logs in a "/var/log/app/" 
# backing up app-logs-YYYY-MM-DD.tar.gz, delete log files older than 30
# log script actions to /var/log/app-backup.log: Date and time, Number of logs, Size of the archive created, Status of the log cleanup
# custom log directory and backup directory


#!/bin/bash
LOG_DIR="/var/log/app/"
BACKUP_DIR="/backup/log/"

if [ "$#" -ge 2 ]; then
    LOG_DIR=$1
    BACKUP_DIR=$2
fi

CURRENT_DATE=$(date + %Y-%m-%d %H:%M:%S)
BACKUP_FILE="app-logs-$(date +%Y-%m-%d).tar.gz"
LOG_FILE="/var/log/app-backup.log"

LOGS_NUMBER=$(find "$LOG_DIR" -type f | wc -l)
tar -czf "$BACKUP_DIR/$BACKUP_FILE" -C "$LOG_DIR"

if [ $? -eq 0 ]; then
    ARCHIVE_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | awk '{print $1}')
    echo "[$CURRENT_DATE] - Backup successful: $LOGS_NUMBER logs archived, size: $ARCHIVE_SIZE" >> "$LOG_FILE"
else
    echo "[$CURRENT_DATE] - Backup failed" >> "$LOG_FILE"
    exit 1
fi

find "$LOG_DIR" -type f -name "*.log" -mtime +30 -delete
if [ $? -eq 0 ]; then
    echo "Old Logs deleted, Date: $CURRENT_DATE" >> "/var/log/app-backup.log"
else
    echo "[$CURRENT_DATE] - Failed to delete old logs" >> "$LOG_FILE"
    exit 1
fi


### du vs df:
# du (Disk Usage): This command reports the actual disk space used by files or directories
# df (Disk Free): This command shows the available disk space and disk usage of entire filesystems (partitions) 
# even when you specify a single file, not individual files

### tail:
# tail filename.txt -> shows last 10 lines of the file
# tail -n 5 filename.txt -> show the last 5 lines of the file
# tail -n +5 filename.txt -> show from line number 5 to the end of the file

### head:
# head myfile.txt -> shows first 10 lines of myfile.txt
# head -n 3 myfile.txt -> show the first 3 lines of myfile.txt
# head -n -3 myfile.txt -> show all lines except the last 3 lines


### head -n 10 filename.txt | tail -n +5 -> Gets the first 10 lines then Outputs everything from line 5 onward -> display line 5 to 10


