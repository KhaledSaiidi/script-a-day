## Continuously monitor the status of critical services and alert the team if any of these services go down.
    # Specify the services to monitor.
    # Check each service status.
    # Log downtime incidents if any service is down.
    # Send a single email alert listing all services that are down.

#!/bin/bash
services=("nginx" "mysql" "docker")
ALERT_EMAIL="my-email@mail.com"
LOG_FILE="/var/log/service_monitor.log"

check_services() {
    local alert_message=""
    local down_count=0
    for service in "${services[@]}"; do
        if ! systemctl is-active --quiet "$service"; then
            alert_message+="$(date): WARNING - $service is down\n"
            ((down_count++))
        else
            echo "$(date): $service is running" >> "$LOG_FILE"
        fi
    done

    if [[ "$down_count" -gt 0 ]]; then
        echo -e "$alert_message" >> "$LOG_FILE"
        echo -e "$alert_message" | mail -s "Service Alert: $down_count services down" "$ALERT_EMAIL"
    fi
}

check_services