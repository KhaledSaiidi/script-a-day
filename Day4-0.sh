## script check each service is active and running. 
# If a service is down, the script should attempt to restart it and log the action (include  date, time, service name, and status). 
# it should send an alert (email) if the service fails to start after a specified number of attempts
### Inputs:
# A list of services to check (e.g., nginx, mysql).
# The maximum number of restart attempts (default to 3 if not provided).
# An email address to send alerts to.

#!/bin/bash

LOG_FILE="/var/log/service_health_check.log"

send_alert() {
    local service=$1
    local email=$2
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ALERT: $service failed to start after $MAX_ATTEMPTS attempts." | mail -s "$service Restart Alert" "$email"
}

check_service() {
    local service=$1
    local max_attempts=$2
    local attempts=0
    if ! systemctl is-active --quiet "$service"; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $service is down. Attempting to restart..." >> "$LOG_FILE"
        while [ "$attempts" -lt "$max_attempts" ]; do
            systemctl restart "$service"
            ((attempts++))
            sleep 5

            if systemctl is-active --quiet "$service"; then
                echo "$(date '+%Y-%m-%d %H:%M:%S') - $service successfully restarted after $attempts attempt(s)." >> "$LOG_FILE"
                return 0
            fi
        done
        
        send_alert "$service" "$EMAIL"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $service is running." >> "$LOG_FILE"
    fi
}

# Default values
MAX_ATTEMPTS=3
EMAIL="admin@example.com"

# Check for input parameters
if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <service1> <service2> ... [max_attempts] [email]"
    exit 1
fi

# Extract the last two parameters as max_attempts and email


# $@ all the arguments      : -1  selects the last element
EMAIL="${@: -1}"  # Get the last argument as email

# : -2  selects the second last element                   :1 specifies that we only want 1 element
MAX_ATTEMPTS="${@: -2:1}"  # Get the second to last argument as max_attempts

# Remove the last two parameters from the list of services
set -- "${@:1:$(($#-2))}"  # Keep all but the last two arguments as services

# Iterate over the services provided as arguments
for service in "$@"; do
    check_service "$service" "$MAX_ATTEMPTS"
done
