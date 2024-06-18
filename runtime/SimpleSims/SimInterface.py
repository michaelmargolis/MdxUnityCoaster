
""" 
SimInterface.py

Code to drive  platform from various sims using a simple protocol

protocol: "xyzrpy,x,y,z,roll,pitch,yaw\n"
where parameters are float values ranging between -1 and 1
"""

from PyQt5 import QtWidgets, uic, QtCore, QtGui
from PyQt5.QtWidgets import QMessageBox
import sys
import os
import time
import logging as log
import logging.handlers
import argparse
import operator  # for map sub
import importlib
import socket
import traceback
import math # for conversion of radians to degrees

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(RUNTIME_DIR))

import common.gui_utils as gutil # for sleep QT func
from kinematics.dynamics import Dynamics
from kinematics.kinematicsV2 import Kinematics
from kinematics.cfg_SlidingActuators import *
from RemoteControls.RemoteControl import RemoteControl

import output.d_to_p as d_to_p
from output.muscle_output import MuscleOutput

import SimpleSims.available_sims  as sims  # sims to be loaded are defined in this module

    
LATENCY = 0
DATA_PERIOD =  50 - LATENCY  # ms between samples

# fixme config from system_config is not being used
ECHO_UDP_IP = "127.0.0.1"
# ECHO_UDP_IP = "255.255.255.255"
# ECHO_UDP_IP = "192.168.1.107"
# ECHO_UDP_IP = "192.168.1.180"
# ECHO_UDP_IP = "192.168.4.1"
echo_address = ((ECHO_UDP_IP, 10020),) # you can add additional echo Ip addresses to this list

slider_config_module = "cfg_SlidingActuators"
chair_config_module = "cfg_SuspendedChair"

qtcreator_file  = "SimpleSims/SimInterface_H.ui"
Ui_MainWindow, QtBaseClass = uic.loadUiType(qtcreator_file)

QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True) #enable highdpi scaling
QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True) #use highdpi icons
        
