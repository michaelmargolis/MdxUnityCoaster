""" Serial remote control """

import sys
import serial
import time
import serial.tools.list_ports
import threading
import os
try:
    from queue import Queue
except ImportError:
    from Queue import Queue

import logging
log = logging.getLogger(__name__)

class SerialRemote(object):
    """ provide action strings associated with buttons on serial remote control."""
    auto_conn_str = "MdxRemote_V1"  # remote responds with this when promted for version

    def __init__(self, actions):
        """ Call with dictionary of action strings.
 
        Keys are the strings sent by the remote,
        values are the functons to be called for the given key.
        """
        self.ser = None
        self.ser_buffer = ""
        self.baud_rate = 57600
        self.timeout_period = 2
        self.is_connected = False
        self.actions = actions
        self.RxQ = Queue()
        t = threading.Thread(target=self.rx_thread, args=(self.ser, self.RxQ,))
        t.daemon = True
        t.start()

    def rx_thread(self, ser, RxQ):
        """ Auto detect com port and put data in given que."""

        self.RxQ = RxQ
        self.ser = ser
        port = None
        while port == None:
            port = self._search()
        self.RxQ.put("Detected Remote Control on %s" % port)
        while True:
            #  wait forever for data to forward to client
            try:
                result = self.ser.readline().decode()
                if len(result) > 0:
                    self.RxQ.put(result)
            except:
                log.warning("serial remote error, trying to reconnect")
                self.RxQ.put("Reconnect Remote Control")
                while True:
                    if self._connect(port):
                        log.debug("sending detected msg")
                        self.RxQ.put("Detected Remote Control on %s" % port)
                        break
    def _search(self):
        for p in sorted(list(serial.tools.list_ports.comports())):
            port = p[0] 
            #print port, len(port)
            if os.name == 'posix' or len(port) < 6:  # ignore ports > 99 on windows
                # self.RxQ.put("Looking for Remote on %s" % port)
                if self._connect(port):
                    # log.info("found remote on %s", port)
                    return port
        return None

    def _connect(self, portName):
        # Private method try and connect to the given portName.

        self.connected = False
        self.ser = None
        result = ""
        try:
            self.ser = serial.Serial(portName, self.baud_rate)
            self.ser.timeout = self.timeout_period
            log.info("Looking for remote on %s", portName)
            #self.ser.setDTR(False)
            if not self.ser.isOpen():
                log.error("Serial remote err: %s, already open in another process", portName)
                self.ser = None
                return False

            for i in range(3): 
                self.ser.write(b'V\n')
                self.ser.flush()
                time.sleep(.5)
                result = self.ser.readline().decode()
                if len(result) > 0:
                    if SerialRemote.auto_conn_str in result or "intensity" in result or "reset" in result or 'pause' in result:
                        self.connected = True
                        log.info("Found remote on %s", portName)
                        return True
            self.ser.close()
        except:
            self.ser = None
            pass
        return False

    def _send_serial(self, toSend):
        # private method sends given string to serial port
        if self.ser and self.connected:
            if self.ser.isOpen() and self.ser.writable:
                self.ser.write(toSend)
                self.ser.flush()
                return True
        return False

    def send(self, toSend):
        #  print " ".join(str(ord(char)) for char in toSend)
        self._send_serial(toSend)

    def service(self):
        """ Poll to service remote control requests."""
        while not self.RxQ.empty():
            msg = self.RxQ.get().rstrip()
            if "Detected Remote" in msg or "Reconnect Remote" in msg or "Looking for Remote" in msg:
                self.actions['detected remote'](msg)
            elif SerialRemote.auto_conn_str not in msg:  # ignore remote ident
                if "intensity" in msg:
                    # TODO add error checking below
                    m, intensity = msg.split('=', 2)
                    # print m, "=", intensity
                    self.actions[m](msg)
                else:
                    self.actions[msg]()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%H:%M:%S')
    log.info("Starting serial remote test")

    def detected_remote(info):
        print(info)
    def activate():
        print("activate")
    def deactivate():
        print("deactivate")
    def pause():
        print("pause")
    def dispatch():
        print("dispatch")
    def reset_vr():
        print("reset vr")
    def deactivate():
        print("deactivate")
    def emergency_stop():
        print("estop")
    def set_intensity(intensity):
        print("intensity ", intensity)

    actions = {'detected remote': detected_remote, 'activate': activate,
               'deactivate': deactivate, 'pause': pause, 'dispatch': dispatch,
               'reset': reset_vr, 'emergency_stop': emergency_stop, 'intensity' : set_intensity}

    RemoteControl = SerialRemote(actions)
    while True:
        RemoteControl.service()
        time.sleep(.5)
