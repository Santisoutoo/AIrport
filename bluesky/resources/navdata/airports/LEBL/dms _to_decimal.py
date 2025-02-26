def dms_to_decimal(degrees, minutes, seconds, direction):
    decimal = degrees + minutes/60 + seconds/3600
    if direction in ['S', 'W']:
        decimal *= -1
    return decimal


lat = dms_to_decimal(41, 17, 41.43, 'N')
lon = dms_to_decimal(2, 4, 36.05, 'E')

print(f'{lat}, {lon}')