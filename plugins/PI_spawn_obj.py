from XPPython3 import xp

class PythonInterface:
    
    def __init__(self):
        self.name: str = 'obj spawn'
        self.sig: str = 'obj_spawner_v1.0'
        self.desc: str = 'Spawns .obj files in a given (lat, lon, h, pitch, heading, roll)'
        
    def XPluginStart(self):
        return self.name, self.desc, self.sig
    
    def XPluginStop(self):
        pass
    
    def XPluginEnable(self):
        try:
            print("Plugin enabled")
            self.spawnAircraft()
            print("Aircraft spawned")
        except Exception as e:
            print(f"Error: {e}")
        return 1

    def XPluginDisable(self):
        pass
    
    def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
        pass

    def spawnAircraft(self):
        try: 
                        
            pth = r'C:\X-Plane 12\Resources\default scenery\sim objects\apt_aircraft\jet\B738_RYR\B738_RYR_static.obj'
            print(f"Intentando cargar objeto desde: {pth}")
            
            obj = xp.loadObject(pth)
            print(f"Objeto cargado: {obj}")
            
            if obj is None:
                print("ERROR: obj is None")
                return
            
            position = xp.worldToLocal(lat=42.897760, lon=-8.416466, alt=375)
            # Add: (pitch, heading, roll)
            position += (0,0,0)
            print(f"Posición calculada: {position}")
  
            result = xp.createInstance(obj, [])
            print(f"CreateInstance result: {result}")
            
            xp.instanceSetPosition(result, position, [])

        except Exception as e:
            print(f"Error in spawnAircraft: {e}")