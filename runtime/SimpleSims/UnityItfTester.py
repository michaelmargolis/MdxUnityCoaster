
""" 
UnityItfTester.py

Code to test UnityCoaster UDP interface

"""

from PyQt5 import QtWidgets, uic, QtCore, QtGui

import sys
import os
import time

import socket
import traceback

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(RUNTIME_DIR))
from common.udp_tx_rx import UdpReceive, UdpSend


IP_ADDR = '127.0.0.1' # Address of the UnityCoaster platform interface
TELEMETRY_EVT_PORT = 10022 # Unity telemetry sends events to this port  
TELEMETRY_CMD_PORT = 10023 # send commands for Unity to this port

USE_SPACE_MOUSE = True
if USE_SPACE_MOUSE:
    try:
        import SimpleSims.spacenavigator as sn # 6 dof mouse
    except:
        import spacenavigator as sn # 6 dof mouse

SCALE_FACTORS = ( 2,  # x accel (expected range +1 -2 g?
                  2,  # y accel  (expected range +- 2g)
                  16,    # height (half the height range)
                  30,    # roll  (expected range +- 30 degrees)
                  35,    # pitch (expected range +35 -30 degrees)
                  180 )   # yaw  (+- 180 degrees

DATA_PERIOD = 50  # ms between updates

slider_increments = (5)*6  # todo for slow moves

Ui_MainWindow, QtBaseClass = uic.loadUiType("SimpleSims/TestSim_frame.ui")

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True) #enable highdpi scaling
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True) #use highdpi icons

