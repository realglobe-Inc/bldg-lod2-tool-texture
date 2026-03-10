from .pl_obj import PlObj
from .pl_options import PlOptions


class PlLuse(PlObj):
    def __init__(self, filename=None, options=PlOptions()):
        super().__init__()
        self.kind_str = "luse"
        if filename is not None:
            self.load_file(filename, options=options)

    def load_file(self, filename, options=PlOptions()):
        pass
