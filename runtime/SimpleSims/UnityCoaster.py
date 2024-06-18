# sim class for UnityCoaster
import os, sys
import socket
import logging as log
import traceback

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(RUNTIME_DIR))
from common.udp_tx_rx import UdpReceive

UNITY_IP_ADDR = '127.0.0.1' # this could be any reachable ip address
TELEMETRY_EVT_PORT = 10022 # Unity telemetry sends events to this port  
TELEMETRY_CMD_PORT = 10023 # send commands for Unity to this port

class Sim():
    def __init__(self, sleep_func, frame, report_state_cb):
        self.sleep_func = sleep_func
        self.frame = frame
        self.report_state_cb = report_state_cb
        self.is_connected = False
        self.is_paused = False
        self.norm_factors = [1, 1, 1, 1, 1, 1]
        self.name = "UnityCoaster"
        self.lift_height = 32  # max height of track in meters (used for heave calc)
        self.udp = UdpReceive(TELEMETRY_EVT_PORT) 

    def __del__(self):
        pass
   
    def set_state_callback(self, callback):
        self.report_state_cb = callback
        
    def load(self, loader):
        try:
            # loader is the exeuctable to run to start the unity coaster
            log.info("Starting Unity Coaster: " + loader)
            os.startfile(loader)
            return("loading...") 
        except Exception as e:
            print(e)
            return(str(e))            
   
    def connect(self, sim_ip_address=UNITY_IP_ADDR):
        self.report_state_cb("Attempting to connect to Unity coaster")
        ''' uncomment this when upde command port implimented in Unity   
        while  True:
            # the udp.send below tells unity that this interface is ready
            #   for now, it can be ignored if unity sends telemetry at startup

            self.udp.send('InitComs', (sim_ip_address, TELEMETRY_CMD_PORT))  
            self.sleep_func(.5)
            if self.udp.available() > 2 :
                log.info("Receiving telemetry events")
                break
        '''        
        self.report_state_cb("Receiving coaster telemetry")
        self.is_connected = True    

    def run(self):
        # code here to dispatch coaster
        self.is_paused = False

    def pause(self):
        self.is_paused = not self.is_paused
        # code to pause/unpause unity coaster
        
    def read(self):
        try:   
            msg = None
            xyzrpy =  [0,0,0,0,0,0]
            # ignore all but most recent telemetry msg
            while self.udp.available() > 0:
                msg = self.udp.get()
            if msg != None:
                data = msg[1].split(',')
                if len(data) > 8 and data[0] == 'telemetry': # NOTE CHANGED HEADER !!!
                    raw_telemetry = [float(ele) for ele in data[1:6]]
                    # print(','.join(str(t) for t in telemetry))
                    telemetry = self.process_telemetry(raw_telemetry)
                  # xyzrpy is: surge accel, sway accel, heave accel, roll rad, pitch rad, yaw rate
                    xyzrpy = [a * b for a, b in zip(telemetry, self.norm_factors)] # normalize the values if necessary
            return xyzrpy
        except Exception as e:
            print("in unity read:", str(e))
            print(traceback.format_exc())
            return (0,0,0,0,0,0)

    def get_washout_config(self):
        return [0,0,0,0,0,0]
        
    def set_washout_callback(self, callback):
        pass


    def process_telemetry(self, raw_telemetry):
        """
        process_telemetry is passed a transform list as: Surge (g), Sway (g), Heave (g), Roll, Pitch, Yaw
        this raw transform gets converted into normalized data where:
            translation values are linear acceleration relative to a rider on the coaster (all normalized)
            Roll and Pitch are euler angles, yaw is rotaton rate (all normalized)
              
        The transform uses ROS convention, positive values: X is forward, Y is left, Z is up,
        roll is right side down, pitch is nose down, yaw is CCW; all from perspective of person on platform.
        """ 

        # the following is derived from the working NoLimits code but needs reworking for Unity !!! 

        surge = gforce_from_raw_telemetry(raw_telemetry[0])
        if  surge >= 0:
            surge = sqrt( surge)
        else:
             surge = -sqrt(-surge)
             
        sway = gforce_from_raw_telemetry(raw_telemetry[1])

        if sway >= 0:
            sway = sqrt(sway)
        else:
            sway = -sqrt(-sway)

        heave = raw_telemetry[2] # this value is the lift height in meters 
        if heave > self.lift_height:
            self.lift_height = heave # adjust height if needed
        heave = ((heave * 2) / self.lift_height) -1
      
        roll =  raw_telemetry[3] # todo convert to accel and normalize 
        pitch = raw_telemetry[4] # todo convert to accel normalize  
       
        yaw = raw_telemetry[4] #
        self.flip=0
        if self.prev_yaw != None:
            # handle crossings between 0 and 360 degrees
            if yaw - self.prev_yaw > pi:
                yaw_rate = (self.prev_yaw - yaw) + (2*pi)
                self.flip= 2
            elif  yaw - self.prev_yaw < -pi:
                yaw_rate = (self.prev_yaw - yaw) - (2*pi)
                self.flip= -2
            else:
                yaw_rate = self.prev_yaw - yaw
            time_delta = time.time() - self.prev_time
            self.prev_time = time.time()
            dbgYr1 = yaw_rate
        else:
            yaw_rate = 0
            self.prev_yaw = yaw
        # the following code limits dynamic range nonlinearly
        if yaw_rate > pi:
           yaw_rate = pi
        elif yaw_rate < -pi:
            yaw_rate = -pi
        dbgYr2 = yaw_rate
        yaw_rate = yaw_rate / 2
        if yaw_rate >= 0:
            yaw_rate = sqrt(yaw_rate)
        elif yaw_rate < 0:
            yaw_rate = -sqrt(-yaw_rate)
        dbgYr3 = yaw_rate
        #self.dbg_yaw = format("%.3f, %.3f, %.3f, %.3f, %d" % (yaw, dbgYr1,dbgYr2,dbgYr3, flip))
        data = [surge, sway, heave, roll, pitch, yaw_rate]
        return data
         
    def gforce_from_raw_telemetry(self, val):
        pass # TODO!!!!