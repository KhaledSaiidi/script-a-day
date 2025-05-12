import datetime
import random

def generate_log_file(filename, num_entries):
    with open(filename, "w") as f:
        current_time = datetime.datetime(2023, 10, 1, 0, 0, 0)
        for _ in range(num_entries):
            log_level = random.choice(["INFO", "WARNING", "ERROR"])
            if log_level == "INFO":
                message = random.choice([
                    "Server started successfully",
                    "User logged in",
                    "Request processed successfully",
                    "Configuration loaded"
                ])
            elif log_level == "WARNING":
                message = random.choice([
                    "Low disk space",
                    "High CPU usage",
                    "Network latency detected"
                ])
            else:
                message = random.choice([
                    "Database connection failed",
                    "Timeout occurred",
                    "Permission denied",
                    "File not found"
                ])
            log_entry = f"{current_time.strftime('%Y-%m-%d %H:%M:%S')} {log_level} {message}"
            f.write(log_entry + "\n")
            current_time += datetime.timedelta(minutes=1)

generate_log_file("server1.log", 1000)
generate_log_file("server2.log", 1000)