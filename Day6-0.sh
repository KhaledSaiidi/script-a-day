# automating server disk usage monitoring -- identify when disk usage reaches a critical level.
# receive an alert if it exceeds a certain threshold 80%. The script should:
##  Check the disk usage percentage on each partition.
##  If usage exceeds a set threshold, send an email alert to the DevOps team with the partition name and usage details.
## Log each check for records and debugging.

#!/bin/bash
THRESHOLD=80
ALERT_EMAIL="devops_team@example.com"
LOG_FILE="/var/log/disk_usage_monitor.log"

check_disk_usage() {
    alert_message=""
    alert_count=0

    # Get disk usage data for each partition
    df -h | grep '^/dev/' | awk '{print $5 " " $1}' | while read -r usage partition; do
        # Remove the % sign from usage for comparison
        usage_percent=${usage%"%"}

        if [[ "$usage_percent" -ge "$THRESHOLD" ]]; then
            # Log the alert
            alert_message+="$(date): WARNING - $partition usage is at $usage\n"
            ((alert_count++))

            echo "$(date): WARNING - $partition usage is at $usage" >> "$LOG_FILE"
        else
            # Log normal usage
            echo "$(date): $partition usage is at $usage, within limits." >> "$LOG_FILE"
        fi
  done
    
  # Check if there are any alerts to send
  if [[ "$alert_count" -gt 0 ]]; then
    # Send alert email
    echo -e "$alert_message" | mail -s "Disk Usage Alert: $alert_count partitions exceeding $THRESHOLD%" "$ALERT_EMAIL"
  fi
}



check_disk_usage


#########################################################################################################
# Edit the crontab file
crontab -e
# Add this line to check disk usage every hour
0 * * * * /path/to/disk_usage_monitor.sh