class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, festo_ip, is_dpi_scaled, selected_platform):
        QtWidgets.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        self.festo_ip = festo_ip
        self.is_dpi_scaled = is_dpi_scaled  

        self.echo_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
        self.echo_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) # enable broadcast
        try:
            from simserver_cfg import simserver_addr
            self.simserver_addr = simserver_addr
        except:
            self.simserver_addr = '127.0.0.1'    
        print("sim server:", self.simserver_addr)

        self.timer_data_update = None
        self.is_ready = False # True when platform config is loaded
        self.sn_avail = False  # space mouse
        self.sim = None
        self.time_interval = DATA_PERIOD / 1000.0
        self.slider_values = [0]*6  # the actual slider percents (-100 to 100)
        self.lagged_slider_values = [0]*6  # values used for calculating pressures

        self.transform = (0,0,-1,0,0,0) # this will be updated when connected to sim
        self.target_pressures = [] # pressures sent to festo

        self.csv_outfile = None
        
        self.is_output_enabled = False
        self.ui.txt_festo_ip.setText(festo_ip)
        
        self.create_activation_toggle()
        self.RemoteControl = None
        self.state = 'disabled'
        
        # configures
        self.configure_timers()
        self.configure_signals()
        self.configure_defaults()
        self.configure_buttons()   
        self.configure_washout()
        self.configure_platform(selected_platform)


    def closeEvent(self, event):
        log.info("User exit")
        if self.sim:
            self.sim = None
        event.accept()
   
    def create_activation_toggle(self):
        if self.is_dpi_scaled:
            padding_adj = 0  
        else:
            padding_adj = -15
        self.chk_activate = gutil.ToggleSwitch(self.ui.widget_activate, "Activated", "Deactivated", padding_adj)
        self.chk_activate.setGeometry(QtCore.QRect(0, 0, 240, 38))
        font = QtGui.QFont()
        font.setPointSize(12)
        self.chk_activate.setFont(font)
        self.chk_activate.setChecked(False)  
        
    def configure_timers(self):
        self.timer_data_update = QtCore.QTimer(self) # timer services muscle pressures and data
        self.timer_data_update.timeout.connect(self.data_update)
        self.timer_data_update.setTimerType(QtCore.Qt.PreciseTimer)

    def configure_signals(self):
        self.ui.btn_load_config.clicked.connect(self.load_config)
        self.ui.btn_load_sim.clicked.connect(self.load_sim)
        self.ui.btn_connect_sim.clicked.connect(self.connect_sim)
        
        self.ui.btn_run.clicked.connect(self.button_clicked)
        self.ui.btn_pause.clicked.connect(self.button_clicked)
        self.chk_activate.clicked.connect(self.button_clicked)  #(self.activation_clicked)
        
        self.ui.chk_capture_csv.stateChanged.connect(self.capture)
        self.ui.rb_chair.clicked.connect(self.chair_selected)
        self.ui.rb_slider.clicked.connect(self.slider_selected)
        self.ui.cmb_sim_select.activated.connect(self.sim_combo_changed)
        self.ui.tabWidget.currentChanged.connect(self.tab_changed)

        # self.ui.rb_activate.clicked.connect(self.button_clicked)
        # self.ui.rb_deactivate.clicked.connect(self.button_clicked)

    def configure_defaults(self):
        # self.ui.grp_platform_control.hide()
        self.ui.lbl_sim_status.setText("Choose Platform Type then click 'Load Config'")
        # self.slider_selected() # default platform
        self.chair_selected() # default platform
        print('Available Sims:')
        for i in range(len(sims.available_sims)):
            print('\t' + sims.available_sims[i][0])
            self.ui.cmb_sim_select.addItem(sims.available_sims[i][0])
        self.ui.cmb_sim_select.setCurrentIndex(sims.default_sim)
        self.sim_combo_changed() # init to default values

    def configure_buttons(self):        
        self.ui.tab_platform.setEnabled(False)
        self.ui.grp_sim.setEnabled(False) 
        #  button groups 
        self.gain = [self.ui.sld_gain_0, self.ui.sld_gain_1, self.ui.sld_gain_2, self.ui.sld_gain_3, self.ui.sld_gain_4, self.ui.sld_gain_5  ]        
        self.transfrm_levels = [self.ui.sld_xform_0, self.ui.sld_xform_1, self.ui.sld_xform_2, self.ui.sld_xform_3, self.ui.sld_xform_4, self.ui.sld_xform_5  ]
        
    def configure_kinematics(self):
        # load_config() must be called before this method 
        self.k = Kinematics()
        self.cfg.calculate_coords()

        self.k.set_geometry(self.cfg.BASE_POS, self.cfg.PLATFORM_POS)
        if self.cfg.PLATFORM_TYPE == "SLIDER":
            self.k.set_slider_params(self.cfg.joint_min_offset, self.cfg.joint_max_offset, self.cfg.strut_length, self.cfg.slider_angles, self.cfg.slider_endpoints)
            self.is_slider = True
        else:
            self.k.set_platform_params(self.cfg.MIN_ACTUATOR_LEN, self.cfg.MAX_ACTUATOR_LEN, self.cfg.FIXED_LEN)
            # self.muscle_output.set_platform_params(self.cfg.MIN_ACTUATOR_LEN, self.cfg.MAX_ACTUATOR_LEN, self.cfg.FIXED_LEN)
            self.is_slider = False
            
        self.invert_axis = self.cfg.INVERT_AXIS 
        self.swap_roll_pitch = self.cfg.SWAP_ROLL_PITCH   

        self.dynam = Dynamics()        
        self.dynam.begin(self.cfg.limits_1dof,"shape.cfg")
        
    def configure_platform(self, selected_platform):
        if selected_platform == 'CHAIR':
            self.chair_selected()
            self.load_config()
        elif selected_platform == 'SLIDER':
            self.slider_selected()
            self.load_config()

    def init_remote_controls(self):
        self.actions = {'activate':  self.remote_activate, 'deactivate': self.remote_deactivate,
                   'pause': self.remote_pause, 'dispatch': self.remote_run, 'reset': self.reset_vr, 
                   'emergency_stop': self.remote_deactivate, 'intensity' : self.remote_intensity,
                   'detected remote': self.detected_remote,  'payload' : self.action_ignore, 
                   'show_parks' : self.action_ignore, 'scroll_parks' : self.action_ignore}       
        self.local_control = None
        if os.name == 'posix' and os.uname()[4].startswith("arm"):
            try:
                import RPi.GPIO as GPIO 
                import RemoteControls.local_control_itf as local_control_itf
                from common.dialog import ModelessDialog
                self.dialog = ModelessDialog(self)
                pin_defines = 'dual_reset_pcb_pins' # cfg.PI_PIN_DEFINES
                if pin_defines != 'None':
                    self.local_control = local_control_itf.LocalControlItf(self.actions, pin_defines, self.cfg.INTENSITY_RANGE, self.cfg.LOAD_RANGE)
                    log.info("using local hardware switch control %s", pin_defines)
                    if self.local_control.is_activated():
                        self.dialog.setWindowTitle('Emergency Stop must be down')
                        self.dialog.txt_info.setText("Flip Emergency Stop Switch down to proceed")
                        self.dialog.show()
                        gutil.sleep_qt(5)
                        self.dialog.close()
                        while self.local_control.is_activated():
                            gutil.sleep_qt(.5)
            except ImportError:
                qm = QtWidgets.QMessageBox
                result = qm.question(self, 'Raspberry Pi GPIO problem', "Unable to access GPIO hardware control\nDo you want to to continue?", qm.Yes | qm.No)
                if result != qm.Yes:
                    raise
                else:
                    log.warning("local hardware switch control will not be used")
        else:
            from RemoteControls.RemoteControl import RemoteControl
            # self.RemoteControl = RemoteControl(self.actions)  # uncomment this for UDP or Serial remote control
            log.info("Serial remote control NOT instantiated")
        
    """   remote control event handlers   """   
    def action_ignore(self, argument):
        print("ignored remote request", argument)
        
    def detected_remote(self, argument):
        print("Detected Remote Control")

    def remote_activate(self):
        self.chk_activate.setChecked(True)
        self.update_state('enabled') 
    def remote_deactivate(self):   
        self.chk_activate.setChecked(False)       
        self.update_state('disabled')  
    
    def remote_pause(self):
        self.update_state('paused')      
    def remote_run(self):
       self.update_state('running')     
    def remote_intensity(self, intensity):
        if type(intensity) == str and "intensity=" in intensity:
            header, intensity = intensity.split('=', 2)
            intensity = int(intensity) - 50 # adjust local control range from 50 to 150
            self.ui.sld_gain_master.setValue(intensity)        
        
    """ gui button handlers   """
    def button_clicked(self, sender):
        source = self.sender()
        if source == self.ui.btn_run:
            self.update_state('running')
        elif source == self.ui.btn_pause:
            self.update_state('paused')
        elif source ==  self.chk_activate:
            if source.isChecked():
                self.update_state('enabled')              
            else:
                self.update_state('disabled')

    """ gui state handlers """
    def update_state(self, new_state):
        if new_state == self.state:
            return
        print("in update state, old state was {}, new state {}".format(self.state, new_state))    
        if new_state == 'enabled':
            self.enable_platform()
            self.ui.btn_pause.setEnabled(True)
            self.ui.btn_run.setEnabled(True)
            self.state = new_state  
        elif new_state == 'disabled':
            self.ui.btn_pause.setEnabled(False)
            self.ui.btn_run.setEnabled(False)
            self.reset()
            self.disable_platform()
            self.state = new_state              
        elif new_state == 'running' and self.state != 'disabled':
            print('run')
            self.ui.btn_pause.setChecked(False)
            self.ui.btn_run.setChecked(True)
            self.run()
            self.state = new_state              
        elif new_state == 'paused' and self.state != 'disabled':
            print('pause') 
            self.ui.btn_run.setChecked(False)
            self.ui.btn_pause.setChecked(True)
            self.pause()
            self.state = new_state  
        else:
            print("state change from {} to {} was ignored".format(self.state, new_state))
            return
        
        self.report_state(self.state)    
  
   
    def tab_changed(self, tab_index):
        if tab_index == 0:
            #self.ui.grp_platform_control.hide()
            self.ui.widget_activate.setEnabled(False)
        else:
            if self.sim and self.sim.is_connected: 
                self.ui.widget_activate.setEnabled(True) 

            else:
                self.ui.tabWidget.setCurrentIndex(0) # don't allow change
          
    def configure_washout(self):
        nbr_plots = 6
        traces_per_plot = 2
        titles = ('x (surge)', 'y (sway)', 'z (heave)', 'roll', 'pitch', 'yaw')
        legends = ('raw', 'washed')
   
    def do_washout(self, transform):       
        washed = []
        for t in transform:
            washed.append(t* 1.1)
        data = [transform, washed]
        # self.plotter.plot(data)
        
    def data_update(self):
        if not self.is_ready:
            print("ignoring update because not ready")
            return # don't output if distance to pressure file has not been loaded

        elif self.sim:
            self.transform = self.sim.read()
            if not self.sim.is_connected:
                self.report_state("Sim is not connected, is it running")
            if self.transform:
                self.move(self.transform)
            
            if self.RemoteControl:            
                self.RemoteControl.service()
            if self.local_control:
                self.local_control.service()    

                            
    def move(self, transform):
        if self.is_output_enabled:
            self.do_washout(transform)
            transform = [inv * axis for inv, axis in zip(self.invert_axis, transform)]          
            master_gain = self.ui.sld_gain_master.value() *.01     
            for idx in range(6): 
                gain = self.gain[idx].value() * master_gain      
                percent =  round(transform[idx]*gain)  
                self.transfrm_levels[idx].setValue(percent) # set the UI transform indicators
                self.dynam.set_gain(idx, gain *.01)
            request = self.dynam.regulate(transform) # convert normalized to real values
            if self.swap_roll_pitch:
                # swap roll, pitch and x,y if set in config
                request[0],request[1], request[3],request[4] =  request[1],request[0],request[4], request[3] 
            
            percents = self.k.actuator_percents(request)
            # print("request:", request, "percents:", percents)
           
            #percents = remap_valves(percents)
            distances = self.k.actuator_lengths(request)
            if self.is_slider:
                self.muscle_output.move_percent(percents)            
            else:
                self.muscle_output.move_distance(distances)
            self.echo( request.tolist(), distances, self.k.get_pose())

    def sim_combo_changed(self):       
        idx = self.ui.cmb_sim_select.currentIndex()
        self.selected_sim_name = sims.available_sims[idx][0]
        self.selected_sim_class =  sims.available_sims[idx][1]
        img = "images/" + sims.available_sims[idx][2]
        self.sim_loader = sims.available_sims[idx][3]
        self.ui.lbl_sim_image.setPixmap(QtGui.QPixmap(img))
        
        
    def instantiate_sim(self):
        if not self.sim:
            sim_path = "SimpleSims." + self.selected_sim_class
            print("selected sim is " + self.selected_sim_class, "path is", sim_path)
            try:
                sim_module = importlib.import_module(sim_path)
                self.sim = sim_module.Sim(gutil.sleep_qt, self.ui.tab_sim, self.report_state)
                log.info("Instantiated sim: " + self.sim.name) 
            except Exception as e:
                print(e)
                print(traceback.format_exc())
                
    def load_sim(self):       
        if not self.sim:
           self.instantiate_sim()
        try:
            if not self.sim_loader:
                self.sim.load(None)  # if no OS loader then call sim load explicitly
            else:
                self.sim.load(self.sim_loader)            
                self.report_state("Loading") 
        except Exception as e:            
            print(e)
            print(traceback.format_exc())

            
    def connect_sim(self):    
        if not self.sim:
           self.instantiate_sim()    
        if self.sim:
            # self.instantiate_sim()  
            # self.sim.set_state_callback(self.report_state )  
            self.sim.connect(self.simserver_addr)  # this will block until sim is connected
            self.ui.tab_platform.setEnabled(True)
            self.ui.tab_load.setEnabled(False)
            self.ui.tabWidget.setCurrentIndex(1)  
     
            washout_times = self.sim.get_washout_config()
            for idx in range(6):
                self.dynam.set_washout(idx, washout_times[idx]) 
            self.sim.set_washout_callback(self.dynam.get_washed_telemetry)

            self.is_ready = True;
            self.sim.run()
            self.timer_data_update.start(DATA_PERIOD) 
            log.info("Started {}ms data update timer".format(DATA_PERIOD) ) 
                
             

    def report_state(self, state_info):
        self.ui.lbl_sim_status.setText(self.selected_sim_name + ": " + state_info)         

    def run(self):
        self.sim.run()

    def pause(self):
        self.sim.pause()
        
    def reset(self):
        try:
            self.sim.reset()
        except AttributeError:
            print('Ignoring reset cmd, sim does not have reset capability')  

    def reset_vr(self):
        print("reset vr not yet implimented")

    def enable_platform(self):
        self.park_platform(False)
        actuator_distances = self.k.actuator_lengths(self.transform)
        print("enabling")
        self.slow_move(self.cfg.DISABLED_DISTANCES, actuator_distances, self.cfg.DISABLED_XFORM, self.transform, 100)
        # todo check sensor distance reading here to auto calibrate load ???
        if not self.is_output_enabled:
            self.is_output_enabled = True
            log.debug("Platform Enabled")
        print("Festo pressures", self.muscle_output.festo.get_pressure())    

    def disable_platform(self):
        print("disabling");
        if self.is_output_enabled:
            self.is_output_enabled = False
            log.debug("Platform Disabled")
        # self.set_activation_buttons(False) fixme: needed when using physical buttons so gui is in sync
        actuator_distances = self.k.actuator_lengths(self.transform)
        self.slow_move(actuator_distances, self.cfg.DISABLED_DISTANCES, self.transform, self.cfg.DISABLED_XFORM,100)
        self.park_platform(True)
         
    def slow_move(self, begin_dist, end_dist, begin_xform, end_xform, rate_mm_per_sec):
        # moves from the given begin to end distances at the given duration
        #  caution, this moves even if disabled
        interval = .05  # ms between steps
        distance = max([abs(j-i) for i,j in zip(begin_dist, end_dist)])
        dur = abs(distance) / rate_mm_per_sec
        steps = int(dur / interval)
        xform_steps = [(j-i)/steps for i,j in zip(begin_xform, end_xform)]
        if steps < 1:
            self.muscle_output.move_distance(end_dist)
        else:
            current_dist = begin_dist
            current_xform = begin_xform
            print("moving from", begin_dist, "to", end_dist, "steps", steps)
            # print("xform from", begin_xform, "to", end_xform)
            # print "percent", (end[0]/start[0]) * 100
            delta = [float(e - s)/steps for s, e in zip(begin_dist, end_dist)]
            for step in range(steps):
                current_dist = [x + y for x, y in zip(current_dist, delta)]
                current_dist = np.clip(current_dist, 0, 6000)
                self.muscle_output.move_distance(current_dist)
                current_xform = [ i+j for i, j in zip(current_xform, xform_steps)]
                self.echo(current_xform, current_dist, self.k.get_pose())
                # print("echoing", [round(x,1) for x in current_xform],  current_dist)
                gutil.sleep_qt(interval)
                
    def swell_for_access(self):
        if self.cfg.HAS_PISTON and not self.is_output_enabled:
            #Briefly raises platform high enough to insert access stairs and activate piston
            log.debug("Start swelling for access")
            self.slow_move(self.cfg.DISABLED_DISTANCES, self.cfg.PROPPING_DISTANCES,  self.cfg.DISABLED_XFORM, self.cfg.PROPPING_XFORM, 100)
            gutil.sleep_qt(3) # time in seconds in up pos
            self.slow_move(self.cfg.PROPPING_DISTANCES, self.cfg.DISABLED_DISTANCES,  self.cfg.PROPPING_XFORM, self.cfg.DISABLED_XFORM, 100)
            log.debug("Finished swelling for access")
   
        
    def park_platform(self, do_park):
        if do_park:
            if self.cfg.HAS_PISTON:
                self.muscle_output.set_pistion_flag(False)
                log.debug("Setting flag to activate piston to 0")
                log.debug("TODO check if festo msg sent before delay")
                gutil.sleep_qt(0.5)
            if self.cfg.HAS_BRAKE:
               self.muscle_output.set_brake(True)
            # self.ui.lbl_parked.setText("Parked")
        else:  #  unpark
            if self.cfg.HAS_PISTON:
                self.muscle_output.set_pistion_flag(True)
                log.debug("setting flag to activate piston to 1")
            if self.cfg.HAS_BRAKE:
                self.muscle_output.set_brake(False)
            # self.ui.lbl_parked.setText("")
        log.debug("Platform park state changed to %s", "parked" if do_park else "unparked")

    def set_intensity(self, intensity):
        # argument is either string as: "intensity=n"  or just 'n' where n ranges is '50'-'150'
        # if called while waiting-for-dispatch and if encoders are not enabled, scales and sets d to P index:
        # otherwise sets value in dynamics module to scale output values
        # payload weight passed to platform for deprecated method only used in old platform code
        
        if type(intensity) == str and "intensity=" in intensity:
            header, intensity = intensity.split('=', 2)
        self.intensity = int(intensity) 

        if True: # self.output_gui.encoders_is_enabled() or self.agent_mux.get_ride_state() != RideState.READY_FOR_DISPATCH :
            self.dynam.set_intensity(self.intensity)
            # self.show_intensity_payload()            
    def centre_pos(self):
        self.move((0,0,0,0,0,0))

    def load_pos(self):
        self.move((0,0,-1,0,0,0))

    def echo(self, transform, distances, pose):
        # print(transform, distances)
        t = [""]*6
        for idx, val in enumerate(transform):
            if idx < 3:
                if idx == 2:
                    val = -val #  TODO invert z ?
                t[idx] = str(round(val))
            else:
                t[idx] = "{:.3f}".format(val)        
        # req_msg = "request," + ','.join(str(round(t*180/math.pi, 1)) for t in transform)
        req_msg = "request," + ','.join(t)
        dist_msg = ",distances," +  ",".join(str(int(d)) for d in distances)
        pose_msg = ",pose," + ",".join([";".join(map(lambda x: format(x, ".1f"), row)) for row in pose])
        #  "1.0,2.0,3.0;4.0,5.0,6.0;7.0,8.0,9.0" lst = [[float(x) for x in row.split(",")] for row in s.split(";")] 
        msg = req_msg + dist_msg + pose_msg + "\n"
        for i in range(len(echo_address)):
            # print("sending",  echo_address[i], msg)
            self.echo_sock.sendto(bytes(msg, "utf-8"), echo_address[i])
  
        if self.csv_outfile:
            self.csv_outfile.write(msg)

    def capture(self):
        if self.ui.chk_capture_csv.isChecked():
            fname = self.ui.txt_csv_fname.text()
            self.open_file(fname)
        else:
            if self.csv_outfile:
                self.csv_outfile.close()
                self.csv_outfile = None

    def open_file(self, fname):
            if os.path.isfile(fname):
                reply = QMessageBox.question(self, 'Opening exisitng file', "Delete old data before adding new messages?", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
                if reply == QMessageBox.Yes:
                    self.csv_outfile = open(fname, 'w')
                    header = "'mm/rad','surge','sway','heave','roll','pitch','yaw'\n"
                    self.csv_outfile.write(header)
                elif reply == QMessageBox.No:
                    self.csv_outfile = open(fname, 'a')
                elif reply == QMessageBox.Cancel:
                    return
            else:
                # here if file doesnt exist
                self.csv_outfile = open(fname, 'w')

    def chair_selected(self):
        self.ui.txt_config_fname.setText(chair_config_module)
        self.ui.lbl_platform_image.setPixmap(QtGui.QPixmap("images/chair_small.jpg"))

    def slider_selected(self):
        self.ui.txt_config_fname.setText(slider_config_module)
        self.ui.lbl_platform_image.setPixmap(QtGui.QPixmap("images/slider_small.jpg"))
            
    def load_config(self):
        cfg_path =  'kinematics.' + self.ui.txt_config_fname.text()
        try:        
            cfg = importlib.import_module(cfg_path)
            self.cfg = cfg.PlatformConfig()
            # self.cfg.calculate_coords() # this is called in configure_kinematics
            self.DtoP = d_to_p.D_to_P(200) # argument is max distance 
            self.muscle_output = MuscleOutput(self.DtoP.distance_to_pressure, self.festo_ip)
            self.configure_kinematics()
            # load distance to pressure curves from file
            if self.DtoP.load(self.cfg.DISTANCE_TO_PRESSURE_TABLE): 
                print("todo: add option for polynomial instead of lookup?")
            self.ui.grp_sim.setEnabled(True) 
            self.ui.lbl_sim_status.setText("Click 'Load Sim' if not already running\nClick 'Connect' when sim is loaded") 
            self.init_remote_controls()    
            self.ui.btn_load_config.setEnabled(False)
            self.ui.btn_load_config.setText("Config Loaded")
                      
        except Exception as e:
            print(str(e) + "\nunable to import cfg from:", cfg_path)
            print(traceback.format_exc())

            
def start_logging(level):
    log_format = log.Formatter('%(asctime)s,%(levelname)s: %(message)s')
    logger = log.getLogger()
    logger.setLevel(level)

    file_handler = logging.handlers.RotatingFileHandler("SimInterface.log", maxBytes=(10240 * 5), backupCount=2)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    console_handler = log.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)


