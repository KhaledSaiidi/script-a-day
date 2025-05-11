# Scale AKS pods based on weather conditions
import requests
import subprocess
import os

def get_weather(city):
    api_key = os.getenv('WEATHER_API_KEY')
    if api_key is None:
      print("API key not set. Please set the WEATHER_API_KEY environment variable.")
      return

    weather_api = f'http://api.weatherapi.com/v1/current.json?key={api_key}&q={city}'
    response = requests.get(weather_api)
    data = response.json()
    if 'error' not in data:
        weather = data['current'] ['condition']['text']
        temperature = data['current']['temp_c']
        print(f"weather: {weather}, temperature: {temperature}°C")
        if "Heavy rain" in weather:
            print("Heavy rain detected, Scaling pods number in AKS.")
            scale_aks_pods(namespace="shopping", deployment="shopping-service", replicas=3)
        else:
            print("No Heavy rain detected, No Scaling pods.")
    else:
        print("Error fetching weather data:", data['error']['message'])

def scale_aks_pods(namespace, deployment, replicas):
    try:
        subprocess.run([
            'kubectl', 'scale', f'deployment/{deployment}', f'--replicas={replicas}', '-n', namespace
        ], check=True)
        print(f"Scaled {deployment} to {replicas} replicas in namespace {namespace}.")
    except subprocess.CalledProcessError as e:
        print(f"Error scaling deployment: {e}")

#Usage:
get_weather("Tunis")