import glob

from lxml import etree


def scan_codelists(dir_codelists):
    gml_dict = dict()
    for filename in glob.glob(dir_codelists + "/*.xml"):
        tree = etree.parse(filename)
        root = tree.getroot()
        # gml:name
        vals = tree.xpath("/gml:Dictionary/gml:name", namespaces=root.nsmap)
        if len(vals) > 0:
            title_name = vals[0].text
            gml_dict[title_name] = dict()
            defs = tree.xpath(
                "/gml:Dictionary/gml:dictionaryEntry/gml:Definition",
                namespaces=root.nsmap,
            )
            # pair of description and name
            for deff in defs:
                description = deff.xpath("gml:description", namespaces=root.nsmap)[
                    0
                ].text
                name = deff.xpath("gml:name", namespaces=root.nsmap)[0].text
                gml_dict[title_name][name] = description
    return gml_dict
