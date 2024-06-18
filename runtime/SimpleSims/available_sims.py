# list of sim name and paths for SimInterface platform controller
# sim module is the name of the python module defining the desired Sim class
# a jpg file with the same name as the module will be displayed when selected 

import os

default_sim = 0 # combo box will be set the this value at startup

# Desktop = r"C:/Users/memar/Desktop/Vr/" # location of startup icons (usually C:/Users/name/Desktop/ )
# Desktop = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop') + '/Vr/'
Desktop = 'Loading of this sim is not supporteed in this version: '
print(Desktop)

available_sims = [ #display name, itf module, image, full path to execute to load sim                
                    ["Unity Coaster", "UnityCoaster", "UnityCoaster.jpg", None],  # add shortcut to unity runtime here
                    ["NoLimits2 Coaster", "nolimits2", "nolimits2.jpg", "startNl2.bat"],
                    ["Space Coaster", "spacecoaster", "spacecoaster.jpg", Desktop + "SpaceCoaster.lnk"],
                    ["Test Sim", "TestSim", "test sim.jpg",  None]
                    # add another sim here
                    ]