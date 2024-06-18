""" 
plot itf.py

init:
pass nbr plots, list of titles (one per plot)
list of legends, one pre trace if more than one trace
list of min/max tuples, one for each plot, will autorange if no minmax

plot:
  list of values for each plot
  default group = plots -  all traces for each plot grouped together in a list  
  group =  traces - traces for each plot grouped togeter  
  
  examples: three plots with two traces
  in each plot, the first trace is odd, other trace is even
  

    plot([[1,2], [3,4],[5,6]])  # group = plots
    plot([[1,3,5],[2,4,6]])  # group = traces  
    
  two traces on one plot:
     plot([[1,2]]])  # group = traces 
  two plots with one trace
  plot( [[1],[2]] )  # group = plots
  
  msg format: comma seperates plot names in prefix
    semicolon seperates plot groups in plot values
    comma seperates trace values within plot group 
  
"""
import socket
import datetime # only used to create default main title
import traceback

PLOT_ADDR = ('127.0.0.1',10029)  # default plotter on same PC 

class PlotItf():
    # def __init__(self, main_title, nbr_plots, titles, traces_per_plot, legends=[''], minmax=None, grouping='traces' ):
    def __init__(self, nbr_plots, traces_per_plot, main_title=None, plot_titles=None, legends=None, minmax=None, grouping='traces' ):   
        try:
            if main_title == None:
                self.main_title = "Plot created {}".format(datetime.datetime.now().strftime("%I:%M%p on %B %d %Y"))
            else:
                self.main_title = main_title
            print(main_title)    
            self.main_title = self.main_title.replace(',', ' ')     
            self.nbr_plots = nbr_plots
            if plot_titles == None:
                plot_titles = []
                for i in range(nbr_plots):
                    plot_titles.append("Plot {}".format(i+1))
            elif len(plot_titles) != nbr_plots:
               raise ValueError("Expected {} titles, got {}".format(self.nbr_plots, len(plot_titles)))
            self.plot_titles = plot_titles
            self.nbr_traces = traces_per_plot
            if legends == None:
                legends=[]
                for i in range(traces_per_plot):
                    legends.append("trace {}".format(i+1))
            self.legends = legends # list of legends per trace (use '' if no legend)
            if minmax != None:            
                if any(isinstance(m, list ) for m in minmax) or any(isinstance(m, tuple) for m in minmax):
                    self.minmax = minmax  # minmax was list or tuple of min and max values
                else:
                    self.minmax = [minmax] * self.nbr_plots # repeat minmax for all plots            
            else:      
                self.minmax = None  # auto range
            self.grouping = grouping
            self.prefix = ','.join(title for title in plot_titles) + '#'
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.client_socket.settimeout(1)
            self.addr = PLOT_ADDR
            print("PlotItf initialized for {} with {} plots".format(main_title, nbr_plots)) 
        except Exception as e:
            print(e, traceback.format_exc())
        
    def plot(self, values): 
        if self.grouping == 'traces' :  #  outer value is nbr traces 
            outer = self.nbr_traces
            inner = self.nbr_plots
            # print("plotting trace groups")
        else: # grouping == plots
            outer = self.nbr_plots
            inner = self.nbr_traces
            # print("plotting plot groups")
        
        rows = len(values) # in trace order, these are plots
        cols = len(values[0]) # in trace order, these are traces
        # print(self.grouping, "rows=", rows, 'cols=', cols)     
       
        if self.grouping == 'traces' : 
            if cols != self.nbr_traces:
                raise ValueError("Expected {} traces, got {}".format(self.nbr_traces, cols))     
            traces = []            
            for row in range(self.nbr_plots):
                plot = []
                for col in range(self.nbr_traces):
                    plot.append(values[row][col])
                traces.append(','.join('{0}:{1:2.3f}'.format(self.legends[idx],trace) for idx, trace in enumerate(plot)))   
          
        elif self.grouping == 'plots':  
            if rows != self.nbr_traces:
                raise ValueError("Expected {} traces, got {}".format(self.nbr_traces, rows))   
            # print(values)        
            traces = []
            for plot in values:
               traces.append(','.join('{0}:{1:2.3f}'.format(self.legends[idx],trace) for idx, trace in enumerate(plot)))
            # print(traces) 
        else:
            raise ValueError("unknown grouping " + self.grouping)
        if self.minmax != None:
            titles = []
            for i in range(self.nbr_plots):
                mm =  '{};{}'.format(self.minmax[i][0], self.minmax[i][1])
                titles.append('{}:{}'.format(self.plot_titles[i], mm))
            prefix = ','.join(title  for title in self.plot_titles) + '#'    
        else: 
            prefix = ','.join(title for title in self.plot_titles) + '#'    
        msg = 'MAIN_TITLE=' + self.main_title + ','+prefix + ';'.join(trace for trace in traces) + '\n'
        # print('{}'.format(msg))
        self.client_socket.sendto(msg.encode(), self.addr)


    
 
