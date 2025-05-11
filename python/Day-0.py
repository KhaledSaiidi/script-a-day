import json
from collections import Counter

with open('servers.json', 'r') as file:
    data = json.load(file)

print("------Start----")
for server in data['servers']:
    if server['status'] == 'running':
        print(f"Server: {server['name']}, Ip: {server['ip']}.")

roles = [server['role'] for server in data['servers']]
role_count = Counter(roles)
for role, count in role_count.items():
    print(f"Role: {role}, Count: {count}.")

stopped_servers = [server['name'] for server in data['servers'] if server['status'] == 'stopped']
if stopped_servers:
    print("Stopped servers:")
    for server in stopped_servers:
        print(server)