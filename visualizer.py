import time
import json
import threading
import paho.mqtt.client as mqtt

class MQTTClient(threading.Thread):
    def __init__(self):
        super().__init__()
        self.client = mqtt.Client("visualizer")
        self.client.connect('test.mosquitto.org')
        self.client.subscribe("visualizer17")

    def publish(self, message):
        # publishing message to topic
        info = self.client.publish(
            topic = 'visualizer17',
            # payload is the message to publish
            payload = json.dumps(message).encode('utf-8')   
        )
        
        info.wait_for_publish()
        time.sleep(1)

def main():
    client = MQTTClient()
    with open('test_json.txt', 'r') as infile:
        data = json.load(infile)

    print(data)

    client.publish(data)

if __name__ == '__main__':
    main()