if __name__ == "__main__":
    from random import randint

    nbr_plots = 6
    traces_per_plot = 2
    titles = ('x (surge)', 'y (sway)', 'z (heave)', 'roll', 'pitch', 'yaw')
    legends = ('raw', 'washed')
    plotter = PlotItf(nbr_plots, titles, traces_per_plot, legends=legends,  minmax=(-2,2),grouping='traces')
    
    def get_data(grouping):
        plots = []
        if grouping == 'traces':
            outer = traces_per_plot
            inner = nbr_plots
            print("grouping traces")
        else: # grouping == plots
            outer = nbr_plots
            inner = traces_per_plot
            print("grouping plots")
            
        for p in range(outer):
            traces = []
            for t in range(inner):
                traces.append(randint(0,10))
            plots.append(traces)
        return plots    

    for i in range(20):
        data = get_data("traces");
        print(data)
        plotter.plot(data)

"""
def get_wave(step, frequency, amplitude):
    degrees = frequency * 360 * step * interval    
    rad = math.radians(degrees)
    deg2 = frequency * 360 * (step + 11) * interval  
    rad2 =  math.radians(deg2)
    return (math.sin(rad) + math.sin(rad2))*amplitude

def transpose(l1, l2):
    # iterate over the list
    for i in range(len(l1[0])):
        row = [] #to print values
        for j in l1:
            # appending to new list with values and index number
            # j contains values and  i contains index position
            row.append(j[i])
        l2.append(row) #appending value of row list into l2 which is an empty list
    return l2
    
    
def form_message(plot_names, trace_names, data_lists):
    # data lists consist of trace values for each plot 
    try:
        # print(plot_names, trace_names,data_lists)
        combined = []
        for i in range(len(data_lists[0])):
            field = []
            for data in data_lists: 
                field.append(data[i])

            combined.append(field)  
        transposed = []
        # print("combined", combined)
        transposed = transpose(combined, transposed)
        plots = []
        for plot in transposed:
             # print('plot', plot)
             plots.append(','.join('{0}:{1:2.2f}'.format(trace_names[idx],trace) for idx, trace in enumerate(plot)))  
        prefix = ','.join(name for name in plot_names) + '#'
        return prefix + ';'.join( f for f in plots)
    except:
        return None



plots = []
plot_prefixes = []

for i in range(nbr_plots):
    plot = PlotData(plot_names[i], randint(1, nbr_plots), frequency,  max_amplitude)
    plots.append(plot)
    # next line creates plot prefixes that includ emin/max scale
    plot_prefixes.append( '{}:{};{}'.format(plot_names[i], min_max[0], min_max[1]))
prefix = ','.join( prefex for prefex in plot_prefixes)


for step in range(int(dur/interval)):
    trace_data = []
    for plot in  plots:
        trace_data.append(plot.get_data(step))
    msg = prefix + '#' + ';'.join(trace for trace in trace_data)        
    print(msg) 
    udp_send(msg.encode(), ('192.168.1.117',10029))  
    time.sleep(.05)     


dur = 3 # second
interval = .05 # seconds
trace_names = ('trace 1', 'trace 2', 'trace 3') # , 'trace 4', 'trace 5', 'trace 6')
nbr_traces = len(trace_names)
frequency = 1 # hz
max_amplitude = 4 # used to generate waves
min_max = (-10,10) # passed to plotter to set scale
plot_names = ('plot1', 'plot2', 'plot3', 'plot4', 'plot5', 'plot6', 'plot7', 'plot8', 'plot9', 'plot10')
nbr_plots = 6 #  len(plot_names)

"""