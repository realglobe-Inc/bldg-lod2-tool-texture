class PlOptions:
    def __init__(self) -> None:
        # show LOD2 texture
        self.b_use_lod2_texture = False
        self.texture_dir = "cached"
        # use LOD0
        self.b_use_lod0 = False
        # force height = 0
        self.b_height_zero = False
        # divide the mesh 'AAAABB' automatically into the quarter, the group of 'AAAAABBCC'.
        #  specify (0,0)or(0,1)or(1,0)or(1,1)  as lat,lon
        #  Now, it is very hard-coded.  Do not use it.
        self.div_6_to_quarter = None
