## monitor the disk usage of a specified filesystem and send an email alert if the usage exceeds a defined threshold (in this case, 85%)

#!/bin/bash

LOG_FILE="/var/log/disk_usage_monitor.log"

usage() {
    echo "Usage: $0 <FILESYSTEM_FOR_CHECK> <email>"
    echo "  <FILESYSTEM_FOR_CHECK> : FILESYSTEM_FOR_CHECK for disk usage"
    echo "  <email>     : Email address to send alerts"
    exit 1
}

# Function to trigger an alert based on disk usage
trigger_alert() {
    local disk_usage=$1
    if [ "$disk_usage" -ge "$MAXIMUM_USAGE" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ALERT: disk usage is $disk_usage%" >> "$LOG_FILE"
        mail -s "$FILESYSTEM_FOR_CHECK disk usage depasses limit" "$EMAIL" <<< "The disk usage of $FILESYSTEM_FOR_CHECK is at $disk_usage%, which exceeds the FILESYSTEM_FOR_CHECK of $MAXIMUM_USAGE%."
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Disk usage is normal; $disk_usage%" >> "$LOG_FILE"
    fi
}

# Check for correct number of arguments
if [ "$#" -ne 2 ]; then
    usage
fi

MAXIMUM_USAGE=85
FILESYSTEM_FOR_CHECK=$1
EMAIL=$2

if [ -z "$FILESYSTEM_FOR_CHECK"]; then
    echo "You need to specify a FILESYSTEM_FOR_CHECK for $0 to work"
    exit 1
elif [ -z "$EMAIL"]; then
    echo "You need to specify an EMAIL for $0 to work"
    exit 1
fi

## command > /dev/null -> redirect standard output
## command 2> /dev/null -> redirect standard error
## command > /dev/null 2>&1 -> redirect Both Standard Output and Standard Error so you want see them in both cases while executing script
if ! df -h "$FILESYSTEM_FOR_CHECK" > /dev/null 2>&1; then
    echo "Error: The specified filesystem '$FILESYSTEM_FOR_CHECK' does not exist."
    exit 1
fi

DISK_USAGE=$(df -h "$FILESYSTEM_FOR_CHECK" | awk 'NR==2 {print $5}' | sed 's/%//')

********************OR******************
# sed -n '2p': Prints the second line of the output (the line containing the disk usage).
#sed 's/.* \([0-9]*\)%/\1/': Uses a regular expression to match the percentage and extract just the number.
DISK_USAGE=$(df -h "$FILESYSTEM_FOR_CHECK" | sed -n '2p' | sed 's/.* \([0-9]*\)%/\1/')

trigger_alert $DISK_USAGE