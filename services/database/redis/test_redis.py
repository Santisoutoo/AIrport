# test_redis.py
import redis

# Connection
r = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=True
)

# Write
r.set('aircraft:ABC123:status', 'taxiing')
r.set('aircraft:ABC123:altitude', '0')

# Read
status = r.get('aircraft:ABC123:status')
altitude = r.get('aircraft:ABC123:altitude')

print(f"Status: {status}")
print(f"Altitude: {altitude}")


r.hset('aircraft:XYZ789', mapping={
    'callsign': 'XYZ789',
    'altitude': '5000',
    'heading': '270',
    'speed': '250'
})

aircraft = r.hgetall('aircraft:XYZ789')
print(f"\nAircraft: {aircraft}")

# List airplanes created
keys = r.keys('aircraft:*')
print(f"\nAll aircraft: {keys}")