# Delete log files older than 30 days named in the format server-log-YYYY-MM-DD.log & Logs the file names into deleted_logs.txt for auditing

#!/bin/bash
LOG_DIR="/path/to/log/dir"

AUDIT_LOG="/path/to/deleted_logs.txt"

find "$LOG_DIR" -name "server-log-*.log" -mtime +30 -print -delete | tee -a "$AUDIT_LOG"

# -mtime +30 -> modified time +30 days
# -print -> print file name /// -delete -> delete the file
# tee -> takes the printed as input and writes to the output with -a for "append" instead of overwriting the file

# Optional: Notify if no files were deleted
# -s operator returns "true" if the file exists and has a size greater than zero.
if [ ! -s "$AUDIT_LOG" ]; then
  echo "No files were deleted" >> "$AUDIT_LOG"
fi

echo "CleanUp complete"

---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Another way is extracting the date from the log file name server-log-YYYY-MM-DD.log:

#!/bin/bash
LOG_DIR="/path/to/log/dir"

AUDIT_LOG="/path/to/deleted_logs.txt"

# Get the current date in seconds
current_date=$(date +%s)

for log_file in "$LOG_DIR"/server-log-*.log; do

  # Extract the date from the filename (YYYY-MM-DD)
  # basename takes the full file path & return filename only
  # sed is a stream editor :
      # s/ Indicates that we're performing a substitution.
      # using sed capture parts of the text using parentheses \( ... \)
      # /server-log-\(.*\)\.log captures everything between server-log- and .log
      # /\1/ replacement part of sed  -> \1 refers to whatever text was matched will replace the entire string

  file_date=$(basename "$log_file" | sed 's/server-log-\(.*\)\.log/\1/')

  # Convert the file date to seconds since the epoch
  file_date_seconds=$(date -d "$file_date" +%s)

  diff_days=$(( (current_date - file_date_seconds) / (60 * 60 * 24) ))

  if [ "$diff_days" -gt 30 ]; then
    echo "$log_file" >> "$AUDIT_LOG"  # Log the name of the file to delete
    rm "$log_file"                    # Delete the log file
  fi
done