class Dof_Oscilate():
    # oscilates platform in a given DoF
    def __init__(self, frame_rate, rate_function):
        self.frame_rate = frame_rate
        self.rate_function = rate_function
        self.current_dof = -1 
        self.current_level = 0
        self.do_all_dof = False
        self.state = 0 # 0=0ff, 1=going up, 2=going down,3=returning to center 
    
    def set_dof(self, dof):
        if dof == 6: 
            # here if sequencing through all 6 dof
            self.do_all_dof = True
            dof = 0 # start with x
        self.current_dof = dof
        self.state = 1
        print("dof set to ", dof)
        self.start_time = time.time()
        
    def oscilate(self):
        # rate is time in secs for move from -1 to 1
        dur = (self.rate_function() * 0.0005) + .5
        # print("rate fun=", self.rate_function())
        step =  self.frame_rate / dur
        if self.state == 1:
            self.current_level += step
            if self.current_level > 1:
                self.state = 2
        elif self.state == 2:
            self.current_level -= step
            if self.current_level < -1:
                self.state = 3
        elif self.state == 3:
            self.current_level += step
            if self.current_level >= 0:
                self.state = 0
                print("dur was", time.time() - self.start_time)
                if self.do_all_dof:
                    if self.current_dof < 5:
                        self.current_dof  += 1
                        self.state = 1
                    else:
                        self.do_all_dof = False
             
           
        transform = [0,0,0,0,0,0]    
        if self.current_dof  >= 0 and  self.current_dof < 6:     
            transform[self.current_dof] = self.current_level
            return transform
        elif self.current_dof  > 5:
            print("todo sequential tranforms")
        return [0,0,0,0,0,0]  
        
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.event_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP event sender
        self.udp_event = UdpSend() # UDP event sender
        self.udp_command = UdpReceive(TELEMETRY_CMD_PORT) # UDP command receiver

        self.timer_data_update = None
        self.sn_avail = False  # space mouse
        self.time_interval = DATA_PERIOD / 1000.0
        self.slider_values = [0]*6  # the actual slider percents (-100 to 100)
        self.lagged_slider_values = [0]*6  # values used for calculating pressures

        self.transform = [0,0,-1,0,0,0] # this will be updated when connected to sim
        self.prev_info_text  = ''
        
        # configures
        self.configure_timers()
        self.configure_signals()
        self.configure_defaults()
        self.configure_buttons()   
        
        self.frame_rate = 0.05
        self.dof_oscilate = Dof_Oscilate(self.frame_rate, self.ui.sld_lag.value)
        self.timer_data_update.start(DATA_PERIOD) 

    def closeEvent(self, event):
        event.accept()   
       
    def configure_timers(self):
        self.timer_data_update = QtCore.QTimer(self) # timer services muscle pressures and data
        self.timer_data_update.timeout.connect(self.data_update)
        self.timer_data_update.setTimerType(QtCore.Qt.PreciseTimer)

    def configure_signals(self):
        self.ui.btn_centre.clicked.connect(self.centre_pos)
        self.ui.btn_load_pos.clicked.connect(self.load_pos)
        self.ui.cmb_repeated_move.activated.connect(self.move_combo_changed)

    def configure_defaults(self):
        if USE_SPACE_MOUSE:
            if len(sn.list_devices()) > 0:
                self.ui.txt_spacemouse.setText(sn.list_devices()[0])
            else:
                self.ui.txt_spacemouse.setText("Not found")
            self.sn_avail = sn.open()
        else:
            self.ui.gb_space_mouse.close()

    def configure_buttons(self):  
        #  button groups
        self.transfrm_sliders = [self.ui.sld_0, self.ui.sld_1, self.ui.sld_2, self.ui.sld_3, self.ui.sld_4, self.ui.sld_5  ]
        self.lag_indicators = [self.ui.pg_0, self.ui.pg_1, self.ui.pg_2, self.ui.pg_3, self.ui.pg_4, self.ui.pg_5]
        if USE_SPACE_MOUSE:
            self.mouse_rbuttons = [self.ui.rb_m_off, self.ui.rb_m_inc, self.ui.rb_m_abs]
            self.mouse_btn_group = QtWidgets.QButtonGroup()
            for i in range(len(self.mouse_rbuttons)):
               self.mouse_btn_group.addButton(self.mouse_rbuttons[i], i)
               
    def move_combo_changed(self, value):       
        print("combo changed:",  value)
        self.dof_oscilate.set_dof(value-1)
       
    def data_update(self):
        if  self.dof_oscilate and self.dof_oscilate.state > 0:
            xform = self.dof_oscilate.oscilate()
            if self.dof_oscilate.state == 0:
                self.ui.cmb_repeated_move.setCurrentIndex(0)
            
        else:     
            percent_delta = 100.0 / (self.ui.sld_lag.value() / DATA_PERIOD)  # max percent change for each update
            for idx, slider in enumerate(self.transfrm_sliders):
                self.slider_values[idx] = slider.value()
                if not self.ui.chk_instant_move.isChecked():  # moves deferred if checked (todo rename to chk_defer_move)
                    if self.lagged_slider_values[idx] + percent_delta <= self.slider_values[idx]:
                        self.lagged_slider_values[idx] += percent_delta
                    elif self.lagged_slider_values[idx] - percent_delta >=  self.slider_values[idx]:
                        self.lagged_slider_values[idx] -= percent_delta
                    else:
                        self.lagged_slider_values[idx] = self.slider_values[idx]
                if self.lagged_slider_values[idx] ==  self.slider_values[idx]:
                    self.lag_indicators[idx].setValue(1)
                else:
                    self.lag_indicators[idx].setValue(0)
            # print("raw sliders", self.slider_values, "lagged:", self.lagged_slider_values )
            if self.ui.rb_m_abs.isChecked():
                mouse_xform = self.get_mouse_transform()
                for i in range(len(self.transfrm_sliders)):
                    self.transfrm_sliders[i].setValue( int(mouse_xform[i] * 100))
            if self.ui.rb_m_inc.isChecked(): 
                # self.get_mouse_transform()
                print("not implimented")     
            xform = [x * .01 for x in self.lagged_slider_values]
        for i in range(len(self.transform)):  
            self.transform[i] = xform[i] * SCALE_FACTORS[i]
        self.transform[2] += SCALE_FACTORS[2] # offset z value so values ?=0  
        xform_str =  ", ".join([f"{value:.2f}" for value in self.transform])
        if self.prev_info_text != xform_str:
            self.ui.txt_info.setText(xform_str)
            self.prev_info_text = xform_str
            
        self.udp_event.send(f"{'telemetry,'} {xform_str}".encode(), (IP_ADDR, TELEMETRY_EVT_PORT)) 
        # todo if command then print

  
    def get_mouse_transform(self):
        # returns list of normalized floats
        state = sn.read()
        transform = [state.x, state.y, state.z, state.roll, state.pitch, state.yaw]
        return transform
  
    def centre_pos(self):
        for slider in self.transfrm_sliders:
            slider.setValue(0)

    def load_pos(self):
        for idx, slider in enumerate(self.transfrm_sliders):
            if( idx == 2):
                slider.setValue(-100)
            else:
                slider.setValue(0)


if __name__ == '__main__':

    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    app.exec_() #mm added underscore
    win.close()
    app.exit()  
    sys.exit()