def man():
    parser = argparse.ArgumentParser(description='SimInterface\nA test environment for Mdx motion platform')
    parser.add_argument("-l", "--log",
                        dest="logLevel",
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the logging level")
    parser.add_argument("-f", "--festo_ip",
                        dest="festoIP",
                        help="Set IP address of Festo controller")                        
    parser.add_argument("-p", "--platform_kinematics",
                        dest="platform_kinematics",
                        choices=['CHAIR', 'SLIDER'],
                        help="Select platform kinematics (CHAIR OR SLIDER)")

    return parser


if __name__ == '__main__':
    # multiprocessing.freeze_support()
    args = man().parse_args()
    if args.logLevel:
        start_logging(args.logLevel)
    else:
        start_logging(log.INFO)

    log.info("Python: %s, qt version %s", sys.version[0:5], QtCore.QT_VERSION_STR)
    log.info("Starting SimInterface")

    app = QtWidgets.QApplication(sys.argv)
    
    is_dpi_scaled = round(app.primaryScreen().physicalDotsPerInch()*100) != round(app.primaryScreen().logicalDotsPerInch()*100)

    if args.festoIP:
        win = MainWindow(args.festoIP, is_dpi_scaled, args.platform_kinematics)
    else:
        win = MainWindow('192.168.0.10', is_dpi_scaled, args.platform_kinematics)
    win.show()
    app.exec_() #mm added underscore

    log.info("Exiting\n")
    log.shutdown()
    win.close()
    app.exit()  
    sys.exit()
