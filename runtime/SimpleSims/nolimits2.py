# sim class for NoLimits2
from SimpleSims.nl2_simple_itf import CoasterInterface
import os
import logging as log
import traceback

class Sim():
    def __init__(self, sleep_func, frame, report_state_cb):
        self.sleep_func = sleep_func
        self.frame = frame
        self.report_state_cb = report_state_cb
        self.is_connected = False
        self.is_paused = False
        self.norm_factors = [1, 1, 1, 1, 1, 1]
        self.name = "NoLimits2"
        self.coaster = None

    def __del__(self):
        pass
   
    def set_state_callback(self, callback):
        self.state_callback = callback
        
    def load(self, loader):
        try:
            log.info("Starting NoLimits2 executing: " + loader)
            # os.startfile(r"C:\Users\memar\Desktop\Vr\NoLimits 2.lnk")
            os.startfile(loader)
            return("loading...") 
        except Exception as e:
            print(e)
            return(str(e))            
   
    def connect(self, sim_ip_address='127.0.0.1'):
        self.coaster = CoasterInterface(self.sleep_func)
        self.coaster.begin()
        log.info("Coaster trying to connect to " + sim_ip_address)
        while self.coaster.connect_to_coaster(sim_ip_address) == False:
            print("Trying to connect to",sim_ip_address)
            self.sleep_func(1)
        self.is_connected = True    

    def run(self):
        self.coaster.dispatch()
        self.is_paused = False

    def pause(self):
        self.is_paused = not self.is_paused
        self.coaster.set_pause(self.is_paused)
        
    def read(self):
        try:
            xform = self.coaster.get_telemetry(1)
            return xform
        except Exception as e:
            print("in read", str(e))
            return (0,0,0,0,0,0)

    def get_washout_config(self):
        return [0,0,0,0,0,0]
        
    def set_washout_callback(self, callback):
        pass