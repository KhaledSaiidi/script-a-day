# Extract Python error messages from log files by timestamp and log level

import glob
from datetime import datetime

with open("errors.log", "w") as error_file:
    for file_path in glob.glob("*.log"):
        server_name = file_path.split(".")[0]
        try:
            with open(file_path, "r") as log_file:
                for line in log_file:
                    parts = line.split()
                    if len(parts) >= 4 and parts[2] == "ERROR":
                        timestamp_str = parts[0] + " " + parts[1]
                        error_message = " ".join(parts[3:])
                        try:
                            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            formatted_time = timestamp.strftime("%d %B %Y at %I:%M%p").lower()
                            output_message = f"This occurred on {formatted_time}: {error_message}"
                            error_file.write(f"{server_name}: {output_message}\n")
                        except ValueError:
                            print(f"Warning: Invalid timestamp in {file_path}: {line.strip()}")
        except FileNotFoundError:
            print(f"Warning: {file_path} not found. Skipping.")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")