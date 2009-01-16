"""workspace.py - the workspace for an imageset
"""
__version__="$Revision: 1 "

import cellprofiler.gui.cpfigure as cpf

class Workspace(object):
    """The workspace contains the processing information and state for
    a pipeline run on an image set
    """
    def __init__(self,pipeline,module,image_set,object_set,measurements,frame=None):
        self.__pipeline = pipeline
        self.__module = module
        self.__image_set = image_set
        self.__object_set = object_set
        self.__measurements = measurements
        self.__frame = frame
        self.__windows_to_refresh = []
    
    def refresh(self):
        """Refresh any windows created during use"""
        for window in self.__windows_to_refresh:
            window.Refresh()

    def get_pipeline(self):
        """Get the pipeline being run"""
        return self.__pipeline
    pipeline = property(get_pipeline)
    
    def get_image_set(self):
        """The image set is the set of images currently being processed
        """
        return self.__image_set
    image_set = property(get_image_set)

    def get_object_set(self):
        """The object set is the set of image labels for the current image set
        """
        return self.__object_set

    object_set = property(get_object_set)

    def get_measurements(self):
        """The measurements contain measurements made on images and objects
        """
        return self.__measurements

    measurements = property(get_measurements)

    def get_frame(self):
        """The frame is CellProfiler's gui window

        If the frame is present, a module should do its display
        """
        return self.__frame

    frame = property(get_frame)
    
    def get_display(self):
        """True to provide a gui display"""
        return self.__frame != None
    display = property(get_display)
    
    def create_or_find_figure(self,title=None,subplots=None,window_name = None):
        """Create a matplotlib figure window or find one already created"""
        if title==None:
            title=self.__module.module_name
            
        if window_name == None:
            window_name = "CellProfiler:%s:%s"%(self.__module.module_name,
                                                self.__module.module_num)
        figure = cpf.create_or_find(self.__frame, title, window_name, subplots)
        if not figure in self.__windows_to_refresh:
            self.__windows_to_refresh.append(figure)
        return figure
