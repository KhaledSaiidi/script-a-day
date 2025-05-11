# Periodically checks if the service (like nginx) is running, if down restart it, and log status and restart attempts to a log file
# If the service cannot be restarted after 3 attempts -> sending an email or creating an alert log triggered

#!/bin/bash

SERVICE_NAME=$1
LOG_FILE=$2
MAX_ATTEMPT=3
RESTART_COUNT=0

check_service(){
    # is-active returns active, failed, inactive... /// --quiet suppresses output if service active it returns 0 else non-zero status code failure
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $SERVICE_NAME is running." >> "$LOG_FILE"
        return 0
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $SERVICE_NAME is not running." >> "$LOG_FILE"
        return 1
    fi
}

restart_service(){
    while [ $RESTART_COUNT -lt $MAX_ATTEMPTS ]; do
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Attempting to restart $SERVICE_NAME (Attempt $((RESTART_COUNT + 1)))" >> "$LOG_FILE"
        systemctl restart "$SERVICE_NAME"
        sleep 5
        
        if check_service; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') - $SERVICE_NAME successfully restarted." >> "$LOG_FILE"
            return 0
        else
            RESTART_COUNT=$((RESTART_COUNT + 1))
        fi
    done

    echo "$(date '+%Y-%m-%d %H:%M:%S') - $SERVICE_NAME failed to restart after $MAX_ATTEMPTS attempts. Triggering alert." >> "$LOG_FILE"
    trigger_alert
    return 1
}

trigger_alert() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ALERT: $SERVICE_NAME is down and failed to restart." >> "$LOG_FILE"
    # mail -s "$SERVICE service is down!" admin@example.com <<< "$SERVICE failed to restart after $MAX_ATTEMPTS attempts."
}


if ! check_service; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $SERVICE_NAME is down. Attempting to restart." >> "$LOG_FILE"
  restart_service
fi