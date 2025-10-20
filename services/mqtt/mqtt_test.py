import json
import time
import paho.mqtt.client as mqtt


BROKER = "localhost"
PORT = 1883

#                   CONTROLLER (Sends command)
def controller_on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Controller connected")

controller = mqtt.Client(
    client_id="controller",
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2
)
controller.on_connect = controller_on_connect


#                  AIRCRAFT (Receives commands)
def aircraft_on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Aircraft connected")
        client.subscribe("/aircraft/Speedbird234/command")

def aircraft_on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print(f"Speedbird234 received: {data}")

aircraft = mqtt.Client(
    client_id="speedbird234",
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2
)
aircraft.on_connect = aircraft_on_connect
aircraft.on_message = aircraft_on_message


try:
    controller.connect(BROKER, PORT, 60)
    aircraft.connect(BROKER, PORT, 60)

    controller.loop_start()
    aircraft.loop_start()

    time.sleep(1)

    # Controller sends command
    print("\nController: Speedbird 234, taxi to runway 27\n")
    controller.publish(
        "/aircraft/Speedbird234/command",
        json.dumps({"intent": "TAXI", "runway": "27"})
    )

    time.sleep(2)

    controller.loop_stop()
    aircraft.loop_stop()
    controller.disconnect()
    aircraft.disconnect()
    print("\nDisconnected")

except Exception as e:
    print(f"Error: {e}")